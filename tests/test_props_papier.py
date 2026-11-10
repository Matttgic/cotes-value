"""Paris fictifs props : seuil, unicité, clôture, feuille ESPN, bilan. Aucun réseau."""
from datetime import datetime, timedelta, timezone

from cotes import props_papier as P

NOW = datetime(2026, 11, 9, 18, tzinfo=timezone.utc)
DEBUT = "2026-11-10T01:00:00+00:00"


def ligne(**k):
    base = {
        "bookmaker": "Winamax", "sport": "basket", "ligue": "NBA", "match_id": "winamax|8",
        "match_id_reference": "pin-1", "domicile": "Los Angeles Lakers", "exterieur": "Boston Celtics",
        "debut": DEBUT, "joueur": "L. James", "marche": "JOUEUR:Points", "periode": "MATCH",
        "ligne": 25.5, "issue": "PLUS", "cote": 2.10, "reference": "Pinnacle",
        "cote_juste": 1.92, "proba_juste": 0.52, "ecart": 0.092,
        "detecte": "2026-11-09T18:00:00+00:00", "pariable": False,
    }
    base.update(k)
    return base


def test_seuil_par_defaut_et_variable(monkeypatch):
    monkeypatch.delenv("PROPS_ECART_MIN", raising=False)
    assert P.seuil() == 0.02
    monkeypatch.setenv("PROPS_ECART_MIN", "0.04")
    assert P.seuil() == 0.04
    monkeypatch.setenv("PROPS_ECART_MIN", "non")
    assert P.seuil() == 0.02


def test_premiere_detection_sans_doublon_et_meilleure_cote_notee():
    doc = {"paris": []}
    assert P.enregistrer(doc, [ligne(), ligne(bookmaker="Unibet", match_id="unibet|1", ecart=0.01)], NOW) == 1
    assert P.enregistrer(doc, [ligne(cote=2.40, ecart=0.25, detecte="2026-11-09T19:00:00+00:00")], NOW) == 0
    assert len(doc["paris"]) == 1
    assert doc["paris"][0]["cote"] == 2.10 and doc["paris"][0]["cote_max"] == 2.40
    assert doc["paris"][0]["pariable"] is False
    assert all(s["actif"] is False for s in P.STRATEGIES)


def test_hors_nba_nhl_et_sous_le_seuil_ignores():
    doc = {"paris": []}
    assert P.enregistrer(doc, [ligne(ligue="Euroleague"), ligne(ecart=0.015),
                               ligne(reference="Unibet", bookmaker="Winamax")], NOW) == 0


def test_cloture_avant_le_coup_et_clv_a_trente_minutes():
    doc = {"paris": []}
    P.enregistrer(doc, [ligne()], NOW)
    pin = {"source": "pinnacle", "match_id": "pin-1", "marche": "JOUEUR:Points", "ligne": 25.5,
           "issue": "PLUS", "joueur": "LeBron James", "proba_juste": 0.55, "cote_perimee": False,
           "collecte": "2026-11-10T00:40:00+00:00"}
    assert P.clotures(doc, [pin], NOW) == 1
    assert P.clotures(doc, [pin], NOW) == 0
    assert doc["paris"][0]["clv"] == round(2.10 * 0.55 - 1, 4)
    assert P.clv_comptable({**doc["paris"][0], "statut": "gagne"}) == doc["paris"][0]["clv"]
    vieux = {**doc["paris"][0], "statut": "gagne", "cloture_lue": "2026-11-09T20:00:00+00:00"}
    assert P.clv_comptable(vieux) is None
    apres = {**pin, "collecte": "2026-11-10T01:05:00+00:00"}
    assert P.clotures(doc, [apres], datetime(2026, 11, 10, 1, 6, tzinfo=timezone.utc)) == 0


def _feuille():
    return {"boxscore": {"players": [{"team": {"displayName": "Los Angeles Lakers"}, "statistics": [{
        "names": ["MIN", "PTS", "FG", "3PT", "FT", "REB", "AST"],
        "athletes": [
            {"athlete": {"displayName": "LeBron James", "shortName": "L. James"},
             "didNotPlay": False, "stats": ["33", "28", "10-18", "2-5", "6-6", "7", "8"]},
            {"athlete": {"displayName": "Austin Reaves"}, "didNotPlay": True, "stats": [], "reason": "DNP"},
        ],
    }]}]}}


