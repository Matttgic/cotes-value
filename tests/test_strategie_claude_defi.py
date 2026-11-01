"""Claude Défi 1, 2, 3 : chaque filtre, le dédoublonnage, le lancement sans rejeu, le gel.

Le dernier test rejoue les trois règles sur l'export de recherche (tests/fixtures/gemini_defi_rejeu.csv)
et retrouve les N annoncés (construction, validation).
"""
from collections import Counter
from datetime import datetime, timedelta, timezone

import pytest

from cotes.decisions import figer_nouveaux
from cotes.strategie_claude_defi import (
    CLAUDE_DEFIS, DEBUT, SELECTEURS, motif_refus_claude_defi, paris_claude_defi_1, selection_claude_defi)
from cotes.strategie_gemini_defi import GEMINI_DEFIS
from cotes.strategies_prudentes import VARIANTES, selections_prudentes
from tests.test_strategie_gemini_defi import _export, base, horloge, iso, preuve
from tests.test_strategie_jules_v2 import pari

T0 = datetime(2026, 11, 2, 2, 0, tzinfo=timezone.utc)
REGLES = {c["cle"]: c for c in CLAUDE_DEFIS}
# Un pari type par stratégie, au milieu de ses intervalles (horloge : délai 360 min, référence lue 60 s avant).
TYPES = {
    "claude_defi_1": base(sport="hockey", cote=2.5, ecart=0.10, **horloge(detecte=T0)),
    "claude_defi_2": base(sport="basket", marche="HANDICAP", ligne=-4.5, cote=1.9, ecart=0.08,
                          **horloge(detecte=T0)),
    "claude_defi_3": base(bookmaker="Betclic", match_id="betclic|m", cote=2.5, ecart=0.08,
                          **horloge(detecte=T0)),
}


def refus(cle, **kw):
    return motif_refus_claude_defi(pari("a", **{**TYPES[cle], **kw}), REGLES[cle])


@pytest.mark.parametrize("cle", list(REGLES))
def test_pari_type_retenu_apres_lancement_mise_10(cle):
    p = pari("type", **TYPES[cle])
    assert refus(cle) is None
    assert SELECTEURS[cle]([p]) == {id(p)}
    assert REGLES[cle]["mise"] == 10.0 and REGLES[cle]["debut"] == DEBUT == "2026-11-02T01:00:00+00:00"


@pytest.mark.parametrize("cle", list(REGLES))
def test_bornes_de_cote_et_d_ecart_incluses(cle):
    c = REGLES[cle]
    assert refus(cle, cote=c["cote_min"]) is None and refus(cle, cote=c["cote_max"]) is None
    assert refus(cle, cote=round(c["cote_min"] - 0.01, 2)) == "cote hors intervalle"
    assert refus(cle, cote=round(c["cote_max"] + 0.01, 2)) == "cote hors intervalle"
    assert refus(cle, ecart=c["ecart_min_pct"] / 100) is None and refus(cle, ecart=c["ecart_max_pct"] / 100) is None
    assert refus(cle, ecart=c["ecart_min_pct"] / 100 - 0.0001) == "écart hors intervalle"
    assert refus(cle, ecart=c["ecart_max_pct"] / 100 + 0.0001) == "écart hors intervalle"


@pytest.mark.parametrize("cle", list(REGLES))
def test_delai_et_age_de_la_reference(cle):
    c = REGLES[cle]
    assert refus(cle, **horloge(delai_min=720, detecte=T0)) is None
    assert refus(cle, **horloge(delai_min=720.5, detecte=T0)) == "détection trop tôt"
    assert refus(cle, **horloge(delai_min=0, detecte=T0)) == "match déjà commencé"
    assert refus(cle, **horloge(age_s=180, detecte=T0)) is None
    assert refus(cle, **horloge(age_s=181, detecte=T0)) == "référence trop ancienne"
    # Âge signé : une référence relue quelques secondes après la cote française passe.
    assert refus(cle, **horloge(age_s=-5, detecte=T0)) is None
    if cle == "claude_defi_3":
        assert refus(cle, **horloge(delai_min=120, detecte=T0)) == "détection trop tard"
        assert refus(cle, **horloge(delai_min=120.5, detecte=T0)) is None
    else:
        assert refus(cle, **horloge(delai_min=1, detecte=T0)) is None


@pytest.mark.parametrize("cle", list(REGLES))
def test_tronc_commun_references_et_equipes_inversees(cle):
    for ref in ("Pinnacle", "Betfair", "Polymarket"):
        assert refus(cle, reference=ref) is None
    for ref in ("Smarkets", "Matchbook", "Kalshi", "Consensus"):
        assert refus(cle, reference=ref) == "référence hors périmètre"
    assert refus(cle, preuve_prise=preuve(inversees=True)) == "équipes inversées"
    assert refus(cle, preuve_prise=preuve(inversees=None)) is None
    # Aucun score de correspondance minimal.
    assert refus(cle, preuve_prise=preuve(score=0.6)) is None


