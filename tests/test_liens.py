"""Lien direct vers la page du match, par bookmaker et par sport.

Formats vérifiés le 25/10/2026 sur de vrais matchs depuis la France : Winamax River Plate - Racing et Utah -
Lakers, PMU PSG - Lyon et Valentova - Pohankova, NetBet PSG - Lyon et Anglet - Marseille, Betclic Barcelone -
Real, Brindisi - Avellino et Chicago - Florida, Unibet 255 liens de 10 sports, OlyBet PSG - Lyon et
Philadelphia - Detroit. Ces tests figent la forme ; ils ne remplacent pas une vérification en ligne.
"""
import pytest

from cotes.direct import olybet, unibet
from cotes.liens import (BETCLIC_SPORTS, OLYBET_SPORTS, UNIBET_SPORTS, completer_liens, lien_info, lien_match,
                         slug)

SPORTS = ("football", "tennis", "basket", "hockey", "handball", "volley", "rugby", "rugby_league",
          "football_americain", "baseball", "boxe", "mma", "snooker", "golf", "cyclisme")


def pari(bookmaker, match_id, sport="football", **kw):
    return {"bookmaker": bookmaker, "match_id": match_id, "sport": sport, "ligue": "Ligue 1",
            "domicile": "Paris SG", "exterieur": "Lyon", **kw}


@pytest.mark.parametrize("sport", SPORTS)
def test_identifiant_seul_winamax_pmu_netbet(sport):
    assert lien_info(pari("Winamax", "winamax|73719388", sport)) == \
        ("https://www.winamax.fr/paris-sportifs/match/73719388", False)
    assert lien_info(pari("PMU", "pmu|1029625568", sport)) == ("https://www.pmu.fr/sport/event/1029625568", False)
    assert lien_info(pari("NetBet", "netbet|12304431", sport)) == ("https://www.netbet.fr/evenement/12304431", False)


@pytest.mark.parametrize("sport", SPORTS)
def test_betclic_construit_pour_chaque_sport_et_finit_par_l_identifiant(sport):
    lien, repli = lien_info(pari("Betclic", "betclic|1260064035864576", sport))
    segment = BETCLIC_SPORTS.get(sport, "sport-s1")
    assert not repli and lien == f"https://www.betclic.fr/{segment}/ligue-1-c1/paris-sg-lyon-m1260064035864576"


def test_betclic_prefere_le_chemin_de_la_collecte():
    releve = "/hockey-sur-glace-sice_hockey/nhl-c83/chicago-blackhawks-florida-panthers-m1233774502252544"
    assert lien_match(pari("Betclic", "betclic|1233774502252544", "hockey", lien=releve)) == \
        "https://www.betclic.fr" + releve
    # chemin d'un autre match : reconstruit avec le bon identifiant
    assert lien_match(pari("Betclic", "betclic|7", lien="/football-sfootball/l1-c4/a-b-m999")).endswith("-m7")


@pytest.mark.parametrize("sport", SPORTS)
def test_unibet_chemin_exact_sinon_page_du_sport(sport):
    releve = f"/paris-{UNIBET_SPORTS.get(sport, 'football')}/france/ligue-1/3388199/paris-sg-vs-lyon"
    assert lien_info(pari("Unibet", "unibet-fr|3388199", sport, lien=releve)) == ("https://www.unibet.fr" + releve, False)
    repli = f"https://www.unibet.fr/paris-{UNIBET_SPORTS[sport]}" if sport in UNIBET_SPORTS else \
        "https://www.unibet.fr/paris-tous-sports"
    assert lien_info(pari("Unibet", "unibet-fr|3388199", sport)) == (repli, True)


@pytest.mark.parametrize("sport", SPORTS)
def test_olybet_chemin_exact_sinon_page_du_sport(sport):
    alias = OLYBET_SPORTS.get(sport, "Soccer")
    releve = f"/sportsbook/pre-match/match/{alias}/North%20America/756/31196570"
    assert lien_info(pari("OlyBet", "olybet|31196570", sport, lien=releve)) == ("https://www.olybet.fr" + releve, False)
    repli = "https://www.olybet.fr/sportsbook/pre-match/match" + (f"/{OLYBET_SPORTS[sport]}" if sport in OLYBET_SPORTS else "")
    assert lien_info(pari("OlyBet", "olybet|31196570", sport)) == (repli, True)


