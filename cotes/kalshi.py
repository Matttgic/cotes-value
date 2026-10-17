"""Collecte des marchés « vainqueur » de matchs Kalshi (API publique officielle, sans clé).

Kalshi est un marché de prédiction réglementé (États-Unis). Pour chaque match, un marché
oui/non par issue (« Arsenal wins », « Tie », « Leeds wins »). Probabilité juste = milieu entre
le meilleur achat et la meilleure vente du « oui », renormalisée sur les issues du match.

Limites : pas d'heure de début (seulement l'heure de fin prévue, `occurrence_datetime`) et pas
d'ordre domicile/extérieur garanti : l'association avec les autres sources se fait sur les noms
d'équipes et la date, dans les deux sens.
"""
from __future__ import annotations

import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from math import isfinite
from threading import Event, Lock

import requests

BASE = "https://api.elections.kalshi.com/trade-api/v2"
EXCLUS = ("LOCATION", "SERIES", "MATCHUP", "DERBY", "3PT", "1STHOME", "SPECIALS", "GAMETD", "GAMETO", "TOTALGAMES")
SPORTS = {"Soccer": "football", "Basketball": "basket", "Football": "football_americain", "Baseball": "baseball",
          "Tennis": "tennis", "Hockey": "hockey", "Esports": "esport", "Cricket": "cricket", "MMA": "mma"}
DUREE = {"football": 2, "basket": 2.5, "football_americain": 3.5, "baseball": 3, "tennis": 2, "hockey": 2.5,
         "esport": 2, "cricket": 4, "mma": 1}    # durée typique (h) : heure de fin prévue -> début approximatif


ERREURS: list[str] = []
logger = logging.getLogger(__name__)
_verrou = Lock()
_bloque = Event()


def _erreur(message: str) -> None:
    # Aucun corps HTTP, paramètre de requête ni texte d'exception dans les logs.
    with _verrou:
        if message not in ERREURS and len(ERREURS) < 30:
            ERREURS.append(message)
            logger.warning("Kalshi : %s", message)


def _nombre(x):
    if isinstance(x, bool):
        return None
    try:
        n = float(x)
        return n if isfinite(n) else None
    except (TypeError, ValueError, OverflowError):
        return None


def est_nul(nom: str) -> bool:
    # Un préfixe libre « tie » confondrait par exemple Tielemans avec le nul.
    return isinstance(nom, str) and bool(re.fullmatch(
        r"(?:tie|draw)(?:\s*\((?:90\s*(?:mins?|minutes?)|regulation(?: time)?)\))?",
        nom.strip(), re.I))


def _get(path: str, params: dict | None = None, essais: int = 3):
    for i in range(min(3, max(0, essais))):
        if _bloque.is_set():
            return None
        try:
            r = requests.get(BASE + path, params=params, timeout=60)
            recue = datetime.now(timezone.utc).isoformat(timespec="seconds")
            if r.status_code == 200:
                try:
                    d = r.json()
                except ValueError:
                    _erreur("JSON invalide")
                    return None
                if not isinstance(d, dict):
                    _erreur("objet JSON attendu")
                    return None
                return {**d, "_collecte": recue}
            _erreur(f"HTTP {r.status_code}")
            if r.status_code in (401, 403, 429):
                # Une rafale de séries ne doit pas amplifier un refus/quota.
                _bloque.set()
                return None
            if r.status_code != 408 and not 500 <= r.status_code <= 599:
                return None
        except requests.RequestException:
            _erreur("réseau indisponible")
        if i + 1 < min(3, essais):
            time.sleep(2 * (i + 1))
    return None


def series_matchs() -> list[tuple[str, str]]:
    """(ticker, sport) des séries « match » sportives (vainqueur d'un match)."""
    d = _get("/series", {"category": "Sports"}) or {}
    out = []
    series = d.get("series") or []
    if not isinstance(series, list):
        _erreur("liste de séries attendue")
        return []
    for s in series:
        if not isinstance(s, dict) or not isinstance(s.get("ticker"), str):
            _erreur("série invalide")
            continue
        t = s["ticker"]
        if not re.search(r"(GAME|MATCH)$", t) or any(x in t for x in EXCLUS):
            continue
        tags = s.get("tags") or []
        if not isinstance(tags, list):
            _erreur("tags de série invalides")
            continue
        sport = next((SPORTS[x] for x in tags if isinstance(x, str) and x in SPORTS), None)
        if sport:
            out.append((t, sport))
    return out


