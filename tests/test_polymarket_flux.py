import json
from datetime import datetime, timedelta, timezone

from cotes import polymarket, polymarket_flux as pf

T = datetime(2026, 11, 13, 12, tzinfo=timezone.utc)


def test_carnet_image_puis_variations():
    c = pf.Carnets()
    c.appliquer({"event_type": "book", "asset_id": "A", "bids": [{"price": "0.40", "size": "10"}, {"price": "0.42", "size": "5"}],
                 "asks": [{"price": "0.45", "size": "3"}]}, T)
    assert c.meilleurs()["A"][:2] == [0.42, 0.45]
    # format actuel : price_changes[]
    c.appliquer({"event_type": "price_change", "price_changes": [{"asset_id": "A", "side": "BUY", "price": "0.42", "size": "0"},
                                                                 {"asset_id": "A", "side": "SELL", "price": "0.44", "size": "2"}]}, T)
    assert c.meilleurs()["A"][:2] == [0.40, 0.44]
    # ancien format : asset_id + changes[] ; liste de messages
    c.appliquer([{"event_type": "price_change", "asset_id": "A", "changes": [{"side": "BUY", "price": "0.43", "size": "1"}]}], T)
    assert c.meilleurs()["A"][:2] == [0.43, 0.44]


def test_carnet_un_seul_cote_ou_incoherent_ignore():
    c = pf.Carnets()
    c.appliquer({"event_type": "book", "asset_id": "B", "bids": [{"price": "0.5", "size": "1"}], "asks": []}, T)
    c.appliquer({"event_type": "book", "asset_id": "C", "bids": [{"price": "0.6", "size": "1"}],
                 "asks": [{"price": "0.5", "size": "1"}]}, T)
    c.appliquer({"event_type": "last_trade_price", "asset_id": "B"}, T)
    assert c.meilleurs() == {}


def test_prix_frais_selon_age_du_fichier(tmp_path):
    (tmp_path / pf.PRIX).write_text(json.dumps({"maj": T.isoformat(), "prix": {"A": [0.4, 0.45, T.isoformat()]}}))
    assert pf.prix_frais(tmp_path, T + timedelta(seconds=10))["A"] == (0.4, 0.45, T)
    assert pf.prix_frais(tmp_path, T + timedelta(seconds=pf.AGE_MAX_S + 1)) == {}
    assert pf.prix_frais(tmp_path / "absent", T) == {}


class FauxWs:
    def __init__(self, messages, arret):
        self.messages, self.envoyes, self.arret = list(messages), [], arret

    def send_str(self, s):
        self.envoyes.append(s)

    def recv(self, timeout=None):
        if not self.messages:
            self.arret["fin"] = True
            raise TimeoutError("timed out")
        return self.messages.pop(0).encode(), 0

    def close(self):
        pass


def test_session_abonne_et_ecrit(tmp_path, monkeypatch):
    monkeypatch.setattr(pf, "ECRITURE_S", 0.0)
    (tmp_path / pf.JETONS).write_text(json.dumps(["A"]))
    arret = {"fin": False}
    book = {"event_type": "book", "asset_id": "A", "bids": [{"price": "0.3", "size": "1"}], "asks": [{"price": "0.32", "size": "1"}]}
    ws = FauxWs([json.dumps([book]), "PONG"], arret)
    pf._session(tmp_path, ["A"], lambda url: ws, lambda: arret["fin"])
    assert json.loads(ws.envoyes[0]) == {"type": "market", "assets_ids": ["A"]}
    prix = json.loads((tmp_path / pf.PRIX).read_text())["prix"]
    assert prix["A"][:2] == [0.3, 0.32]


def test_boucle_reconnecte_apres_coupure(tmp_path):
    (tmp_path / pf.JETONS).write_text(json.dumps(["A"]))
    essais, attentes = [], []

    def connecter(url):
        essais.append(url)
        raise ConnectionError("refus")
    pf.boucle(tmp_path, connecter, arret=lambda: len(essais) >= 3, attendre=attentes.append)
    assert len(essais) == 3 and attentes == [2.0, 4.0]


def _marche(bid, ask, recu):
    return {"id": "m1", "sportsMarketType": "moneyline", "acceptingOrders": True, "closed": False,
            "bestBid": bid, "bestAsk": ask, "outcomes": '["Lyon", "Nice"]', "clobTokenIds": '["J1", "J2"]',
            "liquidityNum": 1000, "_collecte_recue": recu}


def test_lignes_prennent_le_flux_plus_recent(monkeypatch):
    base = {"source": "polymarket", "sport": "basket", "match_id": "e1", "domicile": "Lyon", "exterieur": "Nice",
            "debut": (T + timedelta(hours=3)).isoformat(), "collecte": T.isoformat()}
    flux_t = T + timedelta(seconds=40)
    monkeypatch.setattr(polymarket, "_flux", {"J1": (0.60, 0.62, flux_t)})
    jetons = []
    lignes = polymarket._lignes([_marche(0.50, 0.52, T.isoformat())], base, "Lyon", "Nice", "basket", jetons)
    dom = next(l for l in lignes if l["issue"] == "DOM")
    assert jetons == ["J1"] and dom["proba_juste"] == 0.61 and dom.get("prix_flux")
    assert dom["collecte"] == flux_t.isoformat(timespec="seconds")
    # flux plus ancien que gamma : gamma garde la main
    monkeypatch.setattr(polymarket, "_flux", {"J1": (0.60, 0.62, T - timedelta(seconds=5))})
    dom = next(l for l in polymarket._lignes([_marche(0.50, 0.52, T.isoformat())], base, "Lyon", "Nice", "basket")
               if l["issue"] == "DOM")
    assert dom["proba_juste"] == 0.51 and not dom.get("prix_flux")
