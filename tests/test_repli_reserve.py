"""Une source coupée par son budget rend sa mémoire du passage précédent au lieu de rien."""
from datetime import datetime, timedelta, timezone

from cotes import memoire
from scripts import cycle

NOW = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)


def ligne(mid, lu_min, debut_h=3):
    return {"match_id": mid, "cote": 2.0, "debut": (NOW + timedelta(hours=debut_h)).isoformat(),
            "collecte": (NOW - timedelta(minutes=lu_min)).isoformat()}


def test_garde_les_lignes_recentes_a_venir_avec_leur_heure_d_origine():
    bloc = {"curseur": 4, "lignes": [ligne("a", 5), ligne("b", 29), ligne("vieille", 31), ligne("finie", 5, debut_h=-1),
                                     {"match_id": "sans date", "cote": 2.0}, "abime"]}
    lignes, meta = cycle.repli_reserve(bloc, NOW)
    assert [l["match_id"] for l in lignes] == ["a", "b"]
    assert lignes[0]["collecte"] == (NOW - timedelta(minutes=5)).isoformat()      # âge honnête
    assert meta == {"ok": False, "erreurs": ["lecture interrompue"], "requetes": 0, "repli": 2, "reserve": bloc}


def test_sans_memoire_comme_avant_aucune_ligne_et_pas_de_reserve():
    for bloc in ({}, None):
        lignes, meta = cycle.repli_reserve(bloc, NOW)
        assert lignes == [] and meta["ok"] is False and "reserve" not in meta


def test_cycle_complet_unibet_coupe_rend_sa_memoire_et_la_garde(monkeypatch):
    from tests.test_collecte_parallele import _sans_reseau
    _sans_reseau(monkeypatch)
    monkeypatch.setattr(cycle.pinnacle, "collecter", lambda: [])
    monkeypatch.setattr(cycle.polymarket, "collecter", lambda *a: [])
    monkeypatch.setattr(cycle.pinnacle_secours, "disponible", lambda: False)
    monkeypatch.setattr("cotes.pipeline.collecte.harmoniser_pinnacle", lambda x: x)
    monkeypatch.setattr(cycle.unibet_direct, "collecter", lambda *a, **k: None)      # source coupée : rien rendu
    bloc = {"curseur": 7, "lignes": [ligne("unibet-fr|1", 4)]}
    import json, tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "horizon_direct.json").write_text(json.dumps({"unibet": bloc}))
        j = {"etapes": {}}
        _, _, lignes = cycle.collecter_prematch("complet", NOW, j, Path(d))
        assert [l["match_id"] for l in lignes] == ["unibet-fr|1"]
        assert memoire.lire(Path(d), "horizon_direct")["unibet"] == bloc     # mémoire intacte


def test_completer_par_reserve_seulement_si_lecture_vide_en_echec():
    from cotes.pipeline.collecte import completer_par_reserve
    bloc = {"lignes": [ligne("winamax|1", 5), ligne("winamax|vieille", 40)]}
    lignes, meta = completer_par_reserve([], {"ok": False, "erreurs": ["sport:1 : réseau (CurlError 22)"]}, bloc, NOW)
    assert [l["match_id"] for l in lignes] == ["winamax|1"]
    assert meta == {"ok": False, "erreurs": ["sport:1 : réseau (CurlError 22)"], "repli": 1}   # panne gardée
    lue = [ligne("winamax|2", 0)]
    assert completer_par_reserve(lue, {"ok": False}, bloc, NOW) == (lue, {"ok": False})        # lecture partielle
    assert completer_par_reserve([], {"ok": True}, bloc, NOW) == ([], {"ok": True})
    assert completer_par_reserve([], {"ok": False}, {}, NOW) == ([], {"ok": False})


def test_cycle_complet_winamax_refuse_rend_sa_lecture_precedente(monkeypatch):
    from tests.test_collecte_parallele import _sans_reseau
    _sans_reseau(monkeypatch)
    monkeypatch.setattr(cycle.pinnacle, "collecter", lambda: [])
    monkeypatch.setattr(cycle.polymarket, "collecter", lambda *a: [])
    monkeypatch.setattr(cycle.pinnacle_secours, "disponible", lambda: False)
    monkeypatch.setattr("cotes.pipeline.collecte.harmoniser_pinnacle", lambda x: x)
    monkeypatch.setattr(cycle.winamax_direct, "collecter", lambda *a, **k: (
        [], {"ok": False, "erreurs": ["sport:1 : réseau (CurlError 22)", "lecture vide"], "requetes": 0}))
    bloc = {"lignes": [{**ligne("winamax|1", 4), "source": "Winamax", "bookmaker": "winamax", "marche": "RESULTAT_1N2"}]}
    import json, tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "horizon_direct.json").write_text(json.dumps({"winamax": bloc}))
        j = {"etapes": {}}
        _, _, lignes = cycle.collecter_prematch("complet", NOW, j, Path(d))
        assert "winamax|1" in [l["match_id"] for l in lignes]
        assert j["etapes"]["winamax_direct"]["ok"] is False and j["etapes"]["winamax_direct"]["repli"] == 1
