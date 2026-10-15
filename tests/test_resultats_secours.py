from datetime import datetime, timezone

from cotes import resultats as R, resultats_nhl as N, reglement
from tests.test_resultats import PARI, enr
from tests.test_theodds import run, pari, HTTP


def fiche():
    return {'id':123,'gameState':'OFF','startTimeUTC':'2026-10-14T00:30:00Z',
            'homeTeam':{'score':3,'abbrev':'DAL','placeName':{'default':'Dallas'},'commonName':{'default':'Stars'}},
            'awayTeam':{'score':2,'abbrev':'COL','placeName':{'default':'Colorado'},'commonName':{'default':'Avalanche'}},
            'periodDescriptor':{'periodType':'SO'},
            'summary':{'scoring':[
                {'periodDescriptor':{'number':i+1,'periodType':'REG'},
                 'goals':[{'teamAbbrev':{'default':t}} for t in ts]}
                for i,ts in enumerate([[],['DAL','COL'],['COL','DAL']])
            ]+[{'periodDescriptor':{'number':4,'periodType':'OT'},'goals':[]},
               {'periodDescriptor':{'number':5,'periodType':'SO'},'goals':[]}]}}


def test_nhl_score_final_et_trois_tiers_ne_se_confondent_pas():
    f=fiche(); r=N.capturer(f)
    sc=reglement.scores_par_periode('hockey',r['score'],r['periodes'],r['libelles'])
    assert sc['MATCH']==(3,2) and sc['TEMPS_REG']==(2,2)
    for changement in ({'gameState':'LIVE'},{'homeTeam':{}},{'summary':{'scoring':[]}}):
        assert N.capturer({**f,**changement}) is None
    f['homeTeam']['score']=4
    assert N.capturer(f) is None


def test_nhl_officielle_corroboration_et_orientation():
    r=N.capturer(fiche()); p={'sport':'hockey','domicile':'Colorado Avalanche','exterieur':'Dallas Stars',
                           'debut':'2026-10-14T00:30:00Z'}
    autres=[{**r,'source':s,'score':(3,2) if s in ('draftkings','espn') else (2,2)}
            for s in ('draftkings','espn','betmgm','unibet-uk','interwetten-de')]
    now=datetime(2026,10,14,12,tzinfo=timezone.utc)
    valide=R.consensus(p,[r]+autres,now)
    assert valide['score']==(2,3) and 'nhl_officiel' in valide['sources']
    assert reglement.scores_par_periode('hockey',valide['score'],valide['periodes'],valide['libelles'])['TEMPS_REG']==(2,2)
    assert not R._majoritaires([{**r,'source':'unibet-uk','score':(2,2)},{**r,'source':'betmgm','score':(2,2)},r])


def test_nhl_aucune_requete_sans_nhl_eligible():
    class Interdit:
        def get(self,*a,**kw):
            raise AssertionError('requête inutile')
    assert N.collecter([{'sport':'basket','statut':'a_regler'}],datetime.now(timezone.utc),Interdit())==([],[])


def test_diagnostic_distingue_attente_24h_de_la_source_absente():
    p={**PARI,'match_id':'x'}; es=[enr('unibet-uk','Honduras','Jamaica',(1,1))]
    now=datetime(2026,10,6,15,tzinfo=timezone.utc)
    d=R.diagnostic(p,es,now)
    assert d['raison']=='source unique : délai de validation automatique'
    assert d['validation_apres']=='2026-10-07T02:00:00+00:00'
    assert R.diagnostic(p,[],now)['raison']=='aucune source'
    assert R.diagnostic(p,es,datetime(2026,10,7,3,tzinfo=timezone.utc))['raison'].startswith('score validé')


def test_diagnostic_odds_competition_et_periode_non_couvertes():
    _,b=run(paris=[pari(ligue='Eurocup (F)'),pari(id='mt',periode='MT1')],http=HTTP())
    assert b['couverture']['competition_non_couverte']==1
    assert b['couverture']['marche_non_couvert']==1
    assert b['couverture']['eligibles']==b['requetes_scores']==0


def test_correction_finale_ne_bloque_pas_les_mi_temps_arrivees_plus_tard():
    from tests.test_theodds import pari
    p=pari(periode='MT1',marche='TOTAL',issue='PLUS',ligne=80.5)
    m={p['match_id']:{'score':[99,91],'source':'club officiel'}}
    r={p['match_id']:{'score':[99,91],'final':True,'periodes':[(25,20),(25,22),(24,24),(25,25)],
                       'libelles':['1','2','3','4'],'sources':['espn']}}
    reglement.appliquer([p],r,m)
    assert p['statut']=='gagne' and p['preuve_reglement']['sources_detail']==['espn']
    p=pari(periode='MT1',marche='TOTAL',issue='PLUS',ligne=80.5)
    r[p['match_id']]['id_paris_autorises']=['autre pari']
    reglement.appliquer([p],r,m)
    assert p['statut'] in ('en_cours','a_regler')
    r[p['match_id']].pop('id_paris_autorises')
    r[p['match_id']]['score']=[100,91]
    reglement.appliquer([p],r,m)
    assert p['statut'] in ('en_cours','a_regler')
