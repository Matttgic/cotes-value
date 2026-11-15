"""Registre des stratégies (cotes/strategies/registre.py, E4.1)."""
import json
import sys
from pathlib import Path

import pytest

from cotes import protocole
from cotes.strategies import registre

RACINE = Path(__file__).resolve().parent.parent


def test_cles_uniques_et_familles_connues():
    cles = [s.cle for s in registre.toutes()]
    assert len(cles) == len(set(cles))
    assert {s.famille for s in registre.toutes()} <= set(registre.FAMILLES)
    lignes = [s.ligne for s in registre.toutes()]
    assert len(lignes) == len(set(lignes))


def test_contient_toutes_les_strategies_du_protocole():
    assert sorted(set(protocole.definitions()) - {s.cle for s in registre.toutes()}) == []


def test_strategies_des_fichiers_figes():
    assert {s.cle for s in registre.toutes() if s.figee} == {"jules", "jules_v2"}
    for nom in registre.FICHIERS_FIGES:
        assert (RACINE / "cotes" / nom).exists(), nom


@pytest.fixture(scope="module")
def temoin():
    paris, _ = protocole.lire_temoin()
    return paris


def test_libelles_affiches_par_le_site_sur_le_temoin(temoin):
    sys.path.insert(0, str(RACINE / "scripts"))
    from scripts import site_web
    maintenant = max(p["detecte"] for p in temoin)
    laboratoire = json.loads((RACINE / "docs" / "comparaison-strategies.json").read_text(encoding="utf-8"))
    # même préparation que site_web._construire : seules les règles actuelles du laboratoire
    ids_regles = {r.id for r in site_web.REGLES_LABO}
    laboratoire["resultats"] = [r for r in laboratoire.get("resultats", []) if r["regle"]["id"] in ids_regles]
    site_web.enrichir_comparateurs(temoin, laboratoire, maintenant)
    affiches = set(site_web.navigation_strategies(temoin, laboratoire, maintenant)["selections"])
    assert affiches, "le témoin doit afficher des stratégies"
    assert sorted(affiches - {s.ligne for s in registre.toutes()}) == []


@pytest.mark.parametrize("cle", ["strategie", "jules_v2", "convergence", "claude_prudent", "grok_1"])
def test_selectionner_rend_les_memes_paris_que_l_original(temoin, cle):
    from cotes.convergence import STRATEGIES, paris_convergence
    from cotes.strategies_prudentes import selections_prudentes
    origine = {c: f for c, _, _, _, f in STRATEGIES}
    attendu = (origine[cle](temoin) if cle in origine else paris_convergence(temoin) if cle == "convergence"
               else selections_prudentes(temoin)[cle])
    assert registre.strategie(cle).selectionner(temoin) == attendu


def test_regle_du_laboratoire(temoin):
    from cotes.laboratoire import REGLES, selectionner
    r = REGLES[0]
    assert registre.strategie("labo:" + r.id).selectionner(temoin) == {id(p) for p in selectionner(temoin, r)}
