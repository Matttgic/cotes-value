"""Paris joueurs NBA/NHL : persistance Pinnacle, livres français, rapprochement sharp seulement."""
from datetime import datetime, timedelta, timezone

from cotes import pinnacle as P
from cotes import reprise
from cotes.direct import netbet, unibet, winamax
from cotes.direct.horizon import fusionner_marches
from cotes.joueurs import cle_joueur, depuis_titre_et_issues, est_titre_joueur, stat_canonique
from cotes.props import comparer

MAINTENANT = datetime(2026, 11, 9, 18, tzinfo=timezone.utc)


class _Reponse:
    def __init__(self, data, age="10"):
        self.status_code = 200
        self.headers = {"Age": age, "cf-cache-status": "HIT"}
        self._data = data

    def json(self):
        return self._data


def test_nom_joueur_accents_initiales_et_suffixe():
    assert cle_joueur("Nikola Jokić") == cle_joueur("Nikola Jokic") == cle_joueur("N. Jokic")
    assert cle_joueur("LeBron James") == cle_joueur("L. James") == cle_joueur("l. james")
    assert cle_joueur("P.J. Washington") == cle_joueur("PJ Washington")
    assert cle_joueur("De'Aaron Fox") == cle_joueur("D. Fox")
    assert cle_joueur("Gary Trent Jr.") == cle_joueur("Gary Trent Jr")
    assert cle_joueur("Gary Trent Jr") != cle_joueur("Gary Trent")
    assert cle_joueur("Martin, Alijah") == cle_joueur("Alijah Martin")
    assert cle_joueur("Al Horford") == cle_joueur("A. Horford")


def test_paliers_et_plus_moins_meme_stat():
    ou = depuis_titre_et_issues(1, "Nombre de points du joueur - Sion James",
                                [("Plus de 7,5", 1.68), ("Moins de 7,5", 1.78)])
    assert ou["canonicalMarket"] == "PLAYER_PROP"
    assert {(s["stat"], s["joueur"], s["canonicalOutcome"], s["line"]) for s in ou["selections"]} == {
        ("Points", "Sion James", "OVER", 7.5), ("Points", "Sion James", "UNDER", 7.5)}
    pra = depuis_titre_et_issues(2, "Total du joueur (points + rebonds + passes) - Nikola Jokić",
                                 [("Plus de 26,5", 1.9), ("Moins de 26,5", 1.9)])
    assert pra["selections"][0]["stat"] == "PointsReboundsAssists"
    palier = depuis_titre_et_issues(3, "Points du joueur : 1 ou plus", [("Connor McDavid", 1.12)])
    assert palier["selections"][0]["line"] == 0.5 and palier["selections"][0]["joueur"] == "Connor McDavid"
    buts = depuis_titre_et_issues(4, "Nombre de Buts - Leon Draisaitl",
                                  [("Leon Draisaitl 1+", 1.9), ("Leon Draisaitl 2+", 4.5)])
    assert {(s["line"], s["canonicalOutcome"]) for s in buts["selections"]} == {(0.5, "OVER"), (1.5, "OVER")}
    assert stat_canonique("Pts&Rebs&Asts") == "PointsReboundsAssists"
    assert stat_canonique("ThreesMade") == stat_canonique("Threes Made") == "ThreePoints"
    assert stat_canonique("Points du joueur : 3 ou plus") == "Points"
    assert stat_canonique("Nombre de paniers à 3 points du joueur") == "ThreePoints"
    assert est_titre_joueur("Plus / Moins Points - Luka Doncic")
    assert not est_titre_joueur("Plus / Moins Points - Equipe - Match")
    assert not est_titre_joueur("Nombre de points")


def _special_joueur():
    parent = {"id": 10, "type": "matchup", "isLive": False, "startTime": "2026-11-10T02:00:00Z",
              "participants": [{"alignment": "home", "name": "Lakers"}, {"alignment": "away", "name": "Celtics"}],
              "league": {"name": "NBA"}}
    special = {"id": 11, "type": "special", "parentId": 10, "isLive": False,
               "units": "Points",
               "participants": [{"id": 1, "name": "Over"}, {"id": 2, "name": "Under"}],
               "special": {"category": "Player Props", "description": "LeBron James Total Points"}}
    prix = {"matchupId": 11, "key": "pp", "prices": [
        {"participantId": 1, "price": -110, "points": 25.5},
        {"participantId": 2, "price": -110, "points": 25.5}]}
    vainqueur = {"matchupId": 10, "type": "moneyline", "key": "ml", "period": 0, "status": "open",
                 "prices": [{"designation": "home", "price": -120}, {"designation": "away", "price": 100}]}
    return [parent, special], [vainqueur], [prix, vainqueur]


