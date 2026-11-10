"""Props FanDuel : lecture, marge, rapprochement Pinnacle. Aucun appel réseau."""
import json
from datetime import datetime, timezone

from cotes.direct import fanduel as F
from cotes.props import comparer_fanduel
from cotes.props_papier import STRATEGIES, bilan

MAINTENANT = datetime(2026, 11, 10, 18, tzinfo=timezone.utc)
FUTUR = "2026-11-11T00:40:00.000Z"
PASSE = "2026-11-10T12:00:00.000Z"


class Reponse:
    def __init__(self, status, texte):
        self.status_code = status
        self.text = texte


def _runner(nom, cote, ligne):
    return {"runnerName": nom, "handicap": ligne,
            "winRunnerOdds": {"decimalDisplayOdds": {"decimalOdds": cote}}}


def _marche(mid, titre, cote_plus, cote_moins, ligne, americaine=False):
    if americaine:
        plus = {"runnerName": "Over", "handicap": ligne,
                "winRunnerOdds": {"americanDisplayOdds": {"americanOdds": -110}}}
        moins = {"runnerName": "Under", "handicap": ligne,
                 "winRunnerOdds": {"americanDisplayOdds": {"americanOdds": -110}}}
    else:
        plus, moins = _runner("Over", cote_plus, ligne), _runner("Under", cote_moins, ligne)
    return mid, {"marketId": mid, "marketName": titre, "marketType": "PLAYER",
                 "runners": [plus, moins]}


def _page(*marches):
    return {"layout": {"tabs": {"26": {"id": "26"}}},
            "attachments": {"markets": dict(marches)}}


def _liste(*events):
    return {"attachments": {"events": {str(e["eventId"]): e for e in events}}}


def _event(eid, nom, debut, en_jeu=False):
    return {"eventId": eid, "name": nom, "openDate": debut, "inPlay": en_jeu}


class Session:
    def __init__(self, routes):
        self.routes = routes
        self.urls = []

    def get(self, url, timeout=20):
        self.urls.append(url)
        for cle, val in self.routes:
            if cle in url:
                if isinstance(val, Exception):
                    raise val
                return val
        return Reponse(404, "")


def test_match_futur_seulement_et_props_sans_periode():
    doc = _liste(
        _event(1, "Boston Celtics @ Los Angeles Lakers", FUTUR),
        _event(2, "Milwaukee Bucks @ New York Knicks", PASSE),
        _event(3, "Oklahoma City Thunder (MARINE) @ New York Knicks (OREZ)", FUTUR),
        _event(4, "NBA Championship Winner", FUTUR, en_jeu=True),
    )
    gardes = F.evenements_liste(doc, MAINTENANT)
    assert [e["eventId"] for e in gardes] == [1]
    assert gardes[0]["domicile"] == "Los Angeles Lakers"
    assert gardes[0]["exterieur"] == "Boston Celtics"
    props, ignores = F.props_de(_page(
        _marche("p", "LeBron James - Points", 1.87, 1.95, 25.5),
        _marche("q", "Josh Hart - 1st Qtr Points", 1.9, 1.9, 2.5),
        _marche("s", "Spread", 1.9, 1.9, -3.5),
        _marche("t", "Auston Matthews - Goals", 2.1, 1.7, 0.5),
        _marche("a", "Stephen Curry - Threes", 1.91, 1.91, 3.5, americaine=True),
    ))
    assert ignores == 1
    assert {(p["joueur"], p["stat"], p["issue"]) for p in props} == {
        ("LeBron James", "Points", "PLUS"), ("LeBron James", "Points", "MOINS"),
        ("Auston Matthews", "Goals", "PLUS"), ("Auston Matthews", "Goals", "MOINS"),
        ("Stephen Curry", "ThreePoints", "PLUS"), ("Stephen Curry", "ThreePoints", "MOINS"),
    }
    lebron = next(p for p in props if p["joueur"] == "LeBron James" and p["issue"] == "PLUS")
    assert lebron["proba_juste"] > 0.5
    assert abs(sum(p["proba_juste"] for p in props if p["joueur"] == "LeBron James") - 1) < 1e-6
    curry = next(p for p in props if p["stat"] == "ThreePoints" and p["issue"] == "PLUS")
    assert abs(curry["proba_juste"] - 0.5) < 1e-6
    assert curry["cote"] > 1


