"""Pause d'une source de cotes qui refuse l'accès (HTTP 403 ou 429) : on respecte le refus, sans insister.

Repris d'Autonome (``autonome/cli.py`` : ``_blocked`` / ``_maybe_block``, ``backoff.jsonl``). Constat du 3 au
9/11/2026 : Unibet « accueil HTTP 403 » pendant 1 703 cycles sur ~2 180 (628 d'affilée), relu 12 fois par heure ;
NetBet a déjà fini par bloquer Autonome à force d'insister.

Règle : une lecture refusée (étape en échec avec un 403/429, ou dont toutes les erreurs sont des 403/429) met la
source en pause ``PAUSE_INITIALE`` (30 min), doublée à chaque récidive jusqu'à ``PAUSE_MAX`` (6 h). Pendant la
pause, aucune requête : l'étape est notée ``pause`` (état connu, pas un incident). Une lecture réussie efface la
récidive. Pinnacle et Polymarket (références principales, refus partiels par sport et reprise déjà en place) ne
sont pas concernés.

État : ``pauses_sources.json.gz`` dans la mémoire de travail (``cotes/memoire.py``, cache Actions), hors de la
branche « donnees ». Absent ou illisible : aucune pause. Ne lève jamais.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from . import memoire

NOM = "pauses_sources"
PAUSE_INITIALE = timedelta(minutes=30)
PAUSE_MAX = timedelta(hours=6)
SOURCES = ("pmu_direct", "winamax_direct", "betclic_direct", "unibet_direct", "olybet", "netbet", "matchbook")


def _instant(valeur) -> datetime | None:
    try:
        t = datetime.fromisoformat(str(valeur))
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else None


def charger(donnees) -> dict:
    try:
        doc = memoire.lire(donnees, NOM, {}, ancien_aussi=False)
    except Exception:  # noqa: BLE001 - une mémoire illisible ne bloque jamais la collecte
        return {}
    return {k: v for k, v in doc.items() if k in SOURCES and isinstance(v, dict)} if isinstance(doc, dict) else {}


def sauver(donnees, etat: dict) -> None:
    try:
        memoire.ecrire(donnees, NOM, etat, retirer_ancien=False)
    except Exception:  # noqa: BLE001
        pass


def en_pause(etat: dict | None, source: str, maintenant: datetime) -> str | None:
    """Fin de la pause (ISO) si la source est en pause, sinon None."""
    v = (etat or {}).get(source)
    fin = _instant(v.get("jusqu_a")) if isinstance(v, dict) else None
    return v["jusqu_a"] if fin is not None and fin > maintenant else None


def refus(etape: dict | None) -> str | None:
    """Premier motif 403/429 d'une lecture refusée, sinon None (un 403 isolé dans une lecture réussie ne compte pas)."""
    if not isinstance(etape, dict) or etape.get("pause") or etape.get("desactive"):
        return None
    erreurs = [str(e) for e in (etape.get("erreurs") or [])]
    refusees = [e for e in erreurs if "HTTP 403" in e or "HTTP 429" in e]
    if refusees and (etape.get("ok") is False or len(refusees) == len(erreurs)):
        return refusees[0][:120]
    return None


def mettre_a_jour(etat: dict, etapes: dict, maintenant: datetime) -> dict:
    """Après la collecte : nouvelle pause (doublée en cas de récidive) ou récidive effacée. Renvoie ``etat``."""
    for source in SOURCES:
        v = (etapes or {}).get(source)
        if not isinstance(v, dict) or v.get("pause") or v.get("desactive"):
            continue
        motif = refus(v)
        if motif:
            n = int((etat.get(source) or {}).get("recidives") or 0) + 1
            duree = min(PAUSE_INITIALE * 2 ** (n - 1), PAUSE_MAX)
            etat[source] = {"depuis": maintenant.isoformat(timespec="seconds"),
                            "jusqu_a": (maintenant + duree).isoformat(timespec="seconds"),
                            "minutes": int(duree.total_seconds() // 60), "recidives": n, "motif": motif}
        elif v.get("ok") and not v.get("degrade"):
            etat.pop(source, None)
    return etat


def etape_en_pause(etat: dict, source: str) -> dict:
    """Étape du journal d'une source en pause : ``ok`` (pas une panne), ``pause`` et sa fin, le motif du refus."""
    v = etat.get(source) or {}
    return {"secondes": 0.0, "ok": True, "pause": True, "pause_jusqu_a": v.get("jusqu_a"),
            "pause_motif": v.get("motif"), "recidives": v.get("recidives")}
