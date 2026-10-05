"""Harmonisation des marchés spéciaux Pinnacle vers le vocabulaire commun des bookmakers.

Vocabulaire commun (clé de comparaison = marché, période, ligne, issue) :
- RESULTAT_1N2 (DOM, NUL, EXT), VAINQUEUR (DOM, EXT), DRAW_NO_BET (DOM, EXT)
- DOUBLE_CHANCE (HOME_DRAW, HOME_AWAY, DRAW_AWAY)
- HANDICAP (ligne = handicap du domicile ; DOM, EXT), HANDICAP_3 (handicap européen : DOM, NUL, EXT)
- TOTAL, TOTAL_DOM, TOTAL_EXT (PLUS, MOINS) ; préfixes CORNERS_, JEUX_, SETS_
- BOTH_TEAMS_TO_SCORE (YES, NO), CORRECT_SCORE (« 2-1 », domicile en premier),
  HALF_TIME_FULL_TIME (« DOM/NUL »…)
Périodes : MATCH, MT1, MT2, P1-P3 et TEMPS_REG (hockey), QT1-QT4, SET1, SET2.
"""
from __future__ import annotations

import re


def _equipe(nom: str, dom: str, ext: str) -> str | None:
    n = (nom or "").strip().lower()
    if n in ("draw", "nul", "x"):
        return "NUL"
    if n == (dom or "").lower():
        return "DOM"
    if n == (ext or "").lower():
        return "EXT"
    return None


def harmoniser_pinnacle(lignes: list[dict]) -> list[dict]:
    """Convertit les « SPECIAL:… » de Pinnacle ; les marchés non convertibles sont retirés."""
    out = []
    for l in lignes:
        m = l["marche"]
        if not m.startswith("SPECIAL:"):
            out.append(l)
            continue
        nom, dom, ext, issue = m[8:], l["domicile"], l["exterieur"], l["issue"]
        nv = None
        if nom == "Both Teams To Score?":
            nv = ("BOTH_TEAMS_TO_SCORE", None, {"Yes": "YES", "No": "NO"}.get(issue))
        elif nom == "Draw No Bet":
            nv = ("DRAW_NO_BET", None, issue if issue in ("DOM", "EXT") else None)
        elif nom == "Double Chance":
            parts = [p.strip() for p in re.split(r"\s+Or\s+", issue or "")]
            codes = [_equipe(p, dom, ext) for p in parts]
            if len(codes) == 2 and None not in codes:
                a, b = sorted(codes, key=["DOM", "NUL", "EXT"].index)
                nv = ("DOUBLE_CHANCE", None, {("DOM", "NUL"): "HOME_DRAW", ("DOM", "EXT"): "HOME_AWAY",
                                              ("NUL", "EXT"): "DRAW_AWAY"}.get((a, b)))
        elif nom == "Half-Time/Full-Time":
            parts = (issue or "").split(" - ")
            if len(parts) == 2:
                a, b = _equipe(parts[0], dom, ext), _equipe(parts[1], dom, ext)
                nv = ("HALF_TIME_FULL_TIME", None, f"{a}/{b}" if a and b else None)
        elif nom.startswith("3-Way Handicap DOM"):
            h = re.search(r"([-+]\d+)$", nom)
            if h:
                if (issue or "").startswith("Draw"):
                    i = "NUL"
                else:
                    i = _equipe(re.sub(r"\s*\([-+]?\d+\)\s*$", "", issue or ""), dom, ext)
                nv = ("HANDICAP_3", float(h.group(1)), i)
        elif nom == "Correct Score":
            s = re.match(r"^(.*) (\d+), (.*) (\d+)$", issue or "")
            if s and s.group(1).lower() == (dom or "").lower():
                nv = ("CORRECT_SCORE", None, f"{s.group(2)}-{s.group(4)}")
        if nv and nv[2]:
            out.append({**l, "marche": nv[0], "ligne": nv[1], "issue": nv[2]})
    return out


def cle(l: dict) -> tuple:
    """Clé de comparaison d'une cote (indépendante de la source)."""
    ligne = l.get("ligne")
    return (l["marche"], l["periode"], None if ligne is None else round(float(ligne), 2), l["issue"])


def inverser(l: dict) -> dict:
    """Même cote vue avec domicile et extérieur échangés (sources dont l'ordre diffère)."""
    swap = {"DOM": "EXT", "EXT": "DOM", "HOME_DRAW": "DRAW_AWAY", "DRAW_AWAY": "HOME_DRAW"}
    issue = l["issue"]
    if l["marche"] == "CORRECT_SCORE" and "-" in issue:
        a, b = issue.split("-")
        issue = f"{b}-{a}"
    elif l["marche"] == "HALF_TIME_FULL_TIME" and "/" in issue:
        issue = "/".join(swap.get(x, x) for x in issue.split("/"))
    else:
        issue = swap.get(issue, issue)
    marche = l["marche"]
    if marche.endswith("TOTAL_DOM"):
        marche = marche[:-3] + "EXT"
    elif marche.endswith("TOTAL_EXT"):
        marche = marche[:-3] + "DOM"
    ligne = l.get("ligne")
    if marche.endswith("HANDICAP") or marche == "HANDICAP_3":
        ligne = -ligne if ligne is not None else None
    return {**l, "domicile": l["exterieur"], "exterieur": l["domicile"], "marche": marche, "issue": issue,
            "ligne": ligne}
