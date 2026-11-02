"""Famille Claude Opus : stratégies conçues le 2/11/2026 par Claude, suivies dès DEBUT (docs/strategie-claude-opus.md).

Valeur solide est la règle principale ; Favoris réguliers, Hors football et Handicaps en sont des déclinaisons
plus ciblées (même protocole, mêmes seuils de choix fixés avant la validation), donc corrélées avec elle.

Idée : ne parier que là où la cote juste est fiable et où l'avantage est réel plutôt que du bruit.
- Références sharp (Pinnacle, Polymarket, Betfair, Consensus), lues depuis au plus 180 s.
- Books qui corrigent lentement leurs cotes (Betclic, Unibet, PMU, NetBet). Winamax corrige vite : CLV
  négative sur la période de construction.
- Cote française 1,60–3,50 : zone où les cotes justes sont calibrées (docs/etude-longues-cotes.md) et où la
  marge ne mange pas l'avantage des grosses favorites.
- Écart 4–15 % : sous 4 %, la cote bat à peine la clôture (bruit) ; au-delà de 15 %, c'est plutôt une erreur
  d'association.
- Match dans les 12 h : plus tôt, la cote de référence bouge encore et la CLV est nulle.
- Ni score exact ni mi-temps/fin (probabilités surestimées de moitié) ; équipes non inversées.
- Une seule mise par cote française : la première détection qui passe la règle. Aucun plafond.

Règles choisies sur les détections du 7 au 22/10 parmi sept candidates (meilleure note /100), puis évaluées
une seule fois sur celles du 23/10 au 2/11, sans retouche. La sélection ne lit jamais statut, gain, CLV ni cote
de clôture. Pas de rejeu : seul le suivi depuis DEBUT compte.
"""
from __future__ import annotations

from .decisions import figer_selecteur
from .laboratoire import heure
from .strategie_commune import nombre_fini, preuve_de
from .strategie_gemini_defi import cle_cote, ecart_pct, groupe_marche

DEBUT = "2026-11-03T00:00:00+00:00"

CLAUDE_OPUS_SOLIDE = {
    "cle": "claude_opus_solide", "nom": "Claude Opus · Valeur solide", "court": "Opus solide",
    "debut": DEBUT, "version": "1", "mise": 10.0, "maximum_jour": None, "auteur": "Claude",
    "prospectif_seulement": True,
    "references": ("Pinnacle", "Polymarket", "Betfair", "Consensus"),
    "bookmakers": ("Betclic", "Unibet", "PMU", "NetBet"),
    "marches_exclus": ("CORRECT_SCORE", "HALF_TIME_FULL_TIME"),
    "cote_min": 1.60, "cote_max": 3.50, "ecart_min_pct": 4.0, "ecart_max_pct": 15.0,
    "delai_max_minutes": 720, "age_max_s": 180, "sports_exclus": (), "groupes": None,
    "regles": "Pinnacle, Polymarket, Betfair ou Consensus lus depuis ≤ 180 s · Betclic, Unibet, PMU ou NetBet · "
              "cote 1,60–3,50 · écart 4–15 % · match dans les 12 h · ni score exact ni mi-temps/fin · "
              "équipes non inversées · une seule mise par cote française, la première détection qui passe la "
              "règle · mise fictive 10 € · règles de Claude Opus",
}
_COMMUN = ("références sharp lues depuis ≤ 180 s · Betclic, Unibet, PMU ou NetBet · match dans les 12 h · "
           "équipes non inversées · une mise par cote française · mise fictive 10 € · règles de Claude Opus")

# Favoris réguliers : cotes courtes et écart borné, pour des résultats plus réguliers (moins de variance par pari).
CLAUDE_OPUS_FAVORIS = {**CLAUDE_OPUS_SOLIDE, "cle": "claude_opus_favoris", "nom": "Claude Opus · Favoris réguliers",
                       "court": "Opus favoris", "cote_min": 1.60, "cote_max": 2.20, "ecart_max_pct": 12.0,
                       "regles": "cote 1,60–2,20 · écart 4–12 % · ni score exact ni mi-temps/fin · " + _COMMUN}
# Hors football : le football est le marché le plus efficient (ROI nul sur la construction malgré la CLV).
CLAUDE_OPUS_HORS_FOOT = {**CLAUDE_OPUS_SOLIDE, "cle": "claude_opus_hors_foot", "nom": "Claude Opus · Hors football",
                         "court": "Opus hors foot", "sports_exclus": ("football",),
                         "regles": "tous sports sauf football · cote 1,60–3,50 · écart 4–15 % · ni score exact ni "
                                   "mi-temps/fin · " + _COMMUN}
# Handicaps : les lignes (asiatique, à 3 issues, jeux, sets) des books lents, la meilleure CLV de la construction.
CLAUDE_OPUS_HANDICAPS = {**CLAUDE_OPUS_SOLIDE, "cle": "claude_opus_handicaps", "nom": "Claude Opus · Handicaps",
                         "court": "Opus handicaps", "groupes": ("handicap",), "cote_min": 1.60, "cote_max": 2.60,
                         "regles": "handicaps (asiatique, à 3 issues, jeux, sets) · cote 1,60–2,60 · écart 4–15 % · "
                                   + _COMMUN}
CLAUDE_OPUS = (CLAUDE_OPUS_SOLIDE, CLAUDE_OPUS_FAVORIS, CLAUDE_OPUS_HORS_FOOT, CLAUDE_OPUS_HANDICAPS)


def motif_refus_claude_opus(p: dict, c: dict = CLAUDE_OPUS_SOLIDE) -> str | None:
    """Raison du refus, ou None si la détection passe la règle (avant dédoublonnage). Bornes incluses, sauf
    0 < délai. Ne lit que ce qui est connu à l'instant de la détection."""
    if p.get("reference") not in c["references"]:
        return "référence hors périmètre"
    if p.get("bookmaker") not in c["bookmakers"]:
        return "bookmaker hors périmètre"
    if p.get("marche") in c["marches_exclus"]:
        return "marché à longues cotes"
    if p.get("sport") in c.get("sports_exclus", ()):
        return "sport hors périmètre"
    if c.get("groupes") is not None and groupe_marche(p.get("marche")) not in c["groupes"]:
        return "groupe de marché hors périmètre"
    if preuve_de(p).get("equipes_inversees") is True:
        return "équipes inversées"
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
    if delai > c["delai_max_minutes"]:
        return "détection trop tôt"
    if (t - lu).total_seconds() > c["age_max_s"]:
        return "référence trop ancienne"
    return None


def selection_claude_opus(paris: list[dict], c: dict = CLAUDE_OPUS_SOLIDE, depart: str | None = None) -> set[int]:
    """Première détection qui passe la règle, par cote française, à partir du lancement, dans l'ordre d'arrivée
    (même seconde : ordre du registre). Une détection refusée ne consomme pas la cote."""
    t0 = heure(depart or c["debut"])
    if t0 is None:
        return set()
    candidats = sorted((p for p in paris if heure(p.get("detecte")) and heure(p["detecte"]) >= t0
                        and motif_refus_claude_opus(p, c) is None), key=lambda p: heure(p["detecte"]))
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
        return selection_claude_opus(paris, c)
    selectionner.__name__ = selectionner.__qualname__ = "paris_" + c["cle"]
    selectionner.__doc__ = c["nom"] + " (figée au lancement, " + c["debut"] + "). Pas de rejeu."
    return selectionner


SELECTEURS = {c["cle"]: _selecteur(c) for c in CLAUDE_OPUS}
paris_claude_opus_solide = SELECTEURS["claude_opus_solide"]
