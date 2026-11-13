"""Claude · PMU régulier : stratégie conçue le 13/11/2026 par Claude, suivie dès DEBUT (docs/strategie-claude-pmu.md).

Origine : sur les paris uniques réglés du 10/10 au 12/11/2026 (hors écarts ≥ 7 %, scores exacts et cotes > 10), PMU
est le seul bookmaker dont la CLV par match est positive dans les trois tiers de la période : +0,7 % sur 756 matchs
(+1,1 / +0,9 / +0,9), et +1,4 % sur 281 matchs entre 2,01 et 3,00. Les gros écarts ont une CLV forte mais un ROI très
négatif : ce sont surtout des erreurs de cote ou d'association, d'où le plafond d'écart à 7 %.
Choisie en regardant ces données parmi 102 sous-ensembles : pas une validation. Seul le suivi depuis DEBUT compte.

Règle : PMU, référence Pinnacle ou Polymarket, cote 1,50–3,00, écart 2–7 %, ni score exact ni mi-temps/fin, équipes
non inversées, match pas commencé ; une mise de 10 € par cote française (première détection qui passe la règle).
"""
from __future__ import annotations

from .strategie_claude_signal import _selecteur

DEBUT = "2026-11-13T02:00:00+00:00"

CLAUDE_PMU = {
    "cle": "claude_pmu", "nom": "Claude · PMU régulier", "court": "PMU régulier",
    "debut": DEBUT, "version": "1", "mise": 10.0, "maximum_jour": None, "auteur": "Claude",
    "prospectif_seulement": True,
    "references": ("Pinnacle", "Polymarket"), "bookmakers": ("PMU",),
    "marches_exclus": ("CORRECT_SCORE", "HALF_TIME_FULL_TIME"),
    "cote_min": 1.50, "cote_max": 3.00, "ecart_min_pct": 2.0, "ecart_max_pct": 7.0,
    "regles": "PMU · référence Pinnacle ou Polymarket · cote 1,50–3,00 · écart 2–7 % · ni score exact ni "
              "mi-temps/fin · équipes non inversées · une mise par cote française, la première détection qui passe "
              "la règle · mise fictive 10 € · règles de Claude",
}
SELECTEURS = {CLAUDE_PMU["cle"]: _selecteur(CLAUDE_PMU)}
paris_claude_pmu = SELECTEURS["claude_pmu"]
