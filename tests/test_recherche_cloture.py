"""Prédiction de la clôture Pinnacle (docs/recherche.md) : mesures hors échantillon et lecture des historiques."""
import math

import numpy as np
import pytest

from etudes.recherche_cloture import (ajuster, bon_sens, cote_a, lire_football, mesurer_attente, moyenne, predire,
                                       r2_hors_echantillon)


def test_r2_hors_echantillon_vaut_un_si_tout_est_prevu_et_zero_si_rien_ne_l_est():
    rng = np.random.default_rng(1)
    y = np.array([0.1, -0.2, 0.3, -0.1])
    cles = ["a", "a", "b", "c"]
    assert r2_hors_echantillon(y, y, 0.0, cles, rng, 200)[0] == pytest.approx(1.0)
    assert r2_hors_echantillon(y, np.zeros(4), 0.0, cles, rng, 200)[0] == pytest.approx(0.0)
    assert r2_hors_echantillon(y, -y, 0.0, cles, rng, 200)[0] == pytest.approx(-3.0)      # prévoir l'inverse : pire que rien


def test_un_modele_appris_sur_du_bruit_ne_bat_pas_la_cote_immobile():
    rng = np.random.default_rng(2)
    x, y = rng.normal(size=(4000, 1)), rng.normal(size=4000)
    b = ajuster(x[:2000], y[:2000])
    r, bas, haut = r2_hors_echantillon(y[2000:], predire(b, x[2000:]), 0.0, range(2000), rng, 500)
    assert bas < 0 < haut and abs(r) < 0.02
    vrai = 0.5 * x[:, 0] + rng.normal(size=4000)                                           # ici il y a un signal
    b = ajuster(x[:2000], vrai[:2000])
    assert b[1] == pytest.approx(0.5, abs=0.1)
    assert r2_hors_echantillon(vrai[2000:], predire(b, x[2000:]), 0.0, range(2000), rng, 500)[1] > 0.1


def test_moyenne_tire_des_matchs_entiers():
    rng = np.random.default_rng(3)
    m, bas, haut = moyenne([1.0, 1.0, 1.0, -1.0], ["a", "a", "a", "b"], rng, 2000)
    assert m == pytest.approx(0.5)
    assert bas == pytest.approx(-1.0) and haut == pytest.approx(1.0)      # deux matchs : tout « a » ou tout « b » possibles


def test_bon_sens_ignore_les_cotes_qui_n_ont_pas_bouge():
    y, prevu = np.array([0.1, -0.1, 0.0, 0.2]), np.array([0.5, 0.01, 0.3, 0.02])
    assert bon_sens(y, prevu) == pytest.approx(2 / 3)
    assert bon_sens(y, prevu, 0.25) == pytest.approx(1.0)                 # la prévision la plus forte seule


def test_cote_a_donne_la_derniere_cote_connue_et_none_apres_un_retrait():
    temps, cotes = [10.0, 20.0, 30.0], [2.0, None, 2.2]
    assert cote_a(temps, cotes, 5) is None and cote_a(temps, cotes, 10) == 2.0
    assert cote_a(temps, cotes, 25) is None and cote_a(temps, cotes, 99) == 2.2


def test_attendre_compare_le_meme_pari_a_la_meme_cloture():
    p = {"detecte": "2026-11-01T10:00:00+00:00", "debut": "2026-11-01T14:00:00+00:00", "match_id": "pmu|1",
         "bookmaker": "PMU", "ecart": 0.04, "cote": 2.10, "cote_juste_cloture": 2.0}
    t0 = 1793527200.0                                                     # 2026-11-01 10:00 UTC
    r = mesurer_attente(p, [t0 - 600, t0 + 1800], [2.10, 1.95])           # le bookmaker baisse sa cote 30 min après
    assert r["clv"] == pytest.approx(0.05) and r["15 min"] == pytest.approx(0.05)
    assert r["1 h"] == pytest.approx(-0.025) and r["jusqu'au match"] == pytest.approx(-0.025)
    assert mesurer_attente(p, [t0 - 600], [2.30]) is None                 # cote prise introuvable : série incomplète
    court = dict(p, debut="2026-11-01T10:30:00+00:00")
    assert math.isnan(mesurer_attente(court, [t0 - 600], [2.10])["1 h"])  # le match commence avant la fin de l'attente


def test_lire_football_mesure_le_mouvement_et_ecarte_le_handicap(tmp_path):
    entete = "Div,FTHG,FTAG,PSH,PSD,PSA,PSCH,PSCD,PSCA,AvgH,AvgD,AvgA,B365H,B365D,B365A,B365CH,B365CD,B365CA,MaxH,MaxD,MaxA,MaxCH,MaxCD,MaxCA,AHh,AHCh,PAHH,PAHA,PCAHH,PCAHA"
    ligne = "E0,1,0,2.10,3.40,3.60,1.95,3.50,4.00,2.05,3.35,3.55,2.05,3.30,3.50,1.91,3.40,3.90,2.15,3.50,3.75,2.00,3.60,4.10,-0.5,-0.5,2.05,1.85,1.90,2.00"
    (tmp_path / "2425-E0.csv").write_text(entete + "\n" + ligne + "\n", encoding="latin-1")
    t = lire_football(tmp_path)
    assert list(t["marche"]) == ["1N2", "1N2"] and list(t["saison"]) == ["2425", "2425"]      # domicile et extérieur
    assert t["y"][0] > 0 > t["y"][1]                                      # la cote domicile baisse : sa proba monte
    assert t["bet365"][0] > 0                                             # bet365 voyait déjà le domicile plus probable
    assert t["meilleur"][0] == pytest.approx(math.log(2.15 * t["p0"][0]))
    assert math.isnan(t["betfair"][0])                                    # pas de colonne Betfair Exchange dans ce fichier
