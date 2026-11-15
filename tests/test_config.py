"""Catalogue des variables d'environnement (cotes/config.py, E1.1)."""
import ast
import re
from pathlib import Path

import pytest

from cotes import config

RACINE = Path(__file__).resolve().parent.parent

# Valeur du YAML (`vars.X || 'y'`) différente du défaut du code : GitHub tourne avec la valeur du YAML, une
# lecture locale avec celle du code. Relevés le 15/11/2026, non corrigés (docs/architecture-cible.md, E1.1).
ECARTS_CONNUS = {
    "SMARKETS_COLLECTE": ("oui", "non"),
    "SOURCE_FANDUEL": ("direct", "off"),
    "SOURCE_DRAFTKINGS": ("direct", "off"),
}


def _fichiers():
    return sorted(list((RACINE / "cotes").rglob("*.py")) + list((RACINE / "scripts").glob("*.py")))


def _lu_dans_environ(appel: ast.Call) -> bool:
    fonction = ast.unparse(appel.func)
    return "environ" in fonction or fonction.endswith(("getenv", "env.get", "_entier_env"))


def noms_lus() -> tuple[set[str], set[str]]:
    """(noms littéraux, préfixes des noms construits par f-string) lus dans l'environnement."""
    noms, prefixes = set(), set()
    for f in _fichiers():
        for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(n, ast.Call) and n.args and _lu_dans_environ(n):
                a = n.args[0]
                if isinstance(a, ast.Constant) and isinstance(a.value, str) and re.fullmatch(r"[A-Z][A-Z0-9_]+", a.value):
                    noms.add(a.value)
                elif isinstance(a, ast.JoinedStr) and a.values and isinstance(a.values[0], ast.Constant):
                    prefixes.add(a.values[0].value)
            elif isinstance(n, ast.Subscript) and "environ" in ast.unparse(n.value):
                if isinstance(n.slice, ast.Constant) and isinstance(n.slice.value, str):
                    noms.add(n.slice.value)
    return noms, prefixes


def defauts_yaml() -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for f in (RACINE / ".github" / "workflows").glob("*.yml"):
        for nom, valeur in re.findall(r"vars\.([A-Z0-9_]+)\s*\|\|\s*'([^']*)'", f.read_text(encoding="utf-8")):
            out.setdefault(nom, set()).add(valeur)
    return out


def noms_exemples() -> set[str]:
    out = set()
    for f in (RACINE / ".env.example", RACINE / "serveur" / "env.exemple"):
        out |= set(re.findall(r"^#?\s*([A-Z][A-Z0-9_]+)=", f.read_text(encoding="utf-8"), re.M))
    return out


def test_chaque_variable_lue_est_declaree():
    noms, prefixes = noms_lus()
    assert sorted(noms - set(config.VARIABLES)) == []
    for p in prefixes:
        assert any(n.startswith(p) for n in config.VARIABLES), p


def test_variables_des_workflows_declarees():
    texte = "".join(f.read_text(encoding="utf-8") for f in (RACINE / ".github" / "workflows").glob("*.yml"))
    noms = set(re.findall(r"\$\{\{\s*(?:vars|secrets)\.([A-Z0-9_]+)", texte))
    assert sorted(noms - set(config.VARIABLES)) == []


def test_defauts_du_yaml_egaux_au_catalogue():
    ecarts = {}
    for nom, valeurs in defauts_yaml().items():
        for valeur in valeurs:
            if valeur != config.VARIABLES[nom].defaut:
                ecarts[nom] = (valeur, config.VARIABLES[nom].defaut)
    assert ecarts == ECARTS_CONNUS


def test_noms_des_exemples_declares():
    assert sorted(noms_exemples() - set(config.VARIABLES)) == []


def test_aucune_entree_morte():
    noms, _ = noms_lus()
    texte = "".join(f.read_text(encoding="utf-8") for f in (RACINE / ".github" / "workflows").glob("*.yml"))
    mortes = [n for n in config.VARIABLES if n not in noms and n not in texte and n not in noms_exemples()
              and not n.startswith("THE_ODDS_API_KEY_")]
    assert mortes == []


def test_secrets_sans_valeur():
    assert all(v.defaut == "" for v in config.VARIABLES.values() if v.secret)


@pytest.mark.parametrize("environ,attendu", [
    ({}, 10.0), ({"PINNACLE_AGE_MAX_MIN": ""}, 10.0), ({"PINNACLE_AGE_MAX_MIN": " 12 "}, 12.0),
    ({"PINNACLE_AGE_MAX_MIN": "abc"}, 10.0),
])
def test_lire_type_et_defaut(environ, attendu):
    assert config.lire("PINNACLE_AGE_MAX_MIN", environ) == attendu


def test_lire_texte_et_nom_inconnu():
    assert config.lire("MODE_COLLECTE", {}) == "complet"
    assert config.lire("PUSHOVER_STRATEGIES", {}) == ""
    assert config.lire("PINNACLE_API_KEY", {"PINNACLE_API_KEY": "x"}) == "x"
    with pytest.raises(KeyError):
        config.lire("INCONNUE", {})


def test_tableau_markdown_sans_secret():
    tableau = config.markdown()
    assert "`PINNACLE_API_KEY` | (secret)" in tableau
    assert tableau.count("\n") == len(config.VARIABLES) + 1


def _crons_des_workflows() -> dict[str, list[str]]:
    out = {}
    for f in sorted((RACINE / ".github" / "workflows").glob("*.yml")):
        crons = re.findall(r'^\s*-\s*cron:\s*"([^"]+)"', f.read_text(encoding="utf-8"), re.M)
        if crons:
            out[f.name] = crons
    return out


def test_calendrier_identique_aux_workflows():
    attendu = {}
    for t in config.TACHES.values():
        attendu.setdefault(t.workflow, []).append(t.cron)
    assert _crons_des_workflows() == attendu


def test_calendrier_identique_au_tableau_de_la_doc():
    """Tableau 1.4 de docs/architecture-cible.md : chaque tâche planifiée y figure avec son cron."""
    doc = (RACINE / "docs" / "architecture-cible.md").read_text(encoding="utf-8")
    tableau = doc[doc.index("### 1.4 Tâches planifiées"):doc.index("### 1.5")]
    for t in config.TACHES.values():
        ligne = next((l for l in tableau.splitlines() if f"`{t.workflow}`" in l), None)
        assert ligne is not None, t.workflow
        assert f"`{t.cron}`" in ligne, (t.workflow, t.cron)
