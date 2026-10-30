"""Stratégies Gemini Défi 1, 3, 4 et 5 : règles de Gemini Argon (IA externe), suivies dès DEBUT.

Gemini Défi 2 (consensus multi-sharps) a été abandonnée par Gemini après validation :
elle n'est pas suivie.

Famille distincte des Grok et des Défi : ce module a ses propres règles, son propre
dédoublonnage et ses propres clés (« gemini_defi_1 », « _3 », « _4 », « _5 »). Il ne modifie
aucune stratégie figée. Règles exactes, rejeu et avertissements : docs/strategie-gemini-defi.md.

La sélection ne lit jamais statut, gain, CLV ni cote de clôture : seulement ce qui est connu
à l'instant de la détection. Correspondance avec les colonnes de l'export de recherche
(paris_regles_sharp_defi.csv) :

    cote_fr                    -> p["cote"]
    ecart_pct                  -> 100 × p["ecart"] (arrondi à 4 décimales, comme l'export)
    delai_min                  -> (p["debut"] − p["detecte"]) en minutes
    age_reference_s            -> (p["detecte"] − p["lu_reference"]) en secondes, signé
    marche_type                -> p["marche"]
    groupe_marche              -> GROUPES_MARCHE[p["marche"]], « exotique » sinon
    equipes_inversees          -> p["preuve_prise"]["equipes_inversees"]
    score_association_journal  -> p["preuve_prise"]["ressemblance_noms"]
    cle_cote_fr                -> match_id | marche | periode | ligne | issue | joueur
    evenement                  -> cotes.evenements.identites (match relié entre books)
"""
from __future__ import annotations

from collections import Counter
from datetime import timezone

from .decisions import figer_selecteur
from .laboratoire import heure
from .strategie_commune import nombre_fini, preuve_de

_UTC = timezone.utc
DEBUT = "2026-10-30T01:00:00+00:00"
AUTEUR = "Gemini Argon"
REFERENCES_SHARP = ("Pinnacle", "Betfair", "Polymarket")
# Clé de la cote française : le match du bookmaker (préfixé par le book), le marché, l'issue.
_CLE_COTE = ("match_id", "marche", "periode", "ligne", "issue", "joueur")
# Regroupement de l'export de recherche (colonne groupe_marche) ; tout le reste est « exotique ».
GROUPES_MARCHE = {
    "RESULTAT_1N2": "principal", "VAINQUEUR": "principal", "DRAW_NO_BET": "principal",
    "DOUBLE_CHANCE": "principal", "HANDICAP": "handicap", "HANDICAP_3": "handicap",
    "SETS_HANDICAP": "handicap", "JEUX_HANDICAP": "handicap", "TOTAL": "total", "TOTAL_DOM": "total",
    "TOTAL_EXT": "total", "JEUX_TOTAL": "total", "SETS_TOTAL": "total",
}

_COMMUN = ("Pinnacle, Betfair ou Polymarket · équipes non inversées · une seule mise par cote "
           "française, la première détection qui passe la règle · mise fictive 10 € · règles de Gemini Argon")


def _regle(**kw) -> dict:
    base = {"debut": DEBUT, "version": "1", "mise": 10.0, "maximum_jour": None, "max_par_match": None,
            "auteur": AUTEUR, "references": REFERENCES_SHARP, "sports": None, "marches": None,
            "groupes": None, "delai_min_minutes": None, "score_min": None}
    base.update(kw)
    return base


GEMINI_DEFI_1 = _regle(
    cle="gemini_defi_1", nom="Gemini Défi 1 · Indoor & Glace", court="GemDéfi1 indoor",
    sports=("basket", "hockey", "handball", "volley"),
    cote_min=1.15, cote_max=6.0, ecart_min_pct=4.0, ecart_max_pct=25.0,
    delai_max_minutes=720, age_max_s=180,
    regles="basket, hockey, handball, volley · cote 1,15–6,00 · écart 4–25 % · "
           "0 < délai ≤ 720 min · référence lue depuis ≤ 180 s · " + _COMMUN)

