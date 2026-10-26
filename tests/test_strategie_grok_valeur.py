"""Grok 9 (Pinnacle) et Grok 10 (Polymarket) : même règle Valeur, une référence chacune."""
import pytest

from cotes.simulation import mise_kelly
from cotes.strategie_grok import (DEBUT_V3, EDGE_MAX_VALEUR, GROK_1, GROK_6, GROK_8, GROK_9, GROK_10,
                                  GROKS, GROKS_V2, GROKS_V3, motif_refus_grok, paris_grok_9, paris_grok_10)
from cotes.strategies_prudentes import VARIANTES, selections_prudentes
from tests.test_strategie_jules_v2 import pari

T = dict(detecte="2026-10-26T20:30:00Z", debut="2026-10-26T22:00:00Z", lu_reference="2026-10-26T20:29:00Z")
# Edge exactement 4 % : cote / cote_juste − 1 = 0,04, donc cote_juste = cote / 1,04.
PIN = dict(reference="Pinnacle", bookmaker="Winamax", sport="football", marche="VAINQUEUR", issue="DOM",
           cote=2.0, cote_juste=2.0 / 1.04, ecart=0.04, **T)
PM = {**PIN, "reference": "Polymarket"}


def avec_cote(base, cote, edge):
    return {**base, "cote": cote, "cote_juste": cote / (1 + edge), "ecart": edge}


@pytest.mark.parametrize("regle,base,fonction", [(GROK_9, PIN, paris_grok_9), (GROK_10, PM, paris_grok_10)])
def test_pari_type_retenu_apres_lancement(regle, base, fonction):
    p = pari("a", **base)
    assert motif_refus_grok(p, regle) is None
    assert fonction([p]) == {id(p)}
    assert regle["mise"] == 10.0


@pytest.mark.parametrize("regle,base,fonction", [(GROK_9, PIN, paris_grok_9), (GROK_10, PM, paris_grok_10)])
def test_bornes_de_cote_incluses(regle, base, fonction):
    for cote in (1.50, 4.50):
        p = pari("a", **avec_cote(base, cote, 0.04))
        assert motif_refus_grok(p, regle) is None
        assert fonction([p]) == {id(p)}
    assert motif_refus_grok(pari("a", **avec_cote(base, 1.49, 0.04)), regle)
    assert motif_refus_grok(pari("a", **avec_cote(base, 4.51, 0.04)), regle)


@pytest.mark.parametrize("regle,base", [(GROK_9, PIN), (GROK_10, PM)])
def test_seuil_edge_4_pourcent(regle, base):
    assert motif_refus_grok(pari("a", **avec_cote(base, 2.0, 0.04)), regle) is None
    assert motif_refus_grok(pari("a", **avec_cote(base, 2.2, 0.039)), regle)
    # Pas le plafond 15 % de Grok 6–8 : un edge cohérent bien au-dessus reste jouable.
    assert motif_refus_grok(pari("a", **avec_cote(base, 2.4, 0.20)), regle) is None
    large = avec_cote(base, 4.50, 4.50 / 1.01 - 1)
    assert motif_refus_grok(pari("a", **large), regle) is None
    assert EDGE_MAX_VALEUR == 3.5


@pytest.mark.parametrize("fonction,base", [(paris_grok_9, PIN), (paris_grok_10, PM)])
def test_pas_de_retroactivite(fonction, base):
    avant = pari("a", **{**base, "detecte": "2026-10-26T19:30:00Z", "debut": "2026-10-26T21:00:00Z",
                         "lu_reference": "2026-10-26T19:29:00Z"})
    assert fonction([avant]) == set()
    assert fonction([pari("b", **base)], depuis="2026-10-01T00:00:00Z") == set()


