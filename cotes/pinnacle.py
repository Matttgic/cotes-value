"""Collecte de toutes les cotes d'avant-match Pinnacle (API « guest » publique, sans compte).

Deux appels par sport : /sports/{id}/matchups (matchs, sous-matchs, marchés spéciaux) et
/sports/{id}/markets/straight (prix). Tout est converti en lignes au format commun :

    sport, ligue, match_id, domicile, exterieur, debut, marche, periode, ligne, issue, cote

puis chaque marché complet reçoit sa probabilité juste (marge retirée, méthode power).

Vocabulaire des marchés (commun à toutes les sources) :
- RESULTAT_1N2 (issues DOM, NUL, EXT), VAINQUEUR (DOM, EXT)
- HANDICAP (ligne = handicap de l'équipe à domicile ; issues DOM, EXT)
- TOTAL, TOTAL_DOM, TOTAL_EXT (issues PLUS, MOINS)
- préfixe d'unité quand ce ne sont pas les buts/points : CORNERS_, CARTONS_, JEUX_ (tennis),
  SETS_ (tennis, volley), POINTS_ (points d'un set au volley)
- marchés spéciaux du football (score exact, mi-temps/fin de match…) : nom normalisé de Pinnacle
- JOUEUR:<stat> (paris joueurs, issues PLUS/MOINS, colonne joueur)
"""
from __future__ import annotations

import re
import time
from datetime import datetime, timezone

import requests

from .marge import marge, proba_justes

BASE = "https://guest.api.arcadia.pinnacle.com/0.1"
HEADERS = {"User-Agent": "Mozilla/5.0 (cotes-value)", "Accept": "application/json",
           "X-API-Key": "CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R", "Referer": "https://www.pinnacle.com/"}

# identifiant Pinnacle -> nom commun du sport
SPORTS = {29: "football", 33: "tennis", 4: "basket", 19: "hockey", 15: "football_americain",
          3: "baseball", 18: "handball", 34: "volley", 27: "rugby", 22: "mma", 6: "boxe",
          10: "flechettes", 12: "esport", 8: "cricket", 32: "tennis_de_table", 13: "snooker"}

# période Pinnacle -> période commune, par sport (le reste est ignoré)
PERIODES = {
    "football": {0: "MATCH", 1: "MT1"},
    "basket": {0: "MATCH", 1: "MT1", 2: "MT2", 3: "QT1", 4: "QT2", 5: "QT3", 6: "QT4"},
    "hockey": {0: "MATCH", 6: "TEMPS_REG", 1: "P1", 2: "P2", 3: "P3"},
    "football_americain": {0: "MATCH", 1: "MT1", 2: "MT2", 3: "QT1", 4: "QT2", 5: "QT3", 6: "QT4"},
    "baseball": {0: "MATCH", 1: "5_MANCHES"},
    "tennis": {0: "MATCH", 1: "SET1", 2: "SET2"},
    "volley": {0: "MATCH", 1: "SET1", 2: "SET2", 3: "SET3"},
    "handball": {0: "MATCH", 1: "MT1"},
    "rugby": {0: "MATCH", 1: "MT1"},
    "esport": {0: "MATCH", 1: "MAP1", 2: "MAP2", 3: "MAP3"},
}
UNITES = {"Corners": "CORNERS_", "Bookings": "CARTONS_", "Games": "JEUX_", "Points": "POINTS_"}


def _get(path: str, essais: int = 3):
    for i in range(essais):
        try:
            r = requests.get(BASE + path, headers=HEADERS, timeout=90)
            if r.status_code == 200:
                return r.json()
        except (requests.RequestException, ValueError):
            pass
        time.sleep(2 * (i + 1))
    return None


def americaine_vers_decimale(p) -> float:
    p = float(p)
    return round(1 + p / 100.0 if p > 0 else 1 + 100.0 / abs(p), 4)


def _equipes(m: dict) -> tuple[str | None, str | None]:
    parts = {p.get("alignment"): p.get("name") for p in m.get("participants") or []}
    return parts.get("home"), parts.get("away")


def _norm_special(desc: str, dom: str, ext: str) -> tuple[str, str]:
    """« Lazio Goals Odd/Even 1st Half » -> (marché « DOM Goals Odd/Even », période « MT1 »)."""
    periode = "MATCH"
    if re.search(r"\b1st Half\b", desc):
        periode, desc = "MT1", re.sub(r"\s*\b1st Half\b", "", desc)
    if dom:
        desc = desc.replace(dom, "DOM")
    if ext:
        desc = desc.replace(ext, "EXT")
    return desc.strip(), periode


def collecter(sports: dict | None = None) -> list[dict]:
    """Toutes les cotes ouvertes (avant-match), une ligne par issue, avec probabilité juste."""
    sports = sports or SPORTS
    maintenant = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lignes: list[dict] = []
    for sid, sport in sports.items():
        matchups = _get(f"/sports/{sid}/matchups?withSpecials=true") or []
        marches = _get(f"/sports/{sid}/markets/straight?primaryOnly=false&withSpecials=true") or []
        if not matchups or not marches:
            continue
        par_id = {m["id"]: m for m in matchups}
        periodes = PERIODES.get(sport, {0: "MATCH"})
        for mk in marches:
            if mk.get("status", "open") != "open":
                continue
            mu = par_id.get(mk.get("matchupId"))
            if mu is None or mu.get("isLive"):
                continue
            prix = mk.get("prices") or []
            if len(prix) < 2:
                continue
            base = {"source": "pinnacle", "sport": sport, "collecte": maintenant,
                    "mise_max": (mk.get("limits") or [{}])[0].get("amount")}
            if mu["type"] == "matchup":
                lignes += _lignes_match(mu, mk, prix, par_id, periodes, base)
            elif mu["type"] == "special":
                lignes += _lignes_special(mu, mk, prix, par_id, base)
    _ajouter_proba_justes(lignes)
    return lignes


