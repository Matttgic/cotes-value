"""Grok 6 à 8 : périmètre de chaque règle, lancement sans rétroactivité, 1/match, plafond, export."""
import pytest

from cotes.strategie_grok import (GROK_1, GROK_6, GROK_7, GROK_8, GROKS, GROKS_V2, motif_refus_grok,
                                  paris_grok_6, paris_grok_7, paris_grok_8)
from cotes.strategies_prudentes import VARIANTES, selections_prudentes
from tests.test_strategie_jules_v2 import pari

T = dict(detecte="2026-10-26T13:30:00Z", debut="2026-10-26T19:00:00Z", lu_reference="2026-10-26T13:29:00Z")
G6 = dict(reference="Pinnacle", bookmaker="PMU", sport="basket", marche="HANDICAP", ligne=-4.5, issue="DOM",
          cote=1.9, cote_juste=1.8, ecart=1.9 / 1.8 - 1, **T)
G7 = dict(reference="Pinnacle", bookmaker="Winamax", sport="football", marche="VAINQUEUR", issue="DOM",
          cote=2.2, cote_juste=2.1, ecart=2.2 / 2.1 - 1, **T)
G8 = {**G6, "reference": "Polymarket"}


def cotes(c, juste):
    return {"cote": c, "cote_juste": juste, "ecart": c / juste - 1}


@pytest.mark.parametrize("regle,base,fonction", [(GROK_6, G6, paris_grok_6), (GROK_7, G7, paris_grok_7),
                                                 (GROK_8, G8, paris_grok_8)])
def test_pari_type_retenu_apres_lancement(regle, base, fonction):
    p = pari("a", **base)
    assert motif_refus_grok(p, regle) is None
    assert fonction([p]) == {id(p)}


@pytest.mark.parametrize("fonction,base", [(paris_grok_6, G6), (paris_grok_7, G7), (paris_grok_8, G8)])
def test_pas_de_retroactivite(fonction, base):
    avant = pari("a", **{**base, "detecte": "2026-10-24T13:30:00Z", "debut": "2026-10-24T19:00:00Z",
                         "lu_reference": "2026-10-24T13:29:00Z"})
    assert fonction([avant]) == set()
    assert fonction([pari("b", **base)], depuis="2026-10-01T00:00:00Z") == set()


def test_grok_6_perimetre():
    assert motif_refus_grok(pari("a", **{**G6, "sport": "football"}), GROK_6)
    assert motif_refus_grok(pari("a", **{**G6, "sport": "volley", "marche": "VAINQUEUR"}), GROK_6)
    assert motif_refus_grok(pari("a", **G8), GROK_6)  # Polymarket : c'est Grok 8
    assert motif_refus_grok(pari("a", **{**G6, "reference": "Smarkets"}), GROK_6)
    assert motif_refus_grok(pari("a", **{**G6, **cotes(1.45, 1.40)}), GROK_6)
    assert motif_refus_grok(pari("a", **{**G6, **cotes(3.8, 3.6)}), GROK_6)
    assert motif_refus_grok(pari("a", **{**G6, **cotes(1.9, 1.86)}), GROK_6)  # écart ~2 %
    assert motif_refus_grok(pari("a", **{**G6, **cotes(2.4, 2.0)}), GROK_6)   # écart 20 %
    assert motif_refus_grok(pari("a", **{**G6, "sport": "tennis", "marche": "TOTAL", "issue": "PLUS"}), GROK_6)
    for s in ("hockey", "handball", "baseball"):
        assert motif_refus_grok(pari("a", **{**G6, "sport": s}), GROK_6) is None


def test_grok_7_perimetre():
    assert motif_refus_grok(pari("a", **{**G7, "sport": "hockey"}), GROK_7) is None
    assert motif_refus_grok(pari("a", **{**G7, "reference": "Polymarket"}), GROK_7)
    assert motif_refus_grok(pari("a", **{**G7, **cotes(1.75, 1.68)}), GROK_7)
    assert motif_refus_grok(pari("a", **{**G7, **cotes(2.6, 2.48)}), GROK_7)
    assert motif_refus_grok(pari("a", **{**G7, **cotes(2.2, 2.14)}), GROK_7)  # écart ~3 % < 4 %
    assert motif_refus_grok(pari("a", **{**G7, "sport": "rugby"}), GROK_7)


def test_grok_8_perimetre():
    assert motif_refus_grok(pari("a", **G6), GROK_8)
    assert motif_refus_grok(pari("a", **{**G8, "sport": "football"}), GROK_8)
    assert motif_refus_grok(pari("a", **{**G8, "reference": "Consensus"}), GROK_8)


def test_garde_fous_communs():
    for k, v in (("lu_reference", "2026-10-26T13:00:00Z"), ("debut", "2026-10-26T13:40:00Z"),
                 ("ligne", -4.25), ("suspect", True), ("bookmaker", "Smarkets")):
        assert motif_refus_grok(pari("a", **{**G6, k: v}), GROK_6)
    faible = pari("a", **G6)
    faible["preuve_prise"] = {**faible["preuve_prise"], "ressemblance_noms": .7}
    assert motif_refus_grok(faible, GROK_6)


def test_une_prise_par_match_et_plafond_journalier():
    memes = [pari("m", **{**G6, "bookmaker": b, "match_id": f"{b}|m", "detecte": f"2026-10-26T13:3{i}:00Z",
                         "lu_reference": f"2026-10-26T13:3{i}:00Z"}) for i, b in enumerate(("PMU", "Betclic"))]
    assert len(paris_grok_6(memes)) == 1
    autres = [pari(f"x{i}", **{**G6, "domicile": f"Eq{i}", "exterieur": f"Ad{i}", "match_id": f"pmu|{i}",
                              "match_reference": f"Eq{i} - Ad{i}",
                              "detecte": f"2026-10-26T13:{10 + i}:00Z", "lu_reference": f"2026-10-26T13:{10 + i}:00Z"})
              for i in range(12)]
    assert len(paris_grok_6(autres)) == GROK_6["maximum_jour"] == 10


def test_branchement_sans_toucher_grok_1_a_5():
    assert [g["cle"] for g in GROKS] == ["grok_1", "grok_2", "grok_3", "grok_4", "grok_5"]
    assert GROK_1["debut"] == "2026-10-25T00:00:00+00:00" and GROK_1["version"] == "1"
    assert all(g in VARIANTES for g in GROKS_V2)
    assert all(g["debut"] == "2026-10-25T01:00:00+00:00" for g in GROKS_V2)
    p, q = pari("a", **G6), pari("b", **{**G7, "domicile": "X", "exterieur": "Y", "match_reference": "X - Y"})
    r = selections_prudentes([p, q])
    assert r["grok_6"] == {id(p)} and r["grok_7"] == {id(p), id(q)} and r["grok_8"] == set()
    assert selections_prudentes([p], depuis="2026-10-26T00:00:00Z")["grok_6"] == set()
