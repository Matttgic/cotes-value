"""Optimisée 19/11 : la stratégie figée du 14/11 (docs/strategie-mises.md), moins le volley et le total au basket,
suivie dès DEBUT (docs/strategie-optimisee.md). Variante « + Polymarket » : même règle, référence Pinnacle, et
Polymarket voit aussi un écart d'au moins 5 %.

Origine : analyse de tous les paris au 19/11/2026 (docs/analyse-paris-19-11.md). La règle du 14/11 bat la clôture
Pinnacle sur des paris neufs (depuis le 15/11 : CLV +6,1 % [+1,5 ; +12,8]) ; les paris qu'elle écarte, non
(−0,2 %). Le volley (ROI −15,8 %, négatif sur les trois périodes) et le total au basket (CLV −1,5 %) n'y ont pas de
CLV. La confirmation Polymarket (CLV +9,3 % sur 231 paris, 49 clôtures) est une piste : suivie à part, pas une règle.

Règle : toutes les références, cote ≤ 5, écart ≥ 3 %, tous les bookmakers sauf Winamax et OlyBet, ni volley ni total
au basket (le total d'une équipe reste), détecté au plus 24 h avant le début, match pas commencé, équipes non
inversées ; une mise par cote française (première détection qui passe la règle). La sélection ne lit jamais statut,
gain, CLV ni cote de clôture. Pas de rejeu : seul le suivi depuis DEBUT compte.

Mise conseillée (affichage seul, ``mise_conseillee``) : Kelly au 1/8 sur l'avantage « compté » de l'étude du 14/11,
c'est-à-dire l'écart annoncé rétréci selon ce que la CLV a confirmé (3 % → +0,18 %, 10 % et plus → +8,15 %).
"""
from __future__ import annotations

from .laboratoire import heure
from .strategie_commune import nombre_fini, preuve_de
from .strategie_gemini_defi import ecart_pct, premieres_par_cote, selecteur_sans_rejeu

DEBUT = "2026-11-19T17:00:00+00:00"   # 18 h à Paris, après l'inscription au protocole

OPTIMISEE = {
    "cle": "optimisee_19_11", "nom": "Optimisée 19/11", "court": "Optimisée 19/11",
    "debut": DEBUT, "version": "1", "mise": 10.0, "maximum_jour": None, "auteur": "Claude",
    "prospectif_seulement": True,
    "references": None, "bookmakers_exclus": ("Winamax", "OlyBet"), "sports_exclus": ("volley",),
    "marches_exclus_par_sport": {"basket": ("TOTAL",)},
    "cote_max": 5.0, "ecart_min_pct": 3.0, "avance_max_h": 24.0,
    "regles": "Toutes références · cote ≤ 5 · écart ≥ 3 % · sans Winamax ni OlyBet · sans volley ni total au basket · "
              "au plus 24 h avant le match · équipes non inversées · une mise par cote française, la première "
              "détection qui passe la règle · mise fictive 10 € · analyse du 19/11",
}
OPTIMISEE_POLYMARKET = {
    **OPTIMISEE,
    "cle": "optimisee_19_11_polymarket", "nom": "Optimisée 19/11 + Polymarket", "court": "Optimisée + Poly",
    "references": ("Pinnacle",), "polymarket_min_pct": 5.0,
    "regles": "Règle Optimisée 19/11, référence Pinnacle seulement, et Polymarket voit aussi un écart ≥ 5 % · "
              "une mise par cote française · mise fictive 10 € · piste à confirmer (analyse du 19/11)",
}
OPTIMISEES = (OPTIMISEE, OPTIMISEE_POLYMARKET)

