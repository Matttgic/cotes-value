"""Enveloppe : l'envoi des alertes vit dans cotes/alertes/envoi.py (docs/architecture-cible.md, E6.1).

Importé, ce fichier donne ce module-là (les tests qui y remplacent une fonction la remplacent dans le code qui
tourne) ; lancé, il appelle son ``main``. Même commande : python -m cotes alertes.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cotes.alertes import envoi  # noqa: E402

if __name__ == "__main__":
    sys.exit(envoi.main())
sys.modules[__name__] = envoi
