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
    assert regler(p("TOTAL", "PLUS", 4.5), s) == "gagne"             # prolongation incluse
    assert regler(p("TOTAL", "PLUS", 4.5, "TEMPS_REG"), s) == "perdu"


def test_hockey_tirs_au_but():
    # 2-2 après prolongation, l'extérieur gagne les tirs au but 2-1 : un but de plus pour lui (3 buts à 2... soit 5)
    s = scores_par_periode("hockey", (2, 3), [(1, 0), (1, 1), (0, 1), (0, 0), (1, 2)], ["1", "2", "3", "OT", "SO"])
    assert s["MATCH"] == (2, 3)
    assert regler(p("TOTAL", "PLUS", 4.5), s) == "gagne"
    assert regler(p("VAINQUEUR", "EXT"), s) == "gagne"
    assert regler(p("DRAW_NO_BET", "DOM", periode="TEMPS_REG"), s) == "rembourse"


def test_basket_temps_reglementaire_et_prolongation():
    s = scores_par_periode("basket", (110, 105), [(25, 25), (25, 25), (25, 25), (25, 25), (10, 5)],
                           ["1", "2", "3", "4", "OT"])
    assert s["TEMPS_REG"] == (100, 100) and s["MATCH"] == (110, 105)
    assert regler(p("VAINQUEUR", "DOM", periode="TEMPS_REG"), s) == "rembourse"   # Unibet, NetBet
    assert regler(p("VAINQUEUR", "DOM"), s) == "gagne"                            # Winamax, PMU
    assert regler(p("TOTAL", "PLUS", 210.5), s) == "gagne"


def test_tennis():
    s = scores_par_periode("tennis", (2, 1), [(6, 4), (3, 6), (7, 5)], ["1", "2", "3"])
    assert regler(p("JEUX_TOTAL", "PLUS", 30.5), s) == "gagne"        # 31 jeux
    assert regler(p("SETS_HANDICAP", "DOM", -1.5), s) == "perdu"
    assert regler(p("VAINQUEUR", "DOM", periode="SET1"), s) == "gagne"
    assert regler(p("JEUX_HANDICAP", "EXT", 1.5, "SET1"), s) == "perdu"


def test_tennis_super_tie_break():
    s = scores_par_periode("tennis", (2, 1), [(6, 4), (3, 6), (10, 8)], ["1", "2", "3"])
    assert s["JEUX"] == (10, 10) and "ABANDON" not in s                   # super tie-break = 1 jeu
    assert regler(p("JEUX_TOTAL", "MOINS", 20.5), s) == "gagne"


def test_tennis_abandon():
    # 6-4, 3-1 puis abandon
    s = scores_par_periode("tennis", (1, 0), [(6, 4), (3, 1)], ["1", "2"])
    assert s["ABANDON"]
    assert regler(p("VAINQUEUR", "DOM"), s) == "rembourse"
    assert regler(p("VAINQUEUR", "DOM", periode="SET1"), s) == "gagne"        # set terminé : maintenu
    assert regler(p("JEUX_TOTAL", "PLUS", 12.5), s) == "gagne"                 # 14 jeux : seuil dépassé
    assert regler(p("JEUX_TOTAL", "MOINS", 12.5), s) == "perdu"
    assert regler(p("JEUX_TOTAL", "PLUS", 20.5), s) == "rembourse"
    sets = {**p("SETS_TOTAL", "PLUS", 1.5), "bookmaker": "Winamax"}
    assert regler(sets, s) == "gagne"                                          # 2 sets certains
    assert regler({**sets, "bookmaker": "NetBet"}, s) == "rembourse"


def test_gains():
    assert gain("gagne", 10, 2.5) == 15.0
    assert gain("demi_gagne", 10, 1.9) == 4.5
    assert gain("demi_perdu", 10, 1.9) == -5.0
    assert gain("rembourse", 10, 3) == 0.0


def test_signaux_suspects_sans_pari():
    from cotes.comparaison import comparer
    from cotes.simulation import placer
    base = {"sport": "football", "ligue": "L", "domicile": "Lens", "exterieur": "Lille",
            "debut": "2030-01-01T20:00:00+00:00", "collecte": "2029-12-31T20:00:00+00:00", "marche": "TOTAL",
            "periode": "MATCH", "ligne": 2.5, "issue": "PLUS", "joueur": None}
    fr = [{**base, "source": "winamax", "match_id": "w1", "cote": 4.0},       # écart énorme
          {**base, "source": "betclic", "match_id": "b1", "cote": 2.2}]       # écart de 10 %
    ref = [{**base, "source": "pinnacle", "match_id": "p1", "cote": 1.95, "proba_juste": 0.5, "marge": 0.03}]
    opp = {o["bookmaker"]: o for o in comparer(fr, {"Pinnacle": ref})}
    assert opp["winamax"]["suspect"] == "écart trop grand" and opp["betclic"]["suspect"] is None
    paris = []
    placer(list(opp.values()), paris)
    assert paris and all(p["bookmaker"] == "betclic" for p in paris)


def test_betfair_issues_manquantes_pas_gonflees():
    from cotes.comparaison import reference_betfair
    def l(issue, achat, vente):
        return {"cle_marche": "cs", "marche": "CORRECT_SCORE", "periode": "MATCH", "ligne": None, "issue": issue,
                "achat": [{"price": achat, "liquidity": 50}], "vente": [{"price": vente, "liquidity": 50}]}
    # deux scores seulement sur une quinzaine : les probabilités restent celles du marché
    r = {x["issue"]: x["proba_juste"] for x in reference_betfair([l("1-1", 9.0, 10.0), l("2-2", 15.0, 17.0)])}
    assert abs(r["1-1"] - (1 / 9 + 1 / 10) / 2) < 1e-6
