from datetime import datetime, timedelta, timezone

from cotes import mouvement


def test_z_utilise_les_statistiques_d_avant_le_cycle():
    stats = {}
    base = [0.01 * ((i % 5) - 2) or 0.001 for i in range(mouvement.Z_MIN_MESURES)]
    assert mouvement.z_et_maj(stats, {"TOTAL|MATCH": base}) == {"TOTAL|MATCH": None}   # pas encore de base
    n, moy, var = stats["TOTAL|MATCH"]
    assert n == mouvement.Z_MIN_MESURES and var > 0
    avant = mouvement.z_et_maj(stats, {"TOTAL|MATCH": [0.5]})
    assert avant["TOTAL|MATCH"] == (moy, var ** .5)          # la mesure du cycle n'entre pas dans sa propre base
    assert stats["TOTAL|MATCH"][0] == n + 1


def test_mouvements_nuls_hors_base():
    stats = {}
    mouvement.z_et_maj(stats, {"G": [0, 0, 0.02]})
    assert stats["G"][0] == 1


def _index(p_par_ligne):
    return {"Pinnacle": {"m1": {("HANDICAP", "MATCH", l, "1"): {"proba_juste": p} for l, p in p_par_ligne.items()}}}


def test_annoter_z_et_episode(tmp_path):
    chemin = tmp_path / "ancres_mouvement.json.gz"
    t0 = datetime(2026, 11, 18, 8, tzinfo=timezone.utc)
    mouvement.ecrire(tmp_path / mouvement.STATS, {"HANDICAP|MATCH": [500, 0.0, 0.0001]})   # écart-type 1 %
    mouvement.annoter([], _index({-0.5: 0.50, -1.0: 0.40, -1.5: 0.30}), chemin, t0)
    o = {"match_id": "m1", "marche": "HANDICAP", "periode": "MATCH", "ligne": -0.5, "issue": "1",
         "reference": "Pinnacle"}
    mouvement.annoter([o], _index({-0.5: 0.52, -1.0: 0.42, -1.5: 0.30}), chemin, t0 + timedelta(minutes=15))
    assert o["mouvement_pinnacle"] == 0.04
    assert o["mouvement_z"] == 4.0
    assert o["mouvement_lignes"] == 2          # −0,5 et −1 ont chuté d'au moins 3 %, pas −1,5
    assert mouvement.lire(tmp_path / mouvement.STATS)["HANDICAP|MATCH"][0] == 502   # la ligne figée (0) est exclue


def _ligne_pin(p, issue="DOM", mid="pin|1"):
    return {"match_id": mid, "marche": "RESULTAT_1N2", "periode": "MATCH", "ligne": None, "issue": issue,
            "domicile": "A", "exterieur": "B", "proba_juste": p}


def _index_six(p_dom, p_ext, inverses=("netbet|6",)):
    """Le même match Pinnacle associé à six matchs français ; chez NetBet, domicile et extérieur sont échangés."""
    from cotes.marches import cle, inverser
    out = {}
    for mid_fr in ("betclic|1", "pmu|2", "unibet|3", "winamax|4", "olybet|5", "netbet|6"):
        lignes = [_ligne_pin(p_dom, "DOM"), _ligne_pin(p_ext, "EXT")]
        out[mid_fr] = {cle(inverser(l) if mid_fr in inverses else l): l for l in lignes}
    return {"Pinnacle": out}


def test_une_cote_pinnacle_compte_une_fois_meme_associee_a_six_bookmakers(tmp_path):
    chemin = tmp_path / "ancres_mouvement.json.gz"
    t0 = datetime(2026, 11, 18, 8, tzinfo=timezone.utc)
    assert mouvement.annoter([], _index_six(0.50, 0.30), chemin, t0)["ancres"] == 2
    ops = [{"match_id": m, "marche": "RESULTAT_1N2", "periode": "MATCH", "ligne": None, "issue": "DOM",
            "reference": "Pinnacle"} for m in ("betclic|1", "pmu|2", "unibet|3", "winamax|4", "olybet|5")]
    r = mouvement.annoter(ops, _index_six(0.52, 0.30), chemin, t0 + timedelta(minutes=15))
    assert r["ancres"] == 2 and r["mesures"] == 2
    assert {o["mouvement_pinnacle"] for o in ops} == {0.04}
    assert mouvement.lire(tmp_path / mouvement.STATS)["RESULTAT_1N2|MATCH"][0] == 1   # la cote figée (EXT) est exclue


def test_equipes_inversees_chez_le_bookmaker_recoivent_le_mouvement_de_la_bonne_issue(tmp_path):
    chemin = tmp_path / "ancres_mouvement.json.gz"
    t0 = datetime(2026, 11, 18, 8, tzinfo=timezone.utc)
    mouvement.annoter([], _index_six(0.50, 0.30), chemin, t0)
    # Chez NetBet, « EXT » est le domicile de Pinnacle : il reçoit la hausse de DOM (+4 %), pas EXT (0).
    o = {"match_id": "netbet|6", "marche": "RESULTAT_1N2", "periode": "MATCH", "ligne": None, "issue": "EXT",
         "reference": "Pinnacle"}
    mouvement.annoter([o], _index_six(0.52, 0.30), chemin, t0 + timedelta(minutes=15))
    assert o["mouvement_pinnacle"] == 0.04
