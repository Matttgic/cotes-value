"""Lecture et écriture JSON des fichiers de « donnees » (docs/architecture-cible.md, E1.4).

Copie exacte des fonctions de `scripts/cycle.py` (qui les réimporte) : même format, même écriture atomique.
"""
from __future__ import annotations

import json
import os
from pathlib import Path


def lire_json(chemin: Path, defaut):
    """Contenu d'un fichier de données, ou `defaut` s'il n'existe pas encore. Un fichier illisible arrête le
    cycle (erreur JSON) : le traiter comme vide écraserait, par exemple, tous les paris à la sauvegarde."""
    try:
        texte = chemin.read_text(encoding="utf-8")
    except FileNotFoundError:
        return defaut
    return json.loads(texte)


def ecrire_json(chemin: Path, donnees, compact: bool = False) -> None:
    """Écriture atomique : un cycle interrompu ne laisse jamais un fichier à moitié écrit.
    ``compact`` : sans indentation ni espaces (fichiers lourds réécrits souvent, comme controle.json)."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    tmp = chemin.with_name(chemin.name + ".tmp")
    texte = (json.dumps(donnees, ensure_ascii=False, separators=(",", ":")) if compact
             else json.dumps(donnees, ensure_ascii=False, indent=1))
    tmp.write_text(texte, encoding="utf-8")
    os.replace(tmp, chemin)
