"""Secours Pinnacle : les cotes d'avant-match de pinnodds (puis de PinBook), quand l'API publique de Pinnacle échoue.

pinnodds revend le flux de Pinnacle (REST, sans compte Pinnacle). Le secours ne s'allume que si
``PINNODDS_API_KEY`` existe et seulement pour les sports où la lecture directe a répondu en erreur
HTTP (403, 503…), ou n'a rendu que des cotes périmées pour un sport de ``PINNACLE_SECOURS_PERIME``
(football par défaut ; « non » coupe) : tant que Pinnacle répond à temps, aucune requête n'est faite.
Depuis la maintenance du 19/10/2026, toute l'API invitée est servie avec ``max-age=905`` : chaque
lecture a de 0 à 15 minutes, et un cycle sur trois environ n'a que des cotes de plus de 10 minutes.
Les lignes ont le même format que ``pinnacle.collecter`` (``source`` « pinnacle », ``origine`` « pinnodds »), avec leur probabilité juste.

Prudence :
- seuls les marchés sans ambiguïté sont repris : résultat, vainqueur et totaux (période et sport selon
  ``pinnacle.PERIODES``). Les handicaps et les totaux par équipe ne le sont qu'avec
  ``PINNODDS_HANDICAPS=oui``, après comparaison avec la lecture directe (scripts/comparer_secours_pinnacle.py) ;
- pinnodds retient sa grille quand ses données sont périmées (``X-Data-Status: stale``) : le secours
  ne renvoie alors rien, jamais de vieilles cotes ;
- l'offre gratuite plafonne à 100 requêtes par jour : ``PINNODDS_LIMITE_JOUR`` (90 par défaut) et
  ``PINNODDS_PAUSE_MIN`` (30 minutes entre deux lectures par défaut). Avec un abonnement, relever la
  limite et mettre la pause à 0 ;
- entre deux lectures, le dernier passage est rejoué avec son âge réel (``pinnacle_secours_cache.json``) :
  une ligne plus vieille que ``PINNACLE_AGE_MAX_MIN`` reste marquée périmée et ne sert pas de référence ;
- PinBook (``PINBOOK_API_KEY``, offre gratuite RapidAPI : 550 requêtes par mois) passe après pinnodds et ne comble
  que les sports sans ligne fraîche : ``PINBOOK_SPORTS`` (football, tennis, basket par défaut),
  ``PINBOOK_LIMITE_JOUR`` (16 par défaut) et ``PINBOOK_PAUSE_MIN`` (60 par défaut). Sa fraîcheur vient de ``last_call``.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import requests

from . import pinnacle

BASE = "https://pinnodds.com"
# sport Pinnacle -> identifiant pinnodds (volley et handball ont chacun leur identifiant)
SPORTS_PINNODDS = {29: 1, 33: 2, 4: 3, 19: 4, 15: 5, 3: 6, 22: 8, 6: 9, 34: 14, 18: 15}
LIMITE_JOUR_DEFAUT = 90
PAUSE_MIN_DEFAUT = 30
HOTE_PINBOOK = "pinbook-odds.p.rapidapi.com"
# sport Pinnacle -> identifiant PinBook (mêmes identifiants que pinnodds) ; football, tennis et basket par défaut
SPORTS_PINBOOK_DEFAUT = "football,tennis,basket"
PINBOOK_LIMITE_JOUR_DEFAUT = 16     # 550 requêtes par mois en gratuit : 16 par jour en laisse environ 50 de marge
PINBOOK_PAUSE_MIN_DEFAUT = 60
# Sports relus quand toutes leurs cotes directes sont périmées. Football seul par défaut : une requête
# toutes les 30 minutes au plus, soit 48 par jour, ce qui laisse l'autre moitié du quota aux pannes.
SPORTS_SI_PERIME_DEFAUT = "football"
CACHE_MAX_H = 3                    # au-delà, le cache n'est plus rejoué du tout
ERREURS: list[str] = []
RESUME: dict = {}


def cle() -> str:
    return os.environ.get("PINNODDS_API_KEY", "").strip()


def cle_pinbook() -> str:
    return os.environ.get("PINBOOK_API_KEY", "").strip()


def disponible() -> bool:
    return bool(cle() or cle_pinbook())


def sports_pinbook() -> set[int]:
    """Sports Pinnacle que PinBook peut combler (noms de PINBOOK_SPORTS, par défaut football, tennis, basket)."""
    noms = {n.strip().lower() for n in (os.environ.get("PINBOOK_SPORTS", "").strip() or SPORTS_PINBOOK_DEFAUT).split(",")}
    return {sid for sid, nom in pinnacle.SPORTS.items() if nom in noms and sid in SPORTS_PINNODDS}


def _entier_env(nom: str, defaut: int) -> int:
    try:
        return max(0, int(os.environ.get(nom, "").strip() or defaut))
    except ValueError:
        return defaut


def sports_si_perime() -> set[int]:
    """Sports Pinnacle de PINNACLE_SECOURS_PERIME (noms séparés par des virgules, « non » pour couper)."""
    brut = os.environ.get("PINNACLE_SECOURS_PERIME", "").strip().lower() or SPORTS_SI_PERIME_DEFAUT
    if brut in ("non", "0", "false", "off"):
        return set()
    noms = {n.strip() for n in brut.split(",")}
    return {sid for sid, nom in pinnacle.SPORTS.items() if nom in noms and sid in SPORTS_PINNODDS}


def sports_en_retard(pin: list[dict]) -> set[int]:
    """Sports de PINNACLE_SECOURS_PERIME lus en direct mais sans aucune cote fraîche."""
    out = set()
    for sid in sports_si_perime():
        lignes = [l for l in pin if isinstance(l, dict) and l.get("sport") == pinnacle.SPORTS[sid]]
        if lignes and all(l.get("cote_perimee") for l in lignes):
            out.add(sid)
    return out


def sports_a_secourir(erreurs: list[str], pin: list[dict]) -> set[int]:
    """Sports de Pinnacle en échec HTTP ou en retard ; tous si la lecture directe n'a rien rendu et signale une erreur."""
    if not pin and erreurs:
        return set(SPORTS_PINNODDS)
    en_echec = {int(m.group(1)) for e in erreurs if (m := re.match(r"sport (\d+) .*HTTP \d{3}", str(e)))}
    return (en_echec | sports_en_retard(pin)) & set(SPORTS_PINNODDS)


