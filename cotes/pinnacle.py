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
import logging
import os
import time
from math import isfinite
from datetime import datetime, timezone

import requests

from .marge import marge, proba_justes

BASE = "https://guest.api.arcadia.pinnacle.com/0.1"
HEADERS = {"User-Agent": "Mozilla/5.0 (cotes-value)", "Accept": "application/json",
           "Referer": "https://www.pinnacle.com/"}
CLE_GUEST_PAR_DEFAUT = "CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R"
ERREURS: list[str] = []
logger = logging.getLogger(__name__)
_bloque = False


def headers() -> dict:
    """Surcharge à l'exécution, y compris pour les sondes ; aucun secret dans les diagnostics."""
    return {**HEADERS, "X-API-Key": os.environ.get("PINNACLE_API_KEY", "").strip() or CLE_GUEST_PAR_DEFAUT}


def _erreur(message: str) -> None:
    if message not in ERREURS and len(ERREURS) < 30:
        ERREURS.append(message)
        logger.warning("Pinnacle : %s", message)

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
    global _bloque
    if _bloque:
        return None
    m = re.match(r"^/sports/(\d+)/(matchups|markets/straight)(?:\?|$)", path)
    contexte = f"sport {m[1]} {m[2]}" if m else "requête"
    for i in range(essais):
        try:
            r = requests.get(BASE + path, headers=headers(), timeout=90)
            if r.status_code == 200:
                try:
                    d = r.json()
                except ValueError:
                    _erreur(f"{contexte} : JSON invalide")
                    return None
                if isinstance(d, list):
                    return d
                _erreur(f"{contexte} : liste JSON attendue")
                return None
            _erreur(f"{contexte} : HTTP {r.status_code}")
            if r.status_code in (401, 403, 429):
                _bloque = True                   # pas de rafale sur tous les autres sports du cycle
                return None
            if r.status_code != 408 and not 500 <= r.status_code <= 599:
                return None
        except requests.RequestException:
            _erreur(f"{contexte} : réseau indisponible")
        if i + 1 < essais:
            time.sleep(2 * (i + 1))
    return None


def _nombre(x) -> float | None:
    if isinstance(x, bool):
        return None
    try:
        n = float(x)
        return n if isfinite(n) else None
    except (TypeError, ValueError, OverflowError):
        return None


def americaine_vers_decimale(p) -> float | None:
    p = _nombre(p)
    if p is None or p == 0:
        return None
    cote = round(1 + p / 100.0 if p > 0 else 1 + 100.0 / abs(p), 4)
    return cote if isfinite(cote) and cote > 1 else None