def _lignes_match(mu, mk, prix, par_id, periodes, base) -> list[dict]:
    parent = par_id.get(mu.get("parentId")) if mu.get("parentId") else mu
    if parent is None:
        return []
    unite = UNITES.get(mu.get("units"), "") if mu.get("parentId") else ""
    if mu.get("parentId") and mu.get("units") not in UNITES and mu.get("units") != "Regular":
        return []                      # sous-matchs exotiques (kills…) : ignorés
    if mu.get("parentId") and mu.get("units") == "Regular":
        return []                      # doublons « Regular » (prolongations…) : ignorés
    periode = periodes.get(mk.get("period", 0))
    if periode is None:
        return []
    dom, ext = _equipes(parent)
    typ = mk["type"]
    if base["sport"] == "tennis" and not unite and typ in ("spread", "total"):
        unite = "SETS_"                # marchés principaux du tennis : en sets
    out = []
    for p in prix:
        d = p.get("designation")
        if typ == "moneyline":
            nb = len(prix)
            marche = "RESULTAT_1N2" if nb == 3 else "VAINQUEUR"
            issue = {"home": "DOM", "away": "EXT", "draw": "NUL"}.get(d)
            ligne = None
        elif typ == "spread":
            marche, issue = "HANDICAP", {"home": "DOM", "away": "EXT"}.get(d)
            pts = p.get("points")
            ligne = pts if d == "home" else (-pts if pts is not None else None)   # handicap du domicile
        elif typ == "total":
            marche, issue, ligne = "TOTAL", {"over": "PLUS", "under": "MOINS"}.get(d), p.get("points")
        elif typ == "team_total":
            cote_eq = mk.get("side")
            marche = "TOTAL_DOM" if cote_eq == "home" else "TOTAL_EXT"
            issue, ligne = {"over": "PLUS", "under": "MOINS"}.get(d), p.get("points")
        else:
            return []
        if issue is None:
            return []
        out.append({**base, "ligue": (parent.get("league") or {}).get("name"), "match_id": parent["id"],
                    "domicile": dom, "exterieur": ext, "debut": parent.get("startTime"),
                    "marche": unite + marche, "periode": periode, "ligne": ligne, "issue": issue,
                    "joueur": None, "cote": americaine_vers_decimale(p["price"]),
                    "cle_marche": f"{mu['id']}|{mk.get('key')}|{mk.get('side', '')}"})
    return out


def _lignes_special(mu, mk, prix, par_id, base) -> list[dict]:
    parent = par_id.get(mu.get("parentId")) or mu.get("parent")
    if not parent:
        return []                      # paris à long terme : ignorés
    sp = mu.get("special") or {}
    dom, ext = _equipes(parent)
    noms = {p["id"]: p["name"] for p in mu.get("participants") or []}
    cat, desc = sp.get("category", ""), sp.get("description", "")
    out = []
    if cat == "Player Props":
        m = re.match(r"^(.*?) Total (.*)$", desc)
        joueur = m.group(1) if m else desc
        stat = mu.get("units") or (m.group(2) if m else "?")
        for p in prix:
            issue = {"Over": "PLUS", "Under": "MOINS"}.get(noms.get(p.get("participantId")))
            if issue is None:
                return []
            out.append({**base, "ligue": (parent.get("league") or {}).get("name"), "match_id": parent["id"],
                        "domicile": dom, "exterieur": ext, "debut": parent.get("startTime"),
                        "marche": f"JOUEUR:{stat}", "periode": "MATCH", "ligne": p.get("points"),
                        "issue": issue, "joueur": joueur, "cote": americaine_vers_decimale(p["price"]),
                        "cle_marche": f"{mu['id']}|{mk.get('key')}"})
        return out
    if cat not in ("Team Props", "Game Props", "Exact Scores", "Double Result"):
        return []
    marche, periode = _norm_special(desc, dom, ext)
    for p in prix:
        nom = noms.get(p.get("participantId"), "?")
        issue = {dom: "DOM", ext: "EXT", "Draw": "NUL"}.get(nom, nom)
        out.append({**base, "ligue": (parent.get("league") or {}).get("name"), "match_id": parent["id"],
                    "domicile": dom, "exterieur": ext, "debut": parent.get("startTime"),
                    "marche": f"SPECIAL:{marche}", "periode": periode, "ligne": p.get("points"),
                    "issue": issue, "joueur": None, "cote": americaine_vers_decimale(p["price"]),
                    "cle_marche": f"{mu['id']}|{mk.get('key')}"})
    return out


def _ajouter_proba_justes(lignes: list[dict]) -> None:
    groupes: dict[str, list[dict]] = {}
    for l in lignes:
        groupes.setdefault(l["cle_marche"], []).append(l)
    for g in groupes.values():
        p = proba_justes([l["cote"] for l in g])
        m = marge([l["cote"] for l in g]) if p else None
        for l, pi in zip(g, p or [None] * len(g)):
            l["proba_juste"] = round(pi, 6) if pi else None
            l["cote_juste"] = round(1 / pi, 4) if pi else None
            l["marge_pinnacle"] = round(m, 4) if m is not None else None