def _cote(x) -> float | None:
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    return float(x) if 1.0 < x < 1000 and x == x else None


def _lignes_evenement(ev: dict, sport: str, base: dict, handicaps: bool, maintenant: datetime | None = None) -> list[dict]:
    dom, ext = ev.get("home"), ev.get("away")
    if (not isinstance(dom, str) or not isinstance(ext, str) or not dom or not ext or dom == ext
            or ev.get("special") or not ev.get("is_have_odds") or ev.get("event_type", "prematch") != "prematch"):
        return []
    debut = _heure(ev.get("starts"))
    if debut is None or debut <= (maintenant or datetime.now(timezone.utc)):
        return []
    eid = ev.get("event_id")
    if isinstance(eid, bool) or not isinstance(eid, (int, str)):
        return []
    periodes = pinnacle.PERIODES.get(sport, {0: "MATCH"})
    commun = {**base, "ligue": ev.get("league_name"), "match_id": eid, "domicile": dom, "exterieur": ext,
              "debut": debut.isoformat().replace("+00:00", "Z"), "joueur": None}
    out = []

    def ajouter(cle_marche, marche, periode, ligne, issues, maximum):
        for issue, cote in issues:
            out.append({**commun, "marche": marche, "periode": periode, "ligne": ligne, "issue": issue,
                        "cote": cote, "cle_marche": f"{eid}|{cle_marche}", "mise_max": pinnacle._nombre(maximum)})

    for nom, p in (ev.get("periods") or {}).items():
        m = re.fullmatch(r"num_(\d+)", str(nom))
        periode = periodes.get(int(m.group(1))) if m and isinstance(p, dict) else None
        if periode is None:
            continue
        num = m.group(1)
        ml = p.get("money_line") or {}
        d, h, a = _cote(ml.get("draw")), _cote(ml.get("home")), _cote(ml.get("away"))
        if h and a:
            issues = [("DOM", h), ("NUL", d), ("EXT", a)] if d else [("DOM", h), ("EXT", a)]
            ajouter(f"{num}|ml", "RESULTAT_1N2" if d else "VAINQUEUR", periode, None, issues, None)
        if sport == "tennis":
            continue                   # en tennis, handicaps et totaux principaux sont en sets ou en jeux : non repris
        for pts, t in (p.get("totals") or {}).items():
            ligne, o, u = pinnacle._nombre(t.get("points")), _cote(t.get("over")), _cote(t.get("under"))
            if ligne is not None and o and u:
                ajouter(f"{num}|total|{ligne}", "TOTAL", periode, ligne, [("PLUS", o), ("MOINS", u)], t.get("max"))
        if not handicaps:
            continue
        for hdp, s in (p.get("spreads") or {}).items():
            ligne, h2, a2 = pinnacle._nombre(s.get("hdp")), _cote(s.get("home")), _cote(s.get("away"))
            if ligne is not None and h2 and a2:       # ligne = handicap de l'équipe à domicile
                ajouter(f"{num}|spread|{ligne}", "HANDICAP", periode, ligne, [("DOM", h2), ("EXT", a2)], s.get("max"))
        for cote_eq, marche in (("home", "TOTAL_DOM"), ("away", "TOTAL_EXT")):
            lignes_eq = ((p.get("team_totals") or {}).get(cote_eq)
                         or ({"x": (p.get("team_total") or {}).get(cote_eq)} if (p.get("team_total") or {}).get(cote_eq) else {}))
            for t in lignes_eq.values():
                ligne, o, u = pinnacle._nombre(t.get("points")), _cote(t.get("over")), _cote(t.get("under"))
                if ligne is not None and o and u:
                    ajouter(f"{num}|tt{cote_eq}|{ligne}", marche, periode, ligne, [("PLUS", o), ("MOINS", u)], t.get("max"))
    return out


