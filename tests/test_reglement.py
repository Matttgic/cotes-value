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


def test_tennis_score_final_sans_detail_des_sets():
    # revue externe (B1) : sans le détail des sets, le score 2-0 devenait 0-0 (vainqueur remboursé,
    # « plus de 20,5 jeux » perdu sur 0 jeu)
    s = scores_par_periode("tennis", (2, 0), [], [])
    assert s == {"MATCH": (2, 0)}
    t = {"sport": "tennis"}
    assert regler({**t, **p("VAINQUEUR", "DOM")}, s) == "gagne"
    assert regler({**t, **p("VAINQUEUR", "EXT")}, s) == "perdu"
    assert regler({**t, **p("SETS_HANDICAP", "DOM", -1.5)}, s) == "gagne"
    assert regler({**t, **p("SETS_TOTAL", "PLUS", 2.5)}, s) == "perdu"
    assert regler({**t, **p("JEUX_TOTAL", "PLUS", 20.5)}, s) is None           # jeux inconnus : on attend
    assert regler({**t, **p("JEUX_HANDICAP", "DOM", -3.5)}, s) is None
    assert regler({**t, **p("VAINQUEUR", "DOM", periode="SET1")}, s) is None
    # 2-1 sans détail : sets réglables, jeux non
    s = scores_par_periode("tennis", (2, 1), [], [])
    assert regler({**t, **p("SETS_TOTAL", "PLUS", 2.5)}, s) == "gagne"
    assert regler({**t, **p("JEUX_TOTAL", "MOINS", 30.5)}, s) is None


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


def test_reference_pinnacle_brut():
    from cotes.comparaison import comparer
    base = {"sport": "football", "ligue": "L", "domicile": "Lens", "exterieur": "Lille", "libelle": "x",
            "debut": "2030-01-01T20:00:00+00:00", "collecte": "2029-12-31T20:00:00+00:00", "marche": "VAINQUEUR",
            "periode": "MATCH", "ligne": None, "issue": "DOM", "joueur": None}
    ref = [{**base, "source": "pinnacle", "match_id": "p1", "cote": 1.95, "proba_juste": 0.5, "marge_pinnacle": 0.026}]
    # 1,98 : au-dessus de la cote affichée (1,95) mais sous la cote juste (2,00) -> seulement « Pinnacle brut »
    o = {x["reference"]: x for x in comparer([{**base, "source": "winamax", "match_id": "w1", "cote": 1.98}],
                                             {"Pinnacle": ref}, ecart_min=0.01)}
    assert set(o) == {"Pinnacle brut"} and o["Pinnacle brut"]["cote_juste"] == 1.95


def test_bilan_toutes_sans_le_temoin():
    from cotes.simulation import bilan
    p = {"simulation": "A", "statut": "gagne", "mise": 10, "gain": 10.0, "clv": 0.02}
    b = bilan([{**p, "reference": "Pinnacle"}, {**p, "reference": "Pinnacle brut", "statut": "perdu", "gain": -10.0}])
    assert b["A|Toutes"]["gains"] == 10.0 and b["A|Toutes"]["gagnes"] == 1 and b["A|Pinnacle brut"]["gains"] == -10.0


def test_bilan_par_tranche_de_cote():
    from cotes.simulation import bilan_tranches, tranche
    assert tranche(1.5) == "1,01 – 1,50" and tranche(1.51) == "1,51 – 2,00" and tranche(25) == "plus de 10"
    p = {"reference": "Pinnacle", "statut": "gagne", "mise": 10, "clv": None}
    b = bilan_tranches([{**p, "simulation": "A", "cote": 1.8, "gain": 8.0},
                        {**p, "simulation": "X", "cote": 15.0, "gain": 140.0}])
    assert b["1,51 – 2,00|Toutes"]["paris"] == 1 and b["plus de 10|Pinnacle"]["gains"] == 140.0


def test_tranches_d_ecart_un_pari_une_fois():
    from cotes.simulation import placer, simulation_de
    assert [simulation_de(e, 2.0) for e in (0.019, 0.02, 0.029, 0.03, 0.045, 0.06, 0.07, 0.30)] == \
        [None, "A", "A", "B", "C", "D", "E", "E"]
    assert simulation_de(0.025, 12.0) is None and simulation_de(0.05, 12.0) == "X"
    o = {"reference": "Pinnacle", "detecte": "t1", "bookmaker": "Winamax", "sport": "football", "match_id": "w1",
         "domicile": "A", "exterieur": "B", "debut": "d", "marche": "TOTAL", "periode": "MATCH", "ligne": 2.5,
         "issue": "PLUS", "pari": "x", "cote": 2.1, "cote_juste": 2.05, "ecart": 0.025}
    paris = []
    assert [p["simulation"] for p in placer([o], paris)] == ["A"]
    # plus tard l'écart passe à 6 % : même pari, pas repris dans D
    assert placer([{**o, "detecte": "t2", "cote": 2.2, "ecart": 0.06}], paris) == [] and len(paris) == 1


