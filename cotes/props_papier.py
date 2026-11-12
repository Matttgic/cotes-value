"""Paris fictifs sur les props NBA/NHL, pour mesurer avant d'activer une stratégie.

Un enregistrement par joueur, statistique, ligne, issue et bookmaker. La première
détection est gardée (la cote prise). Une cote française plus haute vue ensuite est
notée à part (``cote_max``) et ne change pas le pari. Rien n'est notifié, rien n'entre
dans ``paris.json``, aucun sélecteur ``@figer_selecteur`` n'est appelé.

Seuil : ``PROPS_ECART_MIN`` (défaut 0,02, soit 2 % au-dessus de la cote juste Pinnacle,
marge retirée). Livres : Winamax, Unibet, NetBet. Ligues : NBA et NHL seulement.

La CLV utilise la dernière cote juste Pinnacle lue avant le coup d'envoi. Elle entre
dans la moyenne seulement si cette lecture date de moins de 30 minutes, comme les
autres paris.

Règlement : feuille de match ESPN (API publique, sans clé). Absent du parquet (DNP) ou
ligne entière touchée : pari annulé. Le connecteur Polymarket ne produit pas de lignes
``JOUEUR`` : la stratégie « Props Polymarket » reste désactivée.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from .correspondance import ressemblance
from .joueurs import cle_joueur, est_joueur
from .simulation import CLOTURE_MAX_MIN
from .temps import instant_utc

FICHIER = "props_papier.json"
ECART_DEFAUT = 0.02
LIVRES = ("Winamax", "Unibet", "NetBet")
MISE = 10.0
PLAFOND_FEUILLES = 12
FENETRE_MATCH_H = 6
STRATEGIES = (
    {"cle": "props_pinnacle", "nom": "Props Pinnacle", "reference": "Pinnacle", "actif": False},
    {"cle": "props_polymarket", "nom": "Props Polymarket", "reference": "Polymarket", "actif": False},
    # Papier seulement, éteint : FanDuel n'est pas un book où Matthieu peut miser.
    {"cle": "props_fanduel", "nom": "Props FanDuel", "reference": "FanDuel", "actif": False, "papier": True},
)
# Colonnes ESPN. NBA : PTS, REB, AST, 3PT (« 2-5 » = 2 réussis). NHL : G, A, SOG, SV.
# Les points NHL sont G + A (la feuille n'a pas de colonne PTS joueur).
_COLONNES = {
    ("basket", "Points"): ("PTS",),
    ("basket", "Rebounds"): ("REB",),
    ("basket", "Assists"): ("AST",),
    ("basket", "ThreePoints"): ("3PT",),
    ("basket", "PointsReboundsAssists"): ("PTS", "REB", "AST"),
    ("hockey", "Goals"): ("G",),
    ("hockey", "Assists"): ("A",),
    ("hockey", "Points"): ("G", "A"),
    ("hockey", "ShotsOnGoal"): ("SOG",),
    ("hockey", "Saves"): ("SV",),
}
NOTE_POLYMARKET = (
    "Le 10/11/2026, un match NBA (Lakers–Hawks) avait des marchés points, rebonds, passes "
    "et tirs à trois. La liquidité dépasse 100 sur quelques lignes seulement (environ 195 "
    "sur les points de Luka Dončić, souvent moins de 100 ailleurs). Le connecteur ne lit "
    "pas ces types : Props Polymarket reste désactivée."
)


def seuil(environ=None) -> float:
    """Écart minimum pour enregistrer un papier. Valeur illisible : le défaut 2 %."""
    brut = (environ if environ is not None else os.environ).get("PROPS_ECART_MIN", "")
    if not str(brut).strip():
        return ECART_DEFAUT
    try:
        valeur = float(str(brut).strip())
    except ValueError:
        return ECART_DEFAUT
    return valeur if valeur >= 0 else ECART_DEFAUT


def _heure(valeur) -> datetime | None:
    return instant_utc(valeur)


def _stat(marche: str) -> str:
    return str(marche or "").split(":", 1)[-1]


def ligue_nba_nhl(sport: str, ligue: str | None) -> bool:
    t = (ligue or "").lower()
    if sport == "basket":
        return "nba" in t and "wnba" not in t
    if sport == "hockey":
        return "nhl" in t
    return False


def cle_observation(l: dict) -> str:
    """Clé stable : book, match du book, stat, ligne, issue, joueur normalisé."""
    ligne = l.get("ligne")
    try:
        ligne_txt = f"{round(float(ligne), 2):.2f}"
    except (TypeError, ValueError):
        ligne_txt = ""
    joueur = l.get("cle_joueur") or cle_joueur(l.get("joueur"))
    return "|".join((
        str(l.get("bookmaker") or l.get("source") or ""),
        str(l.get("match_id") or ""),
        str(l.get("marche") or ""),
        ligne_txt,
        str(l.get("issue") or ""),
        joueur,
    ))


def _doc(brut) -> dict:
    if isinstance(brut, dict) and isinstance(brut.get("paris"), list):
        return brut
    if isinstance(brut, list):
        return {"paris": brut}
    return {"paris": []}


def lire(donnees) -> dict:
    from pathlib import Path
    import json
    chemin = Path(donnees) / FICHIER
    try:
        return _doc(json.loads(chemin.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return {"paris": []}


def ecrire(donnees, doc: dict) -> None:
    import json
    from pathlib import Path
    chemin = Path(donnees) / FICHIER
    chemin.parent.mkdir(parents=True, exist_ok=True)
    tmp = chemin.with_name(chemin.name + ".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, chemin)


def enregistrer(doc: dict, rapproches: list[dict], maintenant: datetime, minimum: float | None = None) -> int:
    """Ajoute les écarts Pinnacle au-dessus du seuil. Rend le nombre de nouvelles lignes.

    La cote de la première détection est le prix du papier. Une cote plus haute vue
    plus tard, avant le coup d'envoi, est gardée dans ``cote_max`` seulement.
    """
    plancher = ECART_DEFAUT if minimum is None else minimum
    paris = doc.setdefault("paris", [])
    par_cle = {p.get("cle"): p for p in paris if p.get("cle")}
    nouveaux = 0
    for l in rapproches or []:
        if l.get("reference") != "Pinnacle" or l.get("bookmaker") not in LIVRES:
            continue
        if not ligue_nba_nhl(l.get("sport"), l.get("ligue")):
            continue
        ecart = l.get("ecart")
        if not isinstance(ecart, (int, float)) or isinstance(ecart, bool) or ecart < plancher:
            continue
        if not l.get("cote") or not l.get("proba_juste") or not cle_joueur(l.get("joueur")):
            continue
        cle = cle_observation(l)
        deja = par_cle.get(cle)
        if deja:
            if (isinstance(l.get("cote"), (int, float)) and not isinstance(l.get("cote"), bool)
                    and l["cote"] > (deja.get("cote_max") or deja.get("cote") or 0)
                    and (_heure(l.get("detecte")) or maintenant) < (_heure(deja.get("debut")) or maintenant)):
                deja["cote_max"] = l["cote"]
                deja["ecart_max"] = ecart
            continue
        pari = {
            "cle": cle, "papier": True, "pariable": False, "statut": "en_cours",
            "mise": MISE, "gain": None, "clv": None,
            "bookmaker": l.get("bookmaker"), "sport": l.get("sport"), "ligue": l.get("ligue"),
            "match_id": l.get("match_id"), "match_id_reference": l.get("match_id_reference"),
            "domicile": l.get("domicile"), "exterieur": l.get("exterieur"), "debut": l.get("debut"),
            "joueur": l.get("joueur"), "cle_joueur": cle_joueur(l.get("joueur")),
            "marche": l.get("marche"), "stat": _stat(l.get("marche")),
            "periode": l.get("periode"), "ligne": l.get("ligne"), "issue": l.get("issue"),
            "cote": l.get("cote"), "cote_max": l.get("cote"),
            "reference": "Pinnacle", "cote_juste": l.get("cote_juste"),
            "proba_juste": l.get("proba_juste"), "ecart": ecart,
            "detecte": l.get("detecte"), "seuil": plancher,
        }
        paris.append(pari)
        par_cle[cle] = pari
        nouveaux += 1
    doc["seuil"] = plancher
    return nouveaux


def _index_pinnacle(lignes: list[dict]) -> dict[tuple, dict]:
    out = {}
    for l in lignes or []:
        if l.get("source") != "pinnacle" or not est_joueur(l.get("marche")):
            continue
        if l.get("cote_perimee") or not l.get("proba_juste"):
            continue
        try:
            ligne = round(float(l.get("ligne")), 2)
        except (TypeError, ValueError):
            continue
        cle = (l.get("match_id"), l.get("marche"), ligne, l.get("issue"), cle_joueur(l.get("joueur")))
        avant = out.get(cle)
        lu = _heure(l.get("collecte"))
        if avant is None or (lu and (_heure(avant.get("collecte")) or lu) <= lu):
            out[cle] = l
    return out


def clotures(doc: dict, pinnacle: list[dict], maintenant: datetime) -> int:
    """Dernière cote juste Pinnacle avant le coup d'envoi. Rend le nombre de mises à jour."""
    index = _index_pinnacle(pinnacle)
    n = 0
    for p in doc.get("paris") or []:
        if p.get("statut") != "en_cours":
            continue
        debut = _heure(p.get("debut"))
        if debut is None:
            continue
        try:
            ligne = round(float(p.get("ligne")), 2)
        except (TypeError, ValueError):
            continue
        l = index.get((p.get("match_id_reference"), p.get("marche"), ligne, p.get("issue"), p.get("cle_joueur")))
        if not l:
            continue
        lu = _heure(l.get("collecte"))
        if lu is None or lu.tzinfo is None or lu >= debut:
            continue
        avant = _heure(p.get("cloture_lue"))
        if avant and lu <= avant:
            continue
        p["cote_juste_cloture"] = round(1 / l["proba_juste"], 4)
        p["clv"] = round(p["cote"] * l["proba_juste"] - 1, 4)
        p["cloture_lue"] = lu.isoformat(timespec="seconds")
        n += 1
    return n


