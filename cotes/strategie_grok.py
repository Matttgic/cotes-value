"""Stratégies Grok : filtres prospectifs basés sur l'analyse des paris simulés historiques.

Les règles sont choisies après lecture de l'historique (branche donnees, paris.json),
donc le rejeu est optimiste. Seul le suivi à partir de DEBUT compte pour la rentabilité.
La sélection ne lit jamais statut, gain ou CLV.
"""
from __future__ import annotations

from .laboratoire import heure
from .strategie_commune import (nombre_fini, correspondance_prouvee, edge_coherent,
                                ligne_non_quart, issue_valide, preuve_de)

DEBUT = "2026-10-25T00:00:00+00:00"
BOOKMAKERS = ("Winamax", "Betclic", "Unibet", "PMU", "OlyBet")
SPORTS_OK = ("football", "basket", "hockey", "tennis", "baseball", "handball")
# Seules références où la value se mesure (jamais un bookmaker français contre un autre).
REFERENCES_SHARP = ("Pinnacle", "Betfair", "Polymarket")


def consensus_prouve(p: dict, seuil: float = 0.85) -> bool:
    """Consensus : chaque référence moyennée doit prouver l'association du match.

    Le Consensus n'a pas de score propre ; on exige celui de chaque composante
    (``preuve_prise.preuves_composantes``), toutes parmi REFERENCES_SHARP, au moins deux.
    """
    preuve = preuve_de(p)
    composantes = preuve.get("preuves_composantes")
    controle = preuve.get("controle")
    if not isinstance(composantes, dict) or len(composantes) < 2:
        return False
    if not set(composantes) <= set(REFERENCES_SHARP):
        return False
    if not isinstance(controle, dict) or controle.get("statut") != "conforme":
        return False
    for c in composantes.values():
        score = nombre_fini(c.get("ressemblance_noms")) if isinstance(c, dict) else None
        if score is None or score < seuil or not c.get("match_id_reference"):
            return False
    return True


def _motif_commun(p: dict, c: dict, preuve_ok=None) -> str | None:
    if p.get("reference") != c["reference"] or p.get("bookmaker") not in c.get("bookmakers", BOOKMAKERS):
        return "référence ou bookmaker hors périmètre"
    if p.get("sport") not in c.get("sports", SPORTS_OK) or p.get("suspect"):
        return "sport ou opportunité hors périmètre"
    if p.get("sport") in ("tennis", "volley") and p.get("marche") != "VAINQUEUR":
        return "tennis/volley : vainqueur uniquement"
    t, debut, lu = heure(p.get("detecte")), heure(p.get("debut")), heure(p.get("lu_reference"))
    if not t or not debut or not lu:
        return "date absente ou invalide"
    if (debut - t).total_seconds() < c.get("avance_min_minutes", 15) * 60:
        return "match trop proche"
    if abs((t - lu).total_seconds()) > c.get("fraicheur_max_minutes", 15) * 60:
        return "référence trop ancienne"
    cote, edge, juste = (nombre_fini(p.get(k)) for k in ("cote", "ecart", "cote_juste"))
    if cote is None or not c["cote_min"] <= cote <= c["cote_max"]:
        return "cote hors intervalle"
    if edge is None or not c["edge_min"] <= edge <= c.get("edge_max", 0.15):
        return "écart hors intervalle"
    if not edge_coherent(cote, juste, edge):
        return "écart incohérent avec la cote juste"
    if not (preuve_ok(p) if preuve_ok else correspondance_prouvee(p, 0.85)):
        return "preuve de correspondance insuffisante"
    if p.get("marche") in ("TOTAL", "HANDICAP") and not ligne_non_quart(p.get("ligne")):
        return "ligne absente ou en quarts"
    if not issue_valide(p.get("marche"), p.get("issue")):
        return "issue invalide"
    return None


GROK_1 = {
    "cle": "grok_1", "nom": "Grok 1 · Polymarket mid", "court": "Grok1 PM mid",
    "debut": DEBUT, "version": "1", "mise": 10.0, "maximum_jour": 8,
    "reference": "Polymarket",
    "cote_min": 1.40, "cote_max": 2.20, "edge_min": 0.025, "edge_max": 0.12,
    "sports": ("football", "tennis", "hockey", "basket"),
    "regles": "Polymarket · cotes 1,40–2,20 · edge 2,5–12 % · sports football/tennis/hockey/basket · 1/match · max 8/j",
}

