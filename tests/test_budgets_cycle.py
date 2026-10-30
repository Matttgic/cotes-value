"""Budgets par source : une lecture trop longue est sautée, le cache Smarkets reste."""
import json
import time
from datetime import datetime, timedelta, timezone

from cotes import memoire
from cotes.delai import Echeance
from cotes.direct import unibet
from scripts import cycle

NOW = datetime(2026, 10, 18, 12, tzinfo=timezone.utc)


def test_echeance_deja_depassee():
    ech = Echeance(0)
    assert ech.ok() is False and ech.reste() == 0
    assert ech.timeout(30) == 1


def test_etape_bornee_saute_sans_bloquer():
    journal = {"etapes": {}}

    def lent():
        time.sleep(0.4)
        return "tard"

    assert cycle.etape_bornee("pmu_direct", journal, 0.1, lent) is None
    assert journal["etapes"]["pmu_direct"]["ok"] is False
    assert journal["etapes"]["pmu_direct"]["erreur"] == "budget dépassé"


def test_ombre_6h_puis_horizon_complet():
    plein, du = cycle.heures_ombre("pmu", "shadow", "complet", NOW, {})
    assert plein == 36 and du is True
    rythme = {"pmu": NOW.isoformat()}
    court, du = cycle.heures_ombre("pmu", "shadow", "complet", NOW + timedelta(minutes=5), rythme)
    assert court == 6 and du is False
    encore, du = cycle.heures_ombre("pmu", "shadow", "complet", NOW + timedelta(minutes=20), rythme)
    assert encore == 36 and du is True
    direct, du = cycle.heures_ombre("pmu", "direct", "complet", NOW + timedelta(minutes=5), rythme)
    assert direct == 36 and du is False
    test, du = cycle.heures_ombre("unibet", "shadow", "test", NOW, {})
    assert test == 12 and du is False
    rythme = {"pmu": NOW.isoformat(), "unibet": NOW.isoformat(), "betclic": NOW.isoformat()}
    assert cycle.heures_ombre("unibet", "shadow", "complet", NOW + timedelta(minutes=20), rythme) == (6, False)
    assert cycle.heures_ombre("unibet", "shadow", "complet", NOW + timedelta(minutes=27), rythme) == (36, True)
    assert cycle.heures_ombre("betclic", "shadow", "complet", NOW + timedelta(minutes=27), rythme) == (6, False)
    assert cycle.heures_ombre("betclic", "shadow", "complet", NOW + timedelta(minutes=34), rythme) == (36, True)


def test_smarkets_eteint_ne_fait_aucun_appel(tmp_path, monkeypatch):
    monkeypatch.delenv("SMARKETS_COLLECTE", raising=False)
    cycle.ecrire_json(tmp_path / "smarkets_cache.json", {
        "lu": (NOW - timedelta(minutes=30)).isoformat(),
        "lignes": [{"cote": 2}],
        "perime": False,
    })

    def boom(*args, **kwargs):
        raise AssertionError("réseau")

    monkeypatch.setattr(cycle.smarkets, "collecter", boom)
    journal = {"etapes": {}}
    lignes, info = cycle.appliquer_smarkets(tmp_path, {"football"}, 36, [{"sport": "football"}], NOW, journal)
    assert lignes == [] and info["requetes"] == 0 and info["desactive"] is True
    assert journal["etapes"]["smarkets"]["desactive"] is True
    cache = memoire.lire(tmp_path, "smarkets_cache")
    assert cache["lignes"] == [{"cote": 2}]


def test_cache_smarkets_reutilise_sans_appel(tmp_path, monkeypatch):
    monkeypatch.setenv("SMARKETS_COLLECTE", "oui")
    cycle.ecrire_json(tmp_path / "smarkets_cache.json", {
        "lu": (NOW - timedelta(minutes=5)).isoformat(),
        "lignes": [{"cote": 1.5}],
        "perime": False,
    })

    def boom(*args, **kwargs):
        raise AssertionError("réseau")

    monkeypatch.setattr(cycle.smarkets, "collecter", boom)
    journal = {"etapes": {}}
    lignes, info = cycle.appliquer_smarkets(tmp_path, {"football"}, 36, [], NOW, journal)
    assert lignes == [{"cote": 1.5}] and info["requetes"] == 0
    assert journal["etapes"]["smarkets"]["cache"] is True
    assert journal["smarkets_cache"]["perime"] is False


