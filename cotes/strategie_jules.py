"""Stratégies JULES EDGE v1 et v2 : valeur par rapport aux cotes de référence.

JULES EDGE v1 (figée) :
- Référence Pinnacle sans marge
- Cotes 1,30 - 2,50, Edge +3 % à +12 %, 15 min à 12 h avant match
- Max 1 pari par match, cap journalier de 6 paris

JULES EDGE v2 :
- Multi-références : Pinnacle, Betfair, Polymarket
- Cotes 1,30 - 2,80, Edge +2,5 % à +12 %, 15 min à 18 h avant match
- Fraîcheur référence <= 5 min, score correspondance >= 0.85
- Max 1 pari par match, cap journalier de 8 paris
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from math import isfinite
from zoneinfo import ZoneInfo

JULES = {
    "nom": "JULES EDGE v1",
    "version": "1",
    "debut": "2026-10-05T00:00:00+00:00",
    "reference": "Pinnacle",
    "cote_min": 1.30,
    "cote_max": 2.50,
    "edge_min": 0.03,
    "edge_max": 0.12,
    "avance_min_minutes": 15,
    "avance_max_h": 12,
    "fraicheur_max_minutes": 5,
    "paris_max_jour": 6,
    "mise": 10.0,
    "bookmakers": ("Winamax", "Betclic", "Unibet", "PMU"),
    "marches": ("RESULTAT_1N2", "VAINQUEUR", "TOTAL", "HANDICAP"),
    "sports": (
        "football", "basket", "hockey", "baseball", "rugby",
        "handball", "football_americain", "tennis", "volley"
    ),
}

JULES_V2 = {
    "nom": "JULES EDGE v2",
    "version": "2",
    "debut": "2026-10-14T12:00:00+00:00",
    "references": ("Pinnacle", "Betfair", "Polymarket"),
    "cote_min": 1.30,
    "cote_max": 2.80,
    "edge_min": 0.025,
    "edge_max": 0.12,
    "avance_min_minutes": 15,
    "avance_max_h": 18,
    "fraicheur_max_minutes": 5,
    "paris_max_jour": 8,
    "mise": 10.0,
    "bookmakers": ("Winamax", "Betclic", "Unibet", "PMU"),
    "marches": ("RESULTAT_1N2", "VAINQUEUR", "TOTAL", "HANDICAP"),
    "sports": (
        "football", "basket", "hockey", "baseball", "rugby",
        "handball", "football_americain", "tennis", "volley"
    ),
}

PARIS = ZoneInfo("Europe/Paris")


def _heure(value) -> datetime | None:
    try:
        t = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return t if t.tzinfo is not None else None
    except (TypeError, ValueError):
        return None


def _nombre(value) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        n = float(value)
        return n if isfinite(n) else None
    except (TypeError, ValueError):
        return None


def motif_refus_jules(p: dict, depuis: str = JULES["debut"]) -> str | None:
    """Filtre de sélection JULES EDGE v1."""
    if p.get("reference") != JULES["reference"]:
        return "référence différente de Pinnacle sans marge"
    if p.get("bookmaker") not in JULES["bookmakers"] or p.get("sport") not in JULES["sports"]:
        return "bookmaker ou sport hors périmètre"
    if p.get("suspect"):
        return "opportunité suspecte"

    t, debut, lancement = (_heure(p.get("detecte")), _heure(p.get("debut")), _heure(depuis))
    if not t or not debut or not lancement or t < lancement:
        return "détection antérieure au lancement ou date invalide"

    avance = (debut - t).total_seconds() / 60
    if not JULES["avance_min_minutes"] <= avance <= JULES["avance_max_h"] * 60:
        return "détection hors fenêtre de 15 minutes à 12 heures"

    cote, edge, juste = (_nombre(p.get(k)) for k in ("cote", "ecart", "cote_juste"))
    if cote is None or not JULES["cote_min"] <= cote <= JULES["cote_max"]:
        return "cote hors intervalle 1,30–2,50"
    if edge is None or not JULES["edge_min"] <= edge <= JULES["edge_max"]:
        return "edge hors intervalle 3–12 %"
    if juste is None or juste <= 1 or abs(cote / juste - 1 - edge) > 0.002:
        return "edge incohérent avec la cote juste"

    lu = _heure(p.get("lu_reference"))
    if not lu or not 0 <= (t - lu).total_seconds() <= JULES["fraicheur_max_minutes"] * 60:
        return "référence absente, future ou vieille de plus de 5 minutes"

    preuve = p.get("preuve_prise") or {}
    score = _nombre(preuve.get("ressemblance_noms"))
    if ((preuve.get("controle") or {}).get("statut") != "conforme"
            or score is None or score < 0.85 or not preuve.get("match_id_reference")):
        return "preuve de correspondance ou de conformité insuffisante"

    marche = p.get("marche")
    if marche not in JULES["marches"] or p.get("periode") not in ("MATCH", "TEMPS_REG"):
        return "marché ou période hors périmètre"

    if p.get("sport") in ("tennis", "volley") and marche != "VAINQUEUR":
        return "tennis et volley : vainqueur uniquement"

    if marche in ("TOTAL", "HANDICAP"):
        ligne = _nombre(p.get("ligne"))
        if ligne is None or not (ligne * 2).is_integer():
            return "ligne absente ou fractionnée en quarts"

    issues = ("PLUS", "MOINS") if marche == "TOTAL" else ("DOM", "EXT", "NUL") if marche == "RESULTAT_1N2" else ("DOM", "EXT")
    if p.get("issue") not in issues:
        return "issue invalide"

    return None


def paris_jules(paris: list[dict], depuis: str = JULES["debut"]) -> set[int]:
    """Sélectionne les paris respectant JULES EDGE v1."""
    candidats = [p for p in paris if motif_refus_jules(p, depuis) is None]
    candidats.sort(key=lambda p: (_heure(p["detecte"]), -float(p["ecart"]), -float(p["cote"]),
                                 p["bookmaker"], str(p.get("id") or p["match_id"])))
    matchs, selection, par_jour = set(), set(), Counter()
    for p in candidats:
        match = (p["sport"], str(p["preuve_prise"]["match_id_reference"]))
        jour = _heure(p["detecte"]).astimezone(PARIS).date()
        if match in matchs or par_jour[jour] >= JULES["paris_max_jour"]:
            continue
        matchs.add(match)
        par_jour[jour] += 1
        selection.add(id(p))
    return selection


def motif_refus_jules_v2(p: dict, depuis: str = JULES_V2["debut"]) -> str | None:
    """Filtre de sélection JULES EDGE v2."""
    if p.get("reference") not in JULES_V2["references"]:
        return "référence hors périmètre (Pinnacle, Betfair, Polymarket)"
    if p.get("bookmaker") not in JULES_V2["bookmakers"] or p.get("sport") not in JULES_V2["sports"]:
        return "bookmaker ou sport hors périmètre"
    if p.get("suspect"):
        return "opportunité suspecte"

    t, debut, lancement = (_heure(p.get("detecte")), _heure(p.get("debut")), _heure(depuis))
    if not t or not debut or not lancement or t < lancement:
        return "détection antérieure au lancement ou date invalide"

    avance = (debut - t).total_seconds() / 60
    if not JULES_V2["avance_min_minutes"] <= avance <= JULES_V2["avance_max_h"] * 60:
        return "détection hors fenêtre de 15 minutes à 18 heures"

    cote, edge, juste = (_nombre(p.get(k)) for k in ("cote", "ecart", "cote_juste"))
    if cote is None or not JULES_V2["cote_min"] <= cote <= JULES_V2["cote_max"]:
        return "cote hors intervalle 1,30–2,80"
    if edge is None or not JULES_V2["edge_min"] <= edge <= JULES_V2["edge_max"]:
        return "edge hors intervalle 2,5–12 %"
    if juste is None or juste <= 1 or abs(cote / juste - 1 - edge) > 0.002:
        return "edge incohérent avec la cote juste"

    lu = _heure(p.get("lu_reference"))
    if not lu or not 0 <= (t - lu).total_seconds() <= JULES_V2["fraicheur_max_minutes"] * 60:
        return "référence absente, future ou vieille de plus de 5 minutes"

    preuve = p.get("preuve_prise") or {}
    score = _nombre(preuve.get("ressemblance_noms"))
    if ((preuve.get("controle") or {}).get("statut") != "conforme"
            or score is None or score < 0.85 or not preuve.get("match_id_reference")):
        return "preuve de correspondance ou de conformité insuffisante"

    marche = p.get("marche")
    if marche not in JULES_V2["marches"] or p.get("periode") not in ("MATCH", "TEMPS_REG"):
        return "marché ou période hors périmètre"

    if p.get("sport") in ("tennis", "volley") and marche != "VAINQUEUR":
        return "tennis et volley : vainqueur uniquement"

    if marche in ("TOTAL", "HANDICAP"):
        ligne = _nombre(p.get("ligne"))
        if ligne is None or not (ligne * 2).is_integer():
            return "ligne absente ou fractionnée en quarts"

    issues = ("PLUS", "MOINS") if marche == "TOTAL" else ("DOM", "EXT", "NUL") if marche == "RESULTAT_1N2" else ("DOM", "EXT")
    if p.get("issue") not in issues:
        return "issue invalide"

    return None


def paris_jules_v2(paris: list[dict], depuis: str = JULES_V2["debut"]) -> set[int]:
    """Sélectionne les paris respectant JULES EDGE v2 (déduplication 1/match, cap 8/jour)."""
    candidats = [p for p in paris if motif_refus_jules_v2(p, depuis) is None]
    candidats.sort(key=lambda p: (_heure(p["detecte"]), -float(p["ecart"]), -float(p["cote"]),
                                 p["bookmaker"], str(p.get("id") or p["match_id"])))
    matchs, selection, par_jour = set(), set(), Counter()
    for p in candidats:
        match = (p["sport"], str(p["preuve_prise"]["match_id_reference"]))
        jour = _heure(p["detecte"]).astimezone(PARIS).date()
        if match in matchs or par_jour[jour] >= JULES_V2["paris_max_jour"]:
            continue
        matchs.add(match)
        par_jour[jour] += 1
        selection.add(id(p))
    return selection
