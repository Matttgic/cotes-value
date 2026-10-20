"""Cotes déjà lues, gardées le temps qu'une tranche lointaine tourne.

Chaque cycle relit les matchs proches. Les autres ne sont relus qu'une tranche
à la fois. La comparaison reçoit l'union : l'horizon complet, pas seulement
la tranche du cycle.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

PRES_H = 6
AGE_MAX_H = 3


def _heure(valeur):
    try:
        t = datetime.fromisoformat(str(valeur).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if getattr(t, "tzinfo", None) is None:
        return None
    return t.astimezone(timezone.utc)


def fusionner(anciennes, nouvelles, maintenant: datetime, heures: float = 36,
              age_max_h: float = AGE_MAX_H) -> list[dict]:
    """Les matchs relus remplacent les anciens. Le reste reste dans l'horizon s'il est encore frais."""
    horizon = maintenant + timedelta(hours=heures)
    frais: dict = {}
    for ligne in nouvelles or []:
        if isinstance(ligne, dict) and ligne.get("match_id"):
            frais.setdefault(ligne["match_id"], []).append(ligne)
    gardes = []
    limite = timedelta(hours=age_max_h)
    for ligne in anciennes or []:
        if not isinstance(ligne, dict):
            continue
        mid = ligne.get("match_id")
        if not mid or mid in frais:
            continue
        debut = _heure(ligne.get("debut"))
        lu = _heure(ligne.get("collecte"))
        if not debut or not (maintenant < debut <= horizon) or lu is None or maintenant - lu > limite:
            continue
        gardes.append(ligne)
    for groupe in frais.values():
        gardes.extend(groupe)
    return gardes


def tranche(items: list, curseur: int, taille: int) -> tuple[list, int]:
    """Tranche tournante. Le curseur suivant retombe au début de la liste."""
    if not items or taille <= 0:
        return [], 0
    n = len(items)
    i = int(curseur or 0) % n
    pris = [items[(i + k) % n] for k in range(min(taille, n))]
    return pris, (i + len(pris)) % n


def fusionner_marches(anciennes, nouvelles, maintenant: datetime, heures: float = 36,
                      age_max_min: float = 15) -> list[dict]:
    """Comme ``fusionner``, au niveau du marché : une ligne ancienne n'est remplacée que si son marché
    (match, marché, période) a été relu. Les marchés lus par rotation restent entre deux lectures, au plus
    ``age_max_min`` minutes : au-delà, la comparaison ne les rapproche plus d'une référence fraîche."""
    horizon = maintenant + timedelta(hours=heures)
    relus = {(l.get("match_id"), l.get("marche"), l.get("periode"))
             for l in nouvelles or [] if isinstance(l, dict) and l.get("match_id")}
    limite = timedelta(minutes=age_max_min)
    gardes = []
    for ligne in anciennes or []:
        if not isinstance(ligne, dict) or not ligne.get("match_id"):
            continue
        if (ligne.get("match_id"), ligne.get("marche"), ligne.get("periode")) in relus:
            continue
        debut = _heure(ligne.get("debut"))
        lu = _heure(ligne.get("collecte"))
        if not debut or not (maintenant < debut <= horizon) or lu is None or maintenant - lu > limite:
            continue
        gardes.append(ligne)
    gardes.extend(l for l in nouvelles or [] if isinstance(l, dict) and l.get("match_id"))
    return gardes
