"""Consensus équipondéré en probabilités et témoin diagnostique non pariable."""
from copy import deepcopy
from datetime import datetime,timezone
import pytest
from cotes.comparaison import comparer,BRUT
from cotes.marches import cle
from cotes.simulation import placer
from cotes.notifications import flux
from tests.test_controle import ligne
from tests.test_notifications import selection
from tests.test_theodds import NOW


def test_consensus_moyenne_probabilites_conserve_somme_marche_commun():
    fr=[ligne(cote=2.4,issue='PLUS'),ligne(cote=2.,issue='MOINS')]
    index={'Pinnacle':{'m1':{}},'Betfair':{'m1':{}}}
    for l in fr:
        for ref,p in [('Pinnacle',.4 if l['issue']=='PLUS' else .6),
                      ('Betfair',.5)]:
            index[ref]['m1'][cle(l)]={**l,'proba_juste':p,'cote':1/p}
    out=comparer(fr,{'Pinnacle':[],'Betfair':[]},index=index,temoin_brut=False)
    consensus={p['issue']:p for p in out if p['reference']=='Consensus'}
    assert consensus['PLUS']['proba_juste']==pytest.approx(.45)
    assert consensus['MOINS']['proba_juste']==pytest.approx(.55)
    assert sum(p['proba_juste'] for p in consensus.values())==pytest.approx(1)
    assert all(p['pariable'] for p in consensus.values())
    # La moyenne des cotes inversées aurait modifié ce consensus, sans nouvelle donnée.
    assert 1/((1/.4+1/.5)/2)!=pytest.approx(.45)


def test_temoin_fausse_value_marque_et_placement_bloque_sans_effacer_historique():
    fr=ligne(cote=1.95)
    ref={**ligne(),'source':'pinnacle','match_id':'p1','cote':1.9,
         'proba_juste':.5,'marge_pinnacle':.05}
    out=comparer([fr],{'Pinnacle':[ref]})
    assert len(out)==1 and out[0]['reference']==BRUT
    assert out[0]['pariable'] is False
    ancien={'id':'historique','reference':BRUT,'gain':12.,'cote':2.2}
    avant=deepcopy(ancien);paris=[ancien]
    assert placer(out,paris,datetime(2029,12,31,21,tzinfo=timezone.utc))==[]
    assert paris==[avant]
    # Une ancienne entrée sans le nouveau champ ne contourne pas le garde-fou.
    out[0].pop('pariable')
    assert placer(out,paris,datetime(2029,12,31,21,tzinfo=timezone.utc))==[]


def test_non_pariable_non_temoin_refuse_en_placement_et_notification():
    p=selection()
    assert placer([{**p,'pariable':False,'ecart':.05}],[],NOW)==[]
    assert not flux([{**p,'pariable':False}],[p],{'strategie':{id(p)}},NOW)['alertes']
