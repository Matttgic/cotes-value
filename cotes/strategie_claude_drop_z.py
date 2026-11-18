"""Claude · Drop z-score : variante de Drop Pinnacle conçue le 18/11/2026, suivie dès DEBUT
(docs/strategie-claude-drop.md, § Variante z-score).

Idée (reprise de kaykyif/pinnacle-odds-radar) : une chute de 3 % est banale sur un marché nerveux et rare sur un
marché calme. On garde la règle de Drop Pinnacle et on exige en plus que la chute soit **inhabituelle pour son
marché** : ``mouvement_z`` ≥ 2, soit au moins deux écarts-types au-dessus du mouvement moyen des cotes Pinnacle du
même type de marché et de la même période (cotes/mouvement.py, statistiques d'avant le cycle).

Règle : celle de Drop Pinnacle (Pinnacle seul, mouvement ≥ +3 % sur 10 à 60 min, cote 1,40–4,00, écart 2–10 %, ni
score exact ni mi-temps/fin, équipes non inversées, tous les bookmakers sauf OlyBet, match pas commencé) + z-score
≥ 2. Une mise de 10 € par cote française (première détection qui passe la règle). Aucun plafond. Seuil posé à la
main avant le suivi, sans rejeu (le z n'existe pas dans les anciens paris). La sélection ne lit jamais statut, gain,
CLV ni cote de clôture.
"""
from __future__ import annotations

from .strategie_claude_drop import CLAUDE_DROP, motif_refus_claude_drop
from .strategie_commune import nombre_fini
from .strategie_gemini_defi import premieres_par_cote, selecteur_sans_rejeu

DEBUT = "2026-11-18T07:00:00+00:00"   # 8 h à Paris : laisse aux statistiques par marché le temps de se remplir

CLAUDE_DROP_Z = {
    **CLAUDE_DROP,
    "cle": "claude_drop_z", "nom": "Claude · Drop z-score", "court": "Drop z-score",
    "debut": DEBUT, "version": "1",
    "z_min": 2.0,
    "regles": "Règle de Drop Pinnacle · chute inhabituelle pour son marché : z-score ≥ 2 (mouvement comparé à la "
              "moyenne et à l'écart-type des mouvements Pinnacle du même marché) · une mise par cote française, la "
              "première détection qui passe la règle · mise fictive 10 € · règles de Claude",
}


def motif_refus_claude_drop_z(p: dict, c: dict = CLAUDE_DROP_Z) -> str | None:
    """Raison du refus, ou None si la détection passe la règle (avant dédoublonnage). Bornes incluses."""
    motif = motif_refus_claude_drop(p, c)
    if motif:
        return motif
    z = nombre_fini(p.get("mouvement_z"))
    if z is None:
        return "z-score non mesuré"
    if round(z, 2) < c["z_min"]:
        return "chute ordinaire pour ce marché"
    return None


def selection_claude_drop_z(paris: list[dict], c: dict = CLAUDE_DROP_Z, depart: str | None = None) -> set[int]:
    """Première détection qui passe la règle, par cote française, à partir du lancement."""
    return {id(p) for p in premieres_par_cote(paris, lambda p: motif_refus_claude_drop_z(p, c), depart or c["debut"])}


paris_claude_drop_z = selecteur_sans_rejeu(CLAUDE_DROP_Z, lambda paris: selection_claude_drop_z(paris), " Pas de rejeu.")
