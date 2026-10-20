"""Résultats TheSportsDB : secours gratuit pour les paris qu'aucune autre source n'a réglés.

L'API publique (clé gratuite « 123 », ou THESPORTSDB_API_KEY) sait chercher un match par son nom
(`searchevents.php?e=Domicile_vs_Exterieur`). La clé gratuite ne renvoie que quelques matchs par jour dans les
listes par date : on cherche donc match par match, seulement pour les paris restés sans résultat, avec un
plafond d'appels par cycle (30 par minute au plus en gratuit) et un cache (donnees/thesportsdb.json).

Seuls les matchs terminés dans le temps de jeu normal sont gardés (« FT », et « AOT » pour les sports où le
score compte la prolongation). Prolongation de football, tirs au but, report et abandon sont ignorés. Pas de
score par période ni de corners, et pas de tennis (scores trop souvent figés) : seuls les marchés sur le score
final se règlent avec cette source. Elle n'est pas dans SOURCES_FIABLES : seule, elle ne règle qu'après 24 h
(jamais au hockey), sinon elle doit être d'accord avec une autre source (cotes/resultats.py).
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone

import requests

from . import resultats

BASE = "https://www.thesportsdb.com/api/v1/json"
CLE_PUBLIQUE = "123"
SPORTS = {"football": "Soccer", "hockey": "Ice Hockey", "basket": "Basketball",
          "football_americain": "American Football", "baseball": "Baseball", "handball": "Handball",
          "rugby": "Rugby", "volley": "Volleyball"}
# statuts d'un match fini ; la prolongation ne compte pas dans le score « match » du football, du handball
# et du rugby, mais compte au basket, au hockey, au football américain et au baseball
FINAUX = {"football": {"FT"}, "handball": {"FT"}, "rugby": {"FT"}, "volley": {"FT"},
          "hockey": {"FT", "AOT"}, "basket": {"FT", "AOT"}, "football_americain": {"FT", "AOT"},
          "baseball": {"FT", "AOT"}}
MAX_APPELS = 20                      # par cycle, sous la limite gratuite de 30 appels par minute
APPELS_PAR_MATCH = 2                 # noms du bookmaker, puis noms de la référence ou ordre inverse
PAUSE_S = 2.1
REESSAI = timedelta(hours=3)         # match sans résultat : relu au plus toutes les 3 heures
GARDE = timedelta(days=8)
HISTORIQUE_J = 7
ERREURS: list[str] = []
RESUME: dict = {}


def cle_api() -> str:
    return os.environ.get("THESPORTSDB_API_KEY", "").strip() or CLE_PUBLIQUE


def _entier(v) -> int | None:
    try:
        n = int(str(v).strip())
    except (TypeError, ValueError):
        return None
    return n if n >= 0 else None


def _debut(e: dict) -> datetime | None:
    """Heure de début en UTC : strTimestamp, sinon dateEvent + strTime."""
    for brut in (e.get("strTimestamp"), f"{e.get('dateEvent')}T{e.get('strTime')}" if e.get("dateEvent") and e.get("strTime") else None):
        try:
            d = datetime.fromisoformat(str(brut).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            continue
        return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)
    return None


def match(sport: str, e: dict) -> dict | None:
    """Un match terminé au format des validateurs, ou None."""
    if not isinstance(e, dict) or e.get("strStatus") not in FINAUX.get(sport, ()):
        return None
    if str(e.get("strPostponed") or "").lower() == "yes":
        return None
    dom, ext = e.get("strHomeTeam"), e.get("strAwayTeam")
    score = (_entier(e.get("intHomeScore")), _entier(e.get("intAwayScore")))
    debut = _debut(e)
    if not dom or not ext or None in score or debut is None:
        return None
    return {"source": "thesportsdb", "id_source": e.get("idEvent"), "sport": sport, "domicile": dom,
            "exterieur": ext, "debut": debut, "score": score, "periodes": [], "libelles": [], "corners": None,
            "abandon": False}


def requetes(p: dict) -> list[str]:
    """Noms de recherche (« Domicile_vs_Exterieur ») d'un pari, au plus APPELS_PAR_MATCH."""
    dom, ext = resultats._noms(p)
    paires = [(dom[0], ext[0])]
    if (dom[-1], ext[-1]) != paires[0]:
        paires.append((dom[-1], ext[-1]))
    paires.append((ext[0], dom[0]))
    noms = []
    for d, x in paires:
        nom = f"{d.strip()} vs {x.strip()}".replace(" ", "_")
        if nom not in noms:
            noms.append(nom)
    return noms[:APPELS_PAR_MATCH]