def test_pinnacle_persiste_les_lignes_joueur(monkeypatch, tmp_path):
    matchups, sans, avec = _special_joueur()

    def get(url, **kw):
        if "matchups" in url:
            return _Reponse(matchups)
        corps = avec if "withSpecials=true" in url else sans
        return _Reponse(corps)

    monkeypatch.setattr(P._http, "get", get)
    monkeypatch.setattr(P, "_cle_dynamique", lambda: None)
    monkeypatch.setenv("PINNACLE_CHOIX_PRIX", "non")
    lignes = P.collecter({4: "basket"})
    props = [l for l in lignes if str(l.get("marche")).startswith("JOUEUR:")]
    assert {(l["marche"], l["joueur"], l["issue"], l["ligne"]) for l in props} == {
        ("JOUEUR:Points", "LeBron James", "PLUS", 25.5),
        ("JOUEUR:Points", "LeBron James", "MOINS", 25.5)}
    assert sum(l["proba_juste"] for l in props) == 1
    assert all(l["cote_perimee"] is False for l in props)
    stock = {}
    reprise.memoriser(stock, "Pinnacle", lignes, MAINTENANT)
    chemin = tmp_path / "derniere_lecture.json.gz"
    reprise.ecrire(chemin, stock, reprise.Seuils(MAINTENANT))
    relu = reprise.lire(chemin)
    gardes = [l for l in relu["Pinnacle"]["basket"]["lignes"] if str(l.get("marche")).startswith("JOUEUR:")]
    assert len(gardes) == 2 and {l["joueur"] for l in gardes} == {"LeBron James"}


def test_choix_prix_sans_speciaux_ne_fait_pas_disparaitre_les_joueurs(monkeypatch):
    """L'URL la plus fraîche sans withSpecials ne doit plus remplacer celle qui porte les props."""
    matchups, sans, avec = _special_joueur()
    heads = []

    class Tete:
        def __init__(self, status, age=None):
            self.status_code = status
            self.headers = {"cf-cache-status": "HIT"}
            if age is not None:
                self.headers["Age"] = str(age)

    def head(url, **kw):
        heads.append(url)
        if url.endswith("?primaryOnly=false"):
            return Tete(200, 5)
        if "withSpecials=true" in url:
            return Tete(200, 400)
        return Tete(200, 600)

    def get(url, **kw):
        corps = matchups if "matchups" in url else (avec if "withSpecials=true" in url else sans)
        return _Reponse(corps, age="20")

    monkeypatch.setenv("PINNACLE_CHOIX_PRIX", "oui")
    monkeypatch.setattr(P._http, "head", head)
    monkeypatch.setattr(P._http, "get", get)
    monkeypatch.setattr(P, "_cle_dynamique", lambda: None)
    lignes = P.collecter({4: "basket"})
    assert any(l["marche"] == "JOUEUR:Points" for l in lignes)
    assert not any(h.endswith("/markets/straight?primaryOnly=false") for h in heads)


class _Memoire:
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


def test_winamax_lit_les_filtres_joueurs_et_normalise(monkeypatch):
    monkeypatch.setattr(winamax, "FILTRES", {"basket": ()})
    monkeypatch.setattr(winamax.time, "sleep", lambda s: None)
    debut = int((MAINTENANT + timedelta(hours=8)).timestamp())
    match = {"matchId": 8, "status": "PREMATCH", "competitor1Name": "Lakers",
             "competitor2Name": "Celtics", "matchStart": debut}
    detail = {
        "bets": {
            "a": {"betId": 1, "matchId": 8, "marketId": 921, "available": True,
                  "betTitle": "Nombre de points du joueur - Nikola Jokić",
                  "specialBetValue": "total=26.5", "outcomes": [1, 2]},
            "b": {"betId": 2, "matchId": 8, "marketId": 9053, "available": True,
                  "betTitle": "Total du joueur (points + rebonds + passes) - L. James",
                  "specialBetValue": "total=40.5", "outcomes": [3, 4]},
        },
        "outcomes": {
            "1": {"label": "Plus de 26,5", "code": "over", "available": True},
            "2": {"label": "Moins de 26,5", "code": "under", "available": True},
            "3": {"label": "Plus de 40,5", "code": "over", "available": True},
            "4": {"label": "Moins de 40,5", "code": "under", "available": True},
        },
        "odds": {"1": 1.87, "2": 1.87, "3": 1.9, "4": 1.9},
    }
    transport = _Memoire({"sport:2": {"matches": {"8": match}, **detail},
                          ("sport:2", 593): detail})
    lignes, meta = winamax.collecter({"basket"}, 36, transport=transport, maintenant=MAINTENANT)
    assert meta["ok"] and 593 in {f for _, f in transport.demandes}
    props = [l for l in lignes if l["marche"].startswith("JOUEUR:")]
    assert {l["marche"] for l in props} == {"JOUEUR:Points", "JOUEUR:PointsReboundsAssists"}
    assert {l["joueur"] for l in props if l["marche"] == "JOUEUR:Points"} == {"Nikola Jokić"}
    assert all(l["periode"] == "MATCH" and l["ligne"] in (26.5, 40.5) for l in props)


