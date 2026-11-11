"""Claude · Méthode humaine : chaque filtre, un par match, plafond par jour, lancement sans rejeu."""
from datetime import datetime, timedelta, timezone

from cotes.strategie_claude_humain import CLAUDE_HUMAIN as C
from cotes.strategie_claude_humain import (
    DEBUT,
    motif_refus_claude_humain,
    paris_claude_humain,
    selection_claude_humain,
)
from cotes.strategies_prudentes import VARIANTES
from tests.test_strategie_gemini_defi import base, horloge
from tests.test_strategie_jules_v2 import pari

T0 = datetime(2026, 11, 12, 6, 0, tzinfo=timezone.utc)
TYPE = base(bookmaker="PMU", match_id="pmu|h", sport="football", cote=2.2, ecart=0.06, reference="Pinnacle",
            **horloge(delai_min=240, detecte=T0))


def refus(**kw):
    return motif_refus_claude_humain(pari("a", **{**TYPE, **kw}))


def test_type_retenu_et_regles_annoncees():
    p = pari("type", **TYPE)
    assert refus() is None and paris_claude_humain([p]) == {id(p)}
    assert DEBUT == "2026-11-12T00:00:00+00:00" and C["prospectif_seulement"] and C["auteur"] == "Claude"
    assert "s'il était humain" in C["regles"] and C in VARIANTES


def test_filtres():
    assert refus(ecart=0.049) == "écart hors intervalle"
    assert refus(ecart=0.26) == "écart hors intervalle"
    assert refus(cote=1.49) == "cote hors intervalle" and refus(cote=3.01) == "cote hors intervalle"
    assert refus(bookmaker="Winamax") == "bookmaker hors périmètre"
    assert refus(bookmaker="OlyBet") == "bookmaker hors périmètre"
    assert refus(reference="Kalshi") == "référence hors périmètre"
    assert refus(periode="MT1") == "mi-temps"
    assert refus(reference="Polymarket") is None and refus(bookmaker="Unibet") is None


def test_un_par_match_et_vingt_par_jour():
    a = pari("a", **TYPE)
    b = pari("b", **{**TYPE, "issue": "EXT", "detecte": (T0 + timedelta(minutes=5)).isoformat()})
    assert selection_claude_humain([a, b]) == {id(a)}
    lot = [pari(f"m{i}", **{**TYPE, "match_id": f"pmu|{i}",
                             "detecte": (T0 + timedelta(minutes=i)).isoformat()}) for i in range(25)]
    assert len(selection_claude_humain(lot)) == 20


def test_avant_lancement_ignore():
    p = pari("tot", **{**TYPE, "detecte": "2026-11-11T20:00:00+00:00"})
    assert paris_claude_humain([p]) == set() and paris_claude_humain([p], depuis="x") == set()
