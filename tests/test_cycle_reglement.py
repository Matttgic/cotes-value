"""Reprise du règlement lorsque le cron GitHub saute des exécutions."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from scripts import cycle

NOW = datetime(2026, 10, 16, 18, tzinfo=timezone.utc)


@pytest.mark.parametrize('date,attendu', [
    (None, True), ('invalide', True), ('2026-10-16T17:50:00', True),
    ((NOW-timedelta(minutes=54)).isoformat(), False),
    ((NOW-timedelta(minutes=55)).isoformat(), True),
    ((NOW-timedelta(hours=5)).isoformat(), True),
    ((NOW+timedelta(minutes=2)).isoformat(), False),
    ((NOW+timedelta(days=1)).isoformat(), True),
    ('2026-10-16T17:05:00Z', True),
])
def test_auto_reprend_un_reglement_en_retard_ou_une_date_invalide(monkeypatch,date,attendu):
    monkeypatch.setattr(cycle,'REGLEMENT_MINUTES',55)
    assert cycle.reglement_echu({'dernier_reglement':date},NOW,'auto') is attendu


def test_mode_explicite_et_journal_du_dernier_vrai_reglement():
    assert cycle.reglement_echu({},NOW,'non') is False
    assert cycle.reglement_echu({'dernier_reglement':NOW.isoformat()},NOW,'oui') is True
    avant={'debut':'avant','resultats':{'paris_en_attente':260}}
    etat={'dernier_reglement':'avant','dernier_cycle_reglement':avant}
    saute={'debut':'maintenant','resultats':{'saute':True}}
    cycle.conserver_journal_reglement(etat,saute,False)
    assert etat['dernier_cycle_reglement'] == avant
    journal={'debut':NOW.isoformat(),'fin':NOW.isoformat(),'mode':'complet','resultats':{'paris_en_attente':40}}
    cycle.conserver_journal_reglement(etat,journal,True)
    assert etat['dernier_reglement'] == NOW.isoformat()
    assert etat['dernier_cycle_reglement']['resultats']['paris_en_attente'] == 40
    journal['mode']='modifié'
    assert etat['dernier_cycle_reglement']['mode']=='complet'


def test_aucune_requete_scores_avant_le_delai(tmp_path,monkeypatch):
    (tmp_path/'etat.json').write_text(json.dumps({'dernier_reglement':NOW.isoformat()}))
    def interdit(*args,**kwargs):
        pytest.fail('Une nouvelle requête de scores a été lancée avant le délai')
    monkeypatch.setattr(cycle.resultats_mod,'a_lire',interdit)
    journal={'etapes':{}}
    assert cycle.effectuer_reglement([],tmp_path,NOW,'',journal,{},'auto') is False
    assert journal['resultats']['saute'] is True


def test_collecte_et_cron_partagent_delai_verrou_et_cles():
    racine=Path(__file__).resolve().parents[1]
    collecte=(racine/'.github/workflows/collecte.yml').read_text()
    reglement=(racine/'.github/workflows/reglement.yml').read_text()
    assert 'REGLEMENT: auto' in collecte and 'REGLEMENT: non' not in collecte
    assert '--seulement-reglement --reglement auto' in reglement
    for texte in (collecte,reglement):
        assert 'group: donnees' in texte
        assert 'cancel-in-progress: true' not in texte
        assert 'PROPLINE_API_KEY: ${{ secrets.PROPLINE_API_KEY }}' in texte
        for i in range(1,5):
            assert f'THE_ODDS_API_KEY_{i}: ${{{{ secrets.THE_ODDS_API_KEY_{i} }}}}' in texte


def test_un_passage_regle_ce_qui_est_prouve_et_compte_les_vrais_temoin_separement(tmp_path,monkeypatch):
    from tests.test_theodds import pari
    for key in ['API_SPORTS_KEY','PROPLINE_API_KEY',*[f'THE_ODDS_API_KEY_{i}' for i in range(1,5)]]:
        monkeypatch.delenv(key,raising=False)
    monkeypatch.setattr(cycle.resultats_mod,'a_lire',lambda *a:{})
    monkeypatch.setattr(cycle.resultats_nhl,'collecter',lambda *a:([],[]))
    monkeypatch.setattr(cycle.resultats_mod,'consensus',lambda *a:None)
    monkeypatch.setattr(cycle.resultats_mod,'reporte',lambda *a:None)
    monkeypatch.setattr(cycle.resultats_mod,'diagnostic',lambda p,*a:{'match_id':p['match_id'],'raison':'aucune source'})
    (tmp_path/'resultats_manuels.json').write_text(json.dumps({'prouve':'gagne'}))
    ps=[pari(id='prouve',debut=(NOW-timedelta(days=2)).isoformat(),statut='a_regler'),
        pari(id='vrai',reference='Pinnacle',match_id='pmu|absent',debut=(NOW-timedelta(days=2)).isoformat(),statut='a_regler'),
        pari(id='temoin-du-vrai',reference='Pinnacle brut',match_id='pmu|absent',debut=(NOW-timedelta(days=2)).isoformat(),statut='a_regler'),
        pari(id='temoin-seul',reference='Pinnacle brut',match_id='pmu|autre',debut=(NOW-timedelta(days=2)).isoformat(),statut='a_regler')]
    j={'etapes':{}}
    assert cycle.effectuer_reglement(ps,tmp_path,NOW,'',j,{},'auto')
    assert ps[0]['statut']=='gagne' and all(p['statut']=='a_regler' for p in ps[1:])
    assert j['resultats']['paris_regles']==1
    assert j['resultats']['paris_en_attente']==3 and j['resultats']['temoins_en_attente']==2
    assert j['resultats']['selections_en_attente']==2 and j['resultats']['selections_temoins_en_attente']==1


@pytest.mark.parametrize('mode,effectue',[('auto',False),('oui',True)])
def test_commande_seulement_reglement_respecte_mode_et_preserve_le_journal(tmp_path,monkeypatch,mode,effectue):
    import sys
    from types import SimpleNamespace
    ancien={'debut':'avant','resultats':{'paris_en_attente':260}}
    (tmp_path/'paris.json').write_text('[]')
    (tmp_path/'etat.json').write_text(json.dumps({'dernier_reglement':'avant','dernier_cycle_reglement':ancien}))
    def regler(ps,chemin,now,cle,j,requetes,choix):
        assert choix==mode
        j['resultats']={'paris_en_attente':40} if effectue else {'saute':True}
        return effectue
    monkeypatch.setattr(cycle,'effectuer_reglement',regler)
    monkeypatch.setitem(sys.modules,'site_web',SimpleNamespace(construire=lambda *a:None))
    monkeypatch.setattr(sys,'argv',['cycle.py','--seulement-reglement','--reglement',mode,'--donnees',str(tmp_path)])
    assert cycle.main()==0
    etat=json.loads((tmp_path/'etat.json').read_text())
    if effectue:
        assert etat['dernier_cycle_reglement']['resultats']['paris_en_attente']==40
        assert etat['dernier_reglement']!='avant'
    else:
        assert etat['dernier_cycle_reglement']==ancien and etat['dernier_reglement']=='avant'


def test_le_temoin_pinnacle_brut_est_retire_des_paris(tmp_path):
    import json
    from scripts import cycle
    (tmp_path / "paris.json").write_text(json.dumps([
        {"id": "a", "reference": "Pinnacle brut"}, {"id": "b", "reference": "Pinnacle"},
        {"id": "c", "reference": "Pinnacle brut"}]), encoding="utf-8")
    journal = {}
    assert [p["id"] for p in cycle.charger_paris(tmp_path, journal)] == ["b"]
    assert journal["temoin_pinnacle_brut_retires"] == 2
    (tmp_path / "paris.json").write_text(json.dumps([{"id": "b", "reference": "Pinnacle"}]), encoding="utf-8")
    journal = {}
    cycle.charger_paris(tmp_path, journal)             # sans témoin à retirer : pas de trace
    assert "temoin_pinnacle_brut_retires" not in journal
