"""Défi 1 et Défi 4 : écart, cote, délai, et une mise par cote française."""
import pytest

from cotes.strategie_defi import (DEBUT, DEFI_1, DEFI_4, DEFIS, motif_refus_defi,
                                  paris_defi_1, paris_defi_4)
from cotes.strategie_grok import GROK_6, GROK_9, GROK_10, GROKS, GROKS_V2, GROKS_V3, paris_grok_9
from cotes.strategies_prudentes import VARIANTES, selections_prudentes
from tests.test_strategie_jules_v2 import pari

T = dict(detecte="2026-10-27T02:00:00Z", debut="2026-10-27T10:00:00Z", lu_reference="2026-10-27T01:59:00Z")
PIN = dict(reference="Pinnacle", bookmaker="Winamax", sport="football", marche="VAINQUEUR", issue="DOM",
           cote=2.0, cote_juste=2.0 / 1.06, ecart=0.06, **T)
PIN4 = {**PIN, "cote_juste": 2.0 / 1.08, "ecart": 0.08}


def avec(base, cote, edge, **kw):
    return {**base, "cote": cote, "cote_juste": cote / (1 + edge), "ecart": edge, **kw}


@pytest.mark.parametrize("regle,base,fonction", [
    (DEFI_1, PIN, paris_defi_1), (DEFI_4, PIN4, paris_defi_4)])
def test_pari_type_retenu_apres_lancement(regle, base, fonction):
    p = pari("a", **base)
    assert motif_refus_defi(p, regle) is None
    assert fonction([p]) == {id(p)}
    assert regle["mise"] == 10.0 and regle["maximum_jour"] is None
    assert regle["debut"] == DEBUT == "2026-10-27T01:00:00+00:00"


def test_seuils_d_ecart_sans_plafond():
    assert motif_refus_defi(pari("a", **avec(PIN, 2.0, 0.06)), DEFI_1) is None
    assert motif_refus_defi(pari("a", **avec(PIN, 2.0, 0.059)), DEFI_1) == "écart insuffisant"
    assert motif_refus_defi(pari("a", **avec(PIN4, 2.0, 0.08)), DEFI_4) is None
    assert motif_refus_defi(pari("a", **avec(PIN4, 2.0, 0.079)), DEFI_4) == "écart insuffisant"
    # Le crible n'a pas de plafond d'écart (emax infini).
    assert motif_refus_defi(pari("a", **avec(PIN, 8.0, 0.50)), DEFI_1) is None
    assert motif_refus_defi(pari("a", **avec(PIN4, 8.0, 0.50)), DEFI_4) is None
    # Un écart qui ne colle pas à la cote juste n'est pas joué.
    faux = {**PIN, "ecart": 0.20}
    assert motif_refus_defi(pari("a", **faux), DEFI_1) == "écart incohérent avec la cote juste"


def test_bornes_de_cote():
    assert motif_refus_defi(pari("a", **avec(PIN, 10.0, 0.06)), DEFI_1) is None
    assert motif_refus_defi(pari("a", **avec(PIN4, 10.0, 0.08)), DEFI_4) is None
    assert motif_refus_defi(pari("a", **avec(PIN, 10.01, 0.06)), DEFI_1) == "cote hors intervalle"
    assert motif_refus_defi(pari("a", **avec(PIN, 0.99, 0.06)), DEFI_1) == "cote hors intervalle"
    # Cote 1 et écart positif : la cote juste tomberait sous 1, donc incohérente.
    assert motif_refus_defi(pari("a", **avec(PIN, 1.0, 0.06)), DEFI_1) == "écart incohérent avec la cote juste"
    plancher = avec(PIN, 1.061, 0.06)
    assert plancher["cote_juste"] > 1
    assert motif_refus_defi(pari("a", **plancher), DEFI_1) is None


def test_references_defi_1_sharp_seulement():
    for reference in ("Pinnacle", "Betfair", "Polymarket"):
        assert motif_refus_defi(pari("a", **{**PIN, "reference": reference}), DEFI_1) is None
    for reference in ("Winamax", "Betclic", "Unibet", "PMU", "OlyBet", "Smarkets", "Kalshi", "Consensus"):
        assert motif_refus_defi(pari("a", **{**PIN, "reference": reference}), DEFI_1)
    assert motif_refus_defi(pari("a", **{**PIN, "bookmaker": "Smarkets"}), DEFI_1)
    assert motif_refus_defi(pari("a", **{**PIN, "bookmaker": "Kalshi"}), DEFI_1)
    assert motif_refus_defi(pari("a", **{**PIN, "reference": "Betclic", "bookmaker": "Unibet"}), DEFI_1)


