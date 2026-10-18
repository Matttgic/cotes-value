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
    P._ages.clear()
    P._statuts.clear()
    P._plans.clear()
    P.oublier_cle()
    monkeypatch.delenv('PINNACLE_RECHAUFFEUR_URL', raising=False)
    monkeypatch.delenv('PINNACLE_RECHAUFFEUR_SECRET', raising=False)
    monkeypatch.delenv('PINNACLE_PROXY_URL', raising=False)
    monkeypatch.setattr(P,'_cle_dynamique',lambda: None)
    yield
    P.ERREURS.clear();M.ERREURS.clear()
    P.oublier_cle()


class Reponse:
    def __init__(self, data=None, status=200, invalide=False, headers=None):
        self.data,self.status_code,self.invalide=data,status,invalide
        self.headers={} if headers is None else headers
        self.json_lu=False
    def json(self):
        self.json_lu=True
        if self.invalide:
            raise ValueError('secret-test-prive dans JSON invalide')
        return self.data


def appeler(module, essais=3):
    return module._get('/sports/29/matchups?withSpecials=true',essais=essais) if module is P else module._get('/events',{},essais=essais)


@pytest.mark.parametrize('module,statut',[(M,401),(M,403),(M,429),(P,401),(P,429)])
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
    P.oublier_cle()
    assert P.headers()['X-API-Key']=='secret-test-prive' and 'X-API-Key' not in P.HEADERS
    assert P.origine_cle=='environnement'
    monkeypatch.delenv('PINNACLE_API_KEY')
    P.oublier_cle()
    assert P.headers()['X-API-Key']==P.CLE_GUEST_PAR_DEFAUT
    assert P.origine_cle=='guest_historique'
    racine=Path(__file__).resolve().parents[1]
    r=subprocess.run(['git','check-ignore','--stdin'],cwd=racine,input='.env\n.env.local\n.env.example\n',
                     text=True,capture_output=True)
    assert r.stdout.splitlines()==['.env','.env.local']
    exemple=(racine/'.env.example').read_text()
    assert 'PINNACLE_API_KEY=' in exemple and 'PINNACLE_AGE_MAX_MIN=' in exemple
    assert 'PINNACLE_RECHAUFFEUR_URL=' in exemple and 'PINNACLE_RECHAUFFEUR_SECRET=' in exemple
    assert 'PINNACLE_PROXY_URL=' in exemple
    for wf in ['collecte.yml','sonde-live.yml','verif.yml']:
        texte=(racine/'.github/workflows'/wf).read_text()
        assert 'PINNACLE_API_KEY: ${{ secrets.PINNACLE_API_KEY }}' in texte
        assert 'PINNACLE_RECHAUFFEUR_URL: ${{ secrets.PINNACLE_RECHAUFFEUR_URL }}' in texte
        assert 'PINNACLE_RECHAUFFEUR_SECRET: ${{ secrets.PINNACLE_RECHAUFFEUR_SECRET }}' in texte


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
    monkeypatch.setattr(cycle.pmu_direct,'collecter',lambda *a,**k:([], {'ok':True,'erreurs':[],'requetes':0,'matchs':0}))
    monkeypatch.delenv('SOURCE_PMU', raising=False)
    monkeypatch.setenv('PINNACLE_API_KEY','secret-test-prive')
    journal={'etapes':{}}
    cycle.collecter_prematch(None,'test',NOW,journal)
    assert journal['etapes']['pinnacle']['degrade'] is True
    assert 'HTTP 429' in journal['etapes']['pinnacle']['erreurs'][0]
    assert journal['pinnacle_configuration']=={'mode':'environnement'}
    assert journal['pinnacle_fraicheur']['seuil_min']==10
    assert journal['pinnacle_fraicheur']['lignes_perimees']==0
    assert 'secret-test-prive' not in json.dumps(journal)


def test_403_pinnacle_na_bloque_pas_le_sport_suivant(monkeypatch):
    calls=[]
    monkeypatch.setattr(P.requests,'get',lambda *a,**kw:calls.append(1) or Reponse(status=403))
    monkeypatch.setattr(P.time,'sleep',lambda _:pytest.fail('Aucun réessai après un 403'))
    assert appeler(P) is None and appeler(P) is None
    assert len(calls)==2 and P._bloque is False and 'HTTP 403' in ' '.join(P.ERREURS)


