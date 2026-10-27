"""Cotes Matchbook (bourse), API REST publique « edge », lue sans compte ni clé.

``GET https://api.matchbook.com/edge/rest/events`` répond en JSON, sans cookie ni
session : meilleurs back et lay, et le montant disponible. Le milieu back/lay est
la cote juste, comme Betfair (``achat`` = meilleur back, ``vente`` = meilleur lay,
``reference_echange``).

Une requête par sport et par cycle (``before`` = horizon 36 h, ``per-page`` 200,
``price-depth`` 1). Politique d'usage : 700 requêtes/min sur le groupe Events.
Ce lecteur reste à deux ou trois requêtes par cycle.

``SOURCE_MATCHBOOK`` : ``direct`` (défaut, les paris value sont pris), ``shadow``
(lecture seule, rien n'est comparé), ``off`` (aucun appel). Une valeur inconnue
reste ``direct``. Aucun identifiant : pas de compte, pas de session-token.
Un 401, 403 ou 429 coupe la lecture ; le cycle continue sans Matchbook.
"""
from __future__ import annotations

import os
import random
import re
import time
from datetime import datetime, timedelta, timezone

import requests

BASE = "https://api.matchbook.com/edge/rest"
SPORTS = {15: "football", 9: "tennis"}
NOM_SOURCE = "Matchbook"
# Toujours hors de la moyenne partagée : les stratégies qui lisent le Consensus
# (Grok 3, entre autres) ne voient pas Matchbook. La table de paris, elle, existe.
HORS_CONSENSUS = frozenset({NOM_SOURCE})
_echeance = None
# (nom de marché, type Matchbook) -> (marché interne, période)
MARCHES_NOM = {
    "Match Odds": ("RESULTAT_1N2", "MATCH"),
    "Half-time Result": ("RESULTAT_1N2", "MT1"),
    "Draw No Bet": ("DRAW_NO_BET", "MATCH"),
    "Double Chance": ("DOUBLE_CHANCE", "MATCH"),
    "Both Teams To Score": ("BOTH_TEAMS_TO_SCORE", "MATCH"),
    "Correct Score": ("CORRECT_SCORE", "MATCH"),
    "Half Time/Full Time": ("HALF_TIME_FULL_TIME", "MATCH"),
    "Total": ("TOTAL", "MATCH"),
    "1st Half Total": ("TOTAL", "MT1"),
    "Home Team Total Goals": ("TOTAL_DOM", "MATCH"),
    "Away Team Total Goals": ("TOTAL_EXT", "MATCH"),
    "Handicap": ("HANDICAP", "MATCH"),
    "Moneyline": ("VAINQUEUR", "MATCH"),
}
# au tennis, totaux et handicaps sont en jeux
TENNIS = {"TOTAL": "JEUX_TOTAL", "HANDICAP": "JEUX_HANDICAP"}
MODES = ("off", "shadow", "direct")


def mode(environ=None) -> str:
    """``direct`` si la variable est absente ou inconnue : les cotes doivent arriver."""
    env = os.environ if environ is None else environ
    valeur = env.get("SOURCE_MATCHBOOK", "direct").strip().lower()
    return valeur if valeur in MODES else "direct"


def hors_consensus() -> frozenset[str]:
    """Matchbook a sa table de paris. Il ne change pas la moyenne des autres références."""
    return HORS_CONSENSUS


def _heure(v):
    try:
        t = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return t.astimezone(timezone.utc) if t.tzinfo else None
    except (TypeError, ValueError):
        return None


def _nombre(v):
    if v is None or isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


