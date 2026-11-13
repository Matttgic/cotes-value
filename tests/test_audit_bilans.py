"""Audit des bilans (docs/audit-bilans.md) : cas réels des données et recoupements du règlement."""
from datetime import datetime, timedelta, timezone
from itertools import permutations, product

import pytest

from cotes import reglement
from cotes.reglement import appliquer, gain, regler, scores_par_periode
from scripts.audit_bilans import erreur_type, regler_independant, roi

T = datetime(2026, 10, 10, 20, 0, tzinfo=timezone.utc)


def test_hockey_score_nul_des_60_minutes_ne_regle_aucun_pari_prolongation_incluse():
    # Pari réel 016561fae52bf691 : Winamax, AHL, Colorado Eagles – Abbotsford Canucks, 10/10/2026, « Vainqueur »
    # à 1,58. Sources betmgm et interwetten-de : 3-3, sans la prolongation. Il avait été remboursé.
    scores = scores_par_periode("hockey", (3, 3), [(0, 1), (2, 2), (1, 0)], ["1", "2", "3"])
    assert scores["TEMPS_REG"] == scores["MATCH"] == (3, 3)
    base = {"sport": "hockey", "periode": "MATCH", "ligne": None}
    assert regler({**base, "marche": "VAINQUEUR", "issue": "EXT"}, scores) is None
    assert regler({**base, "marche": "TOTAL", "issue": "PLUS", "ligne": 5.5}, scores) is None
    assert regler({**base, "marche": "HANDICAP", "issue": "DOM", "ligne": 1.5}, scores) is None
    # les paris sur le temps réglementaire, eux, restent réglés (frère réel b8fffcab43587b53 : nul gagné)
    reg = {"sport": "hockey", "periode": "TEMPS_REG", "ligne": None}
    assert regler({**reg, "marche": "RESULTAT_1N2", "issue": "NUL"}, scores) == "gagne"
    assert regler({**reg, "marche": "TOTAL", "issue": "PLUS", "ligne": 5.5}, scores) == "gagne"


def test_hockey_prolongation_connue_toujours_reglee():
    # Pari réel 611cc29c15703359 : Manitoba Moose – Texas Stars, 3-3 puis 4-3 en prolongation.
    scores = scores_par_periode("hockey", (4, 3), [(1, 1), (1, 0), (1, 2), (1, 0)], ["1", "2", "3", "OT"])
    assert (scores["TEMPS_REG"], scores["MATCH"]) == ((3, 3), (4, 3))
    p = {"sport": "hockey", "marche": "VAINQUEUR", "periode": "MATCH", "ligne": None, "issue": "DOM"}
    assert regler(p, scores) == "gagne"
    assert regler({**p, "issue": "EXT"}, scores) == "perdu"
    # tirs au but : un but au vainqueur de la séance
    tab = scores_par_periode("hockey", (2, 3), [(0, 1), (0, 0), (2, 1), (0, 0), (0, 1)], ["1", "2", "3", "OT", "SO"])
    assert tab["MATCH"] == (2, 3) and regler({**p, "issue": "EXT"}, tab) == "gagne"


def test_hockey_score_nul_reste_a_regler_au_lieu_d_etre_rembourse():
    p = {"id": "016561fae52bf691", "match_id": "winamax|1", "sport": "hockey", "marche": "VAINQUEUR",
         "periode": "MATCH", "ligne": None, "issue": "EXT", "cote": 1.58, "mise": 10.0, "statut": "en_cours",
         "gain": None, "debut": (T - timedelta(hours=19)).isoformat()}
    resultat = {"sport": "hockey", "score": (3, 3), "final": True, "periodes": [(0, 1), (2, 2), (1, 0)],
                "libelles": ["1", "2", "3"], "sources": ["betmgm", "interwetten-de"]}
    appliquer([p], {"winamax|1": resultat}, {}, T)
    assert (p["statut"], p["gain"]) == ("a_regler", None)
    # le résultat retrouvé à la main le règle ensuite
    appliquer([p], {"winamax|1": resultat}, {"winamax|1": {"score": [3, 4], "source": "theahl.com"}}, T)
    assert (p["statut"], p["gain"]) == ("gagne", 5.8)


@pytest.mark.parametrize("ligne", [1.5, 2.5, 3.5])
def test_handicap_libelle_temps_reglementaire_identique_avec_la_prolongation(ligne):
    # 27 paris réels (PMU « Handicap - Temps réglementaire », Betclic « (tps rég.) ») sont rangés en période
    # MATCH pour être comparés à Pinnacle : la prolongation part d'une égalité et ne donne qu'un but d'écart.
    for buts, vainqueur in product(range(6), ("DOM", "EXT")):
        scores = {"TEMPS_REG": (buts, buts), "MATCH": (buts + 1, buts) if vainqueur == "DOM" else (buts, buts + 1)}
        for issue, signe in product(("DOM", "EXT"), (1, -1)):
            p = {"sport": "hockey", "marche": "HANDICAP", "issue": issue, "ligne": signe * ligne}
            assert regler({**p, "periode": "MATCH"}, scores) == regler({**p, "periode": "TEMPS_REG"}, scores)


def test_handicap_demi_but_change_avec_la_prolongation():
    scores = {"TEMPS_REG": (2, 2), "MATCH": (3, 2)}
    p = {"sport": "hockey", "marche": "HANDICAP", "issue": "DOM", "ligne": -0.5}
    assert regler({**p, "periode": "MATCH"}, scores) == "gagne"
    assert regler({**p, "periode": "TEMPS_REG"}, scores) == "perdu"


