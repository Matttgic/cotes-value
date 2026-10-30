"""Gemini Défi 1, 3, 4, 5 (règles de Gemini Argon) : chaque filtre, le dédoublonnage, les plafonds, le gel.

Gemini Défi 2, abandonnée par Gemini, n'a ni clé ni sélecteur. Le dernier test rejoue les quatre sélecteurs sur l'export de recherche (colonnes utiles seulement,
tests/fixtures/gemini_defi_rejeu.csv) et retrouve les N du rejeu de référence.
"""
import csv
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from cotes.decisions import figer_nouveaux
from cotes.strategie_defi import DEFIS
from cotes.strategie_gemini_defi import (
    DEBUT, GEMINI_DEFI_5, GEMINI_DEFIS, SELECTEURS,
    motif_refus_gemini_defi, paris_gemini_defi_1, paris_gemini_defi_5, selection_gemini_defi)
from cotes.strategie_grok import GROKS, GROKS_V2, GROKS_V3
from cotes.strategies_prudentes import VARIANTES, selections_prudentes
from tests.test_strategie_jules_v2 import pari

T0 = datetime(2026, 10, 30, 2, 0, tzinfo=timezone.utc)


def iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


def horloge(delai_min=360.0, age_s=60.0, detecte=T0):
    return dict(detecte=iso(detecte), debut=iso(detecte + timedelta(minutes=delai_min)),
                lu_reference=iso(detecte - timedelta(seconds=age_s)))


def preuve(score=0.95, inversees=False, ref="ref"):
    return {"match_id_reference": ref, "ressemblance_noms": score, "equipes_inversees": inversees,
            "controle": {"statut": "conforme"}}


def base(**kw):
    """Une détection qui passe les règles visées (le reste de pari() : football, Winamax, Pinnacle)."""
    p = dict(marche="VAINQUEUR", issue="DOM", cote=2.0, ecart=0.08, preuve_prise=preuve(), **horloge())
    p.update(kw)
    return p


# Un pari type par stratégie, juste au milieu de ses intervalles.
TYPES = {
    "gemini_defi_1": base(sport="basket", cote=2.0, ecart=0.10),
    "gemini_defi_3": base(sport="tennis", marche="VAINQUEUR", cote=3.0, ecart=0.10),
    "gemini_defi_4": base(sport="rugby", marche="HANDICAP", ligne=-4.5, cote=2.0, ecart=0.08),
    "gemini_defi_5": base(sport="football", marche="CORRECT_SCORE", issue="2-1", cote=20.0, ecart=0.15),
}
REGLES = {c["cle"]: c for c in GEMINI_DEFIS}


def refus(cle, **kw):
    return motif_refus_gemini_defi(pari("a", **{**TYPES[cle], **kw}), REGLES[cle])


@pytest.mark.parametrize("cle", list(REGLES))
def test_pari_type_retenu_apres_lancement_mise_10(cle):
    c = REGLES[cle]
    assert refus(cle) is None
    p = pari("type", **TYPES[cle])
    assert SELECTEURS[cle]([p]) == {id(p)}
    assert c["mise"] == 10.0 and c["version"] == "1" and c["debut"] == DEBUT == "2026-10-30T01:00:00+00:00"
    assert c["auteur"] == "Gemini Argon" and c["nom"].startswith("Gemini Défi ")


@pytest.mark.parametrize("cle", list(REGLES))
def test_bornes_de_cote_et_d_ecart_incluses(cle):
    c = REGLES[cle]
    assert refus(cle, cote=c["cote_min"]) is None and refus(cle, cote=c["cote_max"]) is None
    assert refus(cle, cote=round(c["cote_min"] - 0.01, 2)) == "cote hors intervalle"
    assert refus(cle, cote=round(c["cote_max"] + 0.01, 2)) == "cote hors intervalle"
    assert refus(cle, cote=None) == "cote hors intervalle"
    assert refus(cle, ecart=c["ecart_min_pct"] / 100) is None
    assert refus(cle, ecart=c["ecart_max_pct"] / 100) is None
    assert refus(cle, ecart=c["ecart_min_pct"] / 100 - 0.0001) == "écart hors intervalle"
    assert refus(cle, ecart=c["ecart_max_pct"] / 100 + 0.0001) == "écart hors intervalle"


