"""Cotes Value « en direct » sur un petit serveur (docs/serveur-direct.md).

Boucle continue, à la place de la chaîne GitHub Actions (5 minutes, parfois retardée) :

- au démarrage : battement « actif » poussé dans « donnees » (GitHub cesse de relancer sa chaîne), attente de la fin
  d'un cycle ou d'un règlement GitHub en cours, puis reprise de leurs données ;
- chaque cycle (au plus un par ``PERIODE_S``, 60 s par défaut) : collecte, comparaison, paris, puis alertes
  Pushover et Chrome tout de suite (scripts/cycle.py, scripts/envoyer_notifications.py) ;
- toutes les ``PUBLICATION_S`` (300 s) : règlement (effectif une fois par heure), battement, un commit et un push
  de « donnees », puis publication du site par le workflow site.yml ;
- toutes les heures : mise à jour du code (``git pull --ff-only``) ; si le code a changé, le programme s'arrête et
  systemd le relance sur le nouveau code ;
- arrêt (SIGTERM, ``systemctl stop``) : battement « inactif » poussé, GitHub reprend la main à sa prochaine
  surveillance.

Aucune étape ne fait tomber la boucle : un échec est journalisé et le cycle suivant repart.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
DEPOT = os.environ.get("DEPOT", "Matttgic/cotes-value")
PERIODE_S = float(os.environ.get("PERIODE_S", "60"))
PUBLICATION_S = float(os.environ.get("PUBLICATION_S", "300"))
MAJ_CODE_S = 3600
BATTEMENT = "serveur_direct.json"
CACHES = ("horizon_direct", "pinnacle_secours_cache", "smarkets_cache", "controle")
WORKFLOWS_ECRIVAINS = (".github/workflows/collecte.yml", ".github/workflows/reglement.yml")
ATTENTE_GITHUB_MAX_S = 900

_arret = False


def journal(message: str) -> None:
    print(f"{datetime.now(timezone.utc):%Y-%m-%dT%H:%M:%SZ} {message}", flush=True)


def executer(commande: list[str], cwd: Path = RACINE, timeout: float = 600, env: dict | None = None) -> bool:
    """Lance une commande ; jamais d'exception. True si elle a réussi."""
    try:
        r = subprocess.run(commande, cwd=cwd, timeout=timeout, env=env, capture_output=True, text=True)
    except (OSError, subprocess.SubprocessError) as e:
        journal(f"échec {commande[:3]} : {type(e).__name__}")
        return False
    if r.returncode != 0:
        journal(f"échec {commande[:3]} (code {r.returncode}) : {(r.stderr or r.stdout).strip()[-400:]}")
    return r.returncode == 0


def git(*args: str, cwd: Path, timeout: float = 120) -> bool:
    return executer(["git", *args], cwd=cwd, timeout=timeout)


def url_depot(jeton: str, depot: str = DEPOT) -> str:
    return f"https://x-access-token:{jeton}@github.com/{depot}"


def motifs_du_jour(maintenant: datetime) -> list[str]:
    """Mêmes motifs que scripts/cloner_donnees.sh : tout, sauf les jours passés de cotes/ et opportunites/."""
    motifs = ["/*", "!/cotes/*", "!/opportunites/*"]
    for decalage in (-1, 0, 1):
        jour = (maintenant + timedelta(days=decalage)).astimezone(timezone.utc).strftime("%Y-%m-%d")
        motifs += [f"/cotes/{jour}.jsonl.gz", f"/opportunites/{jour}.jsonl.gz"]
    return motifs


def preparer(donnees: Path, jeton: str, depot: str = DEPOT) -> bool:
    """Clone partiel de « donnees » au premier lancement ; identité git et caches exclus à chaque démarrage."""
    if not (donnees / ".git").exists():
        if not executer(["bash", str(RACINE / "scripts/cloner_donnees.sh"), url_depot(jeton, depot), str(donnees)],
                        timeout=900):
            return False
    git("config", "user.name", "cotes-value-serveur", cwd=donnees)
    git("config", "user.email", "cotes-value-serveur@users.noreply.github.com", cwd=donnees)
    exclure = donnees / ".git" / "info" / "exclude"
    exclure.parent.mkdir(parents=True, exist_ok=True)
    lignes = [f"/{c}.json.gz" for c in CACHES] + ["/horizon_direct.json", "/pinnacle_secours_cache.json",
                                                 "/smarkets_cache.json", "*.tmp"]
    deja = exclure.read_text(encoding="utf-8").splitlines() if exclure.exists() else []
    exclure.write_text("\n".join(deja + [l for l in lignes if l not in deja]) + "\n", encoding="utf-8")
    return True


