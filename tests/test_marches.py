from cotes.correspondance import ressemblance
from cotes.marches import cle, harmoniser_pinnacle, inverser
from cotes.pulsescore import periode, traduire


def ev(markets, home="Lens", away="Lille"):
    return {"eventId": "1", "home": home, "away": away, "league": "L1", "startTime": "2030-01-01T20:00:00Z",
            "markets": markets}


def sel(o, raw, odds, line=None):
    return {"canonicalOutcome": o, "rawName": raw, "odds": odds, "line": line, "isActive": True}


def test_handicap_ligne_du_domicile_sur_les_deux_issues():          # Winamax, NetBet, Betclic
    m = {"canonicalMarket": "ASIAN_HANDICAP", "period": "FULL_TIME", "rawName": "Écart de buts (handicap)",
         "selections": [sel("HOME", "Lens -1.5", 3.1, -1.5), sel("AWAY", "Lille +1.5", 1.35, -1.5)]}
    L = traduire(ev([m]), "winamax", "football", "t")
    assert [(l["ligne"], l["issue"]) for l in L] == [(-1.5, "DOM"), (-1.5, "EXT")]


def test_handicap_ligne_propre_a_chaque_issue():                     # PMU
    m = {"canonicalMarket": "ASIAN_HANDICAP", "period": "FULL_TIME", "rawName": "Handicap",
         "selections": [sel("HOME", "Lens", 2.0, -0.5), sel("AWAY", "Lille", 1.8, 0.5)]}
    assert {l["ligne"] for l in traduire(ev([m]), "pmu", "football", "t")} == {-0.5}


def test_handicap_dans_le_libelle():                                 # Unibet
    m = {"canonicalMarket": "ASIAN_HANDICAP", "period": "FULL_TIME", "rawName": "Face à Face Handicap [-1,5]",
         "selections": [sel("HOME", "Lens [-1,5]", 3.5), sel("AWAY", "Lille [+1,5]", 1.12)]}
    assert {l["ligne"] for l in traduire(ev([m]), "unibet-fr", "football", "t")} == {-1.5}


def test_periode_ecrite_dans_le_libelle_et_cas_ambigus():
    assert periode("football", "FULL_TIME", "Mi-temps - Nombre de buts") == "MT1"
    assert periode("football", "SECOND_HALF", "2nd Half Total Goals") == "MT2"
    assert periode("hockey", "FIRST_HALF", "1ère période - Total de buts") == "P1"
    assert periode("basketball", "FIRST_QUARTER", "1er quart-temps - Nombre de points") == "QT1"
    assert periode("football", "SECOND_HALF", "Résultat") is None       # période non écrite : ignoré


def test_breaks_au_tennis_ignores():
    m = {"canonicalMarket": "OVER_UNDER", "period": "FULL_TIME", "rawName": "Nombre total de breaks",
         "selections": [sel("OVER", "+ de 5,5", 1.8, 5.5), sel("UNDER", "- de 5,5", 1.9, 5.5)]}
    assert traduire(ev([m], "A", "B"), "betclic", "tennis", "t") == []