@pytest.mark.parametrize("cle", list(REGLES))
def test_delai_et_age_de_la_reference(cle):
    c = REGLES[cle]
    assert refus(cle, **horloge(delai_min=c["delai_max_minutes"])) is None
    assert refus(cle, **horloge(delai_min=c["delai_max_minutes"] + 1 / 60)) == "détection trop tôt"
    assert refus(cle, **horloge(delai_min=0)) == "match déjà commencé"
    assert refus(cle, **horloge(delai_min=-5)) == "match déjà commencé"
    if c["delai_min_minutes"] is None:
        assert refus(cle, **horloge(delai_min=1 / 60)) is None   # 0 < délai : une seconde suffit
    else:
        assert refus(cle, **horloge(delai_min=c["delai_min_minutes"])) is None
        assert refus(cle, **horloge(delai_min=c["delai_min_minutes"] - 1 / 60)) == "détection trop tard"
    assert refus(cle, **horloge(age_s=c["age_max_s"])) is None
    assert refus(cle, **horloge(age_s=c["age_max_s"] + 1)) == "référence trop ancienne"
    # Âge signé, comme age_reference_s : une référence relue juste après la cote française passe.
    assert refus(cle, **horloge(age_s=-30)) is None
    assert refus(cle, lu_reference=None) == "date absente ou invalide"


@pytest.mark.parametrize("cle", list(REGLES))
def test_tronc_commun_references_et_equipes_inversees(cle):
    c = REGLES[cle]
    for ref in ("Pinnacle", "Betfair", "Polymarket"):
        assert (refus(cle, reference=ref) is None) == (ref in c["references"])
    for ref in ("Smarkets", "Kalshi", "Consensus", "Matchbook", "Winamax", "Pinnacle brut", None):
        assert refus(cle, reference=ref) == "référence hors périmètre"
    assert refus(cle, preuve_prise=preuve(inversees=True)) == "équipes inversées"
    assert refus(cle, preuve_prise=preuve(inversees=None)) is None   # vide accepté, comme l'export
    assert refus(cle, preuve_prise={k: v for k, v in preuve().items() if k != "equipes_inversees"}) is None


@pytest.mark.parametrize("cle", list(REGLES))
def test_score_de_correspondance(cle):
    c = REGLES[cle]
    if c["score_min"] is None:   # Gemini Défi 1 : pas de seuil de correspondance
        assert refus(cle, preuve_prise=preuve(score=None)) is None
        assert refus(cle, preuve_prise=preuve(score=0.1)) is None
        return
    assert refus(cle, preuve_prise=preuve(score=c["score_min"])) is None
    assert refus(cle, preuve_prise=preuve(score=c["score_min"] - 0.001)) == "correspondance insuffisante"
    assert refus(cle, preuve_prise=preuve(score=None)) == "correspondance insuffisante"
    assert refus(cle, preuve_prise=None) == "correspondance insuffisante"


@pytest.mark.parametrize("cle", ["gemini_defi_1", "gemini_defi_3", "gemini_defi_4"])
def test_defi_1_3_4_references_pinnacle_betfair_polymarket_seulement(cle):
    assert REGLES[cle]["references"] == ("Pinnacle", "Betfair", "Polymarket")
    for ref in ("Pinnacle", "Betfair", "Polymarket"):
        assert refus(cle, reference=ref) is None
        p = pari("r-" + ref, **{**TYPES[cle], "reference": ref})
        assert SELECTEURS[cle]([p]) == {id(p)}
    # Matchbook est exclu, comme le reste.
    m = pari("m", **{**TYPES[cle], "reference": "Matchbook"})
    assert refus(cle, reference="Matchbook") == "référence hors périmètre" and SELECTEURS[cle]([m]) == set()


