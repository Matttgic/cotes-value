"""Règlement : match frère chez un autre bookmaker, faux reports, corrections et contrôle de cohérence."""
from datetime import datetime, timedelta, timezone

from cotes import reglement
from cotes import resultats as R

T = datetime(2026, 10, 28, 19, 30, tzinfo=timezone.utc)
APRES = T + timedelta(hours=8)


def pari(pid, bookmaker, dom, ext, statut="a_regler", marche="RESULTAT_1N2", issue="NUL", periode="MATCH",
         sport="football", debut="2026-10-28T19:30:00Z", **plus):
    return {"id": pid, "match_id": f"{bookmaker.lower()}|{pid}", "bookmaker": bookmaker, "sport": sport,
            "domicile": dom, "exterieur": ext, "debut": debut, "statut": statut, "marche": marche, "issue": issue,
            "periode": periode, "ligne": None, "cote": 4.4, "mise": 10, "gain": None, **plus}


def regle(p, statut, scores, sources=("livescore",), origine="automatique", **preuve):
    return {**p, "statut": statut, "gain": reglement.gain(statut, 10, p["cote"]), "regle_le": "2026-10-29T01:31:42+00:00",
            "preuve_reglement": {"origine": origine, "sources": list(sources), "score": scores.get("MATCH"),
                                 "periodes": [], "scores": scores, **preuve}}


def test_un_pari_est_regle_par_le_meme_match_deja_regle_chez_un_autre_bookmaker():
    frere = regle(pari("a", "PMU", "Manchester City", "Brighton", issue="DOM"), "perdu",
                  {"MATCH": [2, 2], "MT1": [1, 1], "MT2": [1, 1]})
    p = pari("b", "Winamax", "Manchester City", "Brighton")
    mi_temps = pari("c", "Winamax", "Manchester City", "Brighton", periode="MT1", issue="DOM")
    mi_temps["match_id"] = p["match_id"]
    paris = [frere, p, mi_temps]
    ajouts = R.par_freres(paris, {}, APRES)
    assert set(ajouts) == {p["match_id"]} and ajouts[p["match_id"]]["frere"]["bookmaker"] == "PMU"
    reglement.appliquer(paris, ajouts, {}, APRES)
    assert p["statut"] == "gagne" and mi_temps["statut"] == "perdu"            # 2-2, et 1-1 à la mi-temps
    assert p["preuve_reglement"]["frere"]["match_id"] == frere["match_id"]
    assert p["preuve_reglement"]["sources"] == ["livescore"] and p["preuve_reglement"]["scores"]["MATCH"] == (2, 2)
    # un pari réglé par un frère ne sert pas de frère à son tour (pas de chaîne)
    autre = pari("d", "NetBet", "Manchester City", "Brighton")
    assert R.par_freres([p, mi_temps, autre], {}, APRES) == {}


def test_frere_aux_equipes_inversees_et_resultat_du_cycle():
    # le résultat validé à ce cycle pour un bookmaker sert au même match chez un autre, équipes inversées
    ouvert = pari("a", "Unibet", "Cisneros Alter", "Manacor", sport="volley", marche="VAINQUEUR", issue="DOM")
    p = pari("b", "PMU", "Manacor", "Cisneros Alter", sport="volley", marche="VAINQUEUR", issue="DOM")
    resultats = {ouvert["match_id"]: {"sport": "volley", "score": (1, 3), "final": True, "periodes": [(20, 25), (25, 21), (18, 25), (22, 25)],
                                      "libelles": ["1", "2", "3", "4"], "corners": None, "sources": ["flashscore"]}}
    ajouts = R.par_freres([ouvert, p], resultats, APRES)
    r = ajouts[p["match_id"]]
    assert r["score"] == (3, 1) and r["periodes"][0] == (25, 20) and r["frere"]["inverse"] is True
    reglement.appliquer([ouvert, p], {**resultats, **ajouts}, {}, APRES)
    assert ouvert["statut"] == "perdu" and p["statut"] == "gagne"
    # scores déjà enregistrés d'un frère inversé : chaque couple est retourné, pas les autres valeurs
    frere = regle(pari("c", "Unibet", "Cisneros Alter", "Manacor", sport="tennis"), "perdu",
                  {"MATCH": [0, 2], "JEUX": [7, 12], "SETS_TERMINES": 2, "SET1": [3, 6]})
    q = pari("d", "PMU", "Manacor", "Cisneros Alter", sport="tennis", marche="VAINQUEUR", issue="DOM")
    sc = R.par_freres([frere, q], {}, APRES)[q["match_id"]]["scores"]
    assert sc == {"MATCH": (2, 0), "JEUX": (12, 7), "SETS_TERMINES": 2, "SET1": (6, 3)}


