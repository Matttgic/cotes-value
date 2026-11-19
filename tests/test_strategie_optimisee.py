import pytest

from cotes.strategie_optimisee import (OPTIMISEE, OPTIMISEE_POLYMARKET, avantage_compte, mise_kelly_16,
                                       motif_refus_optimisee, selection_optimisee)


def _p(**k):
    base = {"reference": "Pinnacle", "bookmaker": "PMU", "sport": "football", "marche": "RESULTAT_1N2", "cote": 2.2,
            "ecart": 0.04, "ecart_polymarket": 0.06, "detecte": "2026-11-20T10:00:00+00:00",
            "debut": "2026-11-20T18:00:00+00:00", "match_id": "pmu|1", "periode": "MATCH", "ligne": None,
            "issue": "1"}
    return {**base, **k}


def test_regle():
    assert motif_refus_optimisee(_p()) is None
    assert motif_refus_optimisee(_p(reference="Polymarket")) is None
    assert motif_refus_optimisee(_p(ecart=0.03)) is None
    assert motif_refus_optimisee(_p(ecart=0.0299)) == "écart trop faible"
    assert motif_refus_optimisee(_p(cote=5.0)) is None
    assert motif_refus_optimisee(_p(cote=5.01)) == "cote hors intervalle"
    assert motif_refus_optimisee(_p(bookmaker="Winamax")) == "bookmaker écarté"
    assert motif_refus_optimisee(_p(bookmaker="OlyBet")) == "bookmaker écarté"
    assert motif_refus_optimisee(_p(sport="volley")) == "sport écarté"
    assert motif_refus_optimisee(_p(sport="basket", marche="TOTAL")) == "marché écarté pour ce sport"
    assert motif_refus_optimisee(_p(sport="basket", marche="TOTAL_DOM")) is None
    assert motif_refus_optimisee(_p(sport="basket", marche="HANDICAP")) is None
    assert motif_refus_optimisee(_p(sport="football", marche="TOTAL")) is None
    assert motif_refus_optimisee(_p(debut="2026-11-21T10:00:00+00:00")) is None            # 24 h pile
    assert motif_refus_optimisee(_p(debut="2026-11-21T10:00:01+00:00")) == "match trop lointain"
    assert motif_refus_optimisee(_p(debut="2026-11-20T10:00:00+00:00")) == "match déjà commencé"
    assert motif_refus_optimisee(_p(preuve_prise={"equipes_inversees": True})) is not None


def test_variante_polymarket():
    c = OPTIMISEE_POLYMARKET
    assert motif_refus_optimisee(_p(), c) is None
    assert motif_refus_optimisee(_p(ecart_polymarket=0.05), c) is None
    assert motif_refus_optimisee(_p(ecart_polymarket=0.049), c) == "Polymarket ne confirme pas"
    assert motif_refus_optimisee(_p(ecart_polymarket=None), c) == "Polymarket absent"
    assert motif_refus_optimisee(_p(reference="Polymarket"), c) == "référence hors périmètre"
    assert motif_refus_optimisee(_p(sport="volley"), c) == "sport écarté"


def test_une_mise_par_cote_et_rien_avant_le_lancement():
    a, b = _p(), _p(detecte="2026-11-20T10:05:00+00:00", reference="Polymarket")
    avant = _p(detecte="2026-11-19T10:00:00+00:00", debut="2026-11-19T18:00:00+00:00", match_id="pmu|2")
    refuse_puis_accepte = [_p(match_id="pmu|3", ecart=0.02), _p(match_id="pmu|3", detecte="2026-11-20T10:10:00+00:00")]
    assert selection_optimisee([a, b, avant, *refuse_puis_accepte]) == {id(a), id(refuse_puis_accepte[1])}


def test_mise_kelly_16_suit_l_etude_du_14_11():
    # Exemples de docs/strategie-mises.md (1 000 € de bankroll)
    assert mise_kelly_16({"cote": 2.0, "ecart": 0.04}) == pytest.approx(0.63)
    assert mise_kelly_16({"cote": 2.0, "ecart": 0.07}) == pytest.approx(2.90)
    assert mise_kelly_16({"cote": 1.5, "ecart": 0.10}) == pytest.approx(10.19)
    assert mise_kelly_16({"cote": 2.0, "ecart": 0.025}) == 0.0
    assert mise_kelly_16({"cote": 1.01, "ecart": 0.30}) == 20.0                              # plafond 2 %
    assert avantage_compte(0.06) == pytest.approx((0.0219 + 0.0464) / 2)
    assert avantage_compte(0.20) == avantage_compte(0.10)
    # plus d'avantage compté à 10 % qu'à 3 % : la mise grandit avec l'écart
    assert mise_kelly_16({"cote": 2.0, "ecart": 0.10}) > 40 * mise_kelly_16({"cote": 2.0, "ecart": 0.03})


def test_inscrites_dans_les_variantes():
    from cotes.strategies_prudentes import VARIANTES
    assert OPTIMISEE in VARIANTES and OPTIMISEE_POLYMARKET in VARIANTES
