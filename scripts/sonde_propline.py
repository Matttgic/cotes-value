"""Vérifie la clé et les scores gratuits en deux appels maximum, sans afficher le secret."""
from __future__ import annotations

import json
import os
import sys

import requests

BASE = "https://api.prop-line.com/v1/sports"


def sonder(cle: str, http=requests) -> tuple[dict, int]:
    bilan = {"configure": bool(cle), "appels": 0}
    if not cle:
        return {**bilan, "erreur": "Secret PROPLINE_API_KEY absent"}, 1

    def lire(chemin, params=None):
        bilan["appels"] += 1
        try:
            r = http.get(BASE + chemin, headers={"X-API-Key": cle}, params=params, timeout=25)
            bilan["http"] = r.status_code
            try:
                bilan["quota_restant"] = int(r.headers["X-Daily-Remaining"])
            except (KeyError, ValueError, TypeError):
                pass
            if r.status_code != 200:
                bilan["erreur"] = f"HTTP {r.status_code}"
                return None
            d = r.json()
            if not isinstance(d, list) or any(not isinstance(x, dict) for x in d):
                bilan["erreur"] = "Réponse inattendue"
                return None
            return d
        except (requests.RequestException, ValueError):
            # Ni le corps de réponse ni l'exception (qui peut inclure la clé).
            bilan["erreur"] = "Lecture indisponible"
            return None

    sports = lire("")
    if sports is None or any(not isinstance(s.get("key"), str) for s in sports):
        return bilan, 1
    bilan.update(cle_validee=True, competitions=len(sports),
                 cles_competitions=sorted({s["key"] for s in sports}))
    # Une compétition couverte explicitement : aucun appel /results payant.
    choix = next((s for s in ("hockey_nhl", "basketball_nba", "soccer_epl")
                  if s in bilan["cles_competitions"]), None)
    if not choix:
        return {**bilan, "erreur": "Aucune compétition de test disponible"}, 1
    scores = lire(f"/{choix}/scores", {"days_from": 3})
    if scores is None:
        return bilan, 1
    bilan.update(scores_gratuits_accessibles=True, competition_test=choix,
                 matchs=len(scores), termines=sum(g.get("status") == "final" for g in scores))
    return bilan, 0


if __name__ == "__main__":
    bilan, code = sonder(os.environ.get("PROPLINE_API_KEY", "").strip())
    print(json.dumps(bilan, ensure_ascii=False))
    sys.exit(code)
