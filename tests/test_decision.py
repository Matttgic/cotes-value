"""Page Décision : lignes mesurées, corrections et règles de décision (cotes/decision.py, web/decision.js)."""
from datetime import datetime, timedelta, timezone

import pytest

from cotes import decision
from cotes.decision import ATTENDRE, COUPER, JOUER, SURVEILLER

DEBUT = datetime(2026, 11, 1, tzinfo=timezone.utc)


def _pari(i, clv, bookmaker="PMU", reference="Pinnacle", gagne=None, mesure=True, statut=None):
    debut = DEBUT + timedelta(hours=i)
    gagne = i % 2 == 0 if gagne is None else gagne
    p = {"id": f"{bookmaker}-{reference}-{i}", "reference": reference, "bookmaker": bookmaker, "sport": "football",
         "match_id": f"{bookmaker}|{i}", "marche": "VAINQUEUR", "periode": "MATCH", "ligne": None, "issue": "DOM",
         "cote": 2.0, "mise": 10.0, "detecte": (debut - timedelta(hours=3)).isoformat(), "debut": debut.isoformat(),
         "statut": statut or ("gagne" if gagne else "perdu"), "gain": None if statut else 10.0 if gagne else -10.0}
    if mesure:
        p.update(clv=clv, cote_juste_cloture=round(2.0 / (1 + clv), 4),
                 cloture_lue=(debut - timedelta(minutes=10)).isoformat())
    return p


def _ligne(**plus):
    """Ligne déjà mesurée et corrigée, neutre : ni ROI ni CLV ne se distinguent de zéro."""
    x = {"regles": 500, "teste": True, "clv_teste": True, "roi": 1.0, "roi_ic": [-4.0, 6.0], "couverture": 0.8,
         "roi_p_pos_bh": 1.0, "roi_p_neg_bh": 1.0, "clv": 0.2, "clv_p_pos_holm": 1.0, "clv_p_neg_bh": 1.0,
         "ecart_ic": [-5.0, 5.0]}
    return {**x, **plus}


def test_holm_et_quantile_de_student_sur_des_valeurs_connues():
    assert decision.holm([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])
    assert decision.holm([]) == []
    assert decision.quantile_student(10) == pytest.approx(2.2281, abs=1e-3)
    assert decision.quantile_student(1e6) == pytest.approx(1.96, abs=1e-3)


def test_jouer_demande_un_roi_positif_et_une_clv_pinnacle_prouvee_sur_la_moitie_des_paris():
    prouvee = dict(clv=2.0, clv_p_pos_holm=0.001)
    assert decision.decider(_ligne(**prouvee))[0] == JOUER
    assert decision.decider(_ligne(**prouvee, couverture=0.4))[0] == ATTENDRE          # clôture trop rare
    assert decision.decider(_ligne(**prouvee, roi=-1.0)) == (ATTENDRE, "CLV Pinnacle prouvée, ROI négatif")
    assert decision.decider(_ligne(**prouvee, ecart_ic=[-9.0, -1.0]))[0] == ATTENDRE   # le rendement dément la CLV
    assert decision.decider(_ligne(clv=2.0, clv_p_pos_holm=0.2))[0] == ATTENDRE        # ne tient pas après correction
    assert decision.decider(_ligne(regles=12, teste=False, clv_teste=False)) == (ATTENDRE, "trop peu de paris (12 réglés)")


def test_couper_demande_un_roi_negatif_confirme_par_le_roi_ou_par_la_clv():
    assert decision.decider(_ligne(roi=-12.0, roi_ic=[-20.0, -4.0], roi_p_neg_bh=0.01))[0] == COUPER
    assert decision.decider(_ligne(roi=-5.0, roi_ic=[-15.0, 5.0], clv=-3.0, clv_p_neg_bh=0.01))[0] == COUPER
    # Tendance négative sans confirmation, ou CLV négative avec un ROI positif : à surveiller, pas à couper.
    assert decision.decider(_ligne(roi=-12.0, roi_ic=[-20.0, -4.0]))[0] == SURVEILLER
    assert decision.decider(_ligne(clv=-3.0, clv_p_neg_bh=0.01))[0] == SURVEILLER


