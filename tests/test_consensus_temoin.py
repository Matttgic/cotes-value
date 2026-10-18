"""Consensus équipondéré en probabilités, et refus des opportunités non pariables."""
from datetime import datetime,timezone
import pytest
from cotes.comparaison import comparer
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
    out=comparer(fr,{'Pinnacle':[],'Betfair':[]},index=index)
    consensus={p['issue']:p for p in out if p['reference']=='Consensus'}
    assert consensus['PLUS']['proba_juste']==pytest.approx(.45)
    assert consensus['MOINS']['proba_juste']==pytest.approx(.55)
    assert sum(p['proba_juste'] for p in consensus.values())==pytest.approx(1)
    assert all(p['pariable'] for p in consensus.values())
    # La moyenne des cotes inversées aurait modifié ce consensus, sans nouvelle donnée.
    assert 1/((1/.4+1/.5)/2)!=pytest.approx(.45)


def test_non_pariable_non_temoin_refuse_en_placement_et_notification():
    p=selection()
    assert placer([{**p,'pariable':False,'ecart':.05}],[],NOW)==[]
    assert not flux([{**p,'pariable':False}],[p],{'strategie':{id(p)}},NOW)['alertes']