def test_pas_de_frere_sans_certitude():
    frere = regle(pari("a", "PMU", "Manchester City", "Brighton"), "gagne", {"MATCH": [2, 2]})
    cas = {
        "autre heure": pari("b", "Winamax", "Manchester City", "Brighton", debut="2026-10-31T15:00:00Z"),
        "féminines": pari("c", "Winamax", "Manchester City (F)", "Brighton (F)"),
        "autre sport": pari("d", "Winamax", "Manchester City", "Brighton", sport="basket"),
        "autre adversaire": pari("e", "Winamax", "Manchester City", "Brentford"),
    }
    for nom, p in cas.items():
        assert R.par_freres([frere, p], {}, APRES + timedelta(days=4)) == {}, nom
    proche = pari("f", "Winamax", "Manchester City", "Brighton")
    assert R.par_freres([frere, proche], {}, T + timedelta(hours=1)) == {}            # match pas encore fini
    assert R.par_freres([frere, proche], {}, APRES) != {}
    # un statut saisi à la main, un forfait ou un résultat réservé à certains paris ne se propagent pas
    manuel = {**frere, "preuve_reglement": {"origine": "statut saisi à la main"}}
    assert R.par_freres([manuel, proche], {}, APRES) == {}
    reserve = pari("g", "Betclic", "Manchester City", "Brighton", statut="en_cours")
    res = {reserve["match_id"]: {"sport": "football", "score": (2, 2), "final": True, "periodes": [], "libelles": [],
                                 "sources": ["theodds"], "id_paris_autorises": ["g"]}}
    assert R.par_freres([reserve, proche], res, APRES) == {}
    # deux frères qui ne racontent pas le même match : on ne tranche pas
    faux = regle(pari("h", "NetBet", "Manchester City", "Brighton"), "perdu", {"MATCH": [0, 1]})
    assert R.par_freres([frere, faux, proche], {}, APRES) == {}


def test_une_affiche_rejouee_trois_jours_plus_tard_n_est_pas_un_report():
    p = pari("a", "Winamax", "Manchester City", "Brighton")
    base = {"sport": "football", "domicile": "Manchester City", "exterieur": "Brighton & Hove Albion",
            "periodes": [], "libelles": [], "corners": None}
    championnat = {**base, "source": "espn", "debut": T + timedelta(days=2, hours=19, minutes=30), "score": (0, 0),
                   "a_venir": True}
    # seul le match de championnat est connu, à venir : report plausible, comme avant
    assert R.reporte(p, [championnat]) == championnat["debut"]
    # le match de coupe a un score chez une source à sa date : il a eu lieu, ce n'est pas un report
    coupe = {**base, "source": "livescore", "debut": T, "score": (2, 2)}
    assert R.reporte(p, [championnat, coupe]) is None
    # et un pari déjà noté « reporté » par erreur est rattrapé par son frère réglé à la date d'origine
    frere = regle(pari("b", "PMU", "Manchester City", "Brighton"), "gagne", {"MATCH": [2, 2]})
    note = {**p, "statut": "en_cours", "reporte_au": "2026-10-31T15:00:00+00:00"}
    ajouts = R.par_freres([frere, note], {}, APRES)
    reglement.appliquer([frere, note], ajouts, {}, APRES)
    assert note["statut"] == "gagne"


def test_corriger_un_pari_deja_regle_par_son_identifiant():
    p = regle(pari("021816f8", "Winamax", "Manchester City", "Brighton"), "perdu", {"MATCH": [0, 1]},
              sources=("espn", "livescore"))
    reglement.appliquer([p], {}, {"021816f8": "gagne"}, APRES)
    assert p["statut"] == "gagne" and p["gain"] == 34.0 and p["regle_le"] == "2026-10-29T01:31:42+00:00"
    assert p["preuve_reglement"]["ancien_statut"] == "perdu" and p["preuve_reglement"]["anciennes_sources"] == ["espn", "livescore"]
    assert p["preuve_reglement"]["origine"] == "statut saisi à la main" and p["preuve_reglement"]["corrige_le"]
    trace = dict(p["preuve_reglement"])
    reglement.appliquer([p], {}, {"021816f8": "gagne"}, APRES + timedelta(hours=1))     # déjà corrigé : rien ne bouge
    assert p["preuve_reglement"] == trace
    q = regle(pari("x", "PMU", "A", "B"), "gagne", {"MATCH": [1, 1]})
    for valeur in (None, "inconnu", {"score": [1, 0]}, "supprime"):                       # rien d'autre ne corrige
        reglement.appliquer([q], {}, {"x": valeur}, APRES)
        assert q["statut"] == "gagne" and q["preuve_reglement"]["origine"] == "automatique"
    assert reglement.corriger({"statut": "en_cours", "mise": 10, "cote": 2.0}, "gagne", APRES) is False


def test_meme_match_deux_scores_est_signale():
    a = regle(pari("a", "PMU", "Manchester City", "Brighton"), "gagne", {"MATCH": [2, 2]})
    a2 = regle({**pari("a2", "PMU", "Manchester City", "Brighton"), "match_id": a["match_id"]}, "perdu", {"MATCH": [2, 2]})
    b = regle(pari("b", "Winamax", "Manchester City", "Brighton"), "perdu", {"MATCH": [0, 1]}, sources=("espn", "livescore"))
    c = regle(pari("c", "NetBet", "Brighton", "Manchester City"), "perdu", {"MATCH": [2, 2]})         # inversé, d'accord
    d = regle(pari("d", "Betclic", "Arsenal", "Chelsea"), "perdu", {"MATCH": [0, 3]})                  # autre match
    e = regle(pari("e", "Unibet", "Manchester City", "Brighton"), "gagne", {"MATCH": [9, 9]}, frere={"match_id": "x"})
    inc = R.incoherences_freres([a, a2, b, c, d, e])
    assert len(inc) == 2 and all("Winamax" in (x["a"]["bookmaker"], x["b"]["bookmaker"]) for x in inc)
    pmu = next(x for x in inc if x["a"]["bookmaker"] == "PMU")
    assert pmu["a"]["score"] == [2, 2] and pmu["b"]["score"] == [0, 1] and pmu["a"]["paris"] == ["a", "a2"]
    assert R.incoherences_freres([a, c, d]) == []
