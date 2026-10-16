"""La version publiée décrit le HTML entier, données et logique de renouvellement comprises."""
import hashlib
import json
import re

from scripts.site_web import construire


def test_version_publiee_correspond_au_html_et_change_avec_les_donnees(tmp_path):
    sortie = tmp_path / "site"
    html = construire(tmp_path, sortie).read_text()
    version = json.loads((sortie / "version.json").read_text())["version"]
    assert re.fullmatch(r"[a-f0-9]{64}", version)
    assert f'version:"{version}"' in html
    assert "__ACTUALISATION_JS__" not in html
    assert hashlib.sha256(html.replace(version, "__VERSION_SITE__").encode()).hexdigest() == version
    (tmp_path / "etat.json").write_text(json.dumps({"dernier_cycle": {"debut": "2026-10-16T08:00:00Z"}}))
    construire(tmp_path, sortie)
    assert json.loads((sortie / "version.json").read_text())["version"] != version
