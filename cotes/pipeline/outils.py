"""Outils communs des étapes du cycle (déplacés de scripts/cycle.py, E3.1) : étape notée dans le journal, lecture
des paris, fichiers obsolètes."""
from __future__ import annotations

import time
import traceback
from pathlib import Path

from cotes import stockage
from cotes.depot.json_io import lire_json


def etape(nom: str, journal: dict, fonction, *args, **kwargs):
    """Exécute une étape ; une source en panne n'arrête pas le cycle (l'erreur est notée)."""
    t = time.time()
    try:
        r = fonction(*args, **kwargs)
        journal["etapes"][nom] = {"secondes": round(time.time() - t, 1), "ok": True}
        return r
    except Exception as e:                                       # noqa: BLE001
        journal["etapes"][nom] = {"secondes": round(time.time() - t, 1), "ok": False, "erreur": repr(e)[:300]}
        traceback.print_exc()
        return None


def signaler(journal: dict, nom: str, erreurs: list[str]) -> None:
    """Une étape qui a perdu des lectures (HTTP 500, coupure…) est marquée dégradée, pas « ok » muette :
    sinon « aucune source » pour un pari ne dit pas qu'une source était en panne."""
    if erreurs and nom in journal["etapes"]:
        journal["etapes"][nom] |= {"degrade": True, "erreurs": erreurs[:10]}


TEMOIN_ABANDONNE = "Pinnacle brut"

# Fichiers de « donnees » que plus aucun code ne lit ni n'écrit : caches d'API-Sports (plus lu depuis le 15/10/2026)
# et de PulseScore (arrêté le 18/10), rythme de l'ancien mode « shadow », rapports de bascule PulseScore -> lecture
# directe, et trois instantanés de paris des 5-6/10 (essais abandonnés, 5 Mo, absents des bilans). Retirés à chaque
# sauvegarde (rien s'ils sont déjà absents) ; l'historique de la branche les garde.
FICHIERS_OBSOLETES = ("apisports.json", "rythme_sources.json", "pulsescore_attentes.json",
                      "betclic_comparaison.json", "pmu_comparaison.json", "unibet_comparaison.json",
                      "winamax_comparaison.json", "docs/live_papier.json", "paris_avant_controle.json",
                      "paris_netbet_international.json", "paris_seuils_cumules.json")


def retirer_obsoletes(donnees: Path, journal: dict) -> None:
    """Supprime les fichiers de ``FICHIERS_OBSOLETES`` présents ; jamais bloquant."""
    retires = []
    for nom in FICHIERS_OBSOLETES:
        try:
            (donnees / nom).unlink()
            retires.append(nom)
        except OSError:          # absent (cas normal) ou non supprimable : rien à faire
            pass
    if retires:
        journal["obsoletes_retires"] = retires


def charger_paris(donnees: Path, journal: dict) -> list[dict]:
    """paris.json sans le témoin « Pinnacle brut », abandonné : il ne servait qu'à mesurer ce que change le retrait
    de la marge (ROI −12,6 % contre −12,8 % avec la marge retirée) et pesait 80 % du fichier. Retiré à la lecture,
    donc sous le verrou de la branche « donnees » ; l'historique reste dans les commits."""
    paris, retires = stockage.retirer_reference(lire_json(donnees / "paris.json", []), TEMOIN_ABANDONNE)
    if retires:
        journal["temoin_pinnacle_brut_retires"] = retires
    return paris
