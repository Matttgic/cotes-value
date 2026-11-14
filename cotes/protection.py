"""Chaque stratégie isolée pendant la construction du site.

Le site recalcule toutes les stratégies. Sans protection, l'erreur d'une seule arrêtait toute la construction :
plus de mise à jour du site. Dans ``proteger_strategies()`` (site_web.construire), une stratégie qui lève est
notée en échec (annotation GitHub et ligne « Erreurs non bloquantes » de la page Santé) et rend une sélection
vide ; les autres continuent. Les décisions déjà figées restent affichées (cotes/decisions.py).

Hors de ce contexte (cycle de collecte, notifications, tests), l'erreur remonte comme avant : le cycle ne doit
jamais figer un faux « refus » parce qu'une stratégie a planté. Il échoue et le cycle suivant recommence.

Pannes qui durent : ``pannes_strategies.json`` (dans « donnees ») compte les échecs consécutifs de chaque stratégie ;
une construction réussie remet son compteur à zéro. Au ``SEUIL_PANNES``-ième échec de suite (environ 30 min, une
construction toutes les 5 min), un seul message Pushover part (cotes/echecs.py) ; un nouveau message ne part
qu'après un retour à la normale. Ne lève jamais : la construction du site ne dépend pas de cette alerte.
"""
from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from urllib.request import urlopen

from . import echecs

FICHIER_PANNES = "pannes_strategies.json"
SEUIL_PANNES = 6

_ECHECS: dict[str, dict] | None = None
# Temps propre de chaque stratégie (secondes, sans celui des stratégies qu'elle appelle), page Santé.
_DUREES: dict[str, float] = {}
_PILE: list[float] = []


@contextmanager
def proteger_strategies():
    """Active la protection ; rend le dictionnaire des échecs {nom: {"quand", "etape", "message"}}."""
    global _ECHECS
    precedent, _ECHECS = _ECHECS, {}
    _DUREES.clear()
    try:
        yield _ECHECS
    finally:
        _ECHECS = precedent


def calculer(nom: str, calcul, vide=set):
    """``calcul()`` ; dans le contexte protégé, une erreur est notée une fois par stratégie et rend ``vide()``."""
    registre = _ECHECS
    if registre is None:
        return calcul()
    _PILE.append(0.0)
    debut = perf_counter()
    try:
        return calcul()
    except Exception as e:  # noqa: BLE001 - une stratégie en erreur ne doit pas arrêter le site
        if nom not in registre:
            message = echecs.message_court(e)
            registre[nom] = {"quand": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                             "etape": f"stratégie {nom}", "message": message}
            echecs.annoter(f"stratégie {nom}", message)
        return vide()
    finally:
        total, enfants = perf_counter() - debut, _PILE.pop()
        if _PILE:
            _PILE[-1] += total
        _DUREES[nom] = _DUREES.get(nom, 0.0) + total - enfants


def durees(maximum: int = 15) -> dict:
    """Temps de calcul de la construction en cours : total et stratégies les plus lentes, en secondes."""
    tri = sorted(_DUREES.items(), key=lambda x: -x[1])
    return {"total": round(sum(_DUREES.values()), 1), "strategies": len(_DUREES),
            "plus_lentes": [{"nom": n, "secondes": round(t, 2)} for n, t in tri[:maximum]]}


# --------------------------------------------------------------------------- pannes qui durent

def suivre_pannes(etat: dict, echecs_du_jour: dict[str, dict], maintenant: datetime) -> tuple[dict, list[str]]:
    """État suivant et noms des stratégies à signaler maintenant. Pur."""
    instant = maintenant.isoformat(timespec="seconds")
    suivant, a_signaler = {}, []
    for nom, e in echecs_du_jour.items():
        avant = (etat or {}).get(nom) or {}
        x = {"consecutifs": int(avant.get("consecutifs") or 0) + 1, "depuis": avant.get("depuis") or instant,
             "message": (e or {}).get("message", ""), "alerte_le": avant.get("alerte_le")}
        if x["consecutifs"] >= SEUIL_PANNES and not x["alerte_le"]:
            x["alerte_le"] = instant
            a_signaler.append(nom)
        suivant[nom] = x
    return suivant, a_signaler


def alerter_pannes(noms: list[str], etat: dict, env=None, ouvrir=urlopen) -> bool:
    if not noms:
        return False
    lignes = [f"{n} : {etat[n]['consecutifs']} échecs de suite depuis {etat[n]['depuis'][:16].replace('T', ' ')} UTC"
              f" — {etat[n]['message']}" for n in noms]
    return echecs.alerter_pushover(f"Stratégie en panne ({len(noms)})", "\n".join(lignes), env, ouvrir)


def mettre_a_jour_pannes(donnees, echecs_du_jour: dict[str, dict], maintenant: datetime, env=None,
                         ouvrir=urlopen) -> dict:
    """Lit, met à jour et réécrit ``pannes_strategies.json`` ; envoie l'alerte si besoin. Rend l'état publié."""
    try:
        chemin = Path(donnees) / FICHIER_PANNES
        try:
            etat = json.loads(chemin.read_text(encoding="utf-8"))
            etat = etat if isinstance(etat, dict) else {}
        except (OSError, ValueError):
            etat = {}
        suivant, a_signaler = suivre_pannes(etat, echecs_du_jour or {}, maintenant)
        if a_signaler and not alerter_pannes(a_signaler, suivant, env, ouvrir):
            for n in a_signaler:            # échec d'envoi : nouvel essai à la prochaine construction
                suivant[n]["alerte_le"] = None
        if suivant != etat:
            tmp = chemin.with_name(chemin.name + ".tmp")
            tmp.write_text(json.dumps(suivant, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            os.replace(tmp, chemin)
        return {"strategies": suivant, "seuil": SEUIL_PANNES}
    except Exception:  # noqa: BLE001
        return {"strategies": {}, "seuil": SEUIL_PANNES}
