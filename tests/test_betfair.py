"""Betfair Exchange : lecture des réponses réelles du 08/11/2026 (FC Koln v Leverkusen, IP finlandaise).

betfair_catalogue.json : réponse ``byevent`` (catalogue, sans prix), raccourcie. betfair_bymarket.json : réponse
``bymarket`` réduite au meilleur prix de chaque côté, valeurs inchangées.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from cotes.direct import betfair as bf

ICI = Path(__file__).parent / "fixtures"
CATALOGUE = json.loads((ICI / "betfair_catalogue.json").read_text())
PRIX = json.loads((ICI / "betfair_bymarket.json").read_text())
AVANT = datetime(2026, 11, 8, 13, 35, tzinfo=timezone.utc)
RECHERCHE = {"attachments": {"events": {"36241102": {"eventId": 36241102, "name": "FC Koln v Leverkusen",
                                                     "competitionId": 59}},
                             "competitions": {"59": {"competitionId": 59, "name": "German Bundesliga"}}}}
MARQUE = "corps-interdit"


class Rep:
    def __init__(self, code, doc=None, text=MARQUE):
        self.status_code, self._doc, self.text = code, doc, text

    def json(self):
        if self._doc is None:
            raise ValueError
        return self._doc


class Session:
    """Répond selon l'adresse ; garde chaque appel (méthode, adresse, paramètres)."""

    def __init__(self, reponses):
        self.reponses, self.appels = reponses, []

    def request(self, methode, url, params=None, json=None, timeout=None, headers=None):
        self.appels.append((methode, url, dict(params or {})))
        for cle, rep in self.reponses.items():
            if url.endswith(cle):
                return rep(params) if callable(rep) else rep
        return Rep(404)


def _session():
    return Session({"/search": Rep(200, RECHERCHE), "/byevent": Rep(200, CATALOGUE), "/bymarket": Rep(200, PRIX)})


def _collecter(session, cache=None, maintenant=AVANT, **kw):
    return bf.collecter({"football"}, session=session, maintenant=maintenant, pause=(0, 0),
                        environ={"SOURCE_BETFAIR": "direct"}, catalogue={} if cache is None else cache, **kw)


def test_regles_des_types_de_marche():
    assert bf.regle("MATCH_ODDS", "football") == ("RESULTAT_1N2", "MATCH", None)
    assert bf.regle("OVER_UNDER_25", "football") == ("TOTAL", "MATCH", 2.5)
    assert bf.regle("FIRST_HALF_GOALS_15", "football") == ("TOTAL", "MT1", 1.5)
    assert bf.regle("TEAM_B_OVER_UNDER_05", "football") == ("TOTAL_EXT", "MATCH", 0.5)
    for ignore in ("OVER_UNDER_25_CARDS", "OVER_UNDER_85_CORNR", "TO_SCORE", "DOUBLE_CHANCE", "CORRECT_SCORE2"):
        assert bf.regle(ignore, "football") is None
    assert bf.regle("MATCH_ODDS", "tennis") == ("VAINQUEUR", "MATCH", None)
    assert bf.regle("OVER_UNDER_25", "tennis") is None


def test_mode_par_defaut_selon_la_machine():
    assert bf.mode({}) == "off"                                  # GitHub Actions : IP américaine, refusée
    assert bf.mode({"SERVEUR_DIRECT": "oui"}) == "direct"
    assert bf.mode({"SERVEUR_DIRECT": "oui", "SOURCE_BETFAIR": "shadow"}) == "shadow"
    assert bf.mode({"SOURCE_BETFAIR": "nimporte"}) == "off"
    lignes, info = bf.collecter(environ={})
    assert lignes == [] and info["mode"] == "off" and info["requetes"] == 0


