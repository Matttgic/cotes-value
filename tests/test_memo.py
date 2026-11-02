"""Mémo des sélections (cotes/memo.py) : même résultat qu'un calcul direct, partagé entre les copies Kelly."""
from collections import Counter

from cotes.memo import memoriser, memoriser_selections

APPELS = []


@memoriser
def selecteur(paris, eligibles=frozenset(), seuil=0):
    APPELS.append(1)
    return {"selection": {id(p) for p in paris if p["cote"] > seuil and (not eligibles or id(p) in eligibles)},
            "par_jour": {"2026-11-02": 1}, "premier": [p for p in paris[:1]]}


def _paris():
    return [{"id": "a", "cote": 2.0, "mise": 10}, {"id": "b", "cote": 3.0, "mise": 10}]


def test_hors_contexte_aucun_cache():
    APPELS.clear()
    paris = _paris()
    selecteur(paris)
    selecteur(paris)
    assert len(APPELS) == 2


def test_copies_kelly_reprennent_la_selection_traduite():
    APPELS.clear()
    paris = _paris()
    copies = [{**p, "mise": 4.5} for p in paris]
    with memoriser_selections():
        r1 = selecteur(paris, eligibles={id(paris[1])}, seuil=1)
        r2 = selecteur(copies, eligibles={id(copies[1])}, seuil=1)
    assert len(APPELS) == 1
    assert r1["selection"] == {id(paris[1])} and r2["selection"] == {id(copies[1])}
    assert r2["premier"][0] is copies[0] and r2["par_jour"] == {"2026-11-02": 1}


def test_arguments_differents_recalculent_et_resultat_modifiable_sans_effet():
    APPELS.clear()
    paris = _paris()
    with memoriser_selections():
        a = selecteur(paris, seuil=1)
        a["selection"].clear()
        b = selecteur(paris, seuil=1)
        c = selecteur(paris, seuil=2.5)
    assert len(APPELS) == 2
    assert b["selection"] == {id(paris[0]), id(paris[1])} and c["selection"] == {id(paris[1])}


def test_liste_sans_identifiants_uniques_calculee_directement():
    APPELS.clear()
    paris = [{"id": "a", "cote": 2.0}, {"id": "a", "cote": 3.0}]
    with memoriser_selections():
        selecteur(paris)
        selecteur(paris)
    assert len(APPELS) == 2


def test_type_non_exact_jamais_memorise():
    vus = []

    @memoriser
    def compte(paris):
        vus.append(1)
        return Counter(p["id"] for p in paris)

    paris = _paris()
    with memoriser_selections():
        assert compte(paris)["absent"] == 0         # un Counter reste un Counter
        compte(paris)
    assert len(vus) == 2