def test_lignes_mesurees_sur_des_paris_bookmakers_sur_les_uniques_references_sur_tous():
    # PMU : 200 paris qui battent la clôture de 3 % ± 2 et gagnent 3 fois sur 5 à cote 2 (ROI +20 %).
    pmu = [_pari(i, 0.03 + 0.02 * (i % 3 - 1), gagne=i % 5 < 3) for i in range(200)]
    # OlyBet : 200 paris qui perdent 4 % contre la clôture et gagnent 2 fois sur 5 (ROI −20 %).
    oly = [_pari(i, -0.04 + 0.02 * (i % 3 - 1), bookmaker="OlyBet", gagne=i % 5 < 2) for i in range(200)]
    # La même cote PMU repérée ensuite par Polymarket : comptée pour la référence, pas pour le bookmaker.
    double = [{**_pari(i, 0.0, reference="Polymarket", mesure=False),
               "detecte": (DEBUT + timedelta(hours=i - 1)).isoformat()} for i in range(40)]
    ouverts = [_pari(1000 + i, 0.0, mesure=False, statut="en_cours") for i in range(5)]
    bloc = decision.construire(pmu + oly + double + ouverts, DEBUT + timedelta(days=30))
    par_id = {l["id"]: l for l in bloc["lignes"]}
    assert list(par_id) == ["ensemble", "bookmaker:PMU", "bookmaker:OlyBet", "reference:Pinnacle", "reference:Polymarket"]
    p, o = par_id["bookmaker:PMU"], par_id["bookmaker:OlyBet"]
    assert (p["paris"], p["regles"], p["matchs"], p["clv_n"], p["couverture"]) == (205, 200, 200, 200, 100.0)
    assert p["roi"] == pytest.approx(20.0) and p["clv"] == pytest.approx(3.0, abs=0.02)
    assert p["clv_ic"][0] < p["clv"] < p["clv_ic"][1] and p["clv_ic"][0] > 0 and p["clv_p"] < 0.001
    assert p["decision"] == JOUER and p["raison"].startswith("ROI positif")
    assert o["roi"] == pytest.approx(-20.0) and o["decision"] == COUPER
    # Référence Polymarket : ses 40 paris, dont la clôture Pinnacle est reprise du même pari repéré par Pinnacle.
    r = par_id["reference:Polymarket"]
    assert (r["regles"], r["clv_n"]) == (40, 40) and r["clv"] > 0
    assert bloc["regles"]["tests_roi"] == 2 * 5 and bloc["regles"]["tests_clv"] == 2 * 5


def _regle(p, heures=2):
    """Pari réglé ``heures`` après le début de son match."""
    return {**p, "regle_le": (datetime.fromisoformat(p["debut"]) + timedelta(hours=heures)).isoformat()}


def test_quoi_jouer_rejoue_sans_regard_vers_l_avenir():
    # 400 paris PMU / Pinnacle gagnants (ROI +20 %), 400 OlyBet / Betfair perdants, un toutes les heures sur ~17 jours.
    pmu = [_regle(_pari(i, 0.03 + 0.02 * (i % 3 - 1), gagne=i % 5 < 3)) for i in range(400)]
    oly = [_regle(_pari(i, -0.04, bookmaker="OlyBet", reference="Betfair", gagne=i % 5 < 2)) for i in range(400)]
    r = decision.construire(pmu + oly, DEBUT + timedelta(days=30))["rejeu"]
    # Le premier jour, rien n'est encore réglé : la règle ne retient rien avant d'avoir assez de paris passés.
    assert r["debut"] > DEBUT.date().isoformat()
    # Retenus : seulement PMU / Pinnacle, détectés après le jour où PMU est devenu jouable ; jamais OlyBet.
    assert 0 < r["retenus"]["regles"] < 400 and r["retenus"]["roi"] > 0 and r["retenus"]["roi_ic"][0] > 0
    assert r["retenus"]["clv"] == pytest.approx(3.0, abs=0.1) and r["retenus"]["couverture"] == 100.0
    # Écartés : les OlyBet des mêmes jours, perdants.
    assert r["ecartes"]["roi"] < 0 and r["ecartes"]["regles"] >= r["retenus"]["regles"] - 30
    # Un pari réglé après minuit ne sert pas le jour même : réglés deux jours plus tard, la règle démarre plus tard.
    tard = decision.construire([_regle(p, 48) for p in pmu + oly], DEBUT + timedelta(days=30))["rejeu"]
    assert tard["debut"] > r["debut"] and tard["retenus"]["regles"] < r["retenus"]["regles"]


def test_sans_pari_la_page_a_quand_meme_sa_ligne_sans_decision():
    bloc = decision.construire([], DEBUT)
    assert [(l["id"], l["regles"], l["decision"]) for l in bloc["lignes"]] == [("ensemble", 0, ATTENDRE)]
    assert bloc["rejeu"] == {"debut": None, "jours": 0, "retenus": decision._bilan([], None, {}),
                             "ecartes": decision._bilan([], None, {})}


def test_le_site_publie_les_chiffres_et_la_page(tmp_path):
    import json

    from scripts.site_web import construire
    html = construire(tmp_path, tmp_path / "site").read_text(encoding="utf-8")
    debut = html.index("const D = ") + len("const D = ")
    donnees, _ = json.JSONDecoder().raw_decode(html, debut)
    assert donnees["decision"]["lignes"][0]["id"] == "ensemble"
    assert 'id="o-decision"' in html and "function rendreDecision" in html and "__DECISION_JS__" not in html
    # La page ouvre son onglet de départ avant ce fichier : seulement des fonctions, hissées par le navigateur.
    from pathlib import Path
    source = (Path(__file__).resolve().parent.parent / "web/decision.js").read_text(encoding="utf-8")
    assert not [l for l in source.splitlines() if l.startswith(("const ", "let "))]
