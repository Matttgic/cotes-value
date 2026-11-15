"""Modèle de prix (docs/modele-prix.md) : Elo, Poisson, mélange avec la référence, sans regarder l'avenir."""
import numpy as np
import pytest

from etudes.modele_prix import (COTES_1N2, COTES_HANDICAP, COTES_TOTAL, ELO, POISSON, ajuster_melange, elo,
                                 gagnants, grille_scores, holm, marches_poisson, melange, poisson, proba_elo)


def _matchs(n_equipes: int = 8, tours: int = 12, graine: int = 1) -> dict[str, np.ndarray]:
    """Petit championnat : l'équipe 0 est la plus forte, la dernière la plus faible."""
    rng = np.random.default_rng(graine)
    lignes = []
    jour = 735000
    for _ in range(tours):
        for d in range(n_equipes):
            for e in range(n_equipes):
                if d != e:
                    jour += 1
                    lignes.append((jour, d, e, rng.poisson(1.6 * 1.25 ** ((e - d) / 2)), rng.poisson(1.2 * 1.25 ** ((d - e) / 2))))
    n = len(lignes)
    t = {"jour": np.array([x[0] for x in lignes]), "niveau": np.zeros(n, dtype=np.int64),
         "groupe": np.array(["X"] * n), "division": np.array(["X1"] * n), "saison": np.array(["s"] * n),
         "dom": np.array([f"e{x[1]}" for x in lignes]), "ext": np.array([f"e{x[2]}" for x in lignes]),
         "bd": np.array([x[3] for x in lignes], dtype=float), "be": np.array([x[4] for x in lignes], dtype=float)}
    t["td"], t["te"] = t["bd"] * 3 + 1, t["be"] * 3 + 1
    for nom in COTES_1N2:
        t["1n2_" + nom] = np.full((n, 3), np.nan)
    for nom in COTES_TOTAL:
        t["tot_" + nom] = np.full((n, 2), np.nan)
    for nom in COTES_HANDICAP:
        t["han_" + nom] = np.full((n, 3), np.nan)
    return t


def test_la_grille_des_scores_somme_a_un_et_la_correction_ajoute_des_nuls():
    lam_d, lam_e = np.array([1.6, 0.8]), np.array([1.1, 2.3])
    sans, avec = grille_scores(lam_d, lam_e, 0.0), grille_scores(lam_d, lam_e, -0.06)
    assert sans.sum(axis=(1, 2)) == pytest.approx([1.0, 1.0])
    assert avec.sum(axis=(1, 2)) == pytest.approx([1.0, 1.0])
    assert (np.trace(avec, axis1=1, axis2=2) > np.trace(sans, axis1=1, axis2=2)).all()


def test_les_marches_de_poisson_sont_coherents():
    lam_d, lam_e = np.array([1.8, 1.0, np.nan]), np.array([0.9, 1.0, 1.0])
    lignes = {"pin_c": np.array([-0.5, 0.0, -0.5]), "pin_o": np.array([-0.25, 0.5, 0.0])}
    m = marches_poisson(lam_d, lam_e, -0.06, lignes)
    assert m["1n2"][:2].sum(axis=1) == pytest.approx([1.0, 1.0])
    assert m["1n2"][0, 0] > m["1n2"][0, 2] and m["1n2"][1, 0] == pytest.approx(m["1n2"][1, 2])
    assert np.isnan(m["1n2"][2]).all()
    assert m["han_pin_c"][0, 0] == pytest.approx(m["1n2"][0, 0])          # −0,5 : gagner le match
    assert m["han_pin_c"][1, 0] == pytest.approx(0.5)                     # ligne 0 à forces égales, hors nul
    assert np.isnan(m["han_pin_o"][0]).all()                              # quart de but : écarté
    assert m["han_pin_o"][1, 0] == pytest.approx(m["1n2"][1, 0] + m["1n2"][1, 1])


def test_le_logit_ordonne_rend_des_probabilites():
    p = proba_elo(np.array([-3.0, 0.0, 3.0]), 0.6, 0.6)
    assert p.sum(axis=1) == pytest.approx([1.0, 1.0, 1.0])
    assert p[0, 0] < p[1, 0] < p[2, 0] and p[1, 0] == pytest.approx(p[1, 2])


def test_elo_et_poisson_ne_regardent_pas_l_avenir():
    t = _matchs()
    coupe = len(t["jour"]) // 2
    autre = {k: v.copy() for k, v in t.items()}
    autre["bd"][coupe:], autre["be"][coupe:] = 7.0, 0.0
    assert elo(t, ELO)["x"][:coupe + 1] == pytest.approx(elo(autre, ELO)["x"][:coupe + 1])
    for cible in ("buts", "tirs"):
        a, b = poisson(t, POISSON, cible, processus=1), poisson(autre, POISSON, cible, processus=1)
        assert a["lam_d"][:coupe + 1] == pytest.approx(b["lam_d"][:coupe + 1], nan_ok=True)
        assert not np.isnan(a["lam_d"][coupe])


def test_les_modeles_retrouvent_l_ordre_des_equipes():
    t = _matchs()
    x = elo(t, ELO)["x"]
    po = poisson(t, POISSON, processus=1)
    fort_recoit = (t["dom"] == "e0") & (t["ext"] == "e7")
    faible_recoit = (t["dom"] == "e7") & (t["ext"] == "e0")
    assert x[fort_recoit][-1] > 0 > x[faible_recoit][-1]
    assert po["lam_d"][fort_recoit][-1] > po["lam_e"][fort_recoit][-1]
    assert po["lam_d"][faible_recoit][-1] < po["lam_e"][faible_recoit][-1]
    assert gagnants(t)["1n2"].tolist()[:1] == [0 if t["bd"][0] > t["be"][0] else 1 if t["bd"][0] == t["be"][0] else 2]


def test_le_melange_retrouve_les_exposants_qui_ont_fait_les_resultats():
    rng = np.random.default_rng(3)
    ref = rng.dirichlet([3, 2, 2], size=40000)
    mod = rng.dirichlet([3, 2, 2], size=40000)
    vrai = melange(ref, mod, 1.0, 0.3)
    gagnant = (rng.random(len(vrai))[:, None] > vrai.cumsum(axis=1)).sum(axis=1)
    theta, et = ajuster_melange(ref, mod, gagnant)
    assert theta == pytest.approx([1.0, 0.3], abs=4 * et.max())
    seul, et_seul = ajuster_melange(ref, mod, gagnant, (True, False))
    assert seul[1] == 0.0 and et_seul[1] == 0.0


def test_holm_corrige_dans_l_ordre():
    assert holm([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])
