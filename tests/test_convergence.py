"""Convergence : votes causaux, versions d'une même famille, prix et date exacts."""
from copy import deepcopy

from cotes.convergence import CONVERGENCE, paris_convergence, selections, valider_actuelles


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