def test_chaque_strategie_ignore_l_autre_reference_et_les_references_interdites():
    assert motif_refus_grok(pari("a", **PM), GROK_9)
    assert motif_refus_grok(pari("a", **PIN), GROK_10)
    for reference in ("Winamax", "Betclic", "Unibet", "PMU", "OlyBet", "Consensus", "Smarkets", "Kalshi", "Betfair"):
        assert motif_refus_grok(pari("a", **{**PIN, "reference": reference}), GROK_9)
        assert motif_refus_grok(pari("a", **{**PM, "reference": reference}), GROK_10)
    # Bookmaker français comparé à un autre bookmaker français : la référence n'est pas sharp.
    assert motif_refus_grok(pari("a", **{**PIN, "reference": "Betclic", "bookmaker": "Unibet"}), GROK_9)
    assert motif_refus_grok(pari("a", **{**PIN, "bookmaker": "Smarkets"}), GROK_9)
    assert motif_refus_grok(pari("a", **{**PM, "bookmaker": "Kalshi"}), GROK_10)


def test_une_prise_par_match_et_plafond_journalier():
    memes = [pari("m", **{**PIN, "bookmaker": b, "match_id": f"{b}|m", "detecte": f"2026-10-26T20:3{i}:00Z",
                          "lu_reference": f"2026-10-26T20:3{i}:00Z"}) for i, b in enumerate(("Winamax", "Betclic"))]
    assert len(paris_grok_9(memes)) == 1
    autres = [pari(f"x{i}", **{**PIN, "domicile": f"Eq{i}", "exterieur": f"Ad{i}", "match_id": f"win|{i}",
                               "match_reference": f"Eq{i} - Ad{i}",
                               "detecte": f"2026-10-26T20:{10 + i}:00Z", "lu_reference": f"2026-10-26T20:{10 + i}:00Z"})
              for i in range(12)]
    assert len(paris_grok_9(autres)) == GROK_9["maximum_jour"] == 10
    assert GROK_10["maximum_jour"] == 10


def test_prise_figee_ne_recoit_pas_la_nouvelle_cle():
    p = pari("a", **PIN)
    p["selections_figees"] = {"grok_6": {"version": "1", "decide_le": p["detecte"]}}
    assert paris_grok_9([p]) == {id(p)}
    assert selections_prudentes([p])["grok_9"] == set()
    assert selections_prudentes([p])["grok_10"] == set()


def test_branchement_sans_toucher_les_grok_existants():
    assert [g["cle"] for g in GROKS] == ["grok_1", "grok_2", "grok_3", "grok_4", "grok_5"]
    assert [g["cle"] for g in GROKS_V2] == ["grok_6", "grok_7", "grok_8"]
    assert [g["cle"] for g in GROKS_V3] == ["grok_9", "grok_10"]
    assert GROK_1["debut"] == "2026-10-25T00:00:00+00:00"
    assert all(g["debut"] == "2026-10-25T01:00:00+00:00" for g in GROKS_V2)
    assert GROK_6["cote_max"] == 3.50 and GROK_8["edge_max"] == 0.15
    assert all(g in VARIANTES and g["debut"] == DEBUT_V3 for g in GROKS_V3)
    p, q = pari("a", **PIN), pari("b", **{**PM, "domicile": "X", "exterieur": "Y", "match_reference": "X - Y"})
    r = selections_prudentes([p, q])
    assert r["grok_9"] == {id(p)} and r["grok_10"] == {id(q)}
    assert r["grok_6"] == set() and r["grok_8"] == set()
    assert selections_prudentes([p], depuis="2026-10-26T00:00:00Z")["grok_9"] == set()


def test_plancher_kelly_deja_tenu_sans_changer_le_calcul_commun():
    """Dans la bande (edge ≥ 4 %, cote ≤ 4,50), le Kelly ¼ existant reste ≥ 0,25 % de 1 000 €.

    Plus petite mise : 1 000 × ¼ × 0,04 / (4,50 − 1) ≈ 2,86 €, au-dessus de 2,50 €.
    À 1,50 et 4 %, la mise touche le plafond de 2 % (20 €). Le plancher n'est pas
    branché sur le calcul global, qui sert aussi aux stratégies déjà lancées.
    """
    plancher = 1000 * 0.0025
    bas = mise_kelly({"cote": 4.50, "ecart": 0.04})
    assert bas == round(1000 * 0.25 * 0.04 / (4.50 - 1), 2)
    assert bas >= plancher
    assert mise_kelly({"cote": 1.50, "ecart": 0.04}) == 20.0
    assert mise_kelly({"cote": 2.0, "ecart": 0.04}) == 10.0
