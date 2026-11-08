"""Stratégies recommandées : critères de solidité, doublons écartés, fusion figée."""
from cotes.recommandations import raisons_refus, recommander, recouvrement


def _stats(total, matchs=120, borne=2.0, sans=3.0, part=4.0, clv=1.0):
    return {"note": {"total": total, "matchs": matchs,
                     "mesures": {"roi_borne_basse_80": borne, "roi_sans_meilleurs": sans,
                                 "part_meilleur_match": part, "clv_ajustee": clv}}}


def test_criteres_de_solidite():
    assert raisons_refus(_stats(80)) == []
    assert raisons_refus(None) == ["moins de 10 matchs réglés"]
    assert "moins de 50 matchs réglés" in raisons_refus(_stats(80, matchs=40))
    assert "borne basse du ROI négative" in raisons_refus(_stats(80, borne=-0.5))
    assert "ROI négatif sans ses meilleurs matchs" in raisons_refus(_stats(80, sans=-1))
    assert "trop dépendante d'un match" in raisons_refus(_stats(80, part=40))
    assert "CLV par match négative" in raisons_refus(_stats(80, clv=-0.1))


def test_meilleures_notes_sans_doublon_ni_base():
    a, b, c, d = set(range(100)), set(range(20, 120)), set(range(500, 600)), set(range(1000, 1100))
    lignes = [{"id": "A", "stats": _stats(90), "ensemble": a},
              {"id": "B", "stats": _stats(88), "ensemble": b},            # 80 % de paris communs avec A
              {"id": "C", "stats": _stats(70), "ensemble": c},
              {"id": "base:X", "stats": _stats(99), "ensemble": d, "base": True},
              {"id": "D", "stats": _stats(95, sans=-2), "ensemble": d}]   # meilleure note mais fragile
    r = recommander(lignes)
    assert [x["id"] for x in r["liste"]] == ["A", "C"]
    assert r["ecartees"][0]["id"] == "B" and r["ecartees"][0]["proche"] == "A"
    assert recouvrement(a, b) == 0.8


def test_fusion_figee_et_branchee():
    from cotes.laboratoire import REGLES
    from cotes.strategie_recommandee import MEMBRES, RECOMMANDEE_FUSION, paris_fusion
    from cotes.strategies_prudentes import VARIANTES, selections_prudentes
    assert RECOMMANDEE_FUSION in VARIANTES
    assert set(MEMBRES) <= {r.id for r in REGLES}
    assert paris_fusion([]) == set()
    assert selections_prudentes([])["recommandee_fusion"] == set()
