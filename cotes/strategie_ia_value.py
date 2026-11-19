"""Stratégies « IA · Socle sharp », « IA · Sniper écart » et « IA · Consensus multi » : règles d'une IA externe
(rapport du 19/11/2026), suivies dès DEBUT. Règles exactes, chiffres et avertissements : docs/strategie-ia-value.md.

Les seuils ont été choisis par l'IA sur les paris détectés avant le 5/11/2026 (export paris_cotes_value.csv), puis
vérifiés ici sur les paris détectés après, sans retouche. La sélection ne lit jamais statut, gain, CLV, cote de
clôture ni nombre de sources : seulement ce qui est connu à l'instant de la détection.

Dédoublonnage (règles de l'IA) : une sélection (match, marché, période, ligne, issue), tous bookmakers confondus, au
plus une fois (première détection ; à la même seconde, cote puis écart les plus hauts), puis un seul pari par match
(première détection ; à la même seconde, écart puis cote les plus hauts). Socle et Sniper ne gardent que la première
détection de chaque cote française, toutes références confondues (« premiere_prise » de l'export) : si une référence
hors liste l'a vue d'abord, la cote est écartée. Pas de rejeu : seul le suivi depuis DEBUT compte.
"""
from __future__ import annotations

from .laboratoire import heure
from .simulation import premiers_par_selection
from .strategie_commune import nombre_fini, preuve_de
from .strategie_gemini_defi import ecart_pct, selecteur_sans_rejeu

DEBUT = "2026-11-20T00:00:00+00:00"   # 1 h à Paris, après l'inscription au protocole
AUTEUR = "IA externe"
SHARP = ("Pinnacle", "Betfair", "Matchbook")
BOOKMAKERS = ("PMU", "Betclic", "Unibet")
MARCHES_EXCLUS = ("CORRECT_SCORE", "HALF_TIME_FULL_TIME", "HANDICAP_3")
PERIODES = ("MATCH", "TEMPS_REG")

_COMMUN = ("PMU, Betclic ou Unibet · ni volley ni total au basket · sans score exact, mi-temps/fin de match ni "
           "handicap à 3 issues · match entier ou temps réglementaire · une sélection une fois, tous bookmakers "
           "confondus · un seul pari par match · mise fictive 10 € · règles d'une IA externe (19/11)")


def _regle(**kw) -> dict:
    base = {"debut": DEBUT, "version": "1", "mise": 10.0, "maximum_jour": None, "auteur": AUTEUR,
            "prospectif_seulement": True, "max_par_match": 1, "bookmakers": BOOKMAKERS,
            "sports_exclus": ("volley",), "marches_exclus_par_sport": {"basket": ("TOTAL",)},
            "marches_exclus": MARCHES_EXCLUS, "periodes": PERIODES}
    base.update(kw)
    return base


IA_SOCLE = _regle(
    cle="ia_socle_sharp", nom="IA · Socle sharp", court="IA Socle",
    references=SHARP, premiere_prise=True,
    cote_min=1.15, cote_max=4.0, ecart_min_pct=4.0, ecart_max_pct=25.0, delai_max_minutes=1440,
    regles="Pinnacle, Betfair ou Matchbook, première à voir la cote · cote 1,15–4 · écart 4–25 % · "
           "au plus 24 h avant le match · " + _COMMUN)

IA_SNIPER = _regle(
    cle="ia_sniper_ecart", nom="IA · Sniper écart", court="IA Sniper",
    references=SHARP, premiere_prise=True,
    cote_min=1.20, cote_max=3.5, ecart_min_pct=6.0, ecart_max_pct=25.0, delai_max_minutes=720,
    regles="Pinnacle, Betfair ou Matchbook, première à voir la cote · cote 1,20–3,5 · écart 6–25 % · "
           "au plus 12 h avant le match · " + _COMMUN)

