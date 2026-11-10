"""Avis d'analyste et classement d'accueil : métriques, verdicts, ordre des notes."""
import json
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from cotes.analyste import (CHANCE, FIABLE, PROMETTEUR, SEUILS, TROP_TOT, VERDICTS,
                            analyser_serie, annoter_avis, avis_des_paris, benjamini_hochberg, betainc,
                            clv_sans_hautes_cotes, moities, moities_clv, proba_hasard, proba_hasard_matchs,
                            pvalue_clv, pvalue_clv_matchs, pvalue_student, r_carre, ratio_sharpe, repli,
                            trier_par_note)

RACINE = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")


def _ligne(identifiant, nom, note, regles):
    stats = {"regles": regles}
    if note is not None:
        stats["note"] = {"total": note}
    return {"id": identifiant, "nom": nom, "stats": stats}


def test_seuils_prudents_documentes():
    assert SEUILS["min_paris_regles"] == 100
    assert SEUILS["proba_chance_fiable"] == 0.20
    assert SEUILS["min_clv"] == 100
    assert SEUILS["q_bh_fiable"] == 0.05
    assert SEUILS["clv_moyenne_min"] == 0
    assert SEUILS["part_cotes"] == 0.05
    assert SEUILS["tirages_bootstrap"] == 10000
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


def test_moities_de_clv():
    oppose = moities_clv([0.02, 0.01, -0.03, -0.01])
    assert oppose["clv_premiere"] > 0 > oppose["clv_seconde"] and oppose["memes_signe"] is False
    assert moities_clv([0.01])["memes_signe"] is None


def test_moities_meme_signe():
    mises = [10.0] * 8
    stable = moities([1, 1, 1, 1, 2, 2, 2, 2], mises)
    assert stable["roi_premiere"] > 0 and stable["roi_seconde"] > 0 and stable["memes_signe"] is True
    oppose = moities([1, 1, 1, 1, -2, -2, -2, -2], mises)
    assert oppose["roi_premiere"] > 0 > oppose["roi_seconde"] and oppose["memes_signe"] is False
    assert moities([1], [10])["memes_signe"] is None


def test_clv_sans_les_cotes_les_plus_hautes_gagnantes_ou_perdantes():
    # La CLV positive ne tient qu'aux paris les plus chers, qu'ils soient gagnés ou perdus.
    clvs = [-0.02] * 19 + [0.5]
    cotes = [1.5] * 19 + [30.0]
    dep = clv_sans_hautes_cotes(cotes, clvs, 0.05)
    assert dep["cotes_retirees"] == 1
    assert dep["clv_sans_cotes"] < 0 and dep["depend"] is True
    # Une cote haute perdante compte aussi : la retirer peut faire baisser la CLV.
    plat = clv_sans_hautes_cotes([1.8] * 40, [0.01] * 40, 0.05)
    assert plat["depend"] is False and plat["clv_sans_cotes"] > 0
    assert plat["cotes_retirees"] == 2


def test_t_test_groupe_par_match_et_bootstrap_de_grappes():
    # Deux paris du même match ne font pas deux essais : la p-value groupée est plus haute.
    clvs = [0.1, 0.1, -0.05, -0.05]
    p_matchs, moyenne, n, g = pvalue_clv_matchs(clvs, ["a", "a", "b", "b"])
    p_paris, _, _, g_paris = pvalue_clv_matchs(clvs, ["a", "b", "c", "d"])
    assert n == 4 and g == 2 and g_paris == 4
    assert moyenne == pytest.approx(0.025)
    assert p_matchs > p_paris
    # Un match gagnant et beaucoup de matchs perdants : tirer des paris au hasard sous-estime le risque
    # de rater le match gagnant si ses paris sont liés. Ici un seul pari par match, les deux coïncident.
    gains = [-10.0] * 30 + [400.0]
    assert proba_hasard_matchs(gains, list(range(31)), 200, 3) == proba_hasard(gains, 200, 3)
    # Grouper les deux gros gains dans un seul match change la probabilité (graine fixe).
    gains_bloc = [-10.0] * 20 + [200.0, 200.0]
    matchs = list(range(20)) + ["long", "long"]
    assert proba_hasard_matchs(gains_bloc, matchs, 500, 1) != proba_hasard(gains_bloc, 500, 1)


def test_benjamini_hochberg_et_famille_de_strategies():
    assert benjamini_hochberg([]) == []
    # p triées 0,01 ; 0,03 ; 0,04. q brutes 0,03 ; 0,045 ; 0,04, puis monotonie : 0,03 ; 0,04 ; 0,04.
    assert benjamini_hochberg([0.04, 0.01, 0.03]) == pytest.approx([0.04, 0.03, 0.04])
    # Une p de 0,04 seule passerait 5 %. Au milieu de 19 tests à 0,5, la monotonie la ramène à 0,5.
    p = [0.04] + [0.5] * 19
    q = benjamini_hochberg(p)
    assert q[0] == pytest.approx(0.5)
    assert q[0] >= SEUILS["q_bh_fiable"]
    assert all(valeur >= brute - 1e-12 for valeur, brute in zip(q, p))


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
    # 119 pertes et une cote très longue. La CLV moyenne n'est positive que grâce à cette cote.
    gains = [-10.0] * 119 + [1490.0]
    cotes = [1.9] * 119 + [150.0]
    clvs = [-0.01] * 119 + [2.0]
    avis = analyser_serie(gains, [10.0] * 120, cotes, clvs)
    assert avis["verdict"] == CHANCE
    assert avis["details"]["depend_grosses_cotes"] is True
    assert avis["details"]["clv_sans_cotes"] < 0
    assert any("cotes" in phrase for phrase in avis["raisons"])


