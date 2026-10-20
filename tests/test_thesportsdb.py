"""TheSportsDB : secours de règlement, sans réseau."""
from datetime import datetime, timedelta, timezone

import requests

from cotes import resultats, thesportsdb

DEBUT = datetime(2026, 10, 19, 19, 0, tzinfo=timezone.utc)
MAINTENANT = DEBUT + timedelta(hours=30)


def _e(**kw):
    base = {"idEvent": "2494064", "strSport": "Soccer", "strStatus": "FT", "strHomeTeam": "Tottenham Hotspur",
            "strAwayTeam": "Coventry City", "intHomeScore": "3", "intAwayScore": "1",
            "strTimestamp": "2026-10-19T19:00:00", "strPostponed": "no"}
    return base | kw


def _pari(**kw):
    base = {"match_id": "m1", "sport": "football", "domicile": "Tottenham", "exterieur": "Coventry",
            "statut": "en_cours", "debut": DEBUT.isoformat(), "match_reference": "Tottenham Hotspur - Coventry City"}
    return base | kw


class Rep:
    ok = True
    status_code = 200

    def __init__(self, corps):
        self.corps = corps

    def json(self):
        return self.corps


class Http:
    def __init__(self, *reponses):
        self.reponses = list(reponses)
        self.appels = []

    def get(self, url, **kw):
        self.appels.append((url, kw["params"]["e"]))
        r = self.reponses.pop(0) if self.reponses else Rep({"event": None})
        if isinstance(r, Exception):
            raise r
        return r


def test_match_termine_au_format_des_validateurs():
    r = thesportsdb.match("football", _e())
    assert r["source"] == "thesportsdb" and r["score"] == (3, 1) and r["debut"] == DEBUT
    assert r["domicile"] == "Tottenham Hotspur" and r["periodes"] == [] and r["corners"] is None


def test_ignores_non_termines_reports_et_scores_absents():
    assert thesportsdb.match("football", _e(strStatus="NS", intHomeScore=None, intAwayScore=None)) is None
    assert thesportsdb.match("football", _e(strStatus="AET")) is None            # prolongation : pas le temps réglementaire
    assert thesportsdb.match("football", _e(strStatus="PEN")) is None
    assert thesportsdb.match("football", _e(strPostponed="yes")) is None
    assert thesportsdb.match("football", _e(intAwayScore=None)) is None
    assert thesportsdb.match("football", _e(strTimestamp=None, dateEvent=None)) is None
    assert thesportsdb.match("tennis", _e()) is None                              # tennis non couvert
    assert thesportsdb.match("basket", _e(strStatus="AOT"))["score"] == (3, 1)    # prolongation comprise au basket


def test_requetes_noms_du_bookmaker_puis_reference():
    assert thesportsdb.requetes(_pari()) == ["Tottenham_vs_Coventry", "Tottenham_Hotspur_vs_Coventry_City"]
    p = _pari(match_reference=None)
    assert thesportsdb.requetes(p) == ["Tottenham_vs_Coventry", "Coventry_vs_Tottenham"]


def test_collecte_cherche_une_fois_par_match_et_garde_en_cache():
    http = Http(Rep({"event": None}), Rep({"event": [_e(), _e(strHomeTeam="Autre", idEvent="9", strStatus="NS")]}))
    cache, pauses = {}, []
    paris = [_pari(), _pari(match_id="m1", domicile="Spurs")]                    # même match chez deux bookmakers
    out = thesportsdb.collecter(paris, cache, MAINTENANT, http=http, pause=pauses.append)
    assert [m["score"] for m in out] == [(3, 1)] and len(http.appels) == 2 and len(pauses) == 1
    assert cache["m1"]["matchs"][0]["debut"] == DEBUT.isoformat()
    http2 = Http()
    again = thesportsdb.collecter(paris, cache, MAINTENANT + timedelta(hours=1), http=http2, pause=pauses.append)
    assert http2.appels == [] and again[0]["debut"] == DEBUT and again[0]["score"] == (3, 1)   # relu du cache


def test_match_absent_reessaye_apres_delai_seulement():
    http = Http()
    cache = {}
    assert thesportsdb.collecter([_pari()], cache, MAINTENANT, http=http, pause=lambda s: None) == []
    n = len(http.appels)
    thesportsdb.collecter([_pari()], cache, MAINTENANT + timedelta(hours=1), http=http, pause=lambda s: None)
    assert len(http.appels) == n
    thesportsdb.collecter([_pari()], cache, MAINTENANT + timedelta(hours=4), http=http, pause=lambda s: None)
    assert len(http.appels) > n


def test_panne_notee_sans_arreter_le_cycle():
    http = Http(requests.ConnectionError("coupure"), Rep({"event": "pas une liste"}))
    n = len(thesportsdb.ERREURS)
    assert thesportsdb.collecter([_pari()], {}, MAINTENANT, http=http, pause=lambda s: None) == []
    assert len(thesportsdb.ERREURS) == n + 2


