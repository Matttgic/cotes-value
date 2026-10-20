"""Traçabilité du prix et chemin d'alerte, sans toucher à la mise historique."""
import json
from copy import deepcopy
from datetime import timedelta
from pathlib import Path

from cotes import simulation
from cotes.notifications import flux
from scripts import envoyer_notifications as envoi
from tests.test_notifications import selection
from tests.test_theodds import NOW


def test_relecture_preserve_prise_et_ignore_autre_contrat_et_retour_arriere():
    from tests.test_strategie_jules_v2 import pari
    p=pari('grec',cote=1.76,statut='en_cours',gain=None)
    avant=deepcopy(p)
    l={**p,'collecte':'2026-10-17T00:00:00Z','cote':1.56}
    simulation.suivre_prix([p],[l,{**l,'ligne':99,'cote':3}])
    assert p['prix_revu']==1.56 and p['prix_revu_le'].startswith('2026-10-17T00:00:00')
    assert {k:p[k] for k in avant}==avant
    simulation.suivre_prix([p],[{**l,'collecte':'2026-10-16T23:00:00Z','cote':2}])
    assert p['prix_revu']==1.56
    p['statut']='gagne'
    simulation.suivre_prix([p],[{**l,'collecte':'2026-10-17T01:00:00Z','cote':2}])
    assert p['prix_revu']==1.56


def test_alerte_prix_quinze_minutes_et_date_visible_sans_antidater_validation():
    p=selection();base={'strategie':{id(p)}}
    for age,expected in [(899,True),(900,True),(901,False),(-1,False)]:
        o={**p,'collecte_recue':(NOW-timedelta(seconds=age)).isoformat()}
        alertes=flux([o],[p],base,NOW)['alertes']
        assert bool(alertes)==expected
        if expected:
            assert alertes[0]['age_prix_secondes']==age
            assert 'Prix relevé' in alertes[0]['pari']
            assert alertes[0]['validations']['strategie']==p['detecte']
    assert not flux([{**p,'cote':p['cote']-.2}],[p],base,NOW)['alertes']


def test_diagnostic_envoi_public_sans_secret(tmp_path,monkeypatch):
    monkeypatch.setattr(envoi,'preparer',lambda d:{'generated_at':NOW.isoformat(),'alertes':[]})
    monkeypatch.setattr(envoi,'transmettre',lambda f:{'ok':True,'sent':0})
    assert envoi.envoyer_et_journaliser(tmp_path,tmp_path/'flux.json')['ok']
    j=json.loads((tmp_path/'notifications_diagnostic.json').read_text())['cycles'][0]
    assert j['envoi_demande_le'] and j['envoi_termine_le']
    assert j['resultat']=={'ok':True,'sent':0}
    assert 'token' not in json.dumps(j) and 'subscription' not in json.dumps(j)


def test_workflow_sauvegarde_alerte_reglement_puis_site():
    s=(Path(__file__).resolve().parents[1]/'.github/workflows/collecte.yml').read_text()
    assert '--reglement non --sans-site' in s
    assert s.index('name: Enregistrer les données')<s.index('name: Envoyer les nouvelles alertes')
    assert s.index('name: Envoyer les nouvelles alertes')<s.index('name: Règlement après les alertes')
    assert '--seulement-reglement --reglement auto' in s
    assert '--donnees donnees --flux notifications-rapides.json' in s
