"""Un ancien collecteur ne doit pas republier une ancienne interface."""
import os
from pathlib import Path
import subprocess

import pytest


@pytest.mark.parametrize("workflow", ["site.yml", "collecte.yml", "reglement.yml"])
@pytest.mark.parametrize("commit,api_ok,autorise", [("recent", True, True), ("ancien", True, False), ("recent", False, False)])
def test_garde_publication_execute_le_script_reel(tmp_path, workflow, commit, api_ok, autorise):
    texte = (Path(__file__).resolve().parents[1] / ".github/workflows" / workflow).read_text()
    bloc = "dernier=$(gh api" + texte.split("dernier=$(gh api", 1)[1].split("\n      - ", 1)[0]
    script = "\n".join(l[10:] if l.startswith("          ") else l for l in bloc.splitlines())
    gh = tmp_path / "gh"
    gh.write_text('#!/bin/sh\nprintf "recent\\n"\n' if api_ok else '#!/bin/sh\nexit 1\n')
    gh.chmod(0o755)
    sortie = tmp_path / "output"
    sortie.touch()
    env = {**os.environ, "PATH": str(tmp_path) + ":" + os.environ["PATH"], "GITHUB_SHA": commit,
           "GITHUB_OUTPUT": str(sortie), "GITHUB_REPOSITORY": "test/repo", "GITHUB_REF_NAME": "branche"}
    resultat = subprocess.run(["bash", "-e", "-c", script], env=env, capture_output=True)
    assert (resultat.returncode == 0) == api_ok
    assert ("publier=true" in sortie.read_text()) == autorise
    assert "if: steps.fraicheur.outputs.publier == 'true'" in texte
