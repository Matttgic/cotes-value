"""Flashscore : lecture du flux texte, sans réseau."""
from datetime import datetime, timezone

from cotes import flashscore, resultats

MAINTENANT = datetime(2026, 10, 18, 12, tzinfo=timezone.utc)


def _bloc(**kw):
    base = {"AA": "x", "AB": "3", "AC": "3", "AD": "1792087200", "AE": "Oudegem F", "AF": "Gent F",
            "AG": "3", "AH": "1", "BA": "25", "BB": "21", "BC": "23", "BD": "25", "BE": "25", "BF": "19",
            "BG": "25", "BH": "22"}
    return "¬".join(f"{k}÷{v}" for k, v in (base | kw).items())


def test_volley_sets_et_points_par_set():
    texte = "SA÷12¬~ZA÷BELGIQUE: Volley¬~" + _bloc() + "¬~"
    [d] = list(flashscore.lignes(texte))
    r = flashscore.match("volley", d)
    assert r["score"] == (3, 1) and r["periodes"] == [(25, 21), (23, 25), (25, 19), (25, 22)]
    assert r["debut"] == datetime.fromtimestamp(1792087200, timezone.utc)
    assert flashscore.match("volley", {**d, "BC": "30"})["periodes"] == []        # points incohérents avec les sets


def test_seuls_les_matchs_termines_normalement_comptent():
    d = dict(kv.split("÷", 1) for kv in _bloc().split("¬"))
    for ac in ("10", "11", "54", "4", "5", "9", "8"):
        assert flashscore.match("handball", {**d, "AC": ac}) is None
    assert flashscore.match("handball", {**d, "AB": "1"}) is None
    assert flashscore.match("handball", {**d, "AG": ""}) is None


def test_handball_mi_temps_si_elles_font_le_score():
    d = {"AB": "3", "AC": "3", "AD": "1792087200", "AE": "A", "AF": "B", "AG": "30", "AH": "35",
         "BA": "17", "BB": "17", "BC": "13", "BD": "18"}
    assert flashscore.match("handball", d)["periodes"] == [(17, 17), (13, 18)]
    assert flashscore.match("handball", {**d, "AG": "31"})["periodes"] == []


def test_jours_hors_fenetre_ignores_et_panne_notee():
    class Panne:
        ok = False
        status_code = 500
        text = ""

    class Http:
        urls = []

        def get(self, url, **kw):
            self.urls.append(url)
            return Panne()

    http = Http()
    avant = len(flashscore.ERREURS)
    assert flashscore.lire("volley", ["2026-10-17", "2026-09-01", "2026-10-20"], MAINTENANT, http) == []
    assert len(http.urls) == 1 and http.urls[0].endswith("/f_12_-1_0_fr-fr_1")
    assert len(flashscore.ERREURS) == avant + 1


def test_une_source_seule_ne_regle_qu_apres_24_heures():
    p = {"statut": "a_regler", "match_id": "x|1", "sport": "volley", "domicile": "Oudegem F", "exterieur": "Gent F",
         "debut": "2026-10-17T10:00:00Z", "periode": "MATCH", "marche": "VAINQUEUR", "issue": "DOM"}
    d = dict(kv.split("÷", 1) for kv in _bloc(AD=str(int(datetime(2026, 10, 17, 10, tzinfo=timezone.utc).timestamp()))).split("¬"))
    rec = [flashscore.match("volley", d)]
    assert resultats.consensus(p, rec, datetime(2026, 10, 17, 20, tzinfo=timezone.utc)) is None
    r = resultats.consensus(p, rec, datetime(2026, 10, 18, 11, tzinfo=timezone.utc))
    assert r and r["score"] == (3, 1) and r["sources"] == ["flashscore"]
    assert flashscore.jours_a_lire([p], MAINTENANT) == {"volley": ["2026-10-16", "2026-10-17"]}


def _pari(**kw):
    return {"statut": "a_regler", "match_id": "x|1", "sport": "hockey", "domicile": "Eisbären Berlin",
            "exterieur": "EC-KAC", "debut": "2026-10-14T17:30:00Z", "periode": "MATCH", "marche": "VAINQUEUR",
            "issue": "DOM", "ligue": "Champions Hockey League"} | kw


