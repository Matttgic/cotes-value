"""Flux public d'alertes : mêmes prises et mêmes prix que les badges du site.

Ce module ne change aucune sélection et ne place aucun pari. Les abonnements
et clés privées ne transitent jamais par ce flux ni par la branche donnees.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .convergence import STRATEGIES, cle_selection, paris_convergence
from .laboratoire import heure
from .strategies_prudentes import VARIANTES

API = "https://tapotyftgyacbnjmeovn.supabase.co/functions/v1/cv-notifications"
AGE_PRIX_MAX_MINUTES = 5
NOMS = {**{cle: nom for cle, _, nom, _, _ in STRATEGIES},
        **{v["cle"]: v["court"] for v in VARIANTES}, "convergence": "Convergence ≥ 2"}


def empreinte_prix(p: dict) -> str:
    return hashlib.sha256(json.dumps((*cle_selection(p), p.get("cote")),
        ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def flux(actuelles: list[dict], paris: list[dict], retenus: dict[str, set[int]],
         maintenant: datetime | None = None) -> dict:
    maintenant = maintenant or datetime.now(timezone.utc)
    valides = {**retenus, "convergence": paris_convergence(paris, retenus)}
    observations = {}
    for p in paris:
        t = heure(p.get("detecte"))
        if not t:
            continue
        key = (*cle_selection(p), p.get("cote"))
        for cle, ids in valides.items():
            if id(p) in ids:
                dates = observations.setdefault(key, {})
                dates[cle] = min(dates.get(cle, t), t)
    alertes = {}
    for o in actuelles:
        debut = heure(o.get("debut"))
        recue = heure(o.get("collecte_recue") or o.get("detecte"))
        if (o.get("suspect") or o.get("pariable") is False or not debut
                or debut <= maintenant + timedelta(minutes=1) or not recue
                or not timedelta(0) <= maintenant-recue <= timedelta(minutes=AGE_PRIX_MAX_MINUTES)):
            continue
        key = (*cle_selection(o), o.get("cote"))
        dates = observations.get(key, {})
        if not dates or not any(maintenant-timedelta(minutes=15) <= t <= maintenant for t in dates.values()):
            continue
        empreinte = empreinte_prix(o)
        alertes[empreinte] = {
            "id": empreinte, "strategies": sorted(dates), "labels": [NOMS[c] for c in sorted(dates)],
            "validations": {c: t.isoformat() for c, t in dates.items()},
            "detecte": max(dates.values()).isoformat(), "debut": debut.isoformat(),
            "match": f'{o.get("domicile", "")} – {o.get("exterieur", "")}',
            # Le serveur actuel affiche le texte du pari tel quel : l'heure est
            # visible aussi sans redéployer le service Web Push.
            "pari": (o.get("pari", "")[:180]+"\nPrix relevé "+recue.astimezone(ZoneInfo("Europe/Paris")).strftime("%d/%m %H:%M:%S")),
            "collecte_le": recue.isoformat(), "age_prix_secondes": round((maintenant-recue).total_seconds()),
            "bookmaker": o.get("bookmaker", ""), "cote": o.get("cote"),
        }
    return {"generated_at": maintenant.isoformat(timespec="seconds"),
            "alertes": sorted(alertes.values(), key=lambda a: a["detecte"], reverse=True)[:100]}
