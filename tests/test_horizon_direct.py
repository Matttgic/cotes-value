"""Horizon 36 h : cache des matchs lointains, rotation, cycle."""
import json
from datetime import datetime, timedelta, timezone

from cotes.direct import betclic, pmu, unibet
from cotes.direct.horizon import fusionner, fusionner_marches, tranche

MAINTENANT = datetime(2026, 10, 18, 12, tzinfo=timezone.utc)


def _iso(heures):
    return (MAINTENANT + timedelta(hours=heures)).isoformat()


def test_fusion_remplace_garde_et_oublie():
    ancienne = [
        {"match_id": "pmu|1", "debut": _iso(2), "collecte": _iso(-1), "cote": 1.5},
        {"match_id": "pmu|2", "debut": _iso(20), "collecte": _iso(-1), "cote": 2.0},
        {"match_id": "pmu|3", "debut": _iso(-1), "collecte": _iso(-1), "cote": 3.0},
        {"match_id": "pmu|4", "debut": _iso(20), "collecte": _iso(-4), "cote": 4.0},
        {"match_id": "pmu|5", "debut": _iso(10), "cote": 5.0},
    ]
    neuves = [{"match_id": "pmu|1", "debut": _iso(2), "collecte": MAINTENANT.isoformat(), "cote": 1.8}]
    fusion = fusionner(ancienne, neuves, MAINTENANT, 36)
    par_id = {l["match_id"]: l["cote"] for l in fusion}
    assert par_id == {"pmu|1": 1.8, "pmu|2": 2.0}
    pris, curseur = tranche(["a", "b", "c"], 2, 2)
    assert pris == ["c", "a"] and curseur == 1