def rafraichir_extraction(donnees: Path, maintenant: datetime, dernier_jour: str | None) -> str:
    """Le serveur tourne des jours : la fenêtre « hier, aujourd'hui, demain » de l'extraction partielle avance avec la
    date, sinon le fichier du jour sortirait de l'extraction et un ajout l'écraserait. Renvoie le jour appliqué."""
    jour = maintenant.astimezone(timezone.utc).strftime("%Y-%m-%d")
    if jour != dernier_jour:
        git("sparse-checkout", "set", "--no-cone", *motifs_du_jour(maintenant), cwd=donnees)
    return jour


def tirer(donnees: Path) -> bool:
    """Reprend les écritures faites ailleurs (résultat saisi à la main…). En conflit, la version du serveur gagne."""
    if git("pull", "-q", "--rebase", "-X", "theirs", "origin", "donnees", cwd=donnees, timeout=300):
        return True
    git("rebase", "--abort", cwd=donnees)
    return False


def ecrire_battement(donnees: Path, maintenant: datetime, actif: bool = True, cycles: int = 0) -> None:
    (donnees / BATTEMENT).write_text(json.dumps({"vu": maintenant.isoformat(timespec="seconds"), "actif": actif,
                                                "cycles": cycles}, ensure_ascii=False), encoding="utf-8")


def enregistrer(donnees: Path, message: str) -> bool:
    """Comme l'étape « Enregistrer les données » de collecte.yml : un commit, trois essais de push."""
    git("rm", "-q", "--cached", "--ignore-unmatch", "horizon_direct.json", "pinnacle_secours_cache.json",
        "smarkets_cache.json", cwd=donnees)
    git("add", "-A", "--sparse", cwd=donnees)
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=donnees).returncode != 0:     # quelque chose à écrire
        git("commit", "-qm", message, cwd=donnees)
    for _ in range(3):
        if git("push", "-q", "origin", "donnees", cwd=donnees, timeout=300):
            return True
        tirer(donnees)
    return False


def api_github(chemin: str, jeton: str, donnees_json: dict | None = None, ouvrir=urllib.request.urlopen):
    """Appel REST GitHub ; (code HTTP, corps JSON ou None). Jamais d'exception."""
    requete = urllib.request.Request(
        f"https://api.github.com/repos/{DEPOT}/{chemin}",
        data=json.dumps(donnees_json).encode() if donnees_json is not None else None,
        method="POST" if donnees_json is not None else "GET",
        headers={"Authorization": f"Bearer {jeton}", "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28"})
    try:
        with ouvrir(requete, timeout=30) as r:
            corps = r.read()
            return r.status, (json.loads(corps) if corps else None)
    except urllib.error.HTTPError as e:
        return e.code, None
    except (OSError, ValueError):
        return 0, None


def github_ecrit_encore(jeton: str, ouvrir=urllib.request.urlopen) -> bool:
    """Un cycle de collecte ou un règlement GitHub est-il en cours ou en file ?"""
    for statut in ("in_progress", "queued"):
        code, corps = api_github(f"actions/runs?status={statut}&per_page=50", jeton, ouvrir=ouvrir)
        if code != 200 or not isinstance(corps, dict):
            continue
        if any(r.get("path") in WORKFLOWS_ECRIVAINS for r in corps.get("workflow_runs") or []):
            return True
    return False


def declencher_site(jeton: str, branche: str, ouvrir=urllib.request.urlopen) -> bool:
    """Publie le site à partir de « donnees » (workflow site.yml) ; 204 attendu."""
    code, _ = api_github("actions/workflows/site.yml/dispatches", jeton, {"ref": branche}, ouvrir=ouvrir)
    if code != 204:
        journal(f"publication du site refusée (HTTP {code})")
    return code == 204


def code_a_change() -> bool:
    """Nouveau code sur la branche suivie ? Si oui, il est appliqué (fast-forward) et le programme doit redémarrer."""
    avant = subprocess.run(["git", "rev-parse", "HEAD"], cwd=RACINE, capture_output=True, text=True).stdout.strip()
    if not git("pull", "-q", "--ff-only", cwd=RACINE, timeout=300):
        return False
    apres = subprocess.run(["git", "rev-parse", "HEAD"], cwd=RACINE, capture_output=True, text=True).stdout.strip()
    return bool(avant and apres and avant != apres)


