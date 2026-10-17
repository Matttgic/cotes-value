"""Pannes et cotations incomplètes : aucune API réelle n'est sollicitée."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest
import requests

from cotes import kalshi as K


@pytest.fixture(autouse=True)
def reset(monkeypatch):
    K.ERREURS.clear()
    K._bloque.clear()
    monkeypatch.setattr(K.time, 'sleep', lambda _: None)


class Response:
    def __init__(self, data=None, status=200):
        self.data, self.status_code = data, status
    def json(self):
        if isinstance(self.data, Exception):
            raise self.data
        return self.data


@pytest.mark.parametrize('status', [401, 403, 404, 429, 500, 503])
def test_http_diagnostic_borne_sans_url_et_coupe_refus(monkeypatch, caplog, status):
    appels = []
    def get(*a, **kw):
        appels.append(kw)
        return Response(status=status)
    monkeypatch.setattr(K.requests, 'get', get)
    assert K._get('/events?secret=NE_PAS_LOGUER', {'token': 'NE_PAS_LOGUER'}) is None
    assert len(appels) == (3 if status >= 500 else 1)
    assert K.ERREURS == [f'HTTP {status}']
    if status in (401, 403, 429):
        K._get('/series')
        assert len(appels) == 1
    assert 'NE_PAS_LOGUER' not in caplog.text


def test_reseau_json_et_type_invalides_sans_fuite(monkeypatch, caplog):
    def get(*a, **kw):
        raise requests.Timeout('https://secret?key=NE_PAS_LOGUER')
    monkeypatch.setattr(K.requests, 'get', get)
    assert K._get('/events') is None
    assert K.ERREURS == ['réseau indisponible']
    for data in ([], 'x', ValueError('NE_PAS_LOGUER')):
        monkeypatch.setattr(K.requests, 'get', lambda *a, **kw: Response(data))
        assert K._get('/events') is None
    assert 'NE_PAS_LOGUER' not in caplog.text


@pytest.mark.parametrize('nom', ['Draw', 'Tie', 'Draw (90 mins)', 'Tie (regulation time)'])
def test_nul_variantes_connues(nom):
    assert K.est_nul(nom)


@pytest.mark.parametrize('nom', ['Arsenal', 'Tielemans FC', 'Drawbridge', 'Tie-break', None])
def test_nul_ne_confond_pas_un_prefixe(nom):
    assert not K.est_nul(nom)


def evenement():
    now = datetime.now(timezone.utc)
    return {'event_ticker': 'E1', 'title': 'Lens vs. Lille', 'markets': [
        {'status': 'open', 'yes_sub_title': name, 'yes_bid_dollars': bid,
         'yes_ask_dollars': ask, 'open_interest_fp': 'invalide',
         'occurrence_datetime': (now + timedelta(hours=6)).isoformat()}
        for name, bid, ask in [('Lens', '.38', '.40'), ('Lille', '.30', '.32'),
                               ('Draw (90 mins)', '.28', '.30')]]}


def test_horodatage_par_page_et_curseur_repete(monkeypatch):
    appels = []
    def get(*a, **kw):
        appels.append(kw)
        return Response({'events': [evenement()], 'cursor': 'identique'})
    monkeypatch.setattr(K.requests, 'get', get)
    rows = K._evenements('SOCCERGAME')
    assert len(appels) == 2 and len(rows) == 1
    assert rows[0]['_collecte']
    assert 'curseur invalide ou répété' in K.ERREURS


def collect(monkeypatch, event):
    monkeypatch.setattr(K, 'series_matchs', lambda: [('SOCCERGAME', 'football')])
    monkeypatch.setattr(K, '_evenements', lambda *a: [event])
    return K.collecter()


def test_cotes_completes_normalisees_et_heure_reelle_page(monkeypatch):
    event = {**evenement(), '_collecte': '2026-10-17T11:22:33Z'}
    original = deepcopy(event)
    rows = collect(monkeypatch, event)
    assert len(rows) == 3 and abs(sum(r['proba_juste'] for r in rows) - 1) < 1e-5
    assert {r['collecte'] for r in rows} == {'2026-10-17T11:22:33Z'}
    assert {r['issue'] for r in rows} == {'Lens', 'Lille', 'NUL'}
    assert all(r['liquidite'] == 0 and r['debut_approximatif'] for r in rows)
    assert event == original


@pytest.mark.parametrize('changement', [
    {'yes_bid_dollars': None}, {'yes_bid_dollars': True}, {'yes_bid_dollars': 'nan'},
    {'yes_ask_dollars': 'inf'}, {'yes_bid_dollars': '.8', 'yes_ask_dollars': '.7'},
    {'status': 'closed'}, {'yes_sub_title': 'Lens'},
])
def test_aucune_renormalisation_si_une_issue_invalide(monkeypatch, changement):
    event = {**evenement(), '_collecte': '2026-10-17T11:00:00Z'}
    event['markets'][-1].update(changement)
    assert collect(monkeypatch, event) == []


def test_schema_invalide_isole(monkeypatch):
    monkeypatch.setattr(K, '_get', lambda *a: {'series': 42})
    assert K.series_matchs() == []
    monkeypatch.setattr(K, '_get', lambda *a: {'series': [None, {'ticker': 'GAME', 'tags': 42}]})
    assert K.series_matchs() == []
    monkeypatch.setattr(K, '_get', lambda *a: {'events': 42})
    assert K._evenements('GAME') == []


@pytest.mark.parametrize('retard_estime', [-120, 120])
def test_placement_et_cloture_utilisent_horaire_francais(monkeypatch, retard_estime):
    from cotes import comparaison, simulation
    now = datetime(2026, 10, 17, 12, tzinfo=timezone.utc)
    debut_fr = now + timedelta(minutes=20)
    base = {'sport': 'football', 'ligue': 'L1', 'domicile': 'Lens', 'exterieur': 'Lille',
            'collecte': now.isoformat(), 'marche': 'VAINQUEUR', 'periode': 'MATCH',
            'ligne': None, 'issue': 'DOM', 'joueur': None}
    fr = {**base, 'source': 'PMU', 'bookmaker': 'pmu', 'match_id': 'pmu|1',
          'debut': debut_fr.isoformat(), 'cote': 2.2}
    ref = {**base, 'source': 'kalshi', 'match_id': 'K1', 'proba_juste': .5,
           'debut': (debut_fr + timedelta(minutes=retard_estime)).isoformat(),
           'debut_approximatif': True, 'ecart_achat_vente': .02, 'liquidite': 100}
    opportunites = comparaison.comparer([fr], {'Kalshi': [ref]})
    assert len(opportunites) == 1 and opportunites[0]['debut'] == fr['debut']
    paris = []
    assert simulation.placer(opportunites, paris, maintenant=now)
    assert not simulation.placer(opportunites, [], maintenant=debut_fr + timedelta(seconds=1))
    index = comparaison.index_cotes_justes([fr], {'Kalshi': [ref]})
    simulation.suivre_cloture(paris, index, maintenant=debut_fr + timedelta(minutes=1))
    assert paris[0]['cloture_lue'] == now.isoformat(timespec='seconds')