def test_defi_4_pinnacle_seul():
    assert motif_refus_defi(pari("a", **PIN4), DEFI_4) is None
    for reference in ("Betfair", "Polymarket", "Consensus", "Smarkets", "Winamax"):
        assert motif_refus_defi(pari("a", **{**PIN4, "reference": reference}), DEFI_4)
    # L'écart de Défi 1 ne suffit pas à Défi 4.
    assert motif_refus_defi(pari("a", **PIN), DEFI_4) == "écart insuffisant"


def test_delai_avant_le_coup_d_envoi():
    def horloge(detecte, debut, lu=None):
        return {**PIN, "detecte": detecte, "debut": debut, "lu_reference": lu or detecte}

    assert motif_refus_defi(pari("a", **horloge("2026-10-27T02:00:00Z", "2026-10-27T13:59:59Z")), DEFI_1) is None
    assert motif_refus_defi(pari("a", **horloge("2026-10-27T02:00:00Z", "2026-10-27T14:00:00Z")), DEFI_1) == "détection trop tôt"
    loin = horloge("2026-10-27T02:00:00Z", "2026-10-28T08:00:00Z")
    assert motif_refus_defi(pari("a", **loin), DEFI_1) == "détection trop tôt"
    assert motif_refus_defi(pari("a", **{**loin, "ecart": 0.08, "cote_juste": 2.0 / 1.08}), DEFI_4) is None
    pile = horloge("2026-10-27T10:00:00Z", "2026-10-27T10:00:00Z", "2026-10-27T09:50:00Z")
    assert motif_refus_defi(pari("a", **pile), DEFI_1) is None
    assert motif_refus_defi(pari("a", **{**pile, "ecart": 0.08, "cote_juste": 2.0 / 1.08}), DEFI_4) is None
    apres = horloge("2026-10-27T10:00:01Z", "2026-10-27T10:00:00Z")
    assert motif_refus_defi(pari("a", **apres), DEFI_1) == "match déjà commencé"
    assert motif_refus_defi(pari("a", **{**apres, "ecart": 0.08, "cote_juste": 2.0 / 1.08}), DEFI_4) == "match déjà commencé"
    vieille = horloge("2026-10-27T02:00:00Z", "2026-10-27T10:00:00Z", "2026-10-27T01:44:00Z")
    assert motif_refus_defi(pari("a", **vieille), DEFI_1) == "référence trop ancienne"
    juste_15 = horloge("2026-10-27T02:00:00Z", "2026-10-27T10:00:00Z", "2026-10-27T01:45:00Z")
    assert motif_refus_defi(pari("a", **juste_15), DEFI_1) is None


def test_preuve_exigee_mais_pas_de_filtre_de_marche():
    faible = pari("a", **PIN)
    faible["preuve_prise"] = {**faible["preuve_prise"], "ressemblance_noms": 0.84}
    assert motif_refus_defi(faible, DEFI_1) == "preuve de correspondance insuffisante"
    assert motif_refus_defi(pari("a", **{**PIN, "suspect": True}), DEFI_1) == "opportunité signalée suspecte"
    # Le crible historique ne retire ni les quarts de ligne, ni les marchés exotiques.
    quart = avec(PIN, 2.0, 0.06, marche="TOTAL", issue="PLUS", ligne=2.25)
    assert motif_refus_defi(pari("a", **quart), DEFI_1) is None
    exotique = {**PIN4, "sport": "tennis", "marche": "DRAW_NO_BET", "issue": "DOM"}
    assert motif_refus_defi(pari("a", **exotique), DEFI_4) is None


