"""Dérive des sources directes : une source qui répond encore, mais plus comme d'habitude.

La surveillance (cotes/surveillance.py) voit une source qui tombe ou qui refuse. Elle ne voit pas une source lue
« sans erreur » dont le contenu a changé : format modifié, libellés renommés, cache figé. Ce module compare chaque
source à sa propre habitude récente, cycle après cycle, sur quatre signaux :

- ``volume`` : cotes (ou matchs) sous ``CHUTE_VOLUME`` de l'habituel ; une lecture vide sans erreur en fait partie ;
- ``marche`` : un marché d'un sport (« football TOTAL MATCH ») presque disparu, mesuré par la part des matchs de ce
  sport qui l'ont (le nombre de matchs du jour ne joue donc pas) ;
- ``inconnus`` : part d'offres qu'aucun traducteur ne reconnaît (cotes/inconnus.py) en forte hausse ;
- ``figees`` : aucune cote de la source n'a changé depuis ``FIGEES_MIN`` minutes (bookmakers français seulement, les
  seuls dont l'historique a permis de régler le seuil : docs/durer.md).

L'habitude d'une série est une moyenne glissante exponentielle (mémoire ``TAU_MIN``). Elle n'est jugée qu'après
``RODAGE_MIN`` d'apprentissage, et une anomalie ne compte qu'après ``DUREE_MIN``. Pendant l'anomalie l'habitude ne
bouge pas ; au bout de ``ADOPTION_MIN`` le nouveau niveau devient l'habitude (changement durable, déjà signalé).
Tout est en minutes, jamais en cycles : mêmes durées sur GitHub (5 min) et sur le serveur en direct (1 min).

L'état vit dans la mémoire de travail (cotes/memoire.py, ``derive_sources``), hors de la branche « donnees » ;
perdu, il se réapprend en une heure. Une anomalie marque l'étape « dégradée » (page Santé, journal d'incidents) et
envoie un message Pushover, une fois par source et par signal. Aucun pari n'est bloqué. Ne lève jamais.
"""
from __future__ import annotations

import math
import os
import zlib
from collections import defaultdict
from datetime import datetime
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from . import memoire
from .pannes import URL

FICHIER = "derive_sources"
PREFIXE = "dérive : "
TAU_MIN = 60.0
RODAGE_MIN = 60.0
DUREE_MIN = 15.0
ADOPTION_MIN = 360.0
PERIME_MIN = 360.0                  # série plus mise à jour depuis : réapprise
OUBLI_MIN = 3 * 1440.0              # marché plus vu depuis : oublié
CHUTE_VOLUME = 0.5
LIGNES_MIN = 50                     # habitude en dessous : trop peu pour juger une chute
CHUTE_COUVERTURE = 0.3              # marché présent sur moins de 30 % de sa part habituelle des matchs
COUVERTURE_MIN = 0.3                # seuls les marchés habituellement présents sur 30 % des matchs du sport
MATCHS_MIN = 10                     # matchs du sport chez la source pour mesurer ses marchés
HAUSSE_INCONNUS = 2.0               # part d'offres non reconnues doublée…
INCONNUS_PLANCHER = 0.10            # … et en hausse d'au moins 10 points
LIGNES_FIGEES_MIN = 200
# Plus longue durée sans aucun changement de cote, hors panne connue, du 30/10 au 14/11/2026 : Betclic 5 min,
# NetBet 15 min, OlyBet moins de 5 min, Unibet moins de 30 min, Winamax 111 min (nuit). PMU : 45 min, sauf deux
# épisodes de 75 min, dont celui du 10/11 de 08:15 à 09:30 UTC, en journée, pendant que Betclic et Winamax
# bougeaient et sans incident au journal : c'est le cas à attraper, d'où 60 min.
FIGEES_MIN = {"betclic": 45.0, "netbet": 45.0, "olybet": 45.0, "pmu": 60.0, "unibet-fr": 90.0, "winamax": 150.0}
# source (champ « bookmaker » des cotes) -> étape du journal de cycle
ETAPES = {"pmu": "pmu_direct", "winamax": "winamax_direct", "betclic": "betclic_direct", "unibet-fr": "unibet_direct",
          "olybet": "olybet", "netbet": "netbet", "pinnacle": "pinnacle", "polymarket": "polymarket",
          "matchbook": "matchbook", "smarkets": "smarkets"}
