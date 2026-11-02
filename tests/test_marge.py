"""Le retrait de marge refuse les prix non finis et conserve les probabilités valides."""
import math
import pytest
from cotes.marge import proba_justes, marge


@pytest.mark.parametrize('invalide', [float('inf'),-float('inf'),float('nan'),None,0,1,-2])
def test_proba_justes_rejette_prix_invalide(invalide):
    assert proba_justes([1.5,invalide]) is None
    assert proba_justes([invalide,invalide]) is None


@pytest.mark.parametrize('cotes', [[2.,3.,4.],[1.9,1.9],[1.2,7.5],[3.,3.],[1e308,1e308]])
def test_proba_justes_normalise_prix_finis(cotes):
    p=proba_justes(cotes)
    assert p is not None and all(math.isfinite(x) and 0<x<1 for x in p)
    assert sum(p)==pytest.approx(1,abs=1e-12)


def test_marge_equilibre_et_marche_a_deux_issues():
    assert marge([2.,2.])==pytest.approx(0,abs=1e-12)
    assert marge([1.9,1.9])==pytest.approx(1/1.9+1/1.9-1)
    assert proba_justes([1.9,1.9])==pytest.approx([.5,.5])


def test_marche_incomplet_jamais_renormalise_a_la_hausse():
    """Score exact Pinnacle du 12/10/2026 (Durban City – Amazulu) : un tiers des issues seulement dans le groupe."""
    cotes = [28.63, 32.67, 16.61, 48.09]
    gonfle = proba_justes(cotes)                         # marché supposé complet : ancienne lecture
    prudent = proba_justes(cotes, complet=False)
    assert all(1 / g < c for g, c in zip(gonfle, cotes))   # ancienne lecture : cote « juste » sous la cote cotée
    assert prudent == pytest.approx([1 / c for c in cotes])
    assert all(1 / p >= c - 1e-9 for p, c in zip(prudent, cotes))


def test_marche_incomplet_avec_marge_reste_sous_les_prix_cotes():
    cotes = [2.0, 3.0, 4.5]                              # Σ 1/cote > 1 : méthode power, p ≤ 1/cote
    p = proba_justes(cotes, complet=False)
    assert p == proba_justes(cotes)
    assert all(x <= 1 / c for x, c in zip(p, cotes))
