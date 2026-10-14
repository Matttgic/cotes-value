import json
from datetime import datetime, timedelta, timezone

import pytest
import requests

from cotes import reglement, theodds as O

NOW = datetime(2026, 10, 14, 20, tzinfo=timezone.utc)
START = (NOW - timedelta(hours=8)).isoformat()
KEY = "basketball_euroleague"


def pari(**kw):
    return {"id": "p1", "match_id": "winamax|1", "sport": "basket", "ligue": "Euroligue",
            "domicile": "Paris Basketball", "exterieur": "Real Madrid", "debut": START,
            "statut": "en_cours", "periode": "MATCH", "marche": "VAINQUEUR", "issue": "DOM",
            "ligne": None, "mise": 10, "cote": 2, **kw}


def event(**kw):
    return {"id": "event1", "sport_key": KEY, "commence_time": START, "completed": True,
            "home_team": "Paris Basketball", "away_team": "Real Madrid",
            # Ordre volontairement inverse : utiliser le nom, pas la position.
            "scores": [{"name": "Real Madrid", "score": "91"}, {"name": "Paris Basketball", "score": "99"}], **kw}


class Response:
    def __init__(self, data, status=200, remaining=500):
        self.data, self.status_code = data, status
        self.headers = {"x-requests-remaining": str(remaining), "x-requests-used": str(500 - remaining)}

    def json(self):
        return self.data


class HTTP:
    def __init__(self, scores=None, status=None, remaining=None, sports=None):
        self.calls = []
        self.data = scores if scores is not None else [event()]
        self.status, self.remaining = status or {}, remaining or {}
        self.sports = sports or [KEY]

    def get(self, url, params, timeout):
        self.calls.append((url, params.copy()))
        cle = params["apiKey"]
        r = self.remaining.get(cle, 500)
        status = self.status.get(cle, 200)
        data = self.data if "/scores/" in url else [{"key": k, "has_outrights": False} for k in self.sports]
        return Response(data, status, r)

    @property
    def scores_calls(self):
        return [c for c in self.calls if "/scores/" in c[0]]


def run(paris=None, cache=None, now=NOW, http=None, keys=None, deja=None, enr=None):
    return O.collecter(paris if paris is not None else [pari()], deja or {}, enr or [],
                       keys or ["secret-alpha"], cache if cache is not None else {}, now, http or HTTP())


def test_quatre_comptes_verifies_gratuitement_sans_match_a_lire():
    http, cache = HTTP(), {}
    r, bilan = run(paris=[], cache=cache, http=http, keys=["a", "b", "c", "d"])
    assert r == {} and bilan["cles_configurees"] == bilan["cles_valides"] == 4
    assert len(http.calls) == 4 and len(http.scores_calls) == 0
    run(paris=[], cache=cache, http=http, keys=["a", "b", "c", "d"])
    assert len(http.calls) == 4


def test_reglement_et_trace_avec_prolongation_basket():
    http = HTTP()
    p = pari()
    r, bilan = run(http=http, paris=[p])
    reglement.appliquer([p], r, {}, NOW)
    assert p["statut"] == "gagne" and p["gain"] == 10
    assert p["preuve_reglement"]["sources"] == ["theodds"]
    assert p["preuve_reglement"]["preuve_source"]["event_id"] == "event1"
    assert bilan["requetes_scores"] == 1
    assert http.scores_calls[0][1]["daysFrom"] == 3


def test_une_lecture_partagee_et_aucun_quota_pour_match_deja_valide():
    http = HTTP()
    ps = [pari(id=str(i), match_id=f"book|{i}") for i in range(20)]
    r, bilan = run(paris=ps, http=http)
    assert len(r) == 20 and bilan["requetes_scores"] == 1
    http = HTTP()
    r, bilan = run(http=http, deja={"winamax|1": {"score": (99, 91)}})
    assert not r and not http.scores_calls


def test_cache_durable_apres_fenetre_et_deduplication_cles():
    cache, http = {}, HTTP()
    run(cache=cache, http=http, keys=["secret-alpha", "secret-alpha"])
    r, bilan = run(cache=cache, http=http, now=NOW + timedelta(days=4))
    assert r and bilan["requetes_scores"] == 0
    assert len(http.calls) == 2 and len(cache["comptes"]) == 1
    assert "secret-alpha" not in json.dumps(cache)


@pytest.mark.parametrize("change", [
    {"completed": False}, {"completed": "true"}, {"sport_key": "basketball_nba"},
    {"scores": None}, {"scores": [{"name": "Paris Basketball", "score": "-1"}, {"name": "Real Madrid", "score": "91"}]},
    {"scores": [{"name": "Paris Basketball", "score": "99.5"}, {"name": "Real Madrid", "score": "91"}]},
    {"commence_time": "2026-10-14T12:00:00"}, {"commence_time": (NOW + timedelta(hours=1)).isoformat()},
])
def test_resultats_incomplets_ou_invalides_ne_reglent_pas(change):
    r, _ = run(http=HTTP(scores=[event(**change)]))
    assert not r