def _lire_sport(session, sid_pinnodds: int):
    """(événements, âge en secondes) ou (None, None) ; une réponse périmée ou en erreur ne donne rien."""
    r = session.get(f"{BASE}/kit/v1/prematch/fixtures", params={"sport_id": sid_pinnodds},
                    headers={"x-portal-apikey": cle(), "Accept": "application/json"}, timeout=25)
    if r.status_code == 429:
        ERREURS.append("pinnodds : limite de requêtes atteinte (HTTP 429)")
        return None, None
    if r.status_code != 200:
        ERREURS.append(f"pinnodds sport {sid_pinnodds} : HTTP {r.status_code}")
        return None, None
    if str(r.headers.get("X-Data-Status", "fresh")).lower() == "stale":
        ERREURS.append(f"pinnodds sport {sid_pinnodds} : données périmées chez pinnodds")
        return None, None
    try:
        evenements = r.json().get("events") or []
    except (ValueError, AttributeError):
        ERREURS.append(f"pinnodds sport {sid_pinnodds} : JSON invalide")
        return None, None
    try:
        age = int(r.headers.get("X-Data-Age-Ms")) // 1000
    except (TypeError, ValueError):
        age = None
    return evenements, age


def _lire_pinbook(session, sid_pinbook: int):
    """(événements, âge en secondes d'après last_call) ou (None, None)."""
    r = session.get(f"https://{HOTE_PINBOOK}/kit/v1/markets", timeout=40,
                    params={"sport_id": sid_pinbook, "is_have_odds": 1, "event_type": "prematch"},
                    headers={"x-rapidapi-key": cle_pinbook(), "x-rapidapi-host": HOTE_PINBOOK})
    if r.status_code == 429:
        ERREURS.append("pinbook : limite de requêtes atteinte (HTTP 429)")
        return None, None
    if r.status_code != 200:
        ERREURS.append(f"pinbook sport {sid_pinbook} : HTTP {r.status_code}")
        return None, None
    try:
        corps = r.json()
        evenements = corps.get("events") or []
    except (ValueError, AttributeError):
        ERREURS.append(f"pinbook sport {sid_pinbook} : JSON invalide")
        return None, None
    try:
        age = max(0, int(datetime.now(timezone.utc).timestamp() - float(corps.get("last_call"))))
    except (TypeError, ValueError):
        age = None
    return evenements, age


