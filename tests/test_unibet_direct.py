"""Unibet.fr via l'API LVS : fixtures, aucun appel réseau, jeton jamais journalisé."""
import json
from datetime import datetime, timezone

from cotes.direct import unibet

MAINTENANT = datetime(2026, 10, 18, 12, tzinfo=timezone.utc)
JETON = "JETON-TEST-NE-PAS-LOGUER"
HTML = (
    '<html><script id="serverApp-state">'
    + json.dumps({"HsToken": {"hsToken": JETON}, "Ept": {"ept": [
        {"code": "FOOT", "id": 240}, {"code": "FORM", "id": 1300},
    ]}})
    + "</script></html>"
)


class Reponse:
    def __init__(self, status=200, data=None, headers=None, text="SECRET_CORPS"):
        self.status_code = status
        self._data = data if data is not None else {}
        self.headers = headers or {}
        self.text = text

    def json(self):
        if isinstance(self._data, Exception):
            raise self._data
        return self._data


class Page:
    def __init__(self, html=HTML, status=200):
        self.html = html
        self.status = status
        self.urls = []

    def get(self, url, timeout=30, headers=None):
        self.urls.append(url)
        return Reponse(self.status, text=self.html)


class Session:
    def __init__(self, plan):
        self.plan = list(plan)
        self.urls = []
        self.jetons = []

    def get(self, url, timeout=30, headers=None):
        self.urls.append(url)
        self.jetons.append((headers or {}).get("X-LVS-HSToken"))
        statut, data, entetes = self.plan.pop(0)
        return Reponse(statut, data, entetes)


def _event(cle, home, away, start, pdesc="Ligue 1", etype="G"):
    return cle, {
        "a": home, "b": away, "start": start, "pdesc": pdesc, "eType": etype,
        "desc": f"{home} vs {away}", "path": {"League": pdesc, "Category": "France", "Sport": "Football"},
    }


def _issue(cle, parent, desc, prix, pos=1):
    return cle, {"parent": parent, "desc": desc, "price": prix, "pos": pos}


def test_fixture_traduit_les_marches_compares_et_renouvelle_le_jeton(monkeypatch):
    monkeypatch.setattr(unibet, "MARCHES", {"football": ((1, 100), (994001025, 100))})
    monkeypatch.setattr(unibet.time, "sleep", lambda s: None)
    e, ev = _event("e1", "Angers", "Marseille", "2610182000")
    hors, hors_ev = _event("e9", "Lyon", "Nice", "2610200500")
    boost, boost_ev = _event("e8", "Lens", "Lille", "2610181800", pdesc="Cotes Boostées L1")
    page = {
        e: ev, hors: hors_ev, boost: boost_ev,
        "e7": {"a": "Vainqueur", "b": None, "eType": "R", "start": "2610182000", "desc": "Vainqueur"},
        "m1": {"parent": e, "desc": "1 N 2", "style": "WIN_DRAW_WIN", "period": "90 Mins", "markettypeId": 1},
        "m9": {"parent": e, "desc": "Nombre de corners", "style": "TWO_OUTCOME_LONG", "period": "90 Mins"},
        **dict([
            _issue("o1", "m1", "Angers", "2,10", 1),
            _issue("o2", "m1", "N", "3,40", 2),
            _issue("o3", "m1", "Marseille", "3,20", 3),
            _issue("o4", "m9", "Plus 9,5", "1,80", 1),
            _issue("o5", "m9", "Moins 9,5", "1,90", 2),
        ]),
    }
    totaux = {
        e: ev,
        "m2": {"parent": e, "desc": "Plus / Moins 2.5 But(s)", "style": "PROPOSITION",
               "period": "90 Mins", "markettypeId": 994001025},
        **dict([
            _issue("o6", "m2", "Plus 2,5", "1,85", 1),
            _issue("o7", "m2", "Moins 2,5", "1,95", 2),
        ]),
    }
    session = Session([
        (200, {"items": page, "numberOfEvents": 1}, {"X-Lvs-Hstoken": "JETON-RENOUVELE"}),
        (200, {"items": totaux, "numberOfEvents": 1}, {}),
    ])
    lignes, meta = unibet.collecter(
        {"football"}, 36, session=session, page=Page(), pause=(0, 0), maintenant=MAINTENANT)
    assert meta["ok"] and meta["matchs"] == 1
    assert session.jetons == [JETON, "JETON-RENOUVELE"]
    assert JETON not in json.dumps(meta) and "JETON-RENOUVELE" not in json.dumps(meta)
    assert "SECRET_CORPS" not in json.dumps(meta)
    assert all(l["bookmaker"] == "unibet-fr" and l["source"] == "Unibet" for l in lignes)
    cles = {(l["domicile"], l["marche"], l["issue"], l["ligne"], l["cote"]) for l in lignes}
    assert ("Angers", "RESULTAT_1N2", "DOM", None, 2.1) in cles
    assert ("Angers", "RESULTAT_1N2", "NUL", None, 3.4) in cles
    assert ("Angers", "TOTAL", "PLUS", 2.5, 1.85) in cles
    assert not any(l["domicile"] == "Lyon" or l["domicile"] == "Lens" for l in lignes)
    assert not any("corner" in (l.get("libelle") or "").lower() for l in lignes)
    assert "marketTypeId=1" in session.urls[0] and "periodId=100" in session.urls[0]
    assert "formule" not in "".join(session.urls)


