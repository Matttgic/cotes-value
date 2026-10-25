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


class Reduite:
    """Même interface qu'une échéance, finissant ``marge`` secondes plus tôt : le temps de traduire et rendre ce
    qui est déjà lu avant que le cycle ne coupe la source. Accepte toute échéance (``ok``, ``reste``)."""

    def __init__(self, base, marge: float):
        self.base = base
        self.marge = float(marge)

    def reste(self) -> float | None:
        reste = self.base.reste() if hasattr(self.base, "reste") else None
        return None if reste is None else max(0.0, reste - self.marge)

    def ok(self) -> bool:
        reste = self.reste()
        return self.base.ok() and (reste is None or reste > 0)

    def timeout(self, plafond: float) -> float:
        reste = self.reste()
        return float(plafond) if reste is None else max(1.0, min(float(plafond), reste))
