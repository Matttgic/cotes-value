"""Lot « justesse » (9/11/2026) : listes Pinnacle incomplètes non pariables, référence suspecte (marquage seulement),
appariement strict (marqueurs, clubs homonymes, prénoms au tennis). Données au format réel, sans réseau."""
from datetime import datetime, timedelta, timezone

import pytest

from cotes import VERSION, correspondance as C, pinnacle as P
from cotes.comparaison import MOTIF_LISTE_INCOMPLETE, comparer, reference_suspecte
from cotes.marches import cle, harmoniser_pinnacle
from cotes.notifications import alertes_recheck, flux
from cotes.simulation import placer
from tests.test_controle import ligne

T0 = datetime(2029, 12, 31, 20, 0, tzinfo=timezone.utc)


# --------------------------------------------------------------------------- (a) listes incomplètes

def _special(marche, issues, cote=8.0):
    base = {"source": "pinnacle", "sport": "football", "match_id": 1, "domicile": "Lens", "exterieur": "Lille",
            "debut": "2030-01-01T20:00:00Z", "periode": "MATCH", "ligne": None, "joueur": None, "cle_marche": "s"}
    return [{**base, "marche": marche, "issue": i, "cote": cote} for i in issues]


def test_score_exact_pinnacle_marque_liste_incomplete_et_garde_sa_proba():
    rows = _special("SPECIAL:Correct Score", ["Lens 1, Lille 0", "Lens 2, Lille 1", "Lens 0, Lille 0"])
    P._ajouter_proba_justes(rows)
    assert all(l["liste_incomplete"] is True and l["proba_juste"] for l in rows)       # toujours observée
    traduites = harmoniser_pinnacle(rows)
    assert {l["issue"] for l in traduites} == {"1-0", "2-1", "0-0"}
    assert all(l["marche"] == "CORRECT_SCORE" and l["liste_incomplete"] for l in traduites)


def test_marche_a_issues_connues_n_est_pas_marque():
    rows = [{"cle_marche": "x", "marche": "VAINQUEUR", "issue": i, "cote": 1.9, "match_id": 1, "periode": "MATCH",
             "ligne": None, "joueur": None} for i in ("DOM", "EXT")]
    P._ajouter_proba_justes(rows)
    assert all("liste_incomplete" not in l and l["proba_juste"] for l in rows)


def _comparer(incomplete, references=("Pinnacle",)):
    fr = [ligne(marche="CORRECT_SCORE", ligne=None, issue="2-1", cote=9.0, collecte=T0.isoformat())]
    index = {}
    for nom in references:
        ref = {**fr[0], "source": nom.lower(), "proba_juste": 0.12, "cote": 7.5, "collecte": T0.isoformat(),
               "match_id": "p1", "score_association": 1.0, "inverse": False}
        if nom == "Pinnacle":
            ref |= {"marge_pinnacle": .05, "age_cache_s": 30}
            if incomplete:
                ref["liste_incomplete"] = True
        index[nom] = {"m1": {cle(fr[0]): ref}}
    return {o["reference"]: o for o in comparer(fr, {n: [] for n in references}, index=index)}


def test_liste_incomplete_jamais_pariable_mais_visible_en_observation():
    temoin = _comparer(False)["Pinnacle"]
    assert temoin["pariable"] is True and placer([temoin], [], maintenant=T0)          # même cas, liste complète
    o = _comparer(True)["Pinnacle"]
    assert o["suspect"] == MOTIF_LISTE_INCOMPLETE == "liste incomplète"
    assert o["pariable"] is False and o["liste_incomplete"] is True and o["ecart"] == pytest.approx(0.08)
    assert placer([o], [], maintenant=T0) == []


def test_consensus_qui_contient_une_liste_incomplete_n_est_pas_pariable():
    o = _comparer(True, references=("Pinnacle", "Polymarket"))
    assert o["Consensus"]["pariable"] is False and o["Consensus"]["suspect"] == MOTIF_LISTE_INCOMPLETE
    assert o["Polymarket"]["pariable"] is True                                       # l'autre référence : intacte
    assert placer(list(o.values()), [], maintenant=T0)[0]["reference"] == "Polymarket"


# --------------------------------------------------------------------------- (b) référence suspecte