def clv_comptable(p: dict) -> float | None:
    """CLV retenue dans la moyenne : lecture à moins de 30 minutes du coup d'envoi, pari réglé."""
    if p.get("clv") is None or p.get("statut") in ("en_cours", "a_regler"):
        return None
    lu, debut = _heure(p.get("cloture_lue")), _heure(p.get("debut"))
    if not lu or not debut:
        return None
    ecart = (debut - lu).total_seconds()
    return p["clv"] if 0 < ecart <= CLOTURE_MAX_MIN * 60 else None


def _nombre_stat(texte) -> float | None:
    if texte is None:
        return None
    brut = str(texte).strip()
    if not brut or brut in {"-", "--"}:
        return None
    if "-" in brut and not brut.startswith("-"):
        brut = brut.split("-", 1)[0]
    try:
        return float(brut)
    except ValueError:
        return None


def _joueurs_bloc(bloc: dict) -> list[dict]:
    noms = bloc.get("names") or bloc.get("labels") or []
    out = []
    for a in bloc.get("athletes") or []:
        if not isinstance(a, dict):
            continue
        nom = ((a.get("athlete") or {}).get("displayName")
               or (a.get("athlete") or {}).get("shortName"))
        if not nom:
            continue
        stats = {}
        valeurs = a.get("stats") or []
        for i, col in enumerate(noms):
            if i < len(valeurs):
                n = _nombre_stat(valeurs[i])
                if n is not None:
                    stats[col] = n
        out.append({"nom": nom, "cle": cle_joueur(nom), "dnp": bool(a.get("didNotPlay")), "stats": stats})
    return out


