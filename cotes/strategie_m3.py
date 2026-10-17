"""M3 : strategie descriptive optimisee a posteriori sur le releve du 14/10/2026.

Selection uniquement sur des informations disponibles a la detection.
Le rejeu du 7-13 octobre ne prouve pas une rentabilite future.
La selection prospective commence le 15/10/2026 (heure de Paris).
"""
from __future__ import annotations

from .decisions import figer_selecteur

from datetime import datetime
from math import isfinite

M3 = {
    "nom": "M3 · MultiSport Value",
    "version": "1",
    "debut": "2026-10-14T22:00:00+00:00",
    "references": ("Pinnacle", "Betfair", "Polymarket"),
    "bookmakers": ("Winamax", "Betclic", "Unibet", "PMU"),
    "sports": ("basket", "baseball", "handball"),
    "marches": ("VAINQUEUR", "HANDICAP", "TOTAL", "TOTAL_EXT"),
    "cote_min": 1.30,
    "cote_max": 3.0,
    "edge_min": 0.02,
    "edge_max": 0.12,
    "avance_max_h": 36,
    "fraicheur_max_minutes": 15,
    "mise": 10.0,
}


def _heure(s) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return d if d.tzinfo is not None else None
    except (ValueError, TypeError):
        return None


def _nombre(v) -> float | None:
    if isinstance(v, bool):
        return None
    try:
        n = float(v)
        return n if isfinite(n) else None
    except (ValueError, TypeError):
        return None


def motif_refus_m3(p: dict, depuis: str | None = None) -> str | None:
    """Ne lit jamais statut, gain, CLV ou resultat pour choisir un pari."""
    if p.get("reference") not in M3["references"] or p.get("bookmaker") not in M3["bookmakers"]:
        return "reference ou bookmaker hors perimetre"
    if p.get("sport") not in M3["sports"] or p.get("marche") not in M3["marches"]:
        return "sport ou marche hors perimetre"
    if p.get("periode") != "MATCH" or p.get("suspect"):
        return "periode ou correspondance suspecte"
    t, d, lu, depart = (_heure(p.get("detecte")), _heure(p.get("debut")),
                        _heure(p.get("lu_reference")), _heure(depuis or M3["debut"]))
    if not t or not d or not lu or not depart or t < depart:
        return "date invalide ou detection avant lancement"
    if not (0 < (d-t).total_seconds() <= 3600 * M3["avance_max_h"]):
        return "match trop lointain ou deja commence"
    if not (0 <= (t-lu).total_seconds() <= 60 * M3["fraicheur_max_minutes"]):
        return "reference trop ancienne"
    cote, juste, edge = (_nombre(p.get(k)) for k in ("cote", "cote_juste", "ecart"))
    if (cote is None or juste is None or edge is None or juste <= 1
            or not M3["cote_min"] <= cote <= M3["cote_max"]
            or not M3["edge_min"] <= edge <= M3["edge_max"]
            or abs(cote / juste - 1 - edge) > 0.002):
        return "cote ou edge hors bornes / incoherent"
    preuve = p.get("preuve_prise") or {}
    if not preuve.get("match_id_reference") or (preuve.get("controle") or {}).get("statut") != "conforme":
        return "preuve du match ou du marche non conforme"
    if p.get("marche") in ("TOTAL", "TOTAL_EXT", "HANDICAP"):
        ligne = _nombre(p.get("ligne"))
        if ligne is None or not (ligne * 2).is_integer():
            return "ligne absente ou fractionnee"
    issues = {
        "VAINQUEUR": ("DOM", "EXT"),
        "HANDICAP": ("DOM", "EXT"),
        "TOTAL": ("PLUS", "MOINS"),
        "TOTAL_EXT": ("PLUS", "MOINS"),
    }
    if p.get("issue") not in issues[p["marche"]]:
        return "issue hors perimetre"
    return None


@figer_selecteur("m3")
def paris_m3(paris: list[dict], depuis: str | None = None) -> set[int]:
    """Une mise fictive par selection/bookmaker, premier prix disponible.

    Les paris d'un meme match peuvent rester correles s'ils portent sur
    differents marches. Ne pas interpreter la serie comme 100% independante.
    """
    lignes = [p for p in paris if motif_refus_m3(p, depuis) is None]
    lignes.sort(key=lambda p: (_heure(p["detecte"]), -float(p["ecart"]),
                               str(p.get("bookmaker") or ""), str(p.get("id") or "")))
    deja, out = set(), set()
    for p in lignes:
        cle = tuple(p.get(k) for k in
                    ("match_id", "marche", "periode", "ligne", "issue", "joueur"))
        if cle in deja:
            continue
        deja.add(cle)
        out.add(id(p))
    return out
