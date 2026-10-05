"""Collecte PulseScore (bookmakers français + Betfair via Orbit Exchange) et traduction des marchés.

Listes paginées par 30 matchs, triées par heure de début : on lit les pages jusqu'à dépasser
l'horizon voulu. Limite de l'offre : 1 requête par seconde et par bookmaker en PRO (1 par minute
en STARTER), réglable par la variable PULSESCORE_PAUSE (secondes entre deux pages).

La traduction vers le vocabulaire commun (voir cotes/pinnacle.py) s'appuie sur le marché
normalisé de PulseScore (canonicalMarket) mais vérifie le libellé d'origine (rawName) : période
écrite dans le libellé, ligne de handicap notée différemment selon les sites, règles du hockey
(temps réglementaire ou prolongation incluse), marchés mal classés (breaks au tennis…).
"""
from __future__ import annotations

import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import requests

BASE = "https://api.pulsescore.net/api"
FRANCAIS = ["winamax", "betclic", "unibet-fr", "pmu", "netbet"]
NOMS = {"winamax": "Winamax", "betclic": "Betclic", "unibet-fr": "Unibet", "pmu": "PMU", "netbet": "NetBet",
        "orbitxch": "Betfair"}
SPORTS = {"soccer": "football", "basketball": "basket", "tennis": "tennis", "ice-hockey": "hockey",
          "handball": "handball", "volleyball": "volley", "rugby-union": "rugby", "american-football":
          "football_americain", "baseball": "baseball", "mma": "mma", "table-tennis": "tennis_de_table"}


# --------------------------------------------------------------------------- collecte

class Client:
    def __init__(self, cle: str, pause: float | None = None):
        self.s = requests.Session()
        self.s.headers.update({"X-Secret": cle, "Accept-Encoding": "gzip", "Accept": "application/json"})
        self.pause = float(os.environ.get("PULSESCORE_PAUSE", "1.1")) if pause is None else pause
        self.requetes = 0

    def get(self, chemin: str, params: dict | None = None):
        for essai in range(4):
            r = self.s.get(f"{BASE}/{chemin}", params=params, timeout=90)
            self.requetes += 1
            if r.status_code == 429:
                time.sleep(float(r.headers.get("Retry-After") or 2 * (essai + 1)) + self.pause)
                continue
            time.sleep(self.pause)
            return r.json() if r.status_code == 200 else None
        return None

    def matchs(self, bookmaker: str, sport: str, heures: float, pages_max: int = 40) -> list[dict]:
        """Matchs d'avant-match commençant dans les `heures` prochaines heures."""
        limite = datetime.now(timezone.utc) + timedelta(hours=heures)
        out = []
        for page in range(1, pages_max + 1):
            d = self.get(f"{bookmaker}/{sport}/events", {"page": page, "limit": 30})
            if not d or not d.get("events"):
                break
            maintenant = datetime.now(timezone.utc)
            for e in d["events"]:
                debut = _heure(e.get("startTime"))
                if not e.get("live") and not e.get("suspended") and debut and debut > maintenant:
                    out.append(e)
            dernier = _heure(d["events"][-1].get("startTime"))
            if not d.get("hasNextPage") or (dernier and dernier > limite):
                break
        return [e for e in out if (_heure(e["startTime"]) or limite) <= limite]


def collecter(cle: str, bookmakers: list[str], sports: list[str], heures: float = 36) -> tuple[list[dict], int]:
    """Lit chaque bookmaker en parallèle (la limite de débit est par bookmaker). Renvoie (lignes, requêtes)."""
    def un_bookmaker(bm: str):
        c = Client(cle)
        lignes = []
        for sp in sports:
            moment = datetime.now(timezone.utc).isoformat(timespec="seconds")
            for e in c.matchs(bm, sp, heures):
                lignes += traduire(e, bm, SPORTS.get(sp, sp), moment)
        return lignes, c.requetes

    with ThreadPoolExecutor(max_workers=len(bookmakers)) as pool:
        res = list(pool.map(un_bookmaker, bookmakers))
    return [l for r, _ in res for l in r], sum(n for _, n in res)


# --------------------------------------------------------------------------- traduction

def _heure(s):
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None


def _nombre(s) -> float | None:
    m = re.search(r"[-+]?\d+(?:[.,]\d+)?", s or "")
    return float(m.group(0).replace(",", ".")) if m else None


def _crochet(s) -> float | None:
    """« Aruba [-4,5] » -> -4.5 ; « Home (-2.5) » -> -2.5."""
    m = re.search(r"[\[(]\s*([-+]?\d+(?:[.,]\d+)?)\s*[\])]", s or "")
    return float(m.group(1).replace(",", ".")) if m else None


ORDINAUX = {"1": 1, "2": 2, "3": 3, "4": 4}


