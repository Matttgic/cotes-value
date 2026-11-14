"""Cote juste (docs/cote-juste.md) : méthodes de retrait de la marge, mesures et consensus pondéré du script."""
import numpy as np
import pytest

from cotes.marge import proba_justes
from scripts.cote_juste import (METHODES, ajuster, cotes_depuis_puissance, etat, famille, intervalle, log_loss,
                                melange, pente_calibration, poids_de, retirer_marge, variables)


def test_la_puissance_du_script_est_celle_du_site():
    for cotes in ([1.25, 6.0, 11.0], [1.05, 12.0], [1.9, 1.95], [2.4, 3.3, 3.1]):
        assert retirer_marge(np.array([cotes]), "puissance")[0] == pytest.approx(proba_justes(cotes), abs=1e-9)


def test_chaque_methode_rend_des_probabilites_de_somme_un_et_garde_l_ordre():
    cotes = np.array([[1.25, 6.0, 11.0], [2.4, 3.3, 3.1]])
    for methode in METHODES:
        p = retirer_marge(cotes, methode)
        assert p.sum(axis=1) == pytest.approx([1.0, 1.0])
        assert (np.argsort(p, axis=1) == np.argsort(1 / cotes, axis=1)).all()


def test_sur_deux_issues_shin_et_additive_sont_la_meme_methode():
    cotes = np.array([[1.05, 12.0], [1.4, 3.1], [1.9, 1.95]])
    assert retirer_marge(cotes, "shin") == pytest.approx(retirer_marge(cotes, "additive"), abs=1e-9)


def test_le_favori_recoit_de_plus_en_plus_de_la_multiplicative_a_la_puissance():
    favori = {m: retirer_marge(np.array([[1.05, 12.0]]), m)[0, 0] for m in METHODES}
    assert favori["multiplicative"] < favori["additive"] < favori["odds_ratio"] < favori["puissance"]


def test_un_marche_sans_marge_est_seulement_normalise():
    cotes = np.array([[2.1, 2.1]])
    for methode in METHODES:
        assert retirer_marge(cotes, methode)[0] == pytest.approx([0.5, 0.5])


def test_les_cotes_brutes_se_retrouvent_depuis_la_probabilite_puissance_et_la_marge():
    cotes = np.array([[1.25, 6.0, 11.0], [2.4, 3.3, 3.1]])
    p = retirer_marge(cotes, "puissance")
    marge = (1 / cotes).sum(axis=1) - 1
    assert cotes_depuis_puissance(p, marge) == pytest.approx(cotes, rel=1e-6)


def test_la_pente_de_calibration_vaut_un_sur_des_probabilites_justes_et_plus_si_elles_sont_ecrasees():
    rng = np.random.default_rng(7)
    p = rng.dirichlet([2.0, 1.0, 1.0], size=40000)
    gagnant = (rng.random(len(p))[:, None] > p.cumsum(axis=1)).sum(axis=1)
    assert pente_calibration(p, gagnant) == pytest.approx(1.0, abs=0.03)
    ecrasees = np.sqrt(p) / np.sqrt(p).sum(axis=1, keepdims=True)       # favoris sous-estimés : pente 2
    assert pente_calibration(ecrasees, gagnant) == pytest.approx(2.0, abs=0.06)
    assert log_loss(p, gagnant).mean() < log_loss(ecrasees, gagnant).mean()


def test_l_intervalle_par_grappe_est_plus_large_que_par_ligne_quand_les_lignes_se_repetent():
    rng = np.random.default_rng(3)
    valeurs = np.repeat(rng.normal(size=50), 20)
    grappes = np.repeat(np.arange(50), 20)
    _, a, b = intervalle(valeurs, np.random.default_rng(1), 500)
    _, c, d = intervalle(valeurs, np.random.default_rng(1), 500, grappes)
    assert d - c > 2 * (b - a)


def test_le_melange_ignore_les_sources_absentes_et_suit_les_poids():
    p = np.array([[0.50, 0.60, np.nan, np.nan], [0.50, 0.60, 0.40, np.nan]])
    assert melange(p, np.ones((2, 4))) == pytest.approx([0.55, 0.50])
    assert melange(p, np.array([[1.0, 3.0, 1.0, 1.0]] * 2)) == pytest.approx([0.575, 0.54])


def test_l_ajustement_retrouve_la_source_qui_dit_vrai():
    rng = np.random.default_rng(5)
    n = 4000
    vrai = rng.uniform(0.2, 0.8, n)
    p = np.full((n, 4), np.nan)
    p[:, 0] = vrai + rng.normal(0, 0.04, n)          # Pinnacle bruité
    p[:, 1] = vrai + rng.normal(0, 0.01, n)          # autre source précise
    t = {"p": p, "ea": np.full((n, 4), 0.02), "liq": np.full((n, 4), 1000.0), "age": np.zeros((n, 4)),
         "mg": np.full((n, 4), 0.05), "lim": np.full((n, 4), 500.0)}
    actif = ~np.isnan(p)
    theta = ajuster(t, np.ones(n, dtype=bool), actif, vrai, "fixes", tours=1500)
    poids = poids_de(theta, variables(t), actif)
    assert poids[0, 1] > 5 * poids[0, 0]             # variance 16 fois plus faible : poids bien plus grand


def test_etat_rend_la_derniere_ligne_et_rien_apres_un_retrait():
    serie = [(10.0, 2.0, 0.5, None, None, None, None, 0), (20.0, None, None, None, None, None, None, 0),
             (30.0, 1.8, 0.55, None, None, None, None, 0)]
    assert etat(serie, 5.0) is None and etat(serie, 15.0)[2] == 0.5
    assert etat(serie, 25.0) is None and etat(serie, 30.0)[2] == 0.55


def test_les_familles_de_marches():
    assert famille("RESULTAT_1N2") == "1N2" and famille("VAINQUEUR") == "Deux issues"
    assert famille("JEUX_TOTAL_DOM") == "Totaux" and famille("SETS_HANDICAP") == "Handicaps"
    assert famille("JOUEUR:Points") == "Props joueurs" and famille("CORRECT_SCORE") is None