def test_handicap_double_chance_et_mi_temps():
    home, away = "Angers", "Marseille"
    handicap = unibet.marche_depuis("m", {
        "desc": "Face à Face Handicap [-0,5]", "style": "TWO_OUTCOME_LONG", "period": "90 Mins",
        "outcomes": [
            {"desc": "Angers [-0,5]", "price": "1,90"},
            {"desc": "Marseille [+0,5]", "price": "1,90"},
        ],
    }, home, away)
    assert handicap["canonicalMarket"] == "ASIAN_HANDICAP"
    assert {s["canonicalOutcome"]: s["line"] for s in handicap["selections"]} == {"HOME": -0.5, "AWAY": 0.5}
    europeen = unibet.marche_depuis("m", {
        "desc": "1 N 2 Handicap [-1]", "style": "WIN_DRAW_WIN_HANDICAP", "period": "90 Mins",
        "outcomes": [
            {"desc": "Angers [-1]", "price": "3,10"},
            {"desc": "N [-1]", "price": "3,40"},
            {"desc": "Marseille [+1]", "price": "2,05"},
        ],
    }, home, away)
    assert europeen["canonicalMarket"] == "EUROPEAN_HANDICAP"
    assert {s["canonicalOutcome"] for s in europeen["selections"]} == {"HOME", "DRAW", "AWAY"}
    double = unibet.marche_depuis("m", {
        "desc": "Double Chance", "style": "THREE_TEAMS_PRESENT", "period": "90 Mins",
        "outcomes": [
            {"desc": "Angers / N", "price": "1,25"},
            {"desc": "N / Marseille", "price": "1,40"},
            {"desc": "Angers / Marseille", "price": "1,30"},
        ],
    }, home, away)
    assert {s["canonicalOutcome"] for s in double["selections"]} == {"HOME_DRAW", "DRAW_AWAY", "HOME_AWAY"}
    mt = unibet.marche_depuis("m", {
        "desc": "Mi-temps / Fin de match", "style": "HALF_TIME_FULL_TIME", "period": "90 Mins",
        "outcomes": [
            {"desc": "Angers - Angers", "price": "4,50"},
            {"desc": "N - Marseille", "price": "6,00"},
        ],
    }, home, away)
    assert mt["selections"][0]["rawName"] == "Angers/Angers"
    demi = unibet.marche_depuis("m", {
        "desc": "1 N 2", "style": "WIN_DRAW_WIN", "period": "1ère Mi-temps",
        "outcomes": [
            {"desc": "Angers", "price": "2,80"},
            {"desc": "N", "price": "2,10"},
            {"desc": "Marseille", "price": "3,00"},
        ],
    }, home, away)
    assert "1ère Mi-temps" in demi["rawName"]
    cache = unibet.marche_depuis("m", {
        "desc": "1 N 2", "style": "WIN_DRAW_WIN", "period": "90 Mins",
        "outcomes": [
            {"desc": "Angers", "price": "2,00", "flags": ["hidden"]},
            {"desc": "N", "price": "3,00", "flags": ["suspended"]},
            {"desc": "Marseille", "price": "3,00"},
        ],
    }, home, away)
    assert cache is None
    assert unibet.marche_depuis("m", {
        "desc": "Buteur", "style": "TWO_TEAMS_PRESENT", "period": "90 Mins",
        "outcomes": [{"desc": "Oui", "price": "1,50"}, {"desc": "Non", "price": "2,40"}],
    }, home, away) is None


