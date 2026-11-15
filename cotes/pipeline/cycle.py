"""Cycle complet (déplacé de scripts/cycle.py, E6.1) : arguments et enchaînement des étapes sur un même Contexte,
collecte → analyse → prise → règlement → sauvegarde, puis le site. `python -m cotes cycle` et `scripts/cycle.py`
l'appellent."""
from __future__ import annotations

import argparse
import json
import os
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from cotes.pipeline import reglement
from cotes.pipeline.analyse import analyser
from cotes.pipeline.collecte import collecter
from cotes.pipeline.contexte import Contexte
from cotes.pipeline.prise import prendre
from cotes.pipeline.sauvegarde import sauvegarder


def arguments(argv: list[str] | None = None) -> argparse.Namespace:
    a = argparse.ArgumentParser(prog="cycle")
    a.add_argument("--mode", choices=["complet", "test"], default=os.environ.get("MODE_COLLECTE", "complet"))
    a.add_argument("--donnees", default="donnees")
    a.add_argument("--site", default="site")
    a.add_argument("--sans-site", action="store_true",
                   help="Sauvegarder la collecte avant le chemin rapide d'alertes ; site construit ensuite")
    a.add_argument("--reglement", choices=["auto", "oui", "non"], default=os.environ.get("REGLEMENT", "auto"),
                   help="auto = si le dernier règlement date d'au moins REGLEMENT_MINUTES")
    a.add_argument("--reprise", default=os.environ.get("REPRISE_CHEMIN", ""),
                   help="Dernier bon état des références (gzip, hors branche « donnees ») ; vide = aucune reprise")
    a.add_argument("--seulement-reglement", action="store_true",
                   help="Régler les paris sans interroger les cotes ni créer de nouveaux paris")
    return a.parse_args(argv)


def executer(args: argparse.Namespace, construire_site: Callable | None = None) -> int:
    """Enchaîne les étapes ; ``construire_site(donnees, sortie)`` construit le site (cotes/site par défaut)."""
    if construire_site is None:
        from cotes.site.construction import construire as construire_site
    donnees = Path(args.donnees)
    maintenant = datetime.now(timezone.utc)
    journal = {"debut": maintenant.isoformat(timespec="seconds"), "mode": args.mode, "etapes": {}}

    ctx = Contexte(maintenant=maintenant, mode=args.mode, donnees=donnees,
                   reprise=Path(args.reprise) if args.reprise else None, journal=journal)
    if args.seulement_reglement:
        # Cycle indépendant : aucune collecte ni placement de paris (cotes/pipeline/reglement.py).
        reglement.regler_seul(ctx, args.reglement)
        if not args.sans_site:          # serveur en direct : le site est construit par site.yml
            construire_site(donnees, Path(args.site))
        print(json.dumps({"mode": "reglement", "resultats": journal.get("resultats"), "theodds": journal.get("theodds"),
                          "etapes": journal.get("etapes", {})}, ensure_ascii=False))
        return 0

    # 1-2. collecte : références, bookmakers français, bourses, dérive (cotes/pipeline/collecte.py)
    collecter(ctx)
    # 3. analyse : association, contrôle des intitulés, comparaison, props, mouvement (cotes/pipeline/analyse.py)
    analyser(ctx)
    # 4. prise : placement, décisions figées, Qwen, suivi des prix et de la clôture (cotes/pipeline/prise.py)
    prendre(ctx)
    # La collecte reprend le règlement si le workflow horaire a été retardé.
    reglement.regler(ctx, args.reglement)
    # 5. sauvegarde (cotes/pipeline/sauvegarde.py)
    sauvegarder(ctx)

    # 6. site
    if not args.sans_site:
        construire_site(donnees, Path(args.site))
    print(json.dumps({k: journal[k] for k in ("mode", "cotes", "matchs_francais", "opportunites", "nouveaux_paris",
                                               "controle", "etapes")}, ensure_ascii=False, indent=1))
    return 0


def main(argv: list[str] | None = None, construire_site: Callable | None = None) -> int:
    return executer(arguments(argv), construire_site)
