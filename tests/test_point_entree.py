"""Point d'entrée unique `python -m cotes` (cotes/__main__.py, E6.1)."""
import importlib
import subprocess
import sys
from pathlib import Path

import pytest

from cotes import __main__ as entree

RACINE = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("commande,module,devant", [
    ("cycle", "cotes.pipeline.cycle", []),
    ("reglement", "cotes.pipeline.cycle", ["--seulement-reglement"]),
    ("alertes", "cotes.alertes.envoi", []),
    ("site", "cotes.site.construction", []),
    ("archiver", "cotes.depot.archivage", []),
])
def test_chaque_commande_appelle_sa_fonction(monkeypatch, commande, module, devant):
    vus = []
    monkeypatch.setattr(importlib.import_module(module), "main", lambda argv: vus.append(argv) or 7)
    assert entree.main([commande, "--donnees", "d"]) == 7
    assert vus == [devant + ["--donnees", "d"]]


def test_aide_liste_les_commandes(capsys):
    assert entree.main(["--help"]) == 0
    sortie = capsys.readouterr().out
    for commande in entree.COMMANDES:
        assert f"  {commande}" in sortie
    assert entree.main([]) == 2
    assert entree.main(["inconnue"]) == 2


def test_python_m_cotes_help():
    r = subprocess.run([sys.executable, "-m", "cotes", "--help"], cwd=RACINE, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and "reglement" in r.stdout


def test_options_des_scripts_gardees(capsys):
    """Mêmes options que les scripts remplacés."""
    from cotes.pipeline.cycle import arguments
    a = arguments(["--mode", "test", "--donnees", "x", "--sans-site", "--reglement", "non", "--seulement-reglement"])
    assert (a.mode, a.donnees, a.sans_site, a.reglement, a.seulement_reglement) == ("test", "x", True, "non", True)
    with pytest.raises(SystemExit):
        importlib.import_module("cotes.alertes.envoi").main(["--help"])
    assert "--strategies" in capsys.readouterr().out


def test_les_scripts_restent_des_enveloppes():
    from scripts import archiver_donnees_brutes, envoyer_notifications
    from cotes.alertes import envoi
    from cotes.depot import archivage
    assert envoyer_notifications is envoi and archiver_donnees_brutes is archivage
    r = subprocess.run([sys.executable, "scripts/envoyer_notifications.py", "--help"], cwd=RACINE,
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and "--strategies" in r.stdout
