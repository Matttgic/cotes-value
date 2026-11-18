from cotes.strategie_claude_drop import CLAUDE_DROP, motif_refus_claude_drop, selection_claude_drop


def _p(**k):
    base = {"reference": "Pinnacle", "bookmaker": "PMU", "marche": "TOTAL", "cote": 2.2, "ecart": 0.04,
            "mouvement_pinnacle": 0.05, "mouvement_s": 900,
            "detecte": "2026-11-18T10:00:00+00:00", "debut": "2026-11-18T18:00:00+00:00", "match_id": "pmu|1",
            "periode": "MATCH", "ligne": 2.5, "issue": "PLUS"}
    return {**base, **k}


def test_regle():
    assert motif_refus_claude_drop(_p()) is None
    assert motif_refus_claude_drop(_p(mouvement_pinnacle=0.03)) is None
    assert motif_refus_claude_drop(_p(mouvement_pinnacle=0.029)) == "pas de chute Pinnacle"
    assert motif_refus_claude_drop(_p(mouvement_pinnacle=-0.05)) == "pas de chute Pinnacle"
    assert motif_refus_claude_drop(_p(mouvement_pinnacle=None)) == "mouvement Pinnacle non mesuré"
    assert motif_refus_claude_drop(_p(reference="Polymarket")) == "référence hors périmètre"
    assert motif_refus_claude_drop(_p(bookmaker="OlyBet")) == "bookmaker hors périmètre"
    assert motif_refus_claude_drop(_p(ecart=0.11)) == "écart hors intervalle"
    assert motif_refus_claude_drop(_p(cote=4.5)) == "cote hors intervalle"
    assert motif_refus_claude_drop(_p(marche="CORRECT_SCORE")) == "marché à longues cotes"
    assert motif_refus_claude_drop(_p(debut="2026-11-18T09:00:00+00:00")) == "match déjà commencé"


def test_une_mise_par_cote_et_rien_avant_le_lancement():
    a, b = _p(), _p(detecte="2026-11-18T10:05:00+00:00")
    avant = _p(detecte="2026-11-17T10:00:00+00:00", match_id="pmu|2")
    refuse_puis_accepte = [_p(match_id="pmu|3", mouvement_pinnacle=0.0),
                           _p(match_id="pmu|3", detecte="2026-11-18T10:10:00+00:00")]
    paris = [a, b, avant, *refuse_puis_accepte]
    assert selection_claude_drop(paris) == {id(a), id(refuse_puis_accepte[1])}


def test_inscrite_dans_les_variantes():
    from cotes.strategies_prudentes import VARIANTES
    assert CLAUDE_DROP in VARIANTES