def environnement(donnees: Path) -> dict:
    return {**os.environ, "MEMOIRE_CHEMIN": str(RACINE / "memoire"),
            "REPRISE_CHEMIN": str(RACINE / "reprise" / "derniere_lecture.json.gz"),
            "MODE_COLLECTE": os.environ.get("MODE_COLLECTE", "complet")}


def un_cycle(donnees: Path, env: dict) -> None:
    py = sys.executable
    executer([py, "scripts/cycle.py", "--reglement", "non", "--sans-site", "--donnees", str(donnees),
              "--site", str(RACINE / "site"), "--reprise", env["REPRISE_CHEMIN"]], timeout=420, env=env)
    executer([py, "scripts/envoyer_notifications.py", "--donnees", str(donnees),
              "--flux", "notifications-rapides.json"], timeout=120, env=env)


def publier(donnees: Path, env: dict, jeton: str, branche: str, cycles: int) -> bool:
    py = sys.executable
    executer([py, "scripts/cycle.py", "--seulement-reglement", "--reglement", "auto", "--sans-site",
              "--donnees", str(donnees), "--site", str(RACINE / "site")], timeout=1500, env=env)
    ecrire_battement(donnees, datetime.now(timezone.utc), True, cycles)
    if not enregistrer(donnees, f"Serveur {datetime.now(timezone.utc):%Y-%m-%dT%H:%M:%SZ}"):
        journal("push de « donnees » en échec : nouvel essai au prochain enregistrement")
        return False
    declencher_site(jeton, branche)
    return True


def _arreter(*_):
    global _arret
    _arret = True


def main() -> int:
    jeton = os.environ.get("GITHUB_TOKEN", "").strip()
    if not jeton:
        journal("GITHUB_TOKEN absent : voir docs/serveur-direct.md")
        return 2
    donnees = RACINE / "donnees"
    branche = os.environ.get("BRANCHE_CODE") or subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=RACINE, capture_output=True, text=True).stdout.strip()
    signal.signal(signal.SIGTERM, _arreter)
    signal.signal(signal.SIGINT, _arreter)
    if not preparer(donnees, jeton):
        journal("clone de « donnees » impossible")
        return 1
    env = environnement(donnees)
    jour = rafraichir_extraction(donnees, datetime.now(timezone.utc), None)
    tirer(donnees)
    ecrire_battement(donnees, datetime.now(timezone.utc))
    enregistrer(donnees, "Serveur en direct : démarrage")         # GitHub cesse de relancer sa chaîne
    debut_attente = time.monotonic()
    while github_ecrit_encore(jeton) and time.monotonic() - debut_attente < ATTENTE_GITHUB_MAX_S and not _arret:
        journal("cycle GitHub en cours : attente de sa fin")
        time.sleep(20)
    tirer(donnees)
    journal(f"démarrage : cycle toutes les {PERIODE_S:g} s, enregistrement toutes les {PUBLICATION_S:g} s")
    cycles, derniere_publication, derniere_maj = 0, time.monotonic(), time.monotonic()
    while not _arret:
        t0 = time.monotonic()
        try:
            jour = rafraichir_extraction(donnees, datetime.now(timezone.utc), jour)
            un_cycle(donnees, env)
            cycles += 1
            if time.monotonic() - derniere_publication >= PUBLICATION_S:
                publier(donnees, env, jeton, branche, cycles)
                derniere_publication = time.monotonic()
            if time.monotonic() - derniere_maj >= MAJ_CODE_S:
                derniere_maj = time.monotonic()
                if code_a_change():
                    journal("nouveau code : enregistrement puis redémarrage")
                    publier(donnees, env, jeton, branche, cycles)
                    return 0                                     # systemd relance sur le nouveau code
        except Exception as e:  # noqa: BLE001 - la boucle ne tombe jamais
            journal(f"erreur inattendue : {type(e).__name__}: {e}")
        reste = PERIODE_S - (time.monotonic() - t0)
        while reste > 0 and not _arret:
            time.sleep(min(reste, 5))
            reste -= 5
    journal("arrêt demandé : la main est rendue à GitHub")
    ecrire_battement(donnees, datetime.now(timezone.utc), actif=False, cycles=cycles)
    enregistrer(donnees, "Serveur en direct : arrêt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
