"""Filtres observés (26/11/2026) : sous-ensembles de la règle principale suivis sur les paris neufs, sans être joués.

Constat du 26/11 sur les paris du 05/10 au 25/11 (choisi sur ces données, donc optimiste) : une cote repérée par
2 références ou plus bat bien plus la clôture (CLV +7,8 % contre +2,6 %), d'autant plus que l'écart est grand.
Le seuil d'écart n'a pas d'optimum net (CLV de +7,8 % à 3 % jusqu'à +14,8 % à 12 %, gain net à peu près stable) :
trois seuils sont figés ici, avant les paris qui les jugent, et un seul (``PRINCIPAL``) porte le test.

Rien n'est joué ni retiré : les paris restent ceux de la règle principale. Seuls les paris détectés après ``GEL``
comptent. Test unique : CLV Pinnacle moyenne > 0, Student unilatéral par match, seuil 5 %, à partir de 30 CLV.
Lecture prévue le 5/12/2026, puis chaque mois ; aucun changement de règle avant au moins 100 paris réglés.
"""
from __future__ import annotations

GEL = "2026-11-26T04:00:00+00:00"
ALPHA = 0.05
MIN_CLV = 30
SOURCES_MIN = 2
SEUILS = (0.05, 0.08, 0.10)
PRINCIPAL = 0.08


def _nom(seuil: float) -> str:
    return f"{SOURCES_MIN} sources ou plus · écart ≥ {round(100 * seuil):d} %"


def construire(paris: list[dict], match_de, clvs: dict[int, float]) -> dict:
    """Bloc ``D.decision.observes`` : un bilan par seuil (ROI et CLV Pinnacle par match), verdict sur le principal."""
    from .decision import _bilan
    from .laboratoire import heure
    from .protocole import moyenne_par_match
    from .regle_principale import retenus
    from .reglement import GAIN
    from .simulation import cle_selection_unique, sources_par_selection
    sources = sources_par_selection(paris)
    gel = heure(GEL)
    pris = [p for p in retenus(paris) if (t := heure(p.get("detecte"))) and t >= gel]
    nb = lambda p: len(sources.get(cle_selection_unique(p), ()))  # noqa: E731
    filtres = []
    for seuil in SEUILS:
        dedans = [p for p in pris if nb(p) >= SOURCES_MIN and isinstance(p.get("ecart"), (int, float))
                  and round(p["ecart"], 6) >= seuil]
        regles = [p for p in dedans if p.get("statut") in GAIN and p.get("mise")]
        ligne = {"nom": _nom(seuil), "seuil": seuil, "principal": seuil == PRINCIPAL, "paris": len(dedans),
                 **_bilan(regles, match_de, clvs), "clv_p": None, "prouve": False}
        avec = [(clvs[id(p)], match_de(p)) for p in regles if id(p) in clvs]
        if len(avec) >= MIN_CLV:
            m = moyenne_par_match([c for c, _ in avec], [k for _, k in avec])
            if m["p"] is not None:
                ligne["clv_p"] = m["p"]
                ligne["prouve"] = ligne["principal"] and m["moyenne"] > 0 and m["p"] < ALPHA
        filtres.append(ligne)
    return {"gel": GEL, "alpha": ALPHA, "min_clv": MIN_CLV, "revoir_le": "2026-12-05", "base": len(pris),
            "filtres": filtres}
