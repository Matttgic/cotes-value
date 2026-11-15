"""Alertes Chrome (déplacé de scripts/envoyer_notifications.py, E5.1) : lecture des paris et flux des alertes,
même sélection que le site. L'envoi au service (`transmettre`) reste dans le script."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


def lire_paris(donnees: Path) -> list[dict]:
    """``paris.json`` tel qu'écrit par le cycle. Lu une seule fois par passage (8 Mo) : la sélection, Pushover et
    le webhook ne font que lire ces objets, aucun ne les modifie."""
    return json.loads((donnees / "paris.json").read_text())


def preparer(donnees: Path, maintenant: datetime | None = None, retenues: list | None = None,
             paris_bruts: list[dict] | None = None) -> dict:
    """Même sélection que le site, sans attendre sa génération ni les résultats."""
    from cotes import stockage
    from cotes.convergence import selections
    from cotes.strategies_prudentes import selections_prudentes
    from cotes.notifications import flux, selections_bases, selections_labo
    from cotes.strategie_recommandee import charger_fusions
    charger_fusions(donnees)          # fusions automatiques (Fusion 2, 3…) créées par les révisions
    from cotes import pauses
    pauses.charger(donnees)           # stratégies en pause (pauses.json) : plus de nouveaux paris
    paris = stockage.fusionner_paris(lire_paris(donnees) if paris_bruts is None else paris_bruts,
                                     stockage.lire_archives(donnees))
    actuelles = json.loads((donnees / "opportunites_actuelles.json").read_text())
    retenus = selections(paris)
    retenus.update(selections_prudentes(paris, bases=retenus))
    retenus.update(selections_labo(paris))
    retenus.update(selections_bases(paris))         # bases du Bilan : sans effet sur les votes de convergence
    return flux(actuelles, paris, retenus, maintenant, retenues=retenues)
