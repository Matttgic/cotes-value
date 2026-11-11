"""Résultats 365Scores : un deuxième avis pour les sports où Flashscore était la seule source gratuite.

API publique de l'application web (``webws.365scores.com``), sans clé ni compte. Relevé du 10/11/2026 depuis GitHub
Actions (``scripts/sonde_sources_us.py``) : HTTP 200, une liste ``games`` par sport et par jour, chaque match avec
``startTime``, ``statusText`` (« Ended » une fois fini), et ``homeCompetitor`` / ``awayCompetitor`` (``name``,
``score``). Source non officielle, qui peut changer sans préavis.

Seulement le score final, jamais le détail par période, et seulement les matchs dont le statut est exactement
« Ended » : tout autre libellé (prolongation, tirs au but, abandon, forfait…) est laissé de côté plutôt que deviné.
Volley : score en sets. Deux sources d'accord règlent tout de suite (cotes/resultats.py) ; en désaccord, le pari
attend une saisie à la main au lieu d'être réglé sur un score faux. Seule, cette source ne règle qu'après 24 h.

``SCORES_365`` = ``non`` coupe la lecture.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from .temps import instant_utc

BASE = "https://webws.365scores.com/web/games/allscores/"
# identifiants relevés le 10/11/2026 (liste /web/sports/) ; les sports déjà couverts par deux sources n'y sont pas
SPORTS = {"basket": 2, "handball": 5, "volley": 8, "rugby": 9}
HISTORIQUE_J = 7
JOURS_MAX = 4               # appels par sport et par cycle de règlement, les jours les plus récents d'abord
ERREURS: list[str] = []


def active(environ=None) -> bool:
    env = os.environ if environ is None else environ
    return str(env.get("SCORES_365", "oui")).strip().lower() not in ("non", "off", "0")


def _session():
    try:
        from curl_cffi.requests import Session
        return Session(impersonate="chrome")
    except Exception:  # noqa: BLE001 - bibliothèque absente : requests suffit peut-être
        import requests
        return requests.Session()


def _score(x) -> int | None:
    if isinstance(x, bool) or not isinstance(x, (int, float)) or x < 0 or x != int(x):
        return None
    return int(x)


def match(sport: str, g: dict) -> dict | None:
    """Un match terminé normalement, au format des validateurs ; None sinon."""
    if not isinstance(g, dict) or g.get("statusText") != "Ended":
        return None
    dom, ext = g.get("homeCompetitor") or {}, g.get("awayCompetitor") or {}
    if g.get("isHomeAwayInverted"):
        dom, ext = ext, dom
    debut = instant_utc(g.get("startTime"))
    score = (_score(dom.get("score")), _score(ext.get("score")))
    if not dom.get("name") or not ext.get("name") or debut is None or None in score:
        return None
    return {"source": "365scores", "id_source": g.get("id"), "sport": sport, "domicile": str(dom["name"]),
            "exterieur": str(ext["name"]), "debut": debut, "score": score, "periodes": [], "libelles": [],
            "corners": None, "abandon": False}


def lire(sport: str, jours: list[str], maintenant: datetime | None = None, http=None) -> list[dict]:
    """Matchs terminés de ces jours (AAAA-MM-JJ, UTC). Une panne ou un format inattendu est noté, jamais levé."""
    maintenant = maintenant or datetime.now(timezone.utc)
    identifiant = SPORTS.get(sport)
    if identifiant is None or not active():
        return []
    out, vus = [], set()
    http = http or _session()
    recents = [j for j in sorted(set(jours), reverse=True)
               if 0 <= (maintenant.date() - datetime.strptime(j, "%Y-%m-%d").date()).days <= HISTORIQUE_J]
    for jour in recents[:JOURS_MAX]:
        date = datetime.strptime(jour, "%Y-%m-%d").strftime("%d/%m/%Y")
        try:
            r = http.get(BASE, params={"appTypeId": 5, "langId": 1, "timezoneName": "UTC", "userCountryId": 1,
                                       "sports": identifiant, "startDate": date, "endDate": date,
                                       "showOdds": "false", "onlyMajorGames": "false"}, timeout=30)
            if r.status_code != 200:
                raise ValueError(f"HTTP {r.status_code}")
            doc = r.json()
            if not isinstance(doc, dict) or not isinstance(doc.get("games", []), list):
                raise ValueError("format inattendu")
        except Exception as ex:  # noqa: BLE001 - un secours en panne ne coupe pas le règlement
            ERREURS.append(f"{sport} {jour} : {repr(ex)[:120]}")
            continue
        for g in doc.get("games") or []:
            m = match(sport, g)
            if m and m["id_source"] not in vus:
                vus.add(m["id_source"])
                out.append(m)
    return out


def jours_a_lire(paris: list[dict], maintenant: datetime) -> dict[str, list[str]]:
    """Sport -> jours UTC (le jour du match et la veille) des paris ouverts commencés depuis 2 h."""
    out: dict[str, set[str]] = {}
    for p in paris:
        if p.get("statut") not in ("en_cours", "a_regler") or p.get("sport") not in SPORTS:
            continue
        debut = instant_utc(p.get("reporte_au") or p.get("debut"))
        if debut is None or not timedelta(hours=2) < maintenant - debut < timedelta(days=HISTORIQUE_J):
            continue
        for k in (0, -1):
            out.setdefault(p["sport"], set()).add((debut + timedelta(days=k)).date().isoformat())
    return {sport: sorted(jours) for sport, jours in out.items()}
