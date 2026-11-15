"""Relance de la chaîne de collecte (job « relancer » de .github/workflows/collecte.yml, docs/architecture-cible.md E6.2).

Reprend exactement l'ancien script bash du job :

- attendre jusqu'à début du cycle + 270 s (``DEBUT``, secondes epoch) ;
- serveur « en direct » actif (``scripts/serveur_actif.py``) : il tient la collecte, pas de relance ;
- workflow de collecte non actif : pas de relance ;
- un lancement plus récent que celui-ci (``GITHUB_RUN_ID``) existe : il continue la chaîne ;
- sinon ``gh workflow run collecte.yml``, puis contrôle que le cycle suivant démarre (``startup_failure`` : jusqu'à
  3 relances) ;
- erreurs de l'API : HTTP 422 ou workflow désactivé → arrêt propre (0) ; autre 4xx → échec (1) ; 5xx ou réseau
  (aucun code HTTP) → jusqu'à 6 essais espacés de 20 s × n.

``gh`` et ``sleep`` sont appelés par sous-processus : même authentification que le job (``GH_TOKEN``), et les tests
les remplacent par de faux programmes (tests/test_robustesse_workflow.py). Bibliothèque standard seulement : le job
n'extrait que ce fichier et ``scripts/serveur_actif.py``.

Variables : ``DEPOT`` (owner/repo), ``DEBUT``, ``GITHUB_RUN_ID``, ``GITHUB_REF_NAME``, ``MODE_COLLECTE``.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path

ARRET_PROPRE, ECHEC, PASSAGER = 10, 11, 12
ICI = Path(__file__).resolve().parent


def classer(erreur: str) -> int:
    """10 = arrêt propre ; 11 = échec définitif ; 12 = passager (à réessayer)."""
    if re.search(r"HTTP 422|disabled|désactivé", erreur, re.I):
        return ARRET_PROPRE
    if re.search(r"HTTP 5[0-9][0-9]", erreur):
        return PASSAGER
    if re.search(r"HTTP [0-9]{3}", erreur):
        return ECHEC
    return PASSAGER


def gh(*args: str) -> tuple[int, str, str]:
    r = subprocess.run(["gh", *args], capture_output=True, text=True)
    return r.returncode, r.stdout.strip(), r.stderr


def dormir(secondes: int) -> None:
    subprocess.run(["sleep", str(secondes)])


def lancer(depot: str, ref: str, mode: str) -> tuple[int, str, str]:
    return gh("workflow", "run", "collecte.yml", "--repo", depot, "--ref", ref, "-f", f"mode={mode}")


def serveur_actif(depot: str) -> bool:
    r = subprocess.run([sys.executable, str(ICI / "serveur_actif.py"), "--depot", depot], capture_output=True, text=True)
    return r.stdout.strip() == "oui"


def relancer(environ=None) -> int:
    env = os.environ if environ is None else environ
    depot, run_id = env["DEPOT"], env.get("GITHUB_RUN_ID", "")
    ref, mode = env.get("GITHUB_REF_NAME", ""), env.get("MODE_COLLECTE") or "complet"
    debut = int(env.get("DEBUT") or time.time())
    reste = int(debut + 300 - time.time() - 30)
    if reste > 0:
        dormir(reste)
    # Serveur « en direct » actif (docs/serveur-direct.md) : il tient la collecte, la chaîne GitHub s'arrête ici.
    if serveur_actif(depot):
        print("Serveur en direct actif : pas de relance.")
        return 0
    # Une seule chaîne : c'est le lancement le plus récent qui relance le suivant. L'API GitHub renvoie parfois une
    # erreur passagère (HTTP 500 le 7/10/2026 à 16:59, chaîne arrêtée 2 h) : jusqu'à 6 essais espacés, en revérifiant
    # à chaque fois qu'aucun lancement plus récent n'existe (une erreur 500 peut quand même avoir créé le lancement).
    for essai in range(1, 7):
        code, erreur = 0, ""
        retour, etat, erreur_etat = gh("api", f"repos/{depot}/actions/workflows/collecte.yml", "--jq", ".state")
        if retour:
            code, erreur = classer(erreur_etat), erreur_etat
        if code == 0 and etat and etat != "active":
            print(f"Workflow de collecte non actif ({etat}) : pas de relance.")
            return 0
        cree = ""
        if code == 0:
            retour, cree, erreur_cree = gh("api", f"repos/{depot}/actions/runs/{run_id}", "--jq", ".created_at")
            if retour:
                code, erreur = classer(erreur_cree), erreur_cree
            elif not cree:
                code = PASSAGER
        plus_recents = "0"
        if code == 0:
            filtre = (f'[.[] | select(.createdAt > "{cree}") | select(.conclusion != "cancelled" and .conclusion != '
                      f'"skipped" and .conclusion != "startup_failure")] | length')
            retour, plus_recents, erreur_liste = gh("run", "list", "--repo", depot, "--workflow", "collecte.yml",
                                                    "--limit", "20", "--json", "createdAt,conclusion", "--jq", filtre)
            if retour:
                code, erreur = classer(erreur_liste), erreur_liste
        if code == 0:
            if plus_recents.isdigit() and int(plus_recents) > 0:     # autre réponse : comme le bash, pas > 0
                print("Un lancement plus récent continue la chaîne.")
                return 0
            retour, _, erreur = lancer(depot, ref, mode)
            if retour == 0:
                print("Cycle suivant lancé.")
                # Garde-fou (11/11/2026) : un lancement peut échouer au démarrage (« startup_failure », incident
                # GitHub) ; on vérifie que le cycle suivant démarre vraiment, et on le relance jusqu'à 3 fois sinon.
                for verif in range(1, 4):
                    dormir(60)
                    retour, dernier, _ = gh("run", "list", "--repo", depot, "--workflow", "collecte.yml", "--limit",
                                            "5", "--json", "createdAt,conclusion,status", "--jq",
                                            f'[.[] | select(.createdAt > "{cree}")][0] | (.conclusion // .status)')
                    dernier = dernier if retour == 0 else "inconnu"
                    if dernier != "startup_failure":
                        print(f"Cycle suivant démarré ({dernier}).")
                        return 0
                    print(f"::warning title=Relance::Le cycle suivant a échoué au démarrage : nouvelle relance ({verif}/3).")
                    lancer(depot, ref, mode)
                print("::error::Le cycle suivant échoue au démarrage malgré 3 relances.")
                return 1
            code = classer(erreur)
        for ligne in erreur.splitlines()[:5]:
            print("  " + ligne)
        if code == ARRET_PROPRE:
            print("Relance refusée (HTTP 422 ou workflow désactivé) : arrêt propre.")
            return 0
        if code == ECHEC:
            print("::error::Relance refusée par l'API GitHub (erreur 4xx, voir ci-dessus).")
            return 1
        print(f"API GitHub indisponible (essai {essai}), nouvel essai dans {essai * 20} s", flush=True)
        dormir(essai * 20)
    return 1


if __name__ == "__main__":
    sys.exit(relancer())
