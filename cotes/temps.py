"""Lecture des dates ISO 8601, mémorisée.

La construction du site relit les mêmes dates (détection, début, règlement) des millions de fois : environ
6,5 millions d'analyses pour quelques dizaines de milliers de chaînes distinctes. Une analyse par chaîne
suffit ; les ``datetime`` sont immuables, le résultat se partage sans risque.
"""
from __future__ import annotations

from datetime import datetime
from functools import lru_cache


@lru_cache(maxsize=1 << 18)
def _analyser(texte: str) -> datetime | None:
    try:
        return datetime.fromisoformat(texte.replace("Z", "+00:00"))
    except ValueError:
        return None


def date_iso(valeur) -> datetime | None:
    """``datetime.fromisoformat(str(valeur))`` (« Z » accepté), fuseau facultatif ; ``None`` si illisible."""
    return _analyser(valeur if type(valeur) is str else str(valeur))


def instant(valeur) -> datetime | None:
    """Date avec fuseau ; ``None`` si elle est absente, illisible ou sans fuseau."""
    t = _analyser(valeur if type(valeur) is str else str(valeur))
    return t if t is not None and t.tzinfo is not None else None