# v2 (25/10) : Smarkets abandonné, remplacé par Pinnacle (Betfair n'est plus collecté).
GROK_2 = {
    "cle": "grok_2", "nom": "Grok 2 · Pinnacle low", "court": "Grok2 PIN low",
    "debut": DEBUT, "version": "2", "mise": 10.0, "maximum_jour": 6,
    "reference": "Pinnacle",
    "cote_min": 1.30, "cote_max": 2.00, "edge_min": 0.03, "edge_max": 0.15,
    "sports": SPORTS_OK,
    "regles": "Pinnacle · cotes 1,30–2,00 · edge 3–15 % · 1/match · max 6/j",
}

GROK_3 = {
    "cle": "grok_3", "nom": "Grok 3 · Consensus mid", "court": "Grok3 Cons mid",
    "debut": DEBUT, "version": "2", "mise": 10.0, "maximum_jour": 8,
    "reference": "Consensus",
    "cote_min": 1.40, "cote_max": 2.30, "edge_min": 0.02, "edge_max": 0.10,
    "sports": ("football", "basket", "hockey"),
    "regles": "Consensus (Pinnacle/Betfair/Polymarket uniquement, chaque composante associée ≥0,85) · cotes 1,40–2,30 · edge 2–10 % · sports football/basket/hockey · 1/match · max 8/j",
}

GROK_4 = {
    "cle": "grok_4", "nom": "Grok 4 · Polymarket low-odds", "court": "Grok4 PM low",
    "debut": DEBUT, "version": "1", "mise": 10.0, "maximum_jour": 10,
    "reference": "Polymarket",
    "cote_min": 1.30, "cote_max": 1.75, "edge_min": 0.02, "edge_max": 0.08,
    "sports": SPORTS_OK,
    "regles": "Polymarket · cotes 1,30–1,75 · edge 2–8 % · 1/match · max 10/j",
}

GROK_5 = {
    "cle": "grok_5", "nom": "Grok 5 · Multi-sharp low", "court": "Grok5 multi low",
    "debut": DEBUT, "version": "1", "mise": 10.0, "maximum_jour": 12,
    "reference": None,
    "cote_min": 1.30, "cote_max": 1.80, "edge_min": 0.02, "edge_max": 0.08,
    "sports": SPORTS_OK,
    "regles": "Polymarket/Smarkets/Consensus · cotes 1,30–1,80 · edge 2–8 % · 1/match · max 12/j",
}

GROKS = (GROK_1, GROK_2, GROK_3, GROK_4, GROK_5)


def motif_refus_grok(p: dict, c: dict) -> str | None:
    if c["cle"] == "grok_5":
        if p.get("reference") not in ("Polymarket", "Smarkets", "Consensus"):
            return "référence hors multi-sharp"
        dummy = dict(c)
        dummy["reference"] = p.get("reference")
        return _motif_commun(p, dummy)
    if c["cle"] == "grok_3":
        # v2 : le Consensus n'a pas de score propre, la preuve vient de ses composantes.
        return _motif_commun(p, c, preuve_ok=consensus_prouve)
    return _motif_commun(p, c)


def paris_grok(paris: list[dict], c: dict, depuis: str | None = None) -> set[int]:
    from .strategies_prudentes import selection_unique
    if depuis is not None:
        return set()
    eligibles = {id(p) for p in paris if motif_refus_grok(p, c) is None}
    return selection_unique(paris, eligibles, c["debut"], c["maximum_jour"])["selection"]


def paris_grok_1(paris, depuis=None): return paris_grok(paris, GROK_1, depuis)
def paris_grok_2(paris, depuis=None): return paris_grok(paris, GROK_2, depuis)
def paris_grok_3(paris, depuis=None): return paris_grok(paris, GROK_3, depuis)
def paris_grok_4(paris, depuis=None): return paris_grok(paris, GROK_4, depuis)
def paris_grok_5(paris, depuis=None): return paris_grok(paris, GROK_5, depuis)
