"""Cotes boostées Winamax : lecture, traduction des intitulés, value contre la cote juste (cotes/boosts.py)."""
from datetime import datetime, timedelta, timezone

import pytest

from cotes import boosts as B
from cotes.direct import winamax

T = datetime(2026, 11, 16, 6, 0, tzinfo=timezone.utc)
ISO = T.isoformat(timespec="seconds")
DEBUT = (T + timedelta(hours=7)).isoformat(timespec="seconds")

# Trame réelle de la route sport:100000, relevée par la sonde du 16/11/2026 (champs inutiles retirés).
DOC = {"matches": {"1000314190": {"matchId": 1000314190, "available": True, "status": "PREMATCH", "isOutright": True,
                                  "title": "Cote Boostée : Carlos Alcaraz - Frances Tiafoe", "matchStart": 1794834000,
                                  "sportId": 100000},
                   "1000314576": {"matchId": 1000314576, "available": True, "status": "PREMATCH", "isOutright": True,
                                  "title": "Cote Boostée : Allemagne - Pays-Bas", "matchStart": 1794858300}},
       "bets": {"744536592": {"betId": 744536592, "matchId": 1000314190, "outcomes": [2304993346], "available": True,
                              "betTitle": "Cote boostée (mise max 20 €)", "previousOdd": 2.5},
                "744585606": {"betId": 744585606, "matchId": 1000314576, "outcomes": [2305129253], "available": True,
                              "betTitle": "Cote boostée (mise max 20 €)", "previousOdd": 2.45}},
       "outcomes": {"2304993346": {"label": "Carlos Alcaraz gagne par au moins 6 jeux d'écart", "available": True},
                    "2305129253": {"label": "Allemagne gagne à la mi-temps et à la fin du match", "available": True}},
       "odds": {"2304993346": 2.8, "2305129253": 2.7}}


def test_lecture_de_la_route_des_boosts():
    out = winamax.boosts_depuis(DOC, ISO)
    assert len(out) == 2
    b = next(x for x in out if "Alcaraz" in x["libelle"])
    assert (b["domicile"], b["exterieur"], b["cote"], b["cote_avant"], b["mise_max"]) == (
        "Carlos Alcaraz", "Frances Tiafoe", 2.8, 2.5, 20.0)
    assert b["debut"] == "2026-11-16T13:00:00+00:00" and b["id"] == "winamax|744536592|2304993346"
    assert b["lien"] == "https://www.winamax.fr/paris-sportifs/match/1000314190"
    assert winamax.boosts_depuis(None, ISO) == [] and winamax.boosts_depuis({"bets": []}, ISO) == []


def test_lecture_reseau_jamais_bloquante():
    class Panne:
        erreurs = ["sport:100000 : réseau"]
        echeance = None

        def demander(self, route):
            return None
    assert winamax.lire_boosts(transport=Panne()) == ([], ["sport:100000 : réseau"])