def test_403_dun_sport_laisse_passer_le_suivant(monkeypatch):
    urls=[]
    def get(url, **kw):
        urls.append(url)
        if '/sports/13/' in url:
            return Reponse(status=403)
        if 'matchups' in url:
            return Reponse([matchup()])
        return Reponse([marche_pin()])
    monkeypatch.setattr(P.requests,'get',get)
    monkeypatch.setattr(P.time,'sleep',lambda _:pytest.fail('Aucun réessai après un 403'))
    out=P.collecter({13:'hockey_sur_gazon',29:'football'})
    assert len(out)==2 and {l['issue'] for l in out}=={'DOM','EXT'}
    assert P._bloque is False
    assert any('sport 13 matchups : HTTP 403' in e for e in P.ERREURS)
    assert any('/sports/29/' in u for u in urls)


def test_sports_anj_ordre_et_identifiants():
    ids=list(P.SPORTS)
    assert ids[:8]==[29,33,4,19,18,34,27,15]
    assert P.SPORTS[28]=='snooker' and P.SPORTS[13]=='hockey_sur_gazon'
    assert P.SPORTS[26]=='rugby_league' and P.SPORTS[17]=='golf'
    assert P.SPORTS[9]=='curling' and P.SPORTS[45]=='cyclisme'
    assert {1,5,37,39}<=set(P.SPORTS)
    assert not ({8,10,12}&set(P.SPORTS))


def test_special_sans_statut_survit_et_prix_unique_silencieux(monkeypatch):
    parent=matchup()
    parent['participants']=[{'alignment':'home','name':'Lens'},{'alignment':'away','name':'Lille'}]
    special={'id':2,'type':'special','parentId':1,'isLive':False,
             'participants':[{'id':10,'name':'Yes'},{'id':11,'name':'No'}],
             'special':{'category':'Game Props','description':'Both Teams To Score?'}}
    ouvert={'matchupId':2,'key':'btts',
            'prices':[{'participantId':10,'price':-120},{'participantId':11,'price':100}]}
    incomplet={'matchupId':2,'key':'seul','prices':[{'participantId':10,'price':-120}]}
    ferme={**ouvert,'key':'ferme','status':'closed'}
    sans_statut=marche_pin()
    del sans_statut['status']
    values=[[parent,special],[incomplet,ferme,ouvert,sans_statut]]
    monkeypatch.setattr(P,'_get',lambda *a:values.pop(0))
    out=P.collecter({29:'football'})
    assert {l['marche'] for l in out}>={'SPECIAL:Both Teams To Score?','VAINQUEUR'}
    assert not any('liste de prix invalide' in e for e in P.ERREURS)
    assert all(l['age_cache_s'] is None and l['cote_perimee'] is True for l in out)
    from cotes.marches import harmoniser_pinnacle
    assert any(l['marche']=='BOTH_TEAMS_TO_SCORE' for l in harmoniser_pinnacle(out))


def test_marche_ordinaire_a_un_seul_prix_reste_signale(monkeypatch):
    mauvais=marche_pin(prices=[{'designation':'home','price':-110}])
    monkeypatch.setattr(P,'_get',lambda *a:[matchup()] if 'matchups' in a[0] else [mauvais])
    assert P.collecter({29:'football'})==[]
    assert any('liste de prix invalide' in e for e in P.ERREURS)


def test_age_http_perime_frais_ou_absent(monkeypatch):
    monkeypatch.setenv('PINNACLE_AGE_MAX_MIN','10')
    def lire(age):
        def get(url, **kw):
            entetes={'Age':age} if age is not None else {}
            if 'markets' in url:
                return Reponse([marche_pin()], headers=entetes)
            return Reponse([matchup()])
        monkeypatch.setattr(P.requests,'get',get)
        return P.collecter({29:'football'})
    vieux=lire('601')
    assert vieux and all(l['cote_perimee'] and l['age_cache_s']==601 for l in vieux)
    frais=lire('600')
    assert frais and all(l['cote_perimee'] is False and l['age_cache_s']==600 for l in frais)
    inconnu=lire(None)
    assert inconnu and all(l['cote_perimee'] is True and l['age_cache_s'] is None for l in inconnu)
    illisible=lire('abc')
    assert illisible and all(l['age_cache_s'] is None and l['cote_perimee'] is True for l in illisible)