@pytest.mark.parametrize("o, motif", [
    ({"reference": "Pinnacle", "ecart": 0.31, "cote": 12.0, "proba_juste": 0.11}, "écart > 30 %"),
    ({"reference": "Pinnacle", "ecart": 0.30, "cote": 12.0, "proba_juste": 0.11}, None),
    ({"reference": "Polymarket", "marche": "VAINQUEUR", "periode": "MATCH", "proba_juste": 0.5, "cote": 2.6,
      "ecart": 0.3}, "Polymarket figé à 50/50"),
    # forme d'un pari enregistré : cote juste au lieu de la probabilité
    ({"reference": "Polymarket", "marche": "VAINQUEUR", "periode": "MATCH", "cote_juste": 1.99, "cote": 2.4,
      "ecart": 0.2}, "Polymarket figé à 50/50"),
    ({"reference": "Polymarket", "marche": "VAINQUEUR", "periode": "MATCH", "proba_juste": 0.5, "cote": 2.1,
      "ecart": 0.05}, None),                                  # le bookmaker donne plus de 45 % : pas le cas « figé »
    ({"reference": "Polymarket", "marche": "VAINQUEUR", "periode": "MATCH", "proba_juste": 0.52, "cote": 2.6,
      "ecart": 0.35}, "écart > 30 %"),                         # hors de la bande 0,5 ± 0,016
    ({"reference": "Pinnacle", "marche": "VAINQUEUR", "periode": "MATCH", "proba_juste": 0.5, "cote": 2.6,
      "ecart": 0.3}, None),                                    # figé 50/50 : Polymarket seulement
    ({"reference": "Polymarket", "marche": "TOTAL", "periode": "MATCH", "proba_juste": 0.5, "cote": 2.6,
      "ecart": 0.3}, None),
])
def test_reference_suspecte(o, motif):
    assert reference_suspecte(o) == motif


def _prise(**kw):
    return {**ligne(cote=2.6, collecte=T0.isoformat()), "reference": "Polymarket", "marche": "VAINQUEUR",
            "issue": "DOM", "ligne": None, "cote_juste": 2.0, "proba_juste": 0.5, "ecart": 0.3, "detecte": T0.isoformat(),
            "lu_reference": T0.isoformat(), "pari": "Lens vainqueur", "match_id": "m1", **kw}


def test_reference_suspecte_marquee_pari_pris_et_jamais_alertee():
    o = _prise(reference_suspecte="Polymarket figé à 50/50")
    p = placer([o], [], maintenant=T0)                      # marquage seulement : le pari est pris comme avant
    assert len(p) == 1 and p[0]["reference_suspecte"] == "Polymarket figé à 50/50"
    maintenant = T0 + timedelta(minutes=2)
    ids = {"strategie": {id(p[0])}}
    assert flux([o], p, ids, maintenant)["alertes"] == []
    sain = _prise(cote_juste=2.3, proba_juste=0.435, ecart=0.13)        # même prise, référence saine : alertée
    q = {**{k: v for k, v in p[0].items() if k != "reference_suspecte"}, "cote_juste": 2.3, "ecart": 0.13}
    assert len(flux([sain], [q], {"strategie": {id(q)}}, maintenant)["alertes"]) == 1
    figee = {**p[0], "selections_figees": {"labo:PIN-1.3-2-e2-h36": {}}, "redecision_lecture_posterieure": "x"}
    assert alertes_recheck([figee], maintenant=maintenant) == []
    sain = {k: v for k, v in figee.items() if k != "reference_suspecte"}
    assert alertes_recheck([{**sain, "cote_juste": 2.3, "ecart": 0.13}], maintenant=maintenant)


def test_version_du_moteur_incrementee():
    assert VERSION == "2026-11-09-justesse"


# --------------------------------------------------------------------------- (c) appariement

# pièges communs aux trois dépôts (banc de l'architecte, 9/11/2026)
REFUSEES = [("Paris FC", "Paris SG"), ("Paris FC", "Paris Saint-Germain"), ("Arsenal W", "Arsenal"),
            ("Arsenal Women", "Arsenal"), ("Jong Ajax", "Ajax"), ("France U21", "France"),
            ("Real Madrid B", "Real Madrid"), ("Real Sociedad B", "Real Sociedad"), ("Inter Miami", "Inter")]
ACCEPTEES = [("Man City", "Manchester City"), ("Internazionale", "Inter"), ("Inter", "Inter Milan"),
             ("PSG", "Paris Saint-Germain"), ("Paris SG", "Paris Saint-Germain"), ("Bayern Munich", "Bayern München"),
             ("Naples", "Napoli"), ("Celta Vigo", "Celta de Vigo"), ("Marseille", "Olympique de Marseille"),
             ("Saint-Etienne", "AS Saint-Étienne"), ("Bodø/Glimt", "Bodo Glimt"), ("Jong Ajax", "Ajax II"),
             ("Inter Miami CF", "Inter Miami")]