def test_mauvaise_equipe_heure_ou_double_affiche_rejetee():
    for ev in [event(home_team="Paris Basketball Women"),
               event(commence_time=(NOW - timedelta(hours=9)).isoformat()),
               event(home_team="Paris Basketball U21")]:
        assert not run(http=HTTP(scores=[ev]))[0]
    assert not run(http=HTTP(scores=[event(), event(id="event2")]))[0]


def test_orientation_inverse_et_reference_anglaise():
    p = pari(domicile="Real Madrid", exterieur="Paris Basketball", issue="EXT")
    r, _ = run(paris=[p])
    assert r[p["match_id"]]["score"] == (91, 99)
    assert O.retrouver(pari(domicile="Paris", match_reference="Real Madrid - Paris Basketball"),
                       [O._capture(event(), KEY, NOW)], KEY)["score"] == (99, 91)


def test_interdiction_de_regler_les_autres_marches_du_meme_match():
    ps = [pari(), pari(id="quarter", periode="QT1", marche="TOTAL", issue="PLUS", ligne=300),
          pari(id="regular", periode="TEMPS_REG", marche="TOTAL", issue="MOINS", ligne=300),
          pari(id="corners", marche="CORNERS_TOTAL", issue="PLUS", ligne=1)]
    r, _ = run(paris=ps)
    reglement.appliquer(ps, r, {}, NOW)
    assert ps[0]["statut"] == "gagne"
    assert all(p["statut"] == "en_cours" for p in ps[1:])


def test_coupes_jeunes_femmes_et_ligues_ambigues_non_associees():
    for p in [pari(sport="football", ligue="Ligue des Champions"), pari(sport="football", ligue="Premier League"),
              pari(ligue="Euroligue (F)"), pari(domicile="Paris Basketball Women"),
              pari(domicile="Paris Basketball U21"), pari(sport="baseball", ligue="Major League")]:
        assert O.competition(p) is None
        http = HTTP()
        assert not run(paris=[p], http=http)[0] and not http.scores_calls
    assert O.competition(pari(sport="football", ligue="Brésil Série A")) == "soccer_brazil_campeonato"
    assert O.competition(pari(sport="football", ligue="Ligue 1 McDonald’s®")) == "soccer_france_ligue_one"


def test_hockey_vainqueur_seul_et_pas_de_reglement_du_temps_reglementaire():
    cle = "icehockey_nhl"
    ev = event(sport_key=cle, home_team="Boston Bruins", away_team="Seattle Kraken",
               scores=[{"name": "Boston Bruins", "score": "3"}, {"name": "Seattle Kraken", "score": "2"}])
    ps = [pari(sport="hockey", ligue="NHL", domicile="Boston Bruins", exterieur="Seattle Kraken"),
          pari(id="total", sport="hockey", ligue="NHL", domicile="Boston Bruins", exterieur="Seattle Kraken",
               marche="TOTAL", issue="PLUS", ligne=4.5)]
    r, _ = run(paris=ps, http=HTTP(scores=[ev], sports=[cle]))
    reglement.appliquer(ps, r, {}, NOW)
    assert ps[0]["statut"] == "gagne" and ps[1]["statut"] == "en_cours"


def test_wnba_marqueur_feminin_et_score_par_nom():
    cle = "basketball_wnba"
    p = pari(ligue="WNBA", domicile="Seattle Storm (F)", exterieur="Chicago Sky (F)")
    ev = event(sport_key=cle, home_team="Seattle Storm", away_team="Chicago Sky",
               scores=[{"name": "Chicago Sky", "score": "75"}, {"name": "Seattle Storm", "score": "80"}])
    assert run(paris=[p], http=HTTP(scores=[ev], sports=[cle]))[0][p["match_id"]]["score"] == (80, 75)


def test_desaccord_autre_source_et_delai_source_unique():
    enr = {"source": "espn", "sport": "basket", "domicile": "Paris Basketball", "exterieur": "Real Madrid",
           "debut": datetime.fromisoformat(START), "score": (98, 91), "periodes": [], "libelles": [], "corners": None}
    r, bilan = run(enr=[enr])
    assert not r and bilan["conflits"] == 1
    http = HTTP()
    assert not run(paris=[pari(debut=(NOW - timedelta(hours=5)).isoformat())], http=http)[0]
    assert not http.scores_calls


