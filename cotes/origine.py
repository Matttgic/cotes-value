"""Origine de la value à la prise (audit du 20/11/2026, priorité 8 ; étude : docs/duree-values.md, partie 3).

Dans l'heure qui précède la détection, la cote du bookmaker avait-elle bougé ?

- ``stable`` : pas de changement depuis une heure, la référence a bougé sans lui (CLV +3,2 % dans l'étude) ;
- ``hausse`` : le bookmaker venait de monter sa cote (CLV −1,2 % : il sait peut-être quelque chose) ;
- ``baisse`` : il venait de la baisser ;
- ``nouvelle`` : cote apparue dans l'heure, rien à comparer.

Même définition que ``etudes/etude_duree_values.py`` (``mesurer``), lue dans l'historique ``cotes/AAAA-MM-JJ.jsonl.gz``
que le cycle vient d'écrire. Informatif : aucune règle de prise n'en dépend. ``None`` si l'historique ne couvre pas
la cote (série absente, ou cote prise introuvable).
"""
from __future__ import annotations

import gzip
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .temps import instant_utc

ORIGINE_MIN = 60
TOLERANCE_MIN = 10            # la cote prise doit se retrouver dans l'historique au plus tard 10 min après la détection
LIBELLES = {"stable": "la référence a bougé, pas le bookmaker", "hausse": "le bookmaker vient de monter sa cote",
            "baisse": "le bookmaker vient de baisser sa cote", "nouvelle": "cote apparue dans l'heure"}
_MATCH = re.compile(r'"m":"([^"]*)"')


def cle(p: dict) -> tuple:
    """(bookmaker en minuscules, match, « marché|période|ligne|issue[|joueur] »), comme une ligne d'historique."""
    k = "|".join("" if x is None else str(x) for x in (p.get("marche"), p.get("periode"), p.get("ligne"), p.get("issue")))
    if p.get("joueur"):
        k += "|" + str(p["joueur"])
    return (str(p.get("bookmaker") or "").lower(), p.get("match_id"), k)


def lire_series(dossier: Path, paris: list[dict], maintenant: datetime) -> dict[tuple, list[tuple[datetime, float]]]:
    """Changements de cote des seules sélections de ``paris``, dans l'ordre du temps (jour UTC, et la veille pendant
    la première heure)."""
    import json
    cles = {cle(p) for p in paris}
    matchs = {c[1] for c in cles}
    series: dict[tuple, list] = {c: [] for c in cles}
    t = maintenant.astimezone(timezone.utc)
    jours = {t.strftime("%Y-%m-%d"), (t - timedelta(minutes=ORIGINE_MIN + TOLERANCE_MIN)).strftime("%Y-%m-%d")}
    for jour in sorted(jours):
        chemin = dossier / f"{jour}.jsonl.gz"
        if not chemin.exists():
            continue
        try:
            with gzip.open(chemin, "rt", encoding="utf-8") as f:
                for ligne in f:
                    m = _MATCH.search(ligne)
                    if not m or m.group(1) not in matchs or '"k"' not in ligne:
                        continue
                    try:
                        d = json.loads(ligne)
                    except ValueError:
                        continue
                    c, quand = d.get("c"), instant_utc(d.get("t"))
                    k = (str(d.get("b") or "").lower(), d.get("m"), d.get("k"))
                    if k in series and quand is not None and isinstance(c, (int, float)) and not isinstance(c, bool):
                        series[k].append((quand, float(c)))
        except (OSError, EOFError):
            continue                  # fichier du jour illisible : pas d'origine, le cycle continue
    for s in series.values():
        s.sort()
    return series


def origine(p: dict, serie: list[tuple[datetime, float]]) -> str | None:
    t0, cote = instant_utc(p.get("detecte")), p.get("cote")
    if t0 is None or not isinstance(cote, (int, float)):
        return None
    passes = [(t, c) for t, c in serie if t <= t0 + timedelta(minutes=TOLERANCE_MIN)]
    if not passes or abs(passes[-1][1] - cote) > 0.011:
        return None
    if t0 - passes[-1][0] > timedelta(minutes=ORIGINE_MIN):
        return "stable"
    if len(passes) == 1:
        return "nouvelle"
    return "hausse" if passes[-1][1] > passes[-2][1] else "baisse"


def annoter(donnees: Path | None, nouveaux: list[dict], maintenant: datetime) -> dict[str, int]:
    """Écrit ``origine`` dans chaque pari pris à ce cycle. Rend le compte par origine (journal)."""
    if not donnees or not nouveaux:
        return {}
    series = lire_series(donnees / "cotes", nouveaux, maintenant)
    compte: dict[str, int] = {}
    for p in nouveaux:
        o = origine(p, series.get(cle(p), []))
        p["origine"] = o
        compte[o or "inconnue"] = compte.get(o or "inconnue", 0) + 1
    return compte
