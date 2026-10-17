"""Convergence : votes causaux, versions d'une même famille, prix et date exacts."""
from copy import deepcopy
from itertools import permutations
import pytest

from cotes.convergence import CONVERGENCE, paris_convergence, selections, valider_actuelles, votes


def pari(pid="a", **kw):
    p = {"id": pid, "bookmaker": "Winamax", "match_id": "w|1", "marche": "VAINQUEUR",
         "periode": "MATCH", "ligne": None, "issue": "DOM", "cote": 1.8,
         "detecte": "2026-10-15T00:00:00Z", "reference": "Pinnacle"}
    return {**p, **kw}


def test_jules_versions_ne_creent_pas_de_convergence():
    p = pari()
    assert not paris_convergence([p], {"jules": {id(p)}, "jules_v2": {id(p)}})
    assert paris_convergence([p], {"jules": {id(p)}, "jules_v2": {id(p)}, "strategie": {id(p)}}) == {id(p)}


def test_votes_simultanes_multi_references_utc_et_une_seule_mise():
    a = pari("a", reference="Betfair")
    b = pari("b", reference="Pinnacle", detecte="2026-10-15T02:00:00+02:00")
    later = pari("c", detecte="2026-10-15T01:00:00Z", cote=1.9)
    votes = {"strategie": {id(a), id(later)}, "gemini": {id(b), id(later)}}
    assert paris_convergence([later, a, b], votes) == {id(b)}
    assert paris_convergence([b, later, a], votes) == {id(b)}


def test_vote_tardif_prix_periode_joueur_ou_book_differents_ne_sajoutent_pas():
    a = pari("a")
    for changement in ({"detecte": "2026-10-15T00:01:00Z"}, {"cote": 1.81},
                        {"periode": "MT1"}, {"joueur": "Quelqu'un"}, {"bookmaker": "Betclic"}):
        b = pari("b", **changement)
        assert not paris_convergence([a,b], {"strategie": {id(a)}, "chatgpt": {id(b)}})


def test_lancement_non_retroactif_et_rejeu_explicite():
    p = pari(detecte="2026-10-14T22:59:59Z")
    votes = {"strategie": {id(p)}, "chatgpt": {id(p)}}
    assert not paris_convergence([p], votes)
    assert paris_convergence([p], votes, depuis="2026-10-07T00:00:00+02:00") == {id(p)}
    assert CONVERGENCE["debut"] == "2026-10-14T23:00:00+00:00"


def test_badges_actuels_ne_requalifient_pas_une_nouvelle_cote():
    a = pari("a")
    votes = {"strategie": {id(a)}, "gemini": {id(a)}}
    actuel = pari("maintenant", detecte="2026-10-15T00:30:00Z", reference="Polymarket")
    meme, change = valider_actuelles([actuel, {**actuel, "cote": 1.81}], [a], votes)
    assert meme["strategies"] == ["gemini", "strategie"] and meme["convergence"]
    assert meme["validation_detecte"] == "2026-10-15T00:00:00+00:00"
    assert not change["strategies"] and not change["convergence"]


def test_vrais_selecteurs_ignorent_les_resultats_et_respectent_les_plafonds():
    rows = []
    for i in range(12):
        p = pari(str(i), match_id="w|"+str(i), sport="football", simulation="C", ecart=.045,
                 cote_juste=1.8/1.045, domicile="Equipe "+str(i), exterieur="Adversaire "+str(i),
                 debut="2026-10-15T06:00:00Z", lu_reference="2026-10-15T00:00:00Z",
                 preuve_prise={"match_id_reference":str(i),"ressemblance_noms":.95,"controle":{"statut":"conforme"}})
        rows.append(p)
    avant = selections(rows)
    ids = {cle:{rows[i]["id"] for i in range(len(rows)) if id(rows[i]) in selection} for cle,selection in avant.items()}
    assert len(ids["jules"]) == 6 and len(ids["jules_v2"]) == 8
    copies=deepcopy(rows)
    for i,p in enumerate(copies):
        p.update(statut="gagne" if i%2 else "perdu", gain=999, clv=-.8, regle_le="2026-10-16T12:00:00Z")
    apres=selections(copies)
    assert ids == {cle:{p["id"] for p in copies if id(p) in selection} for cle,selection in apres.items()}


