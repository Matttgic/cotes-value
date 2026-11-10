"""Avis d'analyste et classement d'accueil : métriques, verdicts, ordre des notes."""
import json
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from cotes.analyste import (CHANCE, FIABLE, PROMETTEUR, SEUILS, TROP_TOT, VERDICTS,
                            analyser_serie, avis_des_paris, betainc, dependance_grosses_cotes,
                            moities, proba_hasard, pvalue_clv, pvalue_student, r_carre, ratio_sharpe,
                            repli, trier_par_note)

RACINE = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")


def _ligne(identifiant, nom, note, regles):
    stats = {"regles": regles}
    if note is not None:
        stats["note"] = {"total": note}
    return {"id": identifiant, "nom": nom, "stats": stats}


def test_seuils_prudents_documentes():
    assert SEUILS["min_paris_regles"] == 100
    assert SEUILS["proba_chance_fiable"] == 0.05
    assert SEUILS["proba_chance_yoyo"] == 0.20
    assert SEUILS["min_clv"] >= 20
    assert SEUILS["clv_moyenne_min"] == 0
    assert SEUILS["part_cotes_gagnantes"] == 0.05
    assert SEUILS["nb_gros_gains"] == 3
    assert SEUILS["graine"] == 20261110
    assert set(VERDICTS) == {FIABLE, PROMETTEUR, CHANCE, TROP_TOT}


def test_beta_et_student_sur_des_seuils_connus():
    assert betainc(1, 1, 0.5) == pytest.approx(0.5, abs=1e-9)
    assert betainc(2, 2, 0.5) == pytest.approx(0.5, abs=1e-9)   # 3x² − 2x³ à x = 0,5
    assert betainc(1, 1, 0) == 0 and betainc(1, 1, 1) == 1
    assert pvalue_student(0, 10) == pytest.approx(0.5, abs=1e-9)
    assert pvalue_student(2.015, 5) == pytest.approx(0.05, abs=0.002)
    assert pvalue_student(1.812, 10) == pytest.approx(0.05, abs=0.002)
    assert pvalue_student(1.645, 1000) == pytest.approx(0.05, abs=0.005)
    assert pvalue_student(-2.015, 5) == pytest.approx(0.95, abs=0.002)


def test_t_test_clv_constante_symetrique_et_courte():
    assert pvalue_clv([0.02] * 30) == 0.0
    assert pvalue_clv([0.0] * 8) == 1.0
    assert pvalue_clv([0.01, -0.01, 0.01, -0.01]) == pytest.approx(0.5, abs=1e-6)
    assert pvalue_clv([0.03]) is None
    # Moyenne positive, écart-type non nul : la p-value reste petite.
    assert pvalue_clv([0.02, 0.03, 0.01, 0.04, 0.02, 0.025]) < 0.01


def test_bootstrap_reproductible_bornes_et_cas_extremes():
    assert proba_hasard([], 100, SEUILS["graine"]) is None
    assert proba_hasard([1.0] * 20, 50, 1) == 0.0
    assert proba_hasard([-1.0] * 20, 50, 1) == 1.0
    melange = [10.0, -10.0] * 40
    a = proba_hasard(melange, 400, 7)
    b = proba_hasard(melange, 400, 7)
    assert a == b
    assert 0.2 < a < 0.8


def test_repli_maximal_recuperation_et_jours():
    assert repli([]) == {"max": 0.0, "recupere": True, "paris": 0, "jours": 0.0}
    assert repli([1, 1, 1])["max"] == 0.0
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    instants = [t0 + timedelta(days=i) for i in range(4)]
    baisse = repli([10, -6, 3, 4], instants)
    assert baisse["max"] == 6
    assert baisse["recupere"] is True and baisse["paris"] == 3 and baisse["jours"] == 3
    ouvert = repli([10, -30], instants[:2])
    assert ouvert["max"] == 30 and ouvert["recupere"] is False
    assert ouvert["paris"] is None and ouvert["jours"] is None
    # Sommet au départ (0) : les deux paris ramènent un plus haut, sans date de sommet.
    depart = repli([-5, 10], instants[:2])
    assert depart["max"] == 5 and depart["recupere"] is True and depart["paris"] == 2
    assert depart["jours"] is None


def test_regularite_r2_et_ratio():
    assert r_carre([1]) is None
    assert r_carre([1, 1, 1, 1]) == pytest.approx(1.0)
    assert r_carre([0, 0, 0]) == 1.0
    yoyo = [5] * 40 + [-5] * 40
    assert r_carre(yoyo) < 0.5
    assert ratio_sharpe([1]) is None
    assert ratio_sharpe([2, 2, 2]) is None
    assert ratio_sharpe([1, -1, 1, -1]) == pytest.approx(0.0)
    assert ratio_sharpe([2, 2, 2, -1]) > 0


