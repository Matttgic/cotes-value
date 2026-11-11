"""Suggestions d'interface du 11/11/2026 : syntaxe de la page construite, trace d'un pari, règlements à vérifier."""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import site_web  # noqa: E402
from tests.test_modes_mise import pari  # noqa: E402

NODE = shutil.which("node")


@pytest.mark.skipif(not NODE, reason="Node absent")
def test_le_script_de_la_page_construite_est_du_javascript_valide(tmp_path):
    """Un nom déclaré deux fois dans une fonction casse toute la page sans faire échouer les tests par morceaux."""
    (tmp_path / "paris.json").write_text(json.dumps([pari(i) for i in range(3)]), encoding="utf-8")
    html = site_web.construire(tmp_path, tmp_path / "site").read_text(encoding="utf-8")
    scripts = re.findall(r"<script(?:\s[^>]*)?>([\s\S]*?)</script>", html)
    assert len(scripts) == 1
    (tmp_path / "page.js").write_text(scripts[0], encoding="utf-8")
    r = subprocess.run([NODE, "--check", str(tmp_path / "page.js")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-600:]


def test_trace_age_du_prix_et_duree_de_vie_chez_le_bookmaker():
    p = {**pari(1, statut="en_cours"), "age_prix_pinnacle_s": 117}
    lignes = site_web.trace(p)
    assert "Prix Pinnacle vieux de 117 s à la détection : frais." in lignes
    assert any("Chez PMU" in l and "65 min" in l for l in lignes)
    vieux = site_web.trace({**p, "age_prix_pinnacle_s": 660, "bookmaker": "Winamax"})
    assert any("11 min" in l and "ancien" in l for l in vieux) and not any("baisse d'habitude" in l for l in vieux)
    regle = site_web.trace({**pari(2), "age_prix_pinnacle_s": None})          # réglé : plus rien à jouer
    assert not any("Prix Pinnacle vieux" in l or "baisse d'habitude" in l for l in regle)
    assert not any("Prix Pinnacle vieux" in l for l in site_web.trace({**p, "age_prix_pinnacle_s": True}))


def test_reglements_incoherents_publies_pour_la_page_sante(tmp_path):
    (tmp_path / "paris.json").write_text(json.dumps([pari(1)]), encoding="utf-8")
    inc = [{"sport": "football", "debut": "2026-10-28T19:30:00Z",
            "a": {"bookmaker": "PMU", "match": "Manchester City – Brighton", "score": [2, 2], "sources": ["livescore"], "paris": ["a"]},
            "b": {"bookmaker": "Winamax", "match": "Manchester City – Brighton", "score": [0, 1], "sources": ["espn"], "paris": ["b"]}}]
    (tmp_path / "resultats_a_saisir.json").write_text(json.dumps({"matchs": [], "incoherences": inc + ["pas un dict"]}), encoding="utf-8")
    html = site_web.construire(tmp_path, tmp_path / "site").read_text(encoding="utf-8")
    d = json.loads(re.search(r"const D = (\{.*?\});\n", html, re.S).group(1).replace("<\\/", "</"))
    assert d["incoherences_reglement"] == inc
    assert 'id="sante-incoherences"' in html and 'id="strategies-avis"' in html
    assert '<option value="bons" selected>' in html                           # « Fiables et prometteuses » par défaut
    assert not re.search(r'<details class="mode-emploi" open><summary>(Mise Kelly|Quelle méthode|Le meilleur compromis|TRJ)', html)
