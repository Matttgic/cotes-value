from cotes.strategie_claude_pmu import CLAUDE_PMU
from cotes.strategie_claude_signal import motif_refus_claude_signal, selection_claude_signal


def _p(**k):
    base = {"reference": "Pinnacle", "bookmaker": "PMU", "marche": "TOTAL", "cote": 2.2, "ecart": 0.04,
            "detecte": "2026-11-13T10:00:00+00:00", "debut": "2026-11-13T18:00:00+00:00", "match_id": "pmu|1",
            "periode": "MATCH", "ligne": 2.5, "issue": "PLUS"}
    return {**base, **k}


def test_regle():
    assert motif_refus_claude_signal(_p(), CLAUDE_PMU) is None
    assert motif_refus_claude_signal(_p(bookmaker="Betclic"), CLAUDE_PMU) == "bookmaker hors périmètre"
    assert motif_refus_claude_signal(_p(ecart=0.08), CLAUDE_PMU) == "écart hors intervalle"
    assert motif_refus_claude_signal(_p(cote=3.4), CLAUDE_PMU) == "cote hors intervalle"
    assert motif_refus_claude_signal(_p(reference="Consensus"), CLAUDE_PMU) == "référence hors périmètre"


def test_une_mise_par_cote_et_rien_avant_le_lancement():
    a, b = _p(), _p(reference="Polymarket", detecte="2026-11-13T10:05:00+00:00")
    avant = _p(detecte="2026-11-12T10:00:00+00:00", match_id="pmu|2")
    assert selection_claude_signal([a, b, avant], CLAUDE_PMU) == {id(a)}
