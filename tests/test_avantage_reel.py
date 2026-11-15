"""Avantage réel (docs/avantage-reel.md) : statistiques, corrections et CLV Pinnacle du script."""
import numpy as np
import pytest

from scripts.avantage_reel import (NEGATIF, NON_PROUVE, PROBABLE, PROUVE, benjamini_hochberg, cloture_pinnacle, grappes,
                                   holm, paris_necessaires, rapport, verdict)


def test_holm_et_benjamini_hochberg_sur_un_cas_calcule_a_la_main():
    p = [0.01, 0.04, 0.03, 0.005]
    assert holm(p) == pytest.approx([0.03, 0.06, 0.06, 0.02])
    assert benjamini_hochberg(p) == pytest.approx([0.02, 0.04, 0.04, 0.02])
    assert holm([0.6, 0.9]) == [1.0, 1.0]


def test_les_paris_d_un_meme_match_forment_une_seule_unite():
    num, den = grappes(np.array([10.0, -10.0, 5.0]), np.array([10.0, 10.0, 10.0]), ["a", "a", "b"])
    assert num.tolist() == [0.0, 5.0] and den.tolist() == [20.0, 10.0]


def test_rapport_intervalle_et_p_valeurs_coherents():
    rng = np.random.default_rng(1)
    gains = np.where(rng.random(400) < 0.6, 10.0, -10.0)        # 60 % de gagnés à cote 2 : ROI attendu +20 %
    r = rapport(gains, np.full(400, 10.0), 4000, np.random.default_rng(2))
    assert r["valeur"] == pytest.approx(gains.sum() / 4000)
    assert r["ic"][0] < r["valeur"] < r["ic"][1]
    assert r["ic"][0] > 0 and r["p_pos"] < 0.025 and r["p_neg"] > 0.975      # l'intervalle exclut zéro : p < 2,5 %
    nul = rapport(np.tile([10.0, -10.0], 200), np.full(400, 10.0), 4000, np.random.default_rng(3))
    assert nul["valeur"] == 0 and nul["ic"][0] < 0 < nul["ic"][1] and 0.3 < nul["p_pos"] < 0.7
    assert rapport(np.array([1.0]), np.array([1.0]), 100, rng) is None


def test_paris_necessaires_croit_avec_la_correction_et_quand_l_effet_baisse():
    assert paris_necessaires(1.0, 0.05) == 3140                 # (1,96 + 0,84)² / 0,05²
    assert paris_necessaires(1.0, -0.05) == 3140
    assert paris_necessaires(1.0, 0.05, tests=192) > 2 * paris_necessaires(1.0, 0.05)
    assert paris_necessaires(1.0, 0.01) > 20 * paris_necessaires(1.0, 0.05)
    assert paris_necessaires(1.0, 0) is None


def _pari(reference, cote, juste, **plus):
    return {"reference": reference, "bookmaker": "PMU", "match_id": "pmu|1", "marche": "VAINQUEUR", "periode": "MATCH",
            "ligne": None, "issue": "DOM", "cote": cote, "statut": "gagne", "debut": "2026-11-01T20:00:00+00:00",
            "cloture_lue": "2026-11-01T19:50:00+00:00", "cote_juste_cloture": juste, "clv": round(cote / juste - 1, 4),
            **plus}


def test_cloture_pinnacle_reprise_du_meme_pari_repere_par_pinnacle():
    pin = _pari("Pinnacle", 2.10, 2.00)
    poly = _pari("Polymarket", 2.20, 2.50)                        # même cote française, vue par Polymarket
    autre = _pari("Polymarket", 1.80, 1.90, issue="EXT")          # autre issue : pas de clôture Pinnacle
    tardif = _pari("Pinnacle", 2.10, 2.00, match_id="pmu|2", cloture_lue="2026-11-01T18:00:00+00:00")   # lue 2 h avant
    clv = cloture_pinnacle([pin, poly, autre, tardif])
    assert clv[id(pin)] == pytest.approx(0.05)
    assert clv[id(poly)] == pytest.approx(2.20 / 2.00 - 1)        # recalculée à la cote du pari, pas à celle du frère
    assert id(autre) not in clv and id(tardif) not in clv


def _ligne(**plus):
    base = {"teste": True, "regles": 500, "roi": 0.05, "roi_ic": [-0.02, 0.12], "roi_p_pos": 0.08, "roi_p_neg": 0.92,
            "roi_p_pos_holm": 1.0, "roi_p_neg_holm": 1.0, "roi_p_pos_bh": 0.6, "roi_p_neg_bh": 1.0,
            "clv": {"moyenne": 0.01}, "clv_pinnacle": {"moyenne": 0.01, "part_mesuree": 0.8}}
    return {**base, **plus}


def test_verdicts():
    assert verdict({"teste": False, "regles": 12})[0] == NON_PROUVE
    assert verdict(_ligne())[0] == NON_PROUVE
    assert verdict(_ligne(roi_p_pos_holm=0.01))[0] == PROUVE
    assert verdict(_ligne(roi_p_pos_bh=0.03))[0] == PROBABLE
    clv_prouvee = {"moyenne": 0.02, "part_mesuree": 0.8, "p_pos_holm": 0.01, "p_neg_bh": 1.0, "roi_moins_clv_ic": [-0.05, 0.09]}
    assert verdict(_ligne(clv_pinnacle=clv_prouvee))[0] == PROBABLE
    # CLV prouvée mais ROI négatif, mesurée sur trop peu de paris, ou contredite par le ROI : pas « probable »
    assert verdict(_ligne(clv_pinnacle=clv_prouvee, roi=-0.03))[0] == NON_PROUVE
    assert verdict(_ligne(clv_pinnacle={**clv_prouvee, "part_mesuree": 0.3}))[0] == NON_PROUVE
    assert verdict(_ligne(clv_pinnacle={**clv_prouvee, "roi_moins_clv_ic": [-0.4, -0.1]}))[0] == NON_PROUVE
    assert verdict(_ligne(roi=-0.2, roi_ic=[-0.3, -0.1], roi_p_neg_bh=0.01))[0] == NEGATIF
    assert verdict(_ligne(roi=-0.02, clv={"moyenne": -0.03, "p_neg_bh": 0.01}))[0] == NEGATIF
    assert verdict(_ligne(clv={"moyenne": -0.03, "p_neg_bh": 0.01}))[0] == NON_PROUVE          # ROI positif
    assert verdict(_ligne(roi=-0.2, roi_ic=[-0.3, -0.1]))[1].startswith("tendance négative")
