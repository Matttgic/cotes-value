"""LiveScore : scores attendus par le règlement, sans réseau."""
from datetime import datetime, timezone

from cotes import livescore

DEBUT = 20261014174500


def _e(**kw):
    base = {"Eid": "1", "Esd": DEBUT, "T1": [{"Nm": "Genève-Servette HC", "NmEn": "Geneve-Servette"}],
            "T2": [{"Nm": "Koelner Haie"}]}
    return base | kw


def test_hockey_prolongation_et_tirs_au_but():
    ot = livescore.match("hockey", _e(Eps="OT", Tr1="4", Tr2="3", Tr1OR="3", Tr2OR="3", Tr1OT="1", Tr2OT="0",
                                      Tr1Pe1="1", Tr2Pe1="1", Tr1Pe2="1", Tr2Pe2="1", Tr1Pe3="1", Tr2Pe3="1"))
    assert [r["domicile"] for r in ot] == ["Genève-Servette HC", "Geneve-Servette"]
    assert ot[0]["score"] == (4, 3) and ot[0]["periodes"] == [(1, 1), (1, 1), (1, 1), (1, 0)]
    assert ot[0]["libelles"] == ["1", "2", "3", "OT"] and ot[0]["debut"] == datetime(2026, 10, 14, 17, 45, tzinfo=timezone.utc)
    tab = livescore.match("hockey", _e(Eps="AP", Tr1="2", Tr2="3", Tr1OR="2", Tr2OR="2", Tr1OT="0", Tr2OT="0",
                                       Tr1Pe1="0", Tr2Pe1="1", Tr1Pe2="1", Tr2Pe2="0", Tr1Pe3="1", Tr2Pe3="1"))
    assert tab[0]["score"] == (2, 3) and tab[0]["libelles"] == ["1", "2", "3"]   # le but des tirs au but compte


def test_football_prolongation_garde_le_temps_reglementaire():
    r = livescore.match("football", _e(Eps="AET", Tr1="2", Tr2="4", Trh1="1", Trh2="2", Tr1OR="2", Tr2OR="2"))[0]
    assert r["score"] == (2, 2) and r["periodes"] == [(1, 2), (1, 0)]
    assert livescore.match("football", _e(Eps="AP", Tr1="0", Tr2="0")) == []       # temps réglementaire inconnu
    assert livescore.match("football", _e(Eps="NS", Tr1="0", Tr2="0")) == []
    assert livescore.match("football", _e(Eps="Postp.")) == []


def test_tennis_sets_jeux_abandon_et_forfait():
    r = livescore.match("tennis", _e(Eps="FT", Tr1="1", Tr2="2", Tr1S1="7", Tr2S1="6", Tr1S2="4", Tr2S2="6",
                                     Tr1S3="2", Tr2S3="6"))[0]
    assert r["score"] == (1, 2) and r["periodes"] == [(7, 6), (4, 6), (2, 6)] and r["abandon"] is False
    ab = livescore.match("tennis", _e(Eps="Ret.", Tr1="0", Tr2="1", Tr1S1="1", Tr2S1="6", Tr1S2="0", Tr2S2="2"))[0]
    assert ab["abandon"] is True
    assert livescore.match("tennis", _e(Eps="W.O.", Tr1="0", Tr2="0")) == []


def test_basket_quart_temps_et_lecture_par_jour():
    e = _e(Eps="OT", Tr1="114", Tr2="112", Tr1Q1="25", Tr2Q1="33", Tr1Q2="34", Tr2Q2="28", Tr1Q3="26", Tr2Q3="23",
           Tr1Q4="15", Tr2Q4="16", Tr1OT="14", Tr2OT="12")
    r = livescore.match("basket", e)[0]
    assert r["score"] == (114, 112) and r["libelles"] == ["1", "2", "3", "4", "OT"]

    class Rep:
        ok = True
        status_code = 200

        def json(self):
            return {"Stages": [{"Events": [e, {"Eps": "NS"}]}]}

    class Http:
        urls = []

        def get(self, url, **kw):
            self.urls.append(url)
            return Rep()

    http = Http()
    lus = livescore.lire("basket", ["2026-10-14", "2026-10-14", "2026-10-15"], http=http)
    assert len(http.urls) == 2 and http.urls[0].endswith("/basketball/20261014/0") and len(lus) == 2 * len(livescore.match("basket", e))


def test_panne_ne_leve_pas_et_est_notee():
    class Panne:
        def get(self, *a, **k):
            raise livescore.requests.ConnectionError("réseau")

    avant = len(livescore.ERREURS)
    assert livescore.lire("football", ["2026-10-14"], http=Panne()) == []
    assert len(livescore.ERREURS) == avant + 1


def test_liste_a_saisir_pour_les_matchs_sans_source():
    from cotes import resultats
    p = {"statut": "a_regler", "match_id": "pmu|1", "sport": "football", "domicile": "A", "exterieur": "B",
         "debut": "2026-10-14T01:30:00Z", "periode": "MT1", "marche": "TOTAL", "ligue": "Liga"}
    autre = {**p, "periode": "MATCH", "statut": "gagne", "match_id": "pmu|2"}
    liste = resultats.a_saisir([p, {**p, "periode": "MATCH"}, autre], [], datetime(2026, 10, 18, tzinfo=timezone.utc))
    assert len(liste) == 1 and liste[0]["paris"] == 2 and liste[0]["periodes_requises"] == ["MATCH", "MT1"]
    assert liste[0]["modele"] == {"score": [None, None], "mi_temps": [None, None]}
    assert liste[0]["raison"] == "aucune source"
