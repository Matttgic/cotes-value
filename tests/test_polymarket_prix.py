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


def test_prix_incoherents_restent_une_erreur():
    assert erreurs(marche(bestBid=0.6, bestAsk=0.5)) == ["prix bid/ask invalides"]
    assert erreurs(marche(bestBid=0.4, bestAsk=1.0)) == ["prix bid/ask invalides"]
    assert erreurs(marche(bestBid="n/a", bestAsk=0.5)) == ["prix bid/ask invalides"]
