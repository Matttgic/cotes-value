"""Enveloppe : l'archivage vit dans cotes/depot/archivage.py (docs/architecture-cible.md, E6.1).

Importé, ce fichier donne ce module-là (les tests qui y remplacent une fonction la remplacent dans le code qui
tourne) ; lancé, il appelle son ``main``. Même commande : python -m cotes archiver.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cotes.depot import archivage  # noqa: E402

if __name__ == "__main__":
    sys.exit(archivage.main())
sys.modules[__name__] = archivage
