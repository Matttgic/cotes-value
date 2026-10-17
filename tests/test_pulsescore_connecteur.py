from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json

import pytest
import requests

from cotes import pulsescore as P
from tests.test_marches import ev, sel


class Response:
    def __init__(self, data=None, status=200, retry=None):
        self.data, self.status_code = data, status
        self.headers = {'Retry-After': retry} if retry is not None else {}
    def json(self):
        if isinstance(self.data, Exception):
            raise self.data
        return self.data


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(P.time, 'sleep', lambda _: None)
    return P.Client('CLE_NE_PAS_LOGUER', pause=0)


def test_erreurs_reseau_sans_exception_ni_secret(client, monkeypatch):
    calls = []
    def get(*a, **kw):
        calls.append(1)
        raise requests.Timeout('https://api?key=CLE_NE_PAS_LOGUER')
    monkeypatch.setattr(client.s, 'get', get)
    assert client.get('winamax/soccer/events') is None
    assert len(calls) == 4 and client.requetes == 4
    assert client.erreurs == ['winamax/soccer/events : erreur réseau']
    assert 'CLE_NE_PAS_LOGUER' not in json.dumps(client.erreurs)


def test_exception_collecte_type_seul_et_autres_sports_preserves(monkeypatch):
    def matchs(self, bm, sport, *a):
        if sport == 'soccer':
            raise RuntimeError('CLE_NE_PAS_LOGUER')
        return [ev([{'canonicalMarket': 'MATCH_RESULT', 'selections': [sel('HOME', 'Lens', 2)]}])]
    monkeypatch.setattr(P.Client, 'matchs', matchs)
    rows, _, erreurs = P.collecter('CLE_NE_PAS_LOGUER', {'winamax': ['soccer', 'basketball']})
    assert len(rows) == 1 and erreurs == {'winamax': ['soccer : RuntimeError']}


@pytest.mark.parametrize('prix', [None, True, 'invalide', 'nan', 'inf', 1, -2])
def test_prix_invalide_isole_sans_perdre_les_autres(prix):
    market = {'canonicalMarket': 'OVER_UNDER', 'period': 'FULL_TIME', 'rawName': 'Total de buts',
              'selections': [sel('OVER', 'Plus', prix, 2.5), sel('UNDER', 'Moins', '1.9', '2.5')]}
    event = ev([market])
    original = deepcopy(event)
    erreurs = []
    rows = P.traduire(event, 'winamax', 'football', 't', erreurs=erreurs)
    assert [(r['issue'], r['cote'], r['ligne']) for r in rows] == [('MOINS', 1.9, 2.5)]
    assert erreurs and event == original


def test_nul_invalide_ne_transforme_pas_1n2_en_vainqueur():
    m = {'canonicalMarket': 'MATCH_RESULT', 'selections': [sel('HOME', 'Lens', 2),
         sel('DRAW', 'Nul', 'invalide'), sel('AWAY', 'Lille', 3)]}
    rows = P.traduire(ev([m]), 'pmu', 'football', 't')
    assert len(rows) == 2 and {r['marche'] for r in rows} == {'RESULTAT_1N2'}


def test_schema_marche_invalide_ne_fait_pas_perdre_autre_marche():
    m = {'canonicalMarket': 'MATCH_RESULT', 'selections': [sel('HOME', 'Lens', 2)]}
    rows = P.traduire(ev([None, {'selections': 42}, {**m, 'period': []}, m]), 'pmu', 'football', 't')
    assert len(rows) == 1
    assert P.traduire(ev(42), 'pmu', 'football', 't') == []


def test_periodes_ambigues_hockey_et_tennis_refusees():
    assert P.periode('hockey', 'FIRST_HALF', 'Total de buts') is None
    assert P.periode('hockey', 'FIRST_HALF', '1ère période - Total') == 'P1'
    assert P.periode('tennis', 'FIRST_SET', 'Vainqueur') == 'SET1'
    assert P.periode('tennis', 'SECOND_HALF', 'Vainqueur') is None
    assert P.periode('tennis', 'FIRST_QUARTER', 'Vainqueur') is None


