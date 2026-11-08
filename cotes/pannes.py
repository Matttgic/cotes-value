"""Pannes de stratégies qui durent : une alerte Pushover quand une stratégie échoue plusieurs constructions de suite.

Chaque construction du site note les stratégies en erreur (cotes/protection.py). ``pannes_strategies.json`` (dans
« donnees ») compte les échecs consécutifs de chacune ; une construction réussie remet son compteur à zéro. Au
``SEUIL``-ième échec de suite (environ 30 min, une construction toutes les 5 min), un seul message Pushover part
(``PUSHOVER_APP_TOKEN`` et ``PUSHOVER_USER_KEY``) ; un nouveau message ne part qu'après un retour à la normale.
Ne lève jamais : la construction du site ne dépend pas de cette alerte.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

FICHIER = "pannes_strategies.json"
SEUIL = 6
URL = "https://api.pushover.net/1/messages.json"


def suivre(etat: dict, echecs: dict[str, dict], maintenant: datetime) -> tuple[dict, list[str]]:
    """État suivant et noms des stratégies à signaler maintenant. Pur."""
    instant = maintenant.isoformat(timespec="seconds")
    suivant, a_signaler = {}, []
    for nom, e in echecs.items():
        avant = (etat or {}).get(nom) or {}
        x = {"consecutifs": int(avant.get("consecutifs") or 0) + 1, "depuis": avant.get("depuis") or instant,
             "message": (e or {}).get("message", ""), "alerte_le": avant.get("alerte_le")}
        if x["consecutifs"] >= SEUIL and not x["alerte_le"]:
            x["alerte_le"] = instant
            a_signaler.append(nom)
        suivant[nom] = x
    return suivant, a_signaler


def envoyer(noms: list[str], etat: dict, env=None, ouvrir=urlopen) -> bool:
    env = os.environ if env is None else env
    jeton, cle = env.get("PUSHOVER_APP_TOKEN", "").strip(), env.get("PUSHOVER_USER_KEY", "").strip()
    if not noms or not jeton or not cle:
        return False
    lignes = [f"{n} : {etat[n]['consecutifs']} échecs de suite depuis {etat[n]['depuis'][:16].replace('T', ' ')} UTC"
              f" — {etat[n]['message']}" for n in noms]
    corps = {"token": jeton, "user": cle, "title": f"Stratégie en panne ({len(noms)})",
             "message": ("\n".join(lignes))[:1000]}
    try:
        with ouvrir(Request(URL, data=urlencode(corps).encode(), method="POST",
                            headers={"User-Agent": "cotes-value"}), timeout=10) as r:
            return 200 <= getattr(r, "status", 200) < 300
    except Exception:  # noqa: BLE001
        return False


def mettre_a_jour(donnees, echecs: dict[str, dict], maintenant: datetime, env=None, ouvrir=urlopen) -> dict:
    """Lit, met à jour et réécrit ``pannes_strategies.json`` ; envoie l'alerte si besoin. Rend l'état publié."""
    try:
        chemin = Path(donnees) / FICHIER
        try:
            etat = json.loads(chemin.read_text(encoding="utf-8"))
            etat = etat if isinstance(etat, dict) else {}
        except (OSError, ValueError):
            etat = {}
        suivant, a_signaler = suivre(etat, echecs or {}, maintenant)
        if a_signaler and not envoyer(a_signaler, suivant, env, ouvrir):
            for n in a_signaler:            # échec d'envoi : nouvel essai à la prochaine construction
                suivant[n]["alerte_le"] = None
        if suivant != etat:
            tmp = chemin.with_name(chemin.name + ".tmp")
            tmp.write_text(json.dumps(suivant, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            os.replace(tmp, chemin)
        return {"strategies": suivant, "seuil": SEUIL}
    except Exception:  # noqa: BLE001
        return {"strategies": {}, "seuil": SEUIL}
