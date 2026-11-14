"""Revue de bugs du 14/11/2026 (docs/revue-bugs.md) : un test par bug, sur son exemple réel."""
from datetime import datetime, timedelta, timezone

from cotes import comparaison, simulation
from cotes.correspondance import associer, matchs_de, ressemblance
from cotes.direct import pmu
from cotes.pulsescore import periode, traduire

T = "2026-11-08T10:00:00+00:00"


def _m(mid, source, domicile, exterieur, sport="football", debut="2026-11-08T14:00:00+00:00", **plus):
    return {"match_id": mid, "source": source, "sport": sport, "domicile": domicile, "exterieur": exterieur,
            "debut": debut, **plus}


def _assoc(fr, ref):
    return associer(matchs_de(fr), matchs_de(ref))


# ------------------------------------------------------------------------------------------- matchs mal appariés

def test_deux_noms_seulement_approchants_ne_suffisent_pas():
    """Derby County – Stoke City associé à Newport County – York City (Betfair, 17/10/2026, 5 paris)."""
    for fr, ref in ((("Derby County", "Stoke City"), ("Newport County", "York City")),
                    (("Parnu JK Vaprus", "Nõmme Kalju"), ("Harju JK Laagri", "Nomme United")),
                    (("Odense BK", "Silkeborg"), ("Horsens", "Viborg")),
                    (("Odense BK", "Silkeborg"), ("Viborg", "Horsens"))):
        assert _assoc([_m("winamax|1", "Winamax", *fr)], [_m("r1", "betfair", *ref)]) == {}
    # un nom solide et l'autre approchant, à la même heure : toujours associé
    a = _assoc([_m("betclic|1", "Betclic", "ADO La Haye", "PSV Eindhoven")], [_m("r1", "pinnacle", "ADO Den Haag", "PSV")])
    assert a["betclic|1"][:2] == ("r1", False)
    a = _assoc([_m("betclic|1", "Betclic", "Legia Varsovie", "Wisla Cracovie")],
               [_m("r1", "pinnacle", "Legia Warsaw", "Wisla Krakow")])
    assert a["betclic|1"][2] == 1.0                           # exonymes français traduits


def test_un_match_de_reference_pour_un_seul_match_du_bookmaker():
    """Betclic, 13/10/2026 : deux matchs estoniens sur le même match Pinnacle 1637810025 ; FC Tokyo – Kashiwa
    Reysol sur Yokohama F. Marinos – Tokyo Verdy (Smarkets, 21/10, 74 paris) ; Akureyri (24/10)."""
    ref = [_m("s1", "smarkets", "Yokohama F. Marinos", "Tokyo Verdy")]
    seul = _assoc([_m("pmu|1", "PMU", "FC Tokyo", "Kashiwa Reysol")], ref)
    assert seul["pmu|1"][2] == 0.7                            # sosie accepté quand rien ne le contredit
    a = _assoc([_m("pmu|1", "PMU", "FC Tokyo", "Kashiwa Reysol"), _m("pmu|2", "PMU", "Yokohama F. Marinos", "Tokyo Verdy"),
                _m("betclic|1", "Betclic", "Yokohama F Marinos", "Tokyo Verdy")], ref)
    assert set(a) == {"pmu|2", "betclic|1"}                   # le vrai match garde la référence, chez chaque bookmaker
    a = _assoc([_m("olybet|1", "OlyBet", "Akureyri", "Vestmannaeyjar"), _m("olybet|2", "OlyBet", "Hafnarfjordur", "Thor Akureyri")],
               [_m("p1", "pinnacle", "FH Hafnarfjordur", "Thor Akureyri")])
    assert set(a) == {"olybet|2"}
    # le même match listé deux fois par le bookmaker (noms concordants) garde ses deux associations
    a = _assoc([_m("betclic|1", "Betclic", "Lens", "Lille"), _m("betclic|2", "Betclic", "RC Lens", "Lille OSC")],
               [_m("p1", "pinnacle", "Lens", "Lille")])
    assert set(a) == {"betclic|1", "betclic|2"}


