"""Claude · Drop Pinnacle : stratégie « dropping odds » conçue le 18/11/2026, suivie dès DEBUT
(docs/strategie-claude-drop.md).

Idée : quand la cote de Pinnacle chute sur une issue, le marché sharp a reçu de l'argent informé ; les bookmakers
français suivent avec retard. Les autres stratégies déclenchent sur l'écart à la cote juste ; celle-ci exige en plus
que cet écart vienne d'une **chute de Pinnacle** : la probabilité juste de Pinnacle a monté d'au moins 3 % par
rapport à son ancre, lue 10 à 60 minutes plus tôt (``mouvement_pinnacle``, cotes/mouvement.py, mesuré à la prise
depuis fin octobre et jamais utilisé seul pour choisir).

Origine : étude du 11/11/2026 (docs/duree-values.md, § 3) : les values où la référence a bougé sans le bookmaker
(311 paris) avaient un ROI de +6,9 % et une CLV de +3,2 %. Douze jours de données : une tendance, pas une preuve.
Seuils posés à la main avant le suivi, sans rejeu.

Règle : Pinnacle seul, mouvement Pinnacle ≥ +3 % sur 10 à 60 min, cote 1,40–4,00, écart 2–10 %, ni score exact ni
mi-temps/fin, équipes non inversées, tous les bookmakers sauf OlyBet, match pas commencé ; une mise de 10 € par cote
française (première détection qui passe la règle). Aucun plafond. La sélection ne lit jamais statut, gain, CLV ni
cote de clôture. Pas de rejeu : seul le suivi depuis DEBUT compte.
"""
from __future__ import annotations

from .strategie_claude_signal import motif_refus_claude_signal
from .strategie_commune import nombre_fini
from .strategie_gemini_defi import premieres_par_cote, selecteur_sans_rejeu

DEBUT = "2026-11-18T05:00:00+00:00"   # 6 h à Paris

CLAUDE_DROP = {
    "cle": "claude_drop", "nom": "Claude · Drop Pinnacle", "court": "Drop Pinnacle",
    "debut": DEBUT, "version": "1", "mise": 10.0, "maximum_jour": None, "auteur": "Claude",
    "prospectif_seulement": True,
    "references": ("Pinnacle",), "bookmakers": ("Betclic", "Unibet", "PMU", "NetBet", "Winamax"),
    "marches_exclus": ("CORRECT_SCORE", "HALF_TIME_FULL_TIME"),
    "cote_min": 1.40, "cote_max": 4.00, "ecart_min_pct": 2.0, "ecart_max_pct": 10.0,
    "chute_min": 0.03,
    "regles": "Pinnacle · probabilité juste de Pinnacle en hausse d'au moins 3 % sur 10 à 60 min (cote en chute) · "
              "cote 1,40–4,00 · écart 2–10 % · ni score exact ni mi-temps/fin · équipes non inversées · tous les "
              "bookmakers sauf OlyBet · une mise par cote française, la première détection qui passe la règle · "
              "mise fictive 10 € · règles de Claude",
}


def motif_refus_claude_drop(p: dict, c: dict = CLAUDE_DROP) -> str | None:
    """Raison du refus, ou None si la détection passe la règle (avant dédoublonnage). Bornes incluses. Ne lit que
    ce qui est connu à l'instant de la détection."""
    motif = motif_refus_claude_signal(p, c)
    if motif:
        return motif
    mouvement = nombre_fini(p.get("mouvement_pinnacle"))
    if mouvement is None:
        return "mouvement Pinnacle non mesuré"
    if round(mouvement, 4) < c["chute_min"]:
        return "pas de chute Pinnacle"
    return None


def selection_claude_drop(paris: list[dict], c: dict = CLAUDE_DROP, depart: str | None = None) -> set[int]:
    """Première détection qui passe la règle, par cote française, à partir du lancement. Une détection refusée ne
    consomme pas la cote."""
    return {id(p) for p in premieres_par_cote(paris, lambda p: motif_refus_claude_drop(p, c), depart or c["debut"])}


paris_claude_drop = selecteur_sans_rejeu(CLAUDE_DROP, lambda paris: selection_claude_drop(paris), " Pas de rejeu.")
