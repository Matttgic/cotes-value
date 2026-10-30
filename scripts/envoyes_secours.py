"""Copie de secours des alertes déjà envoyées (Pushover, webhook Pinnacle 2), hors de la branche « donnees ».

``pushover_envoyes.json`` et ``webhook_envoyes.json`` vivent dans « donnees » : si le push du cycle échoue, ils
sont perdus et le cycle suivant renverrait les mêmes alertes. Le workflow de collecte garde donc aussi une copie
dans le cache Actions (``envoyes/``, sauvegardée même si le push échoue) :

- ``fusionner`` (avant le cycle) : union des id de la copie et de la branche, la date la plus récente gagnant
  (« » = mémorisé sans envoi, toujours battu par une date). Rien n'est écrit si la branche contient déjà tout ;
- ``sauver`` (après les alertes) : copie des fichiers de la branche vers ``envoyes/``.

Le tri des envois de plus de trois jours reste fait par scripts/envoyer_notifications.py. Ne lève jamais :
un fichier illisible est ignoré.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.envoyer_notifications import ENVOYES, PUSHOVER_ENVOYES  # noqa: E402

FICHIERS = (PUSHOVER_ENVOYES, ENVOYES)


def _lire(chemin: Path) -> dict | None:
    try:
        doc = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return doc if isinstance(doc, dict) else None


def fusion(branche: dict, secours: dict) -> dict:
    """Union des id ; pour un même id, la valeur la plus grande (dates ISO UTC comparables, « » la plus petite)."""
    out = dict(branche)
    for k, v in secours.items():
        if not isinstance(v, str):
            continue
        actuel = out.get(k)
        if not isinstance(actuel, str) or v > actuel:
            out[k] = v
    return out


def fusionner(donnees: Path, secours: Path) -> list[str]:
    """Complète les fichiers de la branche avec la copie de secours. Renvoie les fichiers modifiés."""
    from scripts.cycle import ecrire_json
    modifies = []
    for nom in FICHIERS:
        copie = _lire(secours / nom)
        if not copie:
            continue
        chemin = donnees / nom
        actuel = _lire(chemin) if chemin.exists() else {}
        if actuel is None:            # illisible : la copie de secours le remplace
            actuel = {}
        nouveau = fusion(actuel, copie)
        if nouveau != actuel or not chemin.exists():
            ecrire_json(chemin, nouveau)
            modifies.append(nom)
    return modifies


def sauver(donnees: Path, secours: Path) -> list[str]:
    """Copie les fichiers lisibles de la branche vers le dossier de secours. Renvoie les fichiers copiés."""
    copies = []
    for nom in FICHIERS:
        chemin = donnees / nom
        if chemin.exists() and _lire(chemin) is not None:
            secours.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(chemin, secours / nom)
            copies.append(nom)
    return copies


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=("fusionner", "sauver"))
    p.add_argument("--donnees", type=Path, default=Path("donnees"))
    p.add_argument("--secours", type=Path, default=Path("envoyes"))
    a = p.parse_args()
    try:
        faits = (fusionner if a.action == "fusionner" else sauver)(a.donnees, a.secours)
    except Exception as e:  # noqa: BLE001 - jamais bloquant pour le cycle
        print(json.dumps({"action": a.action, "erreur": type(e).__name__}))
        sys.exit(0)
    print(json.dumps({"action": a.action, "fichiers": faits}, ensure_ascii=False))
