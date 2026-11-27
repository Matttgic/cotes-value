"""Audit du code cœur du 26/11/2026 (docs/audit-26-11-code.md) : chaque test échoue sur le code d'avant."""
from datetime import datetime, timezone

from cotes import resultats as R
from cotes.comparaison import libelle_pari
from cotes.reglement import appliquer, regler, scores_par_periode

MAINTENANT = datetime(2026, 11, 26, 23, 0, tzinfo=timezone.utc)


def pari_volley(**kw):
    """Pari réel 19fc8e2c46bb24be (PMU, « Point Handicap - 1re set »), resté « à régler »."""
    return {"id": "19fc8e2c46bb24be", "bookmaker": "PMU", "sport": "volley", "ligue": "Efelerligi",
            "match_id": "pmu|1", "domicile": "Onikisubat Bld", "exterieur": "Ziraat Bankasi Ankara",
            "match_reference": "Onikisubat - Ziraat Bankasi Ankara", "debut": "2026-11-24T11:00:00Z",
            "marche": "POINTS_HANDICAP", "periode": "SET1", "ligne": 4.5, "issue": "EXT", "cote": 1.74, "mise": 10.0,
            "statut": "a_regler", "gain": None, **kw}


def enr_volley(source, score, periodes):
    return {"source": source, "sport": "volley", "domicile": "Onikisubat Bld", "exterieur": "Ziraat Bankasi Ankara",
            "debut": datetime(2026, 11, 24, 11, 0, tzinfo=timezone.utc), "score": score, "periodes": periodes,
            "libelles": [str(i + 1) for i in range(len(periodes))], "corners": None}


def test_volley_points_du_1er_set_regles_par_les_sources():
    """Flashscore donne les points de chaque set ; le consensus les jetait (somme des points ≠ score en sets) et le
    règlement ignorait le préfixe POINTS_ : les paris « handicap en points du 1er set » restaient à régler."""
    p = pari_volley()
    sources = [enr_volley("flashscore", (0, 3), [(19, 25), (20, 25), (16, 25)]), enr_volley("365scores", (0, 3), [])]
    r = R.consensus(p, sources, MAINTENANT)
    assert r["score"] == (0, 3) and r["periodes"] == [(19, 25), (20, 25), (16, 25)]
    appliquer([p], {p["match_id"]: r}, {}, MAINTENANT)
    assert p["statut"] == "gagne" and p["gain"] == 7.4          # Ziraat −4,5 : set gagné 25-19
    assert p["preuve_reglement"]["scores"]["SET1"] == (19, 25)


def test_volley_points_du_1er_set_regles_par_une_saisie_avec_periodes():
    """Même avec les points des sets saisis à la main, le pari ne se réglait pas (37e5d275bac39a34)."""
    p = pari_volley(id="37e5d275bac39a34", domicile="Budowlani Łódź (F)", exterieur="Galatasaray Istanbul (F)",
                    ligne=3.5, issue="DOM", cote=1.9)
    manuels = {p["match_id"]: {"score": [1, 3], "periodes": [[25, 23], [19, 25], [22, 25], [21, 25]],
                               "source": "Flashscore"}}
    appliquer([p], {}, manuels, MAINTENANT)
    assert p["statut"] == "gagne" and p["gain"] == 9.0


def test_volley_marches_points_et_sets():
    sc = scores_par_periode("volley", (3, 2), [(25, 20), (22, 25), (25, 23), (23, 25), (15, 13)], ["1"] * 5)
    assert sc["MATCH"] == (3, 2) and sc["SET1"] == (25, 20) and sc["SET5"] == (15, 13) and sc["POINTS"] == (110, 106)
    pari = lambda m, per, i, ligne=None: {"sport": "volley", "marche": m, "periode": per, "issue": i, "ligne": ligne}  # noqa: E731
    assert regler(pari("POINTS_HANDICAP", "SET1", "EXT", -5.5), sc) == "gagne"    # extérieur +5,5 : 20 + 5,5 > 25
    assert regler(pari("POINTS_HANDICAP", "SET1", "DOM", -5.5), sc) == "perdu"    # domicile −5,5 : 25-20 ne suffit pas
    assert regler(pari("POINTS_HANDICAP", "MATCH", "DOM", -3.5), sc) == "gagne"   # 110-106 en points
    assert regler(pari("POINTS_TOTAL", "SET1", "PLUS", 44.5), sc) == "gagne"
    assert regler(pari("VAINQUEUR", "SET2", "EXT"), sc) == "gagne"
    assert regler(pari("HANDICAP", "MATCH", "DOM", -1.5), sc) == "perdu"          # le handicap du match reste en sets


def test_volley_points_incoherents_avec_les_sets_ignores():
    """Un détail qui ne redonne pas le score en sets n'est pas utilisé (set manquant, inversion)."""
    sc = scores_par_periode("volley", (3, 0), [(25, 20), (25, 23)], ["1", "2"])
    assert sc == {"MATCH": (3, 0)}
    assert regler({"sport": "volley", "marche": "POINTS_HANDICAP", "periode": "SET1", "issue": "DOM", "ligne": -1.5},
                  sc) is None


def test_libelle_handicap_en_points_avec_son_signe():
    """« POINTS_HANDICAP EXT 4.5 » se lisait +4,5 pour l'extérieur, alors que la ligne est celle du domicile."""
    assert libelle_pari(pari_volley()) == "Ziraat Bankasi Ankara -4,5 points (1er set)"
