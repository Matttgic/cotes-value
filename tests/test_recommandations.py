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


def test_liste_stable_entre_deux_revisions_puis_remplacement_et_sortie():
    from datetime import date
    from cotes.recommandations import reviser
    ens = lambda i: set(range(1000 * i, 1000 * i + 100))  # noqa: E731
    lignes = [{"id": n, "stats": _stats(t), "ensemble": ens(i)} for i, (n, t) in enumerate(
        [("A", 90), ("B", 85), ("C", 80), ("D", 70)])]
    e1 = reviser(None, lignes, date(2026, 11, 8))
    assert [a["id"] for a in e1["actuelles"]] == ["A", "B", "C"] and e1["derniere_revision"] == "2026-11-08"
    # Six jours plus tard, une meilleure stratégie apparaît : rien ne bouge avant la révision.
    lignes.append({"id": "E", "stats": _stats(95), "ensemble": ens(9)})
    assert reviser(e1, lignes, date(2026, 11, 14)) == {**e1}
    # Révision : E remplace la plus faible (C, 80 < 95 − 5) ; A garde sa date d'entrée.
    e2 = reviser(e1, lignes, date(2026, 11, 15))
    assert {a["id"]: a["depuis"] for a in e2["actuelles"]} == {"A": "2026-11-08", "B": "2026-11-08", "E": "2026-11-15"}
    assert e2["anciennes"][0]["id"] == "C" and e2["anciennes"][0]["jusqua"] == "2026-11-15"
    # Une note un peu meilleure ne suffit pas (écart < 5) ; une recommandée qui échoue un critère sort.
    lignes = [l if l["id"] != "B" else {**l, "stats": _stats(85, borne=-1)} for l in lignes]
    lignes.append({"id": "F", "stats": _stats(88), "ensemble": ens(8)})
    e3 = reviser(e2, lignes, date(2026, 11, 22))
    assert {a["id"] for a in e3["actuelles"]} == {"A", "E", "F"}
    assert e3["anciennes"][-1]["id"] == "B" and "borne basse" in e3["anciennes"][-1]["raison"]


def test_etat_ecrit_dans_donnees(tmp_path):
    from datetime import datetime, timezone
    from cotes.recommandations import FICHIER, mettre_a_jour
    lignes = [{"id": "A", "stats": _stats(90), "ensemble": {1, 2}}]
    e = mettre_a_jour(tmp_path, lignes, datetime(2026, 11, 8, 10, tzinfo=timezone.utc))
    assert e["prochaine_revision"] == "2026-11-15" and (tmp_path / FICHIER).exists()
    assert mettre_a_jour(tmp_path, [], datetime(2026, 11, 10, tzinfo=timezone.utc))["actuelles"][0]["id"] == "A"
