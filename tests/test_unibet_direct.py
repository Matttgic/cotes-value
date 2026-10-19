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


def _collecte(items, heures=36, echeance=None, radar=None, plan=None):
    if plan is None:
        plan = [(200, {"items": items, "numberOfEvents": 1}, {})]
    session = Session(plan)
    lignes, meta = unibet.collecter(
        {"football"}, heures, session=session, page=Page(), pause=(0, 0),
        maintenant=MAINTENANT, echeance=echeance, radar=radar)
    return session, lignes, meta


def test_horizon_court_garde_la_periode_principale(monkeypatch):
    monkeypatch.setattr(unibet, "MARCHES", {"football": ((1, 100), (1, 102), (605, 100))})
    monkeypatch.setattr(unibet.time, "sleep", lambda s: None)
    session, _, meta = _collecte({}, heures=6, plan=[(200, {"items": {}, "numberOfEvents": 0}, {})] * 3)
    assert meta["ok"] is False or meta["requetes"] == 2
    periodes = " ".join(session.urls)
    assert "periodId=102" not in periodes
    assert session.urls[0].count("marketTypeId=1") == 1
    assert any("marketTypeId=605" in u for u in session.urls)
    assert len(session.urls) == 2


def test_radar_ignore_un_sport_sans_match(monkeypatch):
    monkeypatch.setattr(unibet, "MARCHES", {"football": ((1, 100), (605, 100))})
    monkeypatch.setattr(unibet.time, "sleep", lambda s: None)
    e, ev = _event("e1", "Angers", "Marseille", "2610182000")
    session, lignes, _ = _collecte(
        {e: ev}, radar=[{"sport": "football", "domicile": "Nice", "exterieur": "Rennes",
                         "debut": "2026-10-18T20:00:00Z"}])
    assert len(session.urls) == 1 and "marketTypeId=605" not in session.urls[0]
    assert lignes == []
    vide, _, _ = _collecte({}, radar=[{"sport": "tennis", "domicile": "Sinner", "exterieur": "Alcaraz",
                                       "debut": "2026-10-18T20:00:00Z"}])
    assert vide.urls == []


def test_radar_poursuit_les_marches_du_match(monkeypatch):
    monkeypatch.setattr(unibet, "MARCHES", {"football": ((1, 100), (605, 100))})
    monkeypatch.setattr(unibet.time, "sleep", lambda s: None)
    e, ev = _event("e1", "Angers", "Marseille", "2610182000")
    session, _, _ = _collecte(
        {e: ev}, radar=[{"sport": "football", "domicile": "Angers", "exterieur": "Marseille",
                         "debut": "2026-10-18T20:00:00Z"}],
        plan=[(200, {"items": {e: ev}, "numberOfEvents": 1}, {})] * 2)
    assert len(session.urls) == 2
    assert "marketTypeId=605" in session.urls[1]


def test_budget_rend_les_cotes_deja_lues(monkeypatch):
    monkeypatch.setattr(unibet, "MARCHES", {"football": ((1, 100), (605, 100))})
    monkeypatch.setattr(unibet.time, "sleep", lambda s: None)
    e, ev = _event("e1", "Angers", "Marseille", "2610182000")
    offre = {
        e: ev,
        "m1": {"parent": e, "desc": "1 N 2", "style": "WIN_DRAW_WIN", "period": "90 Mins"},
        **dict([
            _issue("o1", "m1", "Angers", "2,10"),
            _issue("o2", "m1", "N", "3,40"),
            _issue("o3", "m1", "Marseille", "3,20"),
        ]),
    }

    class Budget:
        def __init__(self):
            self.n = 0

        def ok(self):
            return self.n < 1

        def reste(self):
            return 10.0 if self.ok() else 0.0

        def timeout(self, plafond):
            return 4

    budget = Budget()

    class UneSession(Session):
        def get(self, url, timeout=30, headers=None):
            budget.n += 1
            return super().get(url, timeout=timeout, headers=headers)

    session = UneSession([(200, {"items": offre, "numberOfEvents": 1}, {})] * 4)
    lignes, meta = unibet.collecter(
        {"football"}, 36, session=session, page=Page(), pause=(0, 0),
        maintenant=MAINTENANT, echeance=budget)
    assert len(session.urls) == 1
    assert meta["matchs"] == 1 and any(l["cote"] == 2.1 for l in lignes)
    assert "budget" in meta["erreurs"]
    assert JETON not in json.dumps(meta)


