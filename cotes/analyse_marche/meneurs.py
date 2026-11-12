"""Qui bouge en premier entre bookmakers français, sur la même sélection.

Sources : ``cotes/`` seul. Les matchs de deux bookmakers sont rapprochés par équipes, sport et heure de début
(cotes/correspondance.py, comme pendant la collecte), d'après les lignes descriptives de l'historique. Les
rapprochements où domicile et extérieur sont inversés sont écartés (issues et lignes à retourner).

Un mouvement est un changement de cote d'au moins ``SEUIL_PROBA`` en probabilité implicite (1/cote), entre deux
cotes connues. Pour chaque paire de bookmakers et chaque sélection commune, chaque mouvement est apparié au
mouvement de même sens le plus proche chez l'autre, à ``FENETRE`` près, un mouvement ne servant qu'une fois :

- écart de lecture de moins de ``SIMULTANE`` : « ensemble » (même cycle de collecte) ;
- sinon le premier lu « mène », le délai du suiveur est noté (en minutes, à un cycle près) ;
- sans appariement : « seul ». Sans relevé des sources (avant le 12/11/2026), on ne sait pas si l'autre
  bookmaker était lu à ce moment : ce compte est indicatif.

Marchés retenus : ceux que tous les bookmakers proposent (``MARCHES``), hors props.
"""
from __future__ import annotations

import json
from datetime import timedelta
from itertools import combinations

from .. import correspondance as C
from . import lecture as L

FRANCAIS = ("PMU", "Betclic", "Unibet", "Winamax", "NetBet", "OlyBet")
MARCHES = ("RESULTAT_1N2", "VAINQUEUR", "TOTAL", "HANDICAP", "BOTH_TEAMS_TO_SCORE")
SEUIL_PROBA = 0.01
FENETRE = timedelta(minutes=30)
SIMULTANE = timedelta(minutes=2)
JOURS_CATALOGUE = 7


def catalogue(donnees, jour: str) -> dict[str, dict[str, dict]]:
    """{bookmaker: {match: résumé au format correspondance.matchs_de}} des matchs décrits la semaine passée."""
    out: dict[str, dict[str, dict]] = {}
    for d in range(-JOURS_CATALOGUE, 1):
        for x in L.lire(L.chemin(donnees, "cotes", L.decaler(jour, d)), lambda brut: '"k"' not in brut):
            b, mid, debut = x.get("b"), x.get("m"), L.t(x.get("debut"))
            if b not in FRANCAIS or mid is None or debut is None or not x.get("dom") or not x.get("ext"):
                continue
            out.setdefault(b, {})[mid] = {"match_id": mid, "sport": x.get("sport"), "domicile": x["dom"],
                                          "exterieur": x["ext"], "debut": debut, "approx": False,
                                          "ordre_incertain": False, "ligue": x.get("ligue")}
    return out


def paires_de_matchs(cat: dict[str, dict[str, dict]], jour: str) -> dict[tuple[str, str], dict]:
    """{(bookmaker A, bookmaker B): {match A: match B}} pour les matchs qui commencent entre la veille et J+3."""
    bas, haut = L.t(f"{L.decaler(jour, -1)}T00:00:00+00:00"), L.t(f"{L.decaler(jour, 4)}T00:00:00+00:00")
    utiles = {b: {m: r for m, r in ms.items() if bas <= r["debut"] < haut} for b, ms in cat.items()}
    out = {}
    for a, b in combinations(sorted(utiles), 2):
        assoc = C.associer(utiles[a], utiles[b]) if utiles[a] and utiles[b] else {}
        out[(a, b)] = {ma: mb for ma, (mb, inverse, _) in assoc.items() if not inverse}
    return out


def _filtre(mids: set):
    cibles = {json.dumps(m, ensure_ascii=False) for m in mids}
    prefixes = tuple(f'"k":"{m}|' for m in MARCHES)

    def garder(brut: str) -> bool:
        i = brut.find('"m":')
        if i < 0 or not any(p in brut for p in prefixes):
            return False
        j = brut.find(',"', i + 4)
        return brut[i + 4:j if j >= 0 else None] in cibles
    return garder


