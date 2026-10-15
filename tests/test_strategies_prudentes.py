"""Nouveaux suivis : causalité, plafonds, votes et intégration exacte au site."""
from copy import deepcopy
from datetime import datetime,timezone
import json,re

from cotes.convergence import paris_convergence,selections
from cotes.strategies_prudentes import (CLAUDE_PRUDENT,CONVERGENCE_3,DEBUT_VARIANTES,
                                        selections_prudentes,selection_unique)
from tests.test_strategie_jules_v2 import pari,ref


def test_lancement_nouveau_pas_de_retroactivite():
    old=pari('avant',detecte='2026-10-15T03:59:59Z',lu_reference='2026-10-15T03:59:00Z',debut='2026-10-15T06:00:00Z')
    new=pari('apres',detecte=DEBUT_VARIANTES,lu_reference='2026-10-15T03:59:00Z',debut='2026-10-15T06:00:00Z')
    official=selections_prudentes([old,new])
    assert official['claude_prudent']=={id(new)}
    assert id(old) not in official['convergence_3']
    assert selections_prudentes([old],depuis='2026-10-07T00:00:00+02:00')['claude_prudent']=={id(old)}


def test_export_prospectif_et_reconstitution_14_restent_separes():
    from cotes.strategies_prudentes import suivis_prudents
    old=pari('avant',detecte='2026-10-14T19:00:00Z',lu_reference='2026-10-14T19:00:00Z',debut='2026-10-14T21:00:00Z')
    new=pari('apres',detecte=DEBUT_VARIANTES,lu_reference='2026-10-15T03:59:00Z',debut='2026-10-15T06:00:00Z')
    r=suivis_prudents([old,new], '2026-10-16T00:00:00Z')
    assert r['officiel']['claude_prudent']['ids']==['apres']
    assert r['reconstitution_exploratoire']['claude_prudent']['ids']==['avant','apres']
    assert r['debut_prospectif']==DEBUT_VARIANTES


def test_script_comparaison_exporte_les_deux_suivis_sans_changer_comparateurs_historiques():
    from scripts.comparer_strategies import comparer
    report=comparer([], '2026-10-16T00:00:00Z')
    assert set(report['suivis_prudents']['officiel'])=={'claude_prudent','convergence_3'}
    assert 'Claude (rejeu)' in report['comparateurs']
    assert CLAUDE_PRUDENT['nom'] not in report['comparateurs']


def test_un_match_multi_books_refs_marches_et_prix_sans_anticipation():
    p=pari('alpha')
    q=ref({**p,'id':'pmu','bookmaker':'PMU','match_id':'pmu|autre','marche':'TOTAL','issue':'PLUS','ligne':2.5,
           'detecte':'2026-10-15T09:01:00Z','ecart':.08,'cote':2.2,'cote_juste':2.2/1.08},'Polymarket','poly')
    assert selections_prudentes([q,p])['claude_prudent']=={id(p)}
    # Le meilleur edge ne départage qu'à instant égal.
    q={**q,'detecte':p['detecte']}
    assert selections_prudentes([p,q])['claude_prudent']==selections_prudentes([q,p])['claude_prudent']=={id(q)}


def test_plafond_dix_par_jour_paris_et_reinitialisation_minuit():
    rows=[pari('equipe'+str(i),detecte=f'2026-10-15T21:{i:02d}:00Z',lu_reference=f'2026-10-15T21:{i:02d}:00Z',
               debut='2026-10-16T01:00:00Z') for i in range(11)]
    suivant=pari('suivant',detecte='2026-10-15T22:00:00Z',lu_reference='2026-10-15T22:00:00Z',debut='2026-10-16T01:00:00Z')
    assert selections_prudentes(rows+[suivant])['claude_prudent']=={id(p) for p in rows[:10]+[suivant]}
    assert CLAUDE_PRUDENT['maximum_jour']==10


def test_alias_appris_sur_prix_refuse_avant_lancement_ne_consomme_pas_de_mise():
    p=pari('alpha',domicile='PSG',exterieur='OL',match_reference='PSG - OL')
    pont=ref({**p,'id':'pont','detecte':'2026-10-15T03:30:00Z','ecart':.8},'Polymarket','poly')
    autre={**pont,'id':'autre','bookmaker':'PMU','match_id':'pmu|autre','domicile':'Paris Saint Germain',
           'exterieur':'Olympique Lyonnais','match_reference':'','detecte':'2026-10-15T09:01:00Z','ecart':.05}
    assert selection_unique([autre,pont,p],{id(p),id(autre)},DEBUT_VARIANTES)['selection']=={id(p)}


def test_fusion_tardive_ne_retires_pas_des_mises_deja_prises():
    p=pari('alpha',match_reference='')
    q=ref(pari('bravo',detecte='2026-10-15T09:01:00Z',match_reference=''),'Betfair','bet')
    pont=ref({**p,'id':'pont','detecte':'2026-10-15T09:02:00Z'},'Betfair','bet')
    avant=selection_unique([p,q],{id(p),id(q)},DEBUT_VARIANTES)
    apres=selection_unique([p,q,pont],{id(p),id(q)},DEBUT_VARIANTES)
    assert avant['selection']==apres['selection']=={id(p),id(q)}
    assert apres['fusions_tardives']==1