IA_CONSENSUS = _regle(
    cle="ia_consensus_multi", nom="IA · Consensus multi", court="IA Consensus",
    references=("Consensus",), premiere_prise=False,
    cote_min=1.15, cote_max=4.0, ecart_min_pct=2.5, ecart_max_pct=25.0, delai_max_minutes=1440,
    regles="Consensus seulement, même s'il voit la cote après une autre référence · cote 1,15–4 · écart 2,5–25 % · "
           "au plus 24 h avant le match · " + _COMMUN)

IA_VALUES = (IA_SOCLE, IA_SNIPER, IA_CONSENSUS)


def motif_refus_ia(p: dict, c: dict) -> str | None:
    """Raison du refus, ou None si la détection passe la règle (avant dédoublonnage). Bornes incluses."""
    if p.get("reference") not in c["references"]:
        return "référence hors périmètre"
    if p.get("bookmaker") not in c["bookmakers"]:
        return "bookmaker hors périmètre"
    sport, marche = p.get("sport"), p.get("marche")
    if sport in c["sports_exclus"]:
        return "sport écarté"
    if marche in c["marches_exclus"] or marche in c["marches_exclus_par_sport"].get(sport, ()):
        return "marché écarté"
    if p.get("periode") not in c["periodes"]:
        return "période écartée"
    if p.get("suspect") or preuve_de(p).get("equipes_inversees") is True:
        return "opportunité suspecte ou équipes inversées"
    cote = nombre_fini(p.get("cote"))
    if cote is None or not c["cote_min"] <= cote <= c["cote_max"]:
        return "cote hors intervalle"
    e = ecart_pct(p)
    if e is None or not c["ecart_min_pct"] <= e <= c["ecart_max_pct"]:
        return "écart hors intervalle"
    t, debut = heure(p.get("detecte")), heure(p.get("debut"))
    if not t or not debut:
        return "date absente ou invalide"
    delai = (debut - t).total_seconds() / 60
    if delai < 0:
        return "match déjà commencé"
    if delai > c["delai_max_minutes"]:
        return "détection trop tôt"
    return None


def _texte(x) -> str:
    return str(x or "").strip().lower()


def cle_match_ia(p: dict) -> tuple:
    """Match selon l'IA : sport, équipes (minuscules, sans espaces autour) et jour UTC du début."""
    debut = heure(p.get("debut"))
    return p.get("sport"), _texte(p.get("domicile")), _texte(p.get("exterieur")), debut.date() if debut else None


def cle_selection_ia(p: dict) -> tuple:
    return cle_match_ia(p), p.get("marche"), p.get("periode"), str(p.get("ligne")), p.get("issue")


def selection_ia(paris: list[dict], c: dict, depart: str) -> set[int]:
    """Paris retenus à partir de ``depart`` : règle, puis une fois par sélection, puis un seul par match. Une
    détection refusée ne consomme ni la sélection ni le match."""
    t0 = heure(depart)
    if t0 is None:
        return set()
    premiers = premiers_par_selection(paris) if c["premiere_prise"] else None
    candidats = [p for p in paris if heure(p.get("detecte")) and heure(p["detecte"]) >= t0
                 and (premiers is None or id(p) in premiers) and motif_refus_ia(p, c) is None]


    def unique(liste, cle, rang):
        vues, garde = set(), []
        for p in sorted(liste, key=rang):
            k = cle(p)
            if k not in vues:
                vues.add(k)
                garde.append(p)
        return garde

    t = lambda p: heure(p["detecte"])  # noqa: E731
    selections = unique(candidats, cle_selection_ia,
                        lambda p: (t(p), -nombre_fini(p.get("cote")), -ecart_pct(p)))
    par_match = unique(selections, cle_match_ia,
                       lambda p: (t(p), -ecart_pct(p), -nombre_fini(p.get("cote"))))
    return {id(p) for p in par_match}


def _selecteur(c: dict):
    return selecteur_sans_rejeu(c, lambda paris: selection_ia(paris, c, c["debut"]), " Pas de rejeu.")


SELECTEURS = {c["cle"]: _selecteur(c) for c in IA_VALUES}