def periode(sport: str, canonique: str | None, libelle: str) -> str | None:
    """Période commune, d'après le libellé d'abord (plus fiable), sinon la période canonique."""
    l = (libelle or "").lower()
    n = None
    m = re.search(r"\b([1-4])\s*(?:er|ère|re|e|ème|eme|de|nd|st|rd|th)?\s*(mi-temps|half|tiers-temps|période|periode|"
                  r"quart-temps|quarter|set|period)", l)
    if m:
        n, unite = ORDINAUX[m.group(1)], m.group(2)
    elif re.search(r"(première|first)\s+(mi-temps|half)", l):
        n, unite = 1, "mi-temps"
    elif re.search(r"(seconde|second|deuxième)\s+(mi-temps|half)", l):
        n, unite = 2, "mi-temps"
    elif re.match(r"^mi-temps\b", l) or "half time" in l or "halftime" in l:
        n, unite = 1, "mi-temps"
    if n:
        if unite in ("mi-temps", "half"):
            return f"MT{n}"
        if unite in ("tiers-temps", "période", "periode", "period"):
            return f"P{n}" if sport == "hockey" else None
        if unite in ("quart-temps", "quarter"):
            return f"QT{n}"
        if unite == "set":
            return f"SET{n}"
    c = canonique or "FULL_TIME"
    if c == "FULL_TIME":
        return "MATCH"
    if sport != "tennis":
        return None        # période annoncée par PulseScore mais absente du libellé : ambigu, ignoré
    table = {"hockey": {"FIRST_HALF": "P1", "SECOND_HALF": "P2", "THIRD_PERIOD": "P3"},
             "tennis": {"FIRST_SET": "SET1", "SECOND_SET": "SET2", "FIRST_HALF": "SET1"}}.get(sport, {})
    if c in table:
        return table[c]
    return {"FIRST_HALF": "MT1", "SECOND_HALF": "MT2", "FIRST_QUARTER": "QT1", "SECOND_QUARTER": "QT2",
            "THIRD_QUARTER": "QT3", "FOURTH_QUARTER": "QT4", "FIRST_SET": "SET1", "SECOND_SET": "SET2"}.get(c)


def _temps_reglementaire(libelle: str) -> bool:
    l = (libelle or "").lower()
    return any(x in l for x in ("t. rég", "tps rég", "temps réglementaire", "regular time", "60 min", "(rt)"))


def _equipe(nom: str, dom: str, ext: str) -> str | None:
    n = (nom or "").strip().lower()
    if not n:
        return None
    if n in ("match nul", "nul", "n", "draw", "x", "tie"):
        return "NUL"
    if n == (dom or "").lower() or n in ("1", "home"):
        return "DOM"
    if n == (ext or "").lower() or n in ("2", "away"):
        return "EXT"
    return None


def traduire(e: dict, bookmaker: str, sport: str, moment: str) -> list[dict]:
    dom, ext = e.get("home"), e.get("away")
    base = {"source": NOMS.get(bookmaker, bookmaker), "bookmaker": bookmaker, "sport": sport,
            "ligue": e.get("league"), "match_id": f"{bookmaker}|{e.get('eventId')}", "domicile": dom,
            "exterieur": ext, "debut": e.get("startTime"), "collecte": moment, "joueur": None,
            "lien": e.get("slug")}
    out = []
    for m in e.get("markets") or []:
        # l'état « actif » du marché n'est pas fiable chez tous les bookmakers (NetBet) : on se fie aux cotes
        sels = [s for s in m.get("selections") or [] if s.get("isActive", True) and not s.get("suspended")
                and (s.get("odds") or 0) > 1]
        if not sels:
            continue
        canon, libelle = m.get("canonicalMarket"), m.get("rawName") or ""
        per = "MATCH" if canon == "HALF_TIME_FULL_TIME" else periode(sport, m.get("period"), libelle)
        if per is None:
            continue
        for marche, ligne, issue, s in _marche(canon, libelle, sels, sport, dom, ext):
            p = per
            if sport == "hockey" and per == "MATCH":
                if marche == "RESULTAT_1N2" or _temps_reglementaire(libelle):
                    p = "TEMPS_REG"
                elif marche not in ("VAINQUEUR",):
                    p = "MATCH?"            # prolongation incluse ou non : règle inconnue -> pas comparé
            out.append({**base, "marche": marche, "periode": p, "ligne": ligne, "issue": issue,
                        "cote": float(s["odds"]), "libelle": libelle, "cle_marche": f"{bookmaker}|{m.get('marketId')}",
                        "achat": s.get("back"), "vente": s.get("lay")})
    return out


