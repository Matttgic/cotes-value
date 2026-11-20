"""Règle principale : la seule règle jugée, figée le 14/11/2026 (audit du 20/11, priorité 1).

Règle (docs/strategie-mises.md, point 2) : cote ≤ 5, écart annoncé ≥ 3 %, hors Winamax et OlyBet, pari pris au plus
24 h avant le match, une mise par cote française (premier pari de la sélection). Elle a été choisie sur les matchs du
05/10 au 25/10 : seuls les paris détectés **après le gel** la jugent (``GEL``). Les exclusions ajoutées le 19/11
(volley, total au basket) ont été choisies sur les données qui les jugent : elles n'en font pas partie.

Un seul test, fixé ici avant de lire la période jugée : CLV moyenne contre la clôture Pinnacle > 0, Student
unilatéral par match, seuil 5 %. Le ROI est donné à côté, sans verdict. Aucune autre ligne du site ne prouve rien.
Ne plus ajouter de stratégie : ``tests/test_regle_principale.py`` bloque le registre à sa taille du 20/11.
"""
from __future__ import annotations

from .laboratoire import heure

GEL = "2026-11-15T00:00:00+01:00"       # lendemain de l'étude du 14/11 (17:17 UTC) : paris neufs seulement
ALPHA = 0.05
MIN_CLV = 30                            # CLV mesurées avant de tester
REGLE = {
    "nom": "Règle du 14/11", "gel": GEL, "cote_max": 5.0, "ecart_min": 0.03,
    "bookmakers_exclus": ("Winamax", "OlyBet"), "avance_max_h": 24.0,
    "texte": "Cote ≤ 5 · écart ≥ 3 % · hors Winamax et OlyBet · au plus 24 h avant le match · une mise par cote "
             "française · jugée sur les paris détectés depuis le 15/11/2026",
}
# Taille du registre au gel des stratégies (20/11/2026) : aucune nouvelle stratégie, aucune nouvelle inscription.
STRATEGIES_MAX = 97
INSCRITES_MAX = 77


def motif_refus(p: dict) -> str | None:
    """Pourquoi un pari sort de la règle principale, ou None. Une valeur absente l'exclut (règle stricte)."""
    cote, ecart = p.get("cote"), p.get("ecart")
    if not isinstance(cote, (int, float)) or cote > REGLE["cote_max"]:
        return "cote"
    if not isinstance(ecart, (int, float)) or round(ecart, 6) < REGLE["ecart_min"]:
        return "écart"
    if p.get("bookmaker") in REGLE["bookmakers_exclus"]:
        return "bookmaker"
    t, debut = heure(p.get("detecte")), heure(p.get("debut"))
    if not t or not debut or not t.tzinfo or not debut.tzinfo:
        return "date"
    if t < heure(GEL):
        return "avant le gel"
    if (debut - t).total_seconds() > REGLE["avance_max_h"] * 3600 or debut <= t:
        return "délai"
    return None


def retenus(paris: list[dict]) -> list[dict]:
    """Paris jugés : pour chaque sélection, la première détection qui passe la règle, après le gel."""
    from .simulation import premiers_par_selection
    passent = [p for p in paris if motif_refus(p) is None]
    uniques = premiers_par_selection(passent)
    return [p for p in passent if id(p) in uniques]


def construire(paris: list[dict], match_de, clvs: dict[int, float]) -> dict:
    """Bloc ``D.decision.principale`` : bilan des paris réglés retenus et verdict du seul test."""
    from .decision import _bilan
    from .protocole import moyenne_par_match
    from .reglement import GAIN
    pris = retenus(paris)
    regles = [p for p in pris if p.get("statut") in GAIN and p.get("mise")]
    out = {"regle": REGLE, "alpha": ALPHA, "paris": len(pris), **_bilan(regles, match_de, clvs),
           "clv_p": None, "prouve": False}
    avec = [(clvs[id(p)], match_de(p)) for p in regles if id(p) in clvs]
    if len(avec) >= MIN_CLV:
        m = moyenne_par_match([c for c, _ in avec], [k for _, k in avec])
        if m["p"] is not None:
            out["clv_p"] = m["p"]
            out["prouve"] = m["moyenne"] > 0 and m["p"] < ALPHA
    return out