NOMS = {"pmu": "PMU", "winamax": "Winamax", "betclic": "Betclic", "unibet-fr": "Unibet", "olybet": "OlyBet",
        "netbet": "NetBet", "pinnacle": "Pinnacle", "polymarket": "Polymarket", "matchbook": "Matchbook",
        "smarkets": "Smarkets"}
_MASQUE = (1 << 64) - 1


def mesurer(lignes, prix: bool = True) -> dict:
    """Mesures d'une source sur un cycle : volume, matchs par sport, part des matchs qui ont chaque marché et, si
    ``prix``, une empreinte des prix indépendante de l'ordre (elle change dès qu'une cote change, apparaît ou
    disparaît)."""
    matchs, marches, somme, n = defaultdict(set), defaultdict(set), 0, 0
    for l in lignes or ():
        if not isinstance(l, dict):
            continue
        n += 1
        match, sport, marche = l.get("match_id"), str(l.get("sport") or "?"), str(l.get("marche") or "?")
        matchs[sport].add(match)
        if not marche.startswith("JOUEUR:"):
            marches[(sport, marche, str(l.get("periode") or "?"))].add(match)
        if prix:
            texte = f"{match}|{marche}|{l.get('periode')}|{l.get('ligne')}|{l.get('issue')}|{l.get('joueur')}|{l.get('cote')}"
            somme = (somme + zlib.crc32(texte.encode("utf-8", "replace")) * 2654435761) & _MASQUE
    sports = {s: len(m) for s, m in matchs.items()}
    return {"lignes": n, "matchs": sum(sports.values()), "sports": sports, "empreinte": somme,
            "couverture": {" ".join(k): round(len(m) / sports[k[0]], 4) for k, m in marches.items()
                           if sports[k[0]] >= MATCHS_MIN}}


def _minutes(depuis, maintenant: datetime) -> float | None:
    try:
        return (maintenant - datetime.fromisoformat(str(depuis))).total_seconds() / 60
    except (TypeError, ValueError):
        return None


def _serie(s, valeur: float, maintenant: datetime, hausse: bool, facteur: float, plancher: float = 0.0,
           minimum: float = 0.0) -> tuple[dict, bool]:
    """(état suivant de la série, anomalie établie depuis au moins ``DUREE_MIN``)."""
    iso = maintenant.isoformat(timespec="seconds")
    ecoule = _minutes((s or {}).get("vu"), maintenant)
    appris = _minutes((s or {}).get("debut"), maintenant)
    if not s or ecoule is None or appris is None or not 0 <= ecoule <= PERIME_MIN or not isinstance(s.get("ref"), (int, float)):
        return {"ref": round(float(valeur), 4), "debut": iso, "vu": iso}, False
    ref = float(s["ref"])
    suivant = {"ref": ref, "debut": s["debut"], "vu": iso}
    anormal = appris >= RODAGE_MIN and ref >= minimum and (
        valeur > max(ref * facteur, ref + plancher) if hausse else valeur < ref * facteur)
    if anormal:
        depuis = s.get("anomalie") or iso
        duree = _minutes(depuis, maintenant) or 0.0
        if duree >= ADOPTION_MIN:
            suivant["ref"] = round(float(valeur), 4)
            return suivant, False
        suivant["anomalie"] = depuis
        return suivant, duree >= DUREE_MIN
    suivant["ref"] = round(ref + (1 - math.exp(-ecoule / TAU_MIN)) * (valeur - ref), 4)
    return suivant, False


def _nombre(n: float) -> str:
    return f"{n:,.0f}".replace(",", " ")