def test_moities_meme_signe():
    mises = [10.0] * 8
    stable = moities([1, 1, 1, 1, 2, 2, 2, 2], mises)
    assert stable["roi_premiere"] > 0 and stable["roi_seconde"] > 0 and stable["memes_signe"] is True
    oppose = moities([1, 1, 1, 1, -2, -2, -2, -2], mises)
    assert oppose["roi_premiere"] > 0 > oppose["roi_seconde"] and oppose["memes_signe"] is False
    assert moities([1], [10])["memes_signe"] is None


def test_dependance_aux_grosses_cotes_et_aux_gros_gains():
    # Vingt petites pertes et un longshot : sans lui, le ROI s'effondre.
    gains = [-10.0] * 20 + [400.0]
    mises = [10.0] * 21
    cotes = [1.5] * 20 + [41.0]
    dep = dependance_grosses_cotes(gains, mises, cotes, 0.05, 3)
    assert dep["depend"] is True
    assert dep["roi_sans_cotes"] < 0 and dep["roi_sans_gains"] < 0
    # Gains réguliers, cotes semblables : retirer le haut ne change pas le signe.
    plat = dependance_grosses_cotes([1.0] * 40, [10.0] * 40, [1.8] * 40, 0.05, 3)
    assert plat["depend"] is False
    assert plat["roi_sans_cotes"] > 0 and plat["roi_sans_gains"] > 0
    assert plat["cotes_retirees"] == 2 and plat["gains_retires"] == 3   # 5 % de 40, au moins 1


def _serie(gains, cote=1.8, clv=0.02, mise=10.0):
    n = len(gains)
    return analyser_serie(gains, [mise] * n, [cote] * n, [clv] * n)


def test_verdict_gagnant_regulier():
    avis = _serie([1.0] * 120)
    assert avis["verdict"] == FIABLE
    assert avis["details"]["proba_chance"] < SEUILS["proba_chance_fiable"]
    assert avis["details"]["r2"] == pytest.approx(1.0, abs=1e-6)
    assert avis["details"]["memes_signe"] is True
    assert avis["details"]["depend_grosses_cotes"] is False
    assert avis["details"]["clv_moyenne"] > 0
    assert 2 <= len(avis["raisons"]) <= 3


def test_verdict_longshot_chanceux():
    # 119 pertes et une cote très longue : le profit tient à ce seul pari.
    gains = [-10.0] * 119 + [1490.0]
    cotes = [1.9] * 119 + [150.0]
    avis = analyser_serie(gains, [10.0] * 120, cotes, [0.01] * 120)
    assert avis["verdict"] == CHANCE
    assert avis["details"]["depend_grosses_cotes"] is True
    assert avis["details"]["proba_chance"] >= SEUILS["proba_chance_yoyo"]
    assert avis["details"]["roi_sans_gains"] < 0
    assert any("cotes" in phrase or "gains" in phrase for phrase in avis["raisons"])


def test_verdict_yoyo():
    gains = [10.0] * 60 + [-8.0] * 60
    avis = _serie(gains, cote=2.0, clv=0.01)
    assert avis["verdict"] == CHANCE
    assert avis["details"]["roi_premiere"] > 0 > avis["details"]["roi_seconde"]
    assert avis["details"]["memes_signe"] is False
    assert any("yo-yo" in phrase for phrase in avis["raisons"])


def test_verdict_echantillon_trop_court_meme_si_la_courbe_est_belle():
    avis = _serie([1.0] * 12)
    assert avis["verdict"] == TROP_TOT
    assert avis["details"]["paris_regles"] == 12
    assert avis["details"]["proba_chance"] == 0.0          # le gain est net, le suivi ne l'est pas
    assert any("100" in phrase for phrase in avis["raisons"])
    assert 2 <= len(avis["raisons"]) <= 3


def test_verdict_prometteur_quand_le_hasard_n_est_pas_ecarte():
    # 110 gains de +10 et 90 pertes de −10, les deux moitiés restent gagnantes.
    gains = [10.0] * 56 + [-10.0] * 44 + [10.0] * 54 + [-10.0] * 46
    avis = _serie(gains, cote=2.0, clv=0.01)
    d = avis["details"]
    assert d["paris_regles"] == 200
    assert d["roi_premiere"] > 0 and d["roi_seconde"] > 0
    assert d["depend_grosses_cotes"] is False
    assert d["clv_moyenne"] > 0
    assert SEUILS["proba_chance_fiable"] <= d["proba_chance"] < SEUILS["proba_chance_yoyo"]
    assert avis["verdict"] == PROMETTEUR
    assert avis["verdict"] in VERDICTS
    assert 2 <= len(avis["raisons"]) <= 3


def test_perte_longue_nest_pas_fiable():
    avis = _serie([-1.0] * 120, clv=-0.01)
    assert avis["verdict"] == CHANCE
    assert avis["details"]["gain"] < 0
    assert avis["details"]["proba_chance"] == 1.0


