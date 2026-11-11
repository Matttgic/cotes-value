"""Claude Signal : double avis et prix frais. Chaque filtre, le dédoublonnage, le lancement sans rejeu, le gel."""
from datetime import datetime, timezone

import pytest

from cotes.decisions import figer_nouveaux
from cotes.strategie_claude_signal import (CLAUDE_SIGNAL_DOUBLE as D, CLAUDE_SIGNAL_FRAIS as F, DEBUT, SELECTEURS,
                                           motif_refus_claude_signal, paris_claude_signal_double,
                                           paris_claude_signal_frais, selection_claude_signal)
from cotes.strategies_prudentes import VARIANTES, selections_prudentes
from tests.test_strategie_gemini_defi import base, horloge, iso
from tests.test_strategie_jules_v2 import pari

T0 = datetime(2026, 11, 12, 6, 0, tzinfo=timezone.utc)
TYPE = base(bookmaker="PMU", match_id="pmu|s", sport="football", cote=2.2, ecart=0.04, reference="Pinnacle",
            ecart_polymarket=0.03, age_prix_pinnacle_s=120, mouvement_pinnacle=0.004,
            **horloge(delai_min=240, detecte=T0))


def refus(c=D, **kw):
    return motif_refus_claude_signal(pari("a", **{**TYPE, **kw}), c)


def test_pari_type_retenu_par_les_deux_apres_lancement():
    p = pari("type", **TYPE)
    assert refus() is None and refus(F) is None
    assert paris_claude_signal_double([p]) == {id(p)} and paris_claude_signal_frais([p]) == {id(p)}
    assert DEBUT == "2026-11-12T00:00:00+00:00" and D["mise"] == F["mise"] == 10.0 and D["maximum_jour"] is None
    assert D["prospectif_seulement"] and F["prospectif_seulement"]


@pytest.mark.parametrize("champ,valeur,motif", [
    ("reference", "Smarkets", "référence hors périmètre"), ("reference", "Consensus", "référence hors périmètre"),
    ("bookmaker", "OlyBet", "bookmaker hors périmètre"),
    ("marche", "CORRECT_SCORE", "marché à longues cotes"), ("marche", "HALF_TIME_FULL_TIME", "marché à longues cotes"),
    ("cote", 1.29, "cote hors intervalle"), ("cote", 5.01, "cote hors intervalle"), ("cote", None, "cote hors intervalle"),
    ("ecart", 0.0199, "écart hors intervalle"), ("ecart", 0.1501, "écart hors intervalle"),
    ("debut", "pas une date", "date absente ou invalide"),
])
def test_filtres_communs(champ, valeur, motif):
    assert refus(**{champ: valeur}) == motif and refus(F, **{champ: valeur}) == (
        motif if (champ, valeur) != ("reference", "Polymarket") else "référence hors périmètre")


def test_bornes_incluses_equipes_inversees_et_match_commence():
    for kw in ({"cote": 1.30}, {"cote": 5.0}, {"ecart": 0.02}, {"ecart": 0.15}, {"bookmaker": "Winamax"},
               {"bookmaker": "NetBet"}):
        assert refus(**kw) is None and refus(F, **kw) is None, kw
    inverse = pari("i", **{**TYPE, "preuve_prise": {"equipes_inversees": True}})
    assert motif_refus_claude_signal(inverse) == "équipes inversées"
    commence = pari("c", **{**TYPE, **horloge(delai_min=-1, detecte=T0)})
    assert motif_refus_claude_signal(commence) == "match déjà commencé"


def test_double_avis_exige_la_seconde_reference_a_2_pour_cent():
    assert refus(ecart_polymarket=0.02) is None
    assert refus(ecart_polymarket=0.0199) == "second avis insuffisant"
    assert refus(ecart_polymarket=-0.01) == "second avis insuffisant"
    assert refus(ecart_polymarket=None) == "second avis absent"
    assert refus(ecart_polymarket=True) == "second avis absent"                       # un booléen n'est pas un écart
    # pari pris contre Polymarket : c'est l'écart contre Pinnacle qui sert de second avis
    assert refus(reference="Polymarket", ecart_pinnacle=0.025, ecart_polymarket=None) is None
    assert refus(reference="Polymarket", ecart_pinnacle=0.01) == "second avis insuffisant"
    assert refus(reference="Polymarket", ecart_pinnacle=None) == "second avis absent"
    # ni l'âge du prix ni le mouvement ne comptent pour cette règle
    assert refus(age_prix_pinnacle_s=None, mouvement_pinnacle=-0.05) is None


