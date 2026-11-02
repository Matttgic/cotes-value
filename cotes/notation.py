"""Note des stratégies sur 100 : rentable, mais d'abord régulière et solide (docs/notation-strategies.md).

Quatre parts, chacune bornée :

- rentabilité prudente (30) : borne basse à 80 % de l'intervalle de confiance du ROI, pas le ROI lui-même. Un gros
  gain sur peu de paris très variables reste incertain : sa borne basse est négative ;
- valeur (25) : CLV moyenne et part des paris qui battent la clôture, ramenées vers zéro et 50 % sur peu de mesures ;
- régularité (25) : part de jours gagnants et plus forte baisse rapportée à ce qu'un hasard équilibré produirait
  (mise moyenne × √n) ;
- solidité (20) : nombre de paris réglés (échelle logarithmique), durée d'observation, cote moyenne (au-delà de 5,
  les cotes justes sont surestimées de moitié : docs/etude-longues-cotes.md).

Descriptif : aucune stratégie n'en dépend, et une bonne note ne garantit aucun gain futur.
"""
from __future__ import annotations

from math import log10, sqrt

NOTE_MIN_PARIS = 10        # en dessous : pas de note
PROVISOIRE_PARIS = 50      # en dessous : note marquée provisoire
Z80 = 1.2816


def _echelle(x: float | None, bas: float, haut: float) -> float:
    """0 à ``bas``, 1 à ``haut``, linéaire et bornée ; ``bas > haut`` inverse l'échelle."""
    if x is None:
        return 0.0
    return max(0.0, min(1.0, (x - bas) / (haut - bas)))


def noter(gains: list[float], mises: list[float], cotes: list[float], clvs: list[float],
          gains_par_jour: list[float], plus_forte_baisse: float) -> dict | None:
    """Note sur 100 d'une stratégie à partir de ses paris réglés (une valeur par pari, dans le même ordre)."""
    n = len(gains)
    if n < NOTE_MIN_PARIS or len(mises) != n or len(cotes) != n:
        return None
    total_mises = sum(mises)
    if total_mises <= 0:
        return None
    roi = sum(gains) / total_mises
    # Variance du ROI (estimateur de ratio), comme l'intervalle de confiance du Bilan.
    s_gg = sum(g * g for g in gains)
    s_gm = sum(g * m for g, m in zip(gains, mises))
    s_mm = sum(m * m for m in mises)
    variance = max(0.0, s_gg - 2 * roi * s_gm + roi * roi * s_mm) * n / (n - 1) / total_mises ** 2
    borne_basse = roi - Z80 * sqrt(variance)
    rentabilite = 30 * _echelle(borne_basse, -0.10, 0.05)

    k = len(clvs)
    clv_ajustee = (sum(clvs) / k) * k / (k + 50) if k else 0.0
    part_clv = (sum(c > 0 for c in clvs) + 25) / (k + 50)
    valeur = 15 * _echelle(clv_ajustee, -0.01, 0.03) + 10 * _echelle(part_clv, 0.45, 0.65)

    jours = len(gains_par_jour)
    part_jours = (sum(g > 0 for g in gains_par_jour) + 2) / (jours + 4)
    baisse_normalisee = plus_forte_baisse / ((total_mises / n) * sqrt(n))
    regularite = 12.5 * _echelle(part_jours, 0.35, 0.65) + 12.5 * _echelle(baisse_normalisee, 3.0, 0.5)

    cote_moyenne = sum(cotes) / n
    solidite = (12 * _echelle(log10(n), log10(20), log10(500)) + 4 * min(1.0, jours / 15)
                + 4 * _echelle(cote_moyenne, 8.0, 3.0))

    return {"total": round(rentabilite + valeur + regularite + solidite),
            "rentabilite": round(rentabilite, 1), "valeur": round(valeur, 1),
            "regularite": round(regularite, 1), "solidite": round(solidite, 1),
            "provisoire": n < PROVISOIRE_PARIS,
            "mesures": {"roi_borne_basse_80": round(100 * borne_basse, 2), "clv_ajustee": round(100 * clv_ajustee, 2),
                        "part_clv_positive": round(100 * part_clv, 1), "part_jours_positifs": round(100 * part_jours, 1),
                        "baisse_normalisee": round(baisse_normalisee, 2), "cote_moyenne": round(cote_moyenne, 2)}}