class Client:
    """GET espacés, sans identifiant. Un 401/403/429 coupe la lecture. Le corps n'est pas journalisé."""

    def __init__(self, session=None, pause=(0.3, 0.6), echeance=None):
        self.session = session or requests.Session()
        self.pause, self.echeance = pause, echeance
        self.requetes, self.erreurs, self.bloque, self._premier = 0, [], False, True

    def _noter(self, m):
        if m not in self.erreurs:
            self.erreurs.append(m)

    def get(self, chemin: str, params: dict):
        if self.bloque:
            return None
        dernier = "réseau"
        for essai in range(3):
            if self.echeance is not None and not self.echeance.ok():
                self.bloque = True
                self._noter("budget")
                return None
            if not self._premier:
                time.sleep(random.uniform(*self.pause))
            self._premier = False
            self.requetes += 1
            try:
                r = self.session.get(f"{BASE}/{chemin.lstrip('/')}", params=params, timeout=30,
                                     headers={"Accept": "application/json", "Accept-Encoding": "gzip",
                                              "User-Agent": "cotes-value/1.0"})
            except (requests.RequestException, OSError):
                dernier = "réseau"
                time.sleep(0.5 * (essai + 1))
                continue
            if r.status_code in (401, 403, 429):
                # 401 : l'API demanderait une session ; 403 : blocage ; 429 : quota.
                # Le corps (page Cloudflare, message) n'est jamais repris.
                self.bloque = True
                self._noter(f"HTTP {r.status_code}")
                return None
            if r.status_code in (500, 502, 503, 504):
                dernier = f"HTTP {r.status_code}"
                time.sleep(0.5 * (essai + 1))
                continue
            if r.status_code != 200:
                self._noter(f"HTTP {r.status_code}")
                return None
            try:
                doc = r.json()
            except ValueError:
                self._noter("JSON invalide")
                return None
            return doc if isinstance(doc, dict) else None
        self._noter(dernier)
        return None


def _equipes(event: dict):
    nom = str(event.get("name") or "")
    if " vs " not in nom:
        return None, None
    a, b = nom.split(" vs ", 1)
    return a.strip() or None, b.strip() or None


def _meme(a: str, b: str) -> bool:
    return (a or "").strip().lower() == (b or "").strip().lower()


def _carnet(runner: dict):
    backs = [p for p in runner.get("prices") or [] if p.get("side") == "back" and (_nombre(p.get("odds")) or 0) > 1]
    lays = [p for p in runner.get("prices") or [] if p.get("side") == "lay" and (_nombre(p.get("odds")) or 0) > 1]
    if not backs or not lays:
        return None
    b = max(backs, key=lambda p: float(p["odds"]))
    v = min(lays, key=lambda p: float(p["odds"]))
    if not float(b["odds"]) <= float(v["odds"]):
        return None
    return ({"price": round(float(b["odds"]), 4), "liquidity": round(_nombre(b.get("available-amount")) or 0, 2)},
            {"price": round(float(v["odds"]), 4), "liquidity": round(_nombre(v.get("available-amount")) or 0, 2)})


_QUART = re.compile(r"\(([+-]?)(\d+(?:\.\d+)?)/(\d+(?:\.\d+)?)\)\s*$")


def _handicap_runner(runner: dict) -> float | None:
    h = _nombre(runner.get("handicap"))
    if h is not None:
        return h
    m = _QUART.search(str(runner.get("name") or ""))       # « Lille OSC (-0.5/1.0) » = -0,75
    if not m:
        return None
    signe = -1 if m.group(1) == "-" else 1
    return signe * (float(m.group(2)) + float(m.group(3))) / 2


def _issue(interne: str, nom: str, dom: str, ext: str):
    n = (nom or "").strip()
    bas = n.lower()
    if interne in ("RESULTAT_1N2", "VAINQUEUR", "DRAW_NO_BET"):
        if bas == "draw":
            return "NUL" if interne == "RESULTAT_1N2" else None
        return "DOM" if _meme(n, dom) else "EXT" if _meme(n, ext) else None
    if interne == "DOUBLE_CHANCE":
        a, _, b = n.partition(" or ")
        cle = {_cote(a, dom, ext), _cote(b, dom, ext)}
        return {frozenset({"DOM", "NUL"}): "HOME_DRAW", frozenset({"DOM", "EXT"}): "HOME_AWAY",
                frozenset({"NUL", "EXT"}): "DRAW_AWAY"}.get(frozenset(cle))
    if interne == "BOTH_TEAMS_TO_SCORE":
        return {"yes": "YES", "no": "NO"}.get(bas)
    if interne == "CORRECT_SCORE":
        return n if re.fullmatch(r"\d+-\d+", n) else None
    if interne == "HALF_TIME_FULL_TIME":
        a, _, b = n.partition("/")
        x, y = _cote(a, dom, ext), _cote(b, dom, ext)
        return f"{x}/{y}" if x and y else None
    if interne.endswith("TOTAL") or interne.startswith("TOTAL"):
        return "PLUS" if bas.startswith("over") else "MOINS" if bas.startswith("under") else None
    if interne.endswith("HANDICAP"):
        return "DOM" if bas.startswith(dom.lower()) else "EXT" if bas.startswith(ext.lower()) else None
    return None


