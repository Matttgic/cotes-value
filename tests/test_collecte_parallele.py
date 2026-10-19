"""Ordonnancement réel : une référence lente ne bloque pas les cotes françaises.

Les bookmakers français sont tous lus en direct (PulseScore n'existe plus).
"""
from datetime import datetime, timezone

from scripts import cycle

NOW = datetime(2026, 10, 17, tzinfo=timezone.utc)


def ligne(sport, bookmaker="winamax"):
    return {"sport": sport, "debut": "2026-10-17T12:00:00Z", "bookmaker": bookmaker,
            "match_id": f"{bookmaker}|{sport}", "domicile": "Lens", "exterieur": "Lille",
            "cote": 1.9, "marche": "VAINQUEUR", "periode": "MATCH", "ligne": None, "issue": "DOM"}


def _sans_reseau(monkeypatch, direct=None):
    def dire(*args, **kwargs):
        if direct:
            return direct(*args, **kwargs)
        return [], {"ok": True, "erreurs": [], "requetes": 0, "matchs": 0}

    monkeypatch.setattr(cycle.pmu_direct, "collecter", dire)
    monkeypatch.setattr(cycle.olybet_direct, "collecter",
                        lambda *a, **k: ([], {"ok": True, "erreurs": [], "requetes": 0, "matchs": 0}))
    monkeypatch.setattr(cycle.winamax_direct, "collecter",
                        lambda *a, **k: ([], {"ok": True, "erreurs": [], "requetes": 0, "matchs": 0}))
    monkeypatch.setattr(cycle.unibet_direct, "collecter",
                        lambda *a, **k: ([], {"ok": True, "erreurs": [], "requetes": 0, "matchs": 0}))
    monkeypatch.setattr(cycle.betclic_direct, "collecter",
                        lambda *a, **k: ([], {"ok": True, "erreurs": [], "requetes": 0, "matchs": 0}))
    monkeypatch.setattr(cycle.netbet_direct, "collecter",
                        lambda *a, **k: ([], {"ok": True, "erreurs": [], "requetes": 0, "matchs": 0}))
    monkeypatch.delenv("SOURCE_OLYBET", raising=False)
    monkeypatch.delenv("SOURCE_NETBET", raising=False)


def test_echec_reference_isole_ne_plante_pas(monkeypatch):
    def panne(*args):
        raise RuntimeError("source indisponible")

    _sans_reseau(monkeypatch)
    monkeypatch.setattr(cycle.pinnacle, "collecter", panne)
    monkeypatch.setattr(cycle.polymarket, "collecter", lambda *a: [])
    j = {"etapes": {}}
    pin, poly, lignes = cycle.collecter_prematch("complet", NOW, j)
    assert pin == [] and not lignes
    assert j["etapes"]["pinnacle"]["ok"] is False
    assert "pulsescore" not in j["etapes"]


def test_toutes_les_cotes_francaises_viennent_des_lecteurs_directs(monkeypatch):
    def direct(bookmaker):
        return lambda *a, **k: ([ligne("football", bookmaker)], {"ok": True, "erreurs": [], "requetes": 1, "matchs": 1})

    _sans_reseau(monkeypatch)
    for nom, module in (("pmu", cycle.pmu_direct), ("winamax", cycle.winamax_direct),
                        ("unibet-fr", cycle.unibet_direct), ("betclic", cycle.betclic_direct)):
        monkeypatch.setattr(module, "collecter", direct(nom))
    # Aucune variable SOURCE_* n'est nécessaire : une ancienne valeur « pulsescore » n'a plus d'effet.
    for variable in ("SOURCE_PMU", "SOURCE_WINAMAX", "SOURCE_UNIBET", "SOURCE_BETCLIC"):
        monkeypatch.setenv(variable, "pulsescore")
    monkeypatch.setattr(cycle.pinnacle, "collecter", lambda: [ligne("football", "pinnacle")])
    monkeypatch.setattr(cycle.polymarket, "collecter", lambda *a: [])
    monkeypatch.setattr(cycle, "harmoniser_pinnacle", lambda x: x)
    j = {"etapes": {}}
    _, _, lignes = cycle.collecter_prematch("complet", NOW, j)
    assert [l["bookmaker"] for l in lignes] == ["pmu", "winamax", "unibet-fr", "betclic"]
    directs = {k: e for k, e in j["etapes"].items() if k.endswith("_direct")}
    assert len(directs) == 4 and all(e["ok"] and not e.get("degrade") for e in directs.values())
    assert "pulsescore" not in j["etapes"]