@pytest.mark.parametrize("libelle, dom, ext, sport, attendu", [
    ("Carlos Alcaraz gagne par au moins 6 jeux d'écart", "Carlos Alcaraz", "Frances Tiafoe", "tennis",
     ("JEUX_HANDICAP", "MATCH", -5.5, "DOM", None)),
    ("Allemagne gagne à la mi-temps et à la fin du match", "Allemagne", "Pays-Bas", "football",
     ("HALF_TIME_FULL_TIME", "MATCH", None, "DOM/DOM", None)),
    ("États-Unis (F) gagne par au moins 3 buts d'écart", "États-Unis (F)", "Canada (F)", "hockey",
     ("HANDICAP", "TEMPS_REG", -2.5, "DOM", None)),
    ("Canada (F) gagne par au moins 2 buts d'écart", "États-Unis (F)", "Canada (F)", "hockey",
     ("HANDICAP", "TEMPS_REG", 1.5, "EXT", None)),
    ("Jack Eichel marque au moins un but", "Vegas Golden Knights", "Vancouver Canucks", "hockey",
     ("JOUEUR:Goals", "MATCH", 0.5, "PLUS", "Jack Eichel")),
    ("Nikola Jokic marque au moins 30 points", "Denver Nuggets", "Los Angeles Lakers", "basket",
     ("JOUEUR:Points", "MATCH", 29.5, "PLUS", "Nikola Jokic")),
    ("Le PSG gagne le match", "PSG", "Marseille", "football", ("RESULTAT_1N2", "MATCH", None, "DOM", None)),
    ("Victoire de Marseille", "PSG", "Marseille", "football", ("RESULTAT_1N2", "MATCH", None, "EXT", None)),
    ("Sinner gagne", "Jannik Sinner", "Carlos Alcaraz", "tennis", ("VAINQUEUR", "MATCH", None, "DOM", None)),
    ("Plus de 2,5 buts dans le match", "PSG", "Marseille", "football", ("TOTAL", "MATCH", 2.5, "PLUS", None)),
    ("Lens ou match nul", "Lens", "Lille", "football", ("DOUBLE_CHANCE", "MATCH", None, "HOME_DRAW", None)),
    ("Les deux équipes marquent", "Lens", "Lille", "football", ("BOTH_TEAMS_TO_SCORE", "MATCH", None, "YES", None)),
    ("Lille marque plus de 1,5 buts", "Lens", "Lille", "football", ("TOTAL_EXT", "MATCH", 1.5, "PLUS", None)),
    # formulations réelles relevées par le dépôt cotes-boostees (Genybet, Betsson, OlyBet, octobre 2026)
    ("Lille (vs Arsenal) marque au moins 1 but", "Lille", "Arsenal", "football", ("TOTAL_DOM", "MATCH", 0.5, "PLUS", None)),
    ("Barcola Buteur", "LASK Linz", "Liverpool", "football", ("JOUEUR:Goals", "MATCH", 0.5, "PLUS", "Barcola")),
    ("Le PSG gagne 1-0", "Manchester City", "PSG", "football", ("CORRECT_SCORE", "MATCH", None, "0-1", None)),
    ("Monaco gagne 3-0", "Monaco", "CSKA Sofia", "football", ("CORRECT_SCORE", "MATCH", None, "3-0", None)),
    ("Les 2 équipes marquent", "Arsenal", "Lille", "football", ("BOTH_TEAMS_TO_SCORE", "MATCH", None, "YES", None)),
])
def test_traduction_des_intitules(libelle, dom, ext, sport, attendu):
    c = B.traduire(libelle, dom, ext, sport)[0]
    assert (c["marche"], c["periode"], c["ligne"], c["issue"], c["joueur"]) == attendu


@pytest.mark.parametrize("libelle", ["Arsenal gagne et les deux équipes marquent", "Plus de 2 buts dans le match",
                                     "Inconnu gagne", "Kane marque un doublé", "Arsenal gagne & Saka marque",
                                     "Paris SG gagne et les 2 équipes marquent", "Pavel Sulc Décisif",
                                     "Real Madrid to win and Vinicius to score"])
def test_combines_et_intitules_inconnus(libelle):
    assert B.traduire(libelle, "Arsenal", "Chelsea", "football") == []


def _ligne(marche, issue, cote, periode="MATCH", ligne=None, mid="winamax|72", dom="Carlos Alcaraz",
           ext="Frances Tiafoe", sport="tennis", joueur=None):
    return {"source": "Winamax", "bookmaker": "winamax", "match_id": mid, "domicile": dom, "exterieur": ext,
            "debut": "2026-11-16T13:00:00+00:00", "sport": sport, "ligue": "ATP", "marche": marche, "periode": periode,
            "ligne": ligne, "issue": issue, "cote": cote, "collecte": ISO, "joueur": joueur}


def _index(cles: dict, mid="winamax|72"):
    return {"Pinnacle": {mid: {k: {"match_id": 1, "inverse": False, "proba_juste": p, "collecte": ISO}
                               for k, p in cles.items()}}}


