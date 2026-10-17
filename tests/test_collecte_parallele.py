"""Ordonnancement réel : une référence lente ne bloque pas les cotes FR."""
from datetime import datetime, timezone
from threading import Event

from scripts import cycle

NOW = datetime(2026, 10, 17, tzinfo=timezone.utc)


def ligne(sport):
    return {"sport": sport, "debut": "2026-10-17T12:00:00Z"}


def test_kalshi_attend_pulse_et_sport_exclusif_est_couvert_sans_relecture(monkeypatch):
    pulse_lu, poly_lance = Event(), Event()
    plans = []

    def pin():
        assert poly_lance.wait(2), "les références doivent démarrer en parallèle"
        return [ligne("football")]

    def poly(*args):
        poly_lance.set()
        return []

    def kal(*args):
        assert pulse_lu.wait(2), "PulseScore ne doit pas attendre Kalshi"
        return [ligne("football"), ligne("basket")]

    def pulse(key, plan, horizon, pages, **kwargs):
        plans.append(plan)
        pulse_lu.set()
        return [{"lecture": len(plans)}], {"winamax": 1}, {}

    monkeypatch.setattr(cycle.pinnacle, "collecter", pin)
    monkeypatch.setattr(cycle.polymarket, "collecter", poly)
    monkeypatch.setattr(cycle.kalshi, "collecter", kal)
    monkeypatch.setattr(cycle, "harmoniser_pinnacle", lambda x: x)
    monkeypatch.setattr(cycle.pulsescore, "collecter", pulse)
    j = {"etapes": {}}
    pin, poly, kal, lignes, compte = cycle.collecter_prematch("test", "complet", NOW, j)
    assert [p["winamax"] for p in plans] == [["soccer"], ["basketball"]]
    assert plans[0]["orbitxch"] == ["soccer"] and plans[1]["orbitxch"] == []
    assert lignes == [{"lecture": 1}, {"lecture": 2}] and compte == {"winamax": 2}
    assert all(e["ok"] for e in j["etapes"].values())


def test_echec_reference_isole_et_aucun_appel_api_sans_cle(monkeypatch):
    def panne(*args):
        raise RuntimeError("source indisponible")
    monkeypatch.setattr(cycle.pinnacle, "collecter", panne)
    monkeypatch.setattr(cycle.polymarket, "collecter", lambda *a: [])
    monkeypatch.setattr(cycle.kalshi, "collecter", lambda *a: [ligne("basket")])
    monkeypatch.setattr(cycle.pulsescore, "collecter", lambda *a: (_ for _ in ()).throw(AssertionError("pas de clé")))
    j = {"etapes": {}}
    pin, poly, kal, lignes, compte = cycle.collecter_prematch(None, "complet", NOW, j)
    assert pin == [] and kal and not lignes and not compte
    assert j["etapes"]["pinnacle"]["ok"] is False
    assert j["etapes"]["pulsescore"]["ok"] is False


def test_arret_temoin_ne_change_pas_les_opportunites_calculées():
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


def test_radar_kalshi_estime_passe_ne_supprime_pas_sport_exclusif(monkeypatch):
    plans = []
    monkeypatch.setattr(cycle.pinnacle, 'collecter', lambda: [])
    monkeypatch.setattr(cycle.polymarket, 'collecter', lambda *a: [])
    monkeypatch.setattr(cycle.kalshi, 'collecter', lambda *a: [
        {**ligne('basket'), 'debut': '2026-10-16T22:00:00Z', 'debut_approximatif': True}])
    def pulse(key, plan, *a, **kw):
        plans.append(plan)
        return [], {}, {}
    monkeypatch.setattr(cycle.pulsescore, 'collecter', pulse)
    monkeypatch.setattr(cycle.kalshi, 'ERREURS', ['HTTP 503'])
    j = {'etapes': {}}
    cycle.collecter_prematch('test', 'complet', NOW, j)
    assert plans[0]['winamax'] == ['basketball']
    assert j['etapes']['kalshi']['degrade']
    assert j['etapes']['kalshi']['erreurs'] == ['HTTP 503']