def test_unibet_plus_moins_et_palier_hockey():
    points = unibet._marche_joueur("m1", {
        "desc": "Plus / Moins Points - Luka Doncic",
        "outcomes": [{"desc": "Plus 28.5", "price": "1,90"}, {"desc": "Moins 28.5", "price": "1,85"}],
    })
    assert points["selections"][0]["stat"] == "Points"
    assert points["selections"][0]["joueur"] == "Luka Doncic"
    buts = unibet._marche_joueur("m2", {
        "desc": "Nombre de Buts - Leon Draisaitl",
        "outcomes": [{"desc": "Leon Draisaitl 1+", "price": "1,90"},
                     {"desc": "Leon Draisaitl 2+", "price": "4,50"}],
    })
    assert {(s["stat"], s["line"]) for s in buts["selections"]} == {("Goals", 0.5), ("Goals", 1.5)}
    assert unibet.PROPS["basket"][0] == (994003092, 209)
    assert (994033137, 1191) in unibet.PROPS["hockey"]


def test_netbet_garde_un_total_joueur_deja_dans_la_page():
    offre = netbet.marche_depuis({
        "order": "j",
        "bets": [{"label": "Nombre de points du joueur - Sion James", "selections": [
            {"label": "Plus de 12,5", "odds": 1.8}, {"label": "Moins de 12,5", "odds": 1.9}]}],
    }, "Lakers", "Celtics")
    assert offre["canonicalMarket"] == "PLAYER_PROP"
    assert offre["selections"][0]["stat"] == "Points"
    exclu = netbet.marche_depuis({
        "order": "c", "bets": [{"label": "Nombre de corners", "selections": [
            {"label": "Plus de 9,5", "odds": 1.8}, {"label": "Moins de 9,5", "odds": 1.9}]}],
    }, "Lyon", "Nice")
    assert exclu is None


def test_deux_livres_francais_ne_se_comparent_pas():
    def ligne(source, joueur, cote):
        return {"source": source, "bookmaker": source, "sport": "basket", "match_id": f"{source}|1",
                "domicile": "Lakers", "exterieur": "Celtics", "debut": "2026-11-10T02:00:00Z",
                "collecte": "2026-11-09T18:00:00+00:00", "marche": "JOUEUR:Points", "periode": "MATCH",
                "ligne": 25.5, "issue": "PLUS", "joueur": joueur, "cote": cote, "proba_juste": 0.5}
    pin = {**ligne("pinnacle", "LeBron James", 1.91), "match_id": "p1", "proba_juste": 0.52,
           "cote_juste": 1.9231, "marge_pinnacle": 0.04, "cote_perimee": False}
    fr = [ligne("Winamax", "L. James", 2.2), ligne("Unibet", "LeBron James", 2.4)]
    rapproches = comparer(fr, {"Pinnacle": [pin], "Unibet": fr[1:]})
    assert {r["reference"] for r in rapproches} == {"Pinnacle"}
    assert len(rapproches) == 2
    assert all(r["pariable"] is False and r["ecart"] == round(r["cote"] * 0.52 - 1, 4) for r in rapproches)
    assert comparer(fr, {"Unibet": [fr[1]], "Winamax": [fr[0]]}) == []


def test_fusion_ne_melange_pas_deux_joueurs():
    def l(joueur, cote):
        return {"match_id": "w|1", "marche": "JOUEUR:Points", "periode": "MATCH", "joueur": joueur,
                "debut": (MAINTENANT + timedelta(hours=3)).isoformat(), "collecte": MAINTENANT.isoformat(),
                "cote": cote}
    anciennes = [l("James", 1.8), l("Jokic", 1.9)]
    neuves = [{**l("James", 2.0), "collecte": (MAINTENANT + timedelta(minutes=5)).isoformat()}]
    fusion = fusionner_marches(anciennes, neuves, MAINTENANT + timedelta(minutes=5), 36)
    assert {(x["joueur"], x["cote"]) for x in fusion} == {("James", 2.0), ("Jokic", 1.9)}
