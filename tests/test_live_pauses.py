"""Tests de calcul et refus des signaux invérifiables, sans réseau ni mise."""
import math
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from statistics import NormalDist

import pytest

from cotes.live_pauses import (
    ClosingContext, FairPrice, GaussianModel, LiveQuote, Market, Outcome,
    PauseState, PoissonModel, Policy, SetsModel, evaluate_l1, evaluate_l2,
    fair_reference, fit_gaussian, fit_poisson, fit_sets, set_match_probability,
)

NOW = datetime(2026, 10, 15, 19, 0, tzinfo=timezone.utc)


def quote(sport="football", boundary="HT", scope="REGULATION", score=(0, 0),
          name="RESULTAT_1N2", issue="DOM", unit="goals", line=None):
    state = PauseState("match-1", sport, "cycle-1", "book-score", "native-1", NOW, NOW,
                       score, boundary, "pause", "sets" if sport in {"tennis", "volley"} else
                       "goals" if sport in {"football", "hockey", "handball"} else
                       "runs" if sport == "baseball" else "points")
    market = Market("match-1", sport, name, issue, scope, unit, "rules-v1", line)
    return LiveQuote(market, state, "Betclic", NOW, NOW, 2.4, True, "price-1")


def reference(q, probability=.5):
    return FairPrice(replace(q, bookmaker="Pinnacle", odds=1.9,
                             state=replace(q.state, source="pinnacle-score", source_event_id="p-1")),
                     probability, probability, margin=.05)


def closing(sport="football", scope="REGULATION"):
    return ClosingContext("match-1", sport, "Pinnacle", NOW - timedelta(hours=1),
                          NOW - timedelta(hours=1, seconds=20),
                          NOW - timedelta(hours=1, seconds=25), "rules-v1", "research-v1", scope)


@pytest.mark.parametrize("sport,boundary,scope,score,name,unit", [
    ("football", "HT", "REGULATION", (0, 0), "RESULTAT_1N2", "goals"),
    ("hockey", "P1", "REGULATION", (1, 0), "RESULTAT_1N2", "goals"),
    ("basket", "QT1", "INCLUDING_OT", (20, 18), "VAINQUEUR", "points"),
    ("handball", "HT", "REGULATION", (15, 14), "RESULTAT_1N2", "goals"),
    ("tennis", "SET1", "SETS", (0, 1), "VAINQUEUR", "sets"),
    ("volley", "SET2", "SETS", (1, 1), "VAINQUEUR", "sets"),
    ("rugby", "HT", "REGULATION", (10, 7), "RESULTAT_1N2", "points"),
    ("football_americain", "HT", "INCLUDING_OT", (7, 14), "VAINQUEUR", "points"),
    ("baseball", "TOP3", "INCLUDING_OT", (0, 1), "VAINQUEUR", "runs"),
])
def test_l1_neuf_sports_papier(sport, boundary, scope, score, name, unit):
    q = quote(sport, boundary, scope, score, name=name, unit=unit)
    d = evaluate_l1(q, reference(q), NOW)
    assert d.accepted and d.edge == pytest.approx(.2)
    assert d.mode == "paper"


@pytest.mark.parametrize("change,reason", [
    ({"phase": "live"}, "not_a_confirmed_pause"),
    ({"phase": "suspended"}, "not_a_confirmed_pause"),
    ({"boundary": "FT"}, "not_a_confirmed_pause"),
    ({"updated_at": NOW - timedelta(seconds=16)}, "stale_state"),
    ({"updated_at": NOW + timedelta(seconds=1)}, "stale_state"),
    ({"updated_at": NOW.replace(tzinfo=None)}, "stale_state"),
    ({"source_event_id": ""}, "unknown_state"),
    ({"score": (True, 0)}, "unknown_state"),
    ({"score_unit": "sets"}, "score_unit_mismatch"),
    ({"resumes_at": NOW + timedelta(seconds=15)}, "pause_ending"),
])
def test_l1_refuse_pause_non_verifiee(change, reason):
    q = quote()
    q = replace(q, state=replace(q.state, **change))
    assert evaluate_l1(q, reference(q), NOW).reason == reason


