import json
from datetime import timedelta

import pytest
import requests

from cotes import propline as P, reglement
from tests.test_theodds import NOW, START, pari

KEY = "basketball_nba"


def event(**kw):
    return {"id": "e1", "sport_key": KEY, "commence_time": START,
            "home_team": "Boston Celtics", "away_team": "Chicago Bulls",
            "status": "final", "home_score": 99, "away_score": 91, **kw}


def bet(**kw):
    return pari(**{"ligue":"NBA", "domicile":"Boston Celtics", "exterieur":"Chicago Bulls", **kw})


class HTTP:
    def __init__(self, data=None, status=200, remaining=999):
        self.data = [event()] if data is None else data
        self.status, self.remaining, self.calls = status, remaining, []

    def get(self, url, params, headers, timeout):
        self.calls.append((url, params, headers))
        class Response:
            status_code = self.status
            headers = {"X-Daily-Remaining": str(self.remaining), "Retry-After": "7200"}
            def json(_):
                return self.data
        return Response()


def run(ps=None, http=None, cache=None, now=NOW, key="test-secret", autres=None, deja=None):
    return P.collecter([bet()] if ps is None else ps, deja or {}, autres or [], key,
                       {} if cache is None else cache, now, http or HTTP())


def test_score_final_trace_orientation_et_autorisation_par_marche():
    ps = [bet(), bet(id="quarter", periode="QT1", marche="TOTAL", issue="PLUS", ligne=30),
          bet(id="inverse", match_id="inverse", issue="EXT")]
    ps[2].update(domicile="Chicago Bulls", exterieur="Boston Celtics")
    http, cache = HTTP(), {}
    rs, b = run(ps, http, cache)
    reglement.appliquer(ps, rs, {}, NOW)
    assert [p['statut'] for p in ps] == ['gagne', 'en_cours', 'gagne']
    assert rs['inverse']['score'] == (91, 99)
    assert b['requetes_scores'] == 1 and b['paris_compatibles'] == 2
    assert ps[0]['preuve_reglement']['sources'] == ['propline']
    assert ps[0]['preuve_reglement']['preuve_source']['event_id'] == 'e1'
    assert http.calls[0][1] == {'days_from': 3}
    assert 'test-secret' not in http.calls[0][0]
    assert 'test-secret' not in json.dumps([rs, b, cache])


@pytest.mark.parametrize('change', [
    {'status': s} for s in ('expired', 'cancelled', 'postponed', 'retired', 'walkover', 'in_progress')
] + [{'period': 'h1'}, {'live': True}, {'home_score': None}, {'home_score': True},
     {'home_score': 99.5}, {'home_score': -1}, {'home_score': '99'}, {'home_score': 91},
     {'sport_key': 'basketball_wnba'}, {'commence_time': START[:19]},
     {'home_team': 'Boston Celtics Women'}, {'home_team': 'Boston Celtics U21'}])
def test_statuts_et_scores_invalides_ne_reglent_rien(change):
    assert not run(http=HTTP([event(**change)]))[0]


def test_pas_de_match_ambigu_ni_de_score_en_desaccord():
    assert not run(http=HTTP([event(), event(id='e2')]))[0]
    autres = [{'source': 'espn', 'sport': 'basket', 'domicile': 'Boston Celtics',
               'exterieur': 'Chicago Bulls', 'debut': NOW - timedelta(hours=8),
               'score': (100, 91), 'periodes': [], 'libelles': []}]
    rs, b = run(autres=autres)
    assert not rs and b['conflits'] == 1


def test_cache_partage_espacement_archive_et_correction_de_statut():
    cache, http = {}, HTTP([])
    run(cache=cache, http=http)
    run(cache=cache, http=http, now=NOW + timedelta(minutes=59))
    assert len(http.calls) == 1
    http.data = [event()]
    rs, _ = run(cache=cache, http=http, now=NOW + timedelta(hours=1))
    assert rs and len(http.calls) == 2
    rs, b = run(cache=cache, http=http, now=NOW + timedelta(days=4))
    assert rs and not b['requetes_scores']
    # Une autre affiche manquante provoque une relecture ; un final rétracté
    # ne doit plus être réutilisé pour l'affiche d'origine.
    http.data = [event(status='cancelled')]
    ps = [bet(), bet(id='autre', domicile='Miami Heat')]
    assert not run(ps=ps, cache=cache, http=http, now=NOW + timedelta(hours=2))[0]


