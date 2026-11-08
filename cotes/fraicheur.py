"""Trois horloges, jamais confondues.

- ``maj_source`` : dernier mouvement de prix annoncé par le bookmaker, quand il le dit.
  Une cote inchangée peut donc être ancienne sans être périmée. Ce n'est pas un filtre de prise.
- ``collecte`` / ``collecte_recue`` : réception de notre lecture.
- L'heure du rapport (fin de cycle, page Santé) est celle de l'appelant. Elle n'est pas réécrite ici.

Une heure source absente, naïve, illisible ou postérieure à la réception donne un âge inconnu
(``None``), jamais 0, et n'est pas remplacée par l'heure de réception.
``age_epoch_secondes`` et ``age_depuis_millisecondes`` ne servent que là où l'unité est déjà
établie (``last_call`` PinBook en secondes Unix, ``X-Data-Age-Ms`` en millisecondes).
"""
from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite

from .temps import instant_utc

_CLE_OBSERVATION = ("match_id", "cle_marche", "marche", "periode", "ligne", "issue", "joueur")


def horodatage_source(valeur) -> str | None:
    """ISO 8601 avec fuseau, ramené en UTC à la seconde. Nombre, texte naïf ou vide : ``None``."""
    if not isinstance(valeur, str):
        return None
    texte = valeur.strip()
    if not texte:
        return None
    t = instant_utc(texte)
    if t is None:
        return None
    return t.replace(microsecond=0).isoformat(timespec="seconds")


def _horloge(valeur) -> datetime | None:
    if isinstance(valeur, datetime):
        if valeur.tzinfo is None or valeur.utcoffset() is None:
            return None
        return valeur.astimezone(timezone.utc).replace(microsecond=0)
    iso = horodatage_source(valeur)
    return instant_utc(iso) if iso else None


def age_mouvement_s(source, reception) -> int | None:
    """Secondes entre le dernier mouvement annoncé et la réception.

    0 seulement si les deux heures tombent dans la même seconde. Source future : ``None``.
    """
    s, r = _horloge(source), _horloge(reception)
    if s is None or r is None:
        return None
    delta = int((r - s).total_seconds())
    if delta < 0:
        return None
    return delta


def age_epoch_secondes(valeur, maintenant: datetime) -> int | None:
    """Âge d'un horodatage Unix en secondes, mesuré sur ``maintenant`` (pas l'horloge murale).

    Futur, NaN, booléen, unité non numérique ou ``maintenant`` naïf : ``None``, jamais 0.
    Une valeur en millisecondes tombe dans le futur et reste inconnue : on ne devine pas l'unité.
    """
    if isinstance(valeur, bool) or not isinstance(maintenant, datetime):
        return None
    if maintenant.tzinfo is None or maintenant.utcoffset() is None:
        return None
    if isinstance(valeur, str):
        texte = valeur.strip()
        if not texte:
            return None
        try:
            valeur = float(texte)
        except ValueError:
            return None
    if isinstance(valeur, bool) or not isinstance(valeur, (int, float)):
        return None
    if not isfinite(float(valeur)):
        return None
    delta = maintenant.timestamp() - float(valeur)
    if delta < 0:
        return None
    return int(delta)


def age_depuis_millisecondes(valeur) -> int | None:
    """Millisecondes -> secondes entières. Négatif ou illisible : ``None``. 0 ms reste 0 s."""
    if isinstance(valeur, bool) or valeur is None:
        return None
    if isinstance(valeur, str) and not valeur.strip():
        return None
    try:
        ms = int(str(valeur).strip())
    except (TypeError, ValueError):
        return None
    if ms < 0:
        return None
    return ms // 1000


def resume_lignes(lignes) -> dict:
    """Compte les mouvements datés. N'invente aucun âge quand l'heure source manque."""
    connus: list[int] = []
    inconnue = invalide = 0
    receptions: list[datetime] = []
    n = 0
    for ligne in lignes or []:
        if not isinstance(ligne, dict):
            continue
        n += 1
        rec = ligne.get("collecte_recue") or ligne.get("collecte")
        instant_rec = _horloge(rec)
        if instant_rec is not None:
            receptions.append(instant_rec)
        brut = ligne.get("maj_source")
        if brut is None:
            brut = ligne.get("maj_bookmaker")
        src = horodatage_source(brut)
        if src is None:
            inconnue += 1
            continue
        age = age_mouvement_s(src, instant_rec)
        if age is None:
            invalide += 1
            continue
        connus.append(age)
    return {
        "lignes": n,
        "source_connue": len(connus),
        "source_inconnue": inconnue,
        "source_invalide": invalide,
        "mouvement_min_s": min(connus) if connus else None,
        "mouvement_max_s": max(connus) if connus else None,
        "reception": min(receptions).isoformat(timespec="seconds") if receptions else None,
    }


def derniere_observation(lignes) -> list:
    """Une sélection, une observation dans la même lecture.

    La ligne lue ensuite remplace la précédente : une relance identique ne double pas le marché,
    un prix différent plus tard est l'observation retenue. Une lecture ultérieure (autre appel)
    n'est pas concernée : elle repart de sa propre liste.
    """
    ordre: list[tuple] = []
    par: dict[tuple, dict] = {}
    for ligne in lignes or []:
        if not isinstance(ligne, dict) or not ligne.get("match_id"):
            continue
        cle = tuple(ligne.get(k) for k in _CLE_OBSERVATION)
        if cle not in par:
            ordre.append(cle)
        par[cle] = ligne
    return [par[c] for c in ordre]