def test_collecte_onglets_et_pannes_sans_fuite():
    page = _page(_marche("p", "LeBron James - Points", 1.87, 1.95, 25.5))
    vide = _page()
    session = Session([
        ("customPageId=nba", Reponse(200, json.dumps(_liste(
            _event(9, "Boston Celtics @ Los Angeles Lakers", FUTUR))))),
        ("customPageId=nhl", Reponse(200, json.dumps(_liste()))),
        ("tab=player-points", Reponse(200, json.dumps(page))),
        ("tab=popular", Reponse(200, json.dumps(vide))),
        ("tab=player-rebounds", Reponse(403, "")),
        ("tab=player-assists", Reponse(200, " ")),
        ("tab=player-threes", Reponse(200, "<html>")),
    ])
    lignes, meta = F.collecter({"basket", "hockey"}, 36, session=session, maintenant=MAINTENANT,
                               environ={"SOURCE_FANDUEL": "direct"})
    assert meta["ok"] is True and meta["props"] == 2
    assert {(l["marche"], l["issue"], l["joueur"]) for l in lignes} == {
        ("JOUEUR:Points", "PLUS", "LeBron James"), ("JOUEUR:Points", "MOINS", "LeBron James")}
    assert all(l["source"] == "fanduel" and l["ligue"] == "NBA" for l in lignes)
    assert not any("403" in a or "vide" in a or "illisible" in a for a in meta["avertissements"])
    assert F.AK not in json.dumps(meta)

    refuse = Session([
        ("customPageId=nba", Reponse(403, "secret-cookie=abc")),
        ("customPageId=nhl", Reponse(200, "")),
    ])
    lignes, meta = F.collecter(session=refuse, maintenant=MAINTENANT, environ={"SOURCE_FANDUEL": "direct"})
    assert lignes == [] and meta["ok"] is False
    assert any("403" in a for a in meta["avertissements"])
    assert "secret-cookie" not in json.dumps(meta) and F.AK not in json.dumps(meta)

    delai = Session([("customPageId=", TimeoutError())])
    _, meta = F.collecter(session=delai, maintenant=MAINTENANT, environ={"SOURCE_FANDUEL": "direct"})
    assert meta["avertissements"][0].endswith("delai")
    assert F.AK not in json.dumps(meta)


def test_source_coupee_ne_fait_aucun_appel():
    session = Session([("customPageId=", Reponse(200, "{}"))])
    lignes, meta = F.collecter(session=session, maintenant=MAINTENANT)
    assert lignes == [] and meta["mode"] == "off" and session.urls == []
    assert F.mode({}) == "off"
    assert F.mode({"SOURCE_FANDUEL": "direct"}) == "direct"
    assert F.mode({"SOURCE_FANDUEL": "nimporte"}) == "off"


