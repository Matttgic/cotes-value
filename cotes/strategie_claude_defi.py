"""Stratégies Claude Défi 1, 2 et 3 : règles de Claude (recherche du 1er novembre 2026), suivies dès DEBUT.

Famille distincte des Grok, des Défi et des Gemini Défi : ce module a ses propres règles, son propre
dédoublonnage et ses propres clés (« claude_defi_1 », « _2 », « _3 »). Il ne modifie aucune stratégie
figée. Règles exactes, rejeu et avertissements : docs/strategie-claude-defi.md.

Les règles ont été choisies sur le bloc « construction » de l'export de recherche
(paris_regles_sharp_defi.csv, avant le 18/10/2026 02:29:01 UTC), puis évaluées une seule fois sur le bloc
« validation », sans retouche. La sélection ne lit jamais statut, gain, CLV ni cote de clôture : seulement ce
qui est connu à l'instant de la détection. Mêmes correspondances avec l'export que Gemini Défi (``cle_cote``,
``groupe_marche``, ``ecart_pct``, délai et âge de la référence signés).
"""
from __future__ import annotations

from .decisions import figer_selecteur
from .laboratoire import heure
from .strategie_commune import nombre_fini, preuve_de
from .strategie_gemini_defi import cle_cote, ecart_pct, groupe_marche

DEBUT = "2026-11-02T01:00:00+00:00"
AUTEUR = "Claude"
REFERENCES_SHARP = ("Pinnacle", "Betfair", "Polymarket")
AGE_MAX_S = 180            # âge maximal de la cote de référence (détection − lecture), signé

_COMMUN = ("Pinnacle, Betfair ou Polymarket · référence lue depuis ≤ 180 s · équipes non inversées · "
           "une seule mise par cote française, la première détection qui passe la règle · "
           "mise fictive 10 € · règles de Claude")


def _regle(**kw) -> dict:
    base = {"debut": DEBUT, "version": "1", "mise": 10.0, "maximum_jour": None, "max_par_match": None,
            "auteur": AUTEUR, "references": REFERENCES_SHARP, "bookmakers": None, "groupes": None,
            "delai_min_minutes": None, "age_max_s": AGE_MAX_S}
    base.update(kw)
    return base


CLAUDE_DEFI_1 = _regle(
    cle="claude_defi_1", nom="Claude Défi 1 · Gros écart 12 h", court="ClDéfi1 écart",
    cote_min=1.30, cote_max=10.0, ecart_min_pct=6.0, ecart_max_pct=30.0, delai_max_minutes=720,
    regles="tous sports et marchés · cote 1,30–10 · écart 6–30 % · 0 < délai ≤ 720 min · " + _COMMUN)

CLAUDE_DEFI_2 = _regle(
    cle="claude_defi_2", nom="Claude Défi 2 · Handicaps", court="ClDéfi2 handicaps",
    groupes=("handicap",),
    cote_min=1.30, cote_max=4.0, ecart_min_pct=5.0, ecart_max_pct=30.0, delai_max_minutes=720,
    regles="handicaps (asiatique, à 3 issues, sets, jeux) · cote 1,30–4 · écart 5–30 % · "
           "0 < délai ≤ 720 min · " + _COMMUN)

CLAUDE_DEFI_3 = _regle(
    cle="claude_defi_3", nom="Claude Défi 3 · Books lents 2–12 h", court="ClDéfi3 books lents",
    bookmakers=("Betclic", "PMU"),
    cote_min=1.30, cote_max=10.0, ecart_min_pct=5.0, ecart_max_pct=30.0,
    delai_min_minutes=120, delai_max_minutes=720,
    regles="Betclic et PMU seulement · cote 1,30–10 · écart 5–30 % · 120 < délai ≤ 720 min · " + _COMMUN)

CLAUDE_DEFIS = (CLAUDE_DEFI_1, CLAUDE_DEFI_2, CLAUDE_DEFI_3)


def motif_refus_claude_defi(p: dict, c: dict) -> str | None:
    """Raison du refus, ou None si la détection passe la règle (avant dédoublonnage). Bornes incluses,
    sauf le délai : 0 < délai (Claude Défi 3 : 120 < délai), délai ≤ borne haute."""
    if p.get("reference") not in c["references"]:
        return "référence hors périmètre"
    preuve = preuve_de(p)
    if preuve.get("equipes_inversees") is True:
        return "équipes inversées"
    if c["bookmakers"] is not None and p.get("bookmaker") not in c["bookmakers"]:
        return "bookmaker hors périmètre"
    if c["groupes"] is not None and groupe_marche(p.get("marche")) not in c["groupes"]:
        return "groupe de marché hors périmètre"
    cote = nombre_fini(p.get("cote"))
    if cote is None or not c["cote_min"] <= cote <= c["cote_max"]:
        return "cote hors intervalle"
    e = ecart_pct(p)
    if e is None or not c["ecart_min_pct"] <= e <= c["ecart_max_pct"]:
        return "écart hors intervalle"
    t, debut, lu = heure(p.get("detecte")), heure(p.get("debut")), heure(p.get("lu_reference"))
    if not t or not debut or not lu:
        return "date absente ou invalide"
    delai = (debut - t).total_seconds() / 60
    if delai <= 0:
        return "match déjà commencé"
    if c["delai_min_minutes"] is not None and delai <= c["delai_min_minutes"]:
        return "détection trop tard"
    if delai > c["delai_max_minutes"]:
        return "détection trop tôt"
    if (t - lu).total_seconds() > c["age_max_s"]:
        return "référence trop ancienne"
    return None


def selection_claude_defi(paris: list[dict], c: dict, depart: str) -> set[int]:
    """Première détection qui passe la règle, par cote française, à partir de ``depart``, dans l'ordre
    d'arrivée (à la même seconde, ordre du registre). Une détection refusée ne consomme pas la cote.
    Aucun plafond par match ni par jour."""
    t0 = heure(depart)
    if t0 is None:
        return set()
    candidats = sorted((p for p in paris if heure(p.get("detecte")) and heure(p["detecte"]) >= t0
                        and motif_refus_claude_defi(p, c) is None), key=lambda p: heure(p["detecte"]))
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
        # Pas de rejeu : seul le suivi depuis la mise en service compte.
        if depuis is not None:
            return set()
        return selection_claude_defi(paris, c, c["debut"])
    selectionner.__name__ = selectionner.__qualname__ = "paris_" + c["cle"]
    selectionner.__doc__ = c["nom"] + " (figée au lancement, " + c["debut"] + ")."
    return selectionner


paris_claude_defi_1 = _selecteur(CLAUDE_DEFI_1)
paris_claude_defi_2 = _selecteur(CLAUDE_DEFI_2)
paris_claude_defi_3 = _selecteur(CLAUDE_DEFI_3)
SELECTEURS = {c["cle"]: f for c, f in zip(CLAUDE_DEFIS, (
    paris_claude_defi_1, paris_claude_defi_2, paris_claude_defi_3))}