def test_simple_et_double_ne_sont_pas_le_meme_match():
    """OlyBet, 04/11/2026 : simple Falkowska – Rajeshwaran Revathi associé à un double de Pinnacle."""
    double = _m("p1", "pinnacle", "Aneta Kucmova / Aneta Laboutkova",
                "Shrivalli Rashmikaa Bhamidipaty / Maaya Rajeshwaran Revathi", sport="tennis")
    assert _assoc([_m("olybet|1", "OlyBet", "Weronika Falkowska", "Maaya Rajeshwaran Revathi", sport="tennis")], [double]) == {}
    double = _m("p1", "pinnacle", "Jodie Burrage / Robin Montgomery", "Teodora Kostovic / Jeline Vandromme", sport="tennis")
    assert _assoc([_m("winamax|1", "Winamax", "Robin Montgomery", "Jeline Vandromme", sport="tennis")], [double]) == {}
    a = _assoc([_m("winamax|1", "Winamax", "J. Burrage / R. Montgomery", "T. Kostovic / J. Vandromme", sport="tennis")], [double])
    assert a["winamax|1"][0] == "p1"
    # un nom d'équipe à barre oblique n'est pas un double
    a = _assoc([_m("pmu|1", "PMU", "Charlotte Checkers", "Wilkes-Barre/Scranton Penguins", sport="hockey")],
               [_m("p1", "pinnacle", "Charlotte Checkers", "Wilkes Barre Scranton Penguins", sport="hockey")])
    assert a["pmu|1"][0] == "p1"


def test_un_seul_joueur_reconnu_ne_fait_pas_le_match():
    """OlyBet, 21/10/2026 : Onclin – Struff associé à Blockx – Struff (Polymarket)."""
    assert _assoc([_m("olybet|1", "OlyBet", "Gauthier Onclin", "Jan-Lennard Struff", sport="tennis")],
                  [_m("p1", "polymarket", "Alexander Blockx", "Jan-Lennard Struff", sport="tennis")]) == {}
    a = _assoc([_m("olybet|1", "OlyBet", "G. Onclin", "Jan-Lennard Struff", sport="tennis")],
               [_m("p1", "polymarket", "Gauthier Onclin", "Jan-Lennard Struff", sport="tennis")])
    assert a["olybet|1"][0] == "p1"


def test_equipe_b_et_equipe_ii_sont_la_meme_reserve():
    """Betclic « Real Sociedad B » et Pinnacle « Real Sociedad II » (17/10/2026) n'étaient plus associés."""
    assert ressemblance("Real Sociedad B", "Real Sociedad II") == 1.0
    assert ressemblance("Porto B", "Porto II") == 1.0
    assert ressemblance("Real Sociedad B", "Real Sociedad U19") == 0      # catégories vraiment différentes
    a = _assoc([_m("betclic|1", "Betclic", "Real Sociedad B", "Almeria")], [_m("p1", "pinnacle", "Real Sociedad II", "Almeria")])
    assert a["betclic|1"][:2] == ("p1", False)


