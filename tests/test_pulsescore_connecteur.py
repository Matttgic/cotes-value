"""Traduction des marchés (cotes/pulsescore.py) : entrées invalides isolées."""
from copy import deepcopy

import pytest

from cotes import pulsescore as P
from tests.test_marches import ev, sel


@pytest.mark.parametrize('prix', [None, True, 'invalide', 'nan', 'inf', 1, -2])
def test_prix_invalide_isole_sans_perdre_les_autres(prix):
    market = {'canonicalMarket': 'OVER_UNDER', 'period': 'FULL_TIME', 'rawName': 'Total de buts',
              'selections': [sel('OVER', 'Plus', prix, 2.5), sel('UNDER', 'Moins', '1.9', '2.5')]}
    event = ev([market])
    original = deepcopy(event)
    erreurs = []
    rows = P.traduire(event, 'winamax', 'football', 't', erreurs=erreurs)
    assert [(r['issue'], r['cote'], r['ligne']) for r in rows] == [('MOINS', 1.9, 2.5)]
    assert erreurs and event == original


def test_nul_invalide_ne_transforme_pas_1n2_en_vainqueur():
    m = {'canonicalMarket': 'MATCH_RESULT', 'selections': [sel('HOME', 'Lens', 2),
         sel('DRAW', 'Nul', 'invalide'), sel('AWAY', 'Lille', 3)]}
    rows = P.traduire(ev([m]), 'pmu', 'football', 't')
    assert len(rows) == 2 and {r['marche'] for r in rows} == {'RESULTAT_1N2'}


def test_schema_marche_invalide_ne_fait_pas_perdre_autre_marche():
    m = {'canonicalMarket': 'MATCH_RESULT', 'selections': [sel('HOME', 'Lens', 2)]}
    rows = P.traduire(ev([None, {'selections': 42}, {**m, 'period': []}, m]), 'pmu', 'football', 't')
    assert len(rows) == 1
    assert P.traduire(ev(42), 'pmu', 'football', 't') == []


def test_periodes_ambigues_hockey_et_tennis_refusees():
    assert P.periode('hockey', 'FIRST_HALF', 'Total de buts') is None
    assert P.periode('hockey', 'FIRST_HALF', '1ère période - Total') == 'P1'
    assert P.periode('tennis', 'FIRST_SET', 'Vainqueur') == 'SET1'
    assert P.periode('tennis', 'SECOND_HALF', 'Vainqueur') is None
    assert P.periode('tennis', 'FIRST_QUARTER', 'Vainqueur') is None


