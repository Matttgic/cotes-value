"""Stratégie de mises (docs/strategie-mises.md) : règle d'exclusion, mise de Kelly et simulations du script."""
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from scripts.strategie_mises import (MISE_FIXE, PLAFOND_OUVERT, PLAFOND_PARI, _mise_fixe, avantage, difference, droite,
                                     ecartes, facteur_incertitude, mise_kelly, parts_du_jour, rejouer, retenu,
                                     resumer_trajectoires, tirer_jour, variance, variance_entre_periodes)

T0 = datetime(2026, 11, 1, 12, tzinfo=timezone.utc)


def pari(i, match="m", selection=None, cote=2.0, mu=0.04, rendement=1.0, heures=0, duree=2):
    return {"id": str(i), "match": match, "selection": selection or (match, i), "cote": cote, "mu": mu, "se": 0.0,
            "rendement": rendement, "detecte": T0 + timedelta(hours=heures), "regle": T0 + timedelta(hours=heures + duree),
            "clv": None, "ecart": 0.05}


def test_la_regle_d_exclusion_ne_lit_que_la_periode_a_et_les_segments_assez_mesures():
    segs = [{"dimension": "Bookmaker", "segment": "X", "A": {"mesures": 60, "clv": -0.01}, "B": {"mesures": 60, "clv": 0.05}},
            {"dimension": "Bookmaker", "segment": "Y", "A": {"mesures": 60, "clv": 0.01}, "B": {"mesures": 60, "clv": -0.05}},
            {"dimension": "Bookmaker", "segment": "Z", "A": {"mesures": 49, "clv": -0.05}, "B": {"mesures": 60, "clv": -0.05}},
            {"dimension": "Tranche de cote", "segment": "plus de 10", "A": {"mesures": 60, "clv": -0.05}, "B": {"mesures": 0, "clv": None}}]
    assert ecartes(segs) == [("Bookmaker", "X")]
    x = {"cote": 2.0, "segments": {"Bookmaker": "X"}}
    assert not retenu(x, [("Bookmaker", "X")], 5.0)
    assert retenu({"cote": 2.0, "segments": {"Bookmaker": "Y"}}, [("Bookmaker", "X")], 5.0)
    assert not retenu({"cote": 5.5, "segments": {"Bookmaker": "Y"}}, [("Bookmaker", "X")], 5.0)


def test_facteur_d_incertitude():
    assert facteur_incertitude(0.04, 0.0) == 1.0
    assert facteur_incertitude(0.04, 0.04) == pytest.approx(0.5)
    assert facteur_incertitude(0.01, 0.03) == pytest.approx(0.1)
    assert facteur_incertitude(0.0, 0.01) == 0.0 and facteur_incertitude(-0.02, 0.0) == 0.0


def test_avantage_borne_l_ecart_et_ajoute_l_incertitude_entre_periodes():
    modele = {"a": -0.02, "b": 1.0, "var_a": 0.0001, "var_b": 0.0, "cov_ab": 0.0, "var_periode": 0.0003}
    mu, se = avantage(modele, 0.05)
    assert mu == pytest.approx(0.03) and se == pytest.approx(0.02)
    assert avantage(modele, 0.30)[0] == pytest.approx(0.08)                 # écart compté jusqu'à 10 %
    assert variance_entre_periodes(0.03, 0.01, 0.01) == pytest.approx((0.0009 - 0.0002) / 2)
    assert variance_entre_periodes(0.005, 0.01, 0.01) == 0.0


def test_mise_de_kelly_seule():
    assert mise_kelly(0.04, 0.0, 2.0, 0.25, []) == pytest.approx(0.01)       # Kelly entier 4 %, au quart
    assert mise_kelly(0.04, 0.04, 2.0, 0.25, []) == pytest.approx(0.005)     # avantage incertain : moitié moins
    assert mise_kelly(0.04, 0.0, 5.0, 0.25, []) == pytest.approx(0.0025)     # cote plus haute, mise plus petite
    assert mise_kelly(-0.01, 0.0, 2.0, 0.25, []) == 0.0
    assert mise_kelly(0.20, 0.0, 1.5, 1.0, []) == PLAFOND_PARI
    assert mise_kelly(0.04, 0.0, 2.0, 0.25, [], expose=PLAFOND_OUVERT - 0.004) == pytest.approx(0.004)
    assert mise_kelly(0.04, 0.0, 2.0, 0.25, [], expose=PLAFOND_OUVERT) == 0.0