def joueurs_feuille(summary: dict) -> list[dict]:
    """Joueurs d'une fiche ESPN ``summary``. Les patineurs NHL sont le plus gros bloc G+A."""
    blocs = []
    for equipe in ((summary or {}).get("boxscore") or {}).get("players") or []:
        if isinstance(equipe, dict):
            blocs.extend(b for b in (equipe.get("statistics") or []) if isinstance(b, dict))
    if not blocs:
        return []
    skateurs = [b for b in blocs if "G" in (b.get("names") or []) and "A" in (b.get("names") or [])]
    gardien = [b for b in blocs if "SV" in (b.get("names") or [])]
    if skateurs:
        joueurs, vus = [], set()
        for b in sorted(skateurs, key=lambda b: len(b.get("athletes") or []), reverse=True):
            for j in _joueurs_bloc(b):
                if j["cle"] not in vus:
                    vus.add(j["cle"])
                    joueurs.append(j)
        for b in gardien:
            for j in _joueurs_bloc(b):
                if j["cle"] not in vus:
                    vus.add(j["cle"])
                    joueurs.append(j)
        return joueurs
    # NBA : un bloc par équipe. Avant le 11/11/2026, seul le premier (l'équipe à l'extérieur) était lu : les props
    # des joueurs à domicile restaient « joueur ambigu ou absent » (Cooper Flagg, Mavericks–Pacers du 9/11).
    joueurs, vus = [], set()
    for b in blocs:
        for j in _joueurs_bloc(b):
            if j["cle"] not in vus:
                vus.add(j["cle"])
                joueurs.append(j)
    return joueurs


