"""Note des stratégies sur 100, calculée par match (docs/notation-strategies.md).

Version 2 (8/11/2026). Plusieurs paris sur un même match ne sont pas des essais indépendants : quand le match tourne
bien, ils gagnent ensemble. La note compte donc les **matchs**, pas les paris : chaque match réunit ses gains et ses
mises avant tout calcul.

Cinq parts, chacune bornée :

- rentabilité prudente (25) : borne basse à 80 % de l'intervalle de confiance du ROI, variance calculée par match ;
- robustesse (20) : ROI une fois retirés les meilleurs matchs (5 %, au moins un) et part du gain apportée par le
  meilleur match. Un résultat qui tient à un ou deux matchs chanceux perd ces points ;
- valeur (25) : CLV moyenne par match et part des matchs qui battent la clôture, ramenées vers 0 et 50 % sur peu
  de matchs ;
- régularité (15) : part de jours gagnants et plus forte baisse rapportée à ce qu'un hasard équilibré produirait
  (mise moyenne par match × √matchs) ;
- solidité (15) : nombre de matchs réglés (échelle logarithmique), durée d'observation, cote moyenne.

Descriptif : la note ne garantit aucun gain futur.
"""
from __future__ import annotations

from collections import defaultdict
from math import ceil, log10, sqrt

VERSION = 2
NOTE_MIN_MATCHS = 10       # en dessous : pas de note
PROVISOIRE_MATCHS = 50     # en dessous : note marquée provisoire
Z80 = 1.2816
PART_MEILLEURS = 0.05      # robustesse : part des meilleurs matchs retirés (au moins un)


def _echelle(x: float | None, bas: float, haut: float) -> float:
    """0 à ``bas``, 1 à ``haut``, linéaire et bornée ; ``bas > haut`` inverse l'échelle."""
    if x is None:
        return 0.0
    return max(0.0, min(1.0, (x - bas) / (haut - bas)))


def par_match(gains: list[float], mises: list[float], matchs: list | None) -> list[tuple[float, float]]:
    """(gain, mise) de chaque match : les paris d'un même match sont additionnés. Sans clé : un match par pari."""
    if matchs is None or len(matchs) != len(gains):
        return list(zip(gains, mises))
    sommes: dict = defaultdict(lambda: [0.0, 0.0])
    for g, m, k in zip(gains, mises, matchs):
        sommes[k][0] += g
        sommes[k][1] += m
    return [(g, m) for g, m in sommes.values()]


def borne_basse_roi(unites: list[tuple[float, float]], z: float = Z80) -> float | None:
    """ROI − z × écart type (estimateur de ratio sur les unités : ici les matchs)."""
    k = len(unites)
    total_mises = sum(m for _, m in unites)
    if k < 2 or total_mises <= 0:
        return None
    roi = sum(g for g, _ in unites) / total_mises
    variance = sum((g - roi * m) ** 2 for g, m in unites) * k / (k - 1) / total_mises ** 2
    return roi - z * sqrt(variance)


def roi_sans_meilleurs(unites: list[tuple[float, float]], part: float = PART_MEILLEURS) -> tuple[float | None, int]:
    """ROI après retrait des meilleurs matchs (``part`` des matchs, au moins un) et nombre de matchs retirés."""
    k = len(unites)
    retires = max(1, ceil(part * k))
    reste = sorted(unites, key=lambda u: u[0])[:k - retires]
    mises = sum(m for _, m in reste)
    return (sum(g for g, _ in reste) / mises if mises > 0 else None), retires


def noter(gains: list[float], mises: list[float], cotes: list[float], clvs: list[float],
          gains_par_jour: list[float], plus_forte_baisse: float, matchs: list | None = None,
          matchs_clv: list | None = None) -> dict | None:
    """Note sur 100 d'une stratégie à partir de ses paris réglés (une valeur par pari, dans le même ordre).

    ``matchs`` : clé du match de chaque pari (mêmes positions que ``gains``) ; ``matchs_clv`` : clé du match de
    chaque CLV de ``clvs``. Sans clés, chaque pari compte pour un match (ancien comportement)."""
    n = len(gains)
    if len(mises) != n or len(cotes) != n:
        return None
    unites = par_match(gains, mises, matchs)
    k = len(unites)
    total_mises = sum(mises)
    if k < NOTE_MIN_MATCHS or total_mises <= 0:
        return None
    total = sum(gains)
    roi = total / total_mises

    borne_basse = borne_basse_roi(unites)
    rentabilite = 25 * _echelle(borne_basse, -0.10, 0.05)

    roi_sans, retires = roi_sans_meilleurs(unites)
    positifs = [g for g, _ in unites if g > 0]
    part_meilleur = max(positifs) / sum(positifs) if positifs else 1.0
    robustesse = 12 * _echelle(roi_sans, -0.05, 0.03) + 8 * _echelle(part_meilleur, 0.30, 0.05)

    if matchs_clv is not None and len(matchs_clv) == len(clvs):
        groupes: dict = defaultdict(list)
        for c, cle in zip(clvs, matchs_clv):
            groupes[cle].append(c)
        clv_matchs = [sum(v) / len(v) for v in groupes.values()]
    else:
        clv_matchs = list(clvs)
    kc = len(clv_matchs)
    clv_ajustee = (sum(clv_matchs) / kc) * kc / (kc + 30) if kc else 0.0
    part_clv = (sum(c > 0 for c in clv_matchs) + 15) / (kc + 30)
    valeur = 15 * _echelle(clv_ajustee, -0.01, 0.03) + 10 * _echelle(part_clv, 0.45, 0.65)

    jours = len(gains_par_jour)
    part_jours = (sum(g > 0 for g in gains_par_jour) + 2) / (jours + 4)
    baisse_normalisee = plus_forte_baisse / ((total_mises / k) * sqrt(k))
    regularite = 7.5 * _echelle(part_jours, 0.35, 0.65) + 7.5 * _echelle(baisse_normalisee, 3.0, 0.5)

    cote_moyenne = sum(cotes) / n
    solidite = (9 * _echelle(log10(k), log10(20), log10(400)) + 3 * min(1.0, jours / 15)
                + 3 * _echelle(cote_moyenne, 8.0, 3.0))

    parts = {"rentabilite": rentabilite, "robustesse": robustesse, "valeur": valeur, "regularite": regularite,
             "solidite": solidite}
    return {"total": round(sum(parts.values())), "version": VERSION, **{c: round(v, 1) for c, v in parts.items()},
            "provisoire": k < PROVISOIRE_MATCHS, "matchs": k,
            "mesures": {"roi": round(100 * roi, 2),
                        "roi_borne_basse_80": round(100 * borne_basse, 2) if borne_basse is not None else None,
                        "roi_sans_meilleurs": round(100 * roi_sans, 2) if roi_sans is not None else None,
                        "meilleurs_retires": retires, "part_meilleur_match": round(100 * part_meilleur, 1),
                        "paris_par_match": round(n / k, 2),
                        "clv_ajustee": round(100 * clv_ajustee, 2), "part_clv_positive": round(100 * part_clv, 1),
                        "part_jours_positifs": round(100 * part_jours, 1),
                        "baisse_normalisee": round(baisse_normalisee, 2), "cote_moyenne": round(cote_moyenne, 2)}}
