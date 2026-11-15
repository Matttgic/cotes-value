"""Point d'entrée unique (docs/architecture-cible.md, E6.1) : GitHub, le serveur et le poste local font pareil.

    python -m cotes cycle [options]        # collecte, comparaison, paris, règlement si échu, site (scripts/cycle.py)
    python -m cotes reglement [options]    # règlement seul (cycle --seulement-reglement)
    python -m cotes alertes [options]      # alertes Chrome, Pushover et webhook (scripts/envoyer_notifications.py)
    python -m cotes site [options]         # site depuis les données enregistrées, sans collecter
    python -m cotes archiver [options]     # archive mensuelle des données brutes (scripts/archiver_donnees_brutes.py)
    python -m cotes references [options]   # historique des références en release (cotes/depot/references.py)

Chaque commande garde les options du script qu'elle remplace (`python -m cotes <commande> --help`).
"""
from __future__ import annotations

import importlib
import sys

# commande -> (module, fonction, arguments ajoutés devant ceux donnés)
COMMANDES = {
    "cycle": ("cotes.pipeline.cycle", "main", []),
    "reglement": ("cotes.pipeline.cycle", "main", ["--seulement-reglement"]),
    "alertes": ("cotes.alertes.envoi", "main", []),
    "site": ("cotes.site.construction", "main", []),
    "archiver": ("cotes.depot.archivage", "main", []),
    "references": ("cotes.depot.references", "main", []),
}
AIDE = {
    "cycle": "collecte, comparaison, paris, règlement si échu, site",
    "reglement": "règlement seul (cycle --seulement-reglement)",
    "alertes": "alertes Chrome, Pushover et webhook",
    "site": "site depuis les données enregistrées, sans collecter",
    "archiver": "archive mensuelle des données brutes",
    "references": "historique des références : publier les jours terminés, ou les télécharger",
}


def usage() -> str:
    largeur = max(map(len, COMMANDES))
    return "usage : python -m cotes <commande> [options]\n\ncommandes :\n" + "\n".join(
        f"  {c.ljust(largeur)}  {AIDE[c]}" for c in COMMANDES)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    if not argv or argv[0] in ("-h", "--help", "aide"):
        print(usage())
        return 0 if argv else 2
    commande, reste = argv[0], argv[1:]
    if commande not in COMMANDES:
        print(f"commande inconnue : {commande}\n\n{usage()}", file=sys.stderr)
        return 2
    module, fonction, devant = COMMANDES[commande]
    return getattr(importlib.import_module(module), fonction)(devant + reste)


if __name__ == "__main__":
    sys.exit(main())
