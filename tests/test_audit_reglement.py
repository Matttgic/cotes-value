"""Contradictions de l'audit : règles exactes, cache conservé et diagnostics visibles."""
from datetime import timedelta
import pytest
from cotes import resultats as R
from cotes.reglement import gain, regler, appliquer
from tests.test_resultats import T, PARI, enr


@pytest.mark.parametrize('statut', ['annule','statut_inconnu','en_cours',None])
def test_statut_inconnu_signale_sans_gain_silencieux(statut):
    with pytest.raises(ValueError,match='Statut de règlement inconnu'):
        gain(statut,10,2.5)


@pytest.mark.parametrize('score,issue,resultat', [
    ((2,1),'DOM','perdu'),((2,1),'NUL','gagne'),((2,1),'EXT','perdu'),
    ((1,1),'DOM','perdu'),((2,0),'DOM','gagne'),((2,0),'NUL','perdu'),
    ((0,1),'EXT','gagne')])
def test_handicap_europeen_moins_un_jamais_rembourse(score,issue,resultat):
    p={'marche':'HANDICAP_3','periode':'MATCH','issue':issue,'ligne':-1}
    assert regler(p,{'MATCH':score})==resultat
    assert regler({**p,'marche':'HANDICAP','issue':'DOM'},{'MATCH':(2,1)})=='rembourse'


@pytest.mark.parametrize('marche,issue,ligne,score,attendu',[
    ('TOTAL','PLUS',2.,(1,1),'rembourse'),
    ('TOTAL','PLUS',2.25,(2,0),'demi_perdu'),
    ('TOTAL','MOINS',2.25,(2,0),'demi_gagne'),
    ('TOTAL','PLUS',2.75,(2,1),'demi_gagne'),
    ('HANDICAP','DOM',-.75,(1,1),'perdu'),
    ('HANDICAP','DOM',-.75,(2,1),'demi_gagne'),
    ('HANDICAP','DOM',-.25,(1,1),'demi_perdu')])
def test_quarts_de_ligne_corrects(marche,issue,ligne,score,attendu):
    assert regler({'marche':marche,'periode':'MATCH','issue':issue,'ligne':ligne},{'MATCH':score})==attendu


def pari_ouvert(**kwargs):
    return {**PARI,'id':'p1','match_id':'w|1','statut':'en_cours','gain':None,
            'mise':10,'cote':2.,'marche':'VAINQUEUR','periode':'MATCH','issue':'DOM',**kwargs}


@pytest.mark.parametrize('debut',[None,'invalide','2026-10-06T02:00:00'])
def test_date_pari_invalide_trace_idempotente_et_file_a_regler(debut):
    p=pari_ouvert(debut=debut)
    for _ in range(3):
        appliquer([p],{}, {},T)
    assert p['alertes']==['date_debut_absente_ou_invalide']
    assert p['statut']=='a_regler' and p['gain'] is None and 'regle_le' not in p
    assert 'date de début' in R.diagnostic(p,[],T)['raison']
    # Un pari sans date ne provoque pas d'erreur dans la recherche des scores.
    assert R.a_lire([p],T)=={}


def test_date_manquante_et_statut_manuel_inconnu_ni_crash_ni_faux_gain():
    p=pari_ouvert();p.pop('debut')
    appliquer([p],{}, {'p1':'annule'},T)
    assert set(p['alertes'])=={'date_debut_absente_ou_invalide','statut_reglement_inconnu'}
    assert p['gain'] is None
    # Une instruction manuelle valide explicite reste utilisable.
    appliquer([p],{}, {'p1':'rembourse'},T)
    assert p['statut']=='rembourse' and p['gain']==0


def test_sources_sans_date_ignorees_et_journal_borne_sans_erreur_espn():
    R.reinitialiser_ignores()
    n=len(R.ERREURS_ESPN)
    r=enr('betmgm','Honduras','Jamaica',(2,0));r.pop('debut')
    bon=enr('espn','Honduras','Jamaica',(1,0))
    for _ in range(3):
        assert R.retrouver(PARI,[r,bon])==[bon]
    assert len(R.RESULTATS_IGNORES)==1 and R.RESULTATS_IGNORES[0]['source']=='betmgm'
    assert len(R.ERREURS_ESPN)==n
    for i in range(120):
        R.retrouver(PARI,[{**r,'domicile':str(i)}])
    assert len(R.RESULTATS_IGNORES)==R.IGNORES_MAX
    R.reinitialiser_ignores()


@pytest.mark.parametrize('sport,score,attendu', [
    ('basket',(101,89),True),('basket',(12,9),False),('basket',(20,18),False),
    ('basket',(45,28),False),('volley',(3,1),True),('baseball',(3,3),False),
    ('baseball',(-1,3),False),('volley',(3,-1),False),('basket',(True,40),False)])
def test_plausibilite_source_unique_pas_assouplie_globalement(sport,score,attendu):
    assert R.plausible(sport,score) is attendu


def test_basket_bas_deux_sources_et_detail_complet_exiges():
    p={**PARI,'sport':'basket'}
    q=[(12,8),(11,6),(12,7),(10,7)]
    a=enr('espn','Honduras','Jamaica',(45,28),periodes=q,sport='basket')
    b=enr('betmgm','Honduras','Jamaica',(45,28),sport='basket')
    assert R.consensus(p,[a],T+timedelta(days=2)) is None
    assert R.consensus(p,[{**a,'periodes':[]},b],T+timedelta(days=2)) is None
    assert R.consensus(p,[{**a,'periodes':q[:-1]},b],T+timedelta(days=2)) is None
    assert R.consensus(p,[{**a,'periodes':[(12,8)]*4},b],T+timedelta(days=2)) is None
    assert R.consensus(p,[a,b],T+timedelta(hours=3))['score']==(45,28)
    # Deux entrées du même fournisseur ne sont toujours qu'une voix.
    assert R.consensus(p,[a,a],T+timedelta(days=2)) is None


@pytest.mark.parametrize('score',[None,[],[2],[2,0,1],[2,-1],[True,0]])
def test_score_source_invalide_ignore_meme_si_equipes_inversees(score):
    R.reinitialiser_ignores()
    r=enr('espn','Jamaica','Honduras',score)
    assert R.consensus(PARI,[r],T+timedelta(days=2)) is None
    assert R.RESULTATS_IGNORES[-1]['raison']=='score_invalide'
    R.reinitialiser_ignores()


def test_score_json_normalise_sans_muter_la_source():
    r=enr('espn','Honduras','Jamaica',[2,0])
    assert R.consensus(PARI,[r],T+timedelta(days=2))['score']==(2,0)
    assert r['score']==[2,0]

