"""Mouvement de la cote juste de Pinnacle (« dropping odds ») avant la prise d'un pari.

Quand la cote de Pinnacle baisse sur une issue, la probabilité juste monte : le marché sharp « sait » quelque chose
et les bookmakers français ne l'ont peut-être pas encore suivi. Pour tester si ce signal annonce de meilleurs paris,
on garde pour chaque cote Pinnacle associée à un match français une **ancre** (probabilité juste, heure de lecture).
Chaque cycle compare la probabilité actuelle à l'ancre quand celle-ci a au moins ``AGE_MIN_S`` secondes ; l'ancre
est renouvelée après ``AGE_MAX_S``. Le mouvement (+3 % = probabilité juste 3 % plus haute que l'ancre) et la
durée mesurée sont inscrits dans l'opportunité, puis dans le pari.

Garde-fou (1er novembre 2026) : une cote Pinnacle **figée** ne sert plus de référence. Si sa probabilité juste est
strictement identique à l'ancre lue au moins ``AGE_MIN_S`` secondes plus tôt (mouvement 0, arrondi à 4 décimales),
le prix servi est probablement une copie de cache restée en place pendant que le vrai marché bougeait. Du 25/10 au
01/11, 53 paris adossés à une cote ainsi figée (jusqu'à 62 min) avaient une CLV de −8 % (24 % positives), contre
environ 0 % ou mieux quand la cote bougeait. L'opportunité de référence Pinnacle, ou Consensus dont Pinnacle est une
composante, est alors marquée ``suspect = "cote Pinnacle figée"`` et ``pariable = False`` : ni pari, ni alerte.
Les autres références (Polymarket, Matchbook…) ne sont pas touchées. Les paris déjà pris ne changent pas.

Les ancres vivent dans le cache GitHub Actions, à côté de la reprise (même dossier), jamais dans la branche
« donnees ». Absent ou illisible : aucun mouvement, le cycle continue. Ne lève jamais.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path

from .marches import cle

AGE_MIN_S = 600          # en dessous, le mouvement est du bruit d'un cycle à l'autre
AGE_MAX_S = 3600         # l'ancre est renouvelée après une heure : le mouvement porte sur 10 à 60 minutes
FIGEE = "cote Pinnacle figée"


def _depend_de_pinnacle(o: dict) -> bool:
    """Référence Pinnacle, ou Consensus dont Pinnacle est une composante."""
    if o.get("reference") == "Pinnacle":
        return True
    return o.get("reference") == "Consensus" and "Pinnacle" in str(o.get("sources") or "").split("+")


def est_figee(o: dict) -> bool:
    """Cote Pinnacle de référence strictement inchangée depuis au moins AGE_MIN_S secondes."""
    m, s = o.get("mouvement_pinnacle"), o.get("mouvement_s")
    return (_depend_de_pinnacle(o) and isinstance(m, (int, float)) and not isinstance(m, bool) and m == 0
            and isinstance(s, (int, float)) and not isinstance(s, bool) and s >= AGE_MIN_S)


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
    """Ajoute `mouvement_pinnacle` et `mouvement_s` aux opportunités, écarte celles dont la cote Pinnacle de référence
    est figée (garde-fou, voir en tête du module) ; résumé pour le journal. Ne lève jamais."""
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
        n = figees = 0
        for o in opportunites:
            m = mouvements.get(_id(o.get("match_id"), cle(o)))
            if m:
                o["mouvement_pinnacle"], o["mouvement_s"] = m
                n += 1
                if est_figee(o):
                    if not o.get("suspect"):
                        o["suspect"] = FIGEE
                    o["pariable"] = False
                    figees += 1
        try:
            ecrire(chemin, ancres)
        except Exception as e:  # noqa: BLE001  une écriture ratée ne retire pas les mouvements du cycle
            return {"actif": True, "ancres": len(ancres), "annotees": n, "figees": figees,
                    "ecriture": type(e).__name__}
        return {"actif": True, "ancres": len(ancres), "mesures": len(mouvements), "annotees": n, "figees": figees}
    except Exception as e:  # noqa: BLE001
        return {"actif": True, "erreur": type(e).__name__}
