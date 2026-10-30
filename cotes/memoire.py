"""Mémoire de travail du cycle, hors de la branche « donnees ».

Diagnostic du 29/10/2026 : la branche « donnees » grossissait de 256 Mo par jour. ``horizon_direct.json``
(cotes PMU, Unibet, Betclic et NetBet gardées entre deux lectures, 53 Mo, déjà monté à 99,99 Mo pour une
limite GitHub de 100 Mo) en faisait 76 %, réécrit en entier toutes les 5 minutes alors que 1 % de ses lignes
changeait. ``pinnacle_secours_cache.json`` et ``smarkets_cache.json`` étaient aussi des caches réécrits en
entier. Ces fichiers ne servent qu'au cycle suivant : ils vivent maintenant en gzip dans le dossier
``MEMOIRE_CHEMIN`` (``memoire/`` dans .github/workflows/collecte.yml), gardé par ``actions/cache`` comme
``reprise/``. L'historique utile des cotes va dans ``cotes/AAAA-MM-JJ.jsonl.gz`` (cotes/historique_cotes.py).

Lecture : ``<memoire>/<nom>.json.gz``, sinon l'ancien ``<donnees>/<nom>.json`` (premier cycle après la
migration), sinon la valeur par défaut. Absent ou illisible : démarrage à froid, jamais d'exception.
Écriture : atomique, JSON compact en gzip ; l'ancien fichier de « donnees » est alors supprimé (le commit
suivant le retire de la branche, sans toucher à l'historique).
"""
from __future__ import annotations

import gzip
import json
import os
from pathlib import Path

# Fichiers sortis de la branche « donnees » (le workflow les exclut aussi du git add).
SORTIS = ("horizon_direct", "pinnacle_secours_cache", "smarkets_cache")
NIVEAU_GZIP = 5         # 53 Mo de JSON : ~1 s au niveau 5, contre ~4 s au niveau 9, pour 5 % de plus


def dossier(donnees: Path | None) -> Path | None:
    """Dossier de la mémoire : ``MEMOIRE_CHEMIN`` s'il est rempli, sinon le dossier des données (local, tests)."""
    env = os.environ.get("MEMOIRE_CHEMIN", "").strip()
    if env:
        return Path(env)
    return Path(donnees) if donnees is not None else None


def chemin(donnees: Path | None, nom: str) -> Path | None:
    d = dossier(donnees)
    return d / f"{nom}.json.gz" if d is not None else None


def ancien(donnees: Path | None, nom: str) -> Path | None:
    return Path(donnees) / f"{nom}.json" if donnees is not None else None


def lire(donnees: Path | None, nom: str, defaut=None, ancien_aussi: bool = True):
    """Contenu de la mémoire ``nom`` ; ``defaut`` si elle est absente ou illisible (démarrage à froid)."""
    gz = chemin(donnees, nom)
    if gz is not None:
        try:
            return json.loads(gzip.decompress(gz.read_bytes()))
        except (OSError, EOFError, ValueError):
            pass
    vieux = ancien(donnees, nom) if ancien_aussi else None
    if vieux is not None:
        try:
            return json.loads(vieux.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    return defaut


def ecrire(donnees: Path | None, nom: str, doc, retirer_ancien: bool = True) -> Path | None:
    """Écriture atomique (gzip, JSON compact). Retire l'ancien fichier en clair de « donnees »."""
    gz = chemin(donnees, nom)
    if gz is None:
        return None
    gz.parent.mkdir(parents=True, exist_ok=True)
    tmp = gz.with_name(gz.name + ".tmp")
    brut = json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    tmp.write_bytes(gzip.compress(brut, compresslevel=NIVEAU_GZIP, mtime=0))
    os.replace(tmp, gz)
    vieux = ancien(donnees, nom)
    if retirer_ancien and vieux is not None and vieux != gz:
        try:
            vieux.unlink()
        except FileNotFoundError:
            pass
    return gz
