"""Phase 1 de l'analyse du marché : durée des opportunités, meneurs, cache journalier, segments."""
import gzip
import json
from datetime import datetime, timedelta, timezone

from cotes.analyse_marche import cache, meneurs as M, opportunites as O, segments as S

J = "2026-11-11"
T0 = datetime(2026, 11, 11, 10, 0, tzinfo=timezone.utc)


def iso(dt):
    return dt.isoformat(timespec="seconds")


def ecrire(donnees, dossier, jour, lignes):
    f = donnees / dossier / f"{jour}.jsonl.gz"
    f.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(f, "at", encoding="utf-8") as sortie:
        for x in lignes:
            sortie.write(json.dumps(x, separators=(",", ":")) + "\n")


def opp(cycle, issue="DOM", cote=2.0, bookmaker="PMU", mid="pmu|1", debut="2026-11-11T20:00:00Z"):
    return {"cycle_id": iso(cycle), "detecte": iso(cycle), "bookmaker": bookmaker, "match_id": mid,
            "marche": "RESULTAT_1N2", "periode": "MATCH", "ligne": None, "issue": issue, "reference": "Pinnacle",
            "cote": cote, "ecart": 0.04, "sport": "football", "debut": debut, "pariable": True}


def cyc(i):
    return T0 + timedelta(minutes=5 * i)


def test_episode_corrige_par_le_bookmaker_puis_par_la_reference(tmp_path):
    # cycles 0..5 ; DOM présent aux cycles 0-2 (le bookmaker baisse au cycle 3), EXT aux cycles 1-3
    lignes = [opp(cyc(i), "AUTRE", mid="pmu|9") for i in range(6)]            # cycles connus
    lignes += [opp(cyc(i)) for i in (0, 1, 2)] + [opp(cyc(i), "EXT", 3.0) for i in (1, 2, 3)]
    ecrire(tmp_path, "opportunites", J, lignes)
    ecrire(tmp_path, "cotes", J, [
        {"t": iso(cyc(0) + timedelta(seconds=30)), "b": "PMU", "m": "pmu|1", "k": "RESULTAT_1N2|MATCH||DOM", "c": 2.0},
        {"t": iso(cyc(0) + timedelta(seconds=30)), "b": "PMU", "m": "pmu|1", "k": "RESULTAT_1N2|MATCH||EXT", "c": 3.0},
        {"t": iso(cyc(3) + timedelta(seconds=40)), "b": "PMU", "m": "pmu|1", "k": "RESULTAT_1N2|MATCH||DOM", "c": 1.9},
    ])
    eps = {e["k"]: e for e in O.episodes_du_jour(tmp_path, J) if e["m"] == "pmu|1"}
    dom, ext = eps["RESULTAT_1N2|MATCH||DOM"], eps["RESULTAT_1N2|MATCH||EXT"]
    assert (dom["dmin"], dom["dmax"], dom["cause"]) == (10.0, 15.0, "bookmaker")
    assert (ext["dmin"], ext["dmax"], ext["cause"]) == (10.0, 15.0, "reference")
    assert dom["debut_connu"] is False and ext["debut_connu"] is True     # DOM dès le premier cycle connu


def test_fin_non_observee_et_couverture_inconnue_et_match_commence(tmp_path):
    lignes = [opp(cyc(i), "AUTRE", mid="pmu|9") for i in range(4)]
    lignes += [opp(cyc(i), bookmaker="OlyBet", mid="oly|1") for i in (1, 2)]                 # pas dans cotes/
    lignes += [opp(cyc(i), mid="pmu|2", debut=iso(cyc(2) + timedelta(minutes=1))) for i in (1, 2)]
    lignes += [opp(cyc(3), mid="pmu|3")]                                                      # dernier cycle
    ecrire(tmp_path, "opportunites", J, lignes)
    eps = {e["m"]: e for e in O.episodes_du_jour(tmp_path, J)}
    assert eps["oly|1"]["cause"] == "inconnue"
    assert eps["pmu|2"]["cause"] == "match_commence"
    assert eps["pmu|3"]["cause"] == "en_cours" and eps["pmu|3"]["dmax"] is None


