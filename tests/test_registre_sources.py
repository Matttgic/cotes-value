"""Registre des sources (cotes/sources/registre.py, E2.1) : mêmes valeurs que scripts/cycle.py."""
import ast
from pathlib import Path

import pytest

from cotes import smarkets
from cotes.direct import matchbook, winamax
from cotes.sources import registre
from scripts import cycle

RACINE = Path(__file__).resolve().parent.parent


def test_budgets_identiques_au_cycle():
    assert registre.budgets() == cycle.BUDGETS


def test_memoires_identiques_au_cycle():
    assert registre.memoires() == cycle.MEMOIRES


def _exclusions_du_controle() -> set[str]:
    """Littéraux de `index_controle = {… if n not in (…)}` dans cycle.py."""
    arbre = ast.parse((RACINE / "scripts" / "cycle.py").read_text(encoding="utf-8"))
    for n in ast.walk(arbre):
        if isinstance(n, ast.Assign) and any(isinstance(c, ast.Name) and c.id == "index_controle" for c in n.targets):
            return {c.value for c in ast.walk(n.value) if isinstance(c, ast.Constant) and isinstance(c.value, str)}
    raise AssertionError("index_controle introuvable")


def test_exclusions_du_controle_identiques():
    assert registre.hors_controle() == _exclusions_du_controle()


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
