"""Fusion 1 : réunion des trois stratégies recommandées le 8/11/2026, un seul pari par match
(docs/recommandees.md).

Membres figés au lancement : les trois stratégies retenues ce jour-là par cotes/recommandations.py (note /100
version 2, calculée par match ; critères et choix dans la documentation). Ce sont trois règles du laboratoire :

- Polymarket · cotes 1,5–3 · écart ≥ 2 % · ≤ 36 h (POL-1.5-3-e2-h36) ;
- Pinnacle · cotes 1,3–2 · écart ≥ 2 % · ≤ 36 h (PIN-1.3-2-e2-h36) ;
- Polymarket · cotes 2–5 · écart ≥ 2 % · ≤ 36 h (POL-2-5-e2-h36).

Fusion 1 ne suit pas la liste des recommandées : si une recommandée est remplacée plus tard, Fusion 1 garde ses
trois membres d'origine. Une autre combinaison serait une nouvelle stratégie (Fusion 2), avec sa propre date de départ.

Un pari est pris quand l'une d'elles le prend, à condition que le match n'ait encore aucun pari de la fusion : la
première prise du match l'emporte (à la même seconde, le plus gros écart). Pas de plafond par jour. La sélection
ne lit ni statut, ni gain, ni CLV. Les membres ne changent pas quand le classement change : le suivi compte depuis
DEBUT. Le rejeu depuis le 14/10 est optimiste (membres choisis après avoir vu ces résultats).
"""
from __future__ import annotations

DEBUT = "2026-11-08T08:00:00+00:00"           # 9 h à Paris, après la mise en ligne
MEMBRES = ("POL-1.5-3-e2-h36", "PIN-1.3-2-e2-h36", "POL-2-5-e2-h36")

RECOMMANDEE_FUSION = {
    "cle": "recommandee_fusion", "nom": "Fusion 1 · recommandées du 8/11", "court": "Fusion 1",
    "debut": DEBUT, "version": "1", "mise": 10.0, "maximum_jour": None, "auteur": "Claude",
    "prospectif_seulement": True, "membres": MEMBRES,
    "regles": "Pinnacle 1,3–2 ou Polymarket 1,5–5 · écart ≥ 2 % · ≤ 36 h avant le match · un seul pari par "
              "match (la première prise d'un des trois membres) · mise fictive 10 € · membres figés le 8/11/2026",
}


def selection_membres(paris: list[dict]) -> set[int]:
    """Paris pris par au moins un membre (prises figées de chaque règle du laboratoire, depuis le 14/10)."""
    from .laboratoire import DEBUT_SUIVI, REGLES, selectionner
    regles = {r.id: r for r in REGLES}
    out: set[int] = set()
    for cle in MEMBRES:
        out |= {id(p) for p in selectionner(paris, regles[cle], DEBUT_SUIVI)}
    return out


def paris_fusion(paris: list[dict], depuis: str | None = None) -> set[int]:
    """Prises de la fusion. Sans ``depuis`` : suivi depuis DEBUT, décisions figées (cotes/decisions.py).
    Avec ``depuis`` : rejeu non figé (affiché comme tel, optimiste)."""
    from .decisions import appliquer
    from .strategies_prudentes import selection_unique
    choisis = selection_unique(paris, frozenset(selection_membres(paris)), depuis or DEBUT)["selection"]
    return choisis if depuis is not None else appliquer(paris, choisis, RECOMMANDEE_FUSION["cle"])
