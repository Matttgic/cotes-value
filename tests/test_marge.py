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
