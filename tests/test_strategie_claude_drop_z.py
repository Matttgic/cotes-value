from cotes.strategie_claude_drop_z import CLAUDE_DROP_Z, motif_refus_claude_drop_z, selection_claude_drop_z


def _p(**k):
    base = {"reference": "Pinnacle", "bookmaker": "PMU", "marche": "TOTAL", "cote": 2.2, "ecart": 0.04,
            "mouvement_pinnacle": 0.05, "mouvement_s": 900, "mouvement_z": 2.5,
            "detecte": "2026-11-18T10:00:00+00:00", "debut": "2026-11-18T18:00:00+00:00", "match_id": "pmu|1",
            "periode": "MATCH", "ligne": 2.5, "issue": "PLUS"}
    return {**base, **k}


def test_regle():
    assert motif_refus_claude_drop_z(_p()) is None
    assert motif_refus_claude_drop_z(_p(mouvement_z=2.0)) is None
    assert motif_refus_claude_drop_z(_p(mouvement_z=1.99)) == "chute ordinaire pour ce marché"
    assert motif_refus_claude_drop_z(_p(mouvement_z=None)) == "z-score non mesuré"
    assert motif_refus_claude_drop_z(_p(mouvement_pinnacle=0.02)) == "pas de chute Pinnacle"
    assert motif_refus_claude_drop_z(_p(bookmaker="OlyBet")) == "bookmaker hors périmètre"


def test_une_mise_par_cote_et_rien_avant_le_lancement():
    a, b = _p(), _p(detecte="2026-11-18T10:05:00+00:00")
    avant = _p(detecte="2026-11-18T06:00:00+00:00", match_id="pmu|2")
    refuse_puis_accepte = [_p(match_id="pmu|3", mouvement_z=1.0),
                           _p(match_id="pmu|3", detecte="2026-11-18T10:10:00+00:00")]
    assert selection_claude_drop_z([a, b, avant, *refuse_puis_accepte]) == {id(a), id(refuse_puis_accepte[1])}


def test_inscrite_dans_les_variantes():
    from cotes.strategies_prudentes import VARIANTES
    assert CLAUDE_DROP_Z in VARIANTES
