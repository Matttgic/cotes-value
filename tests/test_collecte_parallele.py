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
    monkeypatch.delenv("SOURCE_PMU", raising=False)

    def dire(*args, **kwargs):
        if direct:
            return direct(*args, **kwargs)
        return [], {"ok": True, "erreurs": [], "requetes": 0, "matchs": 0}

    monkeypatch.setattr(cycle.pmu_direct, "collecter", dire)
    monkeypatch.setattr(cycle.olybet_direct, "collecter",
                        lambda *a, **k: ([], {"ok": True, "erreurs": [], "requetes": 0, "matchs": 0}))
    monkeypatch.delenv("SOURCE_OLYBET", raising=False)


def test_shadow_garde_pulsescore_et_ne_relit_pas_un_complement(monkeypatch):
    plans = []
    appels_direct = []

    def pin():
        return [ligne("football"), ligne("basket")]

    def pulse(key, plan, horizon, pages, **kwargs):
        plans.append(plan)
        return [ligne("football", "pmu")], {"pmu": 1}, {}

    def direct(sports, heures):
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

    def direct(sports, heures):
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

    def direct(sports, heures):
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

    def direct(sports, heures):
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


def test_arret_temoin_ne_change_pas_les_opportunites_calculees():
    from cotes.comparaison import comparer, BRUT
    base = {"sport": "football", "ligue": "L", "domicile": "Lens", "exterieur": "Lille",
            "debut": "2030-01-01T20:00:00Z", "collecte": "2030-01-01T19:00:00Z", "marche": "TOTAL",
            "periode": "MATCH", "ligne": 2.5, "issue": "PLUS", "joueur": None}
    fr = [{**base, "source": "betclic", "match_id": "b1", "cote": 2.2}]
    refs = {"Pinnacle": [{**base, "source": "pinnacle", "match_id": "p1", "cote": 1.95, "proba_juste": 0.5}]}
    avant = comparer(fr, refs)
    apres = comparer(fr, refs, temoin_brut=False)
    assert any(o["reference"] == BRUT for o in avant)
    assert apres == [o for o in avant if o["reference"] != BRUT]