def test_value_du_boost_contre_la_cote_juste():
    boosts = winamax.boosts_depuis(DOC, ISO)
    fr = [_ligne("JEUX_HANDICAP", "DOM", 2.5, ligne=-5.5), _ligne("JEUX_HANDICAP", "EXT", 1.5, ligne=-5.5)]
    idx = _index({("JEUX_HANDICAP", "MATCH", -5.5, "DOM"): 0.38, ("JEUX_HANDICAP", "MATCH", -5.5, "EXT"): 0.62})
    b = next(x for x in B.evaluer(boosts, fr, idx, T) if "Alcaraz" in x["libelle"])
    assert b["statut"] == "évalué" and b["verifie"] is True and b["cote_habituelle"] == 2.5
    assert b["value"] == pytest.approx(2.8 * 0.38 - 1, abs=1e-4) and b["cote_juste"] == pytest.approx(2.632, abs=1e-3)
    assert b["hausse"] == pytest.approx(0.12) and b["marge_seuil"] == pytest.approx(0.1071, abs=1e-4)
    assert b["pari"] == "Carlos Alcaraz -5,5 jeux"


def test_la_cote_d_avant_choisit_la_periode():
    """Hockey : temps réglementaire par défaut, mais la cote d'avant désigne le marché prolongation comprise."""
    boost = {"id": "b", "bookmaker": "Winamax", "domicile": "USA (F)", "exterieur": "Canada (F)", "debut": DEBUT,
             "libelle": "USA (F) gagne par au moins 2 buts d'écart", "cote": 3.0, "cote_avant": 2.6, "lu": ISO}
    kw = dict(dom="USA (F)", ext="Canada (F)", sport="hockey", mid="winamax|9")
    fr = [{**_ligne("HANDICAP", "DOM", 2.9, "TEMPS_REG", -1.5, **kw), "debut": DEBUT},
          {**_ligne("HANDICAP", "DOM", 2.6, "MATCH", -1.5, **kw), "debut": DEBUT}]
    idx = _index({("HANDICAP", "MATCH", -1.5, "DOM"): 0.36}, mid="winamax|9")
    b = B.evaluer([boost], fr, idx, T)[0]
    assert (b["periode"], b["verifie"], b["value"]) == ("MATCH", True, pytest.approx(0.08))


def test_combine_sans_cote_juste_garde_la_hausse():
    boost = {"id": "c", "bookmaker": "Winamax", "domicile": "Carlos Alcaraz", "exterieur": "Frances Tiafoe",
             "debut": "2026-11-16T13:00:00+00:00", "libelle": "Alcaraz gagne et plus de 22,5 jeux",
             "cote": 3.0, "cote_avant": 2.5, "lu": ISO}
    b = B.evaluer([boost], [_ligne("VAINQUEUR", "DOM", 1.2)], {}, T)[0]
    assert b["statut"] == "combiné ou intitulé non traduit" and b["value"] is None and b["hausse"] == pytest.approx(0.2)


def test_match_introuvable_et_match_commence():
    boost = {"id": "d", "bookmaker": "Winamax", "domicile": "Rafael Nadal", "exterieur": "Roger Federer",
             "debut": "2026-11-16T13:00:00+00:00", "libelle": "Nadal gagne", "cote": 2.0, "cote_avant": 1.8, "lu": ISO}
    assert B.evaluer([boost], [_ligne("VAINQUEUR", "DOM", 1.2)], {}, T)[0]["statut"] == "match introuvable"
    passe = {**boost, "debut": (T - timedelta(minutes=5)).isoformat()}
    assert B.evaluer([passe], [], {}, T) == []


def test_pari_habituel_a_une_tout_autre_cote():
    """Le pari traduit existe chez Winamax mais à 1,40 pour une cote d'avant de 2,50 : ce n'est pas lui."""
    boosts = winamax.boosts_depuis(DOC, ISO)
    fr = [_ligne("JEUX_HANDICAP", "DOM", 1.4, ligne=-5.5)]
    b = next(x for x in B.evaluer(boosts, fr, {}, T) if "Alcaraz" in x["libelle"])
    assert b["statut"] == "pari standard introuvable"