TENNIS_REFUSEES = [("Venus Williams", "Serena Williams"), ("V. Williams", "S. Williams"),
                   ("Pliskova Ka.", "Pliskova Kr."), ("Pliskova Kr.", "Karolina Pliskova"),
                   ("Petros Tsitsipas", "Stefanos Tsitsipas"), ("Wang Xin.", "Xiyu Wang")]
TENNIS_ACCEPTEES = [("V. Williams", "Venus Williams"), ("Pliskova Ka.", "Karolina Pliskova"),
                    ("D.Medvedev", "Daniil Medvedev"), ("Danil Medvedev", "Daniil Medvedev"),
                    ("Aleksandr Bublik", "Alexander Bublik"), ("Hsieh S.", "Su-Wei Hsieh"),
                    ("Cerundolo J.M.", "Juan Manuel Cerundolo"), ("De Minaur A.", "Alex de Minaur"),
                    ("E. Mertens /D. Shnaider", "Elise Mertens / Diana Shnaider"),
                    ("F. Cabral/J. Tracy", "Cabral/Tracy")]


@pytest.mark.parametrize("a, b", REFUSEES)
def test_pieges_refuses(a, b):
    assert C.ressemblance_appariement(a, b) == 0 and C.ressemblance_appariement(b, a) == 0


@pytest.mark.parametrize("a, b", ACCEPTEES)
def test_paires_acceptees(a, b):
    assert C.ressemblance_appariement(a, b) >= 0.75


@pytest.mark.parametrize("a, b", TENNIS_REFUSEES)
def test_tennis_prenoms_differents_refuses(a, b):
    assert C.ressemblance_appariement(a, b, True) == 0


@pytest.mark.parametrize("a, b", TENNIS_ACCEPTEES)
def test_tennis_initiales_compatibles_gardees(a, b):
    assert C.ressemblance_appariement(a, b, True) == pytest.approx(C.ressemblance(a, b))


def test_marqueur_absent_chez_une_reference_reste_une_penalite():
    # Pinnacle n'écrit pas toujours « Women » (WNBA) : son absence ne prouve rien côté référence
    assert C.ressemblance_appariement("Atlanta Dream (W)", "Atlanta Dream", False, True, False) == pytest.approx(0.85)
    # le bookmaker français l'écrit toujours : son absence face à une référence marquée = autre équipe
    assert C.ressemblance_appariement("Atlanta Dream", "Atlanta Dream Women", False, True, False) == 0


def _m(source, mid, dom, ext, ligue=None, sport="football", debut="2030-01-01T20:00:00+00:00"):
    return {"source": source, "match_id": mid, "sport": sport, "domicile": dom, "exterieur": ext, "debut": debut,
            "ligue": ligue}


def test_associer_refuse_le_match_feminin_pour_le_match_masculin():
    fr = C.matchs_de([_m("Winamax", "w1", "Arsenal", "Chelsea", "Premier League")])
    ref = C.matchs_de([_m("Matchbook", "r1", "Arsenal Women", "Chelsea Women", "Women's Super League",
                          debut="2030-01-01T20:30:00+00:00")])
    assert C.associer(fr, ref) == {}


def test_marqueur_de_ligue_reporte_pour_toutes_les_sources():
    # « (F) » des ligues françaises et « Women » d'une ligue Polymarket / Matchbook : les noms se rejoignent
    fr = C.matchs_de([_m("PMU", "w1", "Bordeaux", "Nantes", "Ligue A (F)", sport="volley")])
    ref = C.matchs_de([_m("polymarket", "r1", "Bordeaux", "Nantes", "womens-ligue-a", sport="volley")])
    assert fr["w1"]["domicile"] == "Bordeaux Women" and ref["r1"]["domicile"] == "Bordeaux Women"
    assert C.associer(fr, ref) == {"w1": ("r1", False, 1.0)}
    assert C._marqueurs_ligue_appariement("Lyon", "Coupe du Monde - Groupe F") == "Lyon"
    assert C._marqueurs_ligue_appariement("Lyon", "Liga F") == "Lyon Women"


def test_associer_tennis_soeurs_refusees():
    fr = C.matchs_de([_m("Betclic", "w1", "V. Williams", "Pliskova Ka.", sport="tennis")])
    ref = C.matchs_de([_m("pinnacle", "r1", "Serena Williams", "Karolina Pliskova", sport="tennis"),
                       _m("pinnacle", "r2", "Venus Williams", "Karolina Pliskova", sport="tennis")])
    assert C.associer(fr, ref)["w1"][0] == "r2"
