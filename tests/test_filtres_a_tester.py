"""TRJ, limite Pinnacle, mouvement de Pinnacle et mise Kelly : mesures descriptives, jamais des critères de prise."""
from datetime import datetime, timedelta, timezone

import pytest

from cotes import mouvement
from cotes.comparaison import comparer, taux_retour
from cotes.marches import cle
from cotes.simulation import bilan, bilan_filtres, mise_kelly
from tests.test_controle import ligne


def test_taux_retour_marche_complet_seulement():
    assert taux_retour([{"issue": "PLUS", "cote": 1.9}, {"issue": "MOINS", "cote": 1.9}]) == pytest.approx(.95)
    assert taux_retour([{"issue": "PLUS", "cote": 1.9}]) is None                     # marché incomplet
    assert taux_retour([{"issue": "PLUS", "cote": 1.9}, {"issue": "PLUS", "cote": 1.9}]) is None
    assert taux_retour([{"issue": "PLUS", "cote": 1.9}, {"issue": "MOINS", "cote": 1.0}]) is None
    trois = [{"issue": i, "cote": 3.0} for i in ("DOM", "NUL", "EXT")]
    assert taux_retour(trois) == 1.0
    assert taux_retour([{"issue": i, "cote": 1.5} for i in ("HOME_DRAW", "HOME_AWAY", "DRAW_AWAY")]) is None


def test_comparer_note_trj_et_limite_pinnacle():
    fr = [ligne(cote=2.4, issue="PLUS"), ligne(cote=1.5, issue="MOINS")]
    index = {"Pinnacle": {"m1": {}}}
    for l in fr:
        p = .5 if l["issue"] == "PLUS" else .5
        index["Pinnacle"]["m1"][cle(l)] = {**l, "proba_juste": p, "cote": 2.0, "mise_max": 1500.0,
                                           "marge_pinnacle": .03}
    o = [x for x in comparer(fr, {"Pinnacle": []}, index=index) if x["issue"] == "PLUS"][0]
    assert o["trj_bookmaker"] == pytest.approx(1 / (1 / 2.4 + 1 / 1.5), abs=1e-4)
    assert o["limite_pinnacle"] == 1500.0 and o["marge_pinnacle"] == .03


def test_mouvement_ancre_mesure_apres_dix_minutes_et_se_renouvelle():
    t0 = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)
    ancres = {}
    assert mouvement.mettre_a_jour(ancres, {"a": .50, "b": .40}, t0) == {}
    assert mouvement.mettre_a_jour(ancres, {"a": .55}, t0 + timedelta(minutes=5)) == {}      # trop court
    assert "b" not in ancres                                                                  # ligne disparue oubliée
    m = mouvement.mettre_a_jour(ancres, {"a": .55}, t0 + timedelta(minutes=20))
    assert m["a"] == (.1, 1200)                                                               # p +10 % en 20 min
    mouvement.mettre_a_jour(ancres, {"a": .56}, t0 + timedelta(minutes=61))
    assert ancres["a"][0] == .56                                                              # ancre renouvelée


def test_mouvement_annote_sans_lever_si_chemin_absent(tmp_path):
    assert mouvement.annoter([], {}, None, datetime.now(timezone.utc)) == {"actif": False}
    r = mouvement.annoter([], {}, tmp_path / "x" / "ancres.json.gz", datetime.now(timezone.utc))
    assert r["actif"] and r["ancres"] == 0


def test_mise_kelly_fractionnee_et_plafonnee():
    assert mise_kelly({"cote": 2.0, "ecart": .04}) == 10.0           # 1000 × ¼ × 0,04 / 1
    assert mise_kelly({"cote": 3.0, "ecart": .10}) == 12.5
    assert mise_kelly({"cote": 1.5, "ecart": .20}) == 20.0           # plafond 2 % de 1000 €
    assert mise_kelly({"cote": 2.0, "ecart": None}) == 0.0 and mise_kelly({"cote": 1.0, "ecart": .1}) == 0.0