def test_gemini_defi_1_indoor_et_glace():
    for sport in ("basket", "hockey", "handball", "volley"):
        assert refus("gemini_defi_1", sport=sport) is None
    for sport in ("football", "tennis", "rugby", "baseball", None):
        assert refus("gemini_defi_1", sport=sport) == "sport hors périmètre"
    # Aucun filtre de marché.
    assert refus("gemini_defi_1", marche="CORRECT_SCORE", issue="80-78") is None


def test_gemini_defi_3_marches_principaux_seulement():
    for marche in ("RESULTAT_1N2", "VAINQUEUR", "DRAW_NO_BET", "DOUBLE_CHANCE"):
        assert refus("gemini_defi_3", marche=marche) is None
    for marche in ("HANDICAP", "TOTAL", "HANDICAP_3", "CORRECT_SCORE"):
        assert refus("gemini_defi_3", marche=marche) == "groupe de marché hors périmètre"
    assert refus("gemini_defi_3", sport="baseball") is None   # pas de filtre de sport


def test_gemini_defi_4_lignes_asiatiques():
    for sport in ("football", "basket", "handball", "rugby", "hockey", "football_americain"):
        assert refus("gemini_defi_4", sport=sport) is None
    assert refus("gemini_defi_4", sport="tennis") == "sport hors périmètre"
    for marche in ("HANDICAP", "TOTAL", "TOTAL_DOM", "TOTAL_EXT"):
        assert refus("gemini_defi_4", marche=marche) is None
    for marche in ("HANDICAP_3", "JEUX_HANDICAP", "SETS_TOTAL", "RESULTAT_1N2"):
        assert refus("gemini_defi_4", marche=marche) == "marché hors périmètre"


def test_gemini_defi_5_exotiques_foot_pinnacle_seul():
    for marche in ("CORRECT_SCORE", "HALF_TIME_FULL_TIME"):
        assert refus("gemini_defi_5", marche=marche) is None
    assert refus("gemini_defi_5", marche="RESULTAT_1N2") == "marché hors périmètre"
    assert refus("gemini_defi_5", sport="hockey") == "sport hors périmètre"
    assert refus("gemini_defi_5", reference="Betfair") == "référence hors périmètre"


def _exotique(pid, match, minute, issue="1-0", jour=T0):
    return pari(pid, **{**TYPES["gemini_defi_5"], "match_id": f"pmu|{match}", "issue": issue,
                        "preuve_prise": preuve(ref=match), **horloge(detecte=jour + timedelta(minutes=minute))})


def test_gemini_defi_5_deux_cotes_par_match_dans_l_ordre_d_arrivee():
    a, b, c = (_exotique(x, "m1", i, issue=f"{i}-0") for i, x in enumerate("abc"))
    autre = _exotique("d", "m2", 3)
    # Deux books du même match relié comptent ensemble : la carte d'événements le dit.
    ev = {id(a): "E1", id(b): "E1", id(c): "E1", id(autre): "E2"}
    assert selection_gemini_defi([c, autre, b, a], GEMINI_DEFI_5, DEBUT, evenements=ev) == {
        id(a), id(b), id(autre)}
    # Par défaut, les matchs reliés du registre (identites) : ici, un match_id par match.
    assert paris_gemini_defi_5([a, b, c, autre]) == {id(a), id(b), id(autre)}
    # La même cote revue plus tard ne prend pas une 2e place.
    a2 = pari("a2", **{**a, **horloge(detecte=T0 + timedelta(minutes=30))})
    assert paris_gemini_defi_5([a, a2, b]) == {id(a), id(b)}