def test_prix_frais_exige_un_age_mesure_et_pas_de_mouvement_contraire():
    assert refus(F, age_prix_pinnacle_s=400) is None and refus(F, age_prix_pinnacle_s=0) is None
    assert refus(F, age_prix_pinnacle_s=401) == "prix trop ancien"
    assert refus(F, age_prix_pinnacle_s=None) == "âge du prix non mesuré"
    assert refus(F, age_prix_pinnacle_s=-5) == "prix trop ancien"
    assert refus(F, mouvement_pinnacle=-0.005) is None and refus(F, mouvement_pinnacle=None) is None
    assert refus(F, mouvement_pinnacle=-0.0051) == "Pinnacle s'éloigne de la sélection"
    assert refus(F, mouvement_pinnacle=0.08) is None
    assert refus(F, reference="Polymarket", ecart_pinnacle=0.05) == "référence hors périmètre"
    assert refus(F, ecart_polymarket=None) is None                                    # pas de second avis exigé


def test_une_mise_par_cote_francaise_premiere_detection_qui_passe():
    refusee = pari("r", **{**TYPE, "ecart_polymarket": 0.0, "detecte": iso(datetime(2026, 11, 12, 5, 0, tzinfo=timezone.utc))})
    premiere = pari("p", **TYPE)
    # la même cote française repérée ensuite contre Polymarket : une seule mise
    seconde = pari("s", **{**TYPE, "reference": "Polymarket", "ecart_pinnacle": 0.04,
                           "detecte": iso(datetime(2026, 11, 12, 6, 5, tzinfo=timezone.utc))})
    assert paris_claude_signal_double([seconde, refusee, premiere]) == {id(premiere)}


def test_pas_de_rejeu_avant_le_lancement():
    avant = pari("av", **{**TYPE, **horloge(delai_min=240, detecte=datetime(2026, 11, 11, 23, 59, tzinfo=timezone.utc))})
    assert paris_claude_signal_double([avant]) == set() and paris_claude_signal_frais([avant]) == set()
    p = pari("ap", **TYPE)
    assert paris_claude_signal_double([p], depuis="2026-10-01T00:00:00Z") == set()
    # le rejeu d'étude (documentation) passe par un départ explicite, jamais par le sélecteur officiel
    assert selection_claude_signal([avant], D, depart="2026-10-18T00:00:00+00:00") == {id(avant)}


def test_gel_au_lancement_et_inscription_dans_les_variantes():
    p = pari("g", **{**TYPE, "decide_le": iso(T0)})
    q = pari("h", **{**TYPE, "match_id": "pmu|h", "decide_le": iso(T0)})
    q["selections_figees"] = {}          # déjà décidée sans cette stratégie : jamais ajoutée après coup
    figer_nouveaux([p, q], [p])
    assert p["selections_figees"]["claude_signal_double"] == {"version": "1", "decide_le": iso(T0)}
    assert p["selections_figees"]["claude_signal_frais"] == {"version": "1", "decide_le": iso(T0)}
    assert paris_claude_signal_double([p, q]) == {id(p)}
    prudentes = selections_prudentes([p, q])
    assert prudentes["claude_signal_double"] == {id(p)} and prudentes["claude_signal_frais"] == {id(p)}
    assert D in VARIANTES and F in VARIANTES and list(SELECTEURS) == ["claude_signal_double", "claude_signal_frais"]
    assert len({v["cle"] for v in VARIANTES}) == len(VARIANTES) and len({v["nom"] for v in VARIANTES}) == len(VARIANTES)
    for c in (D, F):
        assert c["regles"] and "OlyBet" not in c["bookmakers"]
