"""Robustesse du cycle quand le push de « donnees » échoue, et relance de la chaîne (collecte.yml, reglement.yml)."""
import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

from scripts import envoyes_secours as es

RACINE = Path(__file__).resolve().parents[1]
WF = RACINE / ".github/workflows"


def etapes(fichier, job):
    doc = yaml.safe_load((WF / fichier).read_text(encoding="utf-8"))
    return doc["jobs"][job]["steps"]


def index_nom(steps, debut):
    return next(i for i, s in enumerate(steps) if str(s.get("name", "")).startswith(debut))


# --- mémoire et envois : ordre et conditions des étapes -----------------------------------------------------------

def test_memoire_sauvee_seulement_apres_un_push_reussi():
    steps = etapes("collecte.yml", "cycle")
    push = index_nom(steps, "Enregistrer les données")
    assert steps[push]["id"] == "enregistrer" and steps[push]["if"] == "always()"
    mem = index_nom(steps, "Sauver la mémoire de travail")
    assert mem > push
    assert "steps.enregistrer.outcome == 'success'" in steps[mem]["if"]
    assert steps[mem]["with"]["key"] == "memoire-${{ github.run_id }}-${{ github.run_attempt }}"
    # le dernier bon état des références ne dépend pas de « donnees » : toujours gardé
    rep = index_nom(steps, "Sauver le dernier bon état")
    assert steps[rep]["if"].startswith("always()") and "enregistrer" not in steps[rep]["if"]
    # aucune sauvegarde de cache avant les alertes
    alertes = index_nom(steps, "Envoyer les nouvelles alertes")
    assert all("cache/save" not in str(s.get("uses", "")) or i > alertes for i, s in enumerate(steps))


def test_envois_gardes_en_cache_meme_si_le_push_echoue():
    steps = etapes("collecte.yml", "cycle")
    restaure = index_nom(steps, "Restaurer les alertes déjà envoyées")
    fusion = index_nom(steps, "Fusionner les alertes déjà envoyées")
    cycle = index_nom(steps, "Cycle (collecte")
    alertes = index_nom(steps, "Envoyer les nouvelles alertes")
    copie = index_nom(steps, "Copier les alertes déjà envoyées")
    sauve = index_nom(steps, "Sauver les alertes déjà envoyées")
    push = index_nom(steps, "Enregistrer les données")
    assert index_nom(steps, "Récupérer les données") < restaure < fusion < cycle < alertes < copie < sauve < push
    assert steps[restaure]["with"]["restore-keys"] == "envoyes-"
    assert steps[sauve]["with"]["key"] == "envoyes-${{ github.run_id }}-${{ github.run_attempt }}"
    assert steps[copie]["if"] == "always()" and steps[sauve]["if"].startswith("always()")
    assert "envoyes/" in (RACINE / ".gitignore").read_text().split()


def test_reglement_aligne_sur_la_collecte():
    steps = etapes("reglement.yml", "reglement")
    push = steps[index_nom(steps, "Enregistrer les paris")]
    assert push["if"] == "always()"
    collecte = etapes("collecte.yml", "cycle")[index_nom(etapes("collecte.yml", "cycle"), "Enregistrer les données")]
    for ligne in ("printf '/%s.json.gz\\n' \"$f\" >> .git/info/exclude",
                  "git rm -q --cached --ignore-unmatch horizon_direct.json pinnacle_secours_cache.json smarkets_cache.json",
                  "git push -q origin donnees && exit 0", "for i in 1 2 3 4 5; do", "sleep $((i * 15))",
                  "git pull -q --rebase origin donnees || git rebase --abort 2>/dev/null || true"):
        assert ligne in push["run"] and ligne in collecte["run"]
    assert push["run"].index("git rm -q --cached") < push["run"].index("git add -A")