def test_gemini_defi_5_dix_mises_par_jour_utc_premieres_arrivees():
    # 12 matchs le même jour UTC, écarts croissants : on garde les 10 premiers, pas les 10 plus gros écarts.
    jour = [pari(f"j{i}", **{**TYPES["gemini_defi_5"], "match_id": f"pmu|j{i}",
                             "preuve_prise": preuve(ref=f"j{i}"), "ecart": 0.08 + i / 100,
                             **horloge(detecte=T0 + timedelta(minutes=i))}) for i in range(12)]
    retenus = paris_gemini_defi_5(jour)
    assert retenus == {id(p) for p in jour[:10]}
    # Le jour est celui de l'UTC : 23:59 UTC et 00:01 UTC (01:01 à Paris) sont deux jours.
    soir = datetime(2026, 10, 30, 23, 0, tzinfo=timezone.utc)
    tard = [pari(f"s{i}", **{**TYPES["gemini_defi_5"], "match_id": f"pmu|s{i}", "preuve_prise": preuve(ref=f"s{i}"),
                             **horloge(detecte=soir + timedelta(minutes=i * 5))}) for i in range(12)]
    lendemain = pari("l", **{**TYPES["gemini_defi_5"], "match_id": "pmu|l", "preuve_prise": preuve(ref="l"),
                             **horloge(detecte=datetime(2026, 10, 31, 0, 1, tzinfo=timezone.utc))})
    assert len(paris_gemini_defi_5(tard)) == 10
    assert id(lendemain) in paris_gemini_defi_5(tard + [lendemain])
    # Les autres Gemini Défi n'ont pas de plafond.
    basket = [pari(f"b{i}", **{**TYPES["gemini_defi_1"], "match_id": f"w|{i}",
                               **horloge(detecte=T0 + timedelta(minutes=i))}) for i in range(15)]
    assert len(paris_gemini_defi_1(basket)) == 15


def test_gemini_defi_5_meme_seconde_sur_la_derniere_place_ecart_decroissant():
    # Match : une place prise, puis deux cotes à la même seconde pour la dernière place.
    a = _exotique("a", "m1", 0, issue="1-0")
    faible = pari("f", **{**_exotique("f", "m1", 5, issue="2-0"), "ecart": 0.10})
    fort = pari("F", **{**_exotique("F", "m1", 5, issue="3-0"), "ecart": 0.20})
    for ordre in ([a, faible, fort], [fort, faible, a], [faible, a, fort]):
        assert paris_gemini_defi_5(ordre) == {id(a), id(fort)}
    # Jour UTC : 9 mises, puis trois matchs différents à la même seconde pour la 10e place.
    neuf = [pari(f"n{i}", **{**TYPES["gemini_defi_5"], "match_id": f"pmu|n{i}", "preuve_prise": preuve(ref=f"n{i}"),
                             **horloge(detecte=T0 + timedelta(minutes=i))}) for i in range(9)]
    egaux = [pari(f"e{i}", **{**TYPES["gemini_defi_5"], "match_id": f"pmu|e{i}", "preuve_prise": preuve(ref=f"e{i}"),
                              "ecart": e, **horloge(detecte=T0 + timedelta(minutes=30))})
             for i, e in enumerate((0.09, 0.30, 0.12))]
    for ordre in (neuf + egaux, egaux[::-1] + neuf):
        assert paris_gemini_defi_5(ordre) == {id(p) for p in neuf} | {id(egaux[1])}
    # Une détection plus tôt garde sa place, même avec un écart plus faible : le départage ne vaut qu'à égalité.
    tot = pari("tot", **{**egaux[0], "id": "tot", "match_id": "pmu|tot", "preuve_prise": preuve(ref="tot"),
                         **horloge(detecte=T0 + timedelta(minutes=29))})
    assert paris_gemini_defi_5(neuf + egaux + [tot]) == {id(p) for p in neuf} | {id(tot)}


