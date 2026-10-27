"""Stratégies Défi : deux règles tirées de la recherche CLV, suivies seulement à partir de DEBUT.

Le crible historique (une mise par cote française, première détection qui passe la règle)
est décrit dans docs/strategie-defi.md. Le rejeu est optimiste. La sélection ne lit
jamais statut, gain ou CLV. Les Grok ne sont pas modifiés : ce module a son propre
filtre et son propre dédoublonnage.
"""
from __future__ import annotations

from .laboratoire import heure
from .strategie_commune import correspondance_prouvee, edge_coherent, nombre_fini
from .strategie_grok import BOOKMAKERS

DEBUT = "2026-10-27T01:00:00+00:00"
# Mêmes books français que les Grok. Tuple lu, jamais réécrit.
REFERENCES_DEFI_1 = ("Pinnacle", "Betfair", "Polymarket")
REFERENCES_DEFI_4 = ("Pinnacle",)
FRAICHEUR_MAX_MINUTES = 15
# Clé du rapport : la cote française, pas le match fusionné par alias.
_CLE_COTE = ("match_id", "marche", "periode", "ligne", "issue", "joueur")

_COMMUN = ("preuve de correspondance ≥ 0,85 · référence de moins de 15 min · "
           "une seule mise par cote française, la première détection · "
           "pas de limite par jour · mise fictive 10 € ou Kelly ¼ plafonné 2 %")

DEFI_1 = {
    "cle": "defi_1", "nom": "Défi 1 · Écart fort, match proche", "court": "Défi1 écart fort",
    "debut": DEBUT, "version": "1", "mise": 10.0, "maximum_jour": None,
    "references": REFERENCES_DEFI_1,
    "cote_min": 1.0, "cote_max": 10.0, "edge_min": 0.06, "delai_max_h": 12,
    "regles": ("Pinnacle, Betfair ou Polymarket · jamais un book français, "
               "jamais Smarkets, Kalshi ou le Consensus · écart ≥ 6 % · cote 1–10 · "
               "à moins de 12 h du coup d'envoi, jamais après · " + _COMMUN),
}

DEFI_4 = {
    "cle": "defi_4", "nom": "Défi 4 · Pinnacle très gros écart", "court": "Défi4 PIN gros écart",
    "debut": DEBUT, "version": "1", "mise": 10.0, "maximum_jour": None,
    "references": REFERENCES_DEFI_4,
    "cote_min": 1.0, "cote_max": 10.0, "edge_min": 0.08, "delai_max_h": None,
    "regles": ("Pinnacle seul · écart ≥ 8 % · cote 1–10 · "
               "à n'importe quelle heure avant le coup d'envoi, jamais après · " + _COMMUN),
}

DEFIS = (DEFI_1, DEFI_4)


def motif_refus_defi(p: dict, c: dict) -> str | None:
    if p.get("reference") not in c["references"] or p.get("bookmaker") not in BOOKMAKERS:
        return "référence ou bookmaker hors périmètre"
    if p.get("suspect"):
        return "opportunité signalée suspecte"
    t, debut, lu = heure(p.get("detecte")), heure(p.get("debut")), heure(p.get("lu_reference"))
    if not t or not debut or not lu:
        return "date absente ou invalide"
    # Le crible « délai < 12 h » gardait aussi les détections après le coup d'envoi.
    # Le suivi refuse celles-là : on joue jusqu'à l'instant du début, jamais après.
    delai = (debut - t).total_seconds()
    if delai < 0:
        return "match déjà commencé"
    if c.get("delai_max_h") is not None and delai >= c["delai_max_h"] * 3600:
        return "détection trop tôt"
    if abs((t - lu).total_seconds()) > FRAICHEUR_MAX_MINUTES * 60:
        return "référence trop ancienne"
    cote, edge, juste = (nombre_fini(p.get(k)) for k in ("cote", "ecart", "cote_juste"))
    if cote is None or not c["cote_min"] <= cote <= c["cote_max"]:
        return "cote hors intervalle"
    if edge is None or edge < c["edge_min"]:
        return "écart insuffisant"
    if not edge_coherent(cote, juste, edge):
        return "écart incohérent avec la cote juste"
    if not correspondance_prouvee(p, 0.85):
        return "preuve de correspondance insuffisante"
    return None


def premiers_cotes_francaises(paris: list[dict], eligibles: set[int], depuis: str) -> set[int]:
    """Première détection qui respecte la règle, par cote française.

    La clé est celle de l'analyse : match du bookmaker, marché, période, ligne,
    issue, joueur. Deux books français restent deux mises. Deux références de la
    même cote n'en font qu'une. À la même seconde, l'identifiant départage, pour
    que l'ordre du registre ne change pas le choix.
    """
    depart = heure(depuis)
    if depart is None:
        return set()
    premiers: dict[tuple, dict] = {}
    for p in paris:
        if id(p) not in eligibles:
            continue
        t = heure(p.get("detecte"))
        if t is None or t < depart:
            continue
        cle = tuple(p.get(champ) for champ in _CLE_COTE)
        actuel = premiers.get(cle)
        if actuel is None:
            premiers[cle] = p
            continue
        ta = heure(actuel.get("detecte"))
        if ta is None or t < ta or (t == ta and str(p.get("id") or "") < str(actuel.get("id") or "")):
            premiers[cle] = p
    return {id(p) for p in premiers.values()}


def paris_defi(paris: list[dict], c: dict, depuis: str | None = None) -> set[int]:
    if depuis is not None:
        return set()
    eligibles = {id(p) for p in paris if motif_refus_defi(p, c) is None}
    return premiers_cotes_francaises(paris, eligibles, c["debut"])


def paris_defi_1(paris, depuis=None):
    return paris_defi(paris, DEFI_1, depuis)


def paris_defi_4(paris, depuis=None):
    return paris_defi(paris, DEFI_4, depuis)
