"""Registre des sources (cotes/sources/registre.py, E2.1) : mêmes valeurs que scripts/cycle.py."""
import pytest

from cotes import pinnacle, polymarket, smarkets
from cotes.direct import matchbook, netbet, olybet, winamax
from cotes.sources import registre
from scripts import cycle


# Valeurs de scripts/cycle.py avant E2.2 (BUDGETS, MEMOIRES, exclusions de index_controle), recopiées ici
BUDGETS_15_11 = {"pinnacle": 45, "polymarket": 30, "pmu_direct": 75, "winamax_direct": 80, "unibet_direct": 80,
                 "olybet": 40, "netbet": 55, "betclic_direct": 80, "smarkets": 60, "matchbook": 25, "betfair": 45,
                 "draftkings": 20, "fanduel": 40}
MEMOIRES_15_11 = {"pmu_direct": "pmu", "unibet_direct": "unibet", "betclic_direct": "betclic", "netbet": "netbet"}


def test_budgets_identiques_au_cycle():
    assert registre.budgets() == cycle.BUDGETS == BUDGETS_15_11
    assert list(cycle.BUDGETS) == list(BUDGETS_15_11)


def test_memoires_identiques_au_cycle():
    assert registre.memoires() == cycle.MEMOIRES == MEMOIRES_15_11


def test_exclusions_du_controle_identiques():
    assert registre.hors_controle() == {"Smarkets", "Matchbook", "Betfair"}


@pytest.mark.parametrize("drapeau", ["", "oui"])
def test_hors_consensus_identique(monkeypatch, drapeau):
    monkeypatch.setenv("SMARKETS_DANS_DECISION", drapeau)
    assert registre.hors_consensus() == smarkets.hors_consensus() | matchbook.hors_consensus()


def test_noms_uniques_roles_connus():
    noms = [s.nom for s in registre.SOURCES]
    assert len(noms) == len(set(noms))
    assert {s.role for s in registre.SOURCES} <= set(registre.ROLES)
    assert [s.nom for s in registre.francais()] == ["pmu_direct", "winamax_direct", "unibet_direct", "olybet",
                                                     "netbet", "betclic_direct"]
    assert [s.nom for s in registre.SOURCES if s.attend_radar] == ["unibet_direct"]


def test_lire_suit_le_module_au_moment_de_l_appel(monkeypatch):
    monkeypatch.setattr(winamax, "collecter", lambda *a, **k: ("remplacé", a, k))
    assert registre.source("winamax_direct").lire({"football"}, 12, maintenant=1) == ("remplacé", ({"football"}, 12),
                                                                                       {"maintenant": 1})


def test_modes(monkeypatch):
    for nom in ("SOURCE_OLYBET", "SOURCE_MATCHBOOK", "SMARKETS_COLLECTE"):
        monkeypatch.delenv(nom, raising=False)
    assert registre.source("pinnacle").mode() == "direct"
    assert registre.source("olybet").mode() == "direct"
    assert registre.source("smarkets").mode() == "off"
    monkeypatch.setenv("SOURCE_OLYBET", "off")
    monkeypatch.setenv("SMARKETS_COLLECTE", "oui")
    assert registre.source("olybet").mode() == "off"
    assert registre.source("smarkets").mode() == "direct"


@pytest.mark.parametrize("module,nom", [(pinnacle, "pinnacle"), (polymarket, "polymarket")])
def test_adaptateur_lignes_meta(monkeypatch, module, nom):
    def collecter(*a, **k):
        module.ERREURS.clear()
        return [{"cote": 2.0}]

    monkeypatch.setattr(module, "collecter", collecter)
    lignes, meta = registre.source(nom).lire()
    assert lignes == [{"cote": 2.0}] and meta["ok"] is True and meta["erreurs"] == [] and meta["lignes"] == 1

    def en_panne(*a, **k):
        module.ERREURS.append("HTTP 503")
        return None

    monkeypatch.setattr(module, "collecter", en_panne)
    lignes, meta = registre.source(nom).lire()
    assert lignes == [] and meta["ok"] is False and meta["erreurs"] == ["HTTP 503"]
    module.ERREURS.clear()


@pytest.mark.parametrize("module,variable", [(olybet, "SOURCE_OLYBET"), (netbet, "SOURCE_NETBET")])
def test_mode_alias_de_mode_source(monkeypatch, module, variable):
    for valeur in ("", "off", "direct", "inconnu"):
        monkeypatch.setenv(variable, valeur)
        assert module.mode() == module.mode_source()


ARGS_15_11 = {   # appels lancer(...) de collecter_prematch avant E2.4 : (sports, heures), options
    "pmu_direct": ("tous", {"reserve", "concurrence"}),
    "winamax_direct": ("tous", {"maintenant"}),
    "betclic_direct": ("tous", {"maintenant", "reserve"}),
    "olybet": ("football", set()),
    "netbet": ("football", {"reserve"}),
}


@pytest.mark.parametrize("mode,heures", [("complet", 36), ("test", 12)])
def test_lancement_des_bookmakers_identique(monkeypatch, mode, heures):
    from datetime import datetime, timezone
    appels = {}

    def enregistreur(nom):
        def collecter(sports, h, **options):
            appels[nom] = (set(sports), h, options)
            return [], {"ok": True, "erreurs": [], "requetes": 0}
        return collecter

    for s in registre.francais():
        monkeypatch.setattr(s.module, "collecter", enregistreur(s.nom))
    for variable in ("SOURCE_OLYBET", "SOURCE_NETBET"):
        monkeypatch.setenv(variable, "direct")
    for variable in ("SOURCE_FANDUEL", "SOURCE_DRAFTKINGS"):
        monkeypatch.setenv(variable, "off")
    debut = "2026-10-17T12:00:00Z"
    refs = [{"sport": s, "debut": debut, "bookmaker": "pinnacle", "match_id": s, "marche": "VAINQUEUR"}
            for s in ("football", "tennis")]
    monkeypatch.setattr(cycle.pinnacle, "collecter", lambda *a, **k: refs)
    monkeypatch.setattr(cycle.polymarket, "collecter", lambda *a, **k: [])
    monkeypatch.setattr(cycle, "harmoniser_pinnacle", lambda x: x)
    monkeypatch.setattr(cycle.pinnacle_secours, "disponible", lambda: False)
    cycle.collecter_prematch(mode, datetime(2026, 10, 17, 6, tzinfo=timezone.utc), {"etapes": {}})
    for nom, (sports, options) in ARGS_15_11.items():
        attendus = {"football"} if sports == "football" and mode == "test" else {"football", "tennis"}
        assert appels[nom][0] == attendus and appels[nom][1] == heures, nom
        assert set(appels[nom][2]) == options, nom
    assert appels["pmu_direct"][2]["concurrence"] == 2
    assert set(appels["unibet_direct"][2]) == {"maintenant", "concurrence", "radar", "reserve"}
    assert [s.nom for s in registre.ordre_de_lancement()] == list(ARGS_15_11)
