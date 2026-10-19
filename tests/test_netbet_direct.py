"""NetBet.fr : état Nuxt, pas le DOM. PulseScore n'a pas ce site."""
import json
from datetime import datetime, timezone

from cotes.delai import Echeance
from cotes.direct import netbet

NOW = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)
JETON_FICTIF = "SECRET-COOKIE-NE-PAS-JOURNALISER"


def _script(events: list, liens: list | None = None) -> str:
    corps = {
        "state": {
            "headersCookie": "a",
            "UFWSClient": {"components": {
                "sport_page_featured": {"data": {"last_minutes": {"events": events}}},
                "sport_page_all": {"data": {
                    "topCompetitions": {"links": liens or []},
                    "azCategories": {"categories": []},
                }},
            }},
        }
    }
    # Littéraux seulement : void 0, échappement, nombre « .1 », Array(0).
    return (
        "window.__NUXT__=(function(a,b){fp={csrf_token:a};return "
        + json.dumps(corps).replace('"a"', "a")
        + '}("' + JETON_FICTIF + '","Saint-\\u00c9tienne",.1,Array(0)));'
    )


def _event(eid, state, home, away, markets, start="2026-10-18T20:45:00.000+02:00"):
    return {
        "id": eid, "state": state, "start": start, "competitionLabel": "Ligue 1",
        "actors": [{"label": home, "type": "home"}, {"label": away, "type": "away"}],
        "markets": markets,
    }


def _offre(style, libelle, selections):
    return {"selection_order_type": style, "order": style,
            "bets": [{"label": libelle, "selections": selections}]}


MARCHES = [
    _offre("1x2", "Qui va gagner le match ?", [
        {"label": "Lyon", "odds": 1.81}, {"label": "Nul", "odds": 3.7}, {"label": "Nice", "odds": 3.75}]),
    _offre("over_under", "Plus ou moins de 2,5 buts ?", [
        {"label": "Plus de 2,5", "odds": 1.55}, {"label": "Moins de 2,5", "odds": 1.97}]),
    _offre("yes_no", "Les 2 équipes marquent ?", [
        {"label": "Oui", "odds": 1.51}, {"label": "Non", "odds": 2.05}]),
    _offre("double_chance", "Double chance", [
        {"label": "Lyon ou Nul", "odds": 1.09}, {"label": "Nul ou Nice", "odds": 1.68},
        {"label": "Lyon ou Nice", "odds": 1.11}]),
    _offre("handicap_2ways", "Handicap", [
        {"label": "(-0.5) Lyon", "odds": 1.65}, {"label": "(+0.5) Nice", "odds": 1.83}]),
    _offre("1x2", "Cote boostée garantie", [
        {"label": "Lyon", "odds": 9.99}, {"label": "Nice", "odds": 9.99}]),
    _offre("over_under", "Nombre de corners", [
        {"label": "Plus de 9,5", "odds": 1.8}, {"label": "Moins de 9,5", "odds": 1.9}]),
]


class _Reponse:
    def __init__(self, code, texte):
        self.status_code = code
        self.text = texte


class _Session:
    def __init__(self, pages, echeance=None):
        self.pages = list(pages)
        self.echeance = echeance
        self.urls = []

    def get(self, url, timeout=None, headers=None):
        self.urls.append(url)
        if self.echeance is not None:
            self.echeance.fini = True
        code, texte = self.pages.pop(0)
        return _Reponse(code, texte)


def _html(events, liens=None):
    return "<script>" + _script(events, liens) + "</script>"


def test_etat_nuxt_lit_les_cotes_et_ignore_le_live():
    brut = _event(1, "pm", "Lyon", "Nice", MARCHES)
    direct = _event(2, "live", "A", "B", MARCHES)
    etat = netbet.etat_nuxt(_html([brut, direct]))
    ev = netbet.evenements_de(etat, "football")
    assert [e["home"] for e in ev] == ["Lyon"]
    canons = {m["canonicalMarket"] for m in ev[0]["markets"]}
    assert canons == {"MATCH_RESULT", "OVER_UNDER", "BOTH_TEAMS_TO_SCORE",
                      "DOUBLE_CHANCE", "ASIAN_HANDICAP"}
    assert "SECRET" not in json.dumps(ev)


