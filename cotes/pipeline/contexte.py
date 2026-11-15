"""Contexte d'un cycle (docs/architecture-cible.md, E3.1) : ce que les étapes se passent, sans variable globale."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class Contexte:
    maintenant: datetime
    mode: str                                  # "complet", "test" (ou "reglement" écrit dans le journal)
    donnees: Path
    reprise: Path | None = None                # dernier bon état des références (cache Actions)
    journal: dict = field(default_factory=dict)  # sortie du cycle : etat.json › dernier_cycle