def test_une_mise_par_cote_francaise_premiere_detection_qui_passe():
    meme = {**TYPES["gemini_defi_1"], "match_id": "winamax|m"}
    refusee = pari("r0", **{**meme, "ecart": 0.01, **horloge(detecte=T0)})
    premier = pari("p1", **{**meme, **horloge(detecte=T0 + timedelta(minutes=1))})
    autre_ref = pari("p2", **{**meme, "reference": "Betfair", **horloge(detecte=T0 + timedelta(minutes=2))})
    autre_book = pari("p3", **{**meme, "bookmaker": "Betclic", "match_id": "betclic|m",
                               **horloge(detecte=T0 + timedelta(minutes=3))})
    autre_ligne = pari("p4", **{**meme, "marche": "TOTAL", "issue": "PLUS", "ligne": 160.5,
                                **horloge(detecte=T0 + timedelta(minutes=4))})
    tous = [autre_ligne, autre_book, autre_ref, premier, refusee]
    # Une détection refusée ne consomme pas la cote ; deux books restent deux mises.
    assert paris_gemini_defi_1(tous) == {id(premier), id(autre_book), id(autre_ligne)}


def test_lancement_sans_rejeu_ni_lecture_du_resultat():
    avant = pari("avant", **{**TYPES["gemini_defi_1"], **horloge(detecte=datetime(2026, 10, 30, 0, 59, 59,
                                                                                  tzinfo=timezone.utc))})
    pile = pari("pile", **{**TYPES["gemini_defi_1"], "match_id": "w|pile",
                           **horloge(detecte=datetime(2026, 10, 30, 1, 0, tzinfo=timezone.utc))})
    assert paris_gemini_defi_1([avant, pile]) == {id(pile)}
    # Une détection d'avant le lancement ne consomme pas la cote.
    apres = pari("apres", **{**TYPES["gemini_defi_1"], "match_id": avant["match_id"]})
    assert paris_gemini_defi_1([avant, apres]) == {id(apres)}
    for f in SELECTEURS.values():
        assert f([pile], depuis="2026-10-01T00:00:00Z") == set()
    assert selections_prudentes([pile], depuis="2026-10-01T00:00:00Z")["gemini_defi_1"] == set()
    # Résultat, gain, CLV et clôture n'entrent jamais dans la décision.
    for cle in REGLES:
        p = pari("type", **TYPES[cle])
        attendu = SELECTEURS[cle]([p])
        for issue in (dict(statut="gagne", gain=10.0, clv=0.3, cote_juste_cloture=1.5),
                      dict(statut="perdu", gain=-10.0, clv=-0.4, cote_juste_cloture=99.0)):
            q = {**p, **issue}
            assert SELECTEURS[cle]([q]) == {id(q)} and attendu == {id(p)}