def _cote(nom: str, dom: str, ext: str):
    n = (nom or "").strip()
    if n.lower() == "draw":
        return "NUL"
    return "DOM" if _meme(n, dom) else "EXT" if _meme(n, ext) else None


def _ligue(ev: dict):
    for t in ev.get("meta-tags") or []:
        if isinstance(t, dict) and t.get("type") == "COMPETITION":
            return t.get("name")
    return None


def lignes_brutes(events: list, sport: str, maintenant: datetime, heures: float = 36) -> list[dict]:
    """Événements Matchbook -> lignes achat/vente au format du dépôt (avant cote juste)."""
    moment = maintenant.isoformat(timespec="seconds")
    horizon = maintenant + timedelta(hours=heures)
    out = []
    for ev in events or []:
        if not isinstance(ev, dict) or ev.get("in-running-flag") or ev.get("status") not in (None, "open"):
            continue
        debut = _heure(ev.get("start"))
        dom, ext = _equipes(ev)
        if debut is None or not dom or not ext or not (maintenant < debut <= horizon):
            continue
        for m in ev.get("markets") or []:
            regle = MARCHES_NOM.get(str(m.get("name") or ""))
            if not regle or m.get("status") not in (None, "open"):
                continue
            interne, periode = regle
            if sport == "tennis":
                interne = TENNIS.get(interne, interne)
            runners = [r for r in m.get("runners") or [] if not r.get("withdrawn") and r.get("status") in (None, "open")]
            ligne = None
            if "TOTAL" in interne:
                ligne = _nombre(m.get("handicap"))
                if ligne is None and runners:
                    ligne = _nombre(runners[0].get("handicap"))
                if ligne is None:
                    continue
            elif interne.endswith("HANDICAP"):
                domicile = [r for r in runners if str(r.get("name") or "").lower().startswith(dom.lower())]
                ligne = _handicap_runner(domicile[0]) if domicile else None
                if ligne is None:
                    continue
            base = {"source": NOM_SOURCE, "bookmaker": "matchbook", "sport": sport, "ligue": _ligue(ev),
                    "match_id": f"matchbook|{ev.get('id')}", "domicile": dom, "exterieur": ext,
                    "debut": debut.isoformat(), "collecte": moment, "joueur": None,
                    "cle_marche": f"matchbook|{m.get('id')}", "marche": interne, "periode": periode,
                    "ligne": ligne, "libelle": m.get("name")}
            for r in runners:
                issue = _issue(interne, r.get("name"), dom, ext)
                if not issue:
                    continue
                carnet = _carnet(r)
                if not carnet:
                    out.append({**base, "issue": issue, "achat": [], "vente": []})
                    continue
                out.append({**base, "issue": issue, "achat": [carnet[0]], "vente": [carnet[1]],
                            "maj_bookmaker": r.get("last-price-update-time")})
    return out


def collecter(sports: set[str] | None = None, heures: float = 36, session=None,
              maintenant: datetime | None = None, echeance=None, environ=None, pause=(0.3, 0.6)):
    """Une requête par sport (deux si plus de 200 matchs dans l'horizon)."""
    maintenant = maintenant or datetime.now(timezone.utc)
    actif = mode(environ)
    if actif == "off":
        return [], {"ok": True, "requetes": 0, "erreurs": [], "matchs": 0, "mode": "off"}
    client = Client(session, pause=pause, echeance=echeance if echeance is not None else _echeance)
    avant = int((maintenant + timedelta(hours=heures)).timestamp())
    bruts, matchs = [], 0
    for sid, sport in SPORTS.items():
        if sports is not None and sport not in sports:
            continue
        offset = 0
        for _ in range(3):
            doc = client.get("events", {"sport-ids": sid, "states": "open", "per-page": 200, "offset": offset,
                                        "before": avant, "include-prices": "true", "price-depth": 1,
                                        "exchange-type": "back-lay", "odds-type": "DECIMAL"})
            if doc is None:
                break
            evs = doc.get("events") or []
            matchs += len(evs)
            bruts += lignes_brutes(evs, sport, maintenant, heures)
            offset += 200
            if offset >= int(doc.get("total") or 0) or not evs:
                break
        if client.bloque:
            break
    from cotes.comparaison import reference_echange
    justes = reference_echange(bruts, NOM_SOURCE)
    return justes, {"ok": not client.erreurs or bool(justes), "requetes": client.requetes,
                    "erreurs": list(client.erreurs), "matchs": matchs, "mode": actif}
