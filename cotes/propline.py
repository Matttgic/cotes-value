"""Scores Prop-Line gratuits, en secours seulement (https://prop-line.com/docs).

Pas de /results payant, ni de deuxième vote ESPN : le fournisseur réutilise
notamment ce flux. Les restrictions de marchés et le rapprochement prudent
sont partagés avec The Odds API ; aucun score de période n'est inventé.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

import requests

from . import resultats, theodds

BASE = "https://api.prop-line.com/v1/sports"
MAX_APPELS = 24
BUDGET_JOUR = 800                     # réserve sur les 1 000 appels gratuits
REESSAI = timedelta(hours=1)
GARDE = timedelta(days=8)

# Clés canoniques documentées, compétitions sans ambiguïté. Les coupes et
# ligues à playoffs de football restent exclues faute de score à 90 minutes.
CLES = {
    "basketball_nba": "basketball_nba", "basketball_wnba": "basketball_wnba",
    "basketball_ncaab": "basketball_ncaab", "icehockey_nhl": "hockey_nhl",
    "americanfootball_nfl": "football_nfl", "americanfootball_ncaaf": "football_ncaaf",
    "soccer_epl": "soccer_epl",
    "soccer_france_ligue_one": "soccer_ligue_1",
    "soccer_germany_bundesliga": "soccer_bundesliga",
    "soccer_germany_bundesliga2": "soccer_germany_bundesliga2",
    "soccer_italy_serie_a": "soccer_serie_a", "soccer_spain_la_liga": "soccer_la_liga",
    "soccer_portugal_primeira_liga": "soccer_primeira_liga",
    "soccer_brazil_campeonato": "soccer_brasileirao",
}


def competition(p: dict) -> str | None:
    # La MLB n'est pas activée sans identification robuste des doubleheaders.
    return CLES.get(theodds.competition(p))


def capturer(g: dict, cle: str, maintenant: datetime) -> dict | None:
    if (not isinstance(g, dict) or g.get("status") != "final" or g.get("live") is True
            or g.get("period") not in (None, "")):
        return None
    # Les scores sont des entiers, jamais des booléens ni des jeux de tennis.
    if any(type(g.get(k)) is not int or g[k] < 0 for k in ("home_score", "away_score")):
        return None
    return theodds._capture({**g, "completed": True, "scores": [
        {"name": g.get("home_team"), "score": g["home_score"]},
        {"name": g.get("away_team"), "score": g["away_score"]},
    ]}, cle, maintenant)


def _exploitables(entree: dict) -> list[dict]:
    """Conserve les derniers scores, mais suspend ceux contredits par le fournisseur."""
    attente = entree.get("a_reconfirmer", {})
    return [m for m in entree.get("matchs", []) if m["id"] not in attente]


def collecter(paris: list[dict], deja: dict, enregistrements: list[dict], cle_api: str,
              cache: dict, maintenant: datetime, http=requests) -> tuple[dict, dict]:
    """Cache persistant et diagnostic sans clé, URL authentifiée ni corps d'erreur."""
    bilan = {"configure": bool(cle_api), "requetes_scores": 0, "matchs_valides": 0,
             "paris_compatibles": 0, "conflits": 0, "erreurs": [],
             "couverture": {k: 0 for k in ("deja_valide", "marche_non_couvert",
                 "competition_non_couverte", "trop_recent", "hors_fenetre", "eligibles")}}
    if not cle_api:
        return {}, bilan
    jour = maintenant.strftime("%Y-%m-%d")
    if cache.get("jour") != jour:
        cache.update(jour=jour, requetes_jour=0)
        cache.pop("quota_restant", None)
    empreinte = hashlib.sha256(cle_api.encode()).hexdigest()[:16]
    if cache.get("empreinte") != empreinte:
        if cache.get("empreinte"):
            for e in cache.get("ligues", {}).values():
                e.pop("essai", None)
        cache["empreinte"] = empreinte
        cache.pop("reessai_apres", None)
        cache.pop("quota_restant", None)
    ligues = cache.setdefault("ligues", {})
    for k in list(ligues):
        e = ligues[k]
        e["matchs"] = [m for m in e.get("matchs", []) if (d := theodds._heure(m.get("debut")))
                       and timedelta(0) < maintenant - d < GARDE]
        ids = {m["id"] for m in e["matchs"]}
        e["a_reconfirmer"] = {k: v for k, v in e.get("a_reconfirmer", {}).items() if k in ids}
        if not e["matchs"] and (not (d := theodds._heure(e.get("essai"))) or maintenant - d >= GARDE):
            del ligues[k]
    besoin = {}
    for p in paris:
        debut = theodds._heure(p.get("reporte_au") or p.get("debut"))
        if p.get("statut") not in ("en_cours", "a_regler") or not debut or debut > maintenant:
            continue
        cle = competition(p)
        raison = ("deja_valide" if p["match_id"] in deja else
                  "marche_non_couvert" if not theodds.compatible(p) else
                  "trop_recent" if maintenant - debut < timedelta(hours=6) else
                  "hors_fenetre" if maintenant - debut >= GARDE else
                  "competition_non_couverte" if not cle else "eligibles")
        bilan["couverture"][raison] += 1
        if raison == "eligibles":
            besoin.setdefault(cle, []).append(p)
    for cle, ps in sorted(besoin.items(), key=lambda x: (ligues.get(x[0], {}).get("essai", ""), x[0])):
        e = ligues.setdefault(cle, {"matchs": []})
        nouveaux = [p for p in ps if not theodds.retrouver(p, _exploitables(e), cle)]
        essai = theodds._heure(e.get("essai"))
        bloque = theodds._heure(cache.get("reessai_apres"))
        if (not nouveaux or (essai and maintenant - essai < REESSAI)
                or (bloque and maintenant < bloque)
                or not any(maintenant - theodds._heure(p.get("reporte_au") or p["debut"]) < timedelta(days=3)
                           for p in nouveaux)):
            continue
        if (bilan["requetes_scores"] >= MAX_APPELS or cache.get("requetes_jour", 0) >= BUDGET_JOUR
                or cache.get("quota_restant", 1000) <= 100):
            break
        cache["requetes_jour"] = cache.get("requetes_jour", 0) + 1
        bilan["requetes_scores"] += 1
        e["essai"] = maintenant.isoformat(timespec="seconds")
        try:
            r = http.get(f"{BASE}/{cle}/scores", params={"days_from": 3},
                         headers={"X-API-Key": cle_api}, timeout=20)
            try:
                cache["quota_restant"] = max(0, int(r.headers["X-Daily-Remaining"]))
            except (KeyError, TypeError, ValueError):
                pass
            if r.status_code != 200:
                bilan["erreurs"].append(f"{cle} : HTTP {r.status_code}")
                delai = 3600
                if r.status_code in (401, 403, 429):
                    try:
                        delai = max(delai, int(r.headers.get("Retry-After", 0)))
                    except (TypeError, ValueError):
                        pass
                    cache["reessai_apres"] = (maintenant + timedelta(seconds=delai)).isoformat()
                continue
            try:
                d = r.json()
            except ValueError:
                bilan["erreurs"].append(f"{cle} : JSON invalide")
                continue
            if not isinstance(d, list) or any(not isinstance(g, dict) for g in d):
                bilan["erreurs"].append(f"{cle} : réponse inattendue")
                continue
            matchs = {m["id"]: m for m in e["matchs"]}
            for g in d:
                m = None if g.get("deleted") is True else capturer(g, cle, maintenant)
                attente = e.setdefault("a_reconfirmer", {})
                if m:
                    matchs[m["id"]] = m
                    attente.pop(m["id"], None)
                elif g.get("sport_key") == cle and str(g.get("id")) in matchs:
                    # Une réponse partielle/annulée ne détruit pas le score connu,
                    # et ne permet pas de régler avec un final désormais contredit.
                    attente[str(g["id"])] = {"lu": maintenant.isoformat(timespec="seconds"),
                        "raison": "supprime" if g.get("deleted") is True else "final_non_reconfirme"}
            e["matchs"] = list(matchs.values())
        except (requests.RequestException, ValueError):
            bilan["erreurs"].append(f"{cle} : lecture indisponible")
    valides = {}
    for cle, ps in besoin.items():
        for p in ps:
            m = theodds.retrouver(p, _exploitables(ligues[cle]), cle)
            if not m:
                continue
            autres = resultats.retrouver(p, enregistrements)
            if any(tuple(r["score"]) != m["score"] for r in autres):
                bilan["conflits"] += 1
                continue
            r = valides.setdefault(p["match_id"], {
                "sport": p["sport"], "score": m["score"], "final": True,
                "periodes": [], "libelles": [], "corners": None,
                "sources": ["propline"], "id_paris_autorises": [],
                "preuve_source": {"source": "Prop-Line", "event_id": m["id"], "sport_key": cle,
                                  "debut": m["debut"], "lu": m["lu"], "status": "final"},
            })
            if r["score"] == m["score"]:
                r["id_paris_autorises"].append(p["id"])
    bilan.update(matchs_a_reconfirmer=sum(len(e.get("a_reconfirmer", {})) for e in ligues.values()),
                 matchs_valides=len(valides),
                 paris_compatibles=sum(len(r["id_paris_autorises"]) for r in valides.values()),
                 requetes_jour=cache.get("requetes_jour", 0))
    if "quota_restant" in cache:
        bilan["quota_restant"] = cache["quota_restant"]
    return valides, bilan
