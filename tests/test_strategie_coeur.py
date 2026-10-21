"""Cœur value : périmètre, causalité, une prise par match et plafond journalier."""
from cotes.strategie_coeur import COEUR, motif_refus_coeur, paris_coeur
from cotes.strategies_prudentes import selections_prudentes
from tests.test_strategie_jules_v2 import pari

BON = dict(bookmaker="PMU", sport="basket", marche="HANDICAP", ligne=-8.5, issue="DOM",
           cote=1.9, cote_juste=1.8, ecart=1.9 / 1.8 - 1,
           detecte="2026-10-21T13:30:00Z", debut="2026-10-21T17:00:00Z", lu_reference="2026-10-21T13:29:00Z")


def test_pari_dans_le_perimetre_est_retenu_apres_le_lancement():
    p = pari("a", **BON)
    assert motif_refus_coeur(p) is None
    assert paris_coeur([p]) == {id(p)}


def test_avant_le_lancement_rien_et_pas_de_rejeu_retrospectif():
    p = pari("a", **{**BON, "detecte": "2026-10-21T12:59:00Z", "lu_reference": "2026-10-21T12:58:00Z"})
    assert paris_coeur([p]) == set()
    assert paris_coeur([pari("b", **BON)], depuis="2026-10-07T00:00:00Z") == set()


def test_refus_hors_perimetre():
    assert motif_refus_coeur(pari("a", **{**BON, "sport": "football"}))
    assert motif_refus_coeur(pari("a", **{**BON, "bookmaker": "Winamax"}))
    assert motif_refus_coeur(pari("a", **{**BON, "cote": 2.2, "cote_juste": 2.05, "ecart": 2.2 / 2.05 - 1}))
    assert motif_refus_coeur(pari("a", **{**BON, "cote": 1.9, "cote_juste": 1.7, "ecart": 1.9 / 1.7 - 1}))
    assert motif_refus_coeur(pari("a", **{**BON, "sport": "tennis", "marche": "TOTAL", "issue": "PLUS"}))
    assert motif_refus_coeur(pari("a", **{**BON, "ligne": -8.25}))


def test_une_prise_par_match_et_cinq_par_jour():
    mêmes = [pari("m", **{**BON, "bookmaker": b, "match_id": f"{b}|m", "detecte": f"2026-10-21T13:3{i}:00Z",
                          "lu_reference": f"2026-10-21T13:3{i}:00Z"}) for i, b in enumerate(("PMU", "Betclic"))]
    assert len(paris_coeur(mêmes)) == 1
    autres = [pari(f"x{i}", **{**BON, "domicile": f"Eq{i}", "exterieur": f"Ad{i}", "match_id": f"pmu|{i}",
                               "match_reference": f"Eq{i} - Ad{i}", "detecte": f"2026-10-21T13:3{i}:00Z",
                               "lu_reference": f"2026-10-21T13:3{i}:00Z"}) for i in range(7)]
    assert len(paris_coeur(autres)) == COEUR["maximum_jour"]


def test_la_variante_est_exportee_par_les_variantes_prudentes():
    p = pari("a", **BON)
    assert selections_prudentes([p])["coeur_value"] == {id(p)}