def test_catalogue_garde_les_marches_lus():
    marches = bf.marches_du_catalogue(CATALOGUE, "football", AVANT, 36)
    noms = {m["id"] for m in marches}
    assert "1.264536998" in noms and "1.264537047" in noms      # Match Odds, Asian Handicap
    assert "1.264537000" not in noms                            # double chance : recalculée depuis le 1N2
    assert all(m["debut"] == datetime(2026, 11, 8, 14, 30, tzinfo=timezone.utc) for m in marches)
    assert bf.marches_du_catalogue(CATALOGUE, "football", datetime(2026, 11, 8, 14, 31, tzinfo=timezone.utc), 36) == []


def test_lignes_brutes_resultat_et_handicap():
    lignes = bf.lignes_brutes(PRIX, "football", AVANT, ligues={"36241102": "German Bundesliga"})
    koln = next(l for l in lignes if l["marche"] == "RESULTAT_1N2" and l["periode"] == "MATCH" and l["issue"] == "DOM")
    assert koln["domicile"] == "FC Koln" and koln["exterieur"] == "Leverkusen" and koln["ligue"] == "German Bundesliga"
    assert koln["achat"] == [{"price": 4.6, "liquidity": 845.93}] and koln["vente"] == [{"price": 4.7, "liquidity": 674.79}]
    assert koln["match_id"] == "betfair|36241102" and koln["source"] == "Betfair"
    assert {l["issue"] for l in lignes if l["marche"] == "RESULTAT_1N2" and l["periode"] == "MT1"} == {"DOM", "NUL", "EXT"}
    assert not [l for l in lignes if l["marche"] == "DOUBLE_CHANCE"]
    # handicap asiatique : la ligne est celle du domicile, pour les deux issues
    h = {(l["issue"], l["ligne"]): l for l in lignes if l["marche"] == "HANDICAP"}
    assert h[("DOM", -0.5)]["achat"][0]["price"] == 4.6 and h[("EXT", -0.5)]["achat"][0]["price"] == 1.27
    assert h[("DOM", 0.75)]["vente"][0]["price"] == 1.95 and h[("EXT", 0.75)]["vente"][0]["price"] == 2.09
    assert h[("DOM", -4.0)]["vente"] == [] and h[("EXT", -4.0)]["achat"] == []     # carnet d'un seul côté
    totaux = {(l["periode"], l["ligne"], l["issue"]) for l in lignes if l["marche"] == "TOTAL"}
    assert totaux == {("MATCH", 2.5, "PLUS"), ("MATCH", 2.5, "MOINS"), ("MT1", 1.5, "PLUS"), ("MT1", 1.5, "MOINS")}
    assert {l["issue"] for l in lignes if l["marche"] == "BOTH_TEAMS_TO_SCORE"} == {"YES", "NO"}
    assert {l["issue"] for l in lignes if l["marche"] == "DRAW_NO_BET"} == {"DOM", "EXT"}


def test_marche_en_direct_ou_suspendu_ignore():
    doc = json.loads(json.dumps(PRIX))
    ms = doc["eventTypes"][0]["eventNodes"][0]["marketNodes"]
    ms[3]["state"]["inplay"] = True                             # Match Odds
    ms[0]["state"]["status"] = "SUSPENDED"                      # Half Time
    lignes = bf.lignes_brutes(doc, "football", AVANT)
    assert not [l for l in lignes if l["marche"] == "RESULTAT_1N2"]
    assert bf.lignes_brutes(PRIX, "football", datetime(2026, 11, 8, 14, 30, tzinfo=timezone.utc)) == []