BASE = {"simulation": "A", "mise": 10, "reference": "Pinnacle", "marche": "VAINQUEUR", "periode": "MATCH",
        "ligne": None, "joueur": None, "cote": 2.0, "ecart": .04, "bookmaker": "PMU", "issue": "DOM",
        "detecte": "2026-10-07T15:00:00+00:00", "debut": "2026-10-07T18:00:00+00:00",
        "cloture_lue": "2026-10-07T17:50:00+00:00"}


def test_bilan_kelly_proportionnel_au_gain():
    gagne = {**BASE, "match_id": "w|1", "statut": "gagne", "gain": 10.0, "clv": .05}
    perdu = {**BASE, "match_id": "w|2", "statut": "perdu", "gain": -10.0, "clv": -.01, "cote": 3.0, "ecart": .10}
    b = bilan([gagne, perdu])["A|Pinnacle"]
    assert b["mises_kelly"] == 22.5                                   # 10 € + 12,5 €
    assert b["gains_kelly"] == pytest.approx(10.0 - 12.5)             # gain réel × mise Kelly / mise fixe
    assert b["roi_kelly"] == round(-2.5 / 22.5, 4)


def test_bilan_filtres_tranches_et_anciens_paris_exclus():
    a = {**BASE, "match_id": "w|1", "statut": "gagne", "gain": 10.0, "clv": .05, "trj_bookmaker": .95,
         "limite_pinnacle": 1500.0, "mouvement_pinnacle": .03}
    b = {**BASE, "match_id": "w|2", "statut": "perdu", "gain": -10.0, "clv": -.02, "trj_bookmaker": .90,
         "limite_pinnacle": 200.0, "mouvement_pinnacle": -.02}
    ancien = {**BASE, "match_id": "w|3", "statut": "gagne", "gain": 10.0, "clv": .05}          # sans mesure
    f = bilan_filtres([a, b, ancien])
    trj = {t["tranche"]: t for t in f["trj"]["tranches"]}
    assert f["trj"]["n_mesures"] == 2
    assert trj["94 – 96 %"]["n"] == 1 and trj["94 – 96 %"]["gains"] == 10.0 and trj["94 – 96 %"]["clv_positifs"] == 1
    assert trj["< 92 %"]["roi"] == -1.0
    lim = {t["tranche"]: t for t in f["limite"]["tranches"]}
    assert lim["1 000 – 2 999 €"]["n"] == 1 and lim["< 300 €"]["n"] == 1
    mou = {t["tranche"]: t for t in f["mouvement"]["tranches"]}
    assert mou["Cote Pinnacle en baisse ≥ 2 %"]["n"] == 1 and mou["Cote Pinnacle en hausse"]["n"] == 1


def test_marge_pinnacle_estimee_retrouve_la_vraie_marge_a_deux_issues():
    from cotes.marge import marge, proba_justes
    from cotes.simulation import marge_pinnacle_estimee
    for cotes in ([1.80, 2.10], [1.45, 3.10], [2.0, 2.0]):
        pj = proba_justes(cotes)[0]
        p = {"reference": "Pinnacle", "marche": "TOTAL", "cote_reference": cotes[0], "cote_juste": round(1 / pj, 3)}
        assert marge_pinnacle_estimee(p) == pytest.approx(marge(cotes), abs=.003)
    assert marge_pinnacle_estimee({"reference": "Pinnacle", "marche": "RESULTAT_1N2", "cote_reference": 2.0,
                                   "cote_juste": 2.1}) is None                                   # trois issues
    assert marge_pinnacle_estimee({"reference": "Polymarket", "marche": "TOTAL", "cote_reference": 2.0,
                                   "cote_juste": 2.1}) is None


def test_bilan_filtres_marge_estimee_sur_ancien_pari():
    ancien = {**BASE, "match_id": "w|9", "marche": "TOTAL", "statut": "gagne", "gain": 10.0, "clv": .05,
              "cote_reference": 1.80, "cote_juste": 1.91}
    f = bilan_filtres([ancien])["marge"]
    assert f["n_mesures"] == 1 and f["n_estimees"] == 1
    assert sum(t["n"] for t in f["tranches"]) == 1
