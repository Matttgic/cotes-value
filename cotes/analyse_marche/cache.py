"""Résumé par jour, gardé en cache : un jour terminé n'est jamais recalculé.

``<cache>/AAAA-MM-JJ.json.gz`` : {"version", "jour", "episodes": [...], "meneurs": [...]}. Un jour n'est écrit
que lorsque son lendemain est lui aussi terminé (les épisodes d'opportunité se lisent sur le lendemain). Changer
``VERSION`` (règle de calcul modifiée) fait tout recalculer une fois.
"""
from __future__ import annotations

import gzip
import json
import os
import tempfile
import zlib
from pathlib import Path

from . import lecture as L
from .meneurs import meneurs_du_jour
from .opportunites import episodes_du_jour

VERSION = 1


def jour_termine(jour: str, aujourd_hui: str | None = None) -> bool:
    """Le jour et son lendemain sont finis (UTC) : plus aucune donnée ne peut s'y ajouter."""
    return L.decaler(jour, 1) < (aujourd_hui or L.aujourd_hui())


def calculer(donnees, jour: str) -> dict:
    return {"version": VERSION, "jour": jour, "episodes": episodes_du_jour(donnees, jour),
            "meneurs": meneurs_du_jour(donnees, jour)}


def _lire(f: Path) -> dict | None:
    try:
        doc = json.loads(gzip.decompress(f.read_bytes()))
    except (OSError, EOFError, ValueError, zlib.error):
        return None
    return doc if isinstance(doc, dict) and doc.get("version") == VERSION else None


def _ecrire(f: Path, doc: dict) -> None:
    f.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=f.parent, suffix=".tmp")
    with os.fdopen(fd, "wb") as sortie:
        sortie.write(gzip.compress(json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode(), 6))
    os.replace(tmp, f)


def resume(donnees, jour: str, dossier_cache: Path | None, aujourd_hui: str | None = None) -> tuple[dict, str]:
    """(résumé du jour, « cache » | « calculé » | « provisoire »). Provisoire : jour pas encore terminé."""
    f = Path(dossier_cache) / f"{jour}.json.gz" if dossier_cache else None
    if f is not None and f.exists():
        doc = _lire(f)
        if doc is not None:
            return doc, "cache"
    doc = calculer(donnees, jour)
    if not jour_termine(jour, aujourd_hui):
        return doc, "provisoire"
    if f is not None:
        _ecrire(f, doc)
    return doc, "calculé"


def jours_disponibles(donnees) -> list[str]:
    return sorted(set(L.jours(donnees, "cotes")) | set(L.jours(donnees, "opportunites")))
