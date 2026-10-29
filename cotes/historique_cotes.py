"""Historique des cotes des bookmakers gardés en mémoire (PMU, Unibet, Betclic, NetBet), en ajout seul.

Avant le 30/10/2026, cet historique n'existait que dans les versions successives de ``horizon_direct.json``
de la branche « donnees » (53 Mo réécrits toutes les 5 minutes). Désormais, seules les lignes dont la cote a
changé depuis le cycle précédent (ou nouvelles) sont ajoutées à ``cotes/AAAA-MM-JJ.jsonl.gz`` (jour UTC,
gzip en mode « at » comme ``opportunites/``), avec des champs réduits :

    {"t": heure de lecture, "b": source, "m": match_id, "k": "marché|période|ligne|issue[|joueur]", "c": cote}

Un match vu pour la première fois reçoit en plus une ligne descriptive (sans ``c``) :

    {"t": ..., "b": ..., "m": match_id, "sport": ..., "ligue": ..., "dom": ..., "ext": ..., "debut": ...}

Aucune ligne n'est écrite si rien ne change. Au démarrage à froid (mémoire absente), toutes les cotes en
mémoire sont écrites une fois : c'est l'état de départ de l'historique.
"""
from __future__ import annotations

import gzip
import json
from datetime import datetime, timezone
from pathlib import Path


def _cle(l: dict) -> tuple:
    return (l.get("source"), l.get("match_id"), l.get("marche"), l.get("periode"), l.get("ligne"),
            l.get("issue"), l.get("joueur"))


def _texte(v) -> str:
    return "" if v is None else str(v)


def index(horizon: dict | None) -> dict[tuple, object]:
    """{clé de sélection: cote} de toutes les lignes en mémoire (tous bookmakers). Une même sélection présente deux
    fois (une cinquantaine sur 76 000 lignes le 29/10/2026) garde sa première ligne."""
    out: dict[tuple, object] = {}
    for bloc in (horizon or {}).values() if isinstance(horizon, dict) else []:
        for l in (bloc.get("lignes") or []) if isinstance(bloc, dict) else []:
            if isinstance(l, dict) and l.get("match_id") and l.get("cote") is not None:
                out.setdefault(_cle(l), l.get("cote"))      # doublon : la première ligne, comme changements()
    return out


def changements(avant: dict[tuple, object], horizon: dict | None) -> list[dict]:
    """Lignes réduites des cotes nouvelles ou changées, plus la description des matchs nouveaux."""
    matchs_avant = {k[1] for k in avant}
    decrits: set = set()
    out: list[dict] = []
    vues: set = set()
    for bloc in (horizon or {}).values() if isinstance(horizon, dict) else []:
        for l in (bloc.get("lignes") or []) if isinstance(bloc, dict) else []:
            if not isinstance(l, dict) or not l.get("match_id") or l.get("cote") is None:
                continue
            cle = _cle(l)
            if cle in vues:
                continue
            vues.add(cle)
            if cle in avant and avant[cle] == l.get("cote"):
                continue
            mid = l["match_id"]
            if mid not in matchs_avant and mid not in decrits:
                decrits.add(mid)
                out.append({"t": l.get("collecte"), "b": l.get("source"), "m": mid, "sport": l.get("sport"),
                            "ligue": l.get("ligue"), "dom": l.get("domicile"), "ext": l.get("exterieur"),
                            "debut": l.get("debut")})
            k = "|".join(_texte(x) for x in (l.get("marche"), l.get("periode"), l.get("ligne"), l.get("issue")))
            if l.get("joueur"):
                k += "|" + _texte(l["joueur"])
            out.append({"t": l.get("collecte"), "b": l.get("source"), "m": mid, "k": k, "c": l.get("cote")})
    return out


def ajouter(donnees: Path, avant: dict[tuple, object], horizon: dict | None, maintenant: datetime) -> int:
    """Ajoute les changements au fichier du jour (UTC). Rend le nombre de lignes écrites ; 0 = fichier intact."""
    lignes = changements(avant, horizon)
    if not lignes:
        return 0
    jour = Path(donnees) / "cotes" / f"{maintenant.astimezone(timezone.utc):%Y-%m-%d}.jsonl.gz"
    jour.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(jour, "at", encoding="utf-8") as f:
        f.write("".join(json.dumps(x, ensure_ascii=False, separators=(",", ":")) + "\n" for x in lignes))
    return len(lignes)
