"""Connecteurs hors réseau : erreurs opaques, prix valides et reprise bornée."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess

import pytest
import requests

from cotes import pinnacle as P, polymarket as M, theodds as O

NOW=datetime(2026,10,17,11,tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def diagnostics_isoles(monkeypatch):
    for module in (P,M):
        module.ERREURS.clear()
        monkeypatch.setattr(module,'_bloque',False)
    yield
    P.ERREURS.clear();M.ERREURS.clear()


class Reponse:
    def __init__(self, data=None, status=200, invalide=False):
        self.data,self.status_code,self.invalide=data,status,invalide
        self.headers={};self.json_lu=False
    def json(self):
        self.json_lu=True
        if self.invalide:
            raise ValueError('secret-test-prive dans JSON invalide')
        return self.data


def appeler(module, essais=3):
    return module._get('/sports/29/matchups?withSpecials=true',essais=essais) if module is P else module._get('/events',{},essais=essais)


@pytest.mark.parametrize('module',[P,M])
@pytest.mark.parametrize('statut',[401,403,429])
def test_statut_bloquant_une_seule_requete_sans_fuite(module,statut,monkeypatch,caplog):
    calls=[];rep=Reponse(status=statut)
    monkeypatch.setenv('PINNACLE_API_KEY','secret-test-prive')
    monkeypatch.setattr(module.requests,'get',lambda *a,**kw:calls.append(kw) or rep)
    monkeypatch.setattr(module.time,'sleep',lambda _:pytest.fail('Aucun délai après un statut bloquant'))
    assert appeler(module) is None and appeler(module) is None
    assert len(calls)==1 and not rep.json_lu and f'HTTP {statut}' in ' '.join(module.ERREURS)
    assert 'secret-test-prive' not in caplog.text+json.dumps(module.ERREURS)


@pytest.mark.parametrize('module',[P,M])
def test_reessais_500_bornes_et_pas_de_sleep_apres_dernier_echec(module,monkeypatch):
    calls=[];delais=[]
    monkeypatch.setattr(module.requests,'get',lambda *a,**kw:calls.append(1) or Reponse(status=503))
    monkeypatch.setattr(module.time,'sleep',delais.append)
    assert appeler(module) is None and len(calls)==3 and delais==[2,4]


@pytest.mark.parametrize('module',[P,M])
def test_reprise_apres_panne_reseau_sans_texte_exception(module,monkeypatch,caplog):
    n=0
    def get(*a,**kw):
        nonlocal n
        n+=1
        if n==1:raise requests.Timeout('secret-test-prive URL et en-têtes')
        return Reponse([{'id':1}])
    monkeypatch.setattr(module.requests,'get',get)
    monkeypatch.setattr(module.time,'sleep',lambda _:None)
    assert appeler(module)==[{'id':1}] and n==2
    assert 'secret-test-prive' not in caplog.text+json.dumps(module.ERREURS)


@pytest.mark.parametrize('module',[P,M])
@pytest.mark.parametrize('rep',[Reponse(invalide=True),Reponse({}),Reponse(None),Reponse(status=404)])
def test_json_schema_et_http_permanent_sans_reessai(module,rep,monkeypatch,caplog):
    calls=[]
    monkeypatch.setattr(module.requests,'get',lambda *a,**kw:calls.append(1) or rep)
    monkeypatch.setattr(module.time,'sleep',lambda _:pytest.fail('Pas de réessai de schéma ou HTTP 404'))
    assert appeler(module) is None and len(calls)==1 and module.ERREURS
    assert 'secret-test-prive' not in caplog.text+json.dumps(module.ERREURS)


def test_configuration_pinnacle_dynamique_et_fichiers_env_proteges(monkeypatch):
    monkeypatch.setenv('PINNACLE_API_KEY',' secret-test-prive ')
    assert P.headers()['X-API-Key']=='secret-test-prive' and 'X-API-Key' not in P.HEADERS
    monkeypatch.delenv('PINNACLE_API_KEY')
    assert P.headers()['X-API-Key']==P.CLE_GUEST_PAR_DEFAUT
    racine=Path(__file__).resolve().parents[1]
    r=subprocess.run(['git','check-ignore','--stdin'],cwd=racine,input='.env\n.env.local\n.env.example\n',
                     text=True,capture_output=True)
    assert r.stdout.splitlines()==['.env','.env.local']
    assert 'PINNACLE_API_KEY=' in (racine/'.env.example').read_text()
    for wf in ['collecte.yml','sonde-live.yml','verif.yml']:
        assert 'PINNACLE_API_KEY: ${{ secrets.PINNACLE_API_KEY }}' in (racine/'.github/workflows'/wf).read_text()


@pytest.mark.parametrize('prix,attendu',[(150,2.5),(-200,1.5),('150',2.5),
    (None,None),('',None),('abc',None),(0,None),(True,None),
    (float('nan'),None),(float('inf'),None),(-float('inf'),None)])
def test_conversion_americaine_non_finie_ou_invalide(prix,attendu):
    assert P.americaine_vers_decimale(prix)==attendu


def marche_pin(**kw):
    return {'matchupId':1,'type':'moneyline','key':'m1','period':0,'status':'open',
            'prices':[{'designation':'home','price':-110},{'designation':'away','price':-110}],**kw}


def matchup():
    return {'id':1,'type':'matchup','isLive':False,'startTime':'2026-10-17T18:00:00Z',
            'participants':[{'alignment':'home','name':'A'},{'alignment':'away','name':'B'}],
            'league':{'name':'L'}}


def test_collecte_pinnacle_isole_marche_invalide_et_garde_un_marche_complet(monkeypatch):
    bon=marche_pin()
    mauvais=marche_pin(key='bad',prices=[{'designation':'home','price':'abc'},{'designation':'away','price':120}])
    values=[[None,matchup()],[None,mauvais,{'matchupId':{}},bon]]
    monkeypatch.setattr(P,'_get',lambda *a:values.pop(0))
    out=P.collecter({29:'football'})
    assert len(out)==2 and {l['issue'] for l in out}=={'DOM','EXT'}
    assert sum(l['proba_juste'] for l in out)==pytest.approx(1)
    assert all(l['collecte']==l['collecte_recue'] for l in out) and P.ERREURS


def _groupe_special(marche, issues):
    return [{"cle_marche": "s", "marche": marche, "issue": issue, "cote": 2.1,
             "match_id": 1, "periode": "MATCH", "ligne": None, "joueur": None} for issue in issues]


def test_special_incomplet_ne_recoit_pas_de_proba_juste():
    for marche, issues in (
        ("SPECIAL:3-Way Handicap DOM -1", ["Lens (-1)", "Lille (+1)"]),
        ("SPECIAL:Draw No Bet", ["DOM", "EXT", "NUL"]),
        ("SPECIAL:Both Teams To Score?", ["Yes", "No", "Maybe"]),
    ):
        rows = _groupe_special(marche, issues)
        P._ajouter_proba_justes(rows)
        assert all(l["proba_juste"] is None for l in rows)


def test_handicap_europeen_complet_garde_une_proba():
    rows = _groupe_special("SPECIAL:3-Way Handicap DOM -1", ["Lens (-1)", "Draw", "Lille (+1)"])
    P._ajouter_proba_justes(rows)
    assert sum(l["proba_juste"] for l in rows) == pytest.approx(1, abs=1e-5)


@pytest.mark.parametrize('change',[{'cote':None},{'cote':'abc'},{'cote':True},{'cote':float('inf')},
                                  {'issue':'DOM'},{'ligne':3}])
def test_cote_ou_composition_invalide_ne_produit_pas_de_proba_juste(change):
    rows=[{'cle_marche':'x','marche':'VAINQUEUR','issue':'DOM','cote':2.},
          {'cle_marche':'x','marche':'VAINQUEUR','issue':'EXT','cote':2.,**change}]
    P._ajouter_proba_justes(rows)
    assert all(l['proba_juste'] is None for l in rows)


def marche_poly(**kw):
    return {'id':'m1','sportsMarketType':'totals','acceptingOrders':True,'closed':False,
            'bestBid':.48,'bestAsk':.52,'outcomes':'["Over", "Under"]','line':2.5,'liquidityNum':1000,**kw}


BASE_POLY={'source':'polymarket','sport':'football','match_id':'e1','domicile':'A','exterieur':'B',
           'collecte':NOW.isoformat(),'debut':'2026-10-17T18:00:00Z'}


@pytest.mark.parametrize('change',[{'bestBid':'abc'},{'bestAsk':'abc'},{'bestBid':None},
    {'bestBid':True},{'bestBid':float('nan')},{'bestAsk':float('inf')},{'bestBid':.7,'bestAsk':.6},
    {'bestBid':0},{'bestAsk':1},{'line':'abc'},{'line':None},{'outcomes':'{}'},
    {'outcomes':'["Over",null]'},{'outcomes':'["Over","Over"]'},{'closed':'false'},
    {'acceptingOrders':'false'}])
def test_polymarket_prix_ligne_et_issues_invalides_isoles(change):
    bon=marche_poly(id='bon')
    rows=M._lignes([marche_poly(**change),bon],BASE_POLY,'A','B','football')
    assert len(rows)==2 and all(l['cle_marche']=='pm|bon' for l in rows)
    assert sum(l['proba_juste'] for l in rows)==pytest.approx(1)


@pytest.mark.parametrize('liquidite',[None,'abc',True,-5,float('nan'),float('inf')])
def test_liquidite_inconnue_n_est_pas_inventee(liquidite):
    from cotes.comparaison import _fiable
    out=M._lignes([marche_poly(liquidityNum=liquidite)],BASE_POLY,'A','B','football')
    assert len(out)==2 and all(l['liquidite']==0 for l in out)
    assert all(not _fiable('Polymarket',l) for l in out)


@pytest.mark.parametrize('date',[None,'invalide','2026-10-17T12:00:00','2026-10-16T12:00:00Z'])
def test_evenement_hors_horizon_ou_sans_date(date):
    assert not M.dans_horizon({'id':'1','startTime':date},NOW)


def test_pagination_polymarket_signale_une_liste_coupee(monkeypatch):
    monkeypatch.setattr(M, "_get", lambda *a, **k: [{"id": i} for i in range(100)])
    M.evenements()
    assert "liste d'événements tronquée (plafond de pagination)" in M.ERREURS


def test_date_et_lecture_par_page_ne_sont_pas_remplacees_par_fin_collecte(monkeypatch):
    class Horloge(datetime):
        n=0
        @classmethod
        def now(cls,tz=None):
            cls.n+=1
            return NOW+timedelta(seconds=cls.n)
    monkeypatch.setattr(M,'datetime',Horloge)
    pages=[ [{'id':'e1','title':'A vs. B','startTime':'2026-10-17 18:00:00+00:00',
              'markets':[marche_poly()]}],
            [{'id':'e2','title':'C vs. D','startTime':'2026-10-17T18:00:00Z',
              'markets':[marche_poly(id='m2')]}] ]
    monkeypatch.setattr(M,'_get',lambda *a:pages.pop(0))
    out=M.collecter()
    assert len(out)==4 and len({l['collecte'] for l in out})==2
    assert all(l['debut']=='2026-10-17T18:00:00+00:00' for l in out)
    assert all(l['collecte']==l['collecte_recue'] for l in out)


def test_1n2_exige_les_trois_issues_et_garde_la_plus_ancienne_lecture():
    rows=[{**BASE_POLY,'marche':'RESULTAT_1N2','periode':'MATCH','issue':i,'proba_juste':p,
           'collecte':(NOW+timedelta(seconds=j)).isoformat()}
          for j,(i,p) in enumerate([('DOM',.46),('NUL',.28),('EXT',.24)])]
    bon=deepcopy(rows)
    M._normaliser_1n2(bon)
    assert sum(l['proba_juste'] for l in bon)==pytest.approx(1,abs=2e-5)
    assert {l['collecte'] for l in bon}=={NOW.isoformat()}
    for mauvais in [deepcopy(rows[:2]),[deepcopy(rows[0]),deepcopy(rows[0]),deepcopy(rows[2])]]:
        M._normaliser_1n2(mauvais)
        assert all(l['proba_juste'] is None for l in mauvais)


def test_prix_post_match_ne_devient_pas_cloture_pre_match_par_normalisation():
    base={**BASE_POLY,'debut':NOW.isoformat()}
    assert not M._lignes([marche_poly()],base,'A','B','football')
    rows=[{**base,'marche':'RESULTAT_1N2','periode':'MATCH','issue':i,'proba_juste':p,
           'collecte':(NOW+timedelta(seconds=j)).isoformat()}
          for j,(i,p) in zip([-60,-30,1],[('DOM',.46),('NUL',.28),('EXT',.24)])]
    M._normaliser_1n2(rows)
    assert all(l['proba_juste'] is None for l in rows)


def test_theodds_json_invalide_distinct_sans_rembourser_quota_ni_fuite():
    from tests.test_theodds import NOW as T,KEY
    class Http:
        calls=0
        def get(self,*a,**kw):
            self.calls+=1
            return Reponse(invalide=True)
    http=Http();cache={}
    client=O.Client(['secret-test-prive'],cache,T,http)
    etat=client.comptes[0][1];etat.update(valide=True,sports=[KEY])
    assert client.scores(KEY) is None and http.calls==1
    assert etat['credits_mois']==etat['credits_jour']==O.COUT
    assert client.erreurs==['compte 1 : JSON invalide']
    assert 'secret-test-prive' not in json.dumps([client.erreurs,cache])


def test_diagnostic_pinnacle_remonte_dans_cycle_sans_cle(monkeypatch):
    from scripts import cycle
    def pin():
        P.ERREURS.append('sport 29 matchups : HTTP 429')
        return []
    monkeypatch.setattr(P,'collecter',pin)
    monkeypatch.setattr(M,'collecter',lambda *a:[])
    monkeypatch.setattr(cycle.kalshi,'collecter',lambda *a:[])
    monkeypatch.setenv('PINNACLE_API_KEY','secret-test-prive')
    journal={'etapes':{}}
    cycle.collecter_prematch(None,'test',NOW,journal)
    assert journal['etapes']['pinnacle']['degrade'] is True
    assert 'HTTP 429' in journal['etapes']['pinnacle']['erreurs'][0]
    assert journal['pinnacle_configuration']=={'mode':'environnement'}
    assert 'secret-test-prive' not in json.dumps(journal)