def test_rapprochement_compte_sans_nommer():
    fd = [
        {"source": "fanduel", "sport": "basket", "marche": "JOUEUR:Points", "periode": "MATCH",
         "ligne": 25.5, "issue": "PLUS", "joueur": "LeBron James", "proba_juste": 0.54,
         "domicile": "Los Angeles Lakers", "exterieur": "Boston Celtics", "debut": FUTUR},
        {"source": "fanduel", "sport": "basket", "marche": "JOUEUR:Points", "periode": "MATCH",
         "ligne": 18.5, "issue": "PLUS", "joueur": "Inconnu Personne", "proba_juste": 0.51,
         "domicile": "Los Angeles Lakers", "exterieur": "Boston Celtics", "debut": FUTUR},
    ]
    pin = [
        {"source": "pinnacle", "sport": "basket", "marche": "JOUEUR:Points", "periode": "MATCH",
         "ligne": 25.5, "issue": "PLUS", "joueur": "L. James", "proba_juste": 0.52,
         "domicile": "Los Angeles Lakers", "exterieur": "Boston Celtics", "debut": "2026-11-11T00:40:00+00:00"},
        {"source": "pinnacle", "sport": "basket", "marche": "JOUEUR:Rebounds", "periode": "MATCH",
         "ligne": 7.5, "issue": "PLUS", "joueur": "Anthony Davis", "proba_juste": 0.5,
         "domicile": "Los Angeles Lakers", "exterieur": "Boston Celtics", "debut": "2026-11-11T00:40:00+00:00"},
    ]
    bilan_fd = comparer_fanduel(fd, pin)
    assert bilan_fd["rapproches"] == 1 and bilan_fd["non_rapproches"] == 1
    assert bilan_fd["ecart_proba_moyen"] == round(0.54 - 0.52, 5)
    assert bilan_fd["accord"] == 1
    assert bilan_fd["reference_seule"] is True
    texte = json.dumps(bilan_fd)
    assert "LeBron" not in texte and "Inconnu" not in texte and "James" not in texte
    doc = bilan({"paris": [], "fanduel": bilan_fd})
    assert doc["fanduel"]["rapproches"] == 1
    fd_strat = next(s for s in STRATEGIES if s["cle"] == "props_fanduel")
    assert fd_strat["actif"] is False and fd_strat["papier"] is True
    assert all(s["actif"] is False for s in doc["strategies"])


def test_cycle_garde_fanduel_hors_des_paris(monkeypatch):
    from scripts import cycle

    def vide(*a, **k):
        return [], {"ok": True, "erreurs": [], "requetes": 0, "matchs": 0}

    for module in (cycle.pmu_direct, cycle.winamax_direct, cycle.unibet_direct,
                   cycle.betclic_direct, cycle.olybet_direct, cycle.netbet_direct):
        monkeypatch.setattr(module, "collecter", vide)
    monkeypatch.setattr(cycle.polymarket, "collecter", lambda *a, **k: [])
    monkeypatch.setattr(cycle, "harmoniser_pinnacle", lambda x: x)
    pin = [{"source": "pinnacle", "sport": "basket", "marche": "JOUEUR:Points", "periode": "MATCH",
            "ligne": 25.5, "issue": "PLUS", "joueur": "L. James", "proba_juste": 0.52, "cote": 1.92,
            "domicile": "Los Angeles Lakers", "exterieur": "Boston Celtics",
            "debut": "2026-11-11T00:40:00+00:00", "collecte": "2026-11-10T18:00:00+00:00"}]
    fd = [{**pin[0], "source": "fanduel", "bookmaker": "fanduel", "joueur": "LeBron James",
           "proba_juste": 0.48, "match_id": "fanduel|9"}]
    monkeypatch.setattr(cycle.pinnacle, "collecter", lambda: pin)
    monkeypatch.setattr(cycle.fanduel_direct, "collecter",
                        lambda *a, **k: (fd, {"ok": True, "erreurs": [], "avertissements": [],
                                              "requetes": 3, "matchs": 1, "props": 1, "ignores": 0}))
    monkeypatch.setenv("SOURCE_FANDUEL", "direct")
    monkeypatch.delenv("SOURCE_OLYBET", raising=False)
    monkeypatch.delenv("SOURCE_NETBET", raising=False)
    journal = {"etapes": {}}
    _pin, _poly, francais = cycle.collecter_prematch("complet", MAINTENANT, journal)
    assert francais == []
    assert journal["props_fanduel"]["rapproches"] == 1
    assert journal["props_fanduel"]["accord"] == 0
    assert "LeBron" not in json.dumps(journal["props_fanduel"])
    assert journal["fanduel"]["props"] == 1