def _match_espn(pari: dict, matchs: list[dict]) -> dict | None:
    debut = _heure(pari.get("debut"))
    if debut is None:
        return None
    trouves = []
    for m in matchs or []:
        if m.get("sport") != pari.get("sport") or not m.get("final"):
            continue
        autre = _heure(m.get("debut"))
        if autre is None or abs((debut - autre).total_seconds()) > FENETRE_MATCH_H * 3600:
            continue
        direct = min(ressemblance(pari.get("domicile"), m.get("domicile")),
                     ressemblance(pari.get("exterieur"), m.get("exterieur")))
        inverse = min(ressemblance(pari.get("domicile"), m.get("exterieur")),
                      ressemblance(pari.get("exterieur"), m.get("domicile")))
        if max(direct, inverse) >= 0.85:
            trouves.append(m)
    if len(trouves) != 1:
        return None
    return trouves[0]


def _valeur(joueur: dict, sport: str, stat: str) -> float | None:
    cols = _COLONNES.get((sport, stat))
    if not cols or joueur.get("dnp"):
        return None
    total = 0.0
    for col in cols:
        if col not in joueur.get("stats", {}):
            return None
        total += joueur["stats"][col]
    return total


def regler(doc: dict, matchs: list[dict], feuilles: dict[str, list[dict]], maintenant: datetime) -> int:
    """Règle les papiers dont le match ESPN est terminé. Rend le nombre de verdicts."""
    n = 0
    for p in doc.get("paris") or []:
        if p.get("statut") != "en_cours":
            continue
        debut = _heure(p.get("debut"))
        if debut is None or debut > maintenant:
            continue
        match = _match_espn(p, matchs)
        if not match:
            continue
        joueurs = feuilles.get(str(match.get("espn_id"))) or []
        if not joueurs:
            continue
        meme = [j for j in joueurs if j.get("cle") and j["cle"] == p.get("cle_joueur")]
        if not meme and p.get("cle_joueur"):
            # Suffixe présent d'un seul côté (« Darius Acuff » chez Winamax, « Darius Acuff Jr. » chez ESPN) :
            # même nom et même initiale, seulement si un seul joueur de la feuille correspond.
            base = p["cle_joueur"].rsplit("|", 1)[0]
            meme = [j for j in joueurs if j.get("cle") and j["cle"].rsplit("|", 1)[0] == base]
        if len(meme) != 1:
            p["reglement_note"] = "joueur ambigu ou absent"
            continue
        j = meme[0]
        if j.get("dnp"):
            p.update(statut="annule", gain=0.0, regle_le=maintenant.isoformat(timespec="seconds"),
                     reglement="DNP")
            n += 1
            continue
        valeur = _valeur(j, p.get("sport"), p.get("stat"))
        if valeur is None:
            p["reglement_note"] = "statistique absente"
            continue
        ligne = p.get("ligne")
        try:
            ligne = float(ligne)
        except (TypeError, ValueError):
            continue
        if abs(valeur - ligne) < 1e-9:
            verdict, gain = "annule", 0.0
            motif = "pousse"
        elif (p.get("issue") == "PLUS" and valeur > ligne) or (p.get("issue") == "MOINS" and valeur < ligne):
            verdict, gain = "gagne", round(MISE * (p["cote"] - 1), 2)
            motif = "gagne"
        else:
            verdict, gain = "perdu", -MISE
            motif = "perdu"
        p.update(statut=verdict, gain=gain, stat_reelle=valeur,
                 regle_le=maintenant.isoformat(timespec="seconds"), reglement=motif,
                 espn_id=match.get("espn_id"))
        n += 1
    return n