@pytest.mark.parametrize('retry', ['nan', 'inf', 'abc', '-5', '1e100'])
def test_retry_after_invalide_utilise_backoff(client, monkeypatch, retry):
    responses = iter([Response(status=429, retry=retry), Response({'events': []})])
    sleeps = []
    monkeypatch.setattr(client.s, 'get', lambda *a, **kw: next(responses))
    monkeypatch.setattr(P.time, 'sleep', sleeps.append)
    assert client.get('winamax/soccer/events') == {'events': []}
    assert sleeps[0] == 2 and client.requetes == 2


def test_retry_long_persiste_sans_bloquer_et_cle_changee_reactive(client, monkeypatch):
    appels, sleeps = [], []
    def get(*a, **kw):
        appels.append(1)
        return Response(status=429, retry='7200')
    monkeypatch.setattr(client.s, 'get', get)
    monkeypatch.setattr(P.time, 'sleep', sleeps.append)
    assert client.get('winamax/soccer/events') is None
    assert not sleeps and len(appels) == 1
    c2 = P.Client('CLE_NE_PAS_LOGUER', pause=0, etat=client.etat)
    monkeypatch.setattr(c2.s, 'get', get)
    c2.get('winamax/basketball/events')
    assert len(appels) == 1
    assert 'CLE_NE_PAS_LOGUER' not in json.dumps(client.etat)
    c3 = P.Client('autre-cle', pause=0, etat=client.etat)
    monkeypatch.setattr(c3.s, 'get', lambda *a, **kw: Response({'events': []}))
    assert c3.get('winamax/soccer/events') == {'events': []}


def test_retry_after_date_http():
    now = datetime(2026, 10, 17, 12, tzinfo=timezone.utc)
    assert P._retry_after('Sat, 17 Oct 2026 13:00:00 GMT', now, 2) == 3600
    assert P._retry_after('Sat, 17 Oct 2026 11:00:00 GMT', now, 2) == 2


@pytest.mark.parametrize('status', [401, 403])
def test_refus_ne_fait_pas_une_rafale_sur_tous_les_sports(client, monkeypatch, status):
    appels = []
    def get(*a, **kw):
        appels.append(1)
        return Response(status=status)
    monkeypatch.setattr(client.s, 'get', get)
    client.get('winamax/soccer/events')
    client.get('winamax/basketball/events')
    assert len(appels) == 1 and client.requetes == 1


def test_json_et_horaires_invalides(client, monkeypatch):
    for data in ([], 'secret', ValueError('CLE_NE_PAS_LOGUER')):
        monkeypatch.setattr(client.s, 'get', lambda *a, **kw: Response(data))
        assert client.get('winamax/soccer/events') is None
    assert 'CLE_NE_PAS_LOGUER' not in json.dumps(client.erreurs)
    assert P._heure('2026-10-17T12:00:00') is None
    monkeypatch.setattr(client.s, 'get', lambda *a, **kw: Response({'events': [None,
        {'startTime': '2099-01-01T12:00:00'}, {'startTime': '2099-01-01T12:00:00Z'}]}))
    assert len(client.matchs('winamax', 'soccer', heures=1e7)) == 1


def test_client_resultats_partage_ne_bloque_pas_autre_bookmaker(client, monkeypatch):
    appels = []
    def get(url, **kw):
        appels.append(url)
        return Response(status=429, retry='7200') if '/winamax/' in url else Response({'events': []})
    monkeypatch.setattr(client.s, 'get', get)
    client.get('winamax/results')
    assert client.get('betclic/results') == {'events': []}
    assert client.get('winamax/soccer/events') is None
    assert len(appels) == 2


def test_etat_de_collecte_reutilise_par_les_resultats(monkeypatch):
    monkeypatch.setattr(P.time, 'sleep', lambda _: None)
    appels = []
    def get(self, url, **kw):
        appels.append(url)
        return Response(status=429, retry='7200')
    monkeypatch.setattr(requests.Session, 'get', get)
    etat = {}
    P.collecter('test', {'winamax': ['soccer', 'basketball']}, etat=etat)
    assert len(appels) == 1
    client = P.Client('test', pause=0, etat=json.loads(json.dumps(etat)))
    assert client.get('winamax/results') is None
    assert len(appels) == 1
