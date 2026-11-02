"""Battement du serveur en direct : GitHub s'efface seulement s'il est récent et actif ; les workflows le lisent."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from scripts import serveur_actif as S

NOW = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)
RACINE = Path(__file__).resolve().parents[1]


def battement(minutes, actif=True):
    import json
    return json.dumps({"vu": (NOW - timedelta(minutes=minutes)).isoformat(), "actif": actif})


def test_recent_et_actif_seulement():
    assert S.actif(battement(4), NOW) is True
    assert S.actif(battement(14.9), NOW) is True
    assert S.actif(battement(15), NOW) is False                 # trop vieux : GitHub reprend
    assert S.actif(battement(1, actif=False), NOW) is False     # arrêt propre du serveur
    assert S.actif(battement(-10), NOW) is False                # horloge du serveur très en avance : ignoré
    for illisible in (None, "", "{", '{"vu": "hier"}', '{"vu": "2026-11-03T11:59:00"}', "[]"):
        assert S.actif(illisible, NOW) is False


def test_les_workflows_consultent_le_serveur_avant_de_relancer_ou_de_regler():
    collecte = (RACINE / ".github/workflows/collecte.yml").read_text(encoding="utf-8")
    relance = next(s["run"] for s in yaml.safe_load(collecte)["jobs"]["relancer"]["steps"] if "run" in s)
    assert relance.index("serveur_actif.py") < relance.index("gh workflow run collecte.yml")
    surveillance = yaml.safe_load((RACINE / ".github/workflows/surveillance-collecte.yml").read_text(encoding="utf-8"))
    run = next(s["run"] for s in surveillance["jobs"]["verifier"]["steps"] if "run" in s)
    assert run.index("serveur_actif.py") < run.index("gh workflow run collecte.yml")
    reglement = yaml.safe_load((RACINE / ".github/workflows/reglement.yml").read_text(encoding="utf-8"))
    assert reglement["jobs"]["reglement"]["needs"] == "garde"
    assert "needs.garde.outputs.serveur != 'oui'" in reglement["jobs"]["reglement"]["if"]