@pytest.mark.parametrize("change,reason", [
    ({"active": False}, "unavailable_price"),
    ({"price_id": ""}, "unavailable_price"),
    ({"odds": float("nan")}, "unavailable_price"),
    ({"odds": float("inf")}, "unavailable_price"),
    ({"updated_at": NOW - timedelta(seconds=31)}, "stale_price"),
    ({"updated_at": NOW - timedelta(seconds=11)}, "price_state_skew"),
])
def test_l1_refuse_prix_non_verifie(change, reason):
    q = quote()
    assert evaluate_l1(replace(q, **change), reference(q), NOW).reason == reason


def test_l1_meme_score_ne_suffit_pas():
    q = quote("hockey", "P1")
    r = reference(q)
    for change in ({"boundary": "P2"}, {"cycle": "autre"}, {"score": (1, 0)}):
        altered = replace(r, quote=replace(r.quote, state=replace(r.quote.state, **change)))
        assert evaluate_l1(q, altered, NOW).reason == "state_mismatch"
    altered = replace(r, quote=replace(r.quote, market=replace(r.quote.market, scope="INCLUDING_OT")))
    assert evaluate_l1(q, altered, NOW).reason == "contract_mismatch"


def test_l1_skew_entre_sources_et_non_seulement_dans_cycle():
    q = quote()
    r = reference(q)
    r = replace(r, quote=replace(r.quote, updated_at=NOW - timedelta(seconds=12),
                                state=replace(r.quote.state, updated_at=NOW - timedelta(seconds=12))))
    assert evaluate_l1(q, r, NOW).reason == "cross_source_skew"


def test_prix_pinnacle_marche_complet_marge_retiree():
    q = quote()
    qs = tuple(replace(q, bookmaker="Pinnacle", odds=o, market=replace(q.market, issue=i))
               for i, o in zip(("DOM", "NUL", "EXT"), (2.1, 3.3, 3.6)))
    refs = fair_reference(qs, NOW)
    assert sum(r.probability for r in refs) == pytest.approx(1)
    assert refs[0].probability < 1 / 2.1
    with pytest.raises(ValueError):
        fair_reference(qs[:2], NOW)
    with pytest.raises(ValueError):
        fair_reference((qs[0], qs[0], qs[2]), NOW)
    with pytest.raises(ValueError):
        fair_reference(tuple(replace(x, odds=1.1) for x in qs), NOW)


def test_betfair_bornes_carnet_et_liquidite():
    q = quote("tennis", "SET1", "SETS", (0, 1), name="VAINQUEUR", unit="sets")
    qs = tuple(replace(q, bookmaker="Betfair", odds=1.99, market=replace(q.market, issue=i))
               for i in ("DOM", "EXT"))
    refs = fair_reference(qs, NOW, lay_odds=(2.01, 2.01), liquidity=(50, 50))
    assert refs[0].lower_probability < refs[0].probability == pytest.approx(.5)
    assert evaluate_l1(q, refs[0], NOW).edge < .2
    for lays, amounts in [((2.01, 2.01), (0, 50)), ((1.98, 2.01), (50, 50)),
                          ((2.5, 2.5), (50, 50))]:
        with pytest.raises(ValueError):
            fair_reference(qs, NOW, lay_odds=lays, liquidity=amounts)


def test_push_inconnu_ne_devient_pas_roi_l1():
    q = quote(name="TOTAL", issue="PLUS", line=2)
    r = reference(q)
    assert evaluate_l1(q, r, NOW).reason == "push_probability_unknown"
    d = evaluate_l1(q, replace(r, push_probability=.3), NOW)
    assert d.edge == pytest.approx(.14)
    assert Outcome(.35, .3, .35).edge(2.4) == pytest.approx(d.edge)


@pytest.mark.parametrize("kwargs", [{"quote_age_s": 181}, {"state_age_s": 31},
                                    {"min_edge": float("nan")}, {"skew_s": 16}])
def test_politique_ne_desactive_pas_les_gardes(kwargs):
    with pytest.raises(ValueError):
        Policy(**kwargs)


def test_poisson_symetrique_score_nul_et_masse_du_push():
    q = quote()
    model = PoissonModel(closing(), 1.5, 1.5, .55)
    s = replace(q.state, context_complete=True)
    home = model.project(q.market, s)
    away = model.project(replace(q.market, issue="EXT"), s)
    draw = model.project(replace(q.market, issue="NUL"), s)
    assert home.win == pytest.approx(away.win)
    assert home.win + away.win + draw.win == pytest.approx(1)
    under = model.project(replace(q.market, name="TOTAL", issue="MOINS", line=0), s)
    assert under.win == 0
    assert under.push == pytest.approx(math.exp(-1.65))
    assert under.loss == pytest.approx(1 - math.exp(-1.65))