def test_winamax_incomplet_marque_son_etape(monkeypatch):
    _sans_reseau(monkeypatch)
    monkeypatch.setattr(cycle.winamax_direct, "collecter",
                        lambda *a, **k: ([ligne("football")], {"ok": False, "erreurs": ["socket fermé"], "requetes": 1}))
    monkeypatch.setattr(cycle.pinnacle, "collecter", lambda: [ligne("football", "pinnacle")])
    monkeypatch.setattr(cycle.polymarket, "collecter", lambda *a: [])
    monkeypatch.setattr(cycle, "harmoniser_pinnacle", lambda x: x)
    j = {"etapes": {}}
    _, _, lignes = cycle.collecter_prematch("complet", NOW, j)
    assert [l["bookmaker"] for l in lignes] == ["winamax"]          # les cotes lues restent utilisées
    assert j["etapes"]["winamax_direct"]["ok"] is False


def test_sources_independantes_partent_ensemble(monkeypatch):
    import threading
    import time

    starts = []
    verrou = threading.Lock()

    def lent(*args, **kwargs):
        with verrou:
            starts.append(time.monotonic())
        time.sleep(0.25)
        return [], {"ok": True, "erreurs": [], "requetes": 0, "matchs": 0}

    _sans_reseau(monkeypatch)
    monkeypatch.setattr(cycle.pmu_direct, "collecter", lent)
    monkeypatch.setattr(cycle.winamax_direct, "collecter", lent)
    monkeypatch.setattr(cycle.unibet_direct, "collecter", lent)
    monkeypatch.setattr(cycle.betclic_direct, "collecter", lent)
    monkeypatch.setattr(cycle.olybet_direct, "collecter", lent)
    monkeypatch.setattr(cycle.netbet_direct, "collecter", lent)
    monkeypatch.setattr(cycle.pinnacle, "collecter", lambda: [ligne("football")])
    monkeypatch.setattr(cycle.polymarket, "collecter", lambda *a: [])
    monkeypatch.setattr(cycle, "harmoniser_pinnacle", lambda x: x)
    cycle.collecter_prematch("complet", NOW, {"etapes": {}})
    assert len(starts) == 6
    assert max(starts) - min(starts) < 0.5


def test_cloture_reutilise_l_index(monkeypatch):
    from cotes import comparaison

    base = {"sport": "football", "domicile": "Lens", "exterieur": "Lille",
            "debut": "2030-01-01T20:00:00Z", "collecte": "2030-01-01T19:00:00Z",
            "marche": "VAINQUEUR", "periode": "MATCH", "ligne": None, "issue": "DOM",
            "marge_pinnacle": 0.02}
    fr = [{**base, "source": "winamax", "bookmaker": "winamax", "match_id": "w|1", "cote": 2.1}]
    pin = [{**base, "source": "pinnacle", "match_id": "p1", "cote": 2.0, "proba_juste": 0.5}]
    idx = comparaison.indexer(fr, {"Pinnacle": pin})

    def boom(*args, **kwargs):
        raise AssertionError("associer")

    monkeypatch.setattr(comparaison.C, "associer", boom)
    clos = comparaison.cotes_justes_depuis(idx)
    cle = ("w|1", ("VAINQUEUR", "MATCH", None, "DOM"))
    assert abs(clos[cle]["Pinnacle"][0] - 0.5) < 1e-9