def test_cle_du_site_prime_sans_etre_journalisee(monkeypatch, caplog):
    site='cle-site-ne-pas-journaliser'
    monkeypatch.setattr(P,'_cle_dynamique',lambda: site)
    monkeypatch.setenv('PINNACLE_API_KEY','secret-test-prive')
    P.oublier_cle()
    assert P.headers()['X-API-Key']==site and P.origine_cle=='site'
    appels={'n':0}
    def autre():
        appels['n']+=1
        return 'autre-cle'
    monkeypatch.setattr(P,'_cle_dynamique',autre)
    assert P.headers()['X-API-Key']==site and appels['n']==0
    assert site not in caplog.text+json.dumps(P.ERREURS)
    assert 'secret-test-prive' not in caplog.text+json.dumps(P.ERREURS)


def test_lecture_app_json_extrait_la_cle_sans_journaliser_le_corps(monkeypatch, caplog):
    site='cle-app-json-secrete'
    class R:
        status_code=200
        text=site+' ne doit pas sortir'
        def json(self):
            return {'api':{'haywire':{'apiKey':'  '+site+'  '}}}
    monkeypatch.setattr(P.requests,'get',lambda *a,**kw: R())
    assert P._lire_cle_site()==site
    assert P._cle_depuis_config({}) is None
    assert P._cle_depuis_config({'api':{'haywire':{'apiKey':''}}}) is None
    assert P._cle_depuis_config({'api':{'haywire':{'apiKey':12}}}) is None
    def panne(*a,**kw):
        raise requests.Timeout(site+' dans exception')
    monkeypatch.setattr(P.requests,'get',panne)
    assert P._lire_cle_site() is None
    assert site not in caplog.text+json.dumps(P.ERREURS)


def test_perimetre_anj_et_cote_perimee_ne_declenchent_pas_de_pari():
    from cotes.comparaison import comparer, _fiable
    from cotes.marches import cle
    from tests.test_controle import ligne
    ref={**ligne(),'source':'pinnacle','match_id':'p1','cote':1.9,
         'proba_juste':.5,'marge_pinnacle':.04,'cote_perimee':True,'age_cache_s':700}
    assert _fiable('Pinnacle', ref) is False
    assert comparer([ligne(cote=2.2)],{'Pinnacle':[ref]})==[]
    frais={**ref,'cote_perimee':False,'age_cache_s':30}
    assert _fiable('Pinnacle', frais) is True
    out=comparer([ligne(cote=2.2)],{'Pinnacle':[frais]})
    assert any(o['reference']=='Pinnacle' and o['pariable'] for o in out)
    brut={**frais,'cote':1.8,'proba_juste':.55}
    for marche, libelle in (
        ('CORNERS_TOTAL','Plus de corners'),
        ('CARTONS_TOTAL','Nombre de cartons'),
        ('TOTAL','Nombre de buts Pair / Impair'),
        ('TOTAL','Goals Odd/Even'),
    ):
        fr=ligne(marche=marche, libelle=libelle, cote=2.2)
        index={'Pinnacle':{fr['match_id']:{cle(fr):{**brut,'proba_juste':.55,'cote':1.8}}}}
        assert comparer([fr],{'Pinnacle':[]},index=index)==[]


def test_age_max_entete_et_horodatage_rechauffeur():
    maintenant=datetime(2026,10,18,2,tzinfo=timezone.utc)
    chemin='/sports/29/markets/straight?withSpecials=true'
    P._ages[chemin]=30
    P._plans[29]={'markets':chemin,'fresh':True,'t':(maintenant-timedelta(seconds=90)).isoformat()}
    age,perime=P._age_ligne(chemin,29,maintenant)
    assert age==90 and perime is False
    P._ages[chemin]=700
    age,perime=P._age_ligne(chemin,29,maintenant)
    assert age==700 and perime is True
    # Un HIT sans Age ne devient pas frais parce que le réchauffeur vient de répondre.
    P._ages[chemin]=None
    P._plans[29]={'markets':chemin,'fresh':False,'age_s':None,
                  't':maintenant.isoformat()}
    age,perime=P._age_ligne(chemin,29,maintenant)
    assert age is None and perime is True
    P._plans[29]['age_s']=290
    age,perime=P._age_ligne(chemin,29,maintenant)
    assert age==290 and perime is False
    P._plans[29]['age_s']=700
    age,perime=P._age_ligne(chemin,29,maintenant)
    assert age==700 and perime is True
    P._ages['/sports/29/markets/straight']=None
    P._plans.clear()
    age,perime=P._age_ligne('/sports/29/markets/straight',29,maintenant)
    assert age is None and perime is True


