"""Catalogue des fichiers de « donnees » (cotes/depot/catalogue.py, E1.3)."""
import ast
import fnmatch
import re
from pathlib import Path

from cotes.depot import catalogue
from scripts import cycle

RACINE = Path(__file__).resolve().parent.parent
EXTENSIONS = (".json", ".json.gz", ".jsonl.gz")


def _fichiers():
    return sorted(list((RACINE / "cotes").rglob("*.py")) + list((RACINE / "scripts").glob("*.py")))


def _constantes(arbre) -> dict[str, str]:
    """Constantes de module : FICHIER = "pauses.json"."""
    out = {}
    for n in arbre.body:
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str):
            for c in n.targets:
                if isinstance(c, ast.Name):
                    out[c.id] = n.value.value
    return out


def _segment(n, constantes) -> str | None:
    if isinstance(n, ast.Constant) and isinstance(n.value, str):
        return n.value
    if isinstance(n, ast.Name) and n.id in constantes:
        return constantes[n.id]
    if isinstance(n, ast.JoinedStr):
        return "".join(v.value if isinstance(v, ast.Constant) else "*" for v in n.values)
    return None


def _chemin(n: ast.BinOp, constantes) -> str | None:
    """`donnees / "cotes" / f"{jour}.jsonl.gz"` -> "cotes/*.jsonl.gz" ; None si ce n'est pas sous « donnees »."""
    parties = []
    while isinstance(n, ast.BinOp) and isinstance(n.op, ast.Div):
        parties.append(n.right)
        n = n.left
    if "donnees" not in ast.unparse(n):
        return None
    segments = [_segment(p, constantes) or "*" for p in reversed(parties)]
    return "/".join(segments)


def fichiers_du_code() -> set[str]:
    """Fichiers JSON écrits ou lus sous « donnees », et noms de la mémoire de travail."""
    out = set()
    for f in _fichiers():
        arbre = ast.parse(f.read_text(encoding="utf-8"))
        constantes = _constantes(arbre)
        for n in ast.walk(arbre):
            if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Div):
                chemin = _chemin(n, constantes)
                if chemin and chemin.endswith(EXTENSIONS):
                    out.add(chemin)
            elif isinstance(n, ast.Call) and ast.unparse(n.func) in ("memoire.lire", "memoire.ecrire") \
                    and len(n.args) >= 2:
                nom = _segment(n.args[1], constantes)
                if nom:
                    out.add(f"memoire/{nom}.json.gz")
    return out


def _au_catalogue(chemin: str) -> bool:
    return any(fnmatch.fnmatch(chemin, motif) for motif in catalogue.FICHIERS)


def _determine(chemin: str) -> bool:
    """Faux pour un chemin dont le nom ou le dossier est une variable (`f"{nom}.json"`, `dossier / f"{jour}…"`)."""
    return not chemin.startswith("*")


def test_chaque_fichier_du_code_est_au_catalogue():
    obsoletes = set(cycle.FICHIERS_OBSOLETES)
    absents = sorted(c for c in fichiers_du_code()
                     if _determine(c) and c not in obsoletes and not _au_catalogue(c))
    assert absents == [], "fichier de « donnees » absent de cotes/depot/catalogue.py"


def test_detection_des_chemins():
    trouves = fichiers_du_code()
    for attendu in ("paris.json", "etat.json", "pauses.json", "memoire/horizon_direct.json.gz",
                    "memoire/derive_sources.json.gz", "opportunites/*.jsonl.gz"):
        assert attendu in trouves


def test_aucun_fichier_obsolete_au_catalogue():
    assert not set(cycle.FICHIERS_OBSOLETES) & set(catalogue.FICHIERS)


def test_aucune_entree_morte():
    texte = "".join(f.read_text(encoding="utf-8") for f in _fichiers())
    mortes = []
    for motif in catalogue.FICHIERS:
        base = motif.rsplit("/", 1)[-1]
        jeton = re.sub(r"\.json(l)?(\.gz)?$", "", base)
        if "*" in jeton:
            jeton = motif.split("/", 1)[0]
        if not re.search(rf"[\"'/]{re.escape(jeton)}\b", texte):
            mortes.append(motif)
    assert mortes == []


def test_entrees_valides():
    for nom, f in catalogue.FICHIERS.items():
        assert f.zone in catalogue.ZONES, nom
        assert f.format and f.ecrivains and f.retention, nom
        assert (f.zone in ("chaud",)) == ("/" not in nom), nom


def test_tableau_markdown(capsys):
    assert catalogue.main(["--markdown"]) == 0
    sortie = capsys.readouterr().out
    assert sortie.count("\n") == len(catalogue.FICHIERS) + 2
    assert "| `paris.json` | chaud |" in sortie


def test_tableau_copie_dans_la_doc():
    assert catalogue.markdown() in (RACINE / "docs" / "donnees.md").read_text(encoding="utf-8")
