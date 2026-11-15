"""Enveloppe du site : la construction vit dans cotes/site/construction.py (docs/architecture-cible.md, E5.4).

`import site_web`, `from scripts import site_web` et `from scripts.site_web import construire` donnent ce module-là :
une fonction du site remplacée dans un test l'est aussi dans le code qui tourne.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cotes.site import construction  # noqa: E402

sys.modules[__name__] = construction