def test_reglement_n_ajoute_pas_les_caches(tmp_path):
    """Le script réel d'enregistrement de reglement.yml, sur un dépôt local : caches et .tmp jamais commités."""
    nu = tmp_path / "nu.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "donnees", str(nu)], check=True)
    d = tmp_path / "donnees"
    subprocess.run(["git", "clone", "-q", str(nu), str(d)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(d), "checkout", "-q", "-b", "donnees"], check=True)
    for nom in ("paris.json", "controle.json.gz", "horizon_direct.json.gz", "x.json.tmp"):
        (d / nom).write_text("{}")
    steps = etapes("reglement.yml", "reglement")
    script = steps[index_nom(steps, "Enregistrer les paris")]["run"]
    r = subprocess.run(["bash", "-e", "-c", script], cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    suivis = subprocess.run(["git", "--git-dir", str(nu), "ls-tree", "--name-only", "donnees"],
                            capture_output=True, text=True).stdout.split()
    assert suivis == ["paris.json"]


# --- fusion des envois ------------------------------------------------------------------------------------------

def test_fusion_union_et_date_la_plus_recente():
    branche = {"a": "2026-10-29T10:00:00+00:00", "b": "", "c": "2026-10-29T12:00:00+00:00"}
    secours = {"a": "2026-10-29T11:00:00+00:00", "b": "2026-10-29T09:00:00+00:00", "d": "", "e": 3}
    assert es.fusion(branche, secours) == {"a": "2026-10-29T11:00:00+00:00", "b": "2026-10-29T09:00:00+00:00",
                                           "c": "2026-10-29T12:00:00+00:00", "d": ""}
    assert es.fusion(secours, {}) == secours


def test_push_perdu_les_alertes_ne_repartent_pas(tmp_path):
    """Cycle 1 : envois mémorisés puis copiés ; push perdu (branche revenue en arrière) ; cycle 2 : fusion."""
    donnees, secours = tmp_path / "donnees", tmp_path / "envoyes"
    donnees.mkdir()
    (donnees / es.PUSHOVER_ENVOYES).write_text(json.dumps({"p1": "2026-10-29T10:00:00+00:00", "p2": ""}))
    (donnees / es.ENVOYES).write_text(json.dumps({"w1": "2026-10-29T10:00:00+00:00"}))
    assert es.sauver(donnees, secours) == [es.PUSHOVER_ENVOYES, es.ENVOYES]
    # push échoué : le clone suivant n'a que l'ancien état (ici : pas de fichier webhook, pushover partiel)
    (donnees / es.PUSHOVER_ENVOYES).write_text(json.dumps({"p0": "2026-10-28T10:00:00+00:00"}))
    (donnees / es.ENVOYES).unlink()
    assert es.fusionner(donnees, secours) == [es.PUSHOVER_ENVOYES, es.ENVOYES]
    assert set(json.loads((donnees / es.PUSHOVER_ENVOYES).read_text())) == {"p0", "p1", "p2"}
    assert json.loads((donnees / es.ENVOYES).read_text()) == {"w1": "2026-10-29T10:00:00+00:00"}
    # cas normal (push réussi) : la branche contient déjà tout, rien n'est réécrit
    assert es.fusionner(donnees, secours) == []


def test_fusion_ignore_les_fichiers_illisibles(tmp_path):
    donnees, secours = tmp_path / "donnees", tmp_path / "envoyes"
    donnees.mkdir(); secours.mkdir()
    (secours / es.ENVOYES).write_text("{pas du json")
    (donnees / es.PUSHOVER_ENVOYES).write_text("[]")
    assert es.fusionner(donnees, secours) == []
    assert es.sauver(donnees, secours) == []
    assert es.fusionner(tmp_path / "absent", tmp_path / "absent2") == []


# --- relance de la chaîne -------------------------------------------------------------------------------------

def script_relance():
    steps = etapes("collecte.yml", "relancer")
    run = next(s["run"] for s in steps if "run" in s)
    return (run.replace("${{ github.run_id }}", "42").replace("${{ github.ref_name }}", "branche")
               .replace("${{ vars.MODE_COLLECTE || 'complet' }}", "complet"))


def relancer(tmp_path, etat="active", run_list="0", dispatch="ok", battement=""):
    """Exécute le vrai script du job ``relancer`` avec un faux ``gh`` ; ``dispatch`` : ok, 422, 500 ou 404."""
    journal = tmp_path / "appels"
    gh = tmp_path / "gh"
    sorties = {
        "ok": "exit 0",
        "422": 'echo "could not create workflow dispatch event: HTTP 422: Workflow is disabled" >&2; exit 1',
        "500": 'echo "HTTP 500: Internal Server Error" >&2; exit 1',
        "404": 'echo "HTTP 404: Not Found" >&2; exit 1',
        "reseau": 'echo "dial tcp: lookup api.github.com: no such host" >&2; exit 1',
    }
    gh.write_text(f"""#!/bin/bash
echo "$*" >> {journal}
case "$1 $2" in
  "api repos/test/repo/actions/workflows/collecte.yml") echo "{etat}";;
  "api repos/test/repo/actions/runs/42") echo "2026-10-30T00:00:00Z";;
  "run list") echo "{run_list}";;
  "api repos/test/repo/contents/serveur_direct.json?ref=donnees") echo "{battement}";;
  "workflow run") {sorties[dispatch]};;
esac
""")
    gh.chmod(0o755)
    sleep = tmp_path / "sleep"
    sleep.write_text(f"#!/bin/sh\necho sleep >> {journal}\n")
    sleep.chmod(0o755)
    env = {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}", "DEPOT": "test/repo", "DEBUT": "0"}
    r = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", script_relance()],
                       env=env, capture_output=True, text=True)
    appels = journal.read_text().splitlines() if journal.exists() else []
    return r, appels