def test_fraicheur_et_repartition_comptes_epuises():
    http, cache = HTTP(scores=[], remaining={"a": 0, "b": 500}), {}
    run(cache=cache, http=http, keys=["a", "b"])
    assert http.scores_calls[0][1]["apiKey"] == "b"
    assert run(cache=cache, http=http, keys=["a", "b"], now=NOW + timedelta(hours=2))[1]["requetes_scores"] == 0
    assert run(cache=cache, http=http, keys=["a", "b"], now=NOW + timedelta(hours=3))[1]["requetes_scores"] == 1


def test_budget_journalier_mensuel_et_reset():
    cache, http = {}, HTTP(scores=[])
    run(cache=cache, http=http)
    etat = next(iter(cache["comptes"].values()))
    etat["credits_jour"] = 16
    assert run(cache=cache, http=http, now=NOW + timedelta(hours=3))[1]["requetes_scores"] == 0
    assert run(cache=cache, http=http, now=NOW + timedelta(days=1))[1]["requetes_scores"] == 1
    etat["credits_mois"] = 500
    assert run(cache=cache, http=http, now=NOW + timedelta(days=2))[1]["requetes_scores"] == 0
    assert run(cache=cache, http=http, now=NOW.replace(month=11, day=1))[1]["cles_valides"] == 1
    assert next(iter(cache["comptes"].values()))["credits_mois"] == 0


def test_limite_globale_et_pas_de_famine_competition():
    cles = list(O.LIGUES["basket"])
    ps = [pari(id=str(i), match_id=f"book|{i}", ligue=O.LIGUES["basket"][k][0]) for i, k in enumerate(cles)]
    cache, http = {}, HTTP(scores=[], sports=cles)
    run(paris=ps, cache=cache, http=http, keys=["a", "b", "c", "d"])
    assert len(http.scores_calls) == 4
    premieres = {c[0] for c in http.scores_calls}
    run(paris=ps, cache=cache, http=http, keys=["a", "b", "c", "d"], now=NOW + timedelta(hours=1))
    assert any(c[0] not in premieres for c in http.scores_calls[4:])


def test_erreurs_ne_publient_jamais_les_cles_et_essais_limites():
    class Panne(HTTP):
        def get(self, url, params, timeout):
            if "/scores/" in url:
                raise requests.RequestException(f"https://api/?apiKey={params['apiKey']}")
            return super().get(url, params, timeout)

    cache = {}
    r, bilan = run(cache=cache, http=Panne(), keys=["secret-a", "secret-b", "secret-c", "secret-d"])
    assert not r and bilan["requetes_scores"] == 4
    assert "secret-" not in json.dumps([cache, bilan])
    assert sum(c["credits_mois"] for c in bilan["comptes"]) == 8
    http = HTTP(status={"bad-secret": 401})
    cache = {}
    r, bilan = run(cache=cache, http=http, keys=["bad-secret", "good-secret"])
    assert bilan["cles_valides"] == 1 and r
    assert "secret" not in json.dumps([cache, bilan])


def test_reportes_et_vieux_resultats_ne_consomment_pas_de_credits():
    for p in [pari(reporte_au=(NOW + timedelta(days=1)).isoformat()),
              pari(debut=(NOW - timedelta(days=4)).isoformat())]:
        http = HTTP()
        assert not run(paris=[p], http=http)[0] and not http.scores_calls


def test_saisie_manuelle_prioritaire_sur_restriction_du_secours():
    p = pari(id="manual", periode="QT1", marche="TOTAL", issue="PLUS", ligne=40)
    r, _ = run()
    reglement.appliquer([p], r, {"manual": "gagne"}, NOW)
    assert p["statut"] == "gagne" and p["preuve_reglement"]["origine"] == "statut saisi à la main"


def test_cycle_branche_les_quatre_secrets_et_persiste_cache_et_diagnostic(tmp_path, monkeypatch):
    from scripts import cycle

    original = O.collecter
    http = HTTP()
    monkeypatch.setattr(cycle.resultats_mod, "a_lire", lambda *a: {})
    monkeypatch.delenv("API_SPORTS_KEY", raising=False)
    secrets = [f"secret-integration-{i}" for i in range(1, 5)]
    for i, secret in enumerate(secrets, 1):
        monkeypatch.setenv(f"THE_ODDS_API_KEY_{i}", secret)

    def collecter(paris, deja, enr, keys, cache, now):
        assert keys == secrets
        return original(paris, deja, enr, keys, cache, NOW, http)

    monkeypatch.setattr(O, "collecter", collecter)
    journal = {"etapes": {}}
    p = pari()
    assert cycle.effectuer_reglement([p], tmp_path, NOW, "", journal, {}, "oui")
    assert p["statut"] == "gagne" and journal["theodds"]["cles_valides"] == 4
    assert journal["resultats"]["matchs_valides"] == 1
    assert json.loads((tmp_path / "theodds.json").read_text())["ligues"][KEY]["matchs"]
    assert all(s not in json.dumps(journal) + (tmp_path / "theodds.json").read_text() for s in secrets)