def test_association_sur_tous_les_matchs_de_la_reference():
    """Tappara – Ilves (Liiga, 30/10/2026) : quand le vrai match n'a aucune cote fiable, il reste le match associé
    (pas de comparaison) au lieu de laisser sa place au match d'une autre catégorie."""
    def fr(mid):
        return {"source": "PMU", "bookmaker": "pmu", "sport": "hockey", "match_id": mid, "domicile": "Tappara",
                "exterieur": "Ilves", "debut": "2026-10-30T16:30:00+00:00", "collecte": T, "marche": "RESULTAT_1N2",
                "periode": "TEMPS_REG", "ligne": None, "issue": "DOM", "cote": 2.4}

    def pin(mid, dom, ext, ligue, perimee):
        return {"source": "pinnacle", "sport": "hockey", "match_id": mid, "domicile": dom, "exterieur": ext,
                "ligue": ligue, "debut": "2026-10-30T16:30:00+00:00", "collecte": T, "marche": "RESULTAT_1N2",
                "periode": "TEMPS_REG", "ligne": None, "issue": "DOM", "proba_juste": 0.45, "cote_juste": 2.222,
                "cote": 2.1, "marge_pinnacle": 0.04, "cote_perimee": perimee}
    autre = pin(1639061776, "Ilves", "Tappara", "Finland - U20 SM-sarja", False)
    vrai = pin(1639048394, "Tappara", "Ilves", "Finland - Liiga", True)             # cote périmée ce cycle
    assert comparaison.indexer([fr("pmu|1")], {"Pinnacle": [autre]})["Pinnacle"]      # seul : accepté à 0,85
    assert comparaison.indexer([fr("pmu|1")], {"Pinnacle": [autre, vrai]})["Pinnacle"] == {}
    assert comparaison.comparer([fr("pmu|1")], {"Pinnacle": [autre, vrai]}) == []
    index = comparaison.indexer([fr("pmu|1")], {"Pinnacle": [autre, {**vrai, "cote_perimee": False}]})
    assert next(iter(index["Pinnacle"]["pmu|1"].values()))["match_id"] == 1639048394


# ----------------------------------------------------------------------------------------- domicile / extérieur

def test_nom_identique_fixe_l_ordre_meme_hors_derby():
    """America de Cali – Deportivo Cali associé à l'envers à « América de Cali – AD Cali » (Polymarket,
    08/11/2026, 41 paris) : les deux noms ne se ressemblent qu'à 0,62, la règle des derbys ne s'appliquait pas."""
    for dom in ("America de Cali", "América de Cali", "America De Cali"):
        a = _assoc([_m("pmu|1", "PMU", dom, "Deportivo Cali")], [_m("p1", "polymarket", "América de Cali", "AD Cali")])
        assert a["pmu|1"][:2] == ("p1", False)
    a = _assoc([_m("pmu|1", "PMU", "America de Cali", "Deportivo Cali")], [_m("p1", "polymarket", "AD Cali", "América de Cali")])
    assert a["pmu|1"][:2] == ("p1", True)                     # réellement inversé chez la référence
    a = _assoc([_m("netbet|1", "NetBet", "New York Islanders", "New York Rangers", sport="hockey")],
               [_m("p1", "pinnacle", "New York Rangers", "New York Islanders", sport="hockey")])
    assert a["netbet|1"][:2] == ("p1", True)


# ------------------------------------------------------------------------------------------------------ périodes

def test_baseball_premieres_manches_en_francais():
    """PMU, « Handicap - 5 1eres manches » comparé au handicap du match entier : 12 paris du 18/10 au 07/11/2026."""
    assert periode("baseball", "FULL_TIME", "Handicap - 5 1eres manches") == "5_MANCHES"
    assert periode("baseball", "FULL_TIME", "Total de Runs - 5 1ers Tours de Batte") == "5_MANCHES"
    assert periode("baseball", "FULL_TIME", "Handicap - First 5 Innings") == "5_MANCHES"
    for libelle in ("Handicap - 7 1eres manches", "Total de Runs - 7 1ers Tours de Batte",
                    "Total de Runs - 3 1ers Tours de Batte", "Handicap - First 3 Innings", "Total de Runs - 1re manche"):
        assert periode("baseball", "FULL_TIME", libelle) is None
    assert periode("baseball", "FULL_TIME", "Run Line") == "MATCH"
    assert periode("baseball", "FULL_TIME", "Vainqueur - manches supplémentaires incluses") == "MATCH"
    m = {"canonicalMarket": "ASIAN_HANDICAP", "period": "FULL_TIME", "rawName": "Handicap - 5 1eres manches",
         "selections": [{"canonicalOutcome": "HOME", "rawName": "Samsung Lions", "odds": 1.5, "line": -1.5},
                        {"canonicalOutcome": "AWAY", "rawName": "KT Wiz Suwon", "odds": 2.45, "line": 1.5}]}
    ev = {"eventId": "1", "home": "Samsung Lions", "away": "KT Wiz Suwon", "startTime": "2026-11-07T09:30:00Z",
          "markets": [m]}
    assert {l["periode"] for l in traduire(ev, "pmu", "baseball", T)} == {"5_MANCHES"}


