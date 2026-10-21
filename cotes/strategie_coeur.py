"""Variante prospective « Cœur value » : règle figée le 21/10/2026 à 15 h (Paris).

Les seuils viennent d'une lecture du bilan des paris simulés du 5 au 21/10 : le rejeu
de cette règle sur ce même historique est donc optimiste (choisi après coup) et ne
prouve rien. Seul le suivi prospectif, à partir de DEBUT, compte. Protocole :
docs/strategie-coeur.md. La sélection ne lit jamais statut, gain ni CLV.
"""
from __future__ import annotations

from .laboratoire import heure
from .strategie_commune import (nombre_fini, correspondance_prouvee, edge_coherent,
                                ligne_non_quart, issue_valide)

COEUR = {
    "cle": "coeur_value", "nom": "Cœur value", "court": "Cœur value",
    "debut": "2026-10-21T13:00:00+00:00",  # 15 h Paris, annoncé avant toute prise
    "version": "1", "mise": 10, "prospectif_seulement": True, "maximum_jour": 5,
    "regles": ("Pinnacle · PMU/Betclic/Unibet · basket, hockey, tennis (vainqueur) · cote 1,50–2,00 · "
               "écart 3–7 % · 1 pari/match · max 5/j · mise fictive 10 €"),
    "reference": "Pinnacle", "bookmakers": ("PMU", "Betclic", "Unibet"),
    "sports": ("basket", "hockey", "tennis"),
    "marches": ("HANDICAP", "VAINQUEUR", "RESULTAT_1N2", "TOTAL"),
    "cote_min": 1.5, "cote_max": 2.0, "edge_min": 0.03, "edge_max": 0.07,
    "avance_min_minutes": 15, "fraicheur_max_minutes": 15,
}


def motif_refus_coeur(p: dict) -> str | None:
    """Uniquement des informations connues à la prise."""
    c = COEUR
    if p.get("reference") != c["reference"] or p.get("bookmaker") not in c["bookmakers"]:
        return "référence ou bookmaker hors périmètre"
    if p.get("sport") not in c["sports"] or p.get("marche") not in c["marches"] or p.get("suspect"):
        return "sport, marché ou opportunité hors périmètre"
    if p.get("sport") == "tennis" and p.get("marche") != "VAINQUEUR":
        return "tennis : vainqueur uniquement"
    t, debut, lu = heure(p.get("detecte")), heure(p.get("debut")), heure(p.get("lu_reference"))
    if not t or not debut or not lu:
        return "date absente ou invalide"
    if (debut - t).total_seconds() < c["avance_min_minutes"] * 60:
        return "match trop proche"
    if abs((t - lu).total_seconds()) > c["fraicheur_max_minutes"] * 60:
        return "référence trop ancienne"
    cote, edge, juste = (nombre_fini(p.get(k)) for k in ("cote", "ecart", "cote_juste"))
    if cote is None or not c["cote_min"] <= cote <= c["cote_max"]:
        return "cote hors intervalle"
    if edge is None or not c["edge_min"] <= edge < c["edge_max"]:
        return "écart hors intervalle"
    if not edge_coherent(cote, juste, edge):
        return "écart incohérent avec la cote juste"
    if not correspondance_prouvee(p, 0.85):
        return "preuve de correspondance insuffisante"
    if p["marche"] in ("TOTAL", "HANDICAP") and not ligne_non_quart(p.get("ligne")):
        return "ligne absente ou en quarts"
    if not issue_valide(p["marche"], p.get("issue")):
        return "issue invalide"
    return None


def paris_coeur(paris: list[dict], depuis: str | None = None) -> set[int]:
    """Première prise admissible par événement, 5 par jour de Paris au plus.

    Pas de bilan rétrospectif officiel : un rejeu explicite renvoie l'ensemble vide.
    """
    if depuis is not None:
        return set()
    from .strategies_prudentes import selection_unique  # import local : évite le cycle
    eligibles = {id(p) for p in paris if motif_refus_coeur(p) is None}
    return selection_unique(paris, eligibles, COEUR["debut"], COEUR["maximum_jour"])["selection"]
