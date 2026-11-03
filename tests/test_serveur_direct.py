"""Serveur en direct : extraction qui suit la date, battement lu par GitHub, enregistrement, conflit, API GitHub."""
import io
import json
import subprocess
from datetime import datetime, timezone
from urllib.error import HTTPError

from scripts import serveur_actif, serveur_direct as SD

T = datetime(2026, 11, 3, 23, 50, tzinfo=timezone.utc)


def _git(*args, cwd=None):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def _depot(tmp_path):
    """Faux GitHub : branche donnees avec un ancien jour, le jour courant et paris.json ; clone partiel du serveur."""
    nu = tmp_path / "nu.git"
    _git("init", "-q", "--bare", "-b", "donnees", str(nu))
    _git("-C", str(nu), "config", "uploadpack.allowFilter", "true")
    src = tmp_path / "src"
    _git("init", "-q", "-b", "donnees", str(src))
    for nom, contenu in (("paris.json", "[1]"), ("cotes/2026-10-01.jsonl.gz", "ancien"),
                         ("cotes/2026-11-03.jsonl.gz", "jour"), ("opportunites/2026-11-04.jsonl.gz", "demain")):
        (src / nom).parent.mkdir(parents=True, exist_ok=True)
        (src / nom).write_text(contenu)
    _git("add", "-A", cwd=src)
    _git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "depart", cwd=src)
    _git("push", "-q", str(nu), "donnees", cwd=src)
    d = tmp_path / "donnees"
    subprocess.run(["bash", str(SD.RACINE / "scripts/cloner_donnees.sh"), f"file://{nu}", str(d)], check=True,
                   capture_output=True)
    assert SD.preparer(d, "jeton-inutile")
    return nu, d


def test_motifs_hier_aujourd_hui_demain_en_utc():
    m = SD.motifs_du_jour(T)
    assert m[:3] == ["/*", "!/cotes/*", "!/opportunites/*"]
    assert "/cotes/2026-11-02.jsonl.gz" in m and "/cotes/2026-11-04.jsonl.gz" in m and "/opportunites/2026-11-03.jsonl.gz" in m


def test_battement_ecrit_par_le_serveur_lu_par_github(tmp_path):
    SD.ecrire_battement(tmp_path, T, cycles=12)
    contenu = (tmp_path / SD.BATTEMENT).read_text()
    assert json.loads(contenu) == {"vu": "2026-11-03T23:50:00+00:00", "actif": True, "cycles": 12}
    assert serveur_actif.actif(contenu, T) is True
    SD.ecrire_battement(tmp_path, T, actif=False)
    assert serveur_actif.actif((tmp_path / SD.BATTEMENT).read_text(), T) is False


def test_enregistrer_garde_les_jours_non_extraits_et_le_serveur_gagne_un_conflit(tmp_path):
    nu, d = _depot(tmp_path)
    assert not (d / "cotes/2026-10-01.jsonl.gz").exists()
    # quelqu'un d'autre pousse un changement de paris.json (règlement GitHub en retard) et un fichier manuel
    autre = tmp_path / "autre"
    _git("clone", "-q", "--branch", "donnees", f"file://{nu}", str(autre))
    (autre / "paris.json").write_text("[2]")
    (autre / "resultats_manuels.json").write_text("{}")
    _git("add", "-A", cwd=autre)
    _git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "autre", cwd=autre)
    _git("push", "-q", "origin", "donnees", cwd=autre)
    # le serveur écrit sa version de paris.json, ajoute au fichier du jour, puis enregistre
    (d / "paris.json").write_text("[3]")
    (d / "cotes/2026-11-03.jsonl.gz").write_text("jour+ajout")
    SD.ecrire_battement(d, T)
    assert SD.enregistrer(d, "test")
    montrer = lambda chemin: _git("--git-dir", str(nu), "show", f"donnees:{chemin}")
    assert montrer("paris.json") == "[3]"                               # le serveur fait foi
    assert montrer("resultats_manuels.json") == "{}"                    # l'autre écriture est gardée
    assert montrer("cotes/2026-10-01.jsonl.gz") == "ancien"             # jour non extrait intact
    assert montrer("cotes/2026-11-03.jsonl.gz") == "jour+ajout"
    assert serveur_actif.actif(montrer(SD.BATTEMENT), T)


def test_l_extraction_suit_la_date(tmp_path):
    nu, d = _depot(tmp_path)
    jour = SD.rafraichir_extraction(d, T, None)
    assert jour == "2026-11-03" and (d / "opportunites/2026-11-04.jsonl.gz").exists()
    lendemain = datetime(2026, 11, 5, 0, 5, tzinfo=timezone.utc)
    assert SD.rafraichir_extraction(d, lendemain, jour) == "2026-11-05"
    assert not (d / "cotes/2026-11-03.jsonl.gz").exists()            # hors de la fenêtre : plus extrait
    assert (d / "opportunites/2026-11-04.jsonl.gz").exists()          # hier : toujours là


class _Rep(io.BytesIO):
    def __init__(self, corps, status=200):
        super().__init__(json.dumps(corps).encode() if corps is not None else b"")
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_api_github_cycles_en_cours_et_publication_du_site():
    vus = []

    def ouvrir(requete, timeout=None):
        vus.append((requete.get_method(), requete.full_url))
        if "dispatches" in requete.full_url:
            return _Rep(None, 204)
        if "in_progress" in requete.full_url:
            return _Rep({"workflow_runs": [{"path": ".github/workflows/site.yml"}]})
        return _Rep({"workflow_runs": [{"path": ".github/workflows/collecte.yml"}]})
    assert SD.github_ecrit_encore("j", ouvrir) is True                 # collecte en file
    assert SD.declencher_site("j", "main", ouvrir) is True
    assert vus[-1] == ("POST", "https://api.github.com/repos/Matttgic/cotes-value/actions/workflows/site.yml/dispatches")

    def refuse(requete, timeout=None):
        raise HTTPError(requete.full_url, 403, "interdit", {}, None)
    assert SD.github_ecrit_encore("j", refuse) is False and SD.declencher_site("j", "main", refuse) is False