def test_relance_normale(tmp_path):
    r, appels = relancer(tmp_path)
    assert r.returncode == 0 and "Cycle suivant lancé." in r.stdout
    assert sum(a.startswith("workflow run") for a in appels) == 1


def test_relance_inutile_si_un_lancement_plus_recent(tmp_path):
    r, appels = relancer(tmp_path, run_list="1")
    assert r.returncode == 0 and not any(a.startswith("workflow run") for a in appels)


@pytest.mark.parametrize("etat", ["disabled_manually", "disabled_inactivity"])
def test_workflow_desactive_sortie_propre_sans_relance(tmp_path, etat):
    r, appels = relancer(tmp_path, etat=etat)
    assert r.returncode == 0 and "non actif" in r.stdout
    assert not any(a.startswith("workflow run") for a in appels) and "sleep" not in appels


def test_http_422_sortie_propre_immediate(tmp_path):
    r, appels = relancer(tmp_path, dispatch="422")
    assert r.returncode == 0 and "arrêt propre" in r.stdout
    assert sum(a.startswith("workflow run") for a in appels) == 1 and "sleep" not in appels


@pytest.mark.parametrize("dispatch", ["500", "reseau"])
def test_5xx_et_reseau_reessayes(tmp_path, dispatch):
    r, appels = relancer(tmp_path, dispatch=dispatch)
    assert r.returncode == 1
    assert sum(a.startswith("workflow run") for a in appels) == 6 and appels.count("sleep") == 6


def test_autre_4xx_echec_immediat(tmp_path):
    r, appels = relancer(tmp_path, dispatch="404")
    assert r.returncode == 1 and "::error::" in r.stdout
    assert sum(a.startswith("workflow run") for a in appels) == 1 and "sleep" not in appels