def test_rechauffeur_impose_les_chemins_et_un_age_sans_entete(monkeypatch,caplog):
    monkeypatch.setenv('PINNACLE_RECHAUFFEUR_URL','https://exemple.test/rechauffe')
    monkeypatch.setenv('PINNACLE_RECHAUFFEUR_SECRET','secret-rechauffe')
    monkeypatch.setattr(P,'_cle_dynamique',lambda: 'cle-de-cycle')
    vu={}
    def post(url, json=None, headers=None, timeout=None):
        vu.update(url=url, corps=json, headers=headers, timeout=timeout)
        return Reponse({'29':{
            'matchups':'/sports/29/matchups?withSpecials=true&_=abc',
            'markets':'/sports/29/markets/straight?withSpecials=true',
            't':datetime.now(timezone.utc).isoformat(),
            'cache':'MISS','fresh':True,'age_s':None,
        }})
    urls=[]
    def get(url, **kw):
        urls.append(url)
        if 'matchups' in url:
            return Reponse([matchup()])
        return Reponse([marche_pin()])
    monkeypatch.setattr(P.requests,'post',post)
    monkeypatch.setattr(P.requests,'get',get)
    out=P.collecter({29:'football'})
    assert vu['url']=='https://exemple.test/rechauffe' and vu['timeout']==120
    assert vu['headers']['x-region']=='eu-west-3' and vu['headers']['x-secret']=='secret-rechauffe'
    assert vu['corps']=={'sports':[29],'key':'cle-de-cycle'}
    assert any(u.endswith('/sports/29/matchups?withSpecials=true&_=abc') for u in urls)
    assert any(u.endswith('/sports/29/markets/straight?withSpecials=true') for u in urls)
    assert out and all(l['cote_perimee'] is False and 0<=l['age_cache_s']<30 for l in out)
    assert 'cle-de-cycle' not in caplog.text+json.dumps(P.ERREURS)
    assert 'secret-rechauffe' not in caplog.text+json.dumps(P.ERREURS)


def test_hit_sans_age_reste_perime_et_age_s_est_utilise(monkeypatch):
    monkeypatch.setenv('PINNACLE_RECHAUFFEUR_URL','https://exemple.test/rechauffe')
    monkeypatch.setenv('PINNACLE_RECHAUFFEUR_SECRET','secret-rechauffe')
    monkeypatch.setattr(P,'_cle_dynamique',lambda: 'cle-de-cycle')
    plans=[{'29':{'matchups':'/sports/29/matchups?withSpecials=true&_=abc',
                  'markets':'/sports/29/markets/straight?withSpecials=true',
                  't':datetime.now(timezone.utc).isoformat(),'cache':'HIT','fresh':False,'age_s':None}},
           {'29':{'matchups':'/sports/29/matchups?withSpecials=true&_=abc',
                  'markets':'/sports/29/markets/straight?withSpecials=true',
                  't':datetime.now(timezone.utc).isoformat(),'cache':'HIT','fresh':False,'age_s':290}}]
    monkeypatch.setattr(P.requests,'post',lambda *a, **k: Reponse(plans.pop(0)))
    monkeypatch.setattr(P.requests,'get',lambda url, **kw: (
        Reponse([matchup()]) if 'matchups' in url else Reponse([marche_pin()])))
    inconnu=P.collecter({29:'football'})
    assert inconnu and all(l['cote_perimee'] is True and l['age_cache_s'] is None for l in inconnu)
    connu=P.collecter({29:'football'})
    assert connu and all(l['cote_perimee'] is False and l['age_cache_s']==290 for l in connu)


def test_rechauffeur_en_panne_garde_les_url_habituelles(monkeypatch,caplog):
    monkeypatch.setenv('PINNACLE_RECHAUFFEUR_URL','https://exemple.test/rechauffe')
    monkeypatch.setenv('PINNACLE_RECHAUFFEUR_SECRET','secret-rechauffe')
    def post(*a, **k):
        raise requests.Timeout('secret-rechauffe dans le message')
    urls=[]
    def get(url, **kw):
        urls.append(url)
        if 'matchups' in url:
            return Reponse([matchup()], headers={'Age':'12'})
        return Reponse([marche_pin()], headers={'Age':'12'})
    monkeypatch.setattr(P.requests,'post',post)
    monkeypatch.setattr(P.requests,'get',get)
    out=P.collecter({29:'football'})
    assert any(u.endswith('/sports/29/matchups?withSpecials=true') for u in urls)
    assert any(u.endswith('/sports/29/markets/straight?primaryOnly=false&withSpecials=true') for u in urls)
    assert out and all(l['age_cache_s']==12 and l['cote_perimee'] is False for l in out)
    assert 'secret-rechauffe' not in caplog.text+json.dumps(P.ERREURS)