def test_avis_des_paris_suit_l_ordre_de_reglement_et_la_fenetre_de_clv():
    def pari(identifiant, regle, gain_statut, clv=0.02, cloture="2026-10-16T17:50:00Z"):
        return {"id": identifiant, "statut": gain_statut, "cote": 2.0, "mise": 10,
                "detecte": "2026-10-16T12:00:00Z", "debut": "2026-10-16T18:00:00Z",
                "regle_le": regle, "clv": clv, "cloture_lue": cloture}
    rows = [
        pari("tard", "2026-10-16T21:00:00Z", "perdu"),
        pari("tot", "2026-10-16T19:00:00Z", "gagne"),
        pari("hors", "2026-10-16T20:00:00Z", "gagne", clv=0.5, cloture="2026-10-16T12:00:00Z"),
        {"id": "attente", "statut": "en_cours", "cote": 2, "mise": 10,
         "detecte": "2026-10-16T12:00:00Z", "gain": None},
    ]
    avis = avis_des_paris(rows, "2026-10-17T00:00:00Z")
    assert avis["verdict"] == TROP_TOT
    assert avis["details"]["paris_regles"] == 3
    # Gagné puis gagné puis perdu : le repli n'existe qu'à la fin, donc pas de retour.
    assert avis["details"]["gain"] == pytest.approx(10.0)          # +10, +10, −10
    assert avis["details"]["clv_n"] == 2                            # la CLV lue trop tôt est ignorée
    assert avis["details"]["drawdown_max"] == pytest.approx(10.0)


def test_tri_par_note_sans_note_en_dernier_et_departage_stable():
    lignes = [
        _ligne("z", "Zed", None, 5),
        _ligne("c", "Charlie", 80, 9),
        _ligne("b", "Bravo", 80, 3),
        _ligne("a", "Alpha", 40, 10),
        _ligne("d", "delta", 80, 9),
        _ligne("e", "Echo", None, 100),
        _ligne("zero", "Zero", 0, 1),
        _ligne("m1", "Meme", 50, 4),
        _ligne("m2", "Meme", 50, 4),
    ]
    assert [l["id"] for l in trier_par_note(lignes)] == [
        "c", "d", "b", "m1", "m2", "a", "zero", "e", "z"]
    # Une note à 0 n'est pas une absence de note : elle passe avant un suivi plus long sans note.
    assert [l["id"] for l in trier_par_note(lignes)].index("zero") < [l["id"] for l in trier_par_note(lignes)].index("e")


@pytest.mark.skipif(not NODE, reason="Node absent")
def test_tri_javascript_identique_au_python():
    lignes = [
        _ligne("z", "Zed", None, 5),
        _ligne("c", "Charlie", 80, 9),
        _ligne("b", "Bravo", 80, 3),
        _ligne("a", "Alpha", 40, 10),
        _ligne("d", "delta", 80, 9),
        _ligne("e", "Echo", None, 100),
        _ligne("zero", "Zero", 0, 1),
        _ligne("m1", "Meme", 50, 4),
        _ligne("m2", "Meme", 50, 4),
    ]
    script = (RACINE / "web/visuels.js").read_text(encoding="utf-8") + (
        "\nconst rows = " + json.dumps(lignes) + ";\n"
        "console.log(JSON.stringify(classerParNote(rows).map(r => r.id)));\n")
    rendu = subprocess.run([NODE, "-"], input=script, text=True, capture_output=True, check=False)
    assert rendu.returncode == 0, rendu.stderr
    assert json.loads(rendu.stdout) == [l["id"] for l in trier_par_note(lignes)]
    accueil = (RACINE / "web/accueil.js").read_text(encoding="utf-8")
    assert "classerParNote" in accueil and "classerParValeur" not in accueil


def test_construire_attache_l_avis_sans_rien_selectionner(tmp_path):
    """Le site publie l'avis des bases à la construction ; la sélection des règles n'est pas relue ici."""
    import re
    import sys
    sys.path.insert(0, str(RACINE / "scripts"))
    import site_web

    pari = {"id": "p1", "simulation": "D", "match_id": "m1", "reference": "Pinnacle", "bookmaker": "Winamax",
            "sport": "football", "marche": "TOTAL", "periode": "MATCH", "ligne": 2.5, "issue": "PLUS",
            "detecte": "2026-10-15T12:00:00Z", "debut": "2026-10-15T18:00:00Z",
            "cloture_lue": "2026-10-15T17:40:00Z", "regle_le": "2026-10-15T20:00:00Z",
            "statut": "gagne", "cote": 1.8, "mise": 10, "gain": 8, "clv": 0.02}
    (tmp_path / "paris.json").write_text(json.dumps([pari]), encoding="utf-8")
    html = site_web.construire(tmp_path, tmp_path / "site").read_text(encoding="utf-8")
    data = json.loads(re.search(r"const D = (\{.*?\});\n", html, re.S).group(1))
    base = data["laboratoire"]["bases_futur"]["Pinnacle"]
    assert base["avis"]["verdict"] == TROP_TOT
    assert base["avis"]["details"]["paris_regles"] == 1
    assert data["laboratoire"]["analyste"]["seuils"]["min_paris_regles"] == 100
    assert "Avis d'analyste" in html
