"""Marchés des bookmakers français qu'aucun traducteur ne reconnaît (couverture et changements de libellé).

Chaque lecteur (cotes/direct/*) appelle ``noter`` quand un marché n'est ni traduit ni exclu en amont (corners,
cartons, pair/impair sont en général écartés avant). Les chiffres sont remplacés par « # » : « Total 2.5 » et « Total 3.5 »
font un seul libellé. Le cycle fusionne le relevé dans ``donnees/marches_inconnus.json`` :
{bookmaker: {libellé: {"n": offres au dernier cycle où il est vu, "premier": ISO, "dernier": ISO}}}.
Un libellé apparu depuis moins de 24 h est « nouveau » sur la page Santé : souvent un libellé qui a changé.
Descriptif seulement : rien n'est traduit automatiquement.
"""
from __future__ import annotations

import re
import threading
from collections import Counter
from datetime import datetime, timedelta

_releve: Counter = Counter()
_verrou = threading.Lock()
GARDE = timedelta(days=7)        # libellé plus vu depuis : oublié
MAX_PAR_BOOK = 200
NOUVEAU = timedelta(hours=24)
_CHIFFRES = re.compile(r"[+-]?\d+(?:[.,]\d+)?")


def normaliser(libelle: str) -> str:
    return " ".join(_CHIFFRES.sub("#", str(libelle or "")).split())[:120]


def noter(bookmaker: str, libelle) -> None:
    lib = normaliser(libelle)
    if lib:
        with _verrou:
            _releve[(bookmaker, lib)] += 1


def vider() -> dict:
    """Relevé du cycle {bookmaker: {libellé: offres}}, remis à zéro."""
    with _verrou:
        copie = dict(_releve)
        _releve.clear()
    out: dict = {}
    for (book, lib), n in copie.items():
        out.setdefault(book, {})[lib] = n
    return out


def fusionner(ancien: dict, releve: dict, maintenant: datetime) -> dict:
    """Ajoute le relevé du cycle au fichier, oublie ce qui n'est plus vu depuis ``GARDE``."""
    iso = maintenant.isoformat(timespec="seconds")
    out: dict = {}
    for book in set(ancien or {}) | set(releve):
        libelles = {k: dict(v) for k, v in ((ancien or {}).get(book) or {}).items() if isinstance(v, dict)}
        for lib, n in (releve.get(book) or {}).items():
            v = libelles.setdefault(lib, {"premier": iso})
            v.update(n=n, dernier=iso)
        gardes = {}
        for lib, v in libelles.items():
            try:
                vu = datetime.fromisoformat(v["dernier"])
            except (KeyError, TypeError, ValueError):
                continue
            if maintenant - vu <= GARDE:
                gardes[lib] = v
        if gardes:
            plus_vus = sorted(gardes.items(), key=lambda kv: (kv[1]["dernier"], kv[1].get("n", 0)), reverse=True)
            out[book] = dict(plus_vus[:MAX_PAR_BOOK])
    return out


def resume(fichier: dict, maintenant: datetime, top: int = 8) -> dict:
    """Pour la page Santé : par bookmaker, libellés distincts, nouveaux (moins de 24 h) et les plus fréquents."""
    out = {}
    for book, libelles in sorted((fichier or {}).items()):
        def recent(v, champ):
            try:
                return maintenant - datetime.fromisoformat(v[champ]) <= NOUVEAU
            except (KeyError, TypeError, ValueError):
                return False
        actifs = {k: v for k, v in libelles.items() if recent(v, "dernier")}
        # Relevé commencé il y a moins de 24 h : tout serait « nouveau », rien ne l'est encore.
        debut = min((v.get("premier") or "" for v in libelles.values()), default="")
        rodage = recent({"premier": debut}, "premier")
        nouveaux = [] if rodage else sorted(k for k, v in actifs.items() if recent(v, "premier"))
        frequents = sorted(actifs.items(), key=lambda kv: -kv[1].get("n", 0))[:top]
        out[book] = {"distincts": len(actifs), "nouveaux": nouveaux[:top], "n_nouveaux": len(nouveaux),
                     "frequents": [[k, v.get("n", 0)] for k, v in frequents]}
    return out
