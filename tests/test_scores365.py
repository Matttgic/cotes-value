"""365Scores : deuxième avis pour les sports où Flashscore était seul. Forme relevée le 10/11/2026."""
from datetime import datetime, timezone

from cotes import resultats, scores365

MAINTENANT = datetime(2026, 11, 10, 22, 0, tzinfo=timezone.utc)
# match réel du relevé (champs lus seulement)
JEU = {"id": 4888826, "sportId": 8, "competitionDisplayName": "Kazakhstan National League",
       "startTime": "2026-11-09T12:00:00+00:00", "statusGroup": 4, "statusText": "Ended",
       "homeCompetitor": {"id": 85691, "name": "Atyrau", "score": 3.0, "isWinner": True},
       "awayCompetitor": {"id": 85690, "name": "Quanysh", "score": 1.0, "isWinner": False},
       "isHomeAwayInverted": False}


class Reponse:
    def __init__(self, doc, status=200):
        self.status_code, self._doc = status, doc

    def json(self):
        if isinstance(self._doc, Exception):
            raise self._doc
        return self._doc


class Http:
    def __init__(self, reponse):
        self.reponse, self.appels = reponse, []

    def get(self, url, params=None, timeout=None):
        self.appels.append(params)
        return self.reponse


def test_match_termine_et_cas_laisses_de_cote():
    m = scores365.match("volley", JEU)
    assert m["source"] == "365scores" and m["domicile"] == "Atyrau" and m["exterieur"] == "Quanysh"
    assert m["score"] == (3, 1) and m["periodes"] == [] and m["debut"] == datetime(2026, 11, 9, 12, tzinfo=timezone.utc)
    inverse = scores365.match("volley", {**JEU, "isHomeAwayInverted": True})
    assert inverse["domicile"] == "Quanysh" and inverse["score"] == (1, 3)
    for autre in ({"statusText": "After Penalties"}, {"statusText": "Postponed"}, {"statusText": "2nd Half"},
                  {"startTime": None}, {"homeCompetitor": {"name": "Atyrau", "score": -1.0}},
                  {"awayCompetitor": {"name": "", "score": 1.0}}, {"homeCompetitor": {"name": "Atyrau", "score": 2.5}}):
        assert scores365.match("volley", {**JEU, **autre}) is None
    assert scores365.match("volley", None) is None


def test_lecture_par_jour_pannes_notees_et_coupure(monkeypatch):
    http = Http(Reponse({"games": [JEU, JEU, {**JEU, "id": 2, "statusText": "Scheduled"}]}))
    recs = scores365.lire("volley", ["2026-11-09", "2026-11-10", "2026-10-01", "2026-11-12"], MAINTENANT, http)
    assert len(recs) == 1                                                   # doublon et match à venir écartés
    assert [p["startDate"] for p in http.appels] == ["10/11/2026", "09/11/2026"]      # ni trop vieux, ni futur
    assert http.appels[0]["sports"] == 8 and http.appels[0]["onlyMajorGames"] == "false"
    assert scores365.lire("football", ["2026-11-09"], MAINTENANT, http) == []          # sport déjà couvert ailleurs
    for panne in (Reponse({}, 403), Reponse(ValueError("pas du JSON")), Reponse(["liste"])):
        avant = len(scores365.ERREURS)
        assert scores365.lire("volley", ["2026-11-09"], MAINTENANT, Http(panne)) == []
        assert len(scores365.ERREURS) == avant + 1
    monkeypatch.setenv("SCORES_365", "non")
    coupe = Http(Reponse({"games": [JEU]}))
    assert scores365.lire("volley", ["2026-11-09"], MAINTENANT, coupe) == [] and coupe.appels == []


def test_jours_a_lire_des_paris_ouverts():
    p = lambda sport, debut, statut="a_regler": {"statut": statut, "sport": sport, "debut": debut}  # noqa: E731
    jours = scores365.jours_a_lire([p("volley", "2026-11-09T12:00:00Z"), p("handball", "2026-11-10T21:00:00Z"),
                                    p("football", "2026-11-09T12:00:00Z"), p("rugby", "2026-11-08T15:00:00Z", "gagne"),
                                    p("basket", "2026-10-20T12:00:00Z")], MAINTENANT)
    assert jours == {"volley": ["2026-11-08", "2026-11-09"]}


def test_deux_sources_d_accord_reglent_tout_de_suite_un_desaccord_attend():
    pari = {"statut": "en_cours", "match_id": "pmu|1", "sport": "volley", "domicile": "Atyrau", "exterieur": "Quanysh",
            "debut": "2026-11-09T12:00:00Z", "periode": "MATCH", "marche": "VAINQUEUR", "issue": "DOM"}
    trois_heures = datetime(2026, 11, 9, 15, 0, tzinfo=timezone.utc)
    s365 = scores365.match("volley", JEU)
    flash = {**s365, "source": "flashscore", "id_source": "f1", "periodes": [(25, 20), (25, 22), (20, 25), (25, 18)],
             "libelles": ["1", "2", "3", "4"]}
    assert resultats.consensus(pari, [flash], trois_heures) is None                   # Flashscore seul : 6 h
    r = resultats.consensus(pari, [flash, s365], trois_heures)
    assert r["score"] == (3, 1) and r["sources"] == ["365scores", "flashscore"]
    faux = {**s365, "score": (1, 3)}
    assert resultats.consensus(pari, [flash, faux], datetime(2026, 11, 12, tzinfo=timezone.utc)) is None
    # seule, cette source attend 24 h comme tout validateur non éprouvé
    assert resultats.consensus(pari, [s365], datetime(2026, 11, 9, 20, tzinfo=timezone.utc)) is None
    assert resultats.consensus(pari, [s365], datetime(2026, 11, 10, 13, tzinfo=timezone.utc))["sources"] == ["365scores"]