def test_suivi_et_bilan():
    a = {"id": "x", "libelle": "L", "cote": 2.8, "cote_avant": 2.5, "mise_max": 20.0, "value": 0.064, "cote_juste": 2.63,
         "statut": "évalué", "verdict": "jouer"}
    b = {"id": "y", "libelle": "M", "cote": 3.0, "cote_avant": 2.5, "mise_max": None, "value": None, "statut": "sans",
         "verdict": "jouer"}
    etat = B.suivre({}, [a, b], T)
    etat = B.suivre(etat, [{**a, "value": 0.05}], T + timedelta(minutes=5))
    e = next(x for x in etat["episodes"] if x["id"] == "x")
    assert (e["cycles"], e["value_initiale"], e["value_derniere"]) == (2, 0.064, 0.05)
    bl = B.bilan(etat["episodes"], T + timedelta(hours=1))
    assert (bl["n"], bl["evalues"], bl["positifs"], bl["gain_espere"]) == (2, 1, 1, 1.28)
    assert (bl["jouer"], bl["jouer_sans_juste"]) == (2, 1)            # le « jouer » sans cote juste hors gain espéré
    assert B.suivre(etat, [], T + timedelta(days=B.GARDER_JOURS + 1))["episodes"] == []


def test_etape_du_cycle_ecrit_boosts_json(tmp_path):
    from cotes.pipeline.analyse import boosts_du_cycle
    fr = [_ligne("JEUX_HANDICAP", "DOM", 2.5, ligne=-5.5)]
    idx = _index({("JEUX_HANDICAP", "MATCH", -5.5, "DOM"): 0.38})
    journal = {}
    r = boosts_du_cycle(tmp_path, fr, idx, journal, lire=lambda: (winamax.boosts_depuis(DOC, ISO), []), maintenant=T)
    assert r == {"lus": 2, "evalues": 1, "couverts": 0, "par_bookmaker": {"Winamax": 2}, "erreurs": []}
    import json
    doc = json.loads((tmp_path / "boosts.json").read_text())
    assert len(doc["actuels"]) == 2 and len(doc["episodes"]) == 2
    r = boosts_du_cycle(tmp_path, fr, idx, journal, lire=lambda: 1 / 0, maintenant=T)
    assert "erreur" in r and journal["echecs"][0]["etape"] == "boosts"


def test_boost_d_un_autre_bookmaker_relie_a_un_match_retourne():
    """Boost NetBet « Lille (vs Arsenal) » sans cote d'avant ; seul Winamax a le match, écrit Arsenal – Lille : la
    cote juste vient de la référence de ce match, l'équipe est retrouvée par son nom."""
    boost = {"id": "netbet|1|2", "bookmaker": "NetBet", "domicile": "Lille", "exterieur": "Arsenal", "debut": DEBUT,
             "libelle": "Lille (vs Arsenal) marque au moins 1 but", "cote": 2.1, "cote_avant": None, "lu": ISO}
    kw = dict(dom="Arsenal", ext="Lille", sport="football", mid="winamax|5")
    fr = [{**_ligne("TOTAL_EXT", "PLUS", 1.62, ligne=0.5, **kw), "debut": DEBUT}]
    idx = _index({("TOTAL_EXT", "MATCH", 0.5, "PLUS"): 0.55}, mid="winamax|5")
    b = B.evaluer([boost], fr, idx, T)[0]
    assert (b["match_id"], b["marche"], b["issue"], b["verifie"]) == ("winamax|5", "TOTAL_EXT", "PLUS", False)
    assert b["value"] == pytest.approx(2.1 * 0.55 - 1) and b["statut"] == "évalué"


