from cotes.reglement import gain, regler, scores_par_periode


def p(marche, issue, ligne=None, periode="MATCH"):
    return {"marche": marche, "issue": issue, "ligne": ligne, "periode": periode}


FOOT = scores_par_periode("football", (2, 1), [(1, 0), (1, 1)], ["1", "2"])


def test_periodes_foot():
    assert FOOT == {"MT1": (1, 0), "MT2": (1, 1), "MATCH": (2, 1)}


def test_resultat_et_double_chance():
    assert regler(p("RESULTAT_1N2", "DOM"), FOOT) == "gagne"
    assert regler(p("RESULTAT_1N2", "NUL", periode="MT2"), FOOT) == "gagne"
    assert regler(p("DOUBLE_CHANCE", "DRAW_AWAY"), FOOT) == "perdu"
    assert regler(p("DRAW_NO_BET", "EXT", periode="MT2"), FOOT) == "rembourse"


def test_handicap_asiatique():
    # domicile gagne 2-1 : -1 remboursé, -0,75 demi-gagné, -1,25 demi-perdu, +0,25 pour l'extérieur demi-perdu
    assert regler(p("HANDICAP", "DOM", -1), FOOT) == "rembourse"
    assert regler(p("HANDICAP", "DOM", -0.75), FOOT) == "demi_gagne"
    assert regler(p("HANDICAP", "DOM", -1.25), FOOT) == "demi_perdu"
    assert regler(p("HANDICAP", "EXT", -0.25), FOOT) == "perdu"
    assert regler(p("HANDICAP", "EXT", -1.5), FOOT) == "gagne"       # extérieur +1,5


def test_totaux():
    assert regler(p("TOTAL", "PLUS", 2.5), FOOT) == "gagne"
    assert regler(p("TOTAL", "MOINS", 3), FOOT) == "rembourse"
    assert regler(p("TOTAL", "PLUS", 2.75), FOOT) == "demi_gagne"
    assert regler(p("TOTAL_EXT", "MOINS", 0.5), FOOT) == "perdu"
    assert regler(p("TOTAL", "MOINS", 0.5, "MT1"), FOOT) == "perdu"


def test_specials_foot():
    assert regler(p("CORRECT_SCORE", "2-1"), FOOT) == "gagne"
    assert regler(p("BOTH_TEAMS_TO_SCORE", "YES"), FOOT) == "gagne"
    assert regler(p("HALF_TIME_FULL_TIME", "DOM/DOM"), FOOT) == "gagne"
    assert regler(p("HANDICAP_3", "NUL", -1), FOOT) == "gagne"
    assert regler(p("CORNERS_TOTAL", "PLUS", 9.5), FOOT) is None
    assert regler(p("CORNERS_TOTAL", "PLUS", 9.5), {**FOOT, "CORNERS": (7, 3)}) == "gagne"


def test_hockey_temps_reglementaire():
    s = scores_par_periode("hockey", (3, 2), [(1, 1), (0, 1), (1, 0), (1, 0)], ["1", "2", "3", "OT"])
    assert s["TEMPS_REG"] == (2, 2)
    assert regler(p("RESULTAT_1N2", "NUL", periode="TEMPS_REG"), s) == "gagne"
    assert regler(p("VAINQUEUR", "DOM"), s) == "gagne"


def test_tennis():
    s = scores_par_periode("tennis", (2, 1), [(6, 4), (3, 6), (7, 5)], ["1", "2", "3"])
    assert regler(p("JEUX_TOTAL", "PLUS", 30.5), s) == "gagne"        # 31 jeux
    assert regler(p("SETS_HANDICAP", "DOM", -1.5), s) == "perdu"
    assert regler(p("VAINQUEUR", "DOM", periode="SET1"), s) == "gagne"
    assert regler(p("JEUX_HANDICAP", "EXT", 1.5, "SET1"), s) == "perdu"


def test_gains():
    assert gain("gagne", 10, 2.5) == 15.0
    assert gain("demi_gagne", 10, 1.9) == 4.5
    assert gain("demi_perdu", 10, 1.9) == -5.0
    assert gain("rembourse", 10, 3) == 0.0
