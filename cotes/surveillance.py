"""Alerte ntfy quand une source de cotes tombe pour de bon (et quand elle revient).

Une panne d'un seul cycle (coupure réseau) ou une lecture partielle « budget » (prévue, la suite est gardée en
cache) ne préviennent pas : il faut SEUIL_CYCLES cycles de suite. L'état est dans donnees/sante_alertes.json.
Ne lève jamais : la surveillance ne doit pas arrêter la collecte.
"""
from __future__ import annotations

import base64
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ETAT = "sante_alertes.json"
SEUIL_CYCLES = 2                    # cycles de suite avant d'alerter (toutes les ~5 min)
RAPPEL = timedelta(hours=3)         # une panne qui dure est rappelée
SURVEILLEES_DEGRADE = {"pinnacle", "winamax_direct", "betclic_direct", "unibet_direct", "pmu_direct", "olybet"}
BENINS = ("budget", "HTTP 429")      # lecture partielle prévue ou quota : pas une alerte


def noms(nom: str) -> str:
    return nom.replace("_direct", "").capitalize()


def problemes(etapes: dict) -> dict[str, tuple[str, str]]:
    """{étape: (niveau, détail)} pour les étapes de cotes en panne ou durablement dégradées."""
    out = {}
    for nom, v in etapes.items():
        if nom.startswith("resultats_") or v.get("desactive"):
            continue
        if not v.get("ok"):
            erreurs = v.get("erreurs") or [v.get("erreur") or "arrêtée"]
            out[nom] = ("panne", str(erreurs[0])[:80])
        elif v.get("degrade") and nom in SURVEILLEES_DEGRADE:
            erreurs = [str(e) for e in (v.get("erreurs") or [])]
            if erreurs and not all(any(b in e for b in BENINS) for e in erreurs):
                out[nom] = ("alerte", erreurs[0][:80])
    return out


def evaluer(etapes: dict, ancien: dict, maintenant: datetime) -> tuple[dict, list[tuple[str, str, str]]]:
    """(nouvel état, messages [(titre, corps, priorité)])."""
    courants, nouvel, messages = problemes(etapes), {}, []
    for nom, (niveau, detail) in courants.items():
        vu = ancien.get(nom, {})
        n = vu.get("cycles", 0) + 1
        envoye = vu.get("envoye")
        a_envoyer = n >= SEUIL_CYCLES and (
            not envoye or vu.get("niveau") != niveau or maintenant - datetime.fromisoformat(envoye) >= RAPPEL)
        if a_envoyer:
            envoye = maintenant.isoformat(timespec="seconds")
            mot = "en panne" if niveau == "panne" else "en alerte"
            messages.append((f"{noms(nom)} {mot}", f"{detail}\n{n} cycles de suite", "high" if niveau == "panne" else "default"))
        nouvel[nom] = {"niveau": niveau, "cycles": n, "envoye": envoye}
    for nom, vu in ancien.items():
        if nom not in courants and vu.get("envoye"):
            messages.append((f"{noms(nom)} rétablie", "Lecture normale", "default"))
    return nouvel, messages


def poster(messages, env=None, ouvrir=urlopen) -> int:
    env = os.environ if env is None else env
    url = (env.get("ALERTE_SANTE_URL") or env.get("ALERTE_WEBHOOK_URL") or "").strip()
    if not url.startswith("https://"):
        return 0
    envoyes = 0
    for titre, corps, priorite in messages[:5]:
        entetes = {"Content-Type": "text/plain; charset=utf-8", "User-Agent": "cotes-value", "Priority": priorite,
                   "Title": "=?UTF-8?B?" + base64.b64encode(titre.encode()).decode() + "?=",
                   "Tags": "warning" if priorite == "high" or "alerte" in titre else "white_check_mark"}
        try:
            with ouvrir(Request(url, data=corps.encode(), headers=entetes, method="POST"), timeout=5):
                envoyes += 1
        except (HTTPError, URLError, OSError, ValueError):
            pass
    return envoyes


def surveiller(donnees: Path, etapes: dict, env=None, ouvrir=urlopen, maintenant: datetime | None = None) -> dict:
    try:
        maintenant = maintenant or datetime.now(timezone.utc)
        chemin = donnees / ETAT
        try:
            ancien = json.loads(chemin.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            ancien = {}
        nouvel, messages = evaluer(etapes, ancien if isinstance(ancien, dict) else {}, maintenant)
        envoyes = poster(messages, env, ouvrir) if messages else 0
        tmp = chemin.with_suffix(".tmp")
        tmp.write_text(json.dumps(nouvel, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(chemin)
        return {"problemes": len(nouvel), "messages": len(messages), "envoyes": envoyes}
    except Exception as e:  # noqa: BLE001
        return {"erreur": type(e).__name__}
