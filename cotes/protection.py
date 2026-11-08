"""Chaque stratégie isolée pendant la construction du site.

Le site recalcule toutes les stratégies. Sans protection, l'erreur d'une seule arrêtait toute la construction :
plus de mise à jour du site. Dans ``proteger_strategies()`` (site_web.construire), une stratégie qui lève est
notée en échec (annotation GitHub et ligne « Erreurs non bloquantes » de la page Santé) et rend une sélection
vide ; les autres continuent. Les décisions déjà figées restent affichées (cotes/decisions.py).

Hors de ce contexte (cycle de collecte, notifications, tests), l'erreur remonte comme avant : le cycle ne doit
jamais figer un faux « refus » parce qu'une stratégie a planté. Il échoue et le cycle suivant recommence.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from functools import wraps
from time import perf_counter

from . import echecs

_ECHECS: dict[str, dict] | None = None
# Temps propre de chaque stratégie (secondes, sans celui des stratégies qu'elle appelle), page Santé.
_DUREES: dict[str, float] = {}
_PILE: list[float] = []


@contextmanager
def proteger_strategies():
    """Active la protection ; rend le dictionnaire des échecs {nom: {"quand", "etape", "message"}}."""
    global _ECHECS
    precedent, _ECHECS = _ECHECS, {}
    _DUREES.clear()
    try:
        yield _ECHECS
    finally:
        _ECHECS = precedent


def calculer(nom: str, calcul, vide=set):
    """``calcul()`` ; dans le contexte protégé, une erreur est notée une fois par stratégie et rend ``vide()``."""
    registre = _ECHECS
    if registre is None:
        return calcul()
    _PILE.append(0.0)
    debut = perf_counter()
    try:
        return calcul()
    except Exception as e:  # noqa: BLE001 - une stratégie en erreur ne doit pas arrêter le site
        if nom not in registre:
            message = echecs.message_court(e)
            registre[nom] = {"quand": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                             "etape": f"stratégie {nom}", "message": message}
            echecs.annoter(f"stratégie {nom}", message)
        return vide()
    finally:
        total, enfants = perf_counter() - debut, _PILE.pop()
        if _PILE:
            _PILE[-1] += total
        _DUREES[nom] = _DUREES.get(nom, 0.0) + total - enfants


def durees(maximum: int = 15) -> dict:
    """Temps de calcul de la construction en cours : total et stratégies les plus lentes, en secondes."""
    tri = sorted(_DUREES.items(), key=lambda x: -x[1])
    return {"total": round(sum(_DUREES.values()), 1), "strategies": len(_DUREES),
            "plus_lentes": [{"nom": n, "secondes": round(t, 2)} for n, t in tri[:maximum]]}


def proteger(nom: str):
    """Décorateur : ``calculer`` autour d'un sélecteur ``f(paris, ...) -> set``."""
    def decorer(f):
        @wraps(f)
        def protege(*args, **kwargs):
            return calculer(nom, lambda: f(*args, **kwargs))
        return protege
    return decorer
