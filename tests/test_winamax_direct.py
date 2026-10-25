"""Winamax via socket.io : fixtures enregistrées, aucun appel réseau."""
import json
from datetime import datetime, timezone
from pathlib import Path

from cotes.direct import winamax

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "winamax_socket.json").read_text())
MAINTENANT = datetime(2026, 10, 18, 12, tzinfo=timezone.utc)


class Memoire:
    def __init__(self, routes):
        self.routes = routes
        self.demandes = []
        self.requetes = 0
        self.erreurs = []

    def _noter(self, message):
        if message not in self.erreurs:
            self.erreurs.append(message)

    def demander(self, route, filtre=None):
        self.demandes.append((route, filtre))
        self.requetes += 1
        if filtre is None:
            return self.routes.get(route)
        return self.routes.get((route, filtre))


def _sport_avec_marches():
    detail = FIXTURE["match:100"]
    return {"matches": FIXTURE["sport:1"]["matches"], "bets": detail["bets"],
            "outcomes": detail["outcomes"], "odds": detail["odds"]}


def test_fixture_traduit_les_marches_connus_et_ecarte_le_reste(monkeypatch):
    monkeypatch.setattr(winamax, "FILTRES", {})
    transport = Memoire({"sport:1": _sport_avec_marches()})
    lignes, meta = winamax.collecter({"football"}, 36, transport=transport, maintenant=MAINTENANT)
    assert meta["ok"] and meta["matchs"] == 1 and meta["requetes"] == 1
    assert transport.demandes == [("sport:1", None)]
    assert all(l["bookmaker"] == "winamax" and l["source"] == "Winamax" for l in lignes)
    cles = {(l["marche"], l["periode"], l["issue"], l["ligne"]) for l in lignes}
    assert ("RESULTAT_1N2", "MATCH", "DOM", None) in cles
    assert ("RESULTAT_1N2", "MATCH", "NUL", None) in cles
    assert ("TOTAL", "MATCH", "PLUS", 2.5) in cles
    assert ("TOTAL_DOM", "MATCH", "PLUS", 0.5) in cles
    assert ("HANDICAP", "MATCH", "DOM", -0.5) in cles
    assert ("HANDICAP", "MATCH", "EXT", -0.5) in cles
    assert ("HANDICAP_3", "MATCH", "NUL", -1.0) in cles
    assert ("BOTH_TEAMS_TO_SCORE", "MATCH", "YES", None) in cles
    assert ("DOUBLE_CHANCE", "MATCH", "HOME_DRAW", None) in cles
    assert ("DRAW_NO_BET", "MATCH", "EXT", None) in cles
    assert ("CORRECT_SCORE", "MATCH", "1-0", None) in cles
    assert ("HALF_TIME_FULL_TIME", "MATCH", "DOM/DOM", None) in cles
    assert ("RESULTAT_1N2", "MT1", "DOM", None) in cles
    assert not any("corner" in (l.get("libelle") or "").lower() for l in lignes)
    assert not any("pair" in (l.get("libelle") or "").lower() for l in lignes)
    domicile = next(l for l in lignes if l["marche"] == "RESULTAT_1N2" and l["issue"] == "DOM"
                    and l["periode"] == "MATCH")
    assert domicile["cote"] == 2.1 and domicile["sport"] == "football"


