"""Régressions d’intégrité : horaires réels, catégories, carnet et registre prospectif."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import pytest
from cotes import comparaison, simulation
from cotes.correspondance import ressemblance
from cotes.decisions import figer_nouveaux
from cotes.strategie_m3 import paris_m3
from cotes.strategie_m3_structure import paris_m3_structure, M3_STRUCTURE
from tests.test_strategie_m3 import pari

NOW = datetime(2026,10,17,2,tzinfo=timezone.utc)


def candidat(n=1, **kwargs):
    p=pari(n, NOW.isoformat())
    p.update(simulation='C', domicile='Athinaikos (F)', exterieur='Panseraikos (F)',
             pari='Athinaikos', mise=10,statut='en_cours',gain=None,
             decide_le=NOW.isoformat(),lot_decision=NOW.isoformat())
    p['preuve_prise']['ressemblance_noms']=.99
    p.update(kwargs)
    return p


@pytest.mark.parametrize('a,b', [('France U19','France U21'), ('Club II','Club U21'),
                                 ('Club B','Club Reserves'), ('France U-19','France U21'),
                                 ('Club II','Club (I)'), ('Club B','Club équipe première')])
def test_categories_contradictoires_sont_bloquantes(a,b):
    assert ressemblance(a,b)==0
    assert ressemblance(b,a)==0
    assert ressemblance('France U21','France U21')==1
    assert ressemblance('France','France U21')==.85


def test_placement_apres_debut_pendant_collecte_et_marge_30_secondes():
    p=candidat();p.update(match_id_reference=123,controle={'statut':'conforme'})
    for secondes, accepte in [(-60,False),(0,False),(29,False),(30,False),(31,True)]:
        o={**p,'debut':(NOW+timedelta(seconds=secondes)).isoformat()}
        rows=[];nouveaux=simulation.placer([o],rows,NOW)
        assert bool(nouveaux)==accepte
        if accepte:
            assert nouveaux[0]['decide_le']==NOW.isoformat(timespec='microseconds')
    assert not simulation.placer([{**p,'debut':'invalide'}],[],NOW)


def test_cloture_lue_avant_depart_integree_apres_traitement_long():
    p=candidat(debut=NOW.isoformat(),cloture_lue=(NOW-timedelta(minutes=20)).isoformat())
    lu=(NOW-timedelta(minutes=1)).isoformat()
    key=(p['match_id'],simulation.cle(p))
    simulation.suivre_cloture([p],{key:{'Pinnacle':(.6,lu)}},NOW+timedelta(minutes=20))
    assert p['cloture_lue']==lu and p['clv']==.08
    before=deepcopy(p)
    for t in [(NOW+timedelta(seconds=1)).isoformat(), (NOW-timedelta(minutes=2)).isoformat()]:
        simulation.suivre_cloture([p],{key:{'Pinnacle':(.8,t)}},NOW+timedelta(minutes=20))
        assert p==before


def test_betfair_carnet_croise_et_cotes_invalides_refuses():
    base={'cle_marche':'a','marche':'VAINQUEUR','periode':'MATCH','match_id':'o1',
          'source':'orbitxch','sport':'basket','ligne':None}
    def ligne(issue,achat,vente):
        return {**base,'issue':issue,'achat':[{'price':achat,'liquidity':100}],
                'vente':[{'price':vente,'liquidity':100}]}
    for achat, vente in [(2.1,2.0),(1,2),(0,2),('bad',2),(float('nan'),2)]:
        assert comparaison.reference_betfair([ligne('DOM',achat,vente),ligne('EXT',2,2.02)])==[]
    assert comparaison.reference_betfair([ligne('DOM',2,2.02),ligne('EXT',2,2.02)])
    assert not comparaison._fiable('Betfair',{'proba_juste':.5,'liquidite':100,'ecart_achat_vente':-.01})


def test_registre_fige_nouveaux_et_refus_sans_retroactivite():
    ancien=candidat('ancien',match_id='b|old')
    bon=candidat('bon',match_id='b|new')
    mauvais=candidat('refus',reference='Kalshi',match_id='b|refus')
    avant=deepcopy(ancien)
    rows=[ancien,bon,mauvais]
    figer_nouveaux(rows,[bon,mauvais])
    assert ancien==avant and 'selections_figees' not in ancien
    assert 'm3' in bon['selections_figees']
    assert mauvais['selections_figees']=={}
    fige=deepcopy([bon['selections_figees'],mauvais['selections_figees']])
    bon.update(statut='perdu',gain=-10,clv=-.5)
    figer_nouveaux(rows,[bon,mauvais])
    assert fige==[bon['selections_figees'],mauvais['selections_figees']]
    # Une modification ultérieure du moteur ne réécrit pas l'acceptation/refus.
    bon['suspect']=True;mauvais['reference']='Pinnacle'
    ids=paris_m3(rows)
    assert id(bon) in ids and id(mauvais) not in ids


def test_m3_structure_trois_familles_meilleur_edge_du_lot_et_pas_de_remplacement():
    a=candidat('a');b=candidat('b',marche='HANDICAP',ligne=-2.5)
    c=candidat('c',marche='HANDICAP',ligne=-3.5,cote_juste=1.7,ecart=round(1.8/1.7-1,4))
    d=candidat('d',marche='TOTAL',ligne=150.5,issue='PLUS')
    e=candidat('e',marche='TOTAL_EXT',ligne=75.5,issue='PLUS')
    rows=[a,b,c,d,e]
    ids=paris_m3_structure(rows)
    assert ids=={id(a),id(c),id(d)}
    # La version Rafale garde les cinq contrats.
    assert len(paris_m3(rows))==5
    figer_nouveaux(rows,rows)
    tard=candidat('tard',marche='HANDICAP',ligne=-4.5,cote_juste=1.65,
                  ecart=round(1.8/1.65-1,4),decide_le=(NOW+timedelta(minutes=5)).isoformat(),
                  lot_decision=(NOW+timedelta(minutes=5)).isoformat())
    rows.append(tard);figer_nouveaux(rows,[tard])
    assert 'm3_structure' not in tard['selections_figees']
    assert paris_m3_structure(rows)==ids
    assert not paris_m3_structure([candidat('avant',lot_decision='2026-10-16T00:00:00Z')])


def test_m3_structure_alias_inter_bookmakers_et_deux_directions_meme_famille():
    a=candidat('1')
    b=candidat('2',bookmaker='PMU',match_id='pmu|x',issue='EXT',
                cote_juste=1.7,ecart=round(1.8/1.7-1,4))
    # Même ID de référence, on ne prend pas les deux directions du vainqueur.
    assert paris_m3_structure([a,b])=={id(b)}


def test_evenements_et_clv_ponderent_les_matchs_pas_le_nombre_de_tickets():
    from cotes.laboratoire import resume
    rows=[candidat(str(i),statut='gagne',gain=8,regle_le='2026-10-17T05:00:00Z',
                    clv=.1,cloture_lue='2026-10-17T03:50:00Z') for i in range(3)]
    autre=candidat('autre',match_id='pmu|2',bookmaker='PMU',domicile='Autre club',
                   exterieur='Autre adversaire',statut='perdu',gain=-10,
                   regle_le='2026-10-17T05:00:00Z',clv=-.1,cloture_lue='2026-10-17T03:50:00Z')
    autre['preuve_prise']=deepcopy(autre['preuve_prise']);autre['preuve_prise']['match_id_reference']=999
    s=resume(rows+[autre],'2026-10-18T00:00:00Z',incertitude=False)
    assert s['regles']==4 and s['evenements_regles']==2
    assert s['clv']==5 and s['clv_evenement']==0 and s['clv_evenements_n']==2
