"""Échecs non bloquants rendus visibles : annotation GitHub Actions et liste récente dans ``etat.json``.

Certaines étapes ne doivent jamais arrêter le cycle (historique des cotes, redécision des paris ouverts,
validation Qwen, envoi des alertes Chrome) : leur erreur était avalée par un ``try/except`` ou masquée par
``continue-on-error``. Elle reste non bloquante, mais elle laisse désormais trois traces :

- une ligne ``::warning title=…::message`` dans le journal (annotation visible sur la page du lancement) ;
- ``etat.json`` › ``echecs_recents`` : ``{"total": n, "maj": …, "liste": [{"quand", "etape", "message"}, …]}``,
  les ``MAX_LISTE`` derniers échecs des ``GARDE`` derniers jours, compteur cumulé ``total`` ;
- la page Santé du site (ligne « Erreurs non bloquantes »), qui lit ``etat.json``.

Le message est court et ne contient jamais de secret : valeurs des variables d'environnement sensibles
masquées, paramètres d'URL et identifiants dans les URL retirés. Ce module ne lève jamais.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

CLE = "echecs_recents"
MAX_LISTE = 30
GARDE = timedelta(days=7)
LONGUEUR = 160
_SENSIBLE = re.compile(r"KEY|TOKEN|SECRET|PASS|URL|WEBHOOK|CREDENTIAL|AUTH", re.I)


def _masquer(texte: str, env=None) -> str:
    env = os.environ if env is None else env
    for nom, valeur in env.items():
        if _SENSIBLE.search(nom) and isinstance(valeur, str) and len(valeur.strip()) >= 6:
            texte = texte.replace(valeur.strip(), "***")
    texte = re.sub(r"(https?://)[^/\s@]+@", r"\1***@", texte)          # identifiants dans une URL
    texte = re.sub(r"(https?://[^\s?#'\"]+)\?[^\s'\"]*", r"\1?***", texte)  # paramètres (clés d'API)
    texte = re.sub(r"(?i)(bearer|token|key|secret)([=: ]+)[^\s,;'\"]+", r"\1\2***", texte)
    return texte


def message_court(erreur, env=None) -> str:
    """« TypeErreur: détail » sur une ligne, LONGUEUR caractères au plus, secrets masqués."""
    if isinstance(erreur, BaseException):
        texte = f"{type(erreur).__name__}: {erreur}" if str(erreur) else type(erreur).__name__
    else:
        texte = str(erreur)
    texte = " ".join(_masquer(texte, env).split())
    return texte[:LONGUEUR]


def _echapper(texte: str, propriete: bool = False) -> str:
    """Échappement des commandes de workflow GitHub (% CR LF, plus « : » et « , » dans une propriété)."""
    texte = texte.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    if propriete:
        texte = texte.replace(":", "%3A").replace(",", "%2C")
    return texte


def annoter(etape: str, message: str, sortie=None) -> None:
    """Annotation ``::warning::`` (GitHub Actions l'affiche sur le résumé du lancement). Ne lève jamais."""
    try:
        sortie = sortie or sys.stdout
        print(f"::warning title={_echapper('Non bloquant : ' + etape, True)}::{_echapper(message)}",
              file=sortie, flush=True)
    except Exception:  # noqa: BLE001
        pass


def noter(journal: dict, etape: str, erreur, maintenant: datetime | None = None, sortie=None) -> str:
    """Note un échec du cycle en cours dans ``journal["echecs"]`` et l'annonce. Rend le message court."""
    message = message_court(erreur)
    try:
        quand = (maintenant or datetime.now(timezone.utc)).isoformat(timespec="seconds")
        journal.setdefault("echecs", []).append({"quand": quand, "etape": etape, "message": message})
    except Exception:  # noqa: BLE001
        pass
    annoter(etape, message, sortie)
    return message


def fusionner(etat: dict, nouveaux: list, maintenant: datetime) -> dict:
    """Ajoute les échecs du cycle à ``etat[CLE]`` (liste bornée, compteur cumulé). Rend le bloc."""
    bloc = etat.get(CLE) if isinstance(etat.get(CLE), dict) else {}
    liste = [e for e in (bloc.get("liste") if isinstance(bloc.get("liste"), list) else []) if isinstance(e, dict)]
    nouveaux = [e for e in (nouveaux or []) if isinstance(e, dict)]
    limite = maintenant - GARDE
    gardes = []
    for e in liste + nouveaux:
        try:
            t = datetime.fromisoformat(str(e.get("quand")).replace("Z", "+00:00"))
        except ValueError:
            continue
        if t.tzinfo is not None and t >= limite:
            gardes.append({"quand": e.get("quand"), "etape": str(e.get("etape"))[:60],
                           "message": str(e.get("message"))[:LONGUEUR]})
    total = bloc.get("total") if isinstance(bloc.get("total"), int) and not isinstance(bloc.get("total"), bool) else 0
    nouveau_bloc = {"total": total + len(nouveaux), "liste": gardes[-MAX_LISTE:]}
    if nouveaux:
        nouveau_bloc["maj"] = maintenant.isoformat(timespec="seconds")
    elif bloc.get("maj"):
        nouveau_bloc["maj"] = bloc["maj"]
    etat[CLE] = nouveau_bloc
    return nouveau_bloc


def enregistrer(donnees: Path, etape: str, erreur, maintenant: datetime | None = None, sortie=None) -> bool:
    """Hors du cycle (script d'alertes) : annonce l'échec et l'ajoute à ``donnees/etat.json`` (écriture
    atomique). Rend False si l'état n'a pas pu être écrit ; ne lève jamais."""
    maintenant = maintenant or datetime.now(timezone.utc)
    journal: dict = {}
    noter(journal, etape, erreur, maintenant, sortie)
    try:
        chemin = Path(donnees) / "etat.json"
        try:
            etat = json.loads(chemin.read_text(encoding="utf-8"))
        except FileNotFoundError:
            etat = {}
        if not isinstance(etat, dict):
            return False
        fusionner(etat, journal.get("echecs", []), maintenant)
        tmp = chemin.with_name(chemin.name + ".tmp")
        tmp.write_text(json.dumps(etat, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, chemin)
        return True
    except Exception:  # noqa: BLE001 - un état illisible n'est jamais écrasé ; le cycle le signalera
        return False
