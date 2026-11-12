"""Durée des opportunités et cause de leur disparition.

Une opportunité est la même sélection (bookmaker, match, marché, période, ligne, issue, joueur) contre la même
référence, présente à des cycles consécutifs de ``opportunites/``. Un épisode commence au premier cycle où elle
apparaît et finit au premier cycle où elle n'est plus là (le « cycle de fin »).

Durée : un intervalle, pas une valeur exacte. Au moins (dernier cycle vu − premier), au plus (cycle de fin −
premier). Sans cycle de fin observé (fin des données), la durée maximale est inconnue (``dmax`` = None, cause
« en_cours ») : elle n'est jamais inventée.

Cause de la disparition, au cycle de fin :

- ``match_commence`` : le match a commencé ;
- ``bookmaker`` : la cote du bookmaker a changé (ou a été retirée) d'après ``cotes/`` ;
- ``reference`` : la cote du bookmaker n'a pas bougé, donc la référence a bougé ou n'est plus lisible ;
- ``inconnue`` : ``cotes/`` ne couvre pas ce bookmaker à ce moment (OlyBet, Winamax avant le 10/11, journées
  Unibet bloquées) : sa cote au dernier cycle vu n'y est pas retrouvée.

Les cycles connus sont ceux de ``opportunites/`` (un cycle sans aucune opportunité n'y laisse pas de trace) et,
depuis le 12/11/2026, ceux de ``releves/``. Lignes sans ``cycle_id`` (avant le 20/10/2026) : écartées.
"""
from __future__ import annotations

import json
from bisect import bisect_right
from datetime import datetime, timedelta

from ..historique_cotes import texte_cle
from . import lecture as L

LECTURE_CYCLE = timedelta(minutes=3)      # les cotes d'un cycle sont lues dans les 3 minutes qui suivent son début
TOLERANCE_COTE = 0.011
JOURS_AVANT = 3                           # une cote inchangée depuis plus de 3 jours : couverture « inconnue »


def cle_opportunite(o: dict) -> tuple:
    return (o.get("bookmaker"), o.get("match_id"), o.get("marche"), o.get("periode"), o.get("ligne"),
            o.get("issue"), o.get("joueur"), o.get("reference"))


def _cycle(o: dict) -> datetime | None:
    """Début du cycle. Avant le 20/10/2026 les lignes n'en ont pas (``detecte`` varie d'une ligne à l'autre dans un
    même cycle) : elles sont écartées, les cycles n'y sont pas reconstituables avec certitude."""
    return L.t(o.get("cycle_id"))


def lire_cycles(donnees, jours: list[str]) -> tuple[dict[tuple, dict], dict[tuple, dict], list[datetime]]:
    """(première ligne de chaque opportunité, {cycle: cote du bookmaker} où elle est présente, cycles triés)."""
    premieres: dict[tuple, dict] = {}
    presences: dict[tuple, dict] = {}
    cycles: set = set()
    for j in jours:
        for o in L.lire(L.chemin(donnees, "opportunites", j)):
            c = _cycle(o)
            if c is None:
                continue
            cycles.add(c)
            cle = cle_opportunite(o)
            presences.setdefault(cle, {})[c] = o.get("cote")
            if cle not in premieres or c < _cycle(premieres[cle]):
                premieres[cle] = o
        for r in L.lire(L.chemin(donnees, "releves", j)):
            c = L.t(r.get("t"))
            if c is not None:
                cycles.add(c)
    return premieres, presences, sorted(cycles)


def episodes_bruts(presences: dict[tuple, dict], cycles: list[datetime]) -> list[tuple[tuple, int, int]]:
    """(clé, indice du premier cycle, indice du dernier cycle vu) de chaque suite de cycles consécutifs."""
    rang = {c: i for i, c in enumerate(cycles)}
    out = []
    for cle, vus in presences.items():
        indices = sorted(rang[c] for c in vus)
        debut = prec = indices[0]
        for i in indices[1:]:
            if i != prec + 1:
                out.append((cle, debut, prec))
                debut = i
            prec = i
        out.append((cle, debut, prec))
    return out


def _filtre_matchs(mids: set):
    """Filtre texte rapide : la ligne d'historique concerne-t-elle un de ces matchs ?"""
    cibles = {json.dumps(m, ensure_ascii=False) for m in mids}

    def garder(brut: str) -> bool:
        i = brut.find('"m":')
        if i < 0 or '"k"' not in brut:
            return False
        j = brut.find(',"', i + 4)
        return brut[i + 4:j if j >= 0 else None] in cibles
    return garder


