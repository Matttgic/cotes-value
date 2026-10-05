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
        ("CORRECT_SCORE", None, "2-1"), ("DOUBLE_CHANCE", None, "DRAW_AWAY"),
        ("HALF_TIME_FULL_TIME", None, "NUL/DOM"), ("HANDICAP_3", -1.0, "NUL")]


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
