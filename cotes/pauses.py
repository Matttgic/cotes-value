"""Mise en pause automatique des stratégies qui perdent clairement contre la cote de clôture.

Une stratégie en pause ne sélectionne plus aucun pari détecté après le début de sa pause : ni décision figée, ni
alerte, ni nouvelle ligne dans son suivi. Son historique reste affiché tel quel.

Critères (``a_mettre_en_pause``), sur son suivi depuis le lancement (mise fixe) :
- au moins ``MIN_REGLES`` paris réglés, dont ``MIN_CLV`` avec une CLV mesurée ;
- CLV moyenne par pari clairement négative : même la borne haute à 95 % (unilatérale) est sous zéro ;
- CLV moyenne par match (``clv_ajustee`` de la note) négative aussi.

Jamais en pause : les bases du Bilan, les 7 stratégies de base et la convergence (leurs votes alimentent d'autres
stratégies figées) et les membres d'une fusion active (ses membres sont figés).

État : ``pauses.json`` dans « donnees », écrit par la construction du site (``mettre_a_jour``) et lu au début de
chaque construction, du cycle et de l'envoi des alertes (``charger``). Une pause décidée à une construction agit à
partir de la suivante. Pour relancer une stratégie, retirer sa ligne de ``pauses.json``.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from math import sqrt
from pathlib import Path

FICHIER = "pauses.json"
MIN_REGLES = 200
MIN_CLV = 100
Z95 = 1.645
_ACTIVES: dict[str, datetime] = {}


def _date(valeur) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(valeur).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else None


def _lire(donnees) -> dict:
    try:
        etat = json.loads((Path(donnees) / FICHIER).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return etat if isinstance(etat, dict) and isinstance(etat.get("pauses"), dict) else {}


def charger(source) -> dict[str, datetime]:
    """Active les pauses de ``pauses.json`` (``source`` : dossier « donnees » ou état déjà lu). Rend {clé: début}."""
    etat = source if isinstance(source, dict) else _lire(source)
    _ACTIVES.clear()
    for cle, p in (etat.get("pauses") or {}).items():
        debut = _date((p or {}).get("depuis"))
        if debut is not None:
            _ACTIVES[cle] = debut
    return dict(_ACTIVES)


def filtrer(paris: list[dict], ids: set[int], cle: str) -> set[int]:
    """``ids`` sans les paris détectés depuis la pause de ``cle`` (inchangés si ``cle`` n'est pas en pause)."""
    limite = _ACTIVES.get(cle)
    if limite is None or not ids:
        return ids
    garde = set()
    for p in paris:
        if id(p) in ids:
            t = _date(p.get("detecte"))
            if t is None or t < limite:
                garde.add(id(p))
    return garde


def stats_clv(valeurs: list[float]) -> tuple[float | None, float | None]:
    """(moyenne, borne haute unilatérale à 95 %) en %, ou (None, None) sous deux valeurs."""
    n = len(valeurs)
    if n < 2:
        return None, None
    m = sum(valeurs) / n
    sd = sqrt(sum((v - m) ** 2 for v in valeurs) / (n - 1))
    return round(100 * m, 2), round(100 * (m + Z95 * sd / sqrt(n)), 2)


def a_mettre_en_pause(stats: dict | None, clvs: list[float]) -> dict | None:
    """Mesures qui justifient la pause, ou None si la stratégie continue."""
    stats = stats or {}
    regles = stats.get("regles") or 0
    par_match = ((stats.get("note") or {}).get("mesures") or {}).get("clv_ajustee")
    if regles < MIN_REGLES or len(clvs) < MIN_CLV or par_match is None or par_match >= 0:
        return None
    moyenne, haute = stats_clv(clvs)
    if haute is None or haute >= 0:
        return None
    return {"regles": regles, "clv_n": len(clvs), "clv": moyenne, "clv_haute": haute, "clv_match": par_match}


def mettre_a_jour(donnees, lignes: list[dict], cle_de: dict[str, str], clvs_de, exemptes: set[str],
                  maintenant: datetime) -> dict:
    """Ajoute les nouvelles pauses à ``pauses.json`` (jamais de reprise automatique) et rend l'état publié.

    ``lignes`` : {id, stats} du classement ; ``cle_de`` : id de ligne → clé de stratégie ; ``clvs_de(id)`` : CLV
    des paris réglés de la ligne ; ``exemptes`` : ids jamais mis en pause. Une erreur d'écriture n'est pas propagée."""
    chemin = Path(donnees) / FICHIER
    etat = _lire(donnees) or {"pauses": {}}
    pauses = dict(etat["pauses"])
    instant = maintenant.isoformat(timespec="seconds")
    for l in lignes:
        cle = cle_de.get(l["id"])
        if not cle or cle in pauses or l["id"] in exemptes:
            continue
        mesures = a_mettre_en_pause(l.get("stats"), clvs_de(l["id"]))
        if mesures:
            pauses[cle] = {"id": l["id"], "depuis": instant, **mesures}
    if pauses != etat["pauses"]:
        etat = {**etat, "pauses": pauses}
        try:
            tmp = chemin.with_name(chemin.name + ".tmp")
            tmp.write_text(json.dumps(etat, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            os.replace(tmp, chemin)
        except OSError:
            pass
    return {"liste": {p["id"]: {k: v for k, v in p.items() if k != "id"} | {"cle": cle}
                      for cle, p in pauses.items() if isinstance(p, dict) and p.get("id")},
            "criteres": {"min_regles": MIN_REGLES, "min_clv": MIN_CLV}}