def series_bookmakers(donnees, cles: set[tuple], jours: list[str]) -> dict[tuple, tuple[list, list]]:
    """{(bookmaker, match, clé texte): ([heures], [cotes ou None])} triées, sur les jours demandés."""
    brut: dict[tuple, list] = {c: [] for c in cles}
    filtre = _filtre_matchs({c[1] for c in cles})
    for j in jours:
        for d in L.lire(L.chemin(donnees, "cotes", j), filtre):
            cle = (d.get("b"), d.get("m"), d.get("k"))
            if cle in brut:
                h = L.t(d.get("t"))
                c = d.get("c")
                if h is not None and (c is None or (isinstance(c, (int, float)) and not isinstance(c, bool))):
                    brut[cle].append((h, c))
    out = {}
    for cle, s in brut.items():
        s.sort(key=lambda x: x[0])
        out[cle] = ([h for h, _ in s], [c for _, c in s])
    return out


def valeur(serie: tuple[list, list] | None, avant: datetime):
    """(trouvée ?, dernière cote relevée strictement avant ``avant``)."""
    if not serie or not serie[0]:
        return False, None
    i = bisect_right(serie[0], avant - timedelta(microseconds=1))
    return (True, serie[1][i - 1]) if i else (False, None)


def cause(o: dict, cote, serie, fin: datetime | None, apres_fin: datetime | None) -> str:
    """Cause de la disparition ; ``cote`` : cote du bookmaker au dernier cycle vu."""
    if fin is None:
        return "en_cours"
    debut = L.t(o.get("debut"))
    if debut is not None and debut <= fin:
        return "match_commence"
    vu, v_avant = valeur(serie, fin)
    if not vu or v_avant is None or not isinstance(cote, (int, float)) or abs(v_avant - cote) > TOLERANCE_COTE:
        return "inconnue"
    borne = fin + LECTURE_CYCLE
    if apres_fin is not None:
        borne = min(borne, apres_fin)
    _, v_apres = valeur(serie, borne)
    return "reference" if v_apres == v_avant else "bookmaker"


def _minutes(a: datetime, b: datetime) -> float:
    return round((b - a).total_seconds() / 60, 1)


def episodes_du_jour(donnees, jour: str) -> list[dict]:
    """Épisodes commencés le jour ``jour`` (UTC), lus sur la veille, le jour et le lendemain."""
    premieres, presences, cycles = lire_cycles(donnees, [L.decaler(jour, -1), jour, L.decaler(jour, 1)])
    bruts = [e for e in episodes_bruts(presences, cycles) if cycles[e[1]].date().isoformat() == jour]
    cles_hist = {(e[0][0], e[0][1], texte_cle(*e[0][2:7])) for e in bruts}
    series = series_bookmakers(donnees, cles_hist,
                               [L.decaler(jour, d) for d in range(-JOURS_AVANT, 2)]) if cles_hist else {}
    out = []
    for cle, i0, i1 in bruts:
        o = premieres[cle]
        t0, dernier = cycles[i0], cycles[i1]
        fin = cycles[i1 + 1] if i1 + 1 < len(cycles) else None
        apres_fin = cycles[i1 + 2] if i1 + 2 < len(cycles) else None
        debut = L.t(o.get("debut"))
        out.append({
            "b": o.get("bookmaker"), "ref": o.get("reference"), "sport": o.get("sport"), "ligue": o.get("ligue"),
            "marche": o.get("marche"), "periode": o.get("periode"), "m": o.get("match_id"),
            "k": texte_cle(*cle[2:7]), "t0": t0.isoformat(timespec="seconds"),
            "dmin": _minutes(t0, dernier), "dmax": _minutes(t0, fin) if fin else None,
            "cause": cause(o, presences[cle][dernier], series.get((cle[0], cle[1], texte_cle(*cle[2:7]))), fin,
                           apres_fin),
            "delai_h": round((debut - t0).total_seconds() / 3600, 2) if debut else None,
            "ecart": o.get("ecart"), "pariable": o.get("pariable"),
            "debut_connu": i0 > 0,        # premier cycle de la fenêtre : l'opportunité existait peut-être avant
        })
    out.sort(key=lambda e: (e["t0"], str(e["b"]), str(e["m"]), e["k"], str(e["ref"])))
    return out