def test_une_mise_par_cote_francaise_deux_books_comptent_deux():
    meme = dict(domicile="Paris", exterieur="Lyon", match_reference="Paris - Lyon", match_id="winamax|m")
    premier = pari("m", **{**PIN, **meme})
    autre_ref = pari("m2", **{**PIN, **meme, "reference": "Betfair",
                              "detecte": "2026-10-27T02:05:00Z", "lu_reference": "2026-10-27T02:05:00Z"})
    autre_book = pari("m3", **{**PIN, **meme, "bookmaker": "Betclic", "match_id": "betclic|m",
                               "detecte": "2026-10-27T02:06:00Z", "lu_reference": "2026-10-27T02:06:00Z"})
    autre_issue = pari("m4", **{**PIN, **meme, "issue": "EXT",
                                "detecte": "2026-10-27T02:07:00Z", "lu_reference": "2026-10-27T02:07:00Z"})
    trop_tot = pari("m0", **{**PIN, **meme, "ecart": 0.01, "cote_juste": 2.0 / 1.01,
                             "detecte": "2026-10-27T01:30:00Z", "lu_reference": "2026-10-27T01:30:00Z"})
    assert paris_defi_1([autre_ref, trop_tot, autre_book, autre_issue, premier]) == {
        id(premier), id(autre_book), id(autre_issue)}
    # Même instant : l'identifiant le plus petit gagne, quel que soit l'ordre d'entrée.
    jumeau = pari("a-plus-tot", **{**PIN, **meme, "reference": "Polymarket"})
    assert paris_defi_1([premier, jumeau]) == paris_defi_1([jumeau, premier]) == {id(jumeau)}
    # Grok 9 fusionne les deux books du même match. Défi garde les deux cotes françaises.
    pin9 = {**PIN4, "cote": 2.0, "cote_juste": 2.0 / 1.08, "ecart": 0.08}
    a = pari("g", **{**pin9, **meme})
    b = pari("h", **{**pin9, **meme, "bookmaker": "Betclic", "match_id": "betclic|m"})
    assert paris_defi_4([a, b]) == {id(a), id(b)}
    assert paris_grok_9([a, b]) == {id(a)} or paris_grok_9([a, b]) == {id(b)}
    assert len(paris_grok_9([a, b])) == 1


def test_pas_de_plafond_journalier_ni_de_rejeu():
    autres = [pari(f"x{i}", **{**PIN, "domicile": f"Eq{i}", "exterieur": f"Ad{i}", "match_id": f"win|{i}",
                               "match_reference": f"Eq{i} - Ad{i}",
                               "detecte": f"2026-10-27T02:{i:02d}:00Z",
                               "lu_reference": f"2026-10-27T02:{i:02d}:00Z"})
              for i in range(12)]
    assert len(paris_defi_1(autres)) == 12
    avant = pari("avant", **{**PIN, "detecte": "2026-10-27T00:30:00Z", "lu_reference": "2026-10-27T00:29:00Z",
                             "debut": "2026-10-27T08:00:00Z"})
    assert paris_defi_1([avant]) == set()
    # Une détection d'avant le lancement ne consomme pas la cote.
    apres = pari("apres", **{**PIN, "match_id": avant["match_id"]})
    assert paris_defi_1([avant, apres]) == {id(apres)}
    assert paris_defi_1([pari("b", **PIN)], depuis="2026-10-01T00:00:00Z") == set()
    assert paris_defi_4([pari("b", **PIN4)], depuis=DEBUT) == set()


def test_prise_figee_ne_recoit_pas_la_cle_et_les_grok_restent_intacts():
    p = pari("a", **PIN4)
    p["selections_figees"] = {"grok_9": {"version": "2", "decide_le": p["detecte"]}}
    assert paris_defi_1([p]) == {id(p)} and paris_defi_4([p]) == {id(p)}
    officiel = selections_prudentes([p])
    # Déjà figée sur Grok 9 : la clé reste, Défi n'est pas ajouté.
    assert officiel["grok_9"] == {id(p)} and officiel["grok_10"] == set()
    assert officiel["defi_1"] == set() and officiel["defi_4"] == set()
    assert set(p["selections_figees"]) == {"grok_9"}
    assert selections_prudentes([p], depuis="2026-10-27T00:00:00Z")["defi_1"] == set()
    assert [g["cle"] for g in GROKS] == ["grok_1", "grok_2", "grok_3", "grok_4", "grok_5"]
    assert [g["cle"] for g in GROKS_V2] == ["grok_6", "grok_7", "grok_8"]
    assert [g["cle"] for g in GROKS_V3] == ["grok_9", "grok_10"]
    assert GROK_6["maximum_jour"] == 10 and GROK_9["portee"] == "selection"
    assert GROK_10["avance_min_minutes"] == 0 and GROK_9["edge_max"] == 3.5
    assert [d["cle"] for d in DEFIS] == ["defi_1", "defi_4"]
    assert all(d in VARIANTES for d in DEFIS)
    assert not any(d["cle"].startswith("grok") for d in DEFIS)
