"""OlyBet swarm : fixture enregistrée, périodes ambiguës, contrôle d'écarts."""
import json
from datetime import datetime, timezone
from pathlib import Path

from cotes.comparaison import comparer
from cotes.direct import olybet

FIXTURE = json.loads(Path("tests/fixtures/swarm_olybet.json").read_text())
NOW = datetime(2026, 10, 18, 12, tzinfo=timezone.utc)


class Faux:
    def __init__(self, docs):
        self.docs = list(docs)
        self.params = []
        self.requetes = 0
        self.erreurs = []

    def appel(self, commande, params):
        self.requetes += 1
        self.params.append((commande, params))
        if commande == "request_session":
            return {"code": 0, "data": {}}
        return self.docs.pop(0) if self.docs else {"code": 0, "data": {"data": {}}}

    def fermer(self):
        raise AssertionError("le client injecté ne doit pas être fermé")


def _lire(sports):
    docs = []
    if "football" in sports:
        docs += [FIXTURE["liste"], FIXTURE["marches"]]
    if "basket" in sports:
        docs += [FIXTURE["basket"], FIXTURE["basket_marches"]]
    if "hockey" in sports:
        docs += [FIXTURE["hockey"], FIXTURE["hockey_marches"]]
    client = Faux(docs)
    lignes, meta = olybet.collecter(set(sports), heures=36, client=client, maintenant=NOW)
    return lignes, meta, client


def test_football_traduit_et_ecarte_corners_et_commence():
    lignes, meta, client = _lire({"football"})
    assert meta["ok"] and meta["matchs"] == 1
    assert {l["bookmaker"] for l in lignes} == {"olybet"}
    assert {l["source"] for l in lignes} == {"OlyBet"}
    dom = next(l for l in lignes if l["marche"] == "RESULTAT_1N2" and l["issue"] == "DOM" and l["periode"] == "MATCH")
    assert dom["cote"] == 1.17 and dom["domicile"] == "Sporting CP"
    assert dom["exterieur"] == "Academico Viseu"
    assert next(l["cote"] for l in lignes if l["marche"] == "TOTAL" and l["issue"] == "PLUS") == 1.4
    assert next(l["ligne"] for l in lignes if l["marche"] == "HANDICAP" and l["issue"] == "DOM") == -0.5
    assert any(l["marche"] == "BOTH_TEAMS_TO_SCORE" and l["issue"] == "YES" for l in lignes)
    assert any(l["periode"] == "MT1" and l["cote"] == 1.42 for l in lignes)
    assert not any("corner" in (l.get("libelle") or "").lower() or "pair" in (l.get("libelle") or "").lower()
                   for l in lignes)
    assert not any(l["domicile"] == "Match" for l in lignes)
    demandes = [p["where"]["market"]["type"]["@in"] for c, p in client.params
                if c == "get" and "market" in p.get("what", {})]
    assert demandes and "P1XP2" in demandes[0]
    assert "OddEven" not in demandes[0]
    assert all("orner" not in t.lower() for t in demandes[0])
    marches = [p for c, p in client.params if c == "get" and "market" in (p.get("what") or {})]
    assert marches[0]["where"]["game"]["id"]["@in"] == [501]


def test_hockey_et_basket_ambigus_ne_sont_pas_compares():
    lignes, meta, _ = _lire({"football", "hockey", "basket"})
    assert meta["ok"]
    total = next(l for l in lignes if l["sport"] == "hockey" and l["marche"] == "TOTAL")
    vainqueur = next(l for l in lignes if l["sport"] == "hockey" and l["marche"] == "VAINQUEUR")
    basket = next(l for l in lignes if l["sport"] == "basket")
    assert total["periode"] == "MATCH?"
    assert vainqueur["periode"] == "MATCH"
    assert basket["periode"] == "MATCH?"
    base = {"sport": "hockey", "ligue": "NHL", "domicile": "Boston Bruins", "exterieur": "Toronto Maple Leafs",
            "debut": "2026-10-18T20:00:00Z", "collecte": "2026-10-18T12:00:00Z", "marche": "TOTAL",
            "periode": "MATCH", "ligne": 5.5, "issue": "PLUS", "joueur": None, "cote": 2.4, "proba_juste": 0.5}
    vides = comparer([total], {"Pinnacle": [{**base, "source": "pinnacle", "match_id": "p1"}]})
    assert vides == []
    pris = comparer([vainqueur | {"cote": 2.2}], {"Pinnacle": [{
        **base, "source": "pinnacle", "match_id": "p1", "marche": "VAINQUEUR", "ligne": None,
        "issue": "DOM", "cote": 1.7, "proba_juste": 0.55}]})
    assert pris and pris[0]["bookmaker"] == "OlyBet"


