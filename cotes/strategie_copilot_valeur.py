"""Copilot Valeur : sélection un peu plus large, sans aller trop loin sur la volatilité.

Règle : Pinnacle, livres français, edge ≥ 2,5 %, 15 min à 4 h, fraîcheur ≤ 8 min,
1 prise par match et max 4/jour.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime

from .decisions import figer_selecteur
from .laboratoire import heure
from .strategie_commune import correspondance_prouvee, edge_coherent, issue_valide, ligne_non_quart, nombre_fini

COPILOT_VALEUR = {
    "cle": "copilot_valeur",
    "nom": "Copilot Valeur",
    "court": "Copilot V",
    "version": "1",
    "debut": "2026-11-06T00:00:00+00:00",
    "prospectif_seulement": True,
    "reference": "Pinnacle",
    "bookmakers": ("Winamax", "Betclic", "Unibet", "PMU"),
    "marches": ("RESULTAT_1N2", "VAINQUEUR", "HANDICAP", "TOTAL"),
    "sports": ("football", "basket", "hockey", "tennis", "baseball", "handball", "volley"),
    "cote_min": 1.35,
    "cote_max": 3.20,
    "edge_min": 0.025,
    "avance_min_minutes": 15,
    "avance_max_h": 4,
    "fraicheur_max_minutes": 8,
    "max_par_jour": 4,
    "mise": 10.0,
}


def _heure(value) -> datetime | None:
    return heure(value)


def motif_refus_copilot_valeur(p: dict, depuis: str = COPILOT_VALEUR["debut"]) -> str | None:
    if p.get("reference") != COPILOT_VALEUR["reference"]:
        return "reference"
    if p.get("bookmaker") not in COPILOT_VALEUR["bookmakers"]:
        return "bookmaker"
    if p.get("sport") not in COPILOT_VALEUR["sports"]:
        return "sport"
    if p.get("suspect"):
        return "suspect"
    if p.get("periode") not in ("MATCH", "TEMPS_REG"):
        return "periode"
    if p.get("marche") not in COPILOT_VALEUR["marches"]:
        return "marche"
    t = _heure(p.get("detecte"))
    debut = _heure(p.get("debut"))
    lu = _heure(p.get("lu_reference"))
    depart = _heure(depuis)
    if not t or not debut or not lu or not depart or t < depart:
        return "date"
    avance = (debut - t).total_seconds() / 60
    if not COPILOT_VALEUR["avance_min_minutes"] <= avance <= COPILOT_VALEUR["avance_max_h"] * 60:
        return "avance"
    if abs((t - lu).total_seconds()) > COPILOT_VALEUR["fraicheur_max_minutes"] * 60:
        return "fraicheur"
    cote = nombre_fini(p.get("cote"))
    juste = nombre_fini(p.get("cote_juste"))
    edge = nombre_fini(p.get("ecart"))
    if cote is None or juste is None or edge is None:
        return "cote"
    if not COPILOT_VALEUR["cote_min"] <= cote <= COPILOT_VALEUR["cote_max"]:
        return "cote_hors_borne"
    if edge < COPILOT_VALEUR["edge_min"]:
        return "edge"
    if not edge_coherent(p.get("cote"), p.get("cote_juste"), p.get("ecart")):
        return "edge_incoherent"
    if not correspondance_prouvee(p, 0.85):
        return "correspondance"
    if p.get("marche") in ("TOTAL", "HANDICAP") and not ligne_non_quart(p.get("ligne")):
        return "ligne"
    if not issue_valide(p.get("marche"), p.get("issue")):
        return "issue"
    return None


@figer_selecteur("copilot_valeur")
def paris_copilot_valeur(paris: list[dict], depuis: str | None = None) -> set[int]:
    """Sélection valeur, un pari par match, plafonné par jour."""
    if depuis is not None:
        return set()
    lignes = [p for p in paris if motif_refus_copilot_valeur(p) is None]
    lignes.sort(key=lambda p: (_heure(p["detecte"]), -float(p["ecart"]), -float(p["cote"]), str(p.get("bookmaker") or ""), str(p.get("id") or "")))
    vus, out, par_jour = set(), set(), Counter()
    for p in lignes:
        match = (p["sport"], str((p.get("preuve_prise") or {}).get("match_id_reference")))
        jour = _heure(p["detecte"]).astimezone().date().isoformat()
        if match in vus or par_jour[jour] >= COPILOT_VALEUR["max_par_jour"]:
            continue
        vus.add(match)
        par_jour[jour] += 1
        out.add(id(p))
    return out
