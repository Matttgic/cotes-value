"""Forfaits et abandons au tennis, mi-temps du football, noms abrégés : les paris restés « à régler » le 3/11/2026."""
from datetime import datetime, timedelta, timezone

from cotes import flashscore, reglement, resultats as R
from cotes.correspondance import ressemblance

DEBUT = datetime(2026, 11, 2, 2, 0, tzinfo=timezone.utc)


def _flux(**kw):
    base = {"AA": "x", "AB": "3", "AC": "3", "AD": str(int(DEBUT.timestamp())), "AE": "Quevedo K.", "AF": "Badosa P."}
    return base | kw


def pari(sport="tennis", dom="Kaitlin Quevedo", ext="Paula Badosa", debut=DEBUT, **kw):
    return {"id": "p1", "match_id": "pmu|1", "sport": sport, "domicile": dom, "exterieur": ext,
            "debut": debut.isoformat().replace("+00:00", "Z"), "statut": "en_cours", "periode": "MATCH",
            "marche": "VAINQUEUR", "issue": "DOM", "ligne": None, "mise": 10, "cote": 2.0, "bookmaker": "pmu",
            "ligue": "", "detecte": "2026-11-01T10:00:00Z", **kw}


def test_forfait_avant_le_match_donne_un_match_annule():
    r = flashscore.match("tennis", _flux(AC="5", AM="Quevedo Kaitlin - forfait."))
    assert r["annule"] is True and r["score"] == (0, 0) and r["periodes"] == []
    assert flashscore.match("tennis", _flux(AC="9"))["annule"] is True            # walkover
    # un code 5 sans le mot « forfait » (autre sens possible) et un sport collectif restent ignorés
    assert flashscore.match("tennis", _flux(AC="5")) is None
    assert flashscore.match("volley", _flux(AC="5", AM="x - forfait.")) is None


def test_abandon_en_cours_de_match():
    r = flashscore.match("tennis", _flux(AC="8", AG="1", AH="0", BA="7", BB="5", BC="0", BD="0"))
    assert r["abandon"] is True and r["score"] == (1, 0) and r["periodes"] == [(7, 5)]    # set non commencé retiré
    assert not r.get("annule")
    assert flashscore.match("tennis", _flux(AC="8")) is None                       # abandon sans aucun score


def test_forfait_regle_tous_les_paris_rembourses_apres_deux_heures():
    annule = flashscore.match("tennis", _flux(AC="5", AM="Quevedo Kaitlin - forfait."))
    p = pari()
    assert R.consensus(p, [annule], DEBUT + timedelta(hours=1)) is None             # trop tôt
    r = R.consensus(p, [annule], DEBUT + timedelta(hours=3))
    assert r["annule"] is True and r["sources"] == ["flashscore"]
    for marche, issue, ligne in (("VAINQUEUR", "DOM", None), ("SETS_TOTAL", "MOINS", 2.5)):
        q = pari(marche=marche, issue=issue, ligne=ligne)
        reglement.appliquer([q], {q["match_id"]: r}, {}, DEBUT + timedelta(hours=3))
        assert q["statut"] == "rembourse" and q["gain"] == 0
        assert q["preuve_reglement"]["annule"] is True


def test_forfait_avec_match_decale_d_un_jour_et_noms_abreges():
    decale = flashscore.match("tennis", _flux(AC="5", AM="Davidovich Fokina Alejandro - forfait.",
                                             AD=str(int((DEBUT + timedelta(hours=33)).timestamp())),
                                             AE="Davidovich Fokina A.", AF="Kouamé M."))
    p = pari(dom="Alejandro Davidovich-Fokina", ext="Moïse Kouame", issue="EXT")
    assert R.consensus(p, [decale], DEBUT + timedelta(days=2))["annule"] is True
    autre_jour = {**decale, "debut": DEBUT + timedelta(days=4)}
    assert R.consensus(p, [autre_jour], DEBUT + timedelta(days=6)) is None          # trop loin : pas le même match


def test_abandon_rembourse_le_vainqueur_meme_si_le_detail_des_sets_est_incoherent():
    # 1-1 en sets, abandon dans le 3e : le détail (2 sets pour le domicile) contredit le score et serait jeté
    e = {"source": "flashscore", "sport": "tennis", "domicile": "Quevedo K.", "exterieur": "Badosa P.", "debut": DEBUT,
         "score": (1, 1), "periodes": [(3, 6), (7, 6), (2, 0)], "libelles": ["1", "2", "3"], "corners": None, "abandon": True}
    p = pari()
    r = R.consensus(p, [e, {**e, "source": "espn"}], DEBUT + timedelta(hours=5))
    assert r["abandon"] is True
    reglement.appliquer([p], {p["match_id"]: r}, {}, DEBUT + timedelta(hours=5))
    assert p["statut"] == "rembourse"
    # le même score sans abandon réglerait sur le score : le drapeau fait la différence
    sans = {**r}
    sans.pop("abandon")
    q = pari()
    reglement.appliquer([q], {q["match_id"]: {**sans, "score": (2, 1), "periodes": []}}, {}, DEBUT + timedelta(hours=5))
    assert q["statut"] == "gagne"


def test_football_premiere_mi_temps_deduite_de_la_deuxieme():
    d = {"AB": "3", "AC": "3", "AD": "1793635200", "AE": "VPS", "AF": "HJK", "AG": "0", "AH": "4", "BC": "0", "BD": "1"}
    r = flashscore.match("football", d)
    assert r["periodes"] == [(0, 3), (0, 1)] and r["libelles"] == ["1", "2"]
    assert flashscore.match("football", {**d, "BC": "1"})["periodes"] == []        # 2e mi-temps > score final : incohérent
    complet = flashscore.match("football", {**d, "BA": "0", "BB": "2", "BC": "0", "BD": "2"})
    assert complet["periodes"] == [(0, 2), (0, 2)]                                  # le flux complet prime


def test_noms_abreges_et_initiale_b():
    assert ressemblance("Ben Woollaston", "Woollaston B.") >= 0.85                  # « B. » n'est pas l'équipe B
    assert ressemblance("Nilüfer Belediyespor (F)", "Nilufer Bld. F") >= 0.85
    assert ressemblance("Real Madrid B.", "Real Madrid") < 0.9                      # la vraie équipe B reste distincte
    assert ressemblance("Bayern", "Barcelona") < 0.6
    assert ressemblance("Nilufer Bld.", "Nilufer Basket") < 0.85                    # « bld » n'abrège pas « basket »