def test_echappements_et_array_vide():
    etat = netbet.evaluer(
        '(function(a,b,c,d){return {nom:b,vide:c,n:d,rien:a}})'
        '(void 0,"Saint-\\u00c9tienne",Array(0),.1);')
    assert etat["nom"] == "Saint-Étienne" and etat["vide"] == [] and etat["n"] == 0.1
    assert etat["rien"] is None


def test_collecte_traduit_et_laisse_le_jeton_dehors():
    html = _html([_event(7, "pm", "Lyon", "Nice", MARCHES)])
    session = _Session([(200, html)])
    lignes, meta = netbet.collecter({"football"}, heures=36, session=session, pause=(0, 0),
                                     maintenant=NOW)
    assert meta["ok"] is True and meta["matchs"] == 1 and meta["requetes"] == 1
    assert {l["bookmaker"] for l in lignes} == {"netbet"}
    dom = next(l for l in lignes if l["marche"] == "RESULTAT_1N2" and l["issue"] == "DOM")
    assert dom["cote"] == 1.81 and dom["periode"] == "MATCH" and dom["domicile"] == "Lyon"
    assert any(l["marche"] == "HANDICAP" and l["issue"] == "DOM" and l["ligne"] == -0.5 for l in lignes)
    assert all(l["cote"] != 9.99 for l in lignes)
    assert "corners" not in json.dumps([l["libelle"] for l in lignes]).lower()
    assert JETON_FICTIF not in json.dumps({"lignes": lignes, "meta": meta})


def test_budget_rend_les_cotes_deja_lues():
    class Ech:
        def __init__(self):
            self.fini = False

        def ok(self):
            return not self.fini

        def reste(self):
            return 0.0 if self.fini else 30.0

    ech = Ech()
    html = _html([_event(7, "pm", "Lyon", "Nice", MARCHES)],
                 [{"url": "/football/france/ligue-1", "events": 4}])
    session = _Session([(200, html), (200, html)], ech)
    lignes, meta = netbet.collecter({"football"}, session=session, pause=(0, 0),
                                     maintenant=NOW, echeance=ech)
    assert session.urls == ["https://www.netbet.fr/football"]
    assert meta["matchs"] == 1 and lignes
    assert "budget" in meta["erreurs"] and meta["ok"] is True
    assert JETON_FICTIF not in json.dumps(meta)


def test_echeance_deja_depassee_n_appelle_pas():
    lignes, meta = netbet.collecter({"football"}, session=_Session([]), pause=(0, 0),
                                     maintenant=NOW, echeance=Echeance(0))
    assert lignes == [] and meta["requetes"] == 0
    assert meta["ok"] is False and meta["erreurs"] == ["budget"]


def test_429_arrete_sans_reprendre():
    sport = _html([_event(7, "pm", "Lyon", "Nice", MARCHES)],
                  [{"url": "/football/france/ligue-1", "events": 2},
                   {"url": "/football/angleterre/premier-league", "events": 1}])
    session = _Session([(200, sport), (429, "trop")])
    lignes, meta = netbet.collecter({"football"}, session=session, pause=(0, 0), maintenant=NOW)
    assert len(session.urls) == 2 and meta["matchs"] == 1
    assert "HTTP 429" in meta["erreurs"]


def test_panne_reseau_ne_propage_pas_le_message():
    class Panne:
        def get(self, *args, **kwargs):
            raise OSError(JETON_FICTIF)

    lignes, meta = netbet.collecter({"football"}, session=Panne(), pause=(0, 0), maintenant=NOW)
    assert lignes == [] and meta["erreurs"] == ["réseau"]
    assert JETON_FICTIF not in json.dumps(meta)


