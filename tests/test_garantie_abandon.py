"""Garantie Abandon Winamax (tennis) : abandon après le 1er set, le pari « vainqueur » sur le joueur qui reste est gagné.

Cas réel : Pridankina – Badosa, Hong Kong, 3/11/2026, 7-5 puis abandon de Badosa ; pari Winamax sur Pridankina à
3,70 réglé « remboursé » avant cette règle."""
from datetime import datetime, timedelta, timezone

from cotes import resultats as R
from cotes.reglement import appliquer, regler, scores_par_periode

T = datetime(2026, 11, 3, 2, 0, tzinfo=timezone.utc)


def _scoreboard(tableau: str, gagnant_dom: bool, jeux=((7, 5),)):
    c = {"id": "1", "date": "2026-11-03T02:00Z", "status": {"type": {"name": "STATUS_RETIRED"}},
         "competitors": [
             {"homeAway": "home", "winner": gagnant_dom, "athlete": {"displayName": "Adrian Mannarino"},
              "linescores": [{"value": a} for a, _ in jeux]},
             {"homeAway": "away", "winner": not gagnant_dom, "athlete": {"displayName": "Nikoloz Basilashvili"},
              "linescores": [{"value": b} for _, b in jeux]}]}
    return {"events": [{"id": "e", "groupings": [{"grouping": {"slug": tableau}, "competitions": [c]}]}]}


def _lire(tableau, gagnant_dom=True, jeux=((7, 5),)):
    data = _scoreboard(tableau, gagnant_dom, jeux)
    return R.lire_espn("tennis", T, T + timedelta(hours=1), lire_json=lambda chemin, params=None: data)


def _pari(bookmaker, issue, inverse=False):
    dom, ext = ("Nikoloz Basilashvili", "Adrian Mannarino") if inverse else ("Adrian Mannarino", "Nikoloz Basilashvili")
    return {"id": f"{bookmaker}{issue}{inverse}", "sport": "tennis", "domicile": dom, "exterieur": ext,
            "debut": "2026-11-03T02:00:00Z", "match_id": f"{bookmaker}|{inverse}", "statut": "a_regler",
            "marche": "VAINQUEUR", "periode": "MATCH", "issue": issue, "ligne": None, "mise": 10, "cote": 3.7,
            "bookmaker": bookmaker}


def _regle(pari, enregistrements):
    r = R.consensus(pari, enregistrements, T + timedelta(hours=12))
    appliquer([pari], {pari["match_id"]: r}, {}, T + timedelta(hours=12))
    return pari["statut"]


def test_espn_donne_le_vainqueur_sur_abandon_en_simple_seulement():
    simple = _lire("mens-singles")
    assert simple[0]["abandon"] is True and simple[0]["abandon_vainqueur"] == "DOM"
    assert "abandon_vainqueur" not in _lire("mens-doubles")[0]                 # double : hors garantie


def test_winamax_paye_le_joueur_qui_reste_et_rembourse_celui_qui_abandonne():
    enr = _lire("mens-singles")
    assert _regle(_pari("Winamax", "DOM"), enr) == "gagne"
    assert _regle(_pari("Winamax", "EXT"), enr) == "rembourse"
    assert _regle(_pari("PMU", "DOM"), enr) == "rembourse"                    # autres bookmakers : règle d'avant
    # match noté à l'envers par le bookmaker : le vainqueur est retourné avec le score
    assert _regle(_pari("Winamax", "EXT", inverse=True), enr) == "gagne"
    assert _regle(_pari("Winamax", "DOM", inverse=True), enr) == "rembourse"


def test_abandon_pendant_le_premier_set_ou_vainqueur_inconnu_rembourse():
    pendant = _lire("mens-singles", jeux=((4, 2),))
    assert _regle(_pari("Winamax", "DOM"), pendant) == "rembourse"            # aucun set terminé
    double = _lire("mens-doubles")
    assert _regle(_pari("Winamax", "DOM"), double) == "rembourse"


def test_regle_et_frere_inverse():
    s = scores_par_periode("tennis", (1, 0), [(6, 4), (3, 1)], ["1", "2"])
    winamax = {"marche": "VAINQUEUR", "issue": "EXT", "ligne": None, "periode": "MATCH", "bookmaker": "Winamax"}
    assert regler(winamax, {**s, "VAINQUEUR_ABANDON": "EXT"}) == "gagne"
    assert regler({**winamax, "periode": "SET1"}, {**s, "VAINQUEUR_ABANDON": "EXT"}) == "perdu"   # set 1 terminé
    assert regler({**winamax, "marche": "HANDICAP", "ligne": 1.5}, {**s, "VAINQUEUR_ABANDON": "EXT"}) == "rembourse"
    assert R._inverser_scores({**s, "VAINQUEUR_ABANDON": "EXT"})["VAINQUEUR_ABANDON"] == "DOM"