def test_hockey_prolongation():
    tot = {"canonicalMarket": "OVER_UNDER", "period": "FULL_TIME", "rawName": "Nombre total de buts (tps rég.)",
           "selections": [sel("OVER", "+ de 5,5", 1.9, 5.5), sel("UNDER", "- de 5,5", 1.9, 5.5)]}
    tot2 = {**tot, "rawName": "Nombre de buts"}
    dc = {"canonicalMarket": "DOUBLE_CHANCE", "period": "FULL_TIME", "rawName": "Double chance",
          "selections": [sel("HOME_DRAW", "A ou nul", 1.3), sel("DRAW_AWAY", "B ou nul", 1.6)]}
    assert {l["periode"] for l in traduire(ev([tot]), "betclic", "hockey", "t")} == {"TEMPS_REG"}
    # Winamax : nombre de buts prolongations incluses (vérifié sur le site)
    assert {l["periode"] for l in traduire(ev([tot2]), "winamax", "hockey", "t")} == {"MATCH"}
    # PMU : temps réglementaire sauf « Prol. et t.a.b. inc. » ; Betclic : prolongation sauf mention
    assert {l["periode"] for l in traduire(ev([tot2]), "pmu", "hockey", "t")} == {"TEMPS_REG"}
    tot3 = {**tot, "rawName": "Nombre de buts (Prol. et t.a.b. inc.)"}
    assert {l["periode"] for l in traduire(ev([tot3]), "pmu", "hockey", "t")} == {"MATCH"}
    assert {l["periode"] for l in traduire(ev([tot2]), "betclic", "hockey", "t")} == {"MATCH"}
    assert {l["periode"] for l in traduire(ev([dc]), "winamax", "hockey", "t")} == {"TEMPS_REG"}
    # Unibet : « Temps réglementaire » écrit dans l'intitulé, sinon prolongation incluse
    tot4 = {**tot, "rawName": "Nombre total de buts - Temps Réglementaire"}
    assert {l["periode"] for l in traduire(ev([tot4]), "unibet-fr", "hockey", "t")} == {"TEMPS_REG"}
    assert {l["periode"] for l in traduire(ev([tot2]), "unibet-fr", "hockey", "t")} == {"TEMPS_REG"}   # constaté sur les cotes
    # Unibet et Winamax : total par équipe sur le temps réglementaire même sans mention (vérifié dans l'appli)
    eq = {"canonicalMarket": "HOME_OVER_UNDER", "period": "FULL_TIME", "rawName": "Plus / Moins But(s) - Lens 2.5",
          "selections": [sel("OVER", "Plus de 2.5", 2.1, 2.5), sel("UNDER", "Moins de 2.5", 1.7, 2.5)]}
    assert {l["periode"] for l in traduire(ev([eq]), "unibet-fr", "hockey", "t")} == {"TEMPS_REG"}
    assert {l["periode"] for l in traduire(ev([eq]), "winamax", "hockey", "t")} == {"TEMPS_REG"}
    assert {l["periode"] for l in traduire(ev([tot2]), "unibet-fr", "basket", "t")} == {"MATCH"}
    assert {l["periode"] for l in traduire(ev([tot4]), "unibet-fr", "basket", "t")} == {"TEMPS_REG"}
    # NetBet : « prolongations incluses » écrit dans l'intitulé, sinon temps réglementaire
    tot5 = {**tot, "rawName": "Nombre total de points (Prolongation(s) incluse(s))"}
    assert {l["periode"] for l in traduire(ev([tot5]), "netbet", "basket", "t")} == {"MATCH"}
    assert {l["periode"] for l in traduire(ev([tot2]), "netbet", "basket", "t")} == {"TEMPS_REG"}
    # sports US : prolongation incluse partout
    for bm in ("winamax", "betclic", "unibet-fr", "pmu", "netbet"):
        for sp in ("football_americain", "baseball"):
            assert {l["periode"] for l in traduire(ev([tot2]), bm, sp, "t")} == {"MATCH"}


def test_handicap_hockey_prolongation_sans_effet():
    def hc(ligne):
        return {"canonicalMarket": "ASIAN_HANDICAP", "period": "FULL_TIME", "rawName": "Handicap",
                "selections": [sel("HOME", "A", 2.0, ligne), sel("AWAY", "B", 1.8, ligne)]}
    # ±1,5 : la prolongation ne donne qu'un but d'écart, même règlement -> comparable à Pinnacle (match entier)
    assert {l["periode"] for l in traduire(ev([hc(-1.5)]), "winamax", "hockey", "t")} == {"MATCH"}
    # ±0,5 : la prolongation change tout -> règle du bookmaker (Winamax : temps réglementaire)
    assert {l["periode"] for l in traduire(ev([hc(-0.5)]), "winamax", "hockey", "t")} == {"TEMPS_REG"}