def test_jules_versions_un_vote_m3_et_variantes_ne_votent_pas():
    p=pari()
    bases={'strategie':{id(p)},'jules':{id(p)},'jules_v2':{id(p)},'m3':{id(p)},'claude_prudent':{id(p)}}
    assert not selections_prudentes([p],bases=bases)['convergence_3']
    bases['gemini']={id(p)}
    assert selections_prudentes([p],bases=bases)['convergence_3']=={id(p)}
    # La convergence existante ignore les nouveaux badges comme votes.
    assert not paris_convergence([p],{'strategie':{id(p)},'claude_prudent':{id(p)},'convergence_3':{id(p)}})


def test_trois_votes_exigent_prix_et_instant_identiques():
    p=pari()
    for change in [{'cote':2.2},{'detecte':'2026-10-15T09:00:01Z'},{'periode':'MT1'}]:
        q={**p,'id':'q',**change}
        bases={'strategie':{id(p)},'gemini':{id(p)},'jules':{id(q)}}
        assert not selections_prudentes([p,q],bases=bases)['convergence_3']


def test_convergence_un_par_match_tous_bookmakers_confondus():
    p=pari()
    q={**p,'id':'pmu','bookmaker':'PMU','match_id':'pmu|autre','detecte':'2026-10-15T09:01:00Z'}
    bases={cle:{id(p),id(q)} for cle in ['strategie','gemini','jules']}
    assert selections_prudentes([q,p],bases=bases)['convergence_3']=={id(p)}


def test_resultats_clv_et_ordre_entree_ne_modifient_pas_les_selections():
    rows=[pari('alpha'),pari('bravo')]
    avant=selections_prudentes(rows)
    ids={k:{p['id'] for p in rows if id(p) in v} for k,v in avant.items()}
    changed=deepcopy(list(reversed(rows)))
    for p in changed:p.update(statut='perdu',gain=-999,clv=.9,regle_le='2026-10-16T12:00:00Z')
    apres=selections_prudentes(changed)
    assert ids=={k:{p['id'] for p in changed if id(p) in v} for k,v in apres.items()}


def test_site_tableau_courbe_navigation_badges_prix_et_export_coherents(tmp_path,monkeypatch):
    from scripts import site_web
    class Horloge(datetime):
        @classmethod
        def now(cls,tz=None):return datetime(2026,10,16,tzinfo=timezone.utc)
    monkeypatch.setattr(site_web,'datetime',Horloge)
    p=pari('alpha',statut='gagne',gain=11,regle_le='2026-10-15T15:00:00Z')
    (tmp_path/'paris.json').write_text(json.dumps([p]))
    html=site_web.construire(tmp_path,tmp_path/'site').read_text()
    d=json.loads(re.search(r'const D = (\{.*?\});\n',html,re.S).group(1).replace('<\\/','</'))
    labo=d['laboratoire'];nav=labo['navigation']
    for v in [CLAUDE_PRUDENT,CONVERGENCE_3]:
        nom=v['nom'];cle=v['cle']
        assert labo['comparateurs_futur'][nom]['gain']==11
        assert nav['selections'][nom]['futur']==['alpha']
        assert nav['courbes'][nom]['futur'][-1][1]==11
        assert cle in nav['paris']['alpha']['strategies']
        row=dict(zip(d['catalogue']['champs'],d['catalogue']['lignes'][0]))
        assert cle in row['strategies'] and row['cote']==2.1
        assert d['variantes'][nom]['debut']==DEBUT_VARIANTES


def test_variantes_ne_changent_pas_la_reference_de_la_convergence_existante():
    p=pari('bet',reference='Betfair')
    q={**p,'id':'pin','reference':'Pinnacle'}
    bases={'strategie':{id(p)},'gemini':{id(p)}}
    avant=paris_convergence([p,q],bases)
    apres=paris_convergence([p,q],{**bases,'claude_prudent':{id(q)},'convergence_3':{id(q)}})
    assert avant==apres=={id(p)}


def test_marche_refuse_peut_apprendre_un_alias_sans_valider_id_fournisseur():
    from cotes.strategies_prudentes import _cles_match
    p=pari('alpha')
    preuve={**p['preuve_prise'],'controle':{'statut':'non_conforme'}}
    cles=_cles_match({**p,'preuve_prise':preuve})
    assert any(k[0]=='equipes' for k in cles)
    assert not any(k[0]=='reference' for k in cles)


def test_match_ecarte_au_plafond_ne_reapparait_pas_le_lendemain():
    rows=[pari('equipe'+str(i),detecte=f'2026-10-15T21:{i:02d}:00Z',lu_reference=f'2026-10-15T21:{i:02d}:00Z',
               debut='2026-10-16T01:00:00Z') for i in range(11)]
    retry={**rows[-1],'id':'nouvelle-ligne','detecte':'2026-10-15T22:01:00Z','lu_reference':'2026-10-15T22:01:00Z',
           'marche':'HANDICAP','ligne':1.5}
    assert selections_prudentes(rows+[retry])['claude_prudent']=={id(p) for p in rows[:10]}
