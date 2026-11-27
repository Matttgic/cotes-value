"""Audit du 26/11/2026, dette et performance (docs/audit-26-11-dette.md).

Les raccourcis ajoutés rendent exactement ce que rendrait le calcul d'avant.
"""
from datetime import datetime, timezone

from cotes import memo


def _paris(n):
    return [{"id": f"p{i}", "x": i} for i in range(n)]


def _compteur():
    appels = []

    @memo.memoriser
    def pairs(paris):
        appels.append(1)
        return {id(p) for p in paris if p["x"] % 2 == 0}
    return pairs, appels


def test_memo_liste_modifiee_entre_deux_appels():
    pairs, appels = _compteur()
    paris = _paris(4)
    with memo.memoriser_selections():
        assert pairs(paris) == {id(paris[0]), id(paris[2])}
        assert pairs(paris) == {id(paris[0]), id(paris[2])} and len(appels) == 1
        paris[0] = {"id": "p0", "x": 0}              # autre objet, même identifiant : rendu vers le nouvel objet
        assert pairs(paris) == {id(paris[0]), id(paris[2])} and len(appels) == 1
        paris[2]["id"] = "q2"                        # identifiant changé sur place : autre clé, nouveau calcul
        assert pairs(paris) == {id(paris[0]), id(paris[2])} and len(appels) == 2
        paris.append({"id": "p4", "x": 4})
        assert pairs(paris) == {id(paris[0]), id(paris[2]), id(paris[4])} and len(appels) == 3
        del paris[2]["id"]                           # identifiant retiré : calcul direct, sans mémo
        assert pairs(paris) == {id(paris[0]), id(paris[2]), id(paris[4])} and len(appels) == 4
        assert pairs(paris) == {id(paris[0]), id(paris[2]), id(paris[4])} and len(appels) == 5


def test_memo_plusieurs_listes_en_alternance_et_contextes_imbriques():
    pairs, appels = _compteur()
    listes = [_paris(n) for n in (2, 3, 5)]
    with memo.memoriser_selections():
        for _ in range(3):
            for paris in listes:
                assert pairs(paris) == {id(p) for p in paris if p["x"] % 2 == 0}
        assert len(appels) == 3
        with memo.memoriser_selections():          # mémo à part (témoin du protocole) : rien de partagé
            assert pairs(listes[0]) == {id(listes[0][0])} and len(appels) == 4
        assert pairs(listes[0]) == {id(listes[0][0])} and len(appels) == 4
    assert pairs(listes[0]) == {id(listes[0][0])} and len(appels) == 5     # hors construction : sans mémo


def test_memo_valeurs_immuables_et_conteneurs_neufs():
    t = datetime(2026, 11, 26, tzinfo=timezone.utc)

    @memo.memoriser
    def cles(paris):
        return {id(p): ("ref", p["x"], t, (None, 1.5, True)) for p in paris}

    @memo.memoriser
    def listes(paris):
        return {id(p): ["liste", p["x"]] for p in paris}

    paris = _paris(3)
    copies = [dict(p) for p in paris]
    with memo.memoriser_selections():
        assert cles(paris) == cles.__wrapped__(paris)
        assert cles(copies) == {id(c): ("ref", c["x"], t, (None, 1.5, True)) for c in copies}
        premier = listes(paris)
        premier[id(paris[0])].append("modifié par l'appelant")
        assert listes(paris) == listes.__wrapped__(paris)
        assert listes(copies) == {id(c): ["liste", c["x"]] for c in copies}