def _evenements(serie: str, pages_max: int = 10) -> list[dict]:
    """Événements ouverts d'une série, toutes pages (200 par page ; le football universitaire en a plus)."""
    out, vus, curseurs, curseur = [], set(), set(), None
    for _ in range(pages_max):
        params = {"series_ticker": serie, "status": "open", "with_nested_markets": "true", "limit": 200}
        if curseur:
            params["cursor"] = curseur
        d = _get("/events", params) or {}
        events = d.get("events") or []
        if not isinstance(events, list):
            _erreur("liste d'événements attendue")
            break
        for e in events:
            if not isinstance(e, dict) or not isinstance(e.get("event_ticker"), str):
                _erreur("événement invalide")
                continue
            if e["event_ticker"] not in vus:
                vus.add(e["event_ticker"])
                out.append({**e, "_collecte": d.get("_collecte")})
        curseur = d.get("cursor")
        if not curseur or not events:
            break
        if not isinstance(curseur, str) or curseur in curseurs:
            _erreur("curseur invalide ou répété")
            break
        curseurs.add(curseur)
    return out


def collecter(heures: int = 48) -> list[dict]:
    ERREURS.clear()
    _bloque.clear()
    series = series_matchs()
    with ThreadPoolExecutor(max_workers=6) as pool:
        resultats = list(pool.map(lambda s: (s, _evenements(s[0])), series))
    maintenant = datetime.now(timezone.utc)
    limite = maintenant + timedelta(hours=heures)
    lignes: list[dict] = []
    for (serie, sport), evs in resultats:
        for e in evs:
            titre = e.get("title")
            m = re.match(r"^(.+?) vs\.? (.+)$", titre) if isinstance(titre, str) else None
            marches = e.get("markets")
            if not isinstance(marches, list) or any(not isinstance(mk, dict) for mk in marches):
                _erreur("marchés invalides")
                continue
            # Pas de renormalisation d'un groupe dont une issue est fermée/inconnue.
            if any(mk.get("status") not in ("active", "open") for mk in marches):
                continue
            if not m or not marches:
                continue
            fin = marches[0].get("occurrence_datetime") or marches[0].get("expected_expiration_time")
            try:
                fin_dt = datetime.fromisoformat(fin.replace("Z", "+00:00"))
            except (AttributeError, ValueError):
                continue
            if fin_dt.tzinfo is None:
                _erreur("date sans fuseau")
                continue
            debut = fin_dt - timedelta(hours=DUREE.get(sport, 2))
            # Radar large uniquement : cette estimation ne prouve jamais un début réel.
            # Le placement et la clôture utilisent ensuite le début du bookmaker FR.
            if not (maintenant - timedelta(hours=5) <= debut <= limite + timedelta(hours=5)):
                continue
            a, b = m.group(1).strip(), m.group(2).strip()
            issues = []
            for mk in marches:
                achat, vente = _nombre(mk.get("yes_bid_dollars")), _nombre(mk.get("yes_ask_dollars"))
                nom = mk.get("yes_sub_title")
                if (achat is None or vente is None or not (0 < achat <= vente < 1)
                        or not isinstance(nom, str) or not nom.strip()):
                    continue
                issues.append((nom.strip(), (achat + vente) / 2, achat, vente, mk))
            if (len(issues) not in (2, 3) or len(issues) != len(marches)
                    or len({n.casefold() for n, *_ in issues}) != len(issues)):
                _erreur("issues incomplètes ou invalides")
                continue
            nul = any(est_nul(n) for n, *_ in issues)
            if len(issues) != (3 if nul else 2) or not e.get("_collecte"):
                continue
            s = sum(p for _, p, *_ in issues)
            for nom, p, achat, vente, mk in issues:
                issue = "NUL" if est_nul(nom) else nom      # équipe : résolue à l'association
                lignes.append({
                    "source": "kalshi", "sport": sport, "ligue": serie, "match_id": e.get("event_ticker"),
                    "domicile": a, "exterieur": b, "ordre_incertain": True,
                    "debut": debut.isoformat(timespec="seconds"), "debut_approximatif": True,
                    "collecte": e["_collecte"],
                    "marche": "RESULTAT_1N2" if nul else "VAINQUEUR", "periode": "MATCH", "ligne": None,
                    "issue": issue, "joueur": None, "achat": achat, "vente": vente,
                    "ecart_achat_vente": round(vente - achat, 4), "proba_juste_brute": round(p, 5),
                    "proba_juste": round(p / s, 5), "cote_juste": round(s / p, 4),
                    "liquidite": max(0, _nombre(mk.get("open_interest_fp") or mk.get("open_interest")) or 0),
                    "cle_marche": f"ks|{e.get('event_ticker')}",
                    "lien": f"https://kalshi.com/markets/{serie.lower()}"})
    return lignes
