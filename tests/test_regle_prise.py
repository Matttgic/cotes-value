"""Règle de prise du 19/11/2026 (docs/analyse-paris-19-11.md) : appliquée à la prise et à tous les bilans du site."""
from datetime import datetime, timezone

from cotes.simulation import motif_hors_regle, placer

BASE = {"reference": "Pinnacle", "bookmaker": "PMU", "sport": "football", "marche": "RESULTAT_1N2", "cote": 2.2,
        "ecart": 0.04, "detecte": "2026-11-20T10:00:00+00:00", "debut": "2026-11-20T18:00:00+00:00"}


def test_motifs():
    assert motif_hors_regle(BASE) is None
    assert motif_hors_regle({**BASE, "cote": 5.01}) == "cote > 5"
    assert motif_hors_regle({**BASE, "cote": 5.0}) is None
    assert motif_hors_regle({**BASE, "ecart": 0.0299}) == "écart < 3 %"
    assert motif_hors_regle({**BASE, "ecart": 0.03}) is None
    assert motif_hors_regle({**BASE, "bookmaker": "Winamax"}) == "Winamax"
    assert motif_hors_regle({**BASE, "bookmaker": "OlyBet"}) == "OlyBet"
    assert motif_hors_regle({**BASE, "sport": "volley"}) == "volley"
    assert motif_hors_regle({**BASE, "sport": "basket", "marche": "TOTAL"}) == "basket · total"
    assert motif_hors_regle({**BASE, "sport": "basket", "marche": "TOTAL_DOM"}) is None
    assert motif_hors_regle({**BASE, "debut": "2026-11-21T10:00:00+00:00"}) is None          # 24 h pile
    assert motif_hors_regle({**BASE, "debut": "2026-11-21T10:00:01+00:00"}) == "plus de 24 h avant le match"
    assert motif_hors_regle({"cote": None, "ecart": None}) is None                           # rien de mesuré : gardé


def test_placer_ne_prend_plus_les_paris_hors_regle():
    maintenant = datetime(2026, 11, 20, 10, tzinfo=timezone.utc)
    o = {**BASE, "detecte": maintenant.isoformat(), "lu_reference": maintenant.isoformat(), "match_id": "pmu|1",
         "domicile": "A", "exterieur": "B", "periode": "MATCH", "ligne": None, "issue": "1", "pari": "A",
         "cote_juste": 2.2 / 1.04}
    assert placer([{**o, "bookmaker": "Winamax"}], [], maintenant) == []
    assert placer([{**o, "sport": "volley"}], [], maintenant) == []
    assert placer([{**o, "debut": "2026-11-21T12:00:00+00:00"}], [], maintenant) == []
    assert [p["bookmaker"] for p in placer([o], [], maintenant)] == ["PMU"]