def test_aucun_appel_sans_besoin_compatible_et_couverture_explicite():
    for p in (bet(periode='MT1'), bet(ligue='Euroligue'), bet(sport='volley'),
              bet(sport='football', ligue='Ligue des Champions'),
              bet(sport='football', ligue='Angleterre Championship')):
        http = HTTP()
        assert not run([p], http)[0] and not http.calls
    http = HTTP()
    run(http=http, deja={'winamax|1': {}})
    assert not http.calls
    assert P.competition({**bet(), 'sport':'football', 'ligue':'Ligue 1'}) == 'soccer_ligue_1'


def test_quota_refus_et_changement_de_cle_sans_fuite():
    cache, http = {}, HTTP(status=403)
    rs, b = run(cache=cache, http=http)
    assert not rs and b['erreurs'] == ['basketball_nba : HTTP 403']
    run(cache=cache, http=http, now=NOW + timedelta(hours=1))
    assert len(http.calls) == 1  # Retry-After : 2 h
    http.status = 200
    assert run(cache=cache, http=http, key='nouvelle-cle', now=NOW + timedelta(minutes=1))[0]
    assert len(http.calls) == 2
    cache['quota_restant'] = 100
    http.data = []
    run(ps=[{**bet(), 'domicile':'Miami Heat'}], cache=cache, http=http,
        key='nouvelle-cle', now=NOW + timedelta(hours=2))
    assert len(http.calls) == 2
    assert 'nouvelle-cle' not in json.dumps(cache)


def test_budget_global_et_reponses_malformees_ou_erreur_reseau():
    cache, http = {}, HTTP()
    run(cache=cache, http=http)
    cache['requetes_jour'] = P.BUDGET_JOUR
    run(ps=[{**bet(), 'domicile':'Miami Heat'}], cache=cache, http=http, now=NOW + timedelta(hours=2))
    assert len(http.calls) == 1
    for data in ({'error':'test-secret'}, [None]):
        assert run(http=HTTP(data))[1]['erreurs'] == ['basketball_nba : réponse inattendue']
    class Timeout:
        def get(self, *a, **kw):
            raise requests.Timeout('test-secret')
    assert run(http=Timeout())[1]['erreurs'] == ['basketball_nba : lecture indisponible']


def test_hockey_ne_regle_que_le_vainqueur_et_wnba_reconnue():
    ps = [{**bet(), 'sport':'hockey', 'ligue':'NHL', 'marche':'VAINQUEUR'},
          {**bet(), 'id':'total', 'sport':'hockey', 'ligue':'NHL', 'marche':'TOTAL', 'ligne':5.5, 'issue':'PLUS'}]
    rs, _ = run(ps, HTTP([event(sport_key='hockey_nhl', home_score=3, away_score=2)]))
    assert rs['winamax|1']['id_paris_autorises'] == ['p1']
    p = {**bet(), 'ligue':'WNBA', 'domicile':'New York Liberty', 'exterieur':'Indiana Fever'}
    assert run([p], HTTP([event(sport_key='basketball_wnba', home_team='New York Liberty', away_team='Indiana Fever')]))[0]


@pytest.mark.parametrize('change', [{'status': 'cancelled'}, {'status': 'in_progress'},
                                    {'home_score': None}, {'deleted': True}])
def test_cache_final_conserve_mais_suspendu_jusqua_reconfirmation(change):
    cache, http = {}, HTTP()
    assert run(cache=cache, http=http)[0]
    http.data = [event(**change)]
    ps = [bet(), bet(id='autre', domicile='Miami Heat')]
    rs, b = run(ps, http, cache, now=NOW + timedelta(hours=2))
    assert not rs and b['matchs_a_reconfirmer'] == 1
    e = cache['ligues'][KEY]
    assert tuple(e['matchs'][0]['score']) == (99, 91)
    assert 'e1' in e['a_reconfirmer']
    # Un JSON valide vide n'est pas une confirmation de ce final.
    http.data = []
    assert not run(ps, http, cache, now=NOW + timedelta(hours=3))[0]
    http.data = [event(home_score=101)]
    rs, b = run(ps, http, cache, now=NOW + timedelta(hours=4))
    assert rs['winamax|1']['score'] == (101, 91) and not b['matchs_a_reconfirmer']


def test_json_invalide_preserve_cache_et_quota():
    cache, http = {}, HTTP()
    run(cache=cache, http=http)
    class Malformed(HTTP):
        def get(self, *a, **kw):
            class Response:
                status_code = 200
                headers = {'X-Daily-Remaining': '998'}
                def json(self):
                    raise ValueError('test-secret')
            return Response()
    rs, b = run([bet(), bet(id='autre', domicile='Miami Heat')], Malformed(), cache,
                now=NOW + timedelta(hours=2))
    assert rs and b['erreurs'] == [KEY + ' : JSON invalide']
    assert cache['quota_restant'] == 998
    assert 'test-secret' not in json.dumps([cache, b])
