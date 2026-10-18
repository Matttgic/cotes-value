"""Résultats Flashscore, pour les sports qu'aucune autre source gratuite ne couvre (volley, handball, rugby).

Flux texte de l'application web, un fichier par sport et par jour (UTC), 7 jours en arrière au plus. Le jeton
d'en-tête est celui du site (public, dans son JavaScript) : ce n'est ni une clé ni un compte. Source non
officielle, qui peut changer sans préavis ; elle ne vaut qu'en accord avec une autre source, ou seule après
24 h (voir cotes/resultats.py).

Seuls les matchs terminés normalement (statut détaillé 3) sont gardés : prolongation, tirs au but, forfait,
match donné gagnant sur tapis vert, abandon et report ne donnent pas un score de jeu fiable.
Volley : sets gagnés, points de chaque set. Handball et rugby : score final, mi-temps.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import requests

BASE = "https://www.flashscore.fr/x/feed"
ENTETES = {"x-fsign": "SW9D1eZo", "x-requested-with": "XMLHttpRequest", "referer": "https://www.flashscore.fr/",
           "User-Agent": "Mozilla/5.0"}
SPORTS = {"football": 1, "tennis": 2, "basket": 3, "hockey": 4, "football_americain": 5, "baseball": 6,
          "handball": 7, "rugby": 8, "volley": 12}
HISTORIQUE_J = 7
ERREURS: list[str] = []


def _entier(v) -> int | None:
    try:
        n = int(str(v))
    except (TypeError, ValueError):
        return None
    return n if n >= 0 else None


def lignes(texte: str):
    """Les matchs du flux : dictionnaires clé -> valeur."""
    for bloc in texte.split("~"):
        if bloc.startswith("AA÷"):
            yield dict(kv.split("÷", 1) for kv in bloc.split("¬") if "÷" in kv)


def match(sport: str, d: dict) -> dict | None:
    if d.get("AB") != "3" or d.get("AC") != "3":
        return None
    try:
        debut = datetime.fromtimestamp(int(d["AD"]), timezone.utc)
    except (KeyError, ValueError, OSError):
        return None
    score = (_entier(d.get("AG")), _entier(d.get("AH")))
    dom, ext = d.get("AE"), d.get("AF")
    if None in score or not dom or not ext:
        return None
    periodes = []
    for a, b in (("BA", "BB"), ("BC", "BD"), ("BE", "BF"), ("BG", "BH"), ("BI", "BJ")):
        x, y = _entier(d.get(a)), _entier(d.get(b))
        if x is None or y is None:
            break
        periodes.append((x, y))
    if sport == "volley":
        # sets gagnés : doivent se déduire des points de chaque set, sinon le détail est inutilisable
        if periodes and (sum(a > b for a, b in periodes), sum(b > a for a, b in periodes)) != score:
            periodes = []
        libelles = [str(i + 1) for i in range(len(periodes))]
    else:
        # Un match terminé normalement n'a pas de prolongation : ses périodes réglementaires font le score
        attendu = {"hockey": 3, "basket": 4, "football_americain": 4}.get(sport, 2)
        if periodes and (len(periodes) != attendu or (sum(a for a, _ in periodes), sum(b for _, b in periodes)) != score):
            periodes = []                          # détail absent ou différent du score : le score final suffit
        libelles = [str(i + 1) for i in range(len(periodes))]
    return {"source": "flashscore", "id_source": d.get("AA"), "sport": sport, "domicile": dom, "exterieur": ext, "debut": debut,
            "score": score, "periodes": periodes, "libelles": libelles, "corners": None, "abandon": False}


def lire(sport: str, jours: list[str], maintenant: datetime | None = None, http=requests) -> list[dict]:
    """Matchs terminés de ces jours (AAAA-MM-JJ, UTC)."""
    maintenant = maintenant or datetime.now(timezone.utc)
    identifiant = SPORTS.get(sport)
    out = []
    for jour in sorted(set(jours)):
        decalage = (datetime.strptime(jour, "%Y-%m-%d").date() - maintenant.date()).days
        if decalage > 0 or decalage < -HISTORIQUE_J:
            continue
        try:
            r = http.get(f"{BASE}/f_{identifiant}_{decalage}_0_fr-fr_1", headers=ENTETES, timeout=40)
            if not r.ok:
                raise ValueError(f"HTTP {r.status_code}")
            if "AA÷" not in r.text and len(r.text) > 5:
                raise ValueError("format inattendu")
        except (requests.RequestException, ValueError) as ex:
            ERREURS.append(f"{sport} {jour} : {repr(ex)[:120]}")
            continue
        for d in lignes(r.text):
            m = match(sport, d)
            if m:
                out.append(m)
    return out


def jours_a_lire(paris: list[dict], maintenant: datetime) -> dict[str, list[str]]:
    """Sport -> jours UTC (le jour du match et la veille) des paris ouverts commencés depuis 2 h,
    dans les HISTORIQUE_J jours que le flux permet de relire."""
    out: dict[str, set[str]] = {}
    for p in paris:
        if p.get("statut") not in ("en_cours", "a_regler") or p.get("sport") not in SPORTS:
            continue
        try:
            debut = datetime.fromisoformat(str(p.get("reporte_au") or p.get("debut")).replace("Z", "+00:00"))
        except ValueError:
            continue
        if debut.tzinfo is None or not timedelta(hours=2) < maintenant - debut < timedelta(days=HISTORIQUE_J):
            continue
        for k in (0, -1):
            jour = (debut + timedelta(days=k)).date()
            if (maintenant.date() - jour).days <= HISTORIQUE_J:
                out.setdefault(p["sport"], set()).add(jour.isoformat())
    return {sport: sorted(jours) for sport, jours in out.items()}
