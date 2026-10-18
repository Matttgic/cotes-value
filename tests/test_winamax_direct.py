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


def test_rapport_seuils():
    pulse = [{"bookmaker": "winamax", "match_id": "w|1", "sport": "football",
              "domicile": "Domicile", "exterieur": "Exterieur", "debut": "2026-10-18T18:00:00+00:00",
              "marche": "TOTAL", "periode": "MATCH", "ligne": 2.5, "issue": "PLUS", "cote": 1.9}]
    direct = [{"bookmaker": "winamax", "match_id": "winamax|100", "sport": "football",
               "domicile": "Domicile", "exterieur": "Exterieur", "debut": "2026-10-18T18:00:00+00:00",
               "marche": "TOTAL", "periode": "MATCH", "ligne": 2.5, "issue": "PLUS", "cote": 1.91}]
    rapport = winamax.rapport(pulse, direct)
    assert rapport["couverture"] == 1 and rapport["accord_cotes"] == 1
    assert rapport["pret_a_basculer"] is True
    assert rapport["seuil_couverture"] == 0.95 and rapport["seuil_accord"] == 0.99
    direct[0]["cote"] = 2.2
    assert winamax.rapport(pulse, direct)["pret_a_basculer"] is False


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


def test_erreur_reseau_sans_corps():
    class Faux:
        def recv_str(self):
            return "0{}"

        def send_str(self, msg):
            if msg.startswith("42"):
                raise OSError("secret-ne-pas-journaliser")

        def close(self):
            pass

    client = winamax.Socket(pause=(0, 0), connecter=lambda: Faux())
    assert client.demander("match:1") is None
    assert client.erreurs == ["match:1 : réseau"]
    assert "secret" not in " ".join(client.erreurs)


def test_mode_par_defaut(monkeypatch):
    monkeypatch.delenv("SOURCE_WINAMAX", raising=False)
    assert winamax.mode_source() == "shadow"
    monkeypatch.setenv("SOURCE_WINAMAX", "direct")
    assert winamax.mode_source() == "direct"
    monkeypatch.setenv("SOURCE_WINAMAX", "autre")
    assert winamax.mode_source() == "shadow"


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


def test_repli_ignore_une_lecture_vide(monkeypatch):
    from datetime import datetime, timezone
    from scripts import cycle
    from tests.test_collecte_parallele import _sans_reseau, ligne
    maintenant = datetime(2026, 10, 17, tzinfo=timezone.utc)

    def pulse(key, plan, *a, **kw):
        return [ligne("football", "winamax") | {"cote": 1.9}], {"winamax": 1}, {
            "winamax": ["winamax/soccer/events : HTTP 401"]}

    def direct(sports, heures, **kwargs):
        return [], {"ok": False, "erreurs": ["lecture vide"], "requetes": 1, "matchs": 0}

    _sans_reseau(monkeypatch)
    monkeypatch.setattr(cycle.winamax_direct, "collecter", direct)
    monkeypatch.setattr(cycle.pinnacle, "collecter", lambda: [ligne("football")])
    monkeypatch.setattr(cycle.polymarket, "collecter", lambda *a: [])
    monkeypatch.setattr(cycle, "harmoniser_pinnacle", lambda x: x)
    monkeypatch.setattr(cycle.pulsescore, "collecter", pulse)
    j = {"etapes": {}}
    _, _, lignes, _ = cycle.collecter_prematch("cle", "complet", maintenant, j)
    wina = [l for l in lignes if l["bookmaker"] == "winamax"]
    assert wina and wina[0]["cote"] == 1.9
    assert j["winamax_source_effective"] == "shadow"
    assert j["etapes"]["winamax_direct"]["ok"] is False