def test_issues_score_exact_mi_temps_fin_et_goal_lines():
    assert bf._issue("CORRECT_SCORE", "2 - 1", "A", "B") == "2-1"
    assert bf._issue("CORRECT_SCORE", "Any Other Home Win", "A", "B") is None
    assert bf._issue("HALF_TIME_FULL_TIME", "FC Koln/Draw", "FC Koln", "Leverkusen") == "DOM/NUL"
    assert bf._issue("DRAW_NO_BET", "The Draw", "A", "B") is None
    doc = {"eventTypes": [{"eventNodes": [{"eventId": 1, "event": {"eventName": "A v B"}, "marketNodes": [{
        "marketId": "1.2", "state": {"status": "OPEN", "inplay": False},
        "description": {"marketType": "ALT_TOTAL_GOALS", "bettingType": "ASIAN_HANDICAP_DOUBLE_LINE",
                        "marketTime": "2026-11-08T14:30:00.000Z"},
        "runners": [{"handicap": h, "description": {"runnerName": n},
                     "exchange": {"availableToBack": [{"price": 1.9, "size": 10}],
                                  "availableToLay": [{"price": 1.95, "size": 10}]}}
                    for h in (2.25, 2.5) for n in ("Under", "Over")]}]}]}]}
    lignes = bf.lignes_brutes(doc, "football", AVANT)
    assert {(l["ligne"], l["issue"]) for l in lignes} == {(2.25, "MOINS"), (2.25, "PLUS")}   # 2.5 : déjà en O/U 2.5


def test_collecter_cote_juste_et_cache_du_catalogue():
    s, cache = _session(), {}
    lignes, info = _collecter(s, cache)
    assert info["ok"] and info["erreurs"] == [] and info["requetes"] == 3 and info["matchs"] == 1
    assert [a[1].rsplit("/", 1)[1] for a in s.appels] == ["search", "byevent", "bymarket"]
    assert all(a[2]["_ak"] == bf.AK_CONNUE for a in s.appels)
    un_n_deux = [l for l in lignes if l["marche"] == "RESULTAT_1N2" and l["periode"] == "MATCH"]
    # milieu back/lay ; somme 0,9996 < 1, donc pas renormalisée (reference_echange ne gonfle jamais)
    assert len(un_n_deux) == 3 and 0.99 < sum(l["proba_juste"] for l in un_n_deux) <= 1
    koln = next(l for l in un_n_deux if l["issue"] == "DOM")
    assert abs(koln["proba_juste"] - (1 / 4.6 + 1 / 4.7) / 2) < 1e-6
    assert all(l["source"] == "Betfair" for l in lignes)
    assert {l["marche"] for l in lignes if l["marche"] == "DOUBLE_CHANCE"}      # recalculée depuis le 1N2
    assert not [l for l in lignes if l["marche"] == "HANDICAP" and l["ligne"] == -4.0]   # carnet incomplet
    # cycle suivant : catalogue gardé, seuls les prix sont relus
    s2 = _session()
    _collecter(s2, cache)
    assert [a[1].rsplit("/", 1)[1] for a in s2.appels] == ["bymarket"]


def test_403_coupe_la_lecture_sans_journaliser_le_corps():
    s = Session({"/search": Rep(403, text="<title>Restricted</title>")})
    lignes, info = _collecter(s)
    assert lignes == [] and not info["ok"] and info["erreurs"] == ["HTTP 403"] and info["requetes"] == 1
    assert MARQUE not in json.dumps(info) and "Restricted" not in json.dumps(info)


def test_401_relit_la_cle_dans_la_page():
    def recherche(params):
        return Rep(200, RECHERCHE) if params["_ak"] == "NouvelleCle12345" else Rep(401)
    s = Session({"/search": recherche, "/exchange/plus/": Rep(200, text='x.js?_ak=NouvelleCle12345"'),
                 "/byevent": Rep(200, CATALOGUE), "/bymarket": Rep(200, PRIX)})
    lignes, info = _collecter(s)
    assert info["ok"] and lignes
    assert s.appels[-1][2]["_ak"] == "NouvelleCle12345"


def test_evenements_trouves_secours():
    assert bf.evenements_trouves(RECHERCHE) == ["36241102"]
    assert bf.evenements_trouves({"results": [{"values": [{"key": {"eventId": 36241102}},
                                                          {"key": {"eventId": "36267103"}}]}]}) == ["36241102", "36267103"]
    assert bf.evenements_trouves(None) == []