def test_mise_de_kelly_et_paris_du_meme_match():
    v = variance(0.04, 2.0)
    seule = mise_kelly(0.04, 0.0, 2.0, 0.25, [])
    assert mise_kelly(0.04, 0.0, 2.0, 0.25, [(seule, v, 1.0)]) == 0.0        # même sélection déjà jouée : rien de plus
    assert mise_kelly(0.04, 0.0, 2.0, 0.25, [(seule, v, 0.0)]) == pytest.approx(seule)
    assert mise_kelly(0.04, 0.0, 2.0, 0.25, [(seule, v, 0.3)]) == pytest.approx(0.7 * seule)
    assert mise_kelly(0.04, 0.0, 2.0, 0.25, [(seule / 2, v, 1.0)]) == pytest.approx(seule / 2)   # complète la mise
    jour = [pari(1, selection="s"), pari(2, selection="s"), pari(3), pari(4, match="autre")]
    parts = parts_du_jour(jour, 0.25, 0.3)
    assert parts.tolist() == pytest.approx([seule, 0.0, 0.7 * seule, seule])


def test_rejeu_a_mise_fixe_et_en_kelly():
    paris = [pari(1, rendement=1.0), pari(2, match="b", rendement=-1.0, heures=3), pari(3, match="c", rendement=-1.0, heures=6)]
    fixe = rejouer(paris, None, 0.3, bankroll=100.0)
    assert fixe["paris"] == 3 and fixe["total_mises"] == 3 * MISE_FIXE and fixe["gain"] == -MISE_FIXE
    assert fixe["perte_max_eur"] == 2 * MISE_FIXE and fixe["perte_max"] == pytest.approx(20 / 110) and fixe["creux"] == 90
    kelly = rejouer(paris, 0.25, 0.3, bankroll=1000.0)
    assert kelly["mises"].tolist() == pytest.approx([10.0, 10.1, 9.999])     # 1 % de la bankroll déjà réglée
    assert kelly["finale"] == pytest.approx(1000 + 10 - 10.1 - 9.999)
    ensemble = rejouer([pari(1), pari(2, heures=1)], 0.25, 0.3, bankroll=1000.0)   # même match, premier pari encore ouvert
    assert ensemble["mises"].tolist() == pytest.approx([10.0, 7.0])


def test_tirages_d_un_jour_probabilites_et_correlation():
    jour = [pari(1, selection="s", cote=2.0), pari(2, selection="s", cote=2.0), pari(3, cote=2.0), pari(4, match="autre", cote=4.0)]
    r = tirer_jour(jour, np.array([0.0, 0.0, 0.0, 0.2]), 0.3, 40000, np.random.default_rng(1))
    assert (r[:, 0] == r[:, 1]).all()                                        # même sélection : même résultat
    assert (r[:, 0] > 0).mean() == pytest.approx(0.5, abs=0.01)
    assert (r[:, 3] > 0).mean() == pytest.approx(0.3, abs=0.01)               # (1 + 0,2) / 4
    assert np.corrcoef(r[:, 0], r[:, 2])[0, 1] == pytest.approx(0.3, abs=0.02)
    assert abs(np.corrcoef(r[:, 0], r[:, 3])[0, 1]) < 0.02                   # autre match : indépendant


def test_mise_fixe_arretee_quand_la_bankroll_ne_couvre_plus_une_mise():
    gains = np.array([[-95.0, -30.0, 500.0], [10.0, -20.0, 30.0]])
    w, depart, roi = _mise_fixe(gains, np.full((2, 3), 100.0), 100.0)
    assert w.tolist() == [[5.0, 5.0, 5.0], [110.0, 90.0, 120.0]]
    assert roi.tolist() == pytest.approx([375 / 300, 20 / 300])
    resume = resumer_trajectoires(w, depart, roi)
    assert resume["ruine"] == 0.5 and resume["perd_moitie"] == 0.5 and resume["finit_en_perte"] == 0.5
    assert resume["perte_max_eur_95"] == pytest.approx(95, abs=4)


def test_droite_et_difference_par_match():
    assert droite(np.array([0.0, 1.0, 2.0]), np.array([1.0, 3.0, 5.0])) == pytest.approx((1.0, 2.0))
    a = [{"match": i, "clv": 0.05} for i in range(40)]
    b = [{"match": i, "clv": 0.01 if i % 2 else None} for i in range(40)]
    d = difference(a, b, "clv", 500, np.random.default_rng(1))
    assert d["valeur"] == pytest.approx(0.04) and d["ic"][0] == pytest.approx(0.04) and d["ic"][1] == pytest.approx(0.04)
