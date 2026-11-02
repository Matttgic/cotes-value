"""Historique quotidien des notes /100 des stratégies (``notes_historique.json`` dans « donnees »).

La note est recalculée à chaque construction du site (chaque cycle, environ toutes les 5 minutes). Le dernier
calcul de chaque jour (heure de Paris) est gardé, sur ``GARDE_JOURS`` jours : la page Stratégies montre ainsi la
progression depuis la veille et sur 7 jours. Mise fixe, suivi prospectif seulement. Jamais bloquant.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

FICHIER = "notes_historique.json"
GARDE_JOURS = 60
PARIS = ZoneInfo("Europe/Paris")


def notes_du_laboratoire(laboratoire: dict) -> dict[str, int]:
    """{identifiant de ligne du classement: note} : règles du laboratoire, comparateurs et bases du Bilan."""
    out: dict[str, int] = {}

    def noter(cle, stats):
        note = (stats or {}).get("note") if isinstance(stats, dict) else None
        if isinstance(note, dict) and isinstance(note.get("total"), int):
            out[cle] = note["total"]
    for s in laboratoire.get("futur") or []:
        if isinstance(s, dict) and s.get("id"):
            noter(s["id"], s)
    for nom, s in (laboratoire.get("comparateurs_futur") or {}).items():
        noter(nom, s)
    for nom, s in (laboratoire.get("bases_futur") or {}).items():
        noter("base:" + nom, s)
    return out


def _lire(chemin: Path) -> dict:
    try:
        doc = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    jours = doc.get("jours") if isinstance(doc, dict) else None
    return {"jours": {j: n for j, n in jours.items() if isinstance(n, dict)}} if isinstance(jours, dict) else {}


def mettre_a_jour(donnees: Path, notes: dict[str, int], maintenant: datetime) -> dict:
    """Remplace les notes du jour (Paris), oublie celles de plus de ``GARDE_JOURS`` jours, écrit de façon atomique.
    Renvoie l'historique. Une erreur d'écriture n'est pas propagée (le site se construit quand même)."""
    chemin = Path(donnees) / FICHIER
    doc = _lire(chemin)
    jours = doc.get("jours", {})
    aujourd_hui = maintenant.astimezone(PARIS).date()
    if notes:
        jours[aujourd_hui.isoformat()] = dict(sorted(notes.items()))
    limite = (aujourd_hui - timedelta(days=GARDE_JOURS)).isoformat()
    doc = {"jours": {j: jours[j] for j in sorted(jours) if j > limite}}
    try:
        tmp = chemin.with_name(chemin.name + ".tmp")
        tmp.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        os.replace(tmp, chemin)
    except OSError:
        pass
    return doc


def reperes(doc: dict, maintenant: datetime) -> dict:
    """Notes de comparaison : le dernier jour avant aujourd'hui (« veille ») et le dernier jour au plus tard J−7."""
    jours = sorted((doc or {}).get("jours", {}))
    aujourd_hui = maintenant.astimezone(PARIS).date()
    avant = [j for j in jours if date.fromisoformat(j) < aujourd_hui]
    semaine = [j for j in jours if date.fromisoformat(j) <= aujourd_hui - timedelta(days=7)]
    out = {}
    if avant:
        out["veille"] = {"jour": avant[-1], "notes": doc["jours"][avant[-1]]}
    if semaine:
        out["semaine"] = {"jour": semaine[-1], "notes": doc["jours"][semaine[-1]]}
    return out