def _etat_budget(chemin: Path | None, maintenant: datetime) -> dict:
    etat = {}
    if chemin is not None and chemin.exists():
        try:
            etat = json.loads(chemin.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            etat = {}
    if not isinstance(etat, dict) or etat.get("jour") != f"{maintenant:%Y-%m-%d}":
        etat = {"jour": f"{maintenant:%Y-%m-%d}", "requetes": 0, "dernier": None}
    return etat


def _bloc(etat: dict, nom: str) -> dict:
    """Compteur d'un fournisseur : pinnodds à la racine (historique du fichier), PinBook dans « pinbook »."""
    return etat if nom == "pinnodds" else etat.setdefault("pinbook", {"requetes": 0, "dernier": None})


def _passer(nom: str, sports: set[int], etat: dict, maintenant: datetime, session, handicaps: bool) -> dict[int, list[dict]]:
    """Une lecture chez un fournisseur, dans la pause et le budget du jour ; sport Pinnacle -> lignes avec proba."""
    if nom == "pinnodds":
        pause = _entier_env("PINNODDS_PAUSE_MIN", PAUSE_MIN_DEFAUT)
        limite = _entier_env("PINNODDS_LIMITE_JOUR", LIMITE_JOUR_DEFAUT)
        correspondance, lire = SPORTS_PINNODDS, _lire_sport
    else:
        pause = _entier_env("PINBOOK_PAUSE_MIN", PINBOOK_PAUSE_MIN_DEFAUT)
        limite = _entier_env("PINBOOK_LIMITE_JOUR", PINBOOK_LIMITE_JOUR_DEFAUT)
        correspondance, lire = SPORTS_PINNODDS, _lire_pinbook
    bloc = _bloc(etat, nom)
    if bloc.get("dernier"):
        try:
            depuis = (maintenant - datetime.fromisoformat(bloc["dernier"])).total_seconds() / 60
        except (TypeError, ValueError):
            depuis = None
        if depuis is not None and depuis < pause:
            RESUME["pause"] = True
            return {}
    par_sport: dict[int, list[dict]] = {}
    lus = 0
    for sid in sorted(sports & set(correspondance)):
        if bloc["requetes"] >= limite:
            ERREURS.append(f"{nom} : limite journalière du secours atteinte")
            break
        bloc["requetes"] += 1
        lus += 1
        RESUME["requetes"] += 1
        try:
            evenements, age = lire(session, correspondance[sid])
        except requests.RequestException as e:
            ERREURS.append(f"{nom} sport {sid} : {type(e).__name__}")
            continue
        if evenements is None:
            continue
        instant = datetime.now(timezone.utc).isoformat(timespec="seconds")
        sport = pinnacle.SPORTS[sid]
        base = {"source": "pinnacle", "origine": nom, "sport": sport, "collecte": instant,
                "collecte_debut": instant, "collecte_recue": instant, "age_cache_s": age,
                "cote_perimee": age is None or age > pinnacle.age_max_secondes()}
        lues = [l for ev in evenements if isinstance(ev, dict) for l in _lignes_evenement(ev, sport, base, handicaps, maintenant)]
        pinnacle._ajouter_proba_justes(lues)
        par_sport[sid] = [l for l in lues if l.get("proba_juste")]      # un marché incomplet ou incohérent ne sert pas
        RESUME["sports"].append(sport)
    if lus:
        bloc["dernier"] = maintenant.isoformat(timespec="seconds")
    return par_sport


def collecter(sports: set[int], maintenant: datetime | None = None, donnees: Path | None = None,
              session=None) -> list[dict]:
    """Lignes de secours pour les sports Pinnacle demandés ; [] sans clé.

    pinnodds d'abord, puis PinBook pour les sports restés sans ligne fraîche. Pause ou budget épuisé :
    le dernier passage est rejoué avec son âge réel."""
    ERREURS.clear()
    RESUME.clear()
    maintenant = maintenant or datetime.now(timezone.utc)
    RESUME.update({"sports": [], "requetes": 0, "lignes": 0, "erreurs": ERREURS})
    if not disponible():
        return []
    chemin = donnees / "pinnacle_secours.json" if donnees is not None else None
    chemin_cache = donnees / "pinnacle_secours_cache.json" if donnees is not None else None
    etat = _etat_budget(chemin, maintenant)
    handicaps = os.environ.get("PINNODDS_HANDICAPS", "").strip().lower() == "oui"
    session = session or requests.Session()
    demandes = sports & set(SPORTS_PINNODDS)
    par_sport: dict[int, list[dict]] = {}
    if cle():
        par_sport.update(_passer("pinnodds", demandes, etat, maintenant, session, handicaps))
    if cle_pinbook():
        # seulement les sports sans ligne fraîche (ni lecture, ni cache encore valable) : on ménage les 550 requêtes
        frais = {sid for sid in demandes
                 if any(not l.get("cote_perimee") for l in par_sport.get(sid, []) + _lire_cache(chemin_cache, {sid}, maintenant))}
        trous = (demandes & sports_pinbook()) - frais
        if trous:
            par_sport.update(_passer("pinbook", trous, etat, maintenant, session, handicaps))
    if RESUME["requetes"] and chemin is not None:
        chemin.write_text(json.dumps(etat), encoding="utf-8")
    rejoues = _lire_cache(chemin_cache, demandes - set(par_sport), maintenant)
    _ecrire_cache(chemin_cache, {sid: [l for l in ls if isinstance(l.get("age_cache_s"), int)] for sid, ls in par_sport.items()}, maintenant)
    RESUME["cache_lignes"] = len(rejoues)
    lignes = [l for ls in par_sport.values() for l in ls] + rejoues
    RESUME["lignes"] = len(lignes)
    return lignes


def _lire_cache(chemin: Path | None, sports: set[int], maintenant: datetime) -> list[dict]:
    """Lignes du dernier passage des sports demandés, avec leur âge réel ; [] si rien d'exploitable."""
    if chemin is None or not chemin.exists():
        return []
    try:
        cache = json.loads(chemin.read_text(encoding="utf-8")).get("sports", {})
    except (OSError, ValueError, AttributeError):
        return []
    out: list[dict] = []
    for sid in sports:
        bloc = cache.get(str(sid)) if isinstance(cache, dict) else None
        try:
            lu = datetime.fromisoformat(bloc["lu"])
            ecoule = (maintenant - lu).total_seconds()
            lignes = bloc["lignes"]
        except (TypeError, KeyError, ValueError):
            continue
        if not isinstance(lignes, list) or not 0 <= ecoule <= CACHE_MAX_H * 3600:
            continue
        for l in lignes:
            if not isinstance(l, dict) or not isinstance(l.get("age_cache_s"), int):
                continue
            debut = _debut(l)
            if debut is None or debut <= maintenant:
                continue
            age = l["age_cache_s"] + int(ecoule)
            out.append({**l, "age_cache_s": age, "cote_perimee": age > pinnacle.age_max_secondes()})
    return out


def _heure(valeur):
    """Heure ISO en UTC ; sans fuseau (PinBook), l'heure est déjà en GMT."""
    try:
        t = datetime.fromisoformat(str(valeur).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t


def _debut(ligne: dict):
    return _heure(ligne.get("debut"))


def _ecrire_cache(chemin: Path | None, par_sport: dict[int, list[dict]], maintenant: datetime) -> None:
    if chemin is None or not par_sport:
        return
    try:
        cache = json.loads(chemin.read_text(encoding="utf-8")).get("sports", {}) if chemin.exists() else {}
    except (OSError, ValueError, AttributeError):
        cache = {}
    if not isinstance(cache, dict):
        cache = {}
    for sid, lignes in par_sport.items():
        cache[str(sid)] = {"lu": maintenant.isoformat(timespec="seconds"), "lignes": lignes}
    chemin.write_text(json.dumps({"sports": cache}, separators=(",", ":")), encoding="utf-8")


def comparer(direct: list[dict], secours: list[dict]) -> dict:
    """Couverture et écarts de cotes entre la lecture directe et le secours (mêmes match, marché, ligne, issue)."""
    def cle_ligne(l):
        return (l["match_id"], l["marche"], l["periode"], l.get("ligne"), l["issue"])

    ref = {cle_ligne(l): l["cote"] for l in direct}
    communes = [(ref[cle_ligne(l)], l["cote"]) for l in secours if cle_ligne(l) in ref]
    ecarts = sorted(abs(a - b) / a for a, b in communes)
    return {"secours": len(secours), "communes": len(communes),
            "couverture": round(len(communes) / len(secours), 3) if secours else None,
            "ecart_median": round(ecarts[len(ecarts) // 2], 4) if ecarts else None,
            "ecart_max": round(ecarts[-1], 4) if ecarts else None,
            "identiques_1pct": round(sum(e <= 0.01 for e in ecarts) / len(ecarts), 3) if ecarts else None}