def test_controle_signale_un_ecart():
    base = {"sport": "football", "marche": "RESULTAT_1N2", "issue": "DOM", "periode": "MATCH",
            "debut": "2026-10-18T18:45:00Z", "domicile": "Lyon", "exterieur": "Nice"}
    nb = [{**base, "match_id": "netbet|1", "cote": 1.81, "bookmaker": "netbet"}]
    refs = [
        {**base, "match_id": "pmu|1", "cote": 1.85, "bookmaker": "pmu"},
        {**base, "match_id": "pin|1", "cote": 2.40, "source": "pinnacle"},
    ]
    rapport = netbet.controle_prix(nb, refs)
    assert rapport["examines"] == 2
    assert [a["source"] for a in rapport["aberrants"]] == ["Pinnacle"]
    assert rapport["aberrants"][0]["cote_netbet"] == 1.81


def test_mode_et_sports_anj(monkeypatch):
    monkeypatch.delenv("SOURCE_NETBET", raising=False)
    assert netbet.mode_source() == "direct"
    monkeypatch.setenv("SOURCE_NETBET", "off")
    assert netbet.mode_source() == "off"
    assert "ski" not in netbet.PAGES and "/football" in netbet.PAGES.values()
    assert netbet.etat_nuxt("<html>rien</html>") is None


def test_cycle_ajoute_netbet_par_defaut(monkeypatch):
    from scripts import cycle
    monkeypatch.delenv("SOURCE_NETBET", raising=False)
    monkeypatch.delenv("SOURCE_OLYBET", raising=False)
    for nom in ("winamax_direct", "unibet_direct", "betclic_direct", "olybet_direct"):
        monkeypatch.setattr(getattr(cycle, nom), "collecter",
                            lambda *a, **k: ([], {"ok": True, "erreurs": [], "requetes": 0, "matchs": 0}))
    monkeypatch.setattr(cycle.pinnacle, "collecter", lambda: [{
        "sport": "football", "debut": "2026-10-18T18:45:00Z", "source": "pinnacle",
        "domicile": "Lyon", "exterieur": "Nice", "cote": 2.40,
        "marche": "RESULTAT_1N2", "periode": "MATCH", "issue": "DOM", "match_id": "pin|1"}])
    monkeypatch.setattr(cycle.polymarket, "collecter", lambda *a: [])
    monkeypatch.setattr(cycle, "harmoniser_pinnacle", lambda x: x)
    monkeypatch.setattr(cycle.pmu_direct, "collecter", lambda *a, **k: ([{
        "bookmaker": "pmu", "sport": "football", "debut": "2026-10-18T18:45:00Z",
        "domicile": "Lyon", "exterieur": "Nice", "cote": 1.85, "marche": "RESULTAT_1N2",
        "periode": "MATCH", "issue": "DOM", "match_id": "pmu|1"}], {"ok": True, "erreurs": [], "requetes": 1, "matchs": 1}))

    def lire(sports, heures, **kwargs):
        assert "football" in sports
        return ([{
            "bookmaker": "netbet", "sport": "football", "match_id": "netbet|1",
            "domicile": "Lyon", "exterieur": "Nice", "debut": "2026-10-18T18:45:00Z",
            "marche": "RESULTAT_1N2", "periode": "MATCH", "issue": "DOM", "cote": 1.81,
        }], {"ok": True, "erreurs": [], "requetes": 2, "matchs": 1})

    monkeypatch.setattr(cycle.netbet_direct, "collecter", lire)
    journal = {"etapes": {}}
    _, _, lignes = cycle.collecter_prematch("complet", NOW, journal)
    assert journal["netbet_source"] == "direct"
    assert any(l["bookmaker"] == "netbet" for l in lignes)
    assert journal["etapes"]["netbet"]["ok"] is True
    assert [a["source"] for a in journal["netbet_controle"]["aberrants"]] == ["Pinnacle"]