def _equipes(m: dict) -> tuple[str | None, str | None]:
    parts = {p.get("alignment"): p.get("name") for p in m.get("participants") or [] if isinstance(p, dict)}
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
    global _bloque
    ERREURS.clear()
    _bloque = False
    sports = sports or SPORTS
    lignes: list[dict] = []
    for sid, sport in sports.items():
        matchups = _get(f"/sports/{sid}/matchups?withSpecials=true") or []
        if _bloque:
            break
        if not matchups:
            continue
        requete_debut = datetime.now(timezone.utc).isoformat(timespec="seconds")
        marches = _get(f"/sports/{sid}/markets/straight?primaryOnly=false&withSpecials=true") or []
        maintenant = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if not matchups or not marches:
            continue
        par_id = {m["id"]: m for m in matchups if isinstance(m, dict)
                  and isinstance(m.get("id"), (str, int)) and not isinstance(m.get("id"), bool)}
        if len(par_id) != len(matchups):
            _erreur(f"sport {sid} : événements invalides ou dupliqués")
        periodes = PERIODES.get(sport, {0: "MATCH"})
        for mk in marches:
            if not isinstance(mk, dict):
                _erreur(f"sport {sid} : marché non objet")
                continue
            if mk.get("status") != "open":
                continue
            mid = mk.get("matchupId")
            if not isinstance(mid, (str, int)) or isinstance(mid, bool):
                _erreur(f"sport {sid} : identifiant de marché invalide")
                continue
            mu = par_id.get(mid)
            if mu is None or mu.get("isLive"):
                continue
            prix = mk.get("prices")
            if not isinstance(prix, list) or len(prix) < 2 or any(not isinstance(p, dict) for p in prix):
                _erreur(f"sport {sid} : liste de prix invalide")
                continue
            limites = mk.get("limits")
            maximum = limites[0].get("amount") if isinstance(limites, list) and limites and isinstance(limites[0], dict) else None
            base = {"source": "pinnacle", "sport": sport, "collecte": maintenant,
                    "collecte_debut": requete_debut, "collecte_recue": maintenant,
                    "mise_max": _nombre(maximum)}
            try:
                if mu.get("type") == "matchup":
                    lignes += _lignes_match(mu, mk, prix, par_id, periodes, base)
                elif mu.get("type") == "special":
                    lignes += _lignes_special(mu, mk, prix, par_id, base)
            except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
                _erreur(f"sport {sid} : schéma de marché invalide")
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
    if not isinstance(dom, str) or not isinstance(ext, str) or not dom or not ext or dom == ext:
        return []
    typ = mk["type"]
    if base["sport"] == "tennis" and not unite and typ in ("spread", "total"):
        unite = "SETS_"                # marchés principaux du tennis : en sets
    out = []
    for p in prix:
        cote = americaine_vers_decimale(p.get("price"))
        if cote is None:
            _erreur("marché rejeté : cote américaine invalide")
            return []
        d = p.get("designation")
        if typ == "moneyline":
            nb = len(prix)
            if nb not in (2, 3):
                return []
            marche = "RESULTAT_1N2" if nb == 3 else "VAINQUEUR"
            issue = {"home": "DOM", "away": "EXT", "draw": "NUL"}.get(d)
            ligne = None
        elif typ == "spread":
            marche, issue = "HANDICAP", {"home": "DOM", "away": "EXT"}.get(d)
            pts = _nombre(p.get("points"))
            ligne = pts if d == "home" else (-pts if pts is not None else None)   # handicap du domicile
        elif typ == "total":
            marche, issue, ligne = "TOTAL", {"over": "PLUS", "under": "MOINS"}.get(d), _nombre(p.get("points"))
        elif typ == "team_total":
            cote_eq = mk.get("side")
            if cote_eq not in ("home", "away"):
                return []
            marche = "TOTAL_DOM" if cote_eq == "home" else "TOTAL_EXT"
            issue, ligne = {"over": "PLUS", "under": "MOINS"}.get(d), _nombre(p.get("points"))
        else:
            return []
        if issue is None or (typ != "moneyline" and ligne is None):
            return []
        out.append({**base, "ligue": (parent.get("league") or {}).get("name"), "match_id": parent["id"],
                    "domicile": dom, "exterieur": ext, "debut": parent.get("startTime"),
                    "marche": unite + marche, "periode": periode, "ligne": ligne, "issue": issue,
                    "joueur": None, "cote": cote,
                    "cle_marche": f"{mu['id']}|{mk.get('key')}|{mk.get('side', '')}"})
    return out


def _lignes_special(mu, mk, prix, par_id, base) -> list[dict]:
    parent = par_id.get(mu.get("parentId")) or mu.get("parent")
    if not parent:
        return []                      # paris à long terme : ignorés
    sp = mu.get("special") or {}
    dom, ext = _equipes(parent)
    if not isinstance(dom, str) or not isinstance(ext, str) or not dom or not ext or dom == ext:
        return []
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
        cotes = [l.get("cote") for l in g]
        valides = all(isinstance(c, (int, float)) and not isinstance(c, bool) and _nombre(c) is not None and c > 1 for c in cotes)
        issues = [l.get("issue") for l in g]
        marche = str(g[0].get("marche") or "")
        attendues = ({"DOM", "NUL", "EXT"} if marche.endswith("RESULTAT_1N2") else
                     {"DOM", "EXT"} if marche.endswith(("VAINQUEUR", "HANDICAP")) else
                     {"PLUS", "MOINS"} if "TOTAL" in marche or marche.startswith("JOUEUR:") else None)
        valides = valides and all(isinstance(i, str) and i for i in issues)
        valides = valides and len(set(issues)) == len(issues) and (attendues is None or set(issues) == attendues)
        # Les spéciaux ne sont pas encore traduits en DOM/NUL/EXT : on exige seulement
        # le nombre d'issues du marché. Un handicap européen à 2 prix n'est pas un 2-issues.
        if marche.startswith("SPECIAL:3-Way Handicap"):
            valides = valides and len(issues) == 3
        elif marche in ("SPECIAL:Draw No Bet", "SPECIAL:Both Teams To Score?"):
            valides = valides and len(issues) == 2
        valides = valides and all(all(l.get(k) == g[0].get(k) for k in
                         ("match_id", "marche", "periode", "ligne", "joueur")) for l in g)
        if not valides:
            _erreur("marché rejeté : cotes ou issues incohérentes")
        p = proba_justes(cotes) if valides else None
        m = marge(cotes) if p else None
        for l, pi in zip(g, p or [None] * len(g)):
            l["proba_juste"] = round(pi, 6) if pi else None
            l["cote_juste"] = round(1 / pi, 4) if pi else None
            l["marge_pinnacle"] = round(m, 4) if m is not None else None