def _resume(paris: list[dict]) -> dict:
    regles = [p for p in paris if p.get("statut") in ("gagne", "perdu")]
    annules = [p for p in paris if p.get("statut") == "annule"]
    gain = round(sum(p.get("gain") or 0 for p in regles), 2)
    mises = round(sum(p.get("mise") or 0 for p in regles), 2)
    clvs = [c for c in (clv_comptable(p) for p in regles) if c is not None]
    gagnes = sum(p.get("statut") == "gagne" for p in regles)
    return {
        "n": len(paris), "regles": len(regles), "annules": len(annules),
        "en_cours": sum(p.get("statut") == "en_cours" for p in paris),
        "gagnes": gagnes,
        "reussite": round(gagnes / len(regles), 4) if regles else None,
        "mise": mises, "gain": gain,
        "roi": round(gain / mises, 4) if mises else None,
        "clv_moyenne": round(sum(clvs) / len(clvs), 4) if clvs else None,
        "clv_n": len(clvs),
    }


LISTE_MAX = 300


def liste_paris(paris: list[dict], limite: int = LISTE_MAX) -> list[dict]:
    """Les paris props eux-mêmes (les plus récents d'abord), pour les voir dans le Bilan et pas seulement les stats.
    Les annulés (DNP, ligne poussée, faux rapprochements) n'y figurent pas : ils restent dans les données et dans
    le compte « annulés » du bilan."""
    paris = [p for p in paris if p.get("statut") != "annule"]
    champs = ("joueur", "stat", "sport", "ligue", "issue", "ligne", "cote", "bookmaker", "domicile", "exterieur",
              "debut", "statut", "gain", "mise", "stat_reelle", "reglement", "clv")
    triees = sorted(paris, key=lambda p: p.get("debut") or "", reverse=True)[:limite]
    return [{c: p.get(c) for c in champs} for p in triees]


