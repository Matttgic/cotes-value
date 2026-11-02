"""Retrait de la marge du bookmaker : cotes -> probabilités justes.

Méthode « power » (p_i = (1/o_i)^k, k tel que la somme vaut 1) : elle corrige le biais
favori/outsider mieux que la normalisation proportionnelle (Clarke, Kovalchik & Ingram, 2017).
"""
from __future__ import annotations

import math


def proba_justes(cotes: list[float], complet: bool = True) -> list[float] | None:
    """Probabilités sans marge d'un marché (toutes ses issues si ``complet``). None si invalide.

    ``complet=False`` : les issues lues peuvent n'être qu'une partie du marché (score exact, mi-temps/fin…).
    Une somme des 1/cote inférieure à 1 y signale des issues absentes, pas une absence de marge : les prix
    cotés sont gardés tels quels (marge comprise, donc prudents), sans renormalisation à la hausse. Au-dessus
    de 1, la méthode « power » donne toujours p ≤ 1/cote : la cote juste ne descend jamais sous la cote lue."""
    if len(cotes) < 2 or any((c is None) or not math.isfinite(c) or c <= 1.0 for c in cotes):
        return None
    inv = [1.0 / c for c in cotes]
    if sum(inv) < 1.0:            # marché sans marge : on normalise simplement ; incomplet : prix cotés
        if not complet:
            return inv
        s = sum(inv)
        return [x / s for x in inv]
    k = 1.0
    for _ in range(100):          # Newton : f(k) = sum(inv^k) - 1, décroissante et convexe
        xk = [x ** k for x in inv]
        f = sum(xk) - 1.0
        fp = sum(v * math.log(x) for v, x in zip(xk, inv))
        if fp == 0:
            break
        pas = f / fp
        k = min(max(k - pas, 0.2), 5.0)
        if abs(pas) < 1e-12:
            break
    p = [x ** k for x in inv]
    s = sum(p)
    return [x / s for x in p]


def marge(cotes: list[float]) -> float:
    return sum(1.0 / c for c in cotes) - 1.0
