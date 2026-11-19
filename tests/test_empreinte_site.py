"""Empreinte du site (scripts/empreinte_site.py, étape E0.1 de docs/architecture-cible.md)."""
import datetime as dt
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
from scripts import empreinte_site as es  # noqa: E402


def _pari(i: int, cote: float = 1.8) -> dict:
    return {"id": f"p{i}", "simulation": "D", "match_id": f"winamax|{i}", "reference": "Pinnacle",
            "bookmaker": "Betclic", "sport": "football", "marche": "TOTAL", "periode": "MATCH", "ligne": 2.5,
            "issue": "PLUS", "detecte": f"2026-10-1{i}T12:00:00Z", "debut": f"2026-10-1{i}T18:00:00Z",
            "cloture_lue": f"2026-10-1{i}T17:40:00Z", "regle_le": f"2026-10-1{i}T20:00:00Z",
            "statut": "gagne" if i % 2 else "perdu", "cote": cote, "mise": 10,
            "gain": round(10 * (cote - 1), 2) if i % 2 else -10, "clv": 0.02}


def _creer(dossier: Path) -> Path:
    dossier.mkdir()
    (dossier / "paris.json").write_text(json.dumps([_pari(i) for i in range(1, 4)]), encoding="utf-8")
    return dossier


@pytest.fixture
def donnees(tmp_path):
    return _creer(tmp_path / "donnees")


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    """Une construction partagée (environ 2 s chacune) : données intactes et empreinte de référence."""
    d = _creer(tmp_path_factory.mktemp("empreinte") / "donnees")
    return d, _contenu(d), es.empreinte(d)


def _contenu(dossier: Path) -> dict:
    return {f.relative_to(dossier).as_posix(): f.read_bytes() for f in dossier.rglob("*") if f.is_file()}


def test_meme_donnees_meme_empreinte_et_donnees_intactes(base):
    dossier, avant, e1 = base
    assert es.differences(e1, es.empreinte(dossier)) == []
    assert "site/index.html" in e1["fichiers"] and e1["modules_figes"] > 0
    assert _contenu(dossier) == avant                        # la construction tourne sur une copie


def test_l_heure_figee_compte(base):
    dossier, _, e1 = base
    assert es.differences(e1, es.empreinte(dossier, "2026-11-20T12:00:00+00:00"))[0].startswith("heure différente")
    with pytest.raises(ValueError):
        es.empreinte(dossier, "2026-11-15T12:00:00")           # sans fuseau


def test_chronometres_figes_puis_remis_en_place():
    es.importer_tout()
    from cotes import protection
    with es.chronometres_figes() as remplaces:
        assert remplaces > 0 and protection.perf_counter() == 0.0
    assert protection.perf_counter is time.perf_counter


def test_l_heure_est_passee_a_la_construction(base, monkeypatch):
    """L'heure n'est plus figée par remplacement (E5.3) : ``construire`` la reçoit."""
    from scripts import site_web
    vues = []
    vraie = site_web.construire
    monkeypatch.setattr(site_web, "construire", lambda d, s, m=None: vues.append(m) or vraie(d, s, m))
    es.empreinte(base[0], "2026-11-15T12:00:00+00:00")
    assert vues == [dt.datetime(2026, 11, 15, 12, tzinfo=dt.timezone.utc)]


def test_sans_reseau_ni_envoi_puis_remis_en_place(monkeypatch):
    monkeypatch.setenv("PUSHOVER_APP_TOKEN", "x")
    monkeypatch.setenv("MEMOIRE_CHEMIN", "/ailleurs")
    with es.sans_reseau_ni_envoi():
        assert "PUSHOVER_APP_TOKEN" not in os.environ and "MEMOIRE_CHEMIN" not in os.environ
        with pytest.raises(OSError):
            socket.create_connection(("example.com", 443))
    assert os.environ["PUSHOVER_APP_TOKEN"] == "x" and socket.create_connection is not es._reseau_coupe


def test_ligne_de_commande_un_pari_change_l_empreinte_change(donnees, tmp_path):
    script = [sys.executable, str(RACINE / "scripts" / "empreinte_site.py"), "--donnees", str(donnees)]
    ref = tmp_path / "ref.json"
    r = subprocess.run([*script, "--sortie", str(ref)], capture_output=True, text=True, timeout=300, check=False)
    assert r.returncode == 0, r.stderr
    assert json.loads(ref.read_text(encoding="utf-8"))["hash_seed"] == "0"   # relancé avec PYTHONHASHSEED=0
    paris = json.loads((donnees / "paris.json").read_text(encoding="utf-8"))
    paris[1]["statut"] = "rembourse"
    (donnees / "paris.json").write_text(json.dumps(paris), encoding="utf-8")
    r = subprocess.run([*script, "--comparer", str(ref)], capture_output=True, text=True, timeout=300, check=False)
    assert r.returncode == 1 and "différent : site/index.html" in r.stdout
