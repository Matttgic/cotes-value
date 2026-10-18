"""Ordonnancement réel : une référence lente ne bloque pas les cotes FR.

PMU en shadow reste celui de PulseScore. Le complément qui n'existait que pour
les sports vus seulement chez Kalshi n'est plus appelé.
"""
from datetime import datetime, timezone

from scripts import cycle

NOW = datetime(2026, 10, 17, tzinfo=timezone.utc)


def ligne(sport, bookmaker="winamax"):
    return {"sport": sport, "debut": "2026-10-17T12:00:00Z", "bookmaker": bookmaker,
            "match_id": f"{bookmaker}|{sport}", "domicile": "Lens", "exterieur": "Lille",
            "cote": 1.9, "marche": "VAINQUEUR", "periode": "MATCH", "ligne": None, "issue": "DOM"}


def _sans_reseau(monkeypatch, direct=None):
    monkeypatch.setenv("SOURCE_PMU", "shadow")

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
    monkeypatch.setenv("SOURCE_UNIBET", "shadow")
    monkeypatch.delenv("SOURCE_BETCLIC", raising=False)
    monkeypatch.delenv("SOURCE_OLYBET", raising=False)
    monkeypatch.delenv("SOURCE_NETBET", raising=False)
    monkeypatch.delenv("SOURCE_WINAMAX", raising=False)


def test_shadow_garde_pulsescore_et_ne_relit_pas_un_complement(monkeypatch):
    plans = []
    appels_direct = []

    def pin():
        return [ligne("football"), ligne("basket")]

    def pulse(key, plan, horizon, pages, **kwargs):
        plans.append(plan)
        return [ligne("football", "pmu")], {"pmu": 1}, {}

    def direct(sports, heures, **kwargs):
        appels_direct.append(set(sports))
        return [ligne("football", "pmu") | {"cote": 9.99, "match_id": "pmu|direct"}], {
            "ok": True, "erreurs": [], "requetes": 1, "matchs": 1}

    _sans_reseau(monkeypatch, direct)
    monkeypatch.setattr(cycle.pinnacle, "collecter", pin)
    monkeypatch.setattr(cycle.polymarket, "collecter", lambda *a: [])
    monkeypatch.setattr(cycle, "harmoniser_pinnacle", lambda x: x)
    monkeypatch.setattr(cycle.pulsescore, "collecter", pulse)
    j = {"etapes": {}}
    pin, poly, lignes, compte = cycle.collecter_prematch("test", "complet", NOW, j)
    assert list(plans) and "pmu" in plans[0]
    assert [p["winamax"] for p in plans] == [["soccer", "basketball"]]
    assert len(plans) == 1
    assert "pulsescore_complement" not in j["etapes"]
    assert lignes[0]["cote"] == 1.9
    assert appels_direct == [{"football", "basket"}]
    assert j["pmu_direct_rapport"]["matchs_communs"] == 1
    assert j["pmu_source"] == "shadow"
    assert all(e["ok"] for e in j["etapes"].values())
    assert pin and poly == [] and compte == {"pmu": 1}


def test_echec_reference_isole_et_shadow_sans_cle_ne_plante_pas(monkeypatch):
    def panne(*args):
        raise RuntimeError("source indisponible")

    _sans_reseau(monkeypatch)
    monkeypatch.setattr(cycle.pinnacle, "collecter", panne)
    monkeypatch.setattr(cycle.polymarket, "collecter", lambda *a: [])
    monkeypatch.setattr(cycle.pulsescore, "collecter", lambda *a: (_ for _ in ()).throw(AssertionError("pas de clé")))
    j = {"etapes": {}}
    pin, poly, lignes, compte = cycle.collecter_prematch(None, "complet", NOW, j)
    assert pin == [] and not lignes and not compte
    assert j["etapes"]["pinnacle"]["ok"] is False
    assert j["etapes"]["pulsescore"]["ok"] is False
    assert j["pmu_direct_rapport"]["matchs_pulsescore"] == 0
    assert "pulsescore_complement" not in j["etapes"]


def test_auto_bascule_sur_pulsescore_si_kambi_echoue(monkeypatch):
    plans = []

    def pulse(key, plan, *a, **kw):
        plans.append(plan)
        return [ligne("football", "pmu")], {"pmu": 1}, {}

    def direct(sports, heures, **kwargs):
        return [], {"ok": False, "erreurs": ["HTTP 429"], "requetes": 4, "matchs": 0}

    _sans_reseau(monkeypatch, direct)
    monkeypatch.setenv("SOURCE_PMU", "auto")
    monkeypatch.setattr(cycle.pinnacle, "collecter", lambda: [ligne("football")])
    monkeypatch.setattr(cycle.polymarket, "collecter", lambda *a: [])
    monkeypatch.setattr(cycle, "harmoniser_pinnacle", lambda x: x)
    monkeypatch.setattr(cycle.pulsescore, "collecter", pulse)
    j = {"etapes": {}}
    _, _, lignes, _ = cycle.collecter_prematch("test", "complet", NOW, j)
    assert "pmu" in plans[0]
    assert lignes[0]["match_id"] == "pmu|football"
    assert j["etapes"]["pmu_direct"]["degrade"] is True
    assert "pmu_direct_rapport" not in j


