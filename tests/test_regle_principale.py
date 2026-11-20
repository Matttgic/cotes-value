"""Règle principale figée le 14/11 (cotes/regle_principale.py) et gel du registre des stratégies."""
import json
from datetime import datetime, timedelta, timezone

from cotes import regle_principale as R
from cotes.protocole import REGISTRE

T = datetime(2026, 11, 18, 10, tzinfo=timezone.utc)
BASE = {"reference": "Pinnacle", "bookmaker": "PMU", "sport": "football", "marche": "RESULTAT_1N2", "periode": "MATCH",
        "issue": "1", "match_id": "pmu|1", "cote": 2.2, "ecart": 0.04, "mise": 10.0,
        "detecte": T.isoformat(), "debut": (T + timedelta(hours=8)).isoformat()}


def test_motifs():
    assert R.motif_refus(BASE) is None
    assert R.motif_refus({**BASE, "cote": 5.01}) == "cote"
    assert R.motif_refus({**BASE, "ecart": 0.0299}) == "écart"
    assert R.motif_refus({**BASE, "bookmaker": "Winamax"}) == "bookmaker"
    assert R.motif_refus({**BASE, "sport": "volley"}) is None
    assert R.motif_refus({**BASE, "detecte": "2026-11-14T22:59:59+00:00"}) == "avant le gel"
    assert R.motif_refus({**BASE, "debut": (T + timedelta(hours=24, seconds=1)).isoformat()}) == "délai"
    assert R.motif_refus({**BASE, "detecte": "2026-11-18T10:00:00"}) == "date"
    assert R.motif_refus({**BASE, "cote": None}) == "cote"


def test_une_mise_par_selection_la_premiere_qui_passe():
    avant = {**BASE, "ecart": 0.02, "detecte": (T - timedelta(minutes=5)).isoformat()}
    ok = {**BASE, "reference": "Betfair"}
    tard = {**BASE, "detecte": (T + timedelta(minutes=5)).isoformat()}
    assert R.retenus([avant, ok, tard]) == [ok]


def test_bilan_et_verdict():
    paris = []
    for i in range(40):
        paris.append({**BASE, "match_id": f"m{i}", "statut": "gagne" if i % 2 else "perdu",
                      "gain": 12.0 if i % 2 else -10.0})
    clvs = {id(p): 0.03 + 0.001 * (i % 5) for i, p in enumerate(paris)}
    b = R.construire(paris, lambda p: p["match_id"], clvs)
    assert b["paris"] == 40 and b["clv_n"] == 40 and b["prouve"] and b["clv_p"] < 0.05
    b = R.construire(paris, lambda p: p["match_id"], {})
    assert not b["prouve"] and b["clv_p"] is None


def test_plus_aucune_strategie_ajoutee():
    """Audit du 20/11 : 97 stratégies testées en parallèle, aucune ne survit à la correction. Le registre est gelé."""
    from cotes.strategies.registre import toutes
    assert len(toutes()) <= R.STRATEGIES_MAX, "registre gelé : juger la règle principale, pas une nouvelle"
    assert len(json.loads(REGISTRE.read_text(encoding="utf-8"))["inscrites"]) <= R.INSCRITES_MAX