def test_pmu_derniere_equipe_a_marquer_n_est_pas_le_vainqueur():
    """PMU : « Dernière équipe à marquer » (rugby) et « To score Goal 2 » (handball) pris pour le vainqueur."""
    def offre(label, anglais):
        return {"id": 1, "eventId": 7, "betOfferType": {"englishName": "Match"},
                "criterion": {"label": label, "englishLabel": anglais, "lifetime": "FULL_TIME"},
                "outcomes": [{"label": "1", "odds": 1630, "type": "OT_ONE", "status": "OPEN"},
                             {"label": "2", "odds": 2150, "type": "OT_TWO", "status": "OPEN"}]}
    for label, anglais in (("Dernière équipe à marquer", "Last Team to Score"), ("To score Goal 2", "To score Goal 2"),
                           ("To score Goal 3", "To score Goal 3")):
        assert pmu.marche_depuis(offre(label, anglais), "Irlande", "Argentine") is None
    assert pmu.marche_depuis(offre("Cotes du match", "Match Odds"), "Irlande", "Argentine")["canonicalMarket"] == "MATCH_RESULT"


# ------------------------------------------------------------------------------------------- écarts « minimum »

def _opportunite(**plus):
    return {"reference": "Polymarket", "detecte": T, "lu_reference": T, "bookmaker": "Winamax", "sport": "basket",
            "match_id": "winamax|1", "domicile": "New Orleans Pelicans", "exterieur": "Brooklyn Nets",
            "debut": "2026-11-09T01:10:00+00:00", "marche": "TOTAL", "periode": "MT1", "ligne": 110.5, "issue": "PLUS",
            "pari": "Plus de 110,5 points", "cote": 1.62, "cote_juste": 1.587, "ecart": 0.0206, **plus}


def test_ecart_minimum_suit_le_pari():
    """Paris b2005ed099a8dd6b et 0c816a6ecca9e08c (Pelicans – Nets, 11/11/2026) : pris au prix d'achat de
    Polymarket, rien ne les distinguait ensuite d'un pari à l'écart exact."""
    maintenant = datetime.fromisoformat(T) + timedelta(seconds=30)
    paris = []
    simulation.placer([_opportunite(prix_prudent=True, proba_milieu=0.66),
                       _opportunite(match_id="betclic|2", bookmaker="Betclic", marche="AVANCE_OU_GAGNE", ligne=10.0,
                                    issue="DOM", reference="Pinnacle", ecart_minimum=True),
                       _opportunite(match_id="pmu|3", bookmaker="PMU")], paris, maintenant)
    par = {p["bookmaker"]: p for p in paris}
    assert par["Winamax"]["ecart_minimum"] and par["Winamax"]["prix_prudent"] and par["Winamax"]["proba_milieu"] == 0.66
    assert par["Betclic"]["ecart_minimum"] and "prix_prudent" not in par["Betclic"]
    assert "ecart_minimum" not in par["PMU"] and "prix_prudent" not in par["PMU"]