def test_direct_retire_pmu_de_pulsescore(monkeypatch):
    plans = []

    def pulse(key, plan, *a, **kw):
        plans.append(plan)
        return [ligne("football", "winamax")], {"winamax": 1}, {}

    def direct(sports, heures, **kwargs):
        return [ligne("football", "pmu") | {"cote": 1.7}], {"ok": True, "erreurs": [], "requetes": 2, "matchs": 1}

    _sans_reseau(monkeypatch, direct)
    monkeypatch.setenv("SOURCE_PMU", "direct")
    monkeypatch.setattr(cycle.pinnacle, "collecter", lambda: [ligne("football")])
    monkeypatch.setattr(cycle.polymarket, "collecter", lambda *a: [])
    monkeypatch.setattr(cycle, "harmoniser_pinnacle", lambda x: x)
    monkeypatch.setattr(cycle.pulsescore, "collecter", pulse)
    j = {"etapes": {}}
    _, _, lignes, _ = cycle.collecter_prematch("test", "complet", NOW, j)
    assert "pmu" not in plans[0] and "winamax" in plans[0]
    assert {l["bookmaker"] for l in lignes} == {"winamax", "pmu"}
    assert next(l["cote"] for l in lignes if l["bookmaker"] == "pmu") == 1.7


def test_shadow_bascule_sur_kambi_si_pulsescore_refuse(monkeypatch):
    def pulse(key, plan, *a, **kw):
        assert "pmu" in plan
        return [ligne("football", "pmu") | {"cote": 1.9}], {"pmu": 1}, {
            "pmu": ["pmu/soccer/events : HTTP 401"]}

    def direct(sports, heures, **kwargs):
        return [ligne("football", "pmu") | {"cote": 1.7, "match_id": "pmu|kambi"}], {
            "ok": True, "erreurs": [], "requetes": 2, "matchs": 1}

    _sans_reseau(monkeypatch, direct)
    monkeypatch.setattr(cycle.pinnacle, "collecter", lambda: [ligne("football")])
    monkeypatch.setattr(cycle.polymarket, "collecter", lambda *a: [])
    monkeypatch.setattr(cycle, "harmoniser_pinnacle", lambda x: x)
    monkeypatch.setattr(cycle.pulsescore, "collecter", pulse)
    j = {"etapes": {}}
    _, _, lignes, _ = cycle.collecter_prematch("cle", "complet", NOW, j)
    pmu = [l for l in lignes if l["bookmaker"] == "pmu"]
    assert pmu and pmu[0]["cote"] == 1.7 and pmu[0]["match_id"] == "pmu|kambi"
    assert j["pmu_source"] == "shadow" and j["pmu_source_effective"] == "direct"
    assert "Kambi" in j["pmu_repli"] and j["etapes"]["pulsescore"]["pmu_repli"] == j["pmu_repli"]


def test_shadow_bascule_sur_socket_si_pulsescore_refuse_winamax(monkeypatch):
    def pulse(key, plan, *a, **kw):
        assert "winamax" in plan
        return [ligne("football", "winamax") | {"cote": 1.9}], {"winamax": 1}, {
            "winamax": ["winamax/soccer/events : HTTP 401"]}

    def direct(sports, heures, **kwargs):
        return [ligne("football", "winamax") | {"cote": 1.7, "match_id": "winamax|socket"}], {
            "ok": True, "erreurs": [], "requetes": 2, "matchs": 1}

    _sans_reseau(monkeypatch)
    monkeypatch.setenv("SOURCE_WINAMAX", "shadow")
    monkeypatch.setattr(cycle.winamax_direct, "collecter", direct)
    monkeypatch.setattr(cycle.pinnacle, "collecter", lambda: [ligne("football")])
    monkeypatch.setattr(cycle.polymarket, "collecter", lambda *a: [])
    monkeypatch.setattr(cycle, "harmoniser_pinnacle", lambda x: x)
    monkeypatch.setattr(cycle.pulsescore, "collecter", pulse)
    j = {"etapes": {}}
    _, _, lignes, _ = cycle.collecter_prematch("cle", "complet", NOW, j)
    wina = [l for l in lignes if l["bookmaker"] == "winamax"]
    assert wina and wina[0]["cote"] == 1.7 and wina[0]["match_id"] == "winamax|socket"
    assert j["winamax_source"] == "shadow" and j["winamax_source_effective"] == "direct"
    assert "Socket" in j["winamax_repli"]
    assert j["etapes"]["pulsescore"]["winamax_repli"] == j["winamax_repli"]


def test_402_coupe_sans_journaliser_le_corps(monkeypatch):
    import json
    from cotes import pulsescore

    class Reponse:
        status_code = 402
        text = "secret-quota-ne-pas-journaliser"
        headers = {}

        def json(self):
            return {"message": self.text}

    appels = []

    class Session:
        headers = {}

        def get(self, *args, **kwargs):
            appels.append(args)
            return Reponse()

    monkeypatch.setattr(pulsescore.time, "sleep", lambda *a: None)
    client = pulsescore.Client("cle", pause=0, etat={})
    client.s = Session()
    assert client.get("pmu/soccer/events") is None
    assert client.get("pmu/tennis/events") is None
    assert appels and len(appels) == 1
    assert client.erreurs[0].endswith("HTTP 402")
    assert "secret" not in json.dumps(client.erreurs)
    assert pulsescore.indisponible(client.erreurs)
    assert pulsescore.indisponible(["winamax/soccer/events : collecte différée (quota/refus)"])
    assert not pulsescore.indisponible(["winamax/soccer/events : HTTP 500"])


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

    def pulse(*args, **kwargs):
        lent()
        return [], {}, {}

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
    monkeypatch.setattr(cycle.pulsescore, "collecter", pulse)
    cycle.collecter_prematch("cle", "complet", NOW, {"etapes": {}})
    assert len(starts) == 7
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
