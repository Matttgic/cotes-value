"""Polymarket : un carnet sans prix est sauté sans alerte ; un prix incohérent reste une erreur de données."""
from cotes import polymarket as pm


def marche(**prix):
    return {"sportsMarketType": "moneyline", "acceptingOrders": True, "closed": False, "outcomes": '["A","B"]',
            "liquidityNum": 500, "id": "1", **prix}


def erreurs(m):
    pm.ERREURS.clear()
    pm._lignes([m], {"collecte": "2026-10-25T16:00:00+00:00"}, "A", "B", "football")
    return list(pm.ERREURS)


def test_carnet_vide_ou_a_sens_unique_est_saute_sans_erreur():
    assert erreurs(marche()) == []
    assert erreurs(marche(bestBid=0.4)) == []
    assert erreurs(marche(bestAsk=0.5)) == []
    assert erreurs(marche(bestBid=None, bestAsk=None)) == []
    assert erreurs(marche(bestBid=0.4, bestAsk=1.0)) == []      # côté vendeur vide, noté 1
    assert erreurs(marche(bestBid=0, bestAsk=0.3)) == []        # côté acheteur vide, noté 0


def test_prix_incoherents_restent_une_erreur():
    assert erreurs(marche(bestBid=0.6, bestAsk=0.5)) == ["prix bid/ask invalides"]
    assert erreurs(marche(bestBid=0.4, bestAsk=1.2)) == ["prix bid/ask invalides"]
    assert erreurs(marche(bestBid=0.7, bestAsk=1)) == []         # le seul cas sauté : côté vide noté 0 ou 1
    assert erreurs(marche(bestBid=-0.1, bestAsk=0.5)) == ["prix bid/ask invalides"]
    assert erreurs(marche(bestBid="n/a", bestAsk=0.5)) == ["prix bid/ask invalides"]


def lignes(t, outcomes, **champs):
    pm.ERREURS.clear()
    m = {"sportsMarketType": t, "acceptingOrders": True, "closed": False, "outcomes": outcomes,
         "liquidityNum": 500, "id": "9", "bestBid": 0.48, "bestAsk": 0.50, **champs}
    return pm._lignes([m], {"collecte": "2026-11-08T10:00:00+00:00", "debut": "2026-11-08T18:00:00+00:00"},
                      "Bengals", "Falcons", "football_americain")


def test_nouveaux_marches_lus():
    h = lignes("first_half_spreads", '["Bengals", "Falcons"]', line=-2.5)
    assert {(l["marche"], l["periode"], l["ligne"], l["issue"]) for l in h} == {
        ("HANDICAP", "MT1", -2.5, "DOM"), ("HANDICAP", "MT1", -2.5, "EXT")}
    assert {l["periode"] for l in lignes("q1_spreads", '["Falcons", "Bengals"]', line=-3.5)} == {"QT1"}
    assert lignes("second_half_spreads", '["Bengals", "Falcons"]', line=-1.5) == []     # prolongation ambiguë
    sets = lignes("tennis_set_totals", '["Over 2.5", "Under 2.5"]', line=2.5)
    assert {(l["marche"], l["issue"]) for l in sets} == {("SETS_TOTAL", "PLUS"), ("SETS_TOTAL", "MOINS")}


def test_total_par_equipe_nom_avant_ou_apres_les_deux_points():
    avant = lignes("team_totals", '["Over", "Under"]', line=10.5, question="Bengals Team Total: O/U 10.5",
                   groupItemTitle="Bengals O/U 10.5")
    assert {l["marche"] for l in avant} == {"TOTAL_DOM"}
    apres = lignes("team_totals", '["Over", "Under"]', line=1.5, question="Bengals vs. Falcons: Falcons O/U 1.5")
    assert {l["marche"] for l in apres} == {"TOTAL_EXT"}
    assert lignes("team_totals", '["Over", "Under"]', line=1.5, question="Bengals vs. Falcons: O/U 1.5") == []


def test_carnet_large_lu_au_prix_d_achat_hors_consensus():
    from cotes.comparaison import _lisible
    serre = {"marche": "TOTAL", "proba_juste": 0.5, "achat": 0.49, "ecart_achat_vente": 0.02, "liquidite": 500}
    large = {**serre, "achat": 0.46, "ecart_achat_vente": 0.08}
    trop = {**serre, "achat": 0.40, "ecart_achat_vente": 0.20}
    assert _lisible("Polymarket", serre) is serre
    prudent = _lisible("Polymarket", large)
    assert prudent["prix_prudent"] and prudent["proba_juste"] == 0.46 and prudent["proba_milieu"] == 0.5
    assert _lisible("Polymarket", trop) is None
    assert _lisible("Smarkets", large) is None                                   # Polymarket seulement
    assert _lisible("Polymarket", {**large, "marche": "RESULTAT_1N2"}) is None   # trois issues : non