def mouvements(donnees, jour: str, matchs: dict[str, set]) -> tuple[dict[tuple, list[tuple]], set[tuple]]:
    """({(bookmaker, match, clé): [(heure, +1 hausse de cote / -1 baisse, écart de probabilité)]} du jour,
    sélections relevées la veille ou le jour, qu'elles aient bougé ou non)."""
    series: dict[tuple, list] = {}
    tous = set().union(*matchs.values()) if matchs else set()
    if not tous:
        return {}, set()
    for j in (L.decaler(jour, -1), jour):
        for d in L.lire(L.chemin(donnees, "cotes", j), _filtre(tous)):
            b, mid, k = d.get("b"), d.get("m"), d.get("k")
            if mid not in matchs.get(b, ()) or not isinstance(k, str) or k.count("|") != 3:
                continue
            h, c = L.t(d.get("t")), d.get("c")
            if h is not None and (c is None or (isinstance(c, (int, float)) and not isinstance(c, bool) and c > 1)):
                series.setdefault((b, mid, k), []).append((h, c))
    out: dict[tuple, list] = {}
    for cle, s in series.items():
        s.sort(key=lambda x: x[0])
        ev = []
        for (_, c1), (h2, c2) in zip(s, s[1:]):
            if c1 is None or c2 is None or h2.date().isoformat() != jour:
                continue
            dp = 1 / c2 - 1 / c1
            if abs(dp) >= SEUIL_PROBA:
                ev.append((h2, 1 if dp < 0 else -1, round(abs(dp), 4)))
        if ev:
            out[cle] = ev
    return out, set(series)


def apparier(ea: list[tuple], eb: list[tuple]) -> tuple[list[tuple[tuple, tuple]], list[tuple], list[tuple]]:
    """(paires (mouvement A, mouvement B), seuls chez A, seuls chez B) : plus proches d'abord, même sens."""
    candidats = sorted((abs((b[0] - a[0]).total_seconds()), i, j) for i, a in enumerate(ea)
                       for j, b in enumerate(eb) if a[1] == b[1] and abs(b[0] - a[0]) <= FENETRE)
    pris_a, pris_b, paires = set(), set(), []
    for _, i, j in candidats:
        if i not in pris_a and j not in pris_b:
            pris_a.add(i)
            pris_b.add(j)
            paires.append((ea[i], eb[j]))
    return (paires, [e for i, e in enumerate(ea) if i not in pris_a],
            [e for j, e in enumerate(eb) if j not in pris_b])


def meneurs_du_jour(donnees, jour: str) -> list[dict]:
    """Un enregistrement par mouvement apparié ou seul, pour les mouvements lus le jour ``jour`` (UTC)."""
    cat = catalogue(donnees, jour)
    paires = paires_de_matchs(cat, jour)
    matchs: dict[str, set] = {}
    for (a, b), m in paires.items():
        matchs.setdefault(a, set()).update(m)
        matchs.setdefault(b, set()).update(m.values())
    ev, presentes = mouvements(donnees, jour, matchs)
    par_match: dict[tuple, dict[str, list]] = {}
    for (bk, mid, k), e in ev.items():
        par_match.setdefault((bk, mid), {})[k] = e
    out = []
    for (a, b), m in sorted(paires.items()):
        for ma, mb in m.items():
            sa, sb = par_match.get((a, ma), {}), par_match.get((b, mb), {})
            if not sa and not sb:
                continue
            r = cat[a][ma]
            debut = r["debut"]
            # sélection relevée chez les deux et qui a bougé chez au moins l'un
            for k in sorted(k for k in set(sa) | set(sb) if (a, ma, k) in presentes and (b, mb, k) in presentes):
                appariees, seuls_a, seuls_b = apparier(sa.get(k, []), sb.get(k, []))
                base = {"a": a, "b": b, "sport": r["sport"], "ligue": r.get("ligue"), "marche": k.split("|")[0],
                        "periode": k.split("|")[1]}
                for x, y in appariees:
                    dt = (y[0] - x[0]).total_seconds()
                    meneur = "ensemble" if abs(dt) < SIMULTANE.total_seconds() else (a if dt > 0 else b)
                    out.append({**base, "meneur": meneur, "delai_min": round(abs(dt) / 60, 1),
                                "t": min(x[0], y[0]).isoformat(timespec="seconds"),
                                "delai_h": round((debut - min(x[0], y[0])).total_seconds() / 3600, 2)})
                for qui, seuls in ((a, seuls_a), (b, seuls_b)):
                    for x in seuls:
                        out.append({**base, "meneur": None, "seul": qui, "delai_min": None,
                                    "t": x[0].isoformat(timespec="seconds"),
                                    "delai_h": round((debut - x[0]).total_seconds() / 3600, 2)})
    return out
