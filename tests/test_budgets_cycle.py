"""Budgets par source : une lecture trop longue est sautée, le cache Smarkets reste."""
import json
import time
from datetime import datetime, timedelta, timezone

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


def test_cache_smarkets_reutilise_sans_appel(tmp_path, monkeypatch):
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
    cache = json.loads((tmp_path / "smarkets_cache.json").read_text(encoding="utf-8"))
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
    monkeypatch.setattr(pinnacle.requests, "get", lambda *a, **k: (_ for _ in ()).throw(AssertionError("réseau")))
    monkeypatch.setattr(pinnacle.requests, "post", lambda *a, **k: (_ for _ in ()).throw(AssertionError("réseau")))
    assert pinnacle.collecter({29: "football"}, echeance=Echeance(0)) == []
    assert "budget" in pinnacle.ERREURS