def test_paris_a_chercher_ouverts_couverts_et_dans_la_fenetre():
    paris = [_pari(), _pari(match_id="m2", statut="gagne"), _pari(match_id="m3", sport="tennis"),
             _pari(match_id="m4", debut=(MAINTENANT - timedelta(hours=1)).isoformat()),
             _pari(match_id="m5", debut=(MAINTENANT - timedelta(days=9)).isoformat())]
    assert [p["match_id"] for p in thesportsdb.a_chercher(paris, MAINTENANT)] == ["m1"]


def test_plafond_d_appels_par_cycle():
    paris = [_pari(match_id=f"m{i}", domicile=f"Equipe{i}", exterieur=f"Autre{i}", match_reference=None)
             for i in range(thesportsdb.MAX_APPELS + 5)]
    http, cache = Http(), {}
    thesportsdb.collecter(paris, cache, MAINTENANT, http=http, pause=lambda s: None)
    assert len(http.appels) == thesportsdb.MAX_APPELS
    assert len(cache) < len(paris)                                               # les derniers seront cherchés au cycle suivant


def test_seule_elle_ne_regle_qu_apres_24_heures_et_jamais_au_hockey():
    r = thesportsdb.match("football", _e())
    pari = _pari()
    assert resultats.consensus(pari, [r], DEBUT + timedelta(hours=10)) is None
    assert resultats.consensus(pari, [r], DEBUT + timedelta(hours=25))["score"] == (3, 1)
    hockey = thesportsdb.match("hockey", _e(strSport="Ice Hockey"))
    assert resultats.consensus(_pari(sport="hockey"), [hockey], DEBUT + timedelta(hours=48)) is None


def test_d_accord_avec_une_autre_source_elle_regle_tout_de_suite():
    r = thesportsdb.match("football", _e())
    autre = {"source": "flashscore", "sport": "football", "domicile": "Tottenham Hotspur",
             "exterieur": "Coventry City", "debut": DEBUT, "score": (3, 1), "periodes": [], "libelles": [],
             "corners": None, "abandon": False}
    res = resultats.consensus(_pari(), [r, autre], DEBUT + timedelta(hours=3))
    assert res["score"] == (3, 1) and res["sources"] == ["flashscore", "thesportsdb"]


# --- correctifs issus du diagnostic des matchs en attente (20 oct. 2026) -------------------------------------

def _enr(source, sport, dom, ext, debut, score):
    return {"source": source, "sport": sport, "domicile": dom, "exterieur": ext, "debut": debut, "score": score,
            "periodes": [], "libelles": [], "corners": None}


def test_volley_vb_n_est_pas_une_equipe_b():
    p = {"match_id": "v1", "sport": "volley", "domicile": "Toulouse V.B.", "exterieur": "Arago de Sète",
         "debut": "2026-10-17T16:00:00.000Z", "match_reference": "Toulouse - Arago de Sete", "statut": "a_regler"}
    d = datetime(2026, 10, 17, 16, 0, tzinfo=timezone.utc)
    r = _enr("flashscore", "volley", "Toulouse", "Sète", d, (3, 1))
    assert [x["source"] for x in resultats.retrouver(p, [r])] == ["flashscore"]
    assert resultats.consensus(p, [r], d + timedelta(hours=60))["score"] == (3, 1)


def test_heure_decalee_d_une_heure_si_les_noms_collent():
    p = {"match_id": "h1", "sport": "hockey", "domicile": "Zvolen", "exterieur": "Banská Bystrica",
         "debut": "2026-10-17T15:00:00.000Z", "match_reference": "HC 05 Banska Bystrica - HKM Zvolen",
         "statut": "a_regler"}
    r = _enr("livescore", "hockey", "Banska Bystrica", "Zvolen", datetime(2026, 10, 17, 16, 0, tzinfo=timezone.utc), (3, 4))
    trouve = resultats.retrouver(p, [r])
    assert len(trouve) == 1 and trouve[0]["score"] == (4, 3)                        # orienté comme le pari
    assert resultats.consensus(p, [r], datetime(2026, 10, 18, 15, 0, tzinfo=timezone.utc))["score"] == (4, 3)
    loin = _enr("livescore", "hockey", "Banska Bystrica", "Zvolen", datetime(2026, 10, 17, 19, 0, tzinfo=timezone.utc), (3, 4))
    assert resultats.retrouver(p, [loin]) == []                                      # 4 h d'écart : pas le même match


def test_radical_aurillac_aurillacois():
    from cotes.correspondance import ressemblance
    assert ressemblance("Aurillac", "Stade Aurillacois") >= 0.88
    assert ressemblance("Toulouse V.B.", "Toulouse") >= 0.9
    assert ressemblance("Lyon", "Lille") < 0.75                                      # pas de faux rapprochement


def test_snooker_flechettes_badminton_lus_chez_flashscore():
    from cotes import flashscore
    assert flashscore.SPORTS["snooker"] == 15 and flashscore.SPORTS["flechettes"] == 14
    d = {"AA": "x", "AB": "3", "AC": "3", "AD": "1792400000", "AE": "Jak Jones", "AF": "Tom Ford", "AG": "4", "AH": "2"}
    m = flashscore.match("snooker", d)
    assert m["score"] == (4, 2) and m["periodes"] == []
    assert resultats.plausible("snooker", (4, 2)) and not resultats.plausible("snooker", (0, 0))
    assert not resultats.plausible("snooker", (3, 3))