def _juger_source(source: str, e: dict, m: dict, maintenant: datetime) -> tuple[dict, list[dict]]:
    iso = maintenant.isoformat(timespec="seconds")
    series, constats = dict(e.get("series") or {}), []

    def juger(nom, valeur, **regles):
        series[nom], actif = _serie(series.get(nom), valeur, maintenant, **regles)
        return series[nom] if actif else None

    volume = juger("lignes", m["lignes"], hausse=False, facteur=CHUTE_VOLUME, minimum=LIGNES_MIN)
    matchs = juger("matchs", m["matchs"], hausse=False, facteur=CHUTE_VOLUME, minimum=MATCHS_MIN)
    for nom, s, valeur, mot in (("volume", volume, m["lignes"], "cotes"), ("volume", matchs, m["matchs"], "matchs")):
        if s and not any(c["genre"] == nom for c in constats):
            constats.append({"genre": nom, "depuis": s["anomalie"],
                             "detail": f"{_nombre(valeur)} {mot}, {_nombre(s['ref'])} d'habitude"})
    disparus = []
    for cle in {k[2:] for k in series if k.startswith("c:")} | set(m["couverture"]):
        if m["sports"].get(cle.split(" ")[0], 0) < MATCHS_MIN:
            continue                    # sport presque absent ce cycle : ses marchés ne sont pas jugés
        part = m["couverture"].get(cle, 0.0)
        s = juger("c:" + cle, part, hausse=False, facteur=CHUTE_COUVERTURE, minimum=COUVERTURE_MIN)
        if s:
            disparus.append((s["anomalie"], cle, part, s["ref"]))
    if disparus:
        disparus.sort()
        liste = ", ".join(f"{cle} ({part:.0%} des matchs, {ref:.0%} d'habitude)" for _, cle, part, ref in disparus[:3])
        constats.append({"genre": "marche", "depuis": disparus[0][0],
                         "detail": f"{len(disparus)} marché{'s' if len(disparus) > 1 else ''} presque "
                                   f"disparu{'s' if len(disparus) > 1 else ''} : {liste}"})
    if m.get("inconnus") is not None:
        total = m["inconnus"] + m["lignes"]
        part = m["inconnus"] / total if total else 0.0
        s = juger("inconnus", part, hausse=True, facteur=HAUSSE_INCONNUS, plancher=INCONNUS_PLANCHER)
        if s:
            frequents = ", ".join(f"« {lib} » ×{n}" for lib, n in (m.get("frequents") or [])[:3])
            constats.append({"genre": "inconnus", "depuis": s["anomalie"],
                             "detail": f"{part:.0%} d'offres non reconnues, {s['ref']:.0%} d'habitude"
                                       + (f" : {frequents}" if frequents else "")})
    for nom in [k for k, s in series.items() if (_minutes(s.get("vu"), maintenant) or 0) > OUBLI_MIN]:
        del series[nom]
    prix = dict(e.get("prix") or {})
    absence = _minutes(e.get("vu"), maintenant)
    if prix.get("empreinte") != m["empreinte"] or absence is None or absence > 4 * DUREE_MIN:
        prix = {"empreinte": m["empreinte"], "change": iso}     # retour de panne : l'horloge repart
    elif source in FIGEES_MIN and m["lignes"] >= LIGNES_FIGEES_MIN:
        duree = _minutes(prix.get("change"), maintenant) or 0.0
        if duree >= FIGEES_MIN[source]:
            constats.append({"genre": "figees", "depuis": prix["change"],
                             "detail": f"aucune cote n'a changé depuis {duree:.0f} min ({_nombre(m['lignes'])} cotes)"})
    alertes = {g: t for g, t in (e.get("alertes") or {}).items() if any(c["genre"] == g for c in constats)}
    for c in constats:
        c["nouveau"] = c["genre"] not in alertes
        alertes.setdefault(c["genre"], iso)
    return {"series": series, "prix": prix, "alertes": alertes, "vu": iso}, constats


