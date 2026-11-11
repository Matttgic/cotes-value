"""Famille Claude Signal : deux stratégies conçues le 11/11/2026 par Claude, suivies dès DEBUT
(docs/strategie-claude-signal.md).

Idée : les stratégies existantes filtrent la cote, l'écart, le délai, le bookmaker. Celles-ci lisent deux mesures
enregistrées à la prise depuis fin octobre et jamais utilisées pour choisir : l'avis d'une deuxième référence
indépendante, et l'âge réel du prix Pinnacle.

- Double avis : Pinnacle et Polymarket voient chacun, séparément, au moins 2 % de valeur sur la même cote
  française. Deux sources sharp indépendantes qui se trompent ensemble, c'est rare ; une seule peut être en
  retard ou mal associée.
- Prix frais : le prix Pinnacle a moins de 400 s (en-tête ``Age`` du cache Cloudflare, pas l'heure de notre
  lecture) et Pinnacle ne s'éloigne pas de la sélection. Un écart contre un prix de 10 minutes est souvent un
  retard de notre référence, pas une erreur du bookmaker.

Communs aux deux : cote 1,30–5,00 (zone où les cotes justes sont calibrées, docs/etude-longues-cotes.md), écart
2–15 %, ni score exact ni mi-temps/fin, équipes non inversées, tous les bookmakers sauf OlyBet (CLV négative sur
les deux périodes d'étude), match pas commencé. Une seule mise par cote française : la première détection qui
passe la règle. Aucun plafond.

La sélection ne lit jamais statut, gain, CLV ni cote de clôture. Pas de rejeu : seul le suivi depuis DEBUT compte.
"""
from __future__ import annotations

from .decisions import figer_selecteur
from .laboratoire import heure
from .strategie_commune import nombre_fini, preuve_de
from .strategie_gemini_defi import cle_cote, ecart_pct

DEBUT = "2026-11-12T00:00:00+00:00"

_BASE = {
    "debut": DEBUT, "version": "1", "mise": 10.0, "maximum_jour": None, "auteur": "Claude",
    "prospectif_seulement": True,
    "bookmakers": ("Betclic", "Unibet", "PMU", "NetBet", "Winamax"),
    "marches_exclus": ("CORRECT_SCORE", "HALF_TIME_FULL_TIME"),
    "cote_min": 1.30, "cote_max": 5.00, "ecart_min_pct": 2.0, "ecart_max_pct": 15.0,
}
_COMMUN = ("cote 1,30–5,00 · écart 2–15 % · ni score exact ni mi-temps/fin · équipes non inversées · tous les "
           "bookmakers sauf OlyBet · une mise par cote française, la première détection qui passe la règle · "
           "mise fictive 10 € · règles de Claude")

# Double avis : la seconde référence, lue au même cycle, donne elle aussi au moins 2 % (écart enregistré à la prise).
CLAUDE_SIGNAL_DOUBLE = {
    **_BASE, "cle": "claude_signal_double", "nom": "Claude Signal · Double avis", "court": "Signal double",
    "references": ("Pinnacle", "Polymarket"),
    # référence du pari -> champ de l'écart contre l'autre référence
    "second_avis": {"Pinnacle": "ecart_polymarket", "Polymarket": "ecart_pinnacle"}, "second_avis_min_pct": 2.0,
    "regles": "Pinnacle et Polymarket donnent chacun au moins 2 % de valeur sur la même cote française · " + _COMMUN,
}
# Prix frais : âge réel du prix Pinnacle, et pas de mouvement de Pinnacle contre la sélection.
CLAUDE_SIGNAL_FRAIS = {
    **_BASE, "cle": "claude_signal_frais", "nom": "Claude Signal · Prix frais", "court": "Signal frais",
    "references": ("Pinnacle",), "age_prix_max_s": 400, "mouvement_min": -0.005,
    "regles": "Pinnacle, prix de moins de 400 s (âge réel, mesuré) · cote juste Pinnacle pas en hausse de plus de "
              "0,5 % sur 10 à 60 min · " + _COMMUN,
}
CLAUDE_SIGNAL = (CLAUDE_SIGNAL_DOUBLE, CLAUDE_SIGNAL_FRAIS)


def motif_refus_claude_signal(p: dict, c: dict = CLAUDE_SIGNAL_DOUBLE) -> str | None:
    """Raison du refus, ou None si la détection passe la règle (avant dédoublonnage). Bornes incluses. Ne lit que
    ce qui est connu à l'instant de la détection."""
    if p.get("reference") not in c["references"]:
        return "référence hors périmètre"
    if p.get("bookmaker") not in c["bookmakers"]:
        return "bookmaker hors périmètre"
    if p.get("marche") in c["marches_exclus"]:
        return "marché à longues cotes"
    if preuve_de(p).get("equipes_inversees") is True:
        return "équipes inversées"
    cote = nombre_fini(p.get("cote"))
    if cote is None or not c["cote_min"] <= cote <= c["cote_max"]:
        return "cote hors intervalle"
    e = ecart_pct(p)
    if e is None or not c["ecart_min_pct"] <= e <= c["ecart_max_pct"]:
        return "écart hors intervalle"
    t, debut = heure(p.get("detecte")), heure(p.get("debut"))
    if not t or not debut:
        return "date absente ou invalide"
    if debut <= t:
        return "match déjà commencé"
    if "second_avis" in c:
        autre = nombre_fini(p.get(c["second_avis"][p["reference"]]))
        if autre is None:
            return "second avis absent"
        if round(100 * autre, 4) < c["second_avis_min_pct"]:
            return "second avis insuffisant"
    if "age_prix_max_s" in c:
        age = nombre_fini(p.get("age_prix_pinnacle_s"))
        if age is None:
            return "âge du prix non mesuré"
        if not 0 <= age <= c["age_prix_max_s"]:
            return "prix trop ancien"
        mouvement = nombre_fini(p.get("mouvement_pinnacle"))
        if mouvement is not None and mouvement < c["mouvement_min"]:
            return "Pinnacle s'éloigne de la sélection"
    return None


def selection_claude_signal(paris: list[dict], c: dict = CLAUDE_SIGNAL_DOUBLE, depart: str | None = None) -> set[int]:
    """Première détection qui passe la règle, par cote française, à partir du lancement, dans l'ordre d'arrivée
    (même seconde : ordre du registre). Une détection refusée ne consomme pas la cote."""
    t0 = heure(depart or c["debut"])
    if t0 is None:
        return set()
    candidats = sorted((p for p in paris if heure(p.get("detecte")) and heure(p["detecte"]) >= t0
                        and motif_refus_claude_signal(p, c) is None), key=lambda p: heure(p["detecte"]))
    retenus, vues = set(), set()
    for p in candidats:
        cle = cle_cote(p)
        if cle not in vues:
            vues.add(cle)
            retenus.add(id(p))
    return retenus


def _selecteur(c: dict):
    @figer_selecteur(c["cle"])
    def selectionner(paris, depuis=None):
        if depuis is not None:            # pas de rejeu : seul le suivi depuis le lancement compte
            return set()
        return selection_claude_signal(paris, c)
    selectionner.__name__ = selectionner.__qualname__ = "paris_" + c["cle"]
    selectionner.__doc__ = c["nom"] + " (figée au lancement, " + c["debut"] + "). Pas de rejeu."
    return selectionner


SELECTEURS = {c["cle"]: _selecteur(c) for c in CLAUDE_SIGNAL}
paris_claude_signal_double = SELECTEURS["claude_signal_double"]
paris_claude_signal_frais = SELECTEURS["claude_signal_frais"]
