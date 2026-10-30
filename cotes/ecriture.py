"""Ajout sûr à un fichier ``.jsonl.gz`` : jamais de fichier tronqué si le job est tué pendant l'écriture.

``gzip.open(chemin, "at")`` écrit directement à la fin du fichier : un job tué (expiration de 40 min, annulation)
pendant l'écriture laisse un dernier membre gzip incomplet, et toute lecture du fichier échoue ensuite
(``EOFError``). Ici, on copie les octets existants tels quels dans un fichier temporaire du même dossier (aucune
décompression), on y ajoute un nouveau membre gzip complet, on synchronise sur disque puis on remplace le fichier
d'un coup (``os.replace``, atomique sur le même système de fichiers). Interrompu avant le remplacement : l'ancien
fichier est intact (il manque seulement les lignes de ce cycle) ; le ``.tmp`` est ignoré par git (collecte.yml).

Le format est exactement celui de ``gzip.open(..., "at")`` : une suite de membres gzip, lue d'un bloc par
``gzip.open(..., "rt")``. Coût : une copie brute du fichier du jour à chaque ajout (quelques ms par Mo).
"""
from __future__ import annotations

import gzip
import io
import os
import shutil
from pathlib import Path


def ajouter_gzip(chemin: Path, texte: str) -> None:
    """Ajoute ``texte`` (UTF-8) comme nouveau membre gzip à la fin de ``chemin``, de façon atomique."""
    if not texte:
        return
    chemin = Path(chemin)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    tmp = chemin.with_name(chemin.name + ".tmp")
    try:
        if chemin.exists():
            shutil.copyfile(chemin, tmp)
            mode = "ab"
        else:
            mode = "wb"
        with open(tmp, mode) as brut:
            # Même pile que gzip.open(chemin, "at", encoding="utf-8") (en-tête avec le nom d'origine, niveau 9,
            # flux texte UTF-8) : le membre ajouté est identique octet pour octet à celui de l'ancien code.
            with io.TextIOWrapper(gzip.GzipFile(filename=str(chemin), fileobj=brut, mode="wb"),
                                  encoding="utf-8") as g:
                g.write(texte)
                g.flush()
            brut.flush()
            os.fsync(brut.fileno())
        os.replace(tmp, chemin)
    finally:
        tmp.unlink(missing_ok=True)
