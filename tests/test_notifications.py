import io
import json
from datetime import timedelta

from cotes.notifications import flux
from scripts.envoyer_notifications import transmettre
from tests.test_theodds import NOW, pari


def selection(**kw):
    return pari(detecte=(NOW-timedelta(minutes=3)).isoformat(), debut=(NOW+timedelta(hours=2)).isoformat(),
                reference="Pinnacle", pari="Paris Basketball vainqueur", **kw)


def test_flux_meme_prise_prix_et_plusieurs_strategies_sans_doublon():
    p=selection(); o=dict(p)
    b=flux([o,{**o,"reference":"Betfair"}],[p],{"strategie":{id(p)},"claude_prudent":{id(p)}},NOW)
    assert len(b['alertes'])==1
    a=b['alertes'][0]
    assert a['strategies']==['claude_prudent','strategie']
    assert a['validations']['strategie']==p['detecte']
    assert not flux([{**o,'cote':2.01}],[p],{'strategie':{id(p)}},NOW)['alertes']
    assert not flux([o],[p],{'strategie':set()},NOW)['alertes']


def test_flux_exclut_anciens_matches_commences_et_suspects():
    p=selection(); ids={'strategie':{id(p)}}
    for o in ({**p,'suspect':True},{**p,'debut':NOW.isoformat()}):
        assert not flux([o],[p],ids,NOW)['alertes']
    p['detecte']=(NOW-timedelta(minutes=16)).isoformat()
    assert not flux([p],[p],ids,NOW)['alertes']


def test_date_de_validation_reste_propre_a_chaque_strategie():
    p=selection(); q={**p,'id':'autre','detecte':NOW.isoformat(),'reference':'Betfair'}
    b=flux([p],[p,q],{'strategie':{id(p)},'gemini':{id(q)}},NOW)['alertes'][0]
    assert b['validations']['strategie']==p['detecte']
    assert b['validations']['gemini']==q['detecte']


def test_identite_github_et_aucun_secret_dans_le_diagnostic():
    appels=[]
    def ouvrir(req,timeout):
        appels.append(req)
        return io.BytesIO(json.dumps({'value':'jeton-secret'} if len(appels)==1 else
             {'ok':True,'sent':0,'devices':0,'subscription':'secret-interdit'}).encode())
    env={'ACTIONS_ID_TOKEN_REQUEST_URL':'https://example.test/token?x=1',
         'ACTIONS_ID_TOKEN_REQUEST_TOKEN':'identite-secrete'}
    r=transmettre({'alertes':[]},env,ouvrir)
    assert r=={'ok':True,'sent':0,'devices':0}
    assert 'audience=cotes-value-notifications' in appels[0].full_url
    assert appels[1].get_header('Authorization')=='Bearer jeton-secret'
    assert 'secret' not in json.dumps(r)
    assert not transmettre({},env={})['ok']