@pytest.mark.parametrize('valeur', [None, True, 1, 0, -2, '2.0', float('nan'), float('inf')])
def test_votes_ignore_cote_invalide_et_cle_absente(valeur):
    p=pari(cote=valeur)
    assert votes([p],{'strategie':{id(p)},'gemini':{id(p)}})=={}
    p.pop('cote')
    assert votes([p],{'strategie':{id(p)},'gemini':{id(p)}})=={}


def test_deux_versions_jules_sur_deux_references_restent_une_famille():
    a,b=pari('a'),pari('b',reference='Betfair')
    retenus={'jules':{id(a)},'jules_v2':{id(b)},'claude_prudent':{id(a)},'m3_structure':{id(b)}}
    groupe=next(iter(votes([a,b],retenus).values()))
    assert groupe['familles']=={'jules'}
    assert not paris_convergence([a,b],retenus)


def test_plusieurs_prix_simultanes_representant_independant_de_l_ordre():
    rows=[pari('z',reference='Betfair',cote=1.9),pari('b',cote=1.8),
          pari('a',cote=1.8),pari('c',reference='Polymarket',cote=1.9)]
    retenus={'strategie':{id(rows[0]),id(rows[1])},'gemini':{id(rows[2]),id(rows[3])}}
    for ordre in permutations(rows):
        assert paris_convergence(list(ordre),retenus)=={id(rows[2])}
    assert not paris_convergence(rows,retenus,depuis='invalide')


def test_prix_change_exige_une_vraie_prise_anterieure_du_meme_contrat():
    p=pari('prise')
    retenus={'strategie':{id(p)},'gemini':{id(p)}}
    actuel=pari('actuel',detecte='2026-10-15T00:30:00Z')
    copies=deepcopy([p,actuel])
    for prix in [1.6,1.81,2.1]:
        o=valider_actuelles([{**actuel,'cote':prix}],[p],retenus)[0]
        assert o['prix_change'] and o['prix_precedent']==1.8
        assert o['strategies']==[] and not o['convergence']
        assert o['strategies_precedentes']==['gemini','strategie'] and o['convergence_precedente']
        assert o['validation_precedente']=='2026-10-15T00:00:00+00:00'
    assert [p,actuel]==copies
    for changement in [{'issue':'EXT'},{'periode':'MT1'},{'bookmaker':'PMU'},
                        {'detecte':'2026-10-14T23:00:00Z'}, {'cote':None}]:
        o=valider_actuelles([{**actuel,'cote':1.6,**changement}],[p],retenus)[0]
        assert not o['prix_change'] and o['prix_precedent'] is None
    assert not valider_actuelles([{**actuel,'cote':1.6}],[p],{})[0]['prix_change']
    identique=valider_actuelles([actuel],[p],retenus)[0]
    assert not identique['prix_change'] and identique['convergence']


def test_prix_precedent_choisi_par_date_pas_par_ordre_et_retour_au_prix_valide():
    a=pari('a');b=pari('b',cote=1.9,detecte='2026-10-15T00:10:00Z')
    retenus={'strategie':{id(a),id(b)}}
    o=pari('actuel',cote=1.7,detecte='2026-10-15T00:30:00Z')
    for rows in [[a,b],[b,a]]:
        assert valider_actuelles([o],rows,retenus)[0]['prix_precedent']==1.9
        retour=valider_actuelles([{**o,'cote':1.8}],rows,retenus)[0]
        assert not retour['prix_change'] and retour['strategies']==['strategie']