def _marche(canon, libelle, sels, sport, dom, ext):
    """Générateur de (marché, ligne, issue, sélection) pour un marché PulseScore."""
    issues = {s.get("canonicalOutcome"): s for s in sels}
    l = libelle.lower()
    if canon in ("MATCH_RESULT", "HALF_TIME_RESULT", "SET_WINNER"):
        nul = "DRAW" in issues
        for k, s in issues.items():
            i = {"HOME": "DOM", "AWAY": "EXT", "DRAW": "NUL"}.get(k)
            if i:
                yield ("RESULTAT_1N2" if nul else "VAINQUEUR"), None, i, s
    elif canon == "DRAW_NO_BET":
        for k, s in issues.items():
            if k in ("HOME", "AWAY"):
                yield "DRAW_NO_BET", None, {"HOME": "DOM", "AWAY": "EXT"}[k], s
    elif canon == "DOUBLE_CHANCE":
        for k, s in issues.items():
            if k in ("HOME_DRAW", "HOME_AWAY", "DRAW_AWAY"):
                yield "DOUBLE_CHANCE", None, k, s
    elif canon in ("ASIAN_HANDICAP", "GAME_HANDICAP", "SET_HANDICAP"):
        if sport == "tennis" and canon == "ASIAN_HANDICAP":
            return                       # au tennis : sets ou jeux ? ambigu -> ignoré
        h, a = issues.get("HOME"), issues.get("AWAY")
        if not (h and a):
            return
        lh, la = h.get("line"), a.get("line")
        if lh is None:
            lh, la = _crochet(h.get("rawName")), _crochet(a.get("rawName"))
        if lh is None:
            return
        ligne = lh if (la is None or abs(lh + la) < 1e-9 and lh != 0) else lh
        if la is not None and abs(lh - la) < 1e-9:
            ligne = lh                   # même ligne sur les deux issues = ligne du domicile
        unite = {"GAME_HANDICAP": "JEUX_", "SET_HANDICAP": "SETS_"}.get(canon, "")
        yield unite + "HANDICAP", float(ligne), "DOM", h
        yield unite + "HANDICAP", float(ligne), "EXT", a
    elif canon == "EUROPEAN_HANDICAP":
        h = issues.get("HOME")
        ligne = h.get("line") if h else None
        if ligne is None and h:
            ligne = _crochet(h.get("rawName"))
        if ligne is None or "DRAW" not in issues:
            return
        for k, s in issues.items():
            i = {"HOME": "DOM", "AWAY": "EXT", "DRAW": "NUL"}.get(k)
            if i:
                yield "HANDICAP_3", float(ligne), i, s
    elif canon in ("OVER_UNDER", "HALF_TIME_OVER_UNDER", "HOME_OVER_UNDER", "AWAY_OVER_UNDER", "TOTAL_GAMES",
                   "TOTAL_SETS", "CORNERS_OVER_UNDER", "HOME_CORNERS_OVER_UNDER", "AWAY_CORNERS_OVER_UNDER"):
        if sport == "tennis" and canon in ("OVER_UNDER", "HOME_OVER_UNDER", "AWAY_OVER_UNDER") and "jeu" not in l \
                and "game" not in l:
            return                       # breaks, aces… mal classés en « total »
        prefixe = "CORNERS_" if "CORNERS" in canon else ("JEUX_" if (sport == "tennis" and canon != "TOTAL_SETS")
                                                          else ("SETS_" if canon == "TOTAL_SETS" else ""))
        marche = prefixe + ("TOTAL_DOM" if canon.startswith("HOME_") else
                            "TOTAL_EXT" if canon.startswith("AWAY_") else "TOTAL")
        for k, s in issues.items():
            if k not in ("OVER", "UNDER"):
                continue
            ligne = s.get("line")
            if ligne is None:
                ligne = _crochet(s.get("rawName")) or _nombre(s.get("rawName")) or _nombre(libelle)
            if ligne is None:
                continue
            yield marche, float(ligne), {"OVER": "PLUS", "UNDER": "MOINS"}[k], s
    elif canon == "BOTH_TEAMS_TO_SCORE":
        for k, s in issues.items():
            if k in ("YES", "NO"):
                yield "BOTH_TEAMS_TO_SCORE", None, k, s
    elif canon == "CORRECT_SCORE" and sport != "tennis":
        for s in sels:
            m = re.match(r"^\s*(\d+)\s*[-:]\s*(\d+)\s*$", s.get("rawName") or "")
            if m:
                yield "CORRECT_SCORE", None, f"{m.group(1)}-{m.group(2)}", s
    elif canon == "HALF_TIME_FULL_TIME":
        for s in sels:
            parts = re.split(r"\s*/\s*", s.get("rawName") or "")
            if len(parts) == 2:
                a, b = _equipe(parts[0], dom, ext), _equipe(parts[1], dom, ext)
                if a and b:
                    yield "HALF_TIME_FULL_TIME", None, f"{a}/{b}", s