def _chercher(nom: str, sport: str, cle: str, http) -> list[dict]:
    r = http.get(f"{BASE}/{cle}/searchevents.php", params={"e": nom}, headers={"User-Agent": "cotes-value"},
                 timeout=30)
    if not r.ok:
        raise ValueError(f"HTTP {r.status_code}")
    d = r.json()
    if not isinstance(d, dict):
        raise ValueError("réponse non objet")
    evenements = d.get("event")
    if evenements is None:                          # aucun match de ce nom : réponse valide
        return []
    if not isinstance(evenements, list):
        raise ValueError("liste event invalide")
    nom_sport = SPORTS[sport]
    out = []
    for e in evenements:
        if isinstance(e, dict) and e.get("strSport") in (None, nom_sport):
            m = match(sport, e)
            if m:
                out.append(m)
    return out


def a_chercher(paris: list[dict], maintenant: datetime) -> list[dict]:
    """Un pari par match (plusieurs bookmakers voient le même), ouvert, commencé depuis 2 h, dans
    HISTORIQUE_J jours, d'un sport couvert."""
    vus, out = set(), []
    for p in paris:
        if p.get("statut") not in ("en_cours", "a_regler") or p.get("sport") not in SPORTS:
            continue
        if p["match_id"] in vus:
            continue
        debut = resultats._heure(p.get("reporte_au") or p.get("debut"))
        if debut and timedelta(hours=2) < maintenant - debut < timedelta(days=HISTORIQUE_J):
            vus.add(p["match_id"])
            out.append(p)
    return out


def collecter(paris: list[dict], cache: dict, maintenant: datetime, http=requests, cle: str | None = None,
              pause=time.sleep) -> list[dict]:
    """Matchs terminés retrouvés pour les paris sans résultat. `cache` (modifié) : match_id ->
    {"lu": heure, "matchs": [...]}. Un match trouvé n'est plus relu ; un match absent l'est après REESSAI."""
    cle = cle or cle_api()
    RESUME.clear()
    RESUME.update({"appels": 0, "trouves": 0, "cle_publique": cle == CLE_PUBLIQUE})
    for k in [k for k, v in cache.items() if (resultats._heure(v.get("lu")) or maintenant) < maintenant - GARDE]:
        del cache[k]
    out, appels = [], 0
    for p in a_chercher(paris, maintenant):
        entree = cache.get(p["match_id"]) or {}
        lu = resultats._heure(entree.get("lu"))
        if not entree.get("matchs") and lu and maintenant - lu < REESSAI:
            continue
        matchs = list(entree.get("matchs") or [])
        if not matchs:
            if appels >= MAX_APPELS:                # plafond atteint : ce match sera cherché au prochain cycle
                continue
            for nom in requetes(p):
                if appels >= MAX_APPELS:
                    break
                if appels:
                    pause(PAUSE_S)
                appels += 1
                try:
                    matchs = _chercher(nom, p["sport"], cle, http)
                except (requests.RequestException, ValueError, TypeError, AttributeError) as ex:
                    ERREURS.append(f"{p['sport']} {nom} : {repr(ex)[:120]}")
                    continue
                if matchs:
                    break
            cache[p["match_id"]] = {"lu": maintenant.isoformat(timespec="seconds"),
                                    "matchs": [{**m, "debut": m["debut"].isoformat()} for m in matchs]}
        else:
            matchs = [{**m, "debut": resultats._heure(m["debut"]), "score": tuple(m["score"])} for m in matchs]
        out += matchs
        RESUME["trouves"] += bool(matchs)
    RESUME["appels"] = appels
    return out