def test_tennis_separe_sets_et_jeux():
    match = {"matchId": 5, "status": "PREMATCH", "competitor1Name": "Rune",
             "competitor2Name": "Collignon", "matchStart": 1792346400}
    detail = {
        "bets": {
            "a": {"betId": 1, "matchId": 5, "marketId": 186, "betTitle": "Vainqueur",
                  "available": True, "outcomes": [1, 2]},
            "b": {"betId": 2, "matchId": 5, "marketId": 189, "betTitle": "Nombre de jeux",
                  "specialBetValue": "total=22.5", "available": True, "outcomes": [3, 4]},
            "c": {"betId": 3, "matchId": 5, "marketId": 314, "betTitle": "Nombre de sets",
                  "specialBetValue": "total=2.5", "available": True, "outcomes": [5, 6]},
            "d": {"betId": 4, "matchId": 5, "marketId": 187, "betTitle": "Écart de jeux",
                  "specialBetValue": "hcp=-1.5", "available": True, "outcomes": [7, 8]},
            "e": {"betId": 5, "matchId": 5, "marketId": 202, "betTitle": "1er set - Vainqueur",
                  "specialBetValue": "setnr=1", "available": True, "outcomes": [9, 10]},
        },
        "outcomes": {
            "1": {"label": "Rune", "code": "1", "available": True},
            "2": {"label": "Collignon", "code": "2", "available": True},
            "3": {"label": "Plus de 22,5", "code": "over", "available": True},
            "4": {"label": "Moins de 22,5", "code": "under", "available": True},
            "5": {"label": "Plus de 2,5", "code": "over", "available": True},
            "6": {"label": "Moins de 2,5", "code": "under", "available": True},
            "7": {"label": "Rune -1.5", "code": "yes", "available": True},
            "8": {"label": "Collignon +1.5", "code": "no", "available": True},
            "9": {"label": "Rune", "code": "1", "available": True},
            "10": {"label": "Collignon", "code": "2", "available": True},
        },
        "odds": {str(i): 1.8 for i in range(1, 11)},
    }
    transport = Memoire({"sport:5": {"matches": {"5": match}, **detail}})
    lignes, meta = winamax.collecter({"tennis"}, 36, transport=transport, maintenant=MAINTENANT)
    assert meta["matchs"] == 1
    cles = {(l["marche"], l["periode"], l["issue"], l["ligne"]) for l in lignes}
    assert ("VAINQUEUR", "MATCH", "DOM", None) in cles
    assert ("JEUX_TOTAL", "MATCH", "PLUS", 22.5) in cles
    assert ("SETS_TOTAL", "MATCH", "PLUS", 2.5) in cles
    assert ("JEUX_HANDICAP", "MATCH", "DOM", -1.5) in cles
    assert ("VAINQUEUR", "SET1", "EXT", None) in cles


def test_pause_entre_les_routes(monkeypatch):
    pauses = []
    monkeypatch.setattr(winamax.time, "sleep", lambda s: pauses.append(s))
    monkeypatch.setattr(winamax.random, "uniform", lambda a, b: 0.4)

    class Faux:
        def __init__(self):
            self.file = [
                "0{}", "40{}",
                '42["m",{"matches":{},"requestId":"w0"}]',
                '42["m",{"matches":{},"requestId":"w1"}]',
            ]
            self.envoyes = []

        def recv_str(self):
            return self.file.pop(0)

        def send_str(self, msg):
            self.envoyes.append(msg)

        def close(self):
            pass

    faux = Faux()
    client = winamax.Socket(pause=(0.35, 0.6), connecter=lambda: faux)
    assert client.demander("sport:1")["matches"] == {}
    assert client.demander("sport:5")["matches"] == {}
    assert pauses == [0.4]
    assert client.requetes == 2
    assert "42" in faux.envoyes[1]


def test_coupure_puis_reprise(monkeypatch):
    monkeypatch.setattr(winamax.time, "sleep", lambda s: None)

    class Faux:
        def __init__(self, casse):
            self.casse = casse
            self.file = ["0{}", "40{}", '42["m",{"matches":{"1":1},"requestId":"w0"}]']

        def recv_str(self):
            return self.file.pop(0)

        def send_str(self, msg):
            if self.casse and msg.startswith("42"):
                raise OSError("coupure")

        def close(self):
            pass

    etat = {"n": 0}

    def connecter():
        etat["n"] += 1
        return Faux(casse=etat["n"] == 1)

    client = winamax.Socket(pause=(0, 0), connecter=connecter)
    assert client.demander("sport:1") == {"matches": {"1": 1}, "requestId": "w0"}
    assert client.erreurs == []
    assert etat["n"] == 2


def test_erreur_reseau_sans_corps(monkeypatch):
    monkeypatch.setattr(winamax.time, "sleep", lambda s: None)

    class Faux:
        def __init__(self):
            self.file = ["0{}", "40{}"]

        def recv_str(self):
            return self.file.pop(0)

        def send_str(self, msg):
            if msg.startswith("42"):
                raise OSError("secret-ne-pas-journaliser")

        def close(self):
            pass

    client = winamax.Socket(pause=(0, 0), connecter=lambda: Faux())
    assert client.demander("match:1") is None
    assert client.erreurs == ["match:1 : réseau (OSError)"]          # la nature, jamais le message
    assert "secret" not in " ".join(client.erreurs)


def test_poussee_sans_identifiant_est_ignoree(monkeypatch):
    monkeypatch.setattr(winamax.time, "sleep", lambda s: None)

    class Faux:
        def __init__(self):
            self.file = [
                "0{}", "40{}",
                '42["m",{"matches":{"9":1}}]',
                '42["m",{"matches":{"1":1},"requestId":"w0"}]',
            ]

        def recv_str(self):
            return self.file.pop(0)

        def send_str(self, msg):
            pass

        def close(self):
            pass

    client = winamax.Socket(pause=(0, 0), connecter=lambda: Faux())
    assert client.demander("sport:1") == {"matches": {"1": 1}, "requestId": "w0"}


