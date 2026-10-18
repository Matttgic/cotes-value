"""Échéance coopérative : une source s'arrête avant de bloquer le cycle."""
from __future__ import annotations

import time


class Echeance:
    """Instant monotone. ``secondes`` nul ou négatif est déjà dépassé."""

    def __init__(self, secondes: float | None):
        if secondes is None:
            self._fin = None
        elif secondes <= 0:
            self._fin = time.monotonic() - 1
        else:
            self._fin = time.monotonic() + float(secondes)

    def ok(self) -> bool:
        return self._fin is None or time.monotonic() < self._fin

    def reste(self) -> float | None:
        if self._fin is None:
            return None
        return max(0.0, self._fin - time.monotonic())

    def timeout(self, plafond: float) -> float:
        """Délai d'une requête, plafonné par le temps qui reste (au moins 1 s)."""
        reste = self.reste()
        if reste is None:
            return plafond
        return max(1.0, min(float(plafond), reste))