GEMINI_DEFI_3 = _regle(
    cle="gemini_defi_3", nom="Gemini Défi 3 · Sniper principaux", court="GemDéfi3 sniper",
    groupes=("principal",),
    cote_min=1.25, cote_max=10.0, ecart_min_pct=6.0, ecart_max_pct=20.0,
    delai_max_minutes=1440, age_max_s=150, score_min=0.75,
    regles="marchés principaux (1N2, vainqueur, remboursé si nul, double chance) · cote 1,25–10 · "
           "écart 6–20 % · 0 < délai ≤ 1 440 min · référence ≤ 150 s · correspondance ≥ 0,75 · " + _COMMUN)

GEMINI_DEFI_4 = _regle(
    cle="gemini_defi_4", nom="Gemini Défi 4 · Lignes asiatiques", court="GemDéfi4 lignes",
    sports=("football", "basket", "handball", "rugby", "hockey", "football_americain"),
    marches=("HANDICAP", "TOTAL", "TOTAL_DOM", "TOTAL_EXT"),
    cote_min=1.35, cote_max=3.50, ecart_min_pct=4.0, ecart_max_pct=12.0,
    delai_max_minutes=720, age_max_s=140, score_min=0.85,
    regles="football, basket, handball, rugby, hockey, football américain · handicap, total, "
           "total domicile, total extérieur · cote 1,35–3,50 · écart 4–12 % · 0 < délai ≤ 720 min · "
           "référence ≤ 140 s · correspondance ≥ 0,85 · " + _COMMUN)

GEMINI_DEFI_5 = _regle(
    cle="gemini_defi_5", nom="Gemini Défi 5 · Exotiques foot", court="GemDéfi5 exotiques",
    references=("Pinnacle",), sports=("football",), marches=("CORRECT_SCORE", "HALF_TIME_FULL_TIME"),
    cote_min=12.0, cote_max=75.0, ecart_min_pct=8.0, ecart_max_pct=35.0,
    delai_min_minutes=15, delai_max_minutes=720, age_max_s=140, score_min=0.85,
    maximum_jour=10, max_par_match=2,
    regles="Pinnacle seul · football · score exact, mi-temps/fin de match · cote 12–75 · écart 8–35 % · "
           "15 ≤ délai ≤ 720 min · référence ≤ 140 s · correspondance ≥ 0,85 · au plus 2 cotes par match · "
           "au plus 10 mises par jour UTC, dans l'ordre d'arrivée (même seconde : plus fort écart d'abord) · "
           "équipes non inversées · une seule mise par cote française · mise fictive 10 € · "
           "règles de Gemini Argon")

# Gemini Défi 2 (convergence ≥ 2) : abandonnée par Gemini, ni clé ni sélecteur.
GEMINI_DEFIS = (GEMINI_DEFI_1, GEMINI_DEFI_3, GEMINI_DEFI_4, GEMINI_DEFI_5)


def cle_cote(p: dict) -> tuple:
    return tuple(p.get(champ) for champ in _CLE_COTE)


def groupe_marche(marche) -> str:
    return GROUPES_MARCHE.get(marche, "exotique")


def ecart_pct(p: dict) -> float | None:
    e = nombre_fini(p.get("ecart"))
    return None if e is None else round(100 * e, 4)


def motif_refus_gemini_defi(p: dict, c: dict) -> str | None:
    """Raison du refus, ou None si la détection passe la règle (avant dédoublonnage et plafonds)."""
    if p.get("reference") not in c["references"]:
        return "référence hors périmètre"
    preuve = preuve_de(p)
    if preuve.get("equipes_inversees") is True:
        return "équipes inversées"
    if c["sports"] is not None and p.get("sport") not in c["sports"]:
        return "sport hors périmètre"
    marche = p.get("marche")
    if c["marches"] is not None and marche not in c["marches"]:
        return "marché hors périmètre"
    if c["groupes"] is not None and groupe_marche(marche) not in c["groupes"]:
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
    if c["delai_min_minutes"] is not None and delai < c["delai_min_minutes"]:
        return "détection trop tard"
    if delai > c["delai_max_minutes"]:
        return "détection trop tôt"
    if (t - lu).total_seconds() > c["age_max_s"]:
        return "référence trop ancienne"
    if c["score_min"] is not None:
        score = nombre_fini(preuve.get("ressemblance_noms"))
        if score is None or score < c["score_min"]:
            return "correspondance insuffisante"
    return None