def test_filtre_ajoute_les_marches_du_sport(monkeypatch):
    monkeypatch.setattr(winamax, "FILTRES", {"football": (6,)})
    match = FIXTURE["sport:1"]["matches"]["100"]
    detail = FIXTURE["match:100"]
    transport = Memoire({
        "sport:1": {"matches": {"100": match}},
        ("sport:1", 6): {"bets": detail["bets"], "outcomes": detail["outcomes"], "odds": detail["odds"]},
    })
    lignes, meta = winamax.collecter({"football"}, 36, transport=transport, maintenant=MAINTENANT)
    assert transport.demandes == [("sport:1", None), ("sport:1", 6)]
    assert meta["ok"] and meta["matchs"] == 1
    assert any(l["marche"] == "TOTAL" and l["ligne"] == 2.5 for l in lignes)


def test_lecture_vide_est_un_echec():
    transport = Memoire({"sport:1": {"matches": {}}})
    lignes, meta = winamax.collecter({"football"}, 36, transport=transport, maintenant=MAINTENANT)
    assert lignes == [] and meta["ok"] is False and meta["matchs"] == 0
    assert "lecture vide" in meta["erreurs"]


def test_lecture_incompletee_est_un_echec(monkeypatch):
    monkeypatch.setattr(winamax, "FILTRES", {})
    matches = {}
    bets, outcomes, odds = {}, {}, {}
    for i in range(1, 9):
        matches[str(i)] = {
            "matchId": i, "status": "PREMATCH", "competitor1Name": f"Domicile{i}",
            "competitor2Name": "Exterieur", "matchStart": 1792346400,
        }
    # Une seule cote pour huit matchs annoncés.
    bets["1"] = {"betId": 1, "matchId": 1, "marketId": 1, "betTitle": "Résultat",
                 "available": True, "outcomes": [11, 12]}
    outcomes["11"] = {"label": "Domicile1", "code": "1", "available": True}
    outcomes["12"] = {"label": "Exterieur", "code": "2", "available": True}
    odds["11"] = 1.8
    odds["12"] = 2.1
    transport = Memoire({"sport:1": {"matches": matches, "bets": bets, "outcomes": outcomes, "odds": odds}})
    lignes, meta = winamax.collecter({"football"}, 36, transport=transport, maintenant=MAINTENANT)
    assert meta["matchs"] == 8 and lignes and meta["ok"] is False
    assert "lecture incomplète" in meta["erreurs"]




def test_noms_abreges_du_tennis_reconnus_par_le_nom_de_famille():
    # 20/10/2026 : « M. Uchijima +0.5 » pour Moyuka Uchijima ; sans cela, aucun handicap de tennis.
    assert winamax._issue("no", "M. Uchijima +0.5", "Moyuka Uchijima", "Eri Shibahara", "GAME_HANDICAP") == "HOME"
    assert winamax._issue("yes", "E. Shibahara -0.5", "Moyuka Uchijima", "Eri Shibahara", "GAME_HANDICAP") == "AWAY"
    assert winamax._issue("no", "J.M. Cerundolo -1.5", "Juan Manuel Cerundolo", "Luca Nardi", "SET_HANDICAP") == "HOME"
    # nom de famille commun aux deux joueurs, ou inconnu : aucune issue plutôt qu'une mauvaise
    assert winamax._issue("no", "A. Zverev +1.5", "Alexander Zverev", "Mischa Zverev", "SET_HANDICAP") is None
    assert winamax._issue("no", "X. Inconnu +1.5", "Moyuka Uchijima", "Eri Shibahara", "SET_HANDICAP") is None


def test_tennis_et_hockey_lisent_leurs_filtres():
    # Sans filtre, la route du sport ne porte que le vainqueur (2 cotes par match).
    assert {107, 108, 116, 121, 122, 123} <= set(winamax.FILTRES["tennis"])
    assert {247, 248, 249, 253, 255} <= set(winamax.FILTRES["hockey"])


def test_filtres_handicap_et_totaux_par_equipe_lus():
    # football : handicap 44, totaux par équipe 58/59, mi-temps ; basket : handicap 208, totaux par équipe 228/229
    assert {44, 58, 59, 48, 45, 70, 71}.issubset(winamax.FILTRES["football"])
    assert {207, 208, 228, 229, 231, 237}.issubset(winamax.FILTRES["basket"])
    assert winamax.FILTRES["football"][:7] == (6, 13, 16, 56, 17, 74, 4)        # anciens d'abord
