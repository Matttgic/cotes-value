"""Claude Opus · Valeur solide : chaque filtre, le dédoublonnage, le lancement sans rejeu, le gel des décisions."""
from datetime import datetime, timezone

import pytest

from cotes.decisions import figer_nouveaux
from cotes.strategie_claude_opus import (CLAUDE_OPUS_SOLIDE as R, DEBUT, SELECTEURS, motif_refus_claude_opus,
                                         paris_claude_opus_solide)
from cotes.strategies_prudentes import VARIANTES, selections_prudentes
from tests.test_strategie_gemini_defi import base, horloge, iso
from tests.test_strategie_jules_v2 import pari

T0 = datetime(2026, 11, 3, 6, 0, tzinfo=timezone.utc)
TYPE = base(bookmaker="Betclic", match_id="betclic|o", sport="basket", cote=2.2, ecart=0.07,
            **horloge(delai_min=240, detecte=T0))


def refus(**kw):
    return motif_refus_claude_opus(pari("a", **{**TYPE, **kw}))


def test_pari_type_retenu_apres_lancement_mise_10_sans_plafond():
    p = pari("type", **TYPE)
    assert refus() is None and paris_claude_opus_solide([p]) == {id(p)}
    assert R["mise"] == 10.0 and R["maximum_jour"] is None and DEBUT == "2026-11-03T00:00:00+00:00"


@pytest.mark.parametrize("champ,valeur,motif", [
    ("reference", "Smarkets", "référence hors périmètre"), ("reference", "Kalshi", "référence hors périmètre"),
    ("bookmaker", "Winamax", "bookmaker hors périmètre"), ("bookmaker", "OlyBet", "bookmaker hors périmètre"),
    ("marche", "CORRECT_SCORE", "marché à longues cotes"), ("marche", "HALF_TIME_FULL_TIME", "marché à longues cotes"),
    ("cote", 1.59, "cote hors intervalle"), ("cote", 3.51, "cote hors intervalle"),
    ("ecart", 0.0399, "écart hors intervalle"), ("ecart", 0.1501, "écart hors intervalle")])
def test_chaque_filtre(champ, valeur, motif):
    assert refus(**{champ: valeur}) == motif


def test_bornes_incluses_et_horloge():
    assert refus(cote=1.60) is None and refus(cote=3.50) is None
    assert refus(ecart=0.04) is None and refus(ecart=0.15) is None
    assert refus(**horloge(delai_min=720, detecte=T0)) is None
    assert refus(**horloge(delai_min=721, detecte=T0)) == "détection trop tôt"
    assert refus(**horloge(delai_min=0, detecte=T0)) == "match déjà commencé"
    assert refus(**horloge(delai_min=240, age_s=181, detecte=T0)) == "référence trop ancienne"


def test_une_mise_par_cote_francaise_premiere_detection_qui_passe():
    trop_large = pari("x", **{**TYPE, "ecart": 0.20, **horloge(delai_min=300, detecte=T0)})
    premiere = pari("p", **{**TYPE, **horloge(delai_min=200, detecte=T0.replace(hour=7))})
    seconde = pari("s", **{**TYPE, "reference": "Polymarket", **horloge(delai_min=100, detecte=T0.replace(hour=8))})
    assert paris_claude_opus_solide([trop_large, premiere, seconde]) == {id(premiere)}


def test_lancement_sans_rejeu_ni_lecture_du_resultat():
    avant = pari("avant", **{**TYPE, **horloge(delai_min=240, detecte=datetime(2026, 11, 2, 23, 59, 59, tzinfo=timezone.utc))})
    assert paris_claude_opus_solide([avant]) == set()
    p = pari("type", **TYPE)
    assert paris_claude_opus_solide([p], depuis="2026-10-01T00:00:00Z") == set()
    for issue in (dict(statut="gagne", gain=12.0, clv=0.3), dict(statut="perdu", gain=-10.0, clv=-0.4)):
        q = {**p, **issue}
        assert paris_claude_opus_solide([q]) == {id(q)}


def test_gel_au_lancement_et_inscription_dans_les_variantes():
    p = pari("g", **{**TYPE, "decide_le": iso(T0)})
    q = pari("h", **{**TYPE, "match_id": "betclic|h", "decide_le": iso(T0)})
    q["selections_figees"] = {}          # déjà décidée sans cette stratégie : jamais ajoutée après coup
    figer_nouveaux([p, q], [p])
    assert p["selections_figees"]["claude_opus_solide"] == {"version": "1", "decide_le": iso(T0)}
    assert paris_claude_opus_solide([p, q]) == {id(p)}
    assert selections_prudentes([p, q])["claude_opus_solide"] == {id(p)}
    assert R in VARIANTES and list(SELECTEURS) == ["claude_opus_solide", "claude_opus_favoris", "claude_opus_hors_foot",
                                                   "claude_opus_handicaps"]
    assert len({v["cle"] for v in VARIANTES}) == len(VARIANTES) and len({v["nom"] for v in VARIANTES}) == len(VARIANTES)


def test_declinaisons_favoris_hors_football_handicaps():
    from cotes.strategie_claude_opus import CLAUDE_OPUS, SELECTEURS as S
    regles = {c["cle"]: c for c in CLAUDE_OPUS}
    def refus_de(cle, **kw):
        return motif_refus_claude_opus(pari("a", **{**TYPE, **kw}), regles[cle])
    # Favoris réguliers : cote 1,60–2,20, écart 4–12 %
    assert refus_de("claude_opus_favoris", cote=2.2) is None and refus_de("claude_opus_favoris", cote=2.21) == "cote hors intervalle"
    assert refus_de("claude_opus_favoris", ecart=0.12) is None and refus_de("claude_opus_favoris", ecart=0.1201) == "écart hors intervalle"
    # Hors football
    assert refus_de("claude_opus_hors_foot") is None
    assert refus_de("claude_opus_hors_foot", sport="football") == "sport hors périmètre"
    assert refus_de("claude_opus_solide", sport="football") is None
    # Handicaps : lignes seulement, cote 1,60–2,60
    assert refus_de("claude_opus_handicaps") == "groupe de marché hors périmètre"           # VAINQUEUR
    assert refus_de("claude_opus_handicaps", marche="HANDICAP", ligne=-1.5) is None
    assert refus_de("claude_opus_handicaps", marche="HANDICAP", ligne=-1.5, cote=2.61) == "cote hors intervalle"
    # mêmes règles communes, chacune sa propre mise par cote française et son propre gel
    for c in CLAUDE_OPUS:
        assert c["debut"] == DEBUT and c["mise"] == 10.0 and c["references"] == R["references"]
        assert c["bookmakers"] == R["bookmakers"] and c["age_max_s"] == 180 and c["delai_max_minutes"] == 720
    p = pari("h", **{**TYPE, "marche": "HANDICAP", "ligne": -1.5})
    assert S["claude_opus_handicaps"]([p]) == {id(p)} and S["claude_opus_handicaps"]([p], depuis="2026-10-01T00:00:00Z") == set()