def test_chemin_rechauffe_invalide_et_proxy(monkeypatch):
    monkeypatch.setenv('PINNACLE_RECHAUFFEUR_URL','https://exemple.test/rechauffe')
    monkeypatch.setenv('PINNACLE_RECHAUFFEUR_SECRET','secret-rechauffe')
    monkeypatch.setenv('PINNACLE_PROXY_URL','https://proxy.exemple.test/pinnacle/')
    monkeypatch.setattr(P,'_cle_dynamique',lambda: 'cle-de-cycle')
    monkeypatch.setattr(P.requests,'post',lambda *a, **k: Reponse({'29':{
        'matchups':'https://evil.exemple/vol','markets':'/sports/29/markets/straight?primaryOnly=false',
        't':datetime.now(timezone.utc).isoformat(),'cache':'MISS'}}))
    urls=[]
    monkeypatch.setattr(P.requests,'get',lambda url, **kw: urls.append(url) or (
        Reponse([matchup()], headers={'Age':'4'}) if 'matchups' in url else Reponse([marche_pin()], headers={'Age':'4'})))
    out=P.collecter({29:'football'})
    assert urls[0]=='https://proxy.exemple.test/pinnacle/sports/29/matchups?withSpecials=true'
    assert any(u.endswith('/sports/29/markets/straight?primaryOnly=false') for u in urls)
    assert not any('evil.exemple' in u for u in urls)
    assert out and all(l['age_cache_s']==4 and l['cote_perimee'] is False for l in out)


def test_statut_cache_origine_est_frais_sans_entete_age():
    maintenant=datetime(2026,10,18,2,tzinfo=timezone.utc)
    chemin='/sports/29/markets/straight?withSpecials=true'
    P._ages[chemin]=None
    for statut in ('MISS','EXPIRED','DYNAMIC'):
        P._statuts[chemin]=statut
        age,perime=P._age_ligne(chemin,29,maintenant)
        assert age==0 and perime is False
    P._ages[chemin]=700
    P._statuts[chemin]='MISS'
    assert P._age_ligne(chemin,29,maintenant)==(700,True)


def test_hit_sans_age_reste_perime_meme_avec_rechauffeur_frais():
    maintenant=datetime(2026,10,18,2,tzinfo=timezone.utc)
    chemin='/sports/29/markets/straight?withSpecials=true'
    P._ages[chemin]=None
    P._statuts[chemin]='HIT'
    P._plans[29]={'markets':chemin,'fresh':True,'t':maintenant.isoformat()}
    assert P._age_ligne(chemin,29,maintenant)==(None,True)
    P._ages[chemin]=30
    assert P._age_ligne(chemin,29,maintenant)[1] is False


def test_lire_statut_cache():
    class R:
        headers={'cf-cache-status':' miss '}
    assert P._lire_statut_cache(R())=='MISS'
    class S:
        headers={}
    assert P._lire_statut_cache(S())==''


def test_rechauffeur_http_refuse_et_journalise(monkeypatch):
    monkeypatch.setenv('PINNACLE_RECHAUFFEUR_URL','http://exemple.test/rechauffe')
    monkeypatch.setenv('PINNACLE_RECHAUFFEUR_SECRET','secret-rechauffe')
    appels=[]
    monkeypatch.setattr(P.requests,'post',lambda *a,**k: appels.append(1))
    P._demander_rechauffe({29:'football'})
    assert appels==[] and P._plans=={} and P.etat_rechauffeur=='url_refusee'


def test_rechauffeur_timeout_120_et_etat(monkeypatch):
    monkeypatch.setenv('PINNACLE_RECHAUFFEUR_URL','https://exemple.test/rechauffe')
    monkeypatch.setenv('PINNACLE_RECHAUFFEUR_SECRET','secret-rechauffe')
    vus={}
    def post(url,**k):
        vus.update(k)
        raise P.requests.Timeout()
    monkeypatch.setattr(P.requests,'post',post)
    P._demander_rechauffe({29:'football'})
    assert vus['timeout']==120 and P.etat_rechauffeur=='indisponible'


def test_gemini_version_2_et_debut_inchange():
    from cotes.strategie_gemini import GEMINI
    assert GEMINI['version']=='2' and GEMINI['debut']=='2026-10-14T18:00:00+00:00'
