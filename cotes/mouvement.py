"""Mouvement de la cote juste de Pinnacle (« dropping odds ») avant la prise d'un pari.

Quand la cote de Pinnacle baisse sur une issue, la probabilité juste monte : le marché sharp « sait » quelque chose
et les bookmakers français ne l'ont peut-être pas encore suivi. Pour tester si ce signal annonce de meilleurs paris,
on garde pour chaque cote Pinnacle associée à un match français une **ancre** (probabilité juste, heure de lecture).
Chaque cycle compare la probabilité actuelle à l'ancre quand celle-ci a au moins ``AGE_MIN_S`` secondes ; l'ancre
est renouvelée après ``AGE_MAX_S``. Le mouvement (+3 % = probabilité juste 3 % plus haute que l'ancre) et la
durée mesurée sont inscrits dans l'opportunité, puis dans le pari : descriptif, jamais un critère de prise.

Les ancres vivent dans le cache GitHub Actions, à côté de la reprise (même dossier), jamais dans la branche
« donnees ». Absent ou illisible : aucun mouvement, le cycle continue. Ne lève jamais.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .marches import cle

AGE_MIN_S = 600          # en dessous, le mouvement est du bruit d'un cycle à l'autre
AGE_MAX_S = 3600         # l'ancre est renouvelée après une heure : le mouvement porte sur 10 à 60 minutes


def _id(match_id, k: tuple) -> str:
    return hashlib.blake2b(f"{match_id}|{k}".encode(), digest_size=6).hexdigest()


def lire(chemin: Path | None) -> dict:
    if chemin is None:
        return {}
    try:
        doc = json.loads(gzip.decompress(chemin.read_bytes()))
    except (OSError, EOFError, ValueError):
        return {}
    return doc if isinstance(doc, dict) else {}


def ecrire(chemin: Path, ancres: dict) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    tmp = chemin.with_name(chemin.name + ".tmp")
    tmp.write_bytes(gzip.compress(json.dumps(ancres, separators=(",", ":")).encode(), 6))
    os.replace(tmp, chemin)


def mettre_a_jour(ancres: dict, lignes: dict[str, float], maintenant: datetime) -> dict[str, tuple[float, int]]:
    """Met `ancres` à jour (modifié sur place) et renvoie {id: (mouvement, secondes mesurées)}.

    `lignes` = {id: probabilité juste de Pinnacle ce cycle}. Les ancres des lignes absentes sont oubliées."""
    t = int(maintenant.timestamp())
    mouvements: dict[str, tuple[float, int]] = {}
    for i in [i for i in ancres if i not in lignes]:
        del ancres[i]
    for i, p in lignes.items():
        a = ancres.get(i)
        if not (isinstance(a, list) and len(a) == 2 and a[0] > 0):
            ancres[i] = [round(p, 5), t]
            continue
        age = t - a[1]
        if age >= AGE_MIN_S:
            mouvements[i] = (round(p / a[0] - 1, 4), age)
        if age >= AGE_MAX_S or age < 0:
            ancres[i] = [round(p, 5), t]
    return mouvements


def annoter(opportunites: list[dict], index: dict, chemin: Path | None, maintenant: datetime) -> dict:
    """Ajoute `mouvement_pinnacle` et `mouvement_s` aux opportunités ; résumé pour le journal. Ne lève jamais."""
    if chemin is None:
        return {"actif": False}
    try:
        lignes: dict[str, float] = {}
        for mid_fr, par_cle in (index.get("Pinnacle") or {}).items():
            for k, l in par_cle.items():
                p = l.get("proba_juste")
                if isinstance(p, (int, float)) and 0 < p < 1:
                    lignes[_id(mid_fr, k)] = p
        ancres = lire(chemin)
        mouvements = mettre_a_jour(ancres, lignes, maintenant)
        n = 0
        for o in opportunites:
            m = mouvements.get(_id(o.get("match_id"), cle(o)))
            if m:
                o["mouvement_pinnacle"], o["mouvement_s"] = m
                n += 1
        try:
            ecrire(chemin, ancres)
        except Exception as e:  # noqa: BLE001  une écriture ratée ne retire pas les mouvements du cycle
            return {"actif": True, "ancres": len(ancres), "annotees": n, "ecriture": type(e).__name__}
        return {"actif": True, "ancres": len(ancres), "mesures": len(mouvements), "annotees": n}
    except Exception as e:  # noqa: BLE001
        return {"actif": True, "erreur": type(e).__name__}
