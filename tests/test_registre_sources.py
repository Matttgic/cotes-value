"""Registre des sources (cotes/sources/registre.py, E2.1) : mêmes valeurs que scripts/cycle.py."""
import pytest

from cotes import smarkets
from cotes.direct import matchbook, winamax
from cotes.sources import registre
from scripts import cycle


# Valeurs de scripts/cyc.py avant E2.2 (BUDGETS, MEMOIRES, exclusions de index_controle), recopiées ici
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