def selection_gemini_defi(paris: list[dict], c: dict, depart: str,
                          evenements: dict[int, object] | None = None) -> set[int]:
    """Première détection qui passe la règle, par cote française, à partir de ``depart``.

    Puis, pour les règles plafonnées (Gemini Défi 5), au plus ``max_par_match`` cotes par match
    et ``maximum_jour`` mises par jour UTC de détection, dans l'ordre d'arrivée. Si plusieurs
    détections ont exactement le même horodatage pour la dernière place, celle qui a le plus fort
    écart passe d'abord (section 3 de la réponse finale de Gemini). Une cote écartée par un plafond
    est perdue : sa détection suivante ne la rattrape pas. ``evenements`` (id → match) sert aux
    rejeux ; par défaut, les matchs reliés du registre (cotes.evenements.identites).
    """
    t0 = heure(depart)
    if t0 is None:
        return set()
    plafonnee = c["maximum_jour"] is not None or c["max_par_match"] is not None

    def ordre(p):
        # Ordre d'arrivée. À la même seconde : pour une règle plafonnée (Gemini Défi 5), écart
        # décroissant, ce qui départage la dernière place d'un match ou d'une journée ; sinon, et à
        # écart égal, ordre du registre (tri stable).
        return (heure(p["detecte"]), -(ecart_pct(p) or 0.0) if plafonnee else 0.0)

    candidats = sorted((p for p in paris if heure(p.get("detecte")) and heure(p["detecte"]) >= t0
                        and motif_refus_gemini_defi(p, c) is None), key=ordre)
    premiers, vues = [], set()
    for p in candidats:
        cle = cle_cote(p)
        if cle not in vues:
            vues.add(cle)
            premiers.append(p)
    if not plafonnee:
        return {id(p) for p in premiers}
    if evenements is None:
        from .evenements import identites
        evenements = identites(paris)
    jours, matchs, retenus = Counter(), Counter(), set()
    for p in premiers:
        jour = heure(p["detecte"]).astimezone(_UTC).date().isoformat()
        match = evenements.get(id(p), ("ligne", p.get("id") or id(p)))
        if c["maximum_jour"] is not None and jours[jour] >= c["maximum_jour"]:
            continue
        if c["max_par_match"] is not None and matchs[match] >= c["max_par_match"]:
            continue
        jours[jour] += 1
        matchs[match] += 1
        retenus.add(id(p))
    return retenus


def _selecteur(c: dict):
    @figer_selecteur(c["cle"])
    def selectionner(paris, depuis=None):
        # Pas de rejeu : seul le suivi depuis la mise en service compte.
        if depuis is not None:
            return set()
        return selection_gemini_defi(paris, c, c["debut"])
    selectionner.__name__ = selectionner.__qualname__ = "paris_" + c["cle"]
    selectionner.__doc__ = c["nom"] + " (figée au lancement, " + c["debut"] + ")."
    return selectionner


paris_gemini_defi_1 = _selecteur(GEMINI_DEFI_1)
paris_gemini_defi_3 = _selecteur(GEMINI_DEFI_3)
paris_gemini_defi_4 = _selecteur(GEMINI_DEFI_4)
paris_gemini_defi_5 = _selecteur(GEMINI_DEFI_5)
SELECTEURS = {c["cle"]: f for c, f in zip(GEMINI_DEFIS, (
    paris_gemini_defi_1, paris_gemini_defi_3, paris_gemini_defi_4, paris_gemini_defi_5))}