def suivre(etat: dict, mesures: dict[str, dict], maintenant: datetime) -> tuple[dict, dict[str, list[dict]]]:
    """(état suivant, {source: constats}). Une source non mesurée ce cycle (panne, coupée) garde son état. Pur."""
    etat = etat if isinstance(etat, dict) else {}
    suivant, constats = {k: v for k, v in etat.items() if k not in mesures}, {}
    for source, m in mesures.items():
        avant = etat.get(source) if isinstance(etat.get(source), dict) else {}
        suivant[source], vus = _juger_source(source, avant, m, maintenant)
        if vus:
            constats[source] = vus
    return suivant, constats


def messages(constats: dict[str, list[dict]]) -> dict[str, list[str]]:
    """{étape du journal: [texte]} pour marquer les étapes dégradées (page Santé, journal d'incidents)."""
    return {ETAPES[s]: [PREFIXE + c["detail"] for c in vus] for s, vus in constats.items() if s in ETAPES}


def envoyer(constats: dict[str, list[dict]], env=None, ouvrir=urlopen) -> bool:
    """Un message Pushover pour les constats nouveaux. Faux si rien n'est parti (pas de clé, échec)."""
    env = os.environ if env is None else env
    jeton, cle = env.get("PUSHOVER_APP_TOKEN", "").strip(), env.get("PUSHOVER_USER_KEY", "").strip()
    lignes = [f"{NOMS.get(s, s)} : {c['detail']} (depuis {str(c['depuis'])[11:16]} UTC)"
              for s, vus in constats.items() for c in vus if c.get("nouveau")]
    if not lignes or not jeton or not cle:
        return False
    corps = {"token": jeton, "user": cle, "title": f"Source qui dérive ({len(lignes)})", "message": "\n".join(lignes)[:1000]}
    try:
        with ouvrir(Request(URL, data=urlencode(corps).encode(), method="POST",
                            headers={"User-Agent": "cotes-value"}), timeout=10) as r:
            return 200 <= getattr(r, "status", 200) < 300
    except Exception:  # noqa: BLE001
        return False


def mesures_du_cycle(etapes: dict, lignes_par_source: dict[str, list], releve_inconnus: dict | None = None) -> dict:
    """Mesures des sources lues normalement ce cycle. Étape en panne, coupée ou servie depuis un cache : pas de
    mesure (la panne est déjà suivie ailleurs, et une lecture en mémoire ne dit rien de la source)."""
    out = {}
    for source, nom in ETAPES.items():
        v = (etapes or {}).get(nom)
        if not isinstance(v, dict) or not v.get("ok") or v.get("desactive") or v.get("cache"):
            continue
        m = mesurer(lignes_par_source.get(source) or [], prix=source in FIGEES_MIN)
        if source in FIGEES_MIN:            # bookmakers français : les seuls à noter leurs marchés non reconnus
            releve = (releve_inconnus or {}).get(source) or {}
            m["inconnus"] = sum(releve.values())
            m["frequents"] = sorted(releve.items(), key=lambda kv: -kv[1])[:3]
        out[source] = m
    return out


def mettre_a_jour(donnees, mesures: dict[str, dict], maintenant: datetime, env=None, ouvrir=urlopen) -> dict:
    """Lit l'état, juge le cycle, alerte, réécrit l'état. Rend le résumé publié dans le journal de cycle."""
    try:
        etat = memoire.lire(donnees, FICHIER, {}, ancien_aussi=False)
        suivant, constats = suivre(etat, mesures, maintenant)
        nouveaux = sum(1 for vus in constats.values() for c in vus if c.get("nouveau"))
        envoye = bool(nouveaux) and envoyer(constats, env, ouvrir)
        if nouveaux and not envoye:         # pas parti : nouvel essai au cycle suivant
            for source, vus in constats.items():
                for c in vus:
                    if c.get("nouveau"):
                        suivant[source]["alertes"].pop(c["genre"], None)
        memoire.ecrire(donnees, FICHIER, suivant, retirer_ancien=False)
        return {"sources": len(mesures), "constats": constats, "etapes": messages(constats), "alerte_envoyee": envoye}
    except Exception as e:  # noqa: BLE001
        return {"sources": 0, "constats": {}, "etapes": {}, "erreur": type(e).__name__}
