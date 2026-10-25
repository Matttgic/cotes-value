"""Variante prospective « Liquidité sûre » : règle figée le 25/10/2026, avant tout pari suivi.

Hypothèse à tester : les écarts repérés sur des marchés Pinnacle liquides (marge faible) et à cote ≤ 10 sont plus
fiables que les autres. Elle vient du bilan du 5 au 25/10 : au-delà de 8 % de marge Pinnacle le CLV passe de +3 % à
−1,8 %, et les cotes > 10 perdent 35 % à mise fixe. Ces seuils ont été lus sur l'historique : le rejeu de la règle
serait optimiste et ne prouve rien. Seul le suivi prospectif, à partir de DEBUT, compte (aucun rejeu rétrospectif).

La marge de Pinnacle est celle **enregistrée à la prise** (`marge_pinnacle`) : un pari sans mesure est refusé.
La sélection ne lit jamais statut, gain ni CLV. Protocole : docs/strategie-liquidite.md.
"""
from __future__ import annotations

from .laboratoire import heure
from .strategie_commune import (nombre_fini, correspondance_prouvee, edge_coherent,
                                ligne_non_quart, issue_valide)

LIQUIDITE = {
    "cle": "liquidite_sure", "nom": "Liquidité sûre", "court": "Liquidité sûre",
    "debut": "2026-10-25T16:30:00+00:00", "version": "1", "mise": 10,
    "prospectif_seulement": True, "maximum_jour": 10,
    "regles": ("Pinnacle · Winamax/Betclic/Unibet/PMU · marge Pinnacle ≤ 8 % · cote 1,30–10 · écart 2–12 % · "
               "15 min avant le match · 1 pari/match · max 10/j · mise fictive 10 €"),
    "reference": "Pinnacle", "bookmakers": ("Winamax", "Betclic", "Unibet", "PMU"),
    "marches": ("RESULTAT_1N2", "VAINQUEUR", "DRAW_NO_BET", "TOTAL", "HANDICAP"),
    "marge_max": 0.08, "cote_min": 1.30, "cote_max": 10.0, "edge_min": 0.02, "edge_max": 0.12,
    "avance_min_minutes": 15, "fraicheur_max_minutes": 15,
}


def motif_refus_liquidite(p: dict) -> str | None:
    """Uniquement des informations connues à la prise."""
    c = LIQUIDITE
    if p.get("reference") != c["reference"] or p.get("bookmaker") not in c["bookmakers"]:
        return "référence ou bookmaker hors périmètre"
    if p.get("marche") not in c["marches"] or p.get("periode") not in ("MATCH", "TEMPS_REG") or p.get("suspect"):
        return "marché, période ou opportunité hors périmètre"
    if p.get("sport") in ("tennis", "volley") and p.get("marche") != "VAINQUEUR":
        return "tennis et volley : vainqueur uniquement"
    marge = nombre_fini(p.get("marge_pinnacle"))
    if marge is None:
        return "marge Pinnacle non mesurée"
    if marge > c["marge_max"]:
        return "marge Pinnacle trop élevée"
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
    if edge is None or not c["edge_min"] <= edge <= c["edge_max"]:
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


def paris_liquidite(paris: list[dict], depuis: str | None = None) -> set[int]:
    """Première prise admissible par événement, 10 par jour de Paris au plus.

    Pas de bilan rétrospectif : un rejeu explicite renvoie l'ensemble vide."""
    if depuis is not None:
        return set()
    from .strategies_prudentes import selection_unique  # import local : évite le cycle
    eligibles = {id(p) for p in paris if motif_refus_liquidite(p) is None}
    return selection_unique(paris, eligibles, LIQUIDITE["debut"], LIQUIDITE["maximum_jour"])["selection"]