def test_controle_signale_un_ecart_sans_retirer_la_cote():
    base = {"sport": "football", "marche": "RESULTAT_1N2", "issue": "DOM", "periode": "MATCH",
            "debut": "2026-10-18T20:00:00Z", "domicile": "Sporting CP", "exterieur": "Academico Viseu"}
    oly = [{**base, "match_id": "olybet|1", "cote": 1.17, "bookmaker": "olybet", "source": "OlyBet"}]
    refs = [
        {**base, "match_id": "pmu|1", "cote": 1.20, "bookmaker": "pmu", "source": "PMU"},
        {**base, "match_id": "pin|1", "cote": 2.00, "source": "pinnacle"},
    ]
    rapport = olybet.controle_prix(oly, refs)
    assert rapport["examines"] == 2
    assert [a["source"] for a in rapport["aberrants"]] == ["Pinnacle"]
    assert oly[0]["cote"] == 1.17


def test_mode_et_sports_anj():
    assert olybet.mode_source() == "direct"
    assert "Biathlon" not in olybet.SPORTS and "Nascar" not in olybet.SPORTS
    assert "tennis_de_table" in olybet.SPORTS.values()
    assert olybet.sports_demandes({"football", "biathlon"}) == [("Soccer", "football")]


def test_session_en_echec_ne_propage_pas_le_message():
    class Panne:
        requetes = 1
        erreurs = ["code 5"]

        def appel(self, commande, params):
            return None

        def fermer(self):
            raise AssertionError("client injecté")

    lignes, meta = olybet.collecter({"football"}, client=Panne(), maintenant=NOW)
    assert lignes == [] and meta["ok"] is False
    assert meta["erreurs"] == ["code 5"]
    assert "site_key" not in json.dumps(meta)


def test_cycle_ajoute_olybet_par_defaut(monkeypatch):
    from scripts import cycle
    monkeypatch.delenv("SOURCE_OLYBET", raising=False)
    monkeypatch.setattr(cycle.pmu_direct, "collecter",
                        lambda *a, **k: ([], {"ok": True, "erreurs": [], "requetes": 0, "matchs": 0}))
    monkeypatch.setattr(cycle.winamax_direct, "collecter",
                        lambda *a, **k: ([], {"ok": True, "erreurs": [], "requetes": 0, "matchs": 0}))
    monkeypatch.setattr(cycle.unibet_direct, "collecter",
                        lambda *a, **k: ([], {"ok": True, "erreurs": [], "requetes": 0, "matchs": 0}))
    monkeypatch.setattr(cycle.betclic_direct, "collecter",
                        lambda *a, **k: ([], {"ok": True, "erreurs": [], "requetes": 0, "matchs": 0}))
    monkeypatch.setattr(cycle.netbet_direct, "collecter",
                        lambda *a, **k: ([], {"ok": True, "erreurs": [], "requetes": 0, "matchs": 0}))
    monkeypatch.delenv("SOURCE_NETBET", raising=False)
    monkeypatch.setattr(cycle.pinnacle, "collecter", lambda: [{
        "sport": "football", "debut": "2026-10-18T20:00:00Z", "source": "pinnacle",
        "domicile": "Sporting CP", "exterieur": "Academico Viseu", "cote": 1.20,
        "marche": "RESULTAT_1N2", "periode": "MATCH", "issue": "DOM", "match_id": "pin|1"}])
    monkeypatch.setattr(cycle.polymarket, "collecter", lambda *a: [])
    monkeypatch.setattr(cycle, "harmoniser_pinnacle", lambda x: x)

    def lire(sports, heures):
        return ([{
            "bookmaker": "olybet", "source": "OlyBet", "sport": "football", "match_id": "olybet|1",
            "domicile": "Sporting CP", "exterieur": "Academico Viseu", "debut": "2026-10-18T20:00:00Z",
            "marche": "RESULTAT_1N2", "periode": "MATCH", "issue": "DOM", "cote": 1.17,
        }], {"ok": True, "erreurs": [], "requetes": 2, "matchs": 1})

    monkeypatch.setattr(cycle.olybet_direct, "collecter", lire)
    journal = {"etapes": {}}
    _, _, lignes = cycle.collecter_prematch("complet", NOW, journal)
    assert journal["olybet_source"] == "direct"
    assert any(l["bookmaker"] == "olybet" for l in lignes)
    assert journal["olybet_controle"]["aberrants"] == []
    assert journal["etapes"]["olybet"]["ok"] is True