def test_pmu_reserve_tourne_les_competitions(monkeypatch):
    from tests.test_pmu_direct import Session, _event, _offre_simple
    monkeypatch.setattr(pmu, "_LOIN_COMP", 1)
    monkeypatch.setattr(pmu.time, "sleep", lambda s: None)
    proche = (MAINTENANT + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    loin_a = (MAINTENANT + timedelta(hours=20)).strftime("%Y-%m-%dT%H:%M:%SZ")
    loin_b = (MAINTENANT + timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    liste = {"events": [_event(1, "Lens", "Lille", proche)]}
    groupe = {"group": {"termKey": "football", "groups": [
        {"termKey": "france", "groups": [
            {"sport": "FOOTBALL", "termKey": "ligue_1", "eventCount": 1},
            {"sport": "FOOTBALL", "termKey": "ligue_2", "eventCount": 1},
        ]},
    ]}}
    feuille_a = {"events": [_event(2, "Brest", "Nice", loin_a)]}
    feuille_b = {"events": [_event(3, "Monaco", "Rennes", loin_b)]}
    offres_a = {"betOffers": [_offre_simple(1), _offre_simple(2)]}
    offres_b = {"betOffers": [_offre_simple(1), _offre_simple(3)]}
    session = Session([
        (200, liste), (200, groupe), (200, feuille_a), (200, offres_a),
        (200, liste), (200, feuille_b), (200, offres_b),
    ])
    lignes, meta = pmu.collecter(
        {"football"}, 36, session=session, pause=(0, 0), maintenant=MAINTENANT, reserve={})
    assert ("Lens", "Lille") in {(l["domicile"], l["exterieur"]) for l in lignes}
    assert ("Brest", "Nice") in {(l["domicile"], l["exterieur"]) for l in lignes}
    assert any("group.json" in u for u in session.urls)
    assert any("ligue_1" in u for u in session.urls)
    reserve = meta["reserve"]
    avant = len(session.urls)
    lignes, meta = pmu.collecter(
        {"football"}, 36, session=session, pause=(0, 0), maintenant=MAINTENANT, reserve=reserve)
    suite = session.urls[avant:]
    noms = {(l["domicile"], l["exterieur"]) for l in lignes}
    assert ("Lens", "Lille") in noms and ("Brest", "Nice") in noms and ("Monaco", "Rennes") in noms
    assert any("ligue_2" in u for u in suite)
    assert not any("group.json" in u for u in suite)


def test_betclic_reserve_page_lointaine_et_cache():
    from tests.test_betclic_direct import _detail, _liste, _match, _sel
    pres = (MAINTENANT + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    loin = (MAINTENANT + timedelta(hours=20)).strftime("%Y-%m-%dT%H:%M:%SZ")

    class Session:
        def __init__(self, reponses):
            self._reponses = list(reponses)
            self.corps = []

        def post(self, url, data=None, headers=None, timeout=None, stream=None):
            self.corps.append(data)
            corps, status = self._reponses.pop(0)

            class Reponse:
                status_code = status

                def iter_content(self, _n=None):
                    yield corps

                def close(self):
                    pass

            return Reponse()

    def charge(offset):
        return betclic.trame_grpc(betclic._charge_liste("football", offset))

    detail_pres = _detail("Résultat du match (t. rég)", [
        _sel("Lens", 1.8), _sel("Nul", 3.4), _sel("Lille", 4.5)])
    detail_loin = _detail("Résultat du match (t. rég)", [
        _sel("Brest", 1.7), _sel("Nul", 3.6), _sel("Nice", 4.4)])
    passe = (MAINTENANT - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    remplissage = [_match(1000 + i, "A", "B", passe) for i in range(39)]
    page_pleine = _liste(_match(7, "Lens", "Lille", pres), *remplissage)
    session = Session([
        (page_pleine, 200),
        (_liste(_match(80, "Brest", "Nice", loin)), 200),
        (detail_pres, 200),
        (detail_loin, 200),
        (page_pleine, 200),
        (_liste(), 200),
    ])
    lignes, meta = betclic.collecter(
        {"football"}, 36, session=session, maintenant=MAINTENANT, reserve={})
    assert {l["domicile"] for l in lignes} == {"Lens", "Brest"}
    assert session.corps[0] == charge(0) and session.corps[1] == charge(40)
    lignes, meta = betclic.collecter(
        {"football"}, 36, session=session, maintenant=MAINTENANT, reserve=meta["reserve"])
    assert session.corps[4] == charge(0) and session.corps[5] == charge(40)
    assert {l["domicile"] for l in lignes} == {"Lens", "Brest"}
    assert len(session.corps) == 6


def test_unibet_reserve_page_lointaine_et_cache(monkeypatch):
    from tests.test_unibet_direct import Page, Session, _event
    monkeypatch.setattr(unibet, "MARCHES", {"football": ((1, 100), (1, 102))})
    monkeypatch.setattr(unibet.time, "sleep", lambda s: None)
    e, ev = _event("e9", "Lyon", "Nice", "2610191800")
    session = Session([
        (200, {"items": {e: ev}, "numberOfEvents": 400, "nextEventId": 42}, {}),
        (200, {"items": {}, "numberOfEvents": 400}, {}),
        (200, {"items": {}, "numberOfEvents": 0}, {}),          # marché secondaire (1, 102)
    ])
    cache = {
        "bookmaker": "unibet-fr", "match_id": "unibet-fr|cache", "sport": "football",
        "domicile": "Brest", "exterieur": "Nice", "debut": _iso(20),
        "collecte": MAINTENANT.isoformat(), "cote": 1.5,
    }
    lignes, meta = unibet.collecter(
        {"football"}, 36, session=session, page=Page(), pause=(0, 0),
        maintenant=MAINTENANT, reserve={"lignes": [cache]})
    assert any("nextEventId=42" in u for u in session.urls)
    assert not any("pageIndex=" in u for u in session.urls)
    assert any(l["match_id"] == "unibet-fr|cache" for l in lignes)
    assert any("periodId=102" in u for u in session.urls)
    assert meta["reserve"]["curseur"] == 0
    assert "JETON" not in json.dumps({k: v for k, v in meta.items() if k != "reserve"})


def test_cycle_enregistre_l_horizon(monkeypatch, tmp_path):
    from scripts import cycle
    from tests.test_collecte_parallele import ligne
    vus = {}

    def capter(nom):
        def f(*args, **kwargs):
            vus[nom] = (args, kwargs)
            return [], {"ok": True, "erreurs": [], "requetes": 0, "matchs": 0,
                        "reserve": {"curseur": 3, "lignes": [{"match_id": nom}]}}
        return f

    monkeypatch.delenv("SOURCE_OLYBET", raising=False)
    monkeypatch.setattr(cycle.pmu_direct, "collecter", capter("pmu"))
    monkeypatch.setattr(cycle.unibet_direct, "collecter", capter("unibet"))
    monkeypatch.setattr(cycle.betclic_direct, "collecter", capter("betclic"))
    monkeypatch.setattr(cycle.winamax_direct, "collecter",
                        lambda *a, **k: ([], {"ok": True, "erreurs": [], "requetes": 0, "matchs": 0}))
    monkeypatch.setattr(cycle.olybet_direct, "collecter",
                        lambda *a, **k: ([], {"ok": True, "erreurs": [], "requetes": 0, "matchs": 0}))
    monkeypatch.setattr(cycle.pinnacle, "collecter", lambda: [ligne("football")])
    monkeypatch.setattr(cycle.polymarket, "collecter", lambda *a: [])
    monkeypatch.setattr(cycle, "harmoniser_pinnacle", lambda x: x)
    maintenant = datetime(2026, 10, 17, tzinfo=timezone.utc)
    cycle.collecter_prematch("complet", maintenant, {"etapes": {}}, donnees=tmp_path)
    assert vus["pmu"][0][1] == 36 and vus["pmu"][1]["reserve"] == {} and vus["pmu"][1]["concurrence"] == 2
    assert vus["unibet"][0][1] == 36 and vus["unibet"][1]["reserve"] == {}
    assert vus["betclic"][0][1] == 36 and vus["betclic"][1]["reserve"] == {}
    sauve = json.loads((tmp_path / "horizon_direct.json").read_text())
    assert sauve["pmu"]["curseur"] == 3 and sauve["unibet"]["lignes"][0]["match_id"] == "unibet"
    cycle.collecter_prematch("complet", maintenant, {"etapes": {}}, donnees=tmp_path)
    assert vus["pmu"][1]["reserve"]["curseur"] == 3
    assert vus["betclic"][1]["reserve"]["lignes"][0]["match_id"] == "betclic"


def test_fusion_par_marche_garde_les_marches_non_relus_quinze_minutes():
    def l(mid, marche, cote, lu_min=-5, periode="MATCH"):
        return {"match_id": mid, "marche": marche, "periode": periode, "debut": _iso(3),
                "collecte": (MAINTENANT + timedelta(minutes=lu_min)).isoformat(), "cote": cote}
    anciennes = [l("u|1", "RESULTAT_1N2", 2.0), l("u|1", "TOTAL", 1.9), l("u|1", "HANDICAP", 1.8, lu_min=-20),
                 l("u|1", "TOTAL", 1.7, periode="MT1")]
    neuves = [l("u|1", "RESULTAT_1N2", 2.1, lu_min=0)]
    fusion = fusionner_marches(anciennes, neuves, MAINTENANT, 36)
    assert sorted((x["marche"], x["periode"], x["cote"]) for x in fusion) == [
        ("RESULTAT_1N2", "MATCH", 2.1), ("TOTAL", "MATCH", 1.9), ("TOTAL", "MT1", 1.7)]


def test_unibet_reserve_tourne_sur_les_marches_secondaires(monkeypatch):
    from tests.test_unibet_direct import Page, Session
    monkeypatch.setattr(unibet, "MARCHES", {"football": tuple((t, 100) for t in range(1, 6))})
    monkeypatch.setattr(unibet, "_SECONDAIRES_PAR_CYCLE", 3)
    monkeypatch.setattr(unibet.time, "sleep", lambda s: None)
    vide = (200, {"items": {}, "numberOfEvents": 0}, {})
    lus = []
    curseur = 0
    for _ in range(2):
        session = Session([vide] * 4)
        _, meta = unibet.collecter({"football"}, 36, session=session, page=Page(), pause=(0, 0),
                                   maintenant=MAINTENANT, reserve={"lignes": [], "curseur": curseur})
        lus.append([u.split("marketTypeId=")[1].split("&")[0] for u in session.urls])
        curseur = meta["reserve"]["curseur"]
    # marché principal (1) à chaque cycle, puis 3 secondaires parmi 2..5, en tournant
    assert lus == [["1", "2", "3", "4"], ["1", "5", "2", "3"]] and curseur == 2