def test_cloture_au_prix_d_achat_donne_une_clv_minimale():
    debut = datetime.now(timezone.utc) + timedelta(hours=3)
    lue = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(timespec="seconds")
    cle = ("TOTAL", "MT1", 110.5, "PLUS")
    pari = {"statut": "en_cours", "debut": debut.isoformat(), "match_id": "winamax|1", "reference": "Polymarket",
            "marche": "TOTAL", "periode": "MT1", "ligne": 110.5, "issue": "PLUS", "cote": 1.62}
    index = {"Polymarket": {"winamax|1": {cle: {"proba_juste": 0.63, "collecte": lue, "prix_prudent": True}}}}
    prudentes: set = set()
    justes = comparaison.cotes_justes_depuis(index, prudentes=prudentes)
    assert prudentes == {("winamax|1", cle, "Polymarket")}
    simulation.suivre_cloture([pari], justes, prudentes=prudentes)
    assert pari["clv"] == round(1.62 * 0.63 - 1, 4) and pari["clv_minimum"] is True
    # carnet resserré au cycle suivant : la clôture relue au milieu n'est plus une borne
    plus_tard = (datetime.now(timezone.utc)).isoformat(timespec="seconds")
    index = {"Polymarket": {"winamax|1": {cle: {"proba_juste": 0.66, "collecte": plus_tard}}}}
    simulation.suivre_cloture([pari], comparaison.cotes_justes_depuis(index, prudentes=set()), prudentes=set())
    assert pari["clv"] == round(1.62 * 0.66 - 1, 4) and "clv_minimum" not in pari
    # « avance ou gagne » : clôture de la simple victoire, toujours une borne
    aog = {**pari, "marche": "AVANCE_OU_GAGNE", "ligne": 10.0, "issue": "DOM", "periode": "MATCH", "reference": "Pinnacle",
           "match_id": "betclic|2", "cloture_lue": None}
    index = {"Pinnacle": {"betclic|2": {("VAINQUEUR", "MATCH", None, "DOM"): {"proba_juste": 0.6, "collecte": plus_tard}}}}
    simulation.suivre_cloture([aog], comparaison.cotes_justes_depuis(index))
    assert aog["clv_minimum"] is True and aog["clv"] == round(1.62 * 0.6 - 1, 4)


def test_bilans_ne_lisent_pas_une_borne_comme_une_probabilite():
    base = {"simulation": "A", "mise": 10, "reference": "Polymarket", "marche": "TOTAL", "periode": "MATCH",
            "ligne": 2.5, "joueur": None, "cote": 2.0, "cote_juste": 2.5, "detecte": "1", "bookmaker": "Betclic",
            "sport": "football", "issue": "PLUS", "ecart": 0.03}
    prudents = [{**base, "match_id": f"b|{i}", "statut": "gagne" if i < 6 else "perdu", "gain": 10.0 if i < 6 else -10.0,
                 "ecart_minimum": True, "prix_prudent": True, "proba_milieu": 0.5} for i in range(12)]
    assert simulation.proba_attendue(prudents[0]) == 0.5 and simulation.proba_attendue(base) == 0.4
    seg = simulation.segments(prudents)[0]
    assert seg["attendus"] == 6.0 and seg["ecart_sigma"] == 0          # 6 gagnés pour 6 attendus au milieu du carnet
    assert "probabilites_minorees" not in seg["sigma_limites"]
    aog = [{**p, "marche": "AVANCE_OU_GAGNE", "prix_prudent": False, "proba_milieu": None} for p in prudents]
    seg = simulation.segments(aog)[0]
    assert seg["attendus"] == 4.8 and "probabilites_minorees" in seg["sigma_limites"] and not seg["sigma_fiable"]
    # moyenne des écarts contre Polymarket : les bornes sont comptées à part
    exacts = [{**base, "match_id": f"e|{i}", "statut": "gagne", "gain": 10.0, "ecart": 0.05} for i in range(3)]
    m = simulation.moyennes_ecarts(prudents + exacts)["Polymarket"]
    assert m == {"moyenne": 0.05, "n": 3, "minimums": 12}
