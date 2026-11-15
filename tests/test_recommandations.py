"""Stratégies recommandées : critères de preuve (CLV Pinnacle corrigée), doublons écartés, fusion figée."""
from cotes.recommandations import raisons_refus, recommander, recouvrement


def _stats(force, matchs=120, couverture=80.0, p=0.001, ecart_haut=5.0, roi=3.0, teste=True):
    """Stratégie dont la borne basse à 95 % de la CLV Pinnacle vaut ``force`` (%)."""
    return {"note": {"total": 50, "matchs": matchs},
            "preuve": {"regles": 2 * matchs, "matchs": matchs, "roi": roi, "clv": force + 1, "clv_n": matchs,
                       "couverture": couverture, "teste": teste, "clv_ic": [force, force + 2] if teste else None,
                       "p": p if teste else None, "ecart_haut": ecart_haut if teste else None}}


def test_criteres_de_preuve():
    assert raisons_refus(_stats(2)) == []
    assert raisons_refus(None) == ["aucun pari réglé"]
    assert "moins de 50 matchs réglés" in raisons_refus(_stats(2, matchs=40))
    assert "clôture Pinnacle connue pour moins de la moitié des paris" in raisons_refus(_stats(2, couverture=30))
    assert raisons_refus(_stats(2, p=0.2)) == ["CLV Pinnacle non prouvée après correction"]
    assert raisons_refus(_stats(2, ecart_haut=-1)) == ["rendement nettement sous la CLV"]
    assert raisons_refus(_stats(2, roi=-4)) == ["ROI négatif"]
    assert raisons_refus(_stats(2, teste=False)) == ["trop peu de clôtures Pinnacle mesurées"]


def test_preuves_mesurees_sur_les_paris_de_chaque_strategie_et_corrigees():
    from datetime import datetime, timedelta, timezone

    from cotes.recommandations import mesurer_preuves
    debut = datetime(2026, 11, 1, tzinfo=timezone.utc)

    def pari(i, clv, gagne):
        d = debut + timedelta(hours=i)
        return {"id": f"p{i}", "reference": "Pinnacle", "bookmaker": "PMU", "sport": "football", "match_id": str(i),
                "marche": "VAINQUEUR", "periode": "MATCH", "ligne": None, "issue": "DOM", "cote": 2.0, "mise": 10.0,
                "detecte": (d - timedelta(hours=3)).isoformat(), "debut": d.isoformat(),
                "statut": "gagne" if gagne else "perdu", "gain": 10.0 if gagne else -10.0,
                "clv": clv, "cote_juste_cloture": round(2.0 / (1 + clv), 4),
                "cloture_lue": (d - timedelta(minutes=10)).isoformat()}
    bons = [pari(i, 0.03 + 0.02 * (i % 3 - 1), i % 5 < 3) for i in range(120)]
    neutres = [pari(1000 + i, 0.02 * (i % 3 - 1), i % 2 == 0) for i in range(120)]
    lignes = [{"id": "A", "stats": {}, "ensemble": {p["id"] for p in bons}},
              {"id": "B", "stats": {}, "ensemble": {p["id"] for p in neutres}},
              {"id": "base:X", "stats": {}, "ensemble": {p["id"] for p in bons}, "base": True}]
    mesurer_preuves(lignes, bons + neutres)
    a, b = lignes[0]["stats"]["preuve"], lignes[1]["stats"]["preuve"]
    assert (a["matchs"], a["couverture"], a["testees"]) == (120, 100.0, 2) and "preuve" not in lignes[2]["stats"]
    assert a["clv_ic"][0] > 0 and a["p"] < 0.001 and raisons_refus(lignes[0]["stats"]) == []
    assert b["p"] > 0.05 and "CLV Pinnacle non prouvée après correction" in raisons_refus(lignes[1]["stats"])


