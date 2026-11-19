from cotes.strategie_neon import NEON_3, NEON_2, NEON_1, SELECTEURS, motif_refus_neon, selection_neon

DEPART = "2026-11-20T00:00:00+00:00"


def _p(**k):
    base = {"reference": "Pinnacle", "bookmaker": "PMU", "sport": "football", "marche": "RESULTAT_1N2", "cote": 2.2,
            "ecart": 0.05, "detecte": "2026-11-20T10:00:00+00:00", "debut": "2026-11-20T18:00:00+00:00",
            "match_id": "pmu|1", "periode": "MATCH", "ligne": None, "issue": "1", "domicile": "Lyon",
            "exterieur": "Nice"}
    return {**base, **k}


def test_regle_socle():
    c = NEON_1
    assert motif_refus_neon(_p(), c) is None
    assert motif_refus_neon(_p(reference="Matchbook"), c) is None
    assert motif_refus_neon(_p(reference="Polymarket"), c) == "référence hors périmètre"
    assert motif_refus_neon(_p(bookmaker="Winamax"), c) == "bookmaker hors périmètre"
    assert motif_refus_neon(_p(sport="volley"), c) == "sport écarté"
    assert motif_refus_neon(_p(sport="basket", marche="TOTAL"), c) == "marché écarté"
    assert motif_refus_neon(_p(sport="football", marche="TOTAL"), c) is None
    assert motif_refus_neon(_p(marche="CORRECT_SCORE"), c) == "marché écarté"
    assert motif_refus_neon(_p(periode="MT1"), c) == "période écartée"
    assert motif_refus_neon(_p(cote=4.0, ecart=0.04), c) is None
    assert motif_refus_neon(_p(cote=4.01), c) == "cote hors intervalle"
    assert motif_refus_neon(_p(ecart=0.0399), c) == "écart hors intervalle"
    assert motif_refus_neon(_p(ecart=0.2501), c) == "écart hors intervalle"
    assert motif_refus_neon(_p(debut="2026-11-21T10:00:00+00:00"), c) is None             # 24 h pile
    assert motif_refus_neon(_p(debut="2026-11-21T10:00:01+00:00"), c) == "détection trop tôt"
    assert motif_refus_neon(_p(debut="2026-11-20T09:59:59+00:00"), c) == "match déjà commencé"
    assert motif_refus_neon(_p(preuve_prise={"equipes_inversees": True}), c) is not None


def test_regles_sniper_et_consensus():
    assert motif_refus_neon(_p(), NEON_2) == "écart hors intervalle"
    assert motif_refus_neon(_p(ecart=0.06), NEON_2) is None
    assert motif_refus_neon(_p(ecart=0.06, debut="2026-11-20T22:00:01+00:00"), NEON_2) == "détection trop tôt"
    assert motif_refus_neon(_p(reference="Consensus", ecart=0.025), NEON_3) is None
    assert motif_refus_neon(_p(ecart=0.025), NEON_3) == "référence hors périmètre"


def test_un_pari_par_match_et_premiere_prise():
    a = _p(detecte="2026-11-20T10:00:00+00:00")
    b = _p(detecte="2026-11-20T10:05:00+00:00", marche="TOTAL", issue="PLUS", ligne=2.5, match_id="pmu|1")
    autre = _p(match_id="pmu|2", domicile="Lens", exterieur="Lille", detecte="2026-11-20T10:01:00+00:00")
    assert selection_neon([a, b, autre], NEON_1, DEPART) == {id(a), id(autre)}
    # Même seconde, même match : le plus gros écart l'emporte.
    c = _p(marche="TOTAL", issue="PLUS", ligne=2.5, ecart=0.08)
    assert selection_neon([a, c], NEON_1, DEPART) == {id(c)}
    # La cote a d'abord été vue par Polymarket (hors liste) : Socle l'écarte, Consensus ne regarde pas l'ordre.
    poly = _p(reference="Polymarket", detecte="2026-11-20T09:59:00+00:00")
    assert selection_neon([poly, a], NEON_1, DEPART) == set()
    cons = _p(reference="Consensus", detecte="2026-11-20T10:02:00+00:00")
    assert selection_neon([a, cons], NEON_3, DEPART) == {id(cons)}
    # Rien avant le lancement.
    assert selection_neon([_p(detecte="2026-11-19T23:59:59+00:00")], NEON_1, DEPART) == set()


def test_sans_rejeu():
    assert all(SELECTEURS[c["cle"]]([_p()], depuis="2026-11-01T00:00:00+00:00") == set()
               for c in (NEON_1, NEON_2, NEON_3))