def test_moteur_independant_d_accord_sur_toutes_les_lignes_y_compris_les_quarts():
    # Aucun quart de ligne (x,25 / x,75) n'existe encore dans les données : seul ce recoupement les couvre.
    lignes = [x / 4 for x in range(-14, 15)]
    scores = list(product(range(5), repeat=2))
    vus = set()
    for (d, e), ligne in product(scores, lignes):
        for marche, issues in (("HANDICAP", ("DOM", "EXT")), ("TOTAL", ("PLUS", "MOINS")),
                               ("TOTAL_DOM", ("PLUS", "MOINS")), ("TOTAL_EXT", ("PLUS", "MOINS"))):
            for issue in issues:
                p = {"marche": marche, "periode": "MATCH", "issue": issue, "ligne": ligne}
                statut = regler(p, {"MATCH": (d, e)})
                assert statut == regler_independant(p, (d, e)), (p, d, e)
                vus.add(statut)
    assert vus == set(reglement.GAIN)
    for (d, e), (m1, m2) in product(scores, [(0, 0), (1, 0), (0, 1)]):
        for marche, issues in (("RESULTAT_1N2", ("DOM", "NUL", "EXT")), ("DRAW_NO_BET", ("DOM", "EXT")),
                               ("DOUBLE_CHANCE", ("HOME_DRAW", "HOME_AWAY", "DRAW_AWAY")),
                               ("BOTH_TEAMS_TO_SCORE", ("YES", "NO")), ("CORRECT_SCORE", ("1-0", "2-2", "0-3")),
                               ("HALF_TIME_FULL_TIME", ("DOM/NUL", "EXT/DOM", "NUL/NUL"))):
            for issue in issues:
                p = {"marche": marche, "periode": "MATCH", "issue": issue, "ligne": None}
                assert regler(p, {"MATCH": (d, e), "MT1": (m1, m2)}) == regler_independant(p, (d, e), (m1, m2))
        for issue, ligne in product(("DOM", "NUL", "EXT"), (-2, -1, 1, 2)):
            p = {"marche": "HANDICAP_3", "periode": "MATCH", "issue": issue, "ligne": ligne}
            assert regler(p, {"MATCH": (d, e)}) == regler_independant(p, (d, e))


def test_quart_de_ligne_gain_des_demi_statuts():
    p = {"marche": "HANDICAP", "periode": "MATCH", "issue": "DOM", "ligne": -0.75}
    assert regler(p, {"MATCH": (1, 0)}) == "demi_gagne" and gain("demi_gagne", 10, 2.0) == 5.0
    p = {"marche": "TOTAL", "periode": "MATCH", "issue": "PLUS", "ligne": 2.25}
    assert regler(p, {"MATCH": (1, 1)}) == "demi_perdu" and gain("demi_perdu", 10, 2.0) == -5.0


def _avance_possible(mi_temps, final, ligne, issue):
    """Toutes les suites de buts compatibles avec la mi-temps et le score final : l'avance demandée a-t-elle pu
    exister, a-t-elle forcément existé ?"""
    sens = 1 if issue == "DOM" else -1
    moities = [mi_temps, (final[0] - mi_temps[0], final[1] - mi_temps[1])]
    ordres = [set(permutations("D" * d + "E" * e)) for d, e in moities]
    resultats = set()
    for premiere, seconde in product(*ordres):
        ecart = maxi = 0
        for but in premiere + seconde:
            ecart += sens if but == "D" else -sens
            maxi = max(maxi, ecart)
        resultats.add(maxi >= ligne)
    return resultats


def test_avance_ou_gagne_contre_toutes_les_suites_de_buts_possibles():
    for (d1, e1), (d2, e2), issue, ligne in product(product(range(3), repeat=2), product(range(3), repeat=2),
                                                    ("DOM", "EXT"), (2.0, 3.0)):
        final = (d1 + d2, e1 + e2)
        p = {"sport": "football", "marche": "AVANCE_OU_GAGNE", "periode": "MATCH", "issue": issue, "ligne": ligne}
        statut = regler(p, {"MATCH": final, "MT1": (d1, e1)})
        gagne_le_match = (final[0] > final[1]) == (issue == "DOM") and final[0] != final[1]
        possibles = _avance_possible((d1, e1), final, ligne, issue)
        if gagne_le_match or possibles == {True}:
            assert statut == "gagne", (p, final, (d1, e1))
        elif possibles == {False}:
            assert statut == "perdu", (p, final, (d1, e1))
        else:                                   # dépend du déroulé : jamais deviné
            assert statut is None, (p, final, (d1, e1))


def test_incertitude_du_roi_plus_large_quand_les_paris_partagent_un_match():
    def pari(match, statut, cote=2.0):
        return {"match_id": match, "statut": statut, "mise": 10.0, "cote": cote,
                "gain": gain(statut, 10.0, cote) if statut in reglement.GAIN else None}
    # trois paris identiques par match : six tickets, mais seulement deux résultats indépendants
    paris = [pari("a", "gagne")] * 3 + [pari("b", "perdu")] * 3 + [pari("c", "en_cours")]
    assert roi(paris) == (6, 0.0, 0.0)
    independants, n = erreur_type(paris)
    par_match, matchs = erreur_type(paris, lambda p: p["match_id"])
    assert (n, matchs) == (6, 2)
    assert par_match == pytest.approx(independants * 3 ** 0.5)
