"""Nombre de sources d'une cote française (cotes/simulation.py) : publié sur les fiches et dans les alertes."""
from cotes.simulation import SOURCES_MAX, facteur_sources, sources_par_selection

P = dict(match_id="betclic|1", marche="VAINQUEUR", periode="MATCH", ligne=None, issue="DOM", joueur=None)


def test_sources_distinctes_par_cote():
    s = sources_par_selection([{**P, "reference": "Pinnacle"}, {**P, "reference": "Pinnacle"},
                               {**P, "reference": "Polymarket"}, {**P, "issue": "EXT", "reference": "Pinnacle"},
                               {"reference": "Pinnacle"}])
    assert s[tuple(P.values())] == {"Pinnacle", "Polymarket"} and len(s) == 2


def test_facteur_borne():
    assert [facteur_sources(n) for n in (0, 1, 2, 3, 7)] == [1, 1, 2, 3, SOURCES_MAX]