def test_lignes_sans_cycle_ecartees(tmp_path):
    o = opp(cyc(0))
    del o["cycle_id"]
    ecrire(tmp_path, "opportunites", J, [o])
    assert O.episodes_du_jour(tmp_path, J) == []


def test_apparier_plus_proche_meme_sens():
    a = [(cyc(0), 1, 0.02), (cyc(10), -1, 0.02)]
    b = [(cyc(1), 1, 0.02), (cyc(0) + timedelta(seconds=30), -1, 0.02), (cyc(20), -1, 0.02)]
    paires, seuls_a, seuls_b = M.apparier(a, b)
    assert paires == [(a[0], b[0])]
    assert seuls_a == [a[1]] and len(seuls_b) == 2                          # cyc(20) : hors fenêtre de 30 min


def test_meneurs_de_bout_en_bout(tmp_path):
    desc = {"sport": "football", "dom": "Lens", "ext": "Lille", "debut": "2026-11-11T20:00:00Z"}
    k = "RESULTAT_1N2|MATCH||DOM"
    ecrire(tmp_path, "cotes", J, [
        {"t": iso(cyc(0)), "b": "PMU", "m": "pmu|1", **desc},
        {"t": iso(cyc(0)), "b": "Betclic", "m": "bc|1", **desc},
        {"t": iso(cyc(0)), "b": "PMU", "m": "pmu|1", "k": k, "c": 2.0},
        {"t": iso(cyc(0)), "b": "Betclic", "m": "bc|1", "k": k, "c": 2.0},
        {"t": iso(cyc(2)), "b": "Betclic", "m": "bc|1", "k": k, "c": 1.8},       # Betclic baisse d'abord
        {"t": iso(cyc(4)), "b": "PMU", "m": "pmu|1", "k": k, "c": 1.85},         # PMU suit 10 min après
        {"t": iso(cyc(6)), "b": "PMU", "m": "pmu|1", "k": k, "c": 1.86},         # trop petit : pas un mouvement
    ])
    r = M.meneurs_du_jour(tmp_path, J)
    assert len(r) == 1 and r[0]["meneur"] == "Betclic" and r[0]["delai_min"] == 10.0
    t = S.resume_meneurs(r)
    assert t[0]["a"] == "Betclic" and t[0]["pct_a_devant"] == 100.0 and t[0]["insuffisant"] is True


def test_cache_seulement_pour_les_jours_termines(tmp_path):
    ecrire(tmp_path, "opportunites", J, [opp(cyc(0)), opp(cyc(1))])
    dossier = tmp_path / "cache"
    _, etat = cache.resume(tmp_path, J, dossier, aujourd_hui="2026-11-12")
    assert etat == "provisoire" and not dossier.exists()
    doc, etat = cache.resume(tmp_path, J, dossier, aujourd_hui="2026-11-13")
    assert etat == "calculé" and (dossier / f"{J}.json.gz").exists()
    (tmp_path / "opportunites" / f"{J}.jsonl.gz").unlink()                  # le passé n'est plus relu
    assert cache.resume(tmp_path, J, dossier, aujourd_hui="2026-11-13") == (doc, "cache")


def test_segments_tranches_et_durees():
    assert [S.tranche(x) for x in (0.5, 2, 5, 20, 30, None, -1)] == [
        "< 1 h", "1-3 h", "3-12 h", "12-24 h", "> 24 h", "inconnu", "inconnu"]
    eps = [{"b": "PMU", "dmin": 0.0, "dmax": 5.0, "cause": "bookmaker", "delai_h": 2},
           {"b": "PMU", "dmin": 10.0, "dmax": 15.0, "cause": "reference", "delai_h": 2},
           {"b": "PMU", "dmin": 20.0, "dmax": None, "cause": "en_cours", "delai_h": 2}]
    r = S.resume_opportunites(eps, ("b", "tranche"))
    assert r == [{"b": "PMU", "tranche": "1-3 h", "n": 3, "fins_observees": 2, "mediane_min": [5.0, 10.0],
                  "p75_min": [10.0, 15.0], "pct_bookmaker": 33.3, "pct_reference": 33.3, "pct_match_commence": 0.0,
                  "pct_inconnue": 0.0, "pct_en_cours": 33.3, "insuffisant": True}]