def test_pinnacle_specials():
    base = {"domicile": "Lens", "exterieur": "Lille", "periode": "MATCH", "ligne": None}
    L = harmoniser_pinnacle([
        {**base, "marche": "SPECIAL:Correct Score", "issue": "Lens 2, Lille 1"},
        {**base, "marche": "SPECIAL:Double Chance", "issue": "Draw Or Lille"},
        {**base, "marche": "SPECIAL:Half-Time/Full-Time", "issue": "Draw - Lens"},
        {**base, "marche": "SPECIAL:3-Way Handicap DOM -1", "issue": "Draw - (Lens -1)"},
        {**base, "marche": "SPECIAL:Winning Margin", "issue": "Lens By 1"},
    ])
    assert [(l["marche"], l["ligne"], l["issue"]) for l in L] == [
        ("CORRECT_SCORE", None, "2-1"),                 # double chance : recalculée depuis le 1N2
        ("HALF_TIME_FULL_TIME", None, "NUL/DOM"), ("HANDICAP_3", -1.0, "NUL")]


def test_double_chance_depuis_le_1n2():
    from cotes.marches import deriver_double_chance
    base = {"match_id": "p1", "periode": "MATCH", "marche": "RESULTAT_1N2", "ligne": None, "cle_marche": "k",
            "marge_pinnacle": 0.03}
    L = deriver_double_chance([{**base, "issue": "DOM", "proba_juste": 0.5}, {**base, "issue": "NUL", "proba_juste": 0.3},
                               {**base, "issue": "EXT", "proba_juste": 0.2},
                               {**base, "marche": "DOUBLE_CHANCE", "issue": "HOME_DRAW", "proba_juste": 0.4}])
    dc = {l["issue"]: l["proba_juste"] for l in L if l["marche"] == "DOUBLE_CHANCE"}
    assert dc == {"HOME_DRAW": 0.8, "HOME_AWAY": 0.7, "DRAW_AWAY": 0.5}


def test_inversion_domicile_exterieur():
    l = {"domicile": "A", "exterieur": "B", "marche": "HANDICAP", "periode": "MATCH", "ligne": -1.5, "issue": "DOM"}
    assert cle(inverser(l)) == ("HANDICAP", "MATCH", 1.5, "EXT")
    s = {**l, "marche": "CORRECT_SCORE", "ligne": None, "issue": "2-0"}
    assert cle(inverser(s)) == ("CORRECT_SCORE", "MATCH", None, "0-2")


def test_noms():
    assert ressemblance("Italie (UN)", "Italy") >= 0.85
    assert ressemblance("D. Vekic", "Donna Vekic") >= 0.85
    assert ressemblance("Llaneros F.C.", "Llaneros") == 1.0
    assert ressemblance("Cordoue", "Cordoba") == 1.0
    assert ressemblance("Lens", "Lille") < 0.6


def test_statistiques_et_manches_partielles_ignorees():
    tirs = {"canonicalMarket": "HOME_OVER_UNDER", "period": "FULL_TIME", "rawName": "Plus / Moins Tirs cadrés - Lens",
            "selections": [sel("OVER", "Plus de 1,5", 1.1, 1.5), sel("UNDER", "Moins de 1,5", 7.5, 1.5)]}
    assert traduire(ev([tirs]), "unibet-fr", "football", "t") == []
    serie = {"canonicalMarket": "ASIAN_HANDICAP", "period": "FULL_TIME", "rawName": "Handicap - Series Outcome",
             "selections": [sel("HOME", "A", 6.15, -1.5), sel("AWAY", "B", 1.1, -1.5)]}
    manches3 = {**serie, "rawName": "Handicap - First 3 Innings"}
    manches5 = {**serie, "rawName": "Handicap - First 5 Innings"}
    assert traduire(ev([serie, manches3]), "pmu", "baseball", "t") == []
    assert {l["periode"] for l in traduire(ev([manches5]), "pmu", "baseball", "t")} == {"5_MANCHES"}
    tab = {"canonicalMarket": "MATCH_RESULT", "period": "FULL_TIME",
           "rawName": "Vainqueur (prolongations et tirs au but inclus)",
           "selections": [sel("HOME", "A", 1.8), sel("AWAY", "B", 2.0)]}
    assert len(traduire(ev([tab]), "betclic", "hockey", "t")) == 2      # « tirs au but » n'est pas une stat