def test_perimetres_propres():
    assert refus("claude_defi_1", sport="tennis", marche="CORRECT_SCORE", issue="2-1") is None
    for marche in ("HANDICAP", "HANDICAP_3", "SETS_HANDICAP", "JEUX_HANDICAP"):
        assert refus("claude_defi_2", marche=marche) is None
    for marche in ("TOTAL", "TOTAL_DOM", "RESULTAT_1N2", "VAINQUEUR"):
        assert refus("claude_defi_2", marche=marche) == "groupe de marché hors périmètre"
    assert refus("claude_defi_3", bookmaker="PMU") is None
    for book in ("Winamax", "Unibet", "OlyBet", "NetBet"):
        assert refus("claude_defi_3", bookmaker=book) == "bookmaker hors périmètre"


def test_une_mise_par_cote_francaise_premiere_detection_qui_passe():
    meme = {**TYPES["claude_defi_1"], "match_id": "winamax|m"}             # même cote française
    refusee = pari("p0", **{**meme, "ecart": 0.03})                                  # refusée : ne consomme rien
    premier = pari("p1", **{**meme, **horloge(detecte=T0 + timedelta(minutes=1))})
    autre_ref = pari("p2", **{**meme, "reference": "Polymarket", **horloge(detecte=T0 + timedelta(minutes=2))})
    autre_book = pari("p3", **{**meme, "bookmaker": "Betclic", "match_id": "betclic|m",
                               **horloge(detecte=T0 + timedelta(minutes=3))})
    tous = [autre_book, autre_ref, premier, refusee]
    assert paris_claude_defi_1(tous) == {id(premier), id(autre_book)}


def test_lancement_sans_rejeu_ni_lecture_du_resultat():
    avant = pari("avant", **{**TYPES["claude_defi_1"], **horloge(
        detecte=datetime(2026, 11, 2, 0, 59, 59, tzinfo=timezone.utc))})
    pile = pari("pile", **{**TYPES["claude_defi_1"], "match_id": "w|pile",
                           **horloge(detecte=datetime(2026, 11, 2, 1, 0, tzinfo=timezone.utc))})
    assert paris_claude_defi_1([avant, pile]) == {id(pile)}
    for f in SELECTEURS.values():
        assert f([pile], depuis="2026-10-01T00:00:00Z") == set()
    assert selections_prudentes([pile], depuis="2026-10-01T00:00:00Z")["claude_defi_1"] == set()
    for cle in REGLES:
        p = pari("type", **TYPES[cle])
        for issue in (dict(statut="gagne", gain=10.0, clv=0.3, cote_juste_cloture=1.5),
                      dict(statut="perdu", gain=-10.0, clv=-0.4, cote_juste_cloture=99.0)):
            q = {**p, **issue}
            assert SELECTEURS[cle]([q]) == {id(q)}


def test_gel_au_lancement_et_famille_distincte():
    p = pari("g", **{**TYPES["claude_defi_1"], "decide_le": iso(T0)})
    q = pari("h", **{**TYPES["claude_defi_1"], "match_id": "w|h", "decide_le": iso(T0)})
    q["selections_figees"] = {}   # déjà décidée sans Claude Défi : jamais ajoutée après coup
    figer_nouveaux([p, q], [p])
    assert p["selections_figees"]["claude_defi_1"] == {"version": "1", "decide_le": iso(T0)}
    assert paris_claude_defi_1([p, q]) == {id(p)}
    assert selections_prudentes([p, q])["claude_defi_1"] == {id(p)}
    cles = [c["cle"] for c in CLAUDE_DEFIS]
    assert cles == ["claude_defi_1", "claude_defi_2", "claude_defi_3"] and list(SELECTEURS) == cles
    assert all(c in VARIANTES for c in CLAUDE_DEFIS)
    assert not {c["cle"] for c in GEMINI_DEFIS} & set(cles)
    assert len({v["cle"] for v in VARIANTES}) == len(VARIANTES)
    assert len({v["nom"] for v in VARIANTES}) == len(VARIANTES)
    assert all(SELECTEURS[c].__wrapped__ for c in cles)   # @figer_selecteur


# N annoncés dans la réponse du 1er novembre (construction, validation), après les deux règles obligatoires.
N_REJEU = {"claude_defi_1": (161, 63), "claude_defi_2": (90, 18), "claude_defi_3": (76, 32)}


def test_rejeu_sur_l_export_retrouve_les_n_annonces():
    paris = _export()
    assert len(paris) == 2845
    for c in CLAUDE_DEFIS:
        retenus = selection_claude_defi(paris, c, "2026-10-05T00:00:00Z")
        blocs = Counter(p["bloc"] for p in paris if id(p) in retenus)
        assert (blocs["construction"], blocs["validation"]) == N_REJEU[c["cle"]], c["cle"]
        assert SELECTEURS[c["cle"]](paris) == set()          # le suivi ne commence qu'au lancement