def test_429_garde_le_cache_perime(tmp_path, monkeypatch):
    monkeypatch.setenv("SMARKETS_COLLECTE", "oui")
    cycle.ecrire_json(tmp_path / "smarkets_cache.json", {
        "lu": (NOW - timedelta(minutes=30)).isoformat(),
        "lignes": [{"cote": 2}],
        "perime": False,
    })
    monkeypatch.setattr(cycle.smarkets, "collecter", lambda *a, **k: (
        [{"cote": 9}], {"ok": False, "erreurs": ["HTTP 429"], "perime": True, "requetes": 1, "matchs": 0}))
    journal = {"etapes": {}}
    lignes, info = cycle.appliquer_smarkets(tmp_path, {"football"}, 36, [], NOW, journal)
    assert lignes == [{"cote": 2}]
    cache = memoire.lire(tmp_path, "smarkets_cache")
    assert cache["perime"] is True and cache["lignes"] == [{"cote": 2}]
    assert journal["etapes"]["smarkets"]["degrade"] is True
    assert "périmé" in journal["etapes"]["smarkets"]["erreurs"]
    assert info["erreurs"] == ["HTTP 429"]


def test_page_unibet_lointaine_s_arrete():
    sac = {"events": {"e1": {"start": "2610182000"}}}
    horizon = datetime(2026, 10, 18, 18, tzinfo=timezone.utc)
    assert unibet._page_lointaine(sac, ["e1"], horizon) is True
    sac["events"]["e1"]["start"] = "2610181400"
    assert unibet._page_lointaine(sac, ["e1"], horizon) is False
    assert unibet._page_lointaine({"events": {"e1": {"start": "pas-une-date"}}}, ["e1"], horizon) is False


def test_pinnacle_budget_coupe_avant_le_reseau(monkeypatch):
    from cotes import pinnacle
    monkeypatch.setattr(pinnacle._http, "get", lambda *a, **k: (_ for _ in ()).throw(AssertionError("réseau")))
    monkeypatch.setattr(pinnacle.requests, "post", lambda *a, **k: (_ for _ in ()).throw(AssertionError("réseau")))
    assert pinnacle.collecter({29: "football"}, echeance=Echeance(0)) == []
    assert "budget" in pinnacle.ERREURS


def test_lecture_directe_en_echec_visible_pour_tous_les_lecteurs():
    from cotes import surveillance
    for nom in ("unibet_direct", "pmu_direct", "betclic_direct", "winamax_direct"):
        journal = {"etapes": {nom: {"secondes": 0.7, "ok": True}}}
        cycle.noter_lecture(journal, nom, {"ok": False, "erreurs": ["accueil HTTP 403"]})
        assert journal["etapes"][nom]["ok"] is False and journal["etapes"][nom]["degrade"] is True
        assert surveillance.problemes(journal["etapes"])[nom][0] == "panne"
    # lecture partielle coupée par le budget : dégradée, pas en panne
    journal = {"etapes": {"unibet_direct": {"secondes": 79, "ok": True}}}
    cycle.noter_lecture(journal, "unibet_direct", {"ok": True, "erreurs": ["budget"]})
    assert journal["etapes"]["unibet_direct"]["ok"] is True
    assert "unibet_direct" not in surveillance.problemes(journal["etapes"])


def test_budgets_winamax_et_unibet_sous_celui_de_betclic():
    # sources lues en parallèle : la plus lente (Betclic) fixe la durée du cycle
    assert cycle.BUDGETS["winamax_direct"] <= cycle.BUDGETS["betclic_direct"]
    assert cycle.BUDGETS["unibet_direct"] <= cycle.BUDGETS["betclic_direct"]
