"""Collecte des marchés « vainqueur » de matchs Kalshi (API publique officielle, sans clé).

Kalshi est un marché de prédiction réglementé (États-Unis). Pour chaque match, un marché
oui/non par issue (« Arsenal wins », « Tie », « Leeds wins »). Probabilité juste = milieu entre
le meilleur achat et la meilleure vente du « oui », renormalisée sur les issues du match.

Limites : pas d'heure de début (seulement l'heure de fin prévue, `occurrence_datetime`) et pas
d'ordre domicile/extérieur garanti : l'association avec les autres sources se fait sur les noms
d'équipes et la date, dans les deux sens.
"""
from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import requests

BASE = "https://api.elections.kalshi.com/trade-api/v2"
EXCLUS = ("LOCATION", "SERIES", "MATCHUP", "DERBY", "3PT", "1STHOME", "SPECIALS", "GAMETD", "GAMETO", "TOTALGAMES")
SPORTS = {"Soccer": "football", "Basketball": "basket", "Football": "football_americain", "Baseball": "baseball",
          "Tennis": "tennis", "Hockey": "hockey", "Esports": "esport", "Cricket": "cricket", "MMA": "mma"}
DUREE = {"football": 2, "basket": 2.5, "football_americain": 3.5, "baseball": 3, "tennis": 2, "hockey": 2.5,
         "esport": 2, "cricket": 4, "mma": 1}    # durée typique (h) : heure de fin prévue -> début approximatif


def _get(path: str, params: dict | None = None, essais: int = 3):
    for i in range(essais):
        try:
            r = requests.get(BASE + path, params=params, timeout=60)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429:
                time.sleep(2 * (i + 1))
                continue
        except (requests.RequestException, ValueError):
            pass
        time.sleep(1 + i)
    return None


def series_matchs() -> list[tuple[str, str]]:
    """(ticker, sport) des séries « match » sportives (vainqueur d'un match)."""
    d = _get("/series", {"category": "Sports"}) or {}
    out = []
    for s in d.get("series") or []:
        t = s.get("ticker", "")
        if not re.search(r"(GAME|MATCH)$", t) or any(x in t for x in EXCLUS):
            continue
        sport = next((SPORTS[x] for x in s.get("tags") or [] if x in SPORTS), None)
        if sport:
            out.append((t, sport))
    return out


def _evenements(serie: str) -> list[dict]:
    d = _get("/events", {"series_ticker": serie, "status": "open", "with_nested_markets": "true", "limit": 200})
    return (d or {}).get("events") or []


def collecter(heures: int = 48) -> list[dict]:
    series = series_matchs()
    with ThreadPoolExecutor(max_workers=6) as pool:
        resultats = list(pool.map(lambda s: (s, _evenements(s[0])), series))
    maintenant = datetime.now(timezone.utc)
    limite = maintenant + timedelta(hours=heures)
    lignes: list[dict] = []
    for (serie, sport), evs in resultats:
        for e in evs:
            m = re.match(r"^(.+?) vs\.? (.+)$", e.get("title") or "")
            marches = [mk for mk in e.get("markets") or [] if mk.get("status") in (None, "active", "open")]
            if not m or not marches:
                continue
            fin = marches[0].get("occurrence_datetime") or marches[0].get("expected_expiration_time")
            try:
                fin_dt = datetime.fromisoformat(fin.replace("Z", "+00:00"))
            except (AttributeError, ValueError):
                continue
            debut = fin_dt - timedelta(hours=DUREE.get(sport, 2))
            if not (maintenant - timedelta(hours=1) <= debut <= limite):
                continue
            a, b = m.group(1).strip(), m.group(2).strip()
            issues = []
            for mk in marches:
                try:
                    achat, vente = float(mk.get("yes_bid_dollars")), float(mk.get("yes_ask_dollars"))
                except (TypeError, ValueError):
                    continue
                if not (0 < achat <= vente < 1):
                    continue
                nom = mk.get("yes_sub_title") or ""
                issues.append((nom, (achat + vente) / 2, achat, vente, mk))
            if len(issues) < 2:
                continue
            nul = any(n.lower() in ("tie", "draw") for n, *_ in issues)
            s = sum(p for _, p, *_ in issues) if len(issues) == len(marches) else 1.0
            for nom, p, achat, vente, mk in issues:
                issue = "NUL" if nom.lower() in ("tie", "draw") else nom      # équipe : résolue à l'association
                lignes.append({
                    "source": "kalshi", "sport": sport, "ligue": serie, "match_id": e.get("event_ticker"),
                    "domicile": a, "exterieur": b, "ordre_incertain": True,
                    "debut": debut.isoformat(timespec="seconds"), "debut_approximatif": True,
                    "collecte": maintenant.isoformat(timespec="seconds"),
                    "marche": "RESULTAT_1N2" if nul else "VAINQUEUR", "periode": "MATCH", "ligne": None,
                    "issue": issue, "joueur": None, "achat": achat, "vente": vente,
                    "ecart_achat_vente": round(vente - achat, 4), "proba_juste_brute": round(p, 5),
                    "proba_juste": round(p / s, 5), "cote_juste": round(s / p, 4),
                    "liquidite": mk.get("open_interest_fp") or mk.get("open_interest"),
                    "cle_marche": f"ks|{e.get('event_ticker')}",
                    "lien": f"https://kalshi.com/markets/{serie.lower()}"})
    return lignes
