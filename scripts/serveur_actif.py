"""Le serveur « en direct » (scripts/serveur_direct.py) tient-il la collecte ? Lu par les workflows GitHub.

Le serveur écrit ``serveur_direct.json`` dans la branche « donnees » à chaque enregistrement (toutes les 5 minutes) :
``{"vu": heure UTC, "actif": true}``. Tant que ce battement a moins de ``FRAIS_MIN`` minutes, la collecte, le
règlement et la relance de GitHub s'effacent : deux moteurs qui écriraient les mêmes paris se contrediraient.
Battement plus vieux, absent, illisible ou ``"actif": false`` (arrêt propre du serveur) : GitHub reprend la main.

    python scripts/serveur_actif.py --depot OWNER/REPO     # imprime « oui » ou « non » (jamais d'erreur)
"""
from __future__ import annotations

import argparse
import base64
import json
import subprocess
from datetime import datetime, timedelta, timezone

FICHIER = "serveur_direct.json"
FRAIS_MIN = 15


def actif(contenu: str | None, maintenant: datetime | None = None) -> bool:
    """True si le battement est récent (moins de FRAIS_MIN minutes, horloge tolérée 5 min en avance) et actif."""
    maintenant = maintenant or datetime.now(timezone.utc)
    try:
        doc = json.loads(contenu or "")
        vu = datetime.fromisoformat(str(doc["vu"]).replace("Z", "+00:00"))
    except (ValueError, TypeError, KeyError):
        return False
    if vu.tzinfo is None or doc.get("actif") is False:
        return False
    return -timedelta(minutes=5) <= maintenant - vu < timedelta(minutes=FRAIS_MIN)


def lire_battement(depot: str) -> str | None:
    """Contenu de serveur_direct.json sur la branche « donnees » (API GitHub via gh), ou None."""
    try:
        r = subprocess.run(["gh", "api", f"repos/{depot}/contents/{FICHIER}?ref=donnees", "--jq", ".content"],
                           capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0 or not r.stdout.strip():
        return None
    try:
        return base64.b64decode(r.stdout.strip()).decode("utf-8")
    except (ValueError, UnicodeError):
        return None


def main() -> int:
    a = argparse.ArgumentParser()
    a.add_argument("--depot", required=True)
    print("oui" if actif(lire_battement(a.parse_args().depot)) else "non")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
