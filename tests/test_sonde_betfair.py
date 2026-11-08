"""Lecture des réponses par la sonde Betfair (réponses écrites à la main, au format attendu du site)."""
from scripts import sonde_betfair as S


def test_pays_lu_dans_la_trace():
    assert S.pays("fl=1\nip=x\nloc=DE\ntls=TLSv1.3\n") == "DE"
    assert S.pays("<html>refus</html>") is None


def test_cles_ak_sans_doublon():
    texte = '{"appKey":"abcdEFGH12345678"} src="x.js?_ak=abcdEFGH12345678" &_ak=ZZZZyyyy00001111'
    assert S.cles_ak(texte) == ["abcdEFGH12345678", "ZZZZyyyy00001111"]
    assert S.cles_ak("aucune clé") == []


def test_corps_recherche_borne_et_sport():
    corps = S.corps_recherche(2, 7)
    assert corps["filter"]["eventTypeIds"] == [2]
    assert corps["facets"][0]["maxValues"] == 7


def test_marches_depuis_attachments():
    rep = {"attachments": {
        "markets": {"1.234567890": {"marketId": "1.234567890", "marketName": "Match Odds", "eventId": 42,
                                    "marketTime": "2026-11-08T15:00:00.000Z"}},
        "events": {"42": {"name": "Lens v Lille", "openDate": "2026-11-08T15:00:00.000Z"}}}}
    assert S.marches_trouves(rep, "") == [{"id": "1.234567890", "nom": "Match Odds", "evenement": "Lens v Lille",
                                           "debut": "2026-11-08T15:00:00.000Z"}]


def test_marches_de_secours_par_identifiant():
    texte = '{"x":["1.234567890","1.234567890","1.98765432"]}'
    assert [m["id"] for m in S.marches_trouves({"x": []}, texte)] == ["1.234567890", "1.98765432"]
    assert S.marches_trouves(None, "") == []


def test_cotes_lues_meilleurs_prix():
    rep = {"eventTypes": [{"eventTypeId": 1, "eventNodes": [{
        "event": {"eventName": "Lens v Lille"},
        "marketNodes": [{"marketId": "1.234567890", "state": {"status": "OPEN", "inplay": False}, "runners": [
            {"selectionId": 1, "description": {"runnerName": "Lens"},
             "exchange": {"availableToBack": [{"price": 2.1, "size": 150.0}, {"price": 2.08, "size": 20.0}],
                          "availableToLay": [{"price": 2.14, "size": 80.0}]}},
            {"selectionId": 2, "exchange": {}},
        ]}]}]}]}
    lignes = S.cotes_lues(rep)
    assert lignes[0] == {"marche": "1.234567890", "evenement": "Lens v Lille", "etat": "OPEN", "en_direct": False,
                         "issue": "Lens", "back": 2.1, "back_eur": 150.0, "lay": 2.14, "lay_eur": 80.0}
    assert lignes[1]["issue"] == 2 and lignes[1]["back"] is None
    assert S.cotes_lues(None) == [] and S.cotes_lues({"eventTypes": None}) == []
