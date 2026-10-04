"""Retrait de la marge du bookmaker : cotes -> probabilités justes.

Méthode « power » (p_i = (1/o_i)^k, k tel que la somme vaut 1) : elle corrige le biais
favori/outsider mieux que la normalisation proportionnelle (Clarke, Kovalchik & Ingram, 2017).
"""
from __future__ import annotations

import math


def proba_justes(cotes: list[float]) -> list[float] | None:
    """Probabilités sans marge d'un marché complet (toutes ses issues). None si invalide."""
    if len(cotes) < 2 or any((c is None) or (c <= 1.0) or math.isnan(c) for c in cotes):
        return None
    inv = [1.0 / c for c in cotes]
    if sum(inv) < 1.0:            # marché sans marge (ou incomplet) : on normalise simplement
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
