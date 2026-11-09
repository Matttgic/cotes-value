"""Pause d'une source sur refus 403/429 (lot fiabilité, 9/11/2026) : 30 min, doublée à chaque récidive, 6 h au plus."""
from datetime import timedelta

from cotes import pauses_sources as PS
from cotes import surveillance
from scripts import cycle
from tests.test_collecte_parallele import NOW, _sans_reseau, ligne

REFUS = {"secondes": 2.4, "ok": False, "degrade": True, "erreurs": ["accueil HTTP 403"]}    # format réel (etat.json)


def test_refus_pause_trente_minutes_puis_doublee_jusqu_a_six_heures():
    etat, t = {}, NOW
    durees = []
    for _ in range(6):
        PS.mettre_a_jour(etat, {"unibet_direct": REFUS}, t)
        durees.append(etat["unibet_direct"]["minutes"])
        assert PS.en_pause(etat, "unibet_direct", t + timedelta(minutes=1))
        t += timedelta(minutes=durees[-1] + 1)
        assert PS.en_pause(etat, "unibet_direct", t) is None          # pause finie : nouvel essai
    assert durees == [30, 60, 120, 240, 360, 360]
    assert etat["unibet_direct"]["motif"] == "accueil HTTP 403"
    PS.mettre_a_jour(etat, {"unibet_direct": {"secondes": 3.0, "ok": True}}, t)       # lecture réussie : oubliée
    assert "unibet_direct" not in etat


def test_seule_une_lecture_refusee_declenche_la_pause():
    assert PS.refus(REFUS) == "accueil HTTP 403"
    assert PS.refus({"ok": True, "degrade": True, "erreurs": ["HTTP 429"]}) == "HTTP 429"   # tout refusé
    assert PS.refus({"ok": True, "degrade": True, "erreurs": ["HTTP 403", "réseau"]}) is None
    assert PS.refus({"ok": False, "erreurs": ["lecture interrompue"]}) is None
    assert PS.refus({"ok": True, "desactive": True, "erreurs": ["HTTP 403"]}) is None
    etat = {}
    PS.mettre_a_jour(etat, {"pinnacle": REFUS, "polymarket": REFUS}, NOW)     # références principales : jamais
    assert etat == {}


def test_memoire_aller_retour_et_fichier_illisible(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMOIRE_CHEMIN", str(tmp_path))
    etat = PS.mettre_a_jour({}, {"netbet": REFUS}, NOW)
    PS.sauver(None, etat)
    assert PS.charger(None) == etat
    (tmp_path / "pauses_sources.json.gz").write_bytes(b"pas du gzip")
    assert PS.charger(None) == {}


def test_source_en_pause_n_est_pas_lue_et_n_est_pas_un_incident(monkeypatch):
    appels = []
    _sans_reseau(monkeypatch)
    monkeypatch.setattr(cycle.unibet_direct, "collecter", lambda *a, **k: appels.append(1))
    monkeypatch.setattr(cycle.pinnacle, "collecter", lambda: [ligne("football", "pinnacle")])
    monkeypatch.setattr(cycle.polymarket, "collecter", lambda *a: [])
    monkeypatch.setattr(cycle, "harmoniser_pinnacle", lambda x: x)
    pauses = PS.mettre_a_jour({}, {"unibet_direct": REFUS}, NOW - timedelta(minutes=5))
    j = {"etapes": {}}
    cycle.collecter_prematch("complet", NOW, j, pauses=pauses)
    etape = j["etapes"]["unibet_direct"]
    assert appels == [] and etape["ok"] is True and etape["pause"] is True
    assert etape["pause_jusqu_a"] == pauses["unibet_direct"]["jusqu_a"]
    assert surveillance.problemes(j["etapes"]) == {} and surveillance.constats(j["etapes"]) == {}
    PS.mettre_a_jour(pauses, j["etapes"], NOW)                     # une étape en pause ne change pas la pause
    assert pauses["unibet_direct"]["recidives"] == 1


def test_matchbook_en_pause_sans_requete(monkeypatch):
    monkeypatch.setattr(cycle.matchbook_direct, "mode", lambda: "direct")
    monkeypatch.setattr(cycle.matchbook_direct, "collecter", lambda *a, **k: 1 / 0)
    pauses = PS.mettre_a_jour({}, {"matchbook": {"ok": False, "erreurs": ["HTTP 403"]}}, NOW)
    j = {"etapes": {}}
    assert cycle.appliquer_matchbook({"football"}, 36, NOW, j, pauses) == []
    assert j["etapes"]["matchbook"]["pause"] is True and j["matchbook"]["requetes"] == 0