def test_reglement_gagne_pousse_dnp_et_nom():
    doc = {"paris": []}
    P.enregistrer(doc, [
        ligne(),
        ligne(issue="MOINS", ecart=0.05, cote=1.8),
        ligne(joueur="Austin Reaves", ligne=12.5, ecart=0.04),
        ligne(ligne=28, issue="PLUS", ecart=0.03, cote=1.9),
    ], NOW)
    matchs = [{"sport": "basket", "domicile": "Los Angeles Lakers", "exterieur": "Boston Celtics",
               "debut": DEBUT, "espn_id": "99", "final": True}]
    feuilles = {"99": P.joueurs_feuille(_feuille())}
    assert P.regler(doc, matchs, feuilles, datetime(2026, 11, 10, 4, tzinfo=timezone.utc)) == 4
    par = {p["issue"] + str(p["ligne"]) + p["joueur"]: p for p in doc["paris"]}
    assert par["PLUS25.5L. James"]["statut"] == "gagne" and par["PLUS25.5L. James"]["gain"] == 11.0
    assert par["MOINS25.5L. James"]["statut"] == "perdu"
    assert par["PLUS12.5Austin Reaves"]["statut"] == "annule" and par["PLUS12.5Austin Reaves"]["reglement"] == "DNP"
    assert par["PLUS28L. James"]["statut"] == "annule" and par["PLUS28L. James"]["reglement"] == "pousse"
    b = P.bilan(doc)
    assert b["total"]["regles"] == 2 and b["total"]["gagnes"] == 1
    assert b["references"]["Pinnacle"]["n"] == 4
    assert b["stats"]["Points · NBA"]["regles"] == 2
    assert all(s["actif"] is False for s in b["strategies"])


def test_feuille_nhl_points_et_tirs():
    summary = {"boxscore": {"players": [{"statistics": [
        {"names": ["G", "A", "SOG"], "athletes": [
            {"athlete": {"displayName": "Connor McDavid"}, "didNotPlay": False, "stats": ["1", "2", "4"]}]},
        {"names": ["G", "A", "SOG"], "athletes": [
            {"athlete": {"displayName": "Leon Draisaitl"}, "didNotPlay": False, "stats": ["0", "1", "3"]}]},
        {"names": ["SV"], "athletes": [
            {"athlete": {"displayName": "Stuart Skinner"}, "didNotPlay": False, "stats": ["27"]}]},
    ]}]}}
    joueurs = {j["nom"]: j for j in P.joueurs_feuille(summary)}
    assert P._valeur(joueurs["Connor McDavid"], "hockey", "Points") == 3
    assert P._valeur(joueurs["Connor McDavid"], "hockey", "ShotsOnGoal") == 4
    assert P._valeur(joueurs["Stuart Skinner"], "hockey", "Saves") == 27


def test_polymarket_absent_de_la_collecte():
    verdict = P.verdict_polymarket([{"marche": "VAINQUEUR", "liquidite": 500}])
    assert verdict["present"] is False and verdict["utilise"] is False and verdict["liquides"] == 0


def test_feuilles_plafonnees_et_sans_reseau():
    appels = []

    def lire(chemin, params):
        appels.append((chemin, params["event"]))
        return _feuille()

    doc = {"paris": []}
    P.enregistrer(doc, [ligne()], NOW)
    matchs = [{"sport": "basket", "domicile": "Los Angeles Lakers", "exterieur": "Boston Celtics",
               "debut": DEBUT, "espn_id": "99", "final": True}]
    ids = P.feuilles_a_lire(doc, matchs, datetime(2026, 11, 10, 4, tzinfo=timezone.utc))
    feuilles = P.charger_feuilles([(i, "basket") for i in ids], lire)
    assert appels == [("basketball/nba/summary", "99")]
    assert P.regler(doc, matchs, feuilles, datetime(2026, 11, 10, 4, tzinfo=timezone.utc)) == 1