def test_aucune_recherche_google_et_anciens_domaines_remplaces():
    paris = [pari(b, m, lien="https://www.google.com/search?q=site%3Ax+PSG") for b, m in
             (("Betclic", "betclic|1"), ("PMU", "pmu|2"), ("Unibet", "unibet-fr|3"), ("OlyBet", "olybet|4"),
              ("Winamax", "winamax|5"), ("NetBet", "netbet|6"))]
    paris.append(pari("PMU", "pmu|10266", lien="https://paris-sportifs.pmu.fr/sport/football/l1/psg---om/10266"))
    completer_liens(paris)
    assert not any("google" in p["lien"] or "paris-sportifs.pmu.fr" in p["lien"] for p in paris)
    assert all(p["lien"].startswith("https://www.") for p in paris)


def test_slug_comme_les_sites():
    assert slug("Ligue 1 McDonald's®") == "ligue-1-mcdonald-s"
    assert slug("Rugby à XIII") == "rugby-a-xiii" and slug("Etats-Unis") == "etats-unis" and slug(None) == ""


# --- lecteurs : le chemin exact part de la collecte ---

def test_unibet_chemin_depuis_path_et_desc():
    event = {"desc": "Paris SG vs Lyon", "path": {"League": "Ligue 1 McDonalds", "Sport": "Football", "Category": "France"}}
    assert unibet.chemin_match("3388199", event) == "/paris-football/france/ligue-1-mcdonalds/3388199/paris-sg-vs-lyon"
    hockey = {"desc": "Dallas Stars vs New York Islanders",
              "path": {"League": "NHL", "Sport": "Hockey sur glace", "Category": "Amérique du Nord"}}
    assert unibet.chemin_match("3390001", hockey) == \
        "/paris-hockey-sur-glace/amerique-du-nord/nhl/3390001/dallas-stars-vs-new-york-islanders"
    assert unibet.chemin_match("3388199", {"desc": "x", "path": {"Sport": "Football"}}) is None
    assert unibet.chemin_match("abc", event) is None


def test_olybet_chemin_depuis_region_et_competition():
    doc = {"data": {"data": {"sport": {"3": {"alias": "Basketball", "region": {"50003": {
        "alias": "North America", "competition": {"756": {"id": 756, "name": "NBA", "game": {
            "31196570": {"id": 31196570, "team1_name": "Philadelphia 76ers", "team2_name": "Detroit Pistons"}}}}}}}}}}}
    (jeu,) = olybet.jeux_depuis(doc)
    assert jeu["league"] == "NBA" and jeu["chemin"] == "/sportsbook/pre-match/match/Basketball/North%20America/756/31196570"
    # ancienne forme de réponse (sans région) : matchs lus, pas de chemin inventé
    ancien = {"data": {"data": {"sport": {"1": {"alias": "Soccer", "competition": {"548": {"name": "Ligue 1", "game": {
        "1": {"id": 1, "team1_name": "A", "team2_name": "B"}}}}}}}}}
    (jeu,) = olybet.jeux_depuis(ancien)
    assert jeu["league"] == "Ligue 1" and jeu["chemin"] is None
    assert olybet.chemin_match("Soccer", "", 548, 1) is None and olybet.chemin_match("Soccer", "France", "x", 1) is None


def test_identifiant_entier_dans_le_chemin_releve():
    # « 1 » n'est pas dans « 31196570 » : chemin d'un autre match, repli annoncé
    assert lien_info(pari("Unibet", "unibet-fr|1", lien="/paris-football/france/l1/31196570/a-vs-b"))[1]
    assert lien_info(pari("Unibet", "unibet-fr|3388199", lien="/paris-football/france/l1/3388199/a-vs-b"))[1] is False
