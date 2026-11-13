"""Libellés relevés par cotes/inconnus.py le 13/11/2026 et désormais traduits."""
from cotes.direct import betclic, netbet, unibet
from cotes.pulsescore import traduire


def test_unibet_les_2_equipes_marquent():
    assert unibet._canon("Les 2 équipes marquent", "") == "BOTH_TEAMS_TO_SCORE"
    assert unibet._canon("Les 2 équipes marqueront", "") == "BOTH_TEAMS_TO_SCORE"
    assert unibet._canon("Les 2 équipes marquent au moins 2 buts", "") is None


def test_betclic_total_prolongations_et_set():
    assert betclic._classe("Nombre total de buts (prolongations et penaltys inclus)", "A", "B") == "OVER_UNDER"
    assert betclic._classe("1er Set - Vainqueur du Set", "A", "B") == "MATCH_RESULT"
    assert betclic._classe("Penalty dans le match", "A", "B") is None


def _netbet(label):
    m = netbet.marche_depuis({"order": "x", "selection_order_type": "2ways", "bets": [
        {"label": label, "selections": [{"label": "Lyon", "odds": 1.8}, {"label": "Nice", "odds": 2.0}]}]}, "Lyon", "Nice")
    if m is None:
        return None
    ev = {"eventId": "1", "home": "Lyon", "away": "Nice", "startTime": "2026-11-14T18:00:00Z", "markets": [m]}
    return {(l["marche"], l["periode"]) for l in traduire(ev, "netbet", "hockey", "2026-11-13T00:00:00Z")}


def test_netbet_vainqueur_et_set():
    assert _netbet("Qui va gagner le match ? (prolongations incluses)") == {("VAINQUEUR", "MATCH")}
    assert _netbet("Set 2 - Qui va gagner le set ?") == {("VAINQUEUR", "SET2")}
    assert _netbet("Qui va gagner le combat ? (remboursé si match nul)") is None