def test_verdict_clv_non_positive_est_chance():
    gains = [10.0] * 60 + [-8.0] * 60
    clvs = [0.02] * 60 + [-0.02] * 60
    avis = analyser_serie(gains, [10.0] * 120, [2.0] * 120, clvs)
    assert avis["details"]["clv_moyenne"] <= 0
    assert avis["verdict"] == CHANCE
    assert any("clôture" in phrase for phrase in avis["raisons"])


def test_moities_opposees_ne_suffisent_plus_a_dire_chance():
    # CLV positive au total et sans les longues cotes, profit positif, mais les deux moitiés
    # n'ont pas le même signe : ce n'est plus « Chance », seulement « Prometteur ».
    clvs = [0.04] * 60 + [-0.01] * 60
    avis = analyser_serie([1.0] * 120, [10.0] * 120, [1.8] * 120, clvs)
    d = avis["details"]
    assert d["clv_premiere"] > 0 > d["clv_seconde"]
    assert d["clv_moyenne"] > 0 and d["clv_sans_cotes"] > 0 and d["gain"] > 0
    assert avis["verdict"] == PROMETTEUR


def test_perte_et_clv_non_significative_est_chance():
    # Gain négatif et p brute de CLV au-dessus de 5 % : « Chance », même si la moyenne est > 0.
    clvs = ([0.05] * 52 + [-0.05] * 48) * 2
    cotes = [1.5 + (i % 10) * 0.1 for i in range(200)]
    avis = analyser_serie([-1.0] * 200, [10.0] * 200, cotes, clvs)
    assert avis["details"]["clv_sans_cotes"] > 0
    assert avis["details"]["gain"] < 0
    assert avis["details"]["clv_moyenne"] > 0
    assert avis["details"]["pvalue_clv"] >= SEUILS["q_bh_fiable"]
    assert avis["verdict"] == CHANCE


def test_moins_de_cent_clv_est_trop_tot_meme_avec_assez_de_paris():
    # 120 paris réglés, mais seulement 99 clôtures : même règle que POL-1.5-3-e2-h36.
    clvs = [0.02] * 99 + [None] * 21
    avis = analyser_serie([1.0] * 120, [10.0] * 120, [1.8] * 120, clvs)
    assert avis["details"]["paris_regles"] == 120 and avis["details"]["clv_n"] == 99
    assert avis["verdict"] == TROP_TOT
    assert any("CLV" in phrase for phrase in avis["raisons"])


def test_la_famille_bh_garde_une_strategie_courte_en_clv():
    # ≥100 paris : elle entre dans la correction, même si le verdict reste « Trop tôt ».
    courte = [pari_regle(i, clv=0.02 if i < 99 else None) for i in range(120)]
    solide = [pari_regle(1000 + i, clv=0.03) for i in range(120)]
    courte_avis, solide_avis = annoter_avis([courte, solide], "2026-11-01T00:00:00Z")
    assert courte_avis["verdict"] == TROP_TOT
    assert courte_avis["details"]["q_bh"] is not None
    assert solide_avis["details"]["q_bh"] is not None
    assert solide_avis["verdict"] == FIABLE


def pari_regle(i, clv=0.02):
    # Règlement le lendemain de la détection, une minute par pari, pour rester dans la fenêtre de CLV.
    return {"id": f"p{i}", "statut": "gagne", "cote": 1.5, "mise": 10, "clv": clv,
            "detecte": "2026-10-16T12:00:00Z", "debut": "2026-10-16T18:00:00Z",
            "cloture_lue": "2026-10-16T17:40:00Z" if clv is not None else None,
            "regle_le": f"2026-10-17T{i // 60:02d}:{i % 60:02d}:00Z",
            "match_id": f"m{i}"}


def test_verdict_echantillon_trop_court_meme_si_la_courbe_est_belle():
    avis = _serie([1.0] * 12)
    assert avis["verdict"] == TROP_TOT
    assert avis["details"]["paris_regles"] == 12
    assert avis["details"]["proba_chance"] == 0.0          # le gain est net, le suivi ne l'est pas
    assert any("100" in phrase for phrase in avis["raisons"])
    assert 2 <= len(avis["raisons"]) <= 3


def test_verdict_prometteur_quand_la_clv_n_est_pas_significative():
    # Profit sûr, CLV légèrement positive sur les deux moitiés, mais le test par match ne passe pas 5 %.
    clvs = ([0.05] * 52 + [-0.05] * 48) * 2
    cotes = [1.5 + (i % 10) * 0.1 for i in range(200)]
    avis = analyser_serie([1.0] * 200, [10.0] * 200, cotes, clvs)
    d = avis["details"]
    assert d["paris_regles"] == 200 and d["clv_n"] == 200
    assert d["clv_moyenne"] > 0 and d["clv_premiere"] > 0 and d["clv_seconde"] > 0
    assert d["proba_chance"] < SEUILS["proba_chance_fiable"]
    assert d["q_bh"] >= SEUILS["q_bh_fiable"]
    assert d["depend_grosses_cotes"] is False
    assert avis["verdict"] == PROMETTEUR
    assert avis["verdict"] in VERDICTS
    assert 2 <= len(avis["raisons"]) <= 3


def test_clv_solide_et_profit_negatif_reste_prometteur():
    # Beaucoup de longues cotes : la CLV est nettement positive, le gain en euros ne l'est pas.
    gains = [-10.0] * 80 + [8.0] * 50
    clvs = [0.04] * 130
    avis = analyser_serie(gains, [10.0] * 130, [3.0] * 130, clvs)
    assert avis["details"]["gain"] < 0
    assert avis["details"]["clv_moyenne"] > 0 and avis["details"]["q_bh"] < SEUILS["q_bh_fiable"]
    assert avis["verdict"] == PROMETTEUR


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