def test_poisson_score_acquis_et_temps_restant():
    q = quote("hockey", "P1", score=(1, 0))
    model = PoissonModel(closing("hockey"), 3, 3)
    assert model.project(q.market, replace(q.state, boundary="P2")).win > model.project(q.market, q.state).win
    with pytest.raises(ValueError):
        model.project(replace(q.market, scope="INCLUDING_OT"), q.state)
    with pytest.raises(ValueError):
        PoissonModel(closing(), 1.5, 1.5).project(quote().market, quote().state)


def test_calibration_poisson_retrouve_intensites_et_refuse_1n2_incompatible():
    q = quote()
    base = PoissonModel(closing(), 1.8, 1.1, .999999)
    # Projection presque pleine durée pour produire un marché synthétique connu.
    probs = tuple(base.project(replace(q.market, issue=i), q.state).win for i in ("DOM", "NUL", "EXT"))
    over = base.project(replace(q.market, name="TOTAL", issue="PLUS", line=2.5), q.state).win
    fitted = fit_poisson(closing(), probs, 2.5, over, second_half_share=.55)
    assert fitted.home_rate == pytest.approx(1.8, abs=1e-5)
    assert fitted.away_rate == pytest.approx(1.1, abs=1e-5)
    with pytest.raises(ValueError, match="incompatible"):
        fit_poisson(closing(), (.1, .8, .1), 2.5, .5)


def test_gaussien_ecart_total_sigmas_distincts_et_push():
    q = quote("basket", "HT", score=(40, 42), unit="points")
    model = fit_gaussian(closing("basket"), -8.5, .5, 160.5, .5,
                         sigma_difference=11.5, sigma_total=17)
    assert model.mean_difference == 8.5 and model.mean_total == 160.5
    d = model.project(q.market, q.state)
    assert d.win > .5 and d.push == 0  # 1N2 : le nul est une perte pour DOM
    tie = model.project(replace(q.market, issue="NUL"), q.state)
    assert tie.win > 0
    with pytest.raises(ValueError):
        model.project(replace(q.market, name="TOTAL", issue="PLUS", line=162.25), q.state)
    h = model.project(replace(q.market, name="HANDICAP", line=-2, issue="DOM"), q.state)
    assert h.push > 0 and sum((h.win, h.push, h.loss)) == pytest.approx(1)
    with pytest.raises(ValueError):
        model.project(replace(q.market, scope="INCLUDING_OT"), q.state)


@pytest.mark.parametrize("sport", ["basket", "handball"])
def test_gaussien_inverse_lignes_non_mediane(sport):
    sd, st, mu, total = 11.5, 17., 6., 160.
    model = fit_gaussian(closing(sport), -3.5, 1 - NormalDist(mu, sd).cdf(3.5),
                         155.5, 1 - NormalDist(total, st).cdf(155.5),
                         sigma_difference=sd, sigma_total=st)
    assert model.mean_difference == pytest.approx(mu)
    assert model.mean_total == pytest.approx(total)


@pytest.mark.parametrize("to_win", [2, 3])
def test_sets_inversion_et_somme_des_issues(to_win):
    model = fit_sets(closing("tennis", "SETS"), .8, to_win, standard_format=True)
    p = model.set_probability
    assert set_match_probability(p, to_win) == pytest.approx(.8)
    assert set_match_probability(.5, to_win, 1, 1) == pytest.approx(.5)
    q = quote("tennis", "SET1", "SETS", (0, 1), name="VAINQUEUR", unit="sets")
    home = model.project(q.market, q.state)
    away = model.project(replace(q.market, issue="EXT"), q.state)
    assert home.win + away.win == pytest.approx(1)
    if to_win == 2:
        assert home.win == pytest.approx(p * p)
        assert .8 == pytest.approx(3 * p * p - 2 * p ** 3)
    else:
        assert home.win != pytest.approx(p * p)