def test_marqueur_u21_de_la_ligue_pinnacle():
    from cotes.correspondance import avec_marqueurs_ligue
    pin = avec_marqueurs_ligue("France", "UEFA - U21 Euro Championship Qualifiers")
    assert ressemblance("France U21", pin) == 1.0
    assert ressemblance("France", pin) < 1.0



def test_ordre_inverse_face_a_pinnacle():
    from datetime import datetime, timezone
    from cotes.correspondance import associer
    t = datetime(2026, 10, 6, 23, 0, tzinfo=timezone.utc)
    fr = {"n1": {"match_id": "n1", "sport": "hockey", "domicile": "New York Islanders", "exterieur": "New York Rangers",
                 "debut": t, "approx": False, "ordre_incertain": False}}
    ref = {"p1": {"match_id": "p1", "sport": "hockey", "domicile": "New York Rangers", "exterieur": "New York Islanders",
                  "debut": t, "approx": False, "ordre_incertain": False}}
    assert associer(fr, ref)["n1"][:2] == ("p1", True)


def test_panne_d_un_bookmaker_n_efface_pas_les_autres(monkeypatch):
    # revue externe (B3) : un timeout chez Betclic faisait perdre toute la collecte PulseScore
    from cotes import pulsescore as P

    def matchs(self, bm, sport, heures, pages_max=40):
        self.requetes += 1
        if bm == "betclic":
            raise TimeoutError("lecture trop longue")
        return []

    monkeypatch.setattr(P.Client, "matchs", matchs)
    monkeypatch.setattr(P, "traduire", lambda e, bm, sp, moment: [])
    lignes, requetes, erreurs = P.collecter("cle", {"winamax": ["soccer", "tennis"], "betclic": ["soccer"]})
    assert requetes == {"winamax": 2, "betclic": 1}
    assert list(erreurs) == ["betclic"] and "TimeoutError" in erreurs["betclic"][0]


def test_client_reessaie_les_erreurs_reseau(monkeypatch):
    import requests
    from cotes import pulsescore as P
    monkeypatch.setattr(P.time, "sleep", lambda s: None)

    class Rep:
        status_code = 200
        headers = {}

        def __init__(self, corps):
            self.corps = corps

        def json(self):
            if self.corps is None:
                raise ValueError("pas du JSON")
            return self.corps

    reponses = [requests.ConnectionError("coupure"), Rep({"events": []}), Rep(None)]

    def get(*a, **k):
        r = reponses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    c = P.Client("cle", pause=0)
    monkeypatch.setattr(c.s, "get", get)
    assert c.get("winamax/soccer/events") == {"events": []} and c.requetes == 2
    assert c.get("winamax/soccer/events") is None and c.erreurs == ["winamax/soccer/events : JSON invalide"]


def test_double_rencontre_le_meme_jour():
    # revue externe (8.6) : deux matchs des mêmes équipes le même jour (baseball) ; à noms égaux, l'heure
    # la plus proche l'emporte, pas le premier match rencontré
    from cotes.correspondance import associer, matchs_de
    m = lambda mid, src, h: {"match_id": mid, "source": src, "sport": "baseball", "domicile": "Yankees",  # noqa: E731
                             "exterieur": "Red Sox", "debut": f"2026-10-07T{h}:05:00+00:00"}
    fr = matchs_de([m("fr2", "winamax", "21")])
    ref = matchs_de([m("p1", "pinnacle", "20"), m("p2", "pinnacle", "21")])
    assert associer(fr, ref)["fr2"][0] == "p2"