def test_erreur_http_ne_journalise_pas_le_corps(monkeypatch):
    monkeypatch.setattr(unibet, "MARCHES", {"football": ((1, 100),)})
    monkeypatch.setattr(unibet.time, "sleep", lambda s: None)
    session = Session([(500, {"secret": JETON}, {})] * 3)
    lignes, meta = unibet.collecter(
        {"football"}, 36, session=session, page=Page(), pause=(0, 0), maintenant=MAINTENANT)
    assert lignes == [] and meta["ok"] is False
    assert meta["erreurs"] == ["HTTP 500"]
    assert JETON not in json.dumps(meta) and "SECRET" not in json.dumps(meta)


def test_sports_vides_ne_contactent_pas_le_reseau():
    class Boom:
        def get(self, *args, **kwargs):
            raise AssertionError("réseau")

    lignes, meta = unibet.collecter(set(), session=Boom(), page=Boom(), maintenant=MAINTENANT)
    assert lignes == [] and meta == {"ok": True, "erreurs": [], "requetes": 0, "matchs": 0}


def test_jeton_absent(monkeypatch):
    monkeypatch.setattr(unibet.time, "sleep", lambda s: None)
    lignes, meta = unibet.collecter(
        {"football"}, 36, session=Session([]), page=Page("<html></html>"), maintenant=MAINTENANT)
    assert lignes == [] and meta["ok"] is False and meta["erreurs"] == ["jeton absent"]


def test_mode_par_defaut_shadow(monkeypatch):
    monkeypatch.delenv("SOURCE_UNIBET", raising=False)
    assert unibet.mode_source() == "shadow"
    monkeypatch.setenv("SOURCE_UNIBET", "DIRECT")
    assert unibet.mode_source() == "direct"
    monkeypatch.setenv("SOURCE_UNIBET", "ailleurs")
    assert unibet.mode_source() == "shadow"


def test_rapport_shadow_et_cotes_a_un_centime():
    base = {"bookmaker": "unibet-fr", "sport": "football", "domicile": "Lens", "exterieur": "Lille",
            "debut": "2026-10-18T20:00:00Z", "marche": "TOTAL", "periode": "MATCH", "issue": "PLUS"}
    pulse = [{**base, "match_id": "unibet-fr|ps", "ligne": 2.5, "cote": 1.85},
             {**base, "match_id": "unibet-fr|manque", "domicile": "Nice", "exterieur": "Rennes", "cote": 2.1}]
    direct = [{**base, "match_id": "unibet-fr|k", "ligne": 2.5, "cote": 2.10}]
    r = unibet.rapport(pulse, direct)
    assert r["matchs_pulsescore"] == 2 and r["matchs_communs"] == 1
    assert r["couverture"] == 0.5 and r["accord_cotes"] == 0 and r["pret_a_basculer"] is False
    parfait = unibet.rapport(pulse[:1], [{**direct[0], "cote": 1.85}])
    assert parfait["couverture"] == 1 and parfait["accord_cotes"] == 1 and parfait["pret_a_basculer"] is True


def test_shadow_bascule_si_pulsescore_refuse(monkeypatch):
    from datetime import datetime, timezone
    from scripts import cycle
    from tests.test_collecte_parallele import _sans_reseau, ligne

    def pulse(key, plan, *a, **kw):
        assert "unibet-fr" in plan
        return [ligne("football", "unibet-fr") | {"cote": 1.9}], {"unibet-fr": 1}, {
            "unibet-fr": ["unibet-fr/soccer/events : HTTP 401"]}

    def direct(sports, heures, **kwargs):
        return [ligne("football", "unibet-fr") | {"cote": 1.7, "match_id": "unibet-fr|lvs"}], {
            "ok": True, "erreurs": [], "requetes": 2, "matchs": 1}

    _sans_reseau(monkeypatch)
    monkeypatch.setattr(cycle.unibet_direct, "collecter", direct)
    monkeypatch.setattr(cycle.pinnacle, "collecter", lambda: [ligne("football")])
    monkeypatch.setattr(cycle.polymarket, "collecter", lambda *a: [])
    monkeypatch.setattr(cycle, "harmoniser_pinnacle", lambda x: x)
    monkeypatch.setattr(cycle.pulsescore, "collecter", pulse)
    j = {"etapes": {}}
    _, _, lignes, _ = cycle.collecter_prematch("cle", "complet", datetime(2026, 10, 17, tzinfo=timezone.utc), j)
    uni = [l for l in lignes if l["bookmaker"] == "unibet-fr"]
    assert uni and uni[0]["cote"] == 1.7 and uni[0]["match_id"] == "unibet-fr|lvs"
    assert j["unibet_source"] == "shadow" and j["unibet_source_effective"] == "direct"
    assert "Unibet" in j["unibet_repli"]