def test_gel_au_lancement_et_famille_distincte():
    p = pari("g", **{**TYPES["gemini_defi_1"], "decide_le": iso(T0)})
    q = pari("h", **{**TYPES["gemini_defi_1"], "match_id": "w|h", "decide_le": iso(T0)})
    q["selections_figees"] = {}   # déjà décidée sans Gemini Défi : jamais ajoutée après coup
    figer_nouveaux([p, q], [p])
    assert p["selections_figees"]["gemini_defi_1"] == {"version": "1", "decide_le": iso(T0)}
    assert q["selections_figees"] == {}
    assert paris_gemini_defi_1([p, q]) == {id(p)}
    assert selections_prudentes([p, q])["gemini_defi_1"] == {id(p)}
    # Une prise figée garde sa décision, même si la règle la refuserait aujourd'hui.
    r = pari("r", **{**TYPES["gemini_defi_1"], "sport": "tennis", "match_id": "w|r",
                     "selections_figees": {"gemini_defi_1": {"version": "1", "decide_le": iso(T0)}}})
    assert paris_gemini_defi_1([r]) == {id(r)}
    cles = [c["cle"] for c in GEMINI_DEFIS]
    assert cles == ["gemini_defi_1", "gemini_defi_3", "gemini_defi_4", "gemini_defi_5"] and list(SELECTEURS) == cles
    # Gemini Défi 2 : abandonnée par Gemini, ni règle, ni sélecteur, ni clé suivie.
    import cotes.strategie_gemini_defi as module
    assert not hasattr(module, "GEMINI_DEFI_2") and not hasattr(module, "paris_gemini_defi_2")
    assert "gemini_defi_2" not in {v["cle"] for v in VARIANTES}
    assert "gemini_defi_2" not in selections_prudentes([p, q])
    assert all(c in VARIANTES for c in GEMINI_DEFIS)
    assert [d["cle"] for d in DEFIS] == ["defi_1", "defi_4"]
    autres = {g["cle"] for g in (*GROKS, *GROKS_V2, *GROKS_V3, *DEFIS)} | {"gemini"}
    assert not autres & set(cles)
    assert len({v["cle"] for v in VARIANTES}) == len(VARIANTES)
    assert len({v["nom"] for v in VARIANTES}) == len(VARIANTES)
    assert all(SELECTEURS[c].__wrapped__ for c in cles)   # @figer_selecteur


FIXTURE = Path(__file__).parent / "fixtures" / "gemini_defi_rejeu.csv"
# N du rejeu de référence et de la section 3 de la réponse finale de Gemini (construction, validation).
N_REJEU = {"gemini_defi_1": (175, 45), "gemini_defi_3": (59, 35),
           "gemini_defi_4": (72, 43), "gemini_defi_5": (59, 23)}


def _export():
    def nombre(x):
        return None if x == "" else float(x)
    paris = []
    for r in csv.DictReader(FIXTURE.open(encoding="utf-8")):
        paris.append(dict(
            id=r["id"], detecte=r["detecte_utc"], debut=r["debut_utc"], lu_reference=r["lu_reference_utc"],
            sport=r["sport"], marche=r["marche_type"], periode=r["periode"] or None, ligne=nombre(r["ligne"]),
            issue=r["issue"] or None, joueur=None, match_id=r["match_id"], bookmaker=r["bookmaker"],
            reference=r["reference"], cote=float(r["cote_fr"]), ecart=float(r["ecart"]),
            preuve_prise={"equipes_inversees": {"True": True, "False": False}.get(r["equipes_inversees"]),
                          "ressemblance_noms": nombre(r["score_association_journal"])},
            evenement=r["evenement"], bloc=r["bloc_defi"]))
    return paris


def test_rejeu_sur_l_export_retrouve_les_n_de_reference():
    paris = _export()
    assert len(paris) == 2845
    evenements = {id(p): p["evenement"] for p in paris}
    for c in GEMINI_DEFIS:
        retenus = selection_gemini_defi(paris, c, "2026-10-05T00:00:00Z", evenements=evenements)
        blocs = Counter(p["bloc"] for p in paris if id(p) in retenus)
        assert (blocs["construction"], blocs["validation"]) == N_REJEU[c["cle"]], c["cle"]
        # Le suivi réel ne commence qu'au lancement : aucune de ces lignes n'est prise.
        assert SELECTEURS[c["cle"]](paris) == set()
        if c is GEMINI_DEFI_5:
            # Égalités de seconde sur la dernière place (10/10 08:27:45, 11/10 06:14:28) : l'écart le plus
            # fort passe, comme le script de Gemini (tri detecte_utc croissant puis ecart_pct décroissant).
            ids = {p["id"] for p in paris if id(p) in retenus}
            assert {"8057ba64a0e7db7c", "aacd7426879c4f8c", "b21f55420fdf0fa8", "de73bae8c5a56953"} <= ids
            assert not {"462449c3f75ecf4d", "ae06920df68ed41c", "bd7d90afb2c9e4ab", "f557c0f7551bd892"} & ids