def test_sets_format_special_et_set_decisif():
    c = closing("volley", "SETS")
    model = fit_sets(c, .75, 3, standard_format=True, deciding_set_probability=.6)
    assert set_match_probability(model.set_probability, 3, 2, 2, .6) == pytest.approx(.6)
    with pytest.raises(ValueError):
        fit_sets(c, .75, 3, standard_format=False)
    with pytest.raises(ValueError):
        set_match_probability(.7, 4)


def test_l2_papier_ferme_sur_information_manquante():
    q = quote("tennis", "SET1", "SETS", (0, 1), name="VAINQUEUR", unit="sets")
    model = fit_sets(closing("tennis", "SETS"), .85, 2, standard_format=True)
    assert evaluate_l2(q, model, NOW).reason == "missing_or_exceptional_context"
    q = replace(q, odds=4, state=replace(q.state, context_complete=True))
    d = evaluate_l2(q, model, NOW)
    assert d.accepted and d.mode == "paper" and d.logic == "L2"
    assert d.edge == pytest.approx(d.outcome.win * 4 - 1)
    assert evaluate_l2(replace(q, state=replace(q.state, incidents=("injury",))), model, NOW).reason == \
        "missing_or_exceptional_context"
    assert evaluate_l2(replace(q, market=replace(q.market, rules="different-retirement")), model, NOW).reason == \
        "closing_contract_mismatch"


def test_sets_rebond_seulement_favori_initial_ayant_perdu_set1():
    q = quote("tennis", "SET1", "SETS", (0, 1), name="VAINQUEUR", unit="sets")
    q = replace(q, odds=4, state=replace(q.state, context_complete=True))
    model = fit_sets(closing("tennis", "SETS"), .6, 2, standard_format=True)
    assert evaluate_l2(q, model, NOW).reason == "sets_rebound_filter"
    model = fit_sets(closing("tennis", "SETS"), .8, 2, standard_format=True)
    won = replace(q, state=replace(q.state, score=(1, 0)))
    assert evaluate_l2(won, model, NOW).reason == "sets_rebound_filter"
    # Orientation inverse : favori extérieur.
    model = fit_sets(closing("tennis", "SETS"), .2, 2, standard_format=True)
    away = replace(won, market=replace(q.market, issue="EXT"))
    assert evaluate_l2(away, model, NOW).accepted


@pytest.mark.parametrize("change", [
    {"captured_at": NOW},
    {"captured_at": NOW - timedelta(hours=2)},
    {"oldest_component_at": NOW - timedelta(hours=1, minutes=2)},
    {"reference": "Consensus"}, {"version": ""},
])
def test_cloture_pas_de_fuite_du_futur_ni_source_ambigue(change):
    with pytest.raises(ValueError):
        replace(closing(), **change).validate()


def test_marche_deja_acquis_et_quart_de_ligne_refuses():
    q = quote(score=(2, 0), name="TOTAL", issue="PLUS", line=.5)
    q = replace(q, state=replace(q.state, context_complete=True))
    model = PoissonModel(closing(), 1.5, 1.5, .55)
    assert evaluate_l2(q, model, NOW).reason == "already_decided_market"
    assert evaluate_l2(replace(q, market=replace(q.market, line=2.25)), model, NOW).reason == \
        "unsupported_or_invalid_model"


def test_total_gaussien_ne_peut_pas_redescendre_sous_score_acquis():
    q = quote("handball", "HT", score=(18, 17), unit="goals", name="TOTAL", issue="PLUS", line=34.5)
    q = replace(q, state=replace(q.state, context_complete=True))
    model = GaussianModel(closing("handball"), 2, 60, 4.5, 7)
    assert model.project(q.market, q.state) == Outcome(1, 0, 0)
    assert evaluate_l2(q, model, NOW).reason == "already_decided_market"


def test_l2_aucun_poisson_de_secours_sur_rugby_nfl_baseball():
    for sport, boundary in (("rugby", "HT"), ("football_americain", "HT"), ("baseball", "TOP3")):
        q = quote(sport, boundary, unit="points")
        q = replace(q, state=replace(q.state, context_complete=True))
        assert not evaluate_l2(q, PoissonModel(closing(sport), 3, 2), NOW).accepted


def test_outcome_push_fair_odds_et_ev():
    o = Outcome(.4, .2, .4)
    assert o.fair_odds == 2
    assert o.edge(2) == pytest.approx(0)
    assert o.edge(2.2) == pytest.approx(.08)  # et non 10 %
    with pytest.raises(ValueError):
        Outcome(.5, .2, .5)