def _git(*args, cwd=None):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def test_clone_partiel_puis_enregistrement_garde_les_jours_passes(tmp_path):
    """Scripts réels : cloner_donnees.sh (sans les anciens jours) puis l'enregistrement de reglement.yml.
    Les jours non extraits restent dans la branche ; ajouts, nouveaux fichiers et suppressions sont poussés."""
    from datetime import datetime, timezone
    auj = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    nu = tmp_path / "nu.git"
    _git("init", "-q", "--bare", "-b", "donnees", str(nu))
    _git("-C", str(nu), "config", "uploadpack.allowFilter", "true")
    source = tmp_path / "source"
    _git("init", "-q", "-b", "donnees", str(source))
    for nom in ("paris.json", "apisports.json", "cotes/2026-10-01.jsonl.gz", f"cotes/{auj}.jsonl.gz",
                "opportunites/2026-10-01.jsonl.gz", "archives/paris-2026-10.json.gz"):
        (source / nom).parent.mkdir(parents=True, exist_ok=True)
        (source / nom).write_text(nom)
    _git("add", "-A", cwd=source)
    _git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "depart", cwd=source)
    _git("push", "-q", str(nu), "donnees", cwd=source)

    r = subprocess.run(["bash", str(RACINE / "scripts/cloner_donnees.sh"), f"file://{nu}", "donnees"],
                       cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    d = tmp_path / "donnees"
    assert "Clone partiel" in r.stdout
    assert not (d / "cotes/2026-10-01.jsonl.gz").exists() and not (d / "opportunites/2026-10-01.jsonl.gz").exists()
    assert (d / f"cotes/{auj}.jsonl.gz").exists() and (d / "archives/paris-2026-10.json.gz").exists()

    (d / f"cotes/{auj}.jsonl.gz").write_text("ajout")
    (d / "opportunites").mkdir(exist_ok=True)              # comme le cycle : aucun fichier extrait dans ce dossier
    (d / f"opportunites/{auj}.jsonl.gz").write_text("nouveau")
    (d / "apisports.json").unlink()
    steps = etapes("reglement.yml", "reglement")
    script = steps[index_nom(steps, "Enregistrer les paris")]["run"]
    r = subprocess.run(["bash", "-e", "-c", script], cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    suivis = _git("--git-dir", str(nu), "ls-tree", "-r", "--name-only", "donnees").split()
    assert suivis == sorted(["paris.json", "archives/paris-2026-10.json.gz", "cotes/2026-10-01.jsonl.gz",
                             f"cotes/{auj}.jsonl.gz", "opportunites/2026-10-01.jsonl.gz", f"opportunites/{auj}.jsonl.gz"])
    assert _git("--git-dir", str(nu), "show", f"donnees:cotes/{auj}.jsonl.gz") == "ajout"
    assert _git("--git-dir", str(nu), "show", "donnees:cotes/2026-10-01.jsonl.gz") == "cotes/2026-10-01.jsonl.gz"


def test_clone_partiel_impossible_repli_sur_le_clone_complet(tmp_path):
    """« sparse-checkout » refusé (git trop ancien, par exemple) : clone complet, avertissement dans le journal."""
    nu = tmp_path / "nu.git"
    _git("init", "-q", "--bare", "-b", "donnees", str(nu))
    source = tmp_path / "source"
    _git("init", "-q", "-b", "donnees", str(source))
    (source / "cotes").mkdir()
    (source / "cotes/2026-10-01.jsonl.gz").write_text("ancien")
    _git("add", "-A", cwd=source)
    _git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "depart", cwd=source)
    _git("push", "-q", str(nu), "donnees", cwd=source)
    faux = tmp_path / "bin"
    faux.mkdir()
    vrai = subprocess.run(["bash", "-c", "command -v git"], capture_output=True, text=True).stdout.strip()
    (faux / "git").write_text(f'#!/bin/bash\nfor a in "$@"; do [ "$a" = sparse-checkout ] && exit 1; done\nexec {vrai} "$@"\n')
    (faux / "git").chmod(0o755)
    env = {**os.environ, "PATH": f"{faux}:{os.environ['PATH']}"}
    r = subprocess.run(["bash", str(RACINE / "scripts/cloner_donnees.sh"), f"file://{nu}", "donnees"],
                       cwd=tmp_path, capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    assert "Clone partiel impossible" in r.stdout
    assert (tmp_path / "donnees/cotes/2026-10-01.jsonl.gz").read_text() == "ancien"


def test_pas_de_relance_quand_le_serveur_en_direct_tient_la_collecte(tmp_path):
    import base64
    from datetime import datetime, timezone
    frais = json.dumps({"vu": datetime.now(timezone.utc).isoformat(), "actif": True})
    r, appels = relancer(tmp_path, battement=base64.b64encode(frais.encode()).decode())
    assert r.returncode == 0 and "Serveur en direct actif" in r.stdout
    assert not any(a.startswith("workflow run") for a in appels)
    arret = json.dumps({"vu": datetime.now(timezone.utc).isoformat(), "actif": False})
    r, appels = relancer(tmp_path / "x" if (tmp_path / "x").mkdir() is None else tmp_path,
                         battement=base64.b64encode(arret.encode()).decode())
    assert "Cycle suivant lancé." in r.stdout                  # arrêt propre du serveur : GitHub reprend
