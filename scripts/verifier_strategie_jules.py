"""Audit descriptif reproductible, sans réglage des critères ni appels API.

python scripts/verifier_strategie_jules.py --donnees chemin/du/snapshot --releve DATE --sortie rapport.json
La version des données est indiquée par leur commit et leur empreinte SHA-256.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cotes.laboratoire import heure, resume  # noqa: E402
from cotes.stockage import lire_archives  # noqa: E402
from cotes.strategie_jules import DEBUT_REJEU, JULES, paris_jules  # noqa: E402


def rapport(paris: list[dict], releve: str) -> dict:
    cutoff = heure(releve)
    if not cutoff:
        raise ValueError("Relevé invalide ou sans fuseau horaire")
    if len({p['id'] for p in paris}) != len(paris):
        raise ValueError("Identifiants de paris dupliqués")
    observes = [p for p in paris if heure(p.get("detecte")) and heure(p["detecte"]) < cutoff]
    selection = paris_jules(observes, depuis=DEBUT_REJEU)
    lignes = [p for p in observes if id(p) in selection]
    return {
        "schema": 1, "strategie": JULES, "depuis_rejeu": DEBUT_REJEU, "releve": releve,
        "nature": "Rejeu descriptif a posteriori ; aucune validation indépendante ni rentabilité future démontrée.",
        "ensemble": resume(lignes, releve, incertitude=False),
        "ids_selections": [p["id"] for p in lignes],
    }


def main():
    a = argparse.ArgumentParser(description=__doc__)
    a.add_argument("--donnees", type=Path, required=True)
    a.add_argument("--releve", required=True)
    a.add_argument("--sortie", type=Path, required=True)
    args = a.parse_args()
    paris = json.loads((args.donnees / "paris.json").read_text()) + lire_archives(args.donnees)
    r = rapport(paris, args.releve)
    r["source_sha256"] = hashlib.sha256(json.dumps(paris, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    r["source_commit"] = subprocess.check_output(
        ["git", "-C", str(args.donnees), "rev-parse", "HEAD"], text=True).strip()
    args.sortie.parent.mkdir(parents=True, exist_ok=True)
    args.sortie.write_text(json.dumps(r, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(r["ensemble"], ensure_ascii=False))


if __name__ == "__main__":
    main()