def bilan(doc: dict) -> dict:
    """Compte, réussite, ROI et CLV moyenne, par référence et par statistique."""
    paris = [p for p in (doc or {}).get("paris") or [] if isinstance(p, dict)]
    par_ref: dict[str, list] = {}
    par_stat: dict[str, list] = {}
    for p in paris:
        par_ref.setdefault(p.get("reference") or "?", []).append(p)
        etiquette = f"{p.get('stat') or '?'} · {'NBA' if p.get('sport') == 'basket' else 'NHL' if p.get('sport') == 'hockey' else p.get('sport') or '?'}"
        par_stat.setdefault(etiquette, []).append(p)
    return {
        "seuil": doc.get("seuil", ECART_DEFAUT),
        "mise": MISE,
        "strategies": [dict(s) for s in STRATEGIES],
        "polymarket": doc.get("polymarket") or {"present": False, "liquides": 0, "utilise": False,
                                                "raison": NOTE_POLYMARKET},
        "fanduel": doc.get("fanduel") or {
            "fanduel": 0, "pinnacle": 0, "rapproches": 0, "non_rapproches": 0,
            "ecart_proba_moyen": None, "ecart_absolu_moyen": None, "accord": None,
            "reference_seule": True,
        },
        # DraftKings, référence seule : props NBA/NHL et lignes de match NBA, NHL, NFL, MLB contre Pinnacle
        "draftkings": doc.get("draftkings") or {},
        "total": _resume(paris),
        "liste": liste_paris(paris),
        "references": {k: _resume(v) for k, v in sorted(par_ref.items())},
        "stats": {k: _resume(v) for k, v in sorted(par_stat.items())},
    }


def verdict_polymarket(lignes: list[dict]) -> dict:
    """Ce que la collecte a réellement produit. Les types non lus restent absents."""
    props = [l for l in lignes or [] if est_joueur(l.get("marche"))]
    liquides = [l for l in props if isinstance(l.get("liquidite"), (int, float)) and l["liquidite"] >= 100]
    if not props:
        return {"present": False, "lignes": 0, "liquides": 0, "utilise": False, "raison": NOTE_POLYMARKET}
    if not liquides:
        return {"present": True, "lignes": len(props), "liquides": 0, "utilise": False,
                "raison": "Props lus, liquidité sous 100 : non utilisés."}
    return {"present": True, "lignes": len(props), "liquides": len(liquides), "utilise": False,
            "raison": "Props liquides vus. Stratégie Props Polymarket désactivée."}


def feuilles_a_lire(doc: dict, matchs: list[dict], maintenant: datetime) -> list[str]:
    """Identifiants ESPN des matchs terminés qui ont encore un papier ouvert. Plafond par cycle."""
    ids = []
    for p in doc.get("paris") or []:
        if p.get("statut") != "en_cours":
            continue
        if (_heure(p.get("debut")) or maintenant) > maintenant:
            continue
        m = _match_espn(p, matchs)
        if m and m.get("espn_id") and str(m["espn_id"]) not in ids:
            ids.append(str(m["espn_id"]))
        if len(ids) >= PLAFOND_FEUILLES:
            break
    return ids


def charger_feuilles(identifiants: list[tuple[str, str]], lire_json) -> dict[str, list[dict]]:
    """``(espn_id, sport)`` -> joueurs. ``lire_json(chemin, params)`` est injecté (pas de réseau ici)."""
    chemins = {"basket": "basketball/nba/summary", "hockey": "hockey/nhl/summary"}
    out = {}
    for eid, sport in identifiants:
        chemin = chemins.get(sport)
        if not chemin or not eid:
            continue
        doc = lire_json(chemin, {"event": eid})
        if isinstance(doc, dict):
            out[str(eid)] = joueurs_feuille(doc)
    return out


def matchs_espn(enregistrements: list[dict]) -> list[dict]:
    """Scoreboard déjà lu (source espn, match terminé) au format du règlement props."""
    out = []
    for r in enregistrements or []:
        if r.get("source") != "espn" or r.get("a_venir") or r.get("abandon"):
            continue
        if r.get("sport") not in ("basket", "hockey") or not r.get("espn_id"):
            continue
        out.append({"sport": r.get("sport"), "domicile": r.get("domicile"), "exterieur": r.get("exterieur"),
                    "debut": r.get("debut"), "espn_id": r.get("espn_id"), "final": True,
                    "ligue": r.get("espn")})
    return out