def test_meilleures_preuves_sans_doublon_ni_base():
    a, b, c, d = set(range(100)), set(range(20, 120)), set(range(500, 600)), set(range(1000, 1100))
    lignes = [{"id": "A", "stats": _stats(3.0), "ensemble": a},
              {"id": "B", "stats": _stats(2.8), "ensemble": b},              # 80 % de paris communs avec A
              {"id": "C", "stats": _stats(1.0), "ensemble": c},
              {"id": "base:X", "stats": _stats(9.0), "ensemble": d, "base": True},
              {"id": "D", "stats": _stats(5.0, p=0.3), "ensemble": d}]     # meilleure CLV, non prouvée
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
        [("A", 3.0), ("B", 2.5), ("C", 2.0), ("D", 1.0)])]
    e1 = reviser(None, lignes, date(2026, 11, 8))
    assert [a["id"] for a in e1["actuelles"]] == ["A", "B", "C"] and e1["derniere_revision"] == "2026-11-08"
    # Six jours plus tard, une meilleure stratégie apparaît : rien ne bouge avant la révision.
    lignes.append({"id": "E", "stats": _stats(4.0), "ensemble": ens(9)})
    assert reviser(e1, lignes, date(2026, 11, 14)) == {**e1}
    # Révision : E remplace la plus faible (C, 2,0 < 4,0 − 0,5) ; A garde sa date d'entrée.
    e2 = reviser(e1, lignes, date(2026, 11, 15))
    assert {a["id"]: a["depuis"] for a in e2["actuelles"]} == {"A": "2026-11-08", "B": "2026-11-08", "E": "2026-11-15"}
    assert e2["anciennes"][0]["id"] == "C" and e2["anciennes"][0]["jusqua"] == "2026-11-15"
    # Un peu mieux ne suffit pas (écart < 0,5) ; une recommandée qui échoue un critère sort.
    lignes = [l if l["id"] != "B" else {**l, "stats": _stats(2.5, p=0.2)} for l in lignes]
    lignes.append({"id": "F", "stats": _stats(3.2), "ensemble": ens(8)})
    lignes.append({"id": "G", "stats": _stats(3.4), "ensemble": ens(7)})
    e3 = reviser(e2, lignes, date(2026, 11, 22))
    assert {a["id"] for a in e3["actuelles"]} == {"A", "E", "G"}
    assert e3["anciennes"][-1]["id"] == "B" and "non prouvée" in e3["anciennes"][-1]["raison"]


def test_nouvelle_version_des_criteres_revise_tout_de_suite():
    from datetime import date
    from cotes.recommandations import CRITERES, reviser
    ancien = {"derniere_revision": "2026-11-15", "actuelles": [{"id": "A", "depuis": "2026-11-08", "note_entree": 88}],
              "anciennes": [], "journal": [], "fusions": []}                        # état des critères version 1
    lignes = [{"id": "A", "stats": _stats(2.0, couverture=30), "ensemble": {1}},
              {"id": "B", "stats": _stats(2.0), "ensemble": {2}}]
    e = reviser(ancien, lignes, date(2026, 11, 16))
    assert e["criteres"] == CRITERES and [a["id"] for a in e["actuelles"]] == ["B"]
    assert e["anciennes"][0]["raison"].endswith("(critères version 2)")
    assert reviser(e, lignes, date(2026, 11, 17)) == e                              # puis tous les 7 jours


def test_etat_ecrit_dans_donnees(tmp_path):
    from datetime import datetime, timezone
    from cotes.recommandations import FICHIER, mettre_a_jour
    lignes = [{"id": "A", "stats": _stats(2.0), "ensemble": {1, 2}}]
    e = mettre_a_jour(tmp_path, lignes, datetime(2026, 11, 8, 10, tzinfo=timezone.utc))
    assert e["prochaine_revision"] == "2026-11-15" and (tmp_path / FICHIER).exists()
    assert mettre_a_jour(tmp_path, [], datetime(2026, 11, 10, tzinfo=timezone.utc))["actuelles"][0]["id"] == "A"


def test_nouvelle_fusion_quand_la_liste_change_et_places_activees():
    from datetime import date
    from cotes.recommandations import reviser
    from cotes.strategie_recommandee import FUSIONS_AUTO, MEMBRES, charger_fusions, selection_fusion_auto
    ens = lambda i: set(range(1000 * i, 1000 * i + 100))  # noqa: E731
    lignes = [{"id": m, "stats": _stats(3.0 - i / 10), "ensemble": ens(i)} for i, m in enumerate(MEMBRES)]
    e1 = reviser(None, lignes, date(2026, 11, 8))
    assert e1["fusions"] == []                                   # même liste que Fusion 1 : pas de doublon
    lignes.append({"id": "Grok 8 · Polymarket hors foot", "stats": _stats(5.0), "ensemble": ens(7)})
    lignes.append({"id": "Fusion 1 · recommandées du 8/11", "stats": _stats(9.0), "ensemble": ens(8)})
    e2 = reviser(e1, lignes, date(2026, 11, 15), instant="2026-11-15T09:00:00+01:00")
    assert "Fusion 1 · recommandées du 8/11" not in {a["id"] for a in e2["actuelles"]}   # une fusion n'est pas candidate
    f = e2["fusions"][-1]
    assert f["n"] == 2 and f["debut"] == "2026-11-15T09:00:00+01:00" and "Grok 8 · Polymarket hors foot" in f["membres"]
    assert reviser(e2, lignes, date(2026, 11, 22))["fusions"] == e2["fusions"]          # liste inchangée : rien
    actives = charger_fusions(e2)
    try:
        assert [p["cle"] for p in actives] == ["fusion_2"] and actives[0]["membres"] == tuple(f["membres"])
        assert selection_fusion_auto([], FUSIONS_AUTO[1], {}) == set()                   # place libre : aucun pari
    finally:
        charger_fusions({})
    assert not any(p["actif"] for p in FUSIONS_AUTO)
