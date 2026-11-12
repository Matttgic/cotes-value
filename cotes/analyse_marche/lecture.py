"""Lecture en flux des fichiers journaliers ``<dossier>/AAAA-MM-JJ.jsonl.gz``."""
from __future__ import annotations

import gzip
import json
import re
import zlib
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

from ..temps import instant_utc

NOM = re.compile(r"^(\d{4}-\d{2}-\d{2})\.jsonl\.gz$")


def jours(donnees: Path, dossier: str) -> list[str]:
    """Jours (AAAA-MM-JJ) présents dans ``donnees/dossier``, triés."""
    d = Path(donnees) / dossier
    return sorted(m.group(1) for f in d.glob("*.jsonl.gz") if (m := NOM.match(f.name))) if d.is_dir() else []


def chemin(donnees: Path, dossier: str, jour: str) -> Path:
    return Path(donnees) / dossier / f"{jour}.jsonl.gz"


def lignes_brutes(f: Path) -> Iterator[str]:
    """Lignes texte d'un fichier ; absent, tronqué ou abîmé : ce qui a pu être lu."""
    if not f.exists():
        return
    try:
        with gzip.open(f, "rt", encoding="utf-8") as flux:
            yield from flux
    except (OSError, EOFError, zlib.error):
        return


def lire(f: Path, filtre=None) -> Iterator[dict]:
    """Objets JSON d'un fichier. ``filtre(texte)`` écarte une ligne avant l'analyse JSON (plus rapide)."""
    for brut in lignes_brutes(f):
        if filtre is not None and not filtre(brut):
            continue
        try:
            d = json.loads(brut)
        except ValueError:
            continue
        if isinstance(d, dict):
            yield d


def decaler(jour: str, n: int) -> str:
    return (date.fromisoformat(jour) + timedelta(days=n)).isoformat()


def aujourd_hui() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def t(valeur) -> datetime | None:
    return instant_utc(valeur)
