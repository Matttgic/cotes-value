"""Chaîne d'approvisionnement (audit du 20/11/2026) : actions épinglées par SHA, droits par tâche, verrous hachés."""
import re
from pathlib import Path

import yaml

RACINE = Path(__file__).resolve().parent.parent
WORKFLOWS = sorted((RACINE / ".github" / "workflows").glob("*.yml"))


def test_actions_epinglees_par_sha():
    for f in WORKFLOWS:
        for ligne in f.read_text(encoding="utf-8").splitlines():
            m = re.search(r"uses:\s*([^\s#]+)", ligne)
            if m and not m.group(1).startswith("./"):
                assert re.search(r"@[0-9a-f]{40}$", m.group(1)), f"{f.name} : {m.group(1)} non épinglée par SHA"


def test_droits_en_ecriture_seulement_par_tache():
    for f in WORKFLOWS:
        w = yaml.safe_load(f.read_text(encoding="utf-8"))
        haut = w.get("permissions") or {}
        ecrit = {k for k, v in haut.items() if v == "write"}
        jobs = w.get("jobs") or {}
        if len(jobs) > 1:
            assert not ecrit, f"{f.name} : droits en écriture au niveau du workflow ({sorted(ecrit)})"


def test_jeton_jamais_interpole_dans_run():
    for f in WORKFLOWS:
        w = yaml.safe_load(f.read_text(encoding="utf-8"))
        for nom, job in (w.get("jobs") or {}).items():
            for etape in job.get("steps") or []:
                assert "github.token" not in str(etape.get("run", "")), f"{f.name} › {nom} : jeton dans run:"


def test_cycle_garde_serveur_actif():
    w = yaml.safe_load((RACINE / ".github/workflows/collecte.yml").read_text(encoding="utf-8"))
    assert w["jobs"]["cycle"]["needs"] == "garde" and "serveur" in w["jobs"]["cycle"]["if"]


def test_verrous_haches():
    for nom in ("requirements.txt", "requirements-dev.txt"):
        texte = (RACINE / nom).read_text(encoding="utf-8")
        paquets = re.findall(r"^([A-Za-z0-9_.-]+)==", texte, re.M)
        assert paquets and texte.count("--hash=sha256:") >= len(paquets), nom
