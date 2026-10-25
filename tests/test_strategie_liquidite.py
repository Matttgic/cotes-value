"""Liquidité sûre : marge Pinnacle mesurée, cote ≤ 10, une prise par match, aucun rejeu rétrospectif."""
from cotes.strategie_liquidite import LIQUIDITE, motif_refus_liquidite, paris_liquidite
from cotes.strategies_prudentes import selections_prudentes
from tests.test_strategie_jules_v2 import pari

BON = dict(bookmaker="PMU", sport="football", marche="TOTAL", ligne=2.5, issue="PLUS", marge_pinnacle=.05,
           cote=2.1, cote_juste=2.0, ecart=2.1 / 2.0 - 1,
           detecte="2026-10-25T17:00:00Z", debut="2026-10-25T20:00:00Z", lu_reference="2026-10-25T16:59:00Z")


def test_pari_dans_le_perimetre_est_retenu_apres_le_lancement():
    p = pari("a", **BON)
    assert motif_refus_liquidite(p) is None
    assert paris_liquidite([p]) == {id(p)}


def test_avant_le_lancement_et_en_rejeu_rien():
    p = pari("a", **{**BON, "detecte": "2026-10-25T16:00:00Z", "lu_reference": "2026-10-25T16:00:00Z"})
    assert paris_liquidite([p]) == set()
    assert paris_liquidite([pari("b", **BON)], depuis="2026-10-07T00:00:00Z") == set()


def test_marge_pinnacle_absente_ou_trop_haute_refusee():
    assert motif_refus_liquidite(pari("a", **{**BON, "marge_pinnacle": None})) == "marge Pinnacle non mesurée"
    assert motif_refus_liquidite(pari("a", **{**BON, "marge_pinnacle": .081})) == "marge Pinnacle trop élevée"
    assert motif_refus_liquidite(pari("a", **{**BON, "marge_pinnacle": .08})) is None


def test_refus_hors_perimetre():
    assert motif_refus_liquidite(pari("a", **{**BON, "cote": 12.0, "cote_juste": 11.0, "ecart": 12 / 11 - 1}))
    assert motif_refus_liquidite(pari("a", **{**BON, "bookmaker": "OlyBet"}))
    assert motif_refus_liquidite(pari("a", **{**BON, "cote": 2.4, "cote_juste": 2.0, "ecart": .2}))   # écart > 12 %
    assert motif_refus_liquidite(pari("a", **{**BON, "ligne": 2.25}))
    assert motif_refus_liquidite(pari("a", **{**BON, "sport": "tennis"}))


def test_une_prise_par_match_et_dix_par_jour():
    mêmes = [pari("m", **{**BON, "bookmaker": b, "match_id": f"{b}|m", "detecte": f"2026-10-25T17:0{i}:00Z",
                          "lu_reference": f"2026-10-25T17:0{i}:00Z"}) for i, b in enumerate(("PMU", "Betclic"))]
    assert len(paris_liquidite(mêmes)) == 1
    autres = [pari(f"x{i}", **{**BON, "domicile": f"Eq{i}", "exterieur": f"Ad{i}", "match_id": f"pmu|{i}",
                               "match_reference": f"Eq{i} - Ad{i}", "detecte": f"2026-10-25T17:{i:02d}:00Z",
                               "lu_reference": f"2026-10-25T17:{i:02d}:00Z"}) for i in range(13)]
    assert len(paris_liquidite(autres)) == LIQUIDITE["maximum_jour"]


def test_la_variante_est_exportee_par_les_variantes_prudentes():
    p = pari("a", **BON)
    assert selections_prudentes([p])["liquidite_sure"] == {id(p)}