def test_pari_a_long_terme_non_evalue():
    boost = {"id": "u", "bookmaker": "Unibet", "domicile": "HOU Rockets", "exterieur": "X", "debut": DEBUT,
             "libelle": "Fred VanVleet fait 6 passes ou + (moyenne)", "cote": 2.1, "cote_avant": 1.8, "lu": ISO,
             "long_terme": True}
    assert B.evaluer([boost], [], {}, T)[0]["statut"] == "pari à long terme"


def test_verdict_jouer_ou_passer():
    assert B.verdict({"value": 0.04}) == ("jouer", None) and B.verdict({"value": -0.01}) == ("passer", None)
    # Sans cote juste : +29,3 % de hausse → seuil 22,66 %, très au-dessus de la marge habituelle (6 % + 5 %).
    assert B.verdict({"libelle": "Lyon gagne", "pari": "Lyon", "value": None, "marge_seuil": 0.2266}) == ("jouer", 0.06)
    assert B.verdict({"libelle": "Lyon gagne", "pari": "Lyon", "value": None, "marge_seuil": 0.08})[0] == "passer"
    # Combiné de trois sélections : marge attendue ≈ 16,9 %, il faut au moins ≈ 21,9 %.
    combo = {"libelle": "Lyon gagne, Paris gagne et Lens gagne", "value": None}
    assert B.verdict({**combo, "marge_seuil": 0.2})[0] == "passer"
    assert B.verdict({**combo, "marge_seuil": 0.23}) == ("jouer", pytest.approx(0.1694, abs=1e-4))
    assert B.verdict({"value": None, "marge_seuil": None}) == ("passer", None)


@pytest.mark.parametrize("boost, attendu", [
    ({"libelle": "Daniil Medvedev gagne 2-1", "domicile": "D. Medvedev", "exterieur": "F. Cobolli"}, "score exact"),
    ({"libelle": "Zverev gagne 2 sets à 0", "domicile": "A", "exterieur": "B"}, "score exact"),
    ({"libelle": "Erling Haaland marque au moins un but", "domicile": "A", "exterieur": "B"}, "simple"),
    ({"libelle": "Luka Doncic marque au moins 40 points", "domicile": "A", "exterieur": "B"}, "joueur"),
    ({"libelle": "A.Zverev gagne le 1er set 6-3 ou 6-4 ?", "domicile": "A", "exterieur": "B"}, "joueur"),
    ({"libelle": "Lyon gagne et plus de 2,5 buts", "domicile": "Lyon", "exterieur": "Nice"}, "combiné même match"),
    ({"libelle": "Plus de 1,5 buts dans chacun des 4 matchs", "domicile": "Ligue 1", "exterieur": "21/11"},
     "combiné multi-matchs"),
    ({"libelle": "Chaque équipe à domicile gagne", "domicile": "Pro D2", "exterieur": None}, "combiné multi-matchs"),
    ({"libelle": "Lyon gagne", "domicile": "Lyon", "exterieur": "Nice"}, "simple"),
    ({"libelle": "Le PSG champion", "long_terme": True}, "long terme"),
])
def test_type_boost_comme_cotes_boostees(boost, attendu):
    assert B.type_boost(boost) == attendu


def test_exclusions_hockey_football_americain_score_exact():
    match = {"domicile": "A", "exterieur": "B", "value": 0.2, "marge_seuil": 0.4}
    assert B.verdict({**match, "libelle": "A gagne", "sport": "football"})[0] == "jouer"
    for boost in ({**match, "libelle": "A gagne", "sport": "hockey"},
                  {**match, "libelle": "A gagne", "sport": "football_americain"},
                  {**match, "libelle": "A gagne 2-1", "sport": "football"},
                  {"libelle": "Chaque équipe à domicile marque au moins 3 buts lors des 3 matchs", "domicile": "KHL",
                   "value": None, "marge_seuil": 0.5}):
        assert B.verdict(boost) == ("passer", None) and B.exclusion(boost)
    assert B.exclusion({**match, "libelle": "A gagne", "sport": "hockey"}).startswith("Hockey : 15 gagnés pour 23,3")