# Avantage « compté » selon l'écart annoncé (docs/strategie-mises.md, partie 3) : écart en %, avantage en fraction.
AVANTAGE_COMPTE = ((3.0, 0.0018), (4.0, 0.0101), (5.0, 0.0219), (7.0, 0.0464), (10.0, 0.0815))
# Kelly 1/8 sur l'avantage corrigé, garde-fou à 5 % (19/11/2026, après 1/16 puis ¼ plafonné à 2 %) : simulation sur
# 3 mois, risque de perdre la moitié 0,1 % si l'avantage est réel, 3 % sinon (contre 10 % et 41 % au ¼).
KELLY_FRACTION_CONSEIL = 1 / 8
KELLY_BANKROLL_CONSEIL = 1000.0       # même bankroll de référence que mise_kelly (rapportée à la bankroll réelle à l'envoi)
KELLY_PLAFOND_CONSEIL = 0.05


def avantage_compte(ecart: float) -> float:
    """Avantage attendu d'un pari, en fraction, selon son écart annoncé (fraction) ; 0 sous 3 %. Interpolation
    linéaire entre les points de l'étude, constant au-delà de 10 %."""
    e = nombre_fini(ecart)
    if e is None:
        return 0.0
    e *= 100
    points = AVANTAGE_COMPTE
    if e < points[0][0]:
        return 0.0
    if e >= points[-1][0]:
        return points[-1][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x0 <= e < x1:
            return y0 + (y1 - y0) * (e - x0) / (x1 - x0)
    return 0.0


def mise_conseillee(p: dict) -> float:
    """Mise Kelly au 1/8 sur l'avantage compté, pour 1 000 € de bankroll, plafonnée à 5 % ; 0 si rien à miser."""
    cote = nombre_fini(p.get("cote"))
    if cote is None or cote <= 1:
        return 0.0
    m = KELLY_BANKROLL_CONSEIL * KELLY_FRACTION_CONSEIL * avantage_compte(p.get("ecart")) / (cote - 1)
    return round(min(m, KELLY_BANKROLL_CONSEIL * KELLY_PLAFOND_CONSEIL), 2)


def motif_refus_optimisee(p: dict, c: dict = OPTIMISEE) -> str | None:
    """Raison du refus, ou None si la détection passe la règle (avant dédoublonnage). Bornes incluses. Ne lit que
    ce qui est connu à l'instant de la détection."""
    if c["references"] is not None and p.get("reference") not in c["references"]:
        return "référence hors périmètre"
    if p.get("bookmaker") in c["bookmakers_exclus"]:
        return "bookmaker écarté"
    sport = p.get("sport")
    if sport in c["sports_exclus"]:
        return "sport écarté"
    if p.get("marche") in c["marches_exclus_par_sport"].get(sport, ()):
        return "marché écarté pour ce sport"
    if p.get("suspect") or preuve_de(p).get("equipes_inversees") is True:
        return "opportunité suspecte ou équipes inversées"
    cote = nombre_fini(p.get("cote"))
    if cote is None or cote <= 1 or cote > c["cote_max"]:
        return "cote hors intervalle"
    e = ecart_pct(p)
    if e is None or e < c["ecart_min_pct"]:
        return "écart trop faible"
    t, debut = heure(p.get("detecte")), heure(p.get("debut"))
    if not t or not debut:
        return "date absente ou invalide"
    if debut <= t:
        return "match déjà commencé"
    if (debut - t).total_seconds() > c["avance_max_h"] * 3600:
        return "match trop lointain"
    if "polymarket_min_pct" in c:
        poly = nombre_fini(p.get("ecart_polymarket"))
        if poly is None:
            return "Polymarket absent"
        if round(100 * poly, 4) < c["polymarket_min_pct"]:
            return "Polymarket ne confirme pas"
    return None


def selection_optimisee(paris: list[dict], c: dict = OPTIMISEE, depart: str | None = None) -> set[int]:
    """Première détection qui passe la règle, par cote française, à partir du lancement. Une détection refusée ne
    consomme pas la cote."""
    return {id(p) for p in premieres_par_cote(paris, lambda p: motif_refus_optimisee(p, c), depart or c["debut"])}


SELECTEURS = {c["cle"]: selecteur_sans_rejeu(c, lambda paris, c=c: selection_optimisee(paris, c), " Pas de rejeu.")
              for c in OPTIMISEES}