def _rec(dom, ext, debut=datetime(2026, 10, 14, 17, 30, tzinfo=timezone.utc), source="flashscore", score=(2, 1)):
    return {"source": source, "sport": "hockey", "domicile": dom, "exterieur": ext, "debut": debut, "score": score,
            "periodes": [], "libelles": [], "corners": None}


def test_meme_equipe_meme_heure_suffit_quand_l_autre_nom_est_inconnu():
    trouves = resultats.retrouver(_pari(), [_rec("Eisbaren Berlin", "Klagenfurt")])
    assert [r["score"] for r in trouves] == [(2, 1)]
    # l'équipe de l'extérieur du pari est celle du domicile de la source : le score est retourné
    inverse = resultats.retrouver(_pari(), [_rec("Klagenfurt", "Eisbaren Berlin", score=(1, 2))])
    assert [r["score"] for r in inverse] == [(2, 1)]
    # trop loin du coup d'envoi, ou deux candidats d'une même source : aucun
    assert resultats.retrouver(_pari(), [_rec("Eisbaren Berlin", "Klagenfurt", datetime(2026, 10, 14, 18, 30, tzinfo=timezone.utc))]) == []
    assert resultats.retrouver(_pari(), [_rec("Eisbaren Berlin", "Klagenfurt"), _rec("Eisbaren Berlin", "Autre")]) == []
    # une autre équipe : rien
    assert resultats.retrouver(_pari(), [_rec("Zurich", "Klagenfurt")]) == []


def test_ligue_feminine_suffit_quand_les_noms_n_ont_pas_de_marqueur():
    pari = _pari(sport="volley", domicile="LKS Lodz", exterieur="Stal Mielec", ligue="Tauron Liga (F)",
                 debut="2026-10-15T15:30:00Z")
    rec = {**_rec("LKS Lodz F", "Stal Mielec F", datetime(2026, 10, 15, 15, 30, tzinfo=timezone.utc), score=(3, 1)),
           "sport": "volley"}
    assert [r["score"] for r in resultats.retrouver(pari, [rec])] == [(3, 1)]
    assert resultats.retrouver({**pari, "ligue": "Tauron Liga"}, [rec]) == []


def test_hockey_flashscore_seul_regle_apres_24_heures_pas_une_autre_source():
    pari = _pari()
    seule = [_rec("Eisbären Berlin", "EC-KAC")]
    assert resultats.consensus(pari, seule, datetime(2026, 10, 14, 23, tzinfo=timezone.utc)) is None
    assert resultats.consensus(pari, seule, datetime(2026, 10, 15, 18, tzinfo=timezone.utc))["score"] == (2, 1)
    autre = [_rec("Eisbären Berlin", "EC-KAC", source="unibet-uk")]
    assert resultats.consensus(pari, autre, datetime(2026, 10, 15, 18, tzinfo=timezone.utc)) is None


def test_mi_temps_du_rugby_et_du_handball():
    from cotes import reglement
    sc = reglement.scores_par_periode("rugby", (49, 28), [(35, 0), (14, 28)], ["1", "2"])
    assert sc["MT1"] == (35, 0) and sc["MT2"] == (14, 28) and sc["MATCH"] == (49, 28)
    p = {"marche": "TOTAL", "periode": "MT1", "issue": "PLUS", "ligne": 30.5, "sport": "rugby"}
    assert reglement.regler(p, sc) == "gagne"


def test_hockey_et_basket_periodes_reglementaires():
    h = {"AB": "3", "AC": "3", "AD": "1792087200", "AE": "A", "AF": "B", "AG": "4", "AH": "7",
         "BA": "1", "BB": "3", "BC": "2", "BD": "3", "BE": "1", "BF": "1"}
    r = flashscore.match("hockey", h)
    assert r["periodes"] == [(1, 3), (2, 3), (1, 1)] and r["libelles"] == ["1", "2", "3"]
    assert flashscore.match("hockey", {**h, "AG": "5"})["periodes"] == []
    b = {"AB": "3", "AC": "3", "AD": "1792087200", "AE": "A", "AF": "B", "AG": "70", "AH": "84",
         "BA": "14", "BB": "21", "BC": "23", "BD": "18", "BE": "19", "BF": "27", "BG": "14", "BH": "18"}
    assert len(flashscore.match("basket", b)["periodes"]) == 4