def test_deduction_sans_score_a_la_mi_temps():
    from cotes.reglement import regler
    pari = lambda **k: {"sport": "football", "periode": "MATCH", "ligne": None, **k}   # noqa: E731
    nul00, nul11 = {"MATCH": (0, 0)}, {"MATCH": (1, 1)}
    assert regler(pari(marche="HALF_TIME_FULL_TIME", issue="EXT/DOM"), nul00) == "perdu"
    assert regler(pari(marche="HALF_TIME_FULL_TIME", issue="NUL/NUL"), nul00) == "gagne"
    assert regler(pari(marche="HALF_TIME_FULL_TIME", issue="EXT/DOM"), nul11) == "perdu"
    assert regler(pari(marche="HALF_TIME_FULL_TIME", issue="DOM/NUL"), nul11) is None      # dépend de la mi-temps
    assert regler(pari(marche="CORRECT_SCORE", periode="MT1", issue="2-1"), nul11) == "perdu"
    assert regler(pari(marche="CORRECT_SCORE", periode="MT1", issue="1-0"), nul11) is None
    assert regler(pari(marche="TOTAL", periode="MT1", ligne=2.5, issue="PLUS"), nul11) == "perdu"
    assert regler(pari(marche="TOTAL", periode="MT1", ligne=2.5, issue="MOINS"), nul11) == "gagne"
    assert regler(pari(marche="TOTAL", periode="MT1", ligne=1.5, issue="MOINS"), nul11) is None
    assert regler(pari(marche="RESULTAT_1N2", periode="MT1", issue="NUL"), nul00) == "gagne"


def test_clv_seulement_avec_une_reference_fraiche_et_avant_le_match():
    # revue externe (B2) : la CLV ne doit pas être mise à jour avec une référence périmée ou lue après le
    # coup d'envoi, et `cloture_lue` doit être l'heure de lecture de la référence
    from datetime import datetime, timezone
    from cotes.marches import cle
    from cotes.simulation import suivre_cloture
    pari = {"statut": "en_cours", "debut": "2026-10-07T18:00:00+00:00", "match_id": "m", "reference": "Pinnacle",
            "cote": 2.0, "marche": "VAINQUEUR", "periode": "MATCH", "ligne": None, "issue": "DOM", "joueur": None}
    k = ("m", cle(pari))
    a = lambda h, m: datetime(2026, 10, 7, h, m, tzinfo=timezone.utc)  # noqa: E731
    suivre_cloture([pari], {k: {"Pinnacle": (0.55, "2026-10-07T17:20:00+00:00")}}, a(17, 50))
    assert "clv" not in pari                                                  # 30 min : périmée
    suivre_cloture([pari], {k: {"Pinnacle": (0.55, "2026-10-07T17:45:00+00:00")}}, a(17, 50))
    assert pari["clv"] == 0.1 and pari["cloture_lue"] == "2026-10-07T17:45:00+00:00"
    suivre_cloture([pari], {k: {"Pinnacle": (0.40, "2026-10-07T17:49:00+00:00")}}, a(17, 50))
    assert pari["clv"] == -0.2
    suivre_cloture([pari], {k: {"Pinnacle": (0.60, "2026-10-07T17:30:00+00:00")}}, a(17, 50))
    assert pari["clv"] == -0.2                                                # nouvelle valeur périmée : on garde
    suivre_cloture([pari], {k: {"Pinnacle": (0.60, "2026-10-07T18:01:00+00:00")}}, a(17, 59))
    assert pari["clv"] == -0.2                                                # lue après le coup d'envoi


def test_clv_heure_future_refusee_et_jamais_de_retour_en_arriere():
    # revue externe (R4)
    from datetime import datetime, timezone
    from cotes.marches import cle
    from cotes.simulation import suivre_cloture
    pari = {"statut": "en_cours", "debut": "2026-10-07T18:00:00+00:00", "match_id": "m", "reference": "Pinnacle",
            "cote": 2.0, "marche": "VAINQUEUR", "periode": "MATCH", "ligne": None, "issue": "DOM", "joueur": None}
    k = ("m", cle(pari))
    a = datetime(2026, 10, 7, 17, 50, tzinfo=timezone.utc)
    suivre_cloture([pari], {k: {"Pinnacle": (0.55, "2026-10-07T17:52:00+00:00")}}, a)
    assert "clv" not in pari                                                  # heure dans le futur
    suivre_cloture([pari], {k: {"Pinnacle": (0.55, "2026-10-07T17:45:00+00:00")}}, a)
    suivre_cloture([pari], {k: {"Pinnacle": (0.40, "2026-10-07T17:40:00+00:00")}}, a)
    assert pari["clv"] == 0.1 and pari["cloture_lue"] == "2026-10-07T17:45:00+00:00"
    suivre_cloture([pari], {k: {"Pinnacle": (0.55, "2026-10-07T17:45:00")}}, a)  # sans fuseau : ignorée, pas d'erreur
    assert pari["cloture_lue"] == "2026-10-07T17:45:00+00:00"


def test_clv_du_bilan_seulement_pres_du_coup_d_envoi():
    # revue externe (R3) : une CLV relevée 1 h avant le match reste sur le pari mais pas dans la moyenne
    from cotes.simulation import bilan, clv_finale
    base = {"simulation": "A", "reference": "Pinnacle", "mise": 10, "gain": -10, "statut": "perdu",
            "debut": "2026-10-07T18:00:00+00:00"}
    loin = {**base, "clv": 0.10, "cloture_lue": "2026-10-07T17:00:00+00:00"}
    pres = {**base, "clv": 0.02, "cloture_lue": "2026-10-07T17:55:00+00:00"}
    ouvert = {**pres, "statut": "en_cours", "gain": None}
    assert clv_finale(loin) is None and clv_finale(pres) == 0.02 and clv_finale(ouvert) is None
    b = bilan([loin, pres, ouvert])["A|Pinnacle"]
    assert b["clv_moyenne"] == 0.02 and b["clv_n"] == 1 and b["regles"] == 2
