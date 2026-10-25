"""Winamax : lecture bornée, résultats partiels gardés, connexion abandonnée vite (diagnostic du 23-25/10/2026)."""
import json
import socket
import time
import types

from curl_cffi import CurlECode, CurlError, CurlWsFlag

from cotes.delai import Echeance
from cotes.direct import winamax
from tests.test_winamax_direct import FIXTURE, MAINTENANT, _sport_avec_marches


def _trame(texte, flags=CurlWsFlag.TEXT, bytesleft=0):
    return texte.encode(), types.SimpleNamespace(flags=flags, bytesleft=bytesleft)


class FauxCurl:
    """WebSocket curl_cffi simulé, fragment par fragment ; file vide = silence (AGAIN), comme le vrai."""

    def __init__(self, routes=None):
        self.a, self.b = socket.socketpair()
        self.curl = types.SimpleNamespace(getinfo=lambda info: self.a.fileno())
        self.file = [_trame("0{}")]
        self.routes = routes or {}

    def recv_fragment(self):
        if not self.file:
            raise CurlError("again", CurlECode.AGAIN)
        return self.file.pop(0)

    def send_str(self, m):
        if m == "40":
            self.file.append(_trame("40{}"))
        elif m.startswith("42"):
            corps = json.loads(m[2:])[1]
            doc = self.routes.get(corps["route"])
            if doc is not None:                     # route absente : le serveur ne répond jamais
                self.file.append(_trame("42" + json.dumps(["m", {**doc, "requestId": corps["requestId"]}])))

    def close(self):
        self.a.close()
        self.b.close()


def test_recevoir_assemble_les_fragments_et_ignore_les_pings():
    ws = FauxCurl()
    ws.file = [_trame("", CurlWsFlag.PING), _trame('42["m",', CurlWsFlag.TEXT | CurlWsFlag.CONT, 3),
               _trame('{}]')]                                        # dernier fragment : sans CONT
    assert winamax._recevoir(ws, time.monotonic() + 1) == '42["m",{}]'
    ws.close()


def test_recevoir_s_arrete_a_l_echeance_au_lieu_d_attendre_sans_fin():
    ws = FauxCurl()
    ws.file = []
    t = time.monotonic()
    try:
        winamax._recevoir(ws, t + 0.3)
        assert False, "aurait dû expirer"
    except TimeoutError as e:
        assert e.args == ("délai",)
    assert 0.25 <= time.monotonic() - t < 1.5
    ws.close()


def test_trame_de_fermeture_signalee():
    ws = FauxCurl()
    ws.file = [_trame("", CurlWsFlag.CLOSE)]
    try:
        winamax._recevoir(ws, time.monotonic() + 1)
        assert False
    except OSError as e:
        assert winamax._cause(e) == "fermeture"
    ws.close()


def test_reponse_perdue_le_deja_lu_est_rendu_avant_le_budget(monkeypatch):
    monkeypatch.setattr(winamax, "FILTRES", {})
    monkeypatch.setattr(winamax.time, "sleep", lambda s: None)
    ws = FauxCurl({"sport:1": _sport_avec_marches()})          # sport:5 (tennis) ne répond jamais
    client = winamax.Socket(pause=(0, 0), connecter=lambda: ws)
    t = time.monotonic()
    lignes, meta = winamax.collecter({"football", "tennis"}, 36, transport=client,
                                     maintenant=MAINTENANT, echeance=Echeance(4.5))
    assert time.monotonic() - t < 4.5 - 1                      # rendu avant que le cycle ne tue la lecture
    assert lignes and {l["sport"] for l in lignes} == {"football"}
    assert "sport:5 : réseau (délai)" in meta["erreurs"]
    ws.close()


def test_connexion_refusee_abandonnee_apres_trois_ouvertures(monkeypatch):
    pauses = []
    monkeypatch.setattr(winamax.time, "sleep", lambda s: pauses.append(s))
    essais = []

    class Refus(Exception):
        code = 22

    def connecter():
        essais.append(1)
        raise Refus()

    client = winamax.Socket(pause=(0, 0), connecter=connecter)
    lignes, meta = winamax.collecter(None, 36, transport=client, maintenant=MAINTENANT, echeance=Echeance(45))
    assert len(essais) == winamax.OUVERTURES_MAX == 3          # et non 10 sports × 3 essais
    assert client.hors_service and lignes == [] and meta["ok"] is False
    assert "connexion impossible (Refus 22)" in meta["erreurs"]
    assert [p for p in pauses if p >= 1] == [1.0, 2.0]          # attente croissante entre les ouvertures


def test_une_coupure_isolee_ne_met_pas_hors_service(monkeypatch):
    monkeypatch.setattr(winamax.time, "sleep", lambda s: None)
    n = {"ouvertures": 0}

    def connecter():
        n["ouvertures"] += 1
        if n["ouvertures"] == 1:
            raise OSError("ouverture")
        return FauxCurl({"sport:1": {"matches": {}}})

    client = winamax.Socket(pause=(0, 0), connecter=connecter)
    assert client.demander("sport:1") == {"matches": {}, "requestId": "w0"}
    assert not client.hors_service and client.erreurs == []


def test_pas_de_demande_sans_la_marge_de_budget():
    client = winamax.Socket(pause=(0, 0), connecter=lambda: FauxCurl({"sport:1": {"matches": {}}}))
    client.echeance = Echeance(winamax.MARGE_S)
    assert client.demander("sport:1") is None and client.erreurs == ["budget"]


def test_fixture_toujours_lue_par_le_vrai_assemblage(monkeypatch):
    monkeypatch.setattr(winamax, "FILTRES", {})
    monkeypatch.setattr(winamax.time, "sleep", lambda s: None)
    ws = FauxCurl({"sport:1": {"matches": FIXTURE["sport:1"]["matches"], **{k: FIXTURE["match:100"][k]
                                                                           for k in ("bets", "outcomes", "odds")}}})
    lignes, meta = winamax.collecter({"football"}, 36, transport=winamax.Socket(pause=(0, 0), connecter=lambda: ws),
                                     maintenant=MAINTENANT)
    assert meta["ok"] and lignes
    ws.close()
