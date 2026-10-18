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
