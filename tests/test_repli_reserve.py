"""Une source coupée par son budget rend sa mémoire du passage précédent au lieu de rien."""
from datetime import datetime, timedelta, timezone

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
    monkeypatch.setattr(cycle, "harmoniser_pinnacle", lambda x: x)
    monkeypatch.setattr(cycle.unibet_direct, "collecter", lambda *a, **k: None)      # source coupée : rien rendu
    bloc = {"curseur": 7, "lignes": [ligne("unibet-fr|1", 4)]}
    import json, tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "horizon_direct.json").write_text(json.dumps({"unibet": bloc}))
        j = {"etapes": {}}
        _, _, lignes = cycle.collecter_prematch("complet", NOW, j, Path(d))
        assert [l["match_id"] for l in lignes] == ["unibet-fr|1"]
        assert json.loads((Path(d) / "horizon_direct.json").read_text())["unibet"] == bloc     # mémoire intacte