def test_bilan_types_historique_plus_regles_ici():
    resultats = {"a": {"statut": "gagne", "cote": 2.0, "libelle": "A gagne et plus de 2,5 buts", "domicile": "A",
                       "exterieur": "B"},
                 "b": {"statut": "rembourse", "cote": 2.0, "libelle": "A gagne", "domicile": "A", "exterieur": "B"},
                 "c": {"statut": "perdu", "cote": 4.0, "libelle": "A gagne", "domicile": "A", "exterieur": "B"}}
    t = {x["type"]: x for x in B.bilan_types(resultats)["types"]}
    cmm, simple = t["combiné même match"], t["simple"]
    assert (cmm["paris"], cmm["gagnes"], cmm["ici"]) == (161, 64, {"paris": 1, "gagnes": 1, "attendus": 0.5})
    assert (simple["paris"], simple["gagnes"], simple["attendus"]) == (174, 51, 57.2)
    assert cmm["conseil"] == "prendre" and simple["conseil"] == "eviter" and t["score exact"]["exclu"]
    vide = {x["type"]: x for x in B.bilan_types({})["types"]}
    assert vide["joueur"]["paris"] == 315 and vide["joueur"]["ici"]["paris"] == 0


@pytest.mark.parametrize("libelle, n", [
    ("PSG gagne + Mbappé marque + Plus de 2,5 buts", 3),
    ("Real gagne & Bellingham buteur", 2),
    ("Arsenal gagne puis plus de 1,5 buts", 2),
    ("Lyon gagne, Paris gagne et Lens gagne", 3),
    ("Lakers +4,5", 1),
    ("Plus de 2,5 buts", 1),
    ("Lakers + 4,5 points", 1),
    ("Mbappé 1+ tir cadré", 1),
])
def test_selections_compte_tous_les_separateurs_de_combine(libelle, n):
    assert B.selections({"libelle": libelle}) == n


def test_selections_boost_traduit_vaut_une():
    assert B.selections({"libelle": "PSG gagne + Mbappé marque", "pari": "PSG"}) == 1


def test_evaluer_donne_un_verdict_a_chaque_boost():
    boost = {"id": "c", "bookmaker": "Winamax", "domicile": "Carlos Alcaraz", "exterieur": "Frances Tiafoe",
             "debut": "2026-11-16T13:00:00+00:00", "libelle": "Alcaraz gagne et plus de 22,5 jeux",
             "cote": 2.9, "cote_avant": 2.5, "lu": ISO}
    b = B.evaluer([boost], [_ligne("VAINQUEUR", "DOM", 1.2)], {}, T)[0]
    assert b["verdict"] == "passer" and b["marge_attendue"] == pytest.approx(0.1164, abs=1e-4)   # seuil 13,8 %


def test_bilan_compte_les_verdicts_et_les_anciens_episodes():
    eps = [{"id": "a", "premier": ISO, "value_initiale": 0.03},                       # avant le verdict : déduit
           {"id": "b", "premier": ISO, "value_initiale": -0.02},
           {"id": "c", "premier": ISO, "value_initiale": None, "verdict_initial": "passer"},
           {"id": "d", "premier": ISO, "value_initiale": None}]                       # ancien, sans cote juste : ignoré
    bl = B.bilan(eps, T + timedelta(hours=1))
    assert (bl["n"], bl["jouer"], bl["jouer_sans_juste"]) == (4, 1, 0)


def test_le_verdict_suit_la_cote_juste_arrivee_plus_tard():
    b = {"id": "z", "libelle": "L", "cote": 2.0, "cote_avant": 1.9, "value": None, "verdict": "passer"}
    etat = B.suivre({}, [b], T)
    etat = B.suivre(etat, [{**b, "value": 0.04, "verdict": "jouer"}], T + timedelta(minutes=5))
    assert etat["episodes"][0]["verdict_initial"] == "jouer"
