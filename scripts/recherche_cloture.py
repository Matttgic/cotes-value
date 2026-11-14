"""Peut-on prédire la clôture Pinnacle ? Tests hors échantillon (docs/recherche.md). Lecture seule, numpy seul.

    python scripts/recherche_cloture.py --donnees donnees --football fd

``--donnees`` : branche « donnees » complète (paris.json, archives/, cotes/, references/, correspondances/).
``--football`` : dossier des CSV de football-data.co.uk nommés ``SAISON-DIVISION.csv`` (p. ex. ``2425-E0.csv``),
comme pour scripts/cote_juste.py. Sans lui, la partie football est sautée.

Quatre parties, chacune apprise sur une période et jugée sur une période plus récente, jamais vue :

1. football-data : relevé d'avant-match -> clôture Pinnacle (1N2, total 2,5). Appris jusqu'à 2023-24, testé ensuite.
2. paris du projet (référence Pinnacle, première détection) : détection -> clôture. Appris avant le 1/11, testé après.
3. attendre : le même pari pris plus tard chez le même bookmaker (historique cotes/), contre la même clôture.
4. historique des références : élan de Pinnacle et écart aux autres références. Appris avant le 14/11, testé le 14/11.

« Mouvement » = logit(proba juste à la clôture) − logit(proba juste au relevé) ; pour les paris du projet, le
logarithme du rapport des deux probas. R² hors échantillon = 1 − erreur du
modèle / erreur de « la cote ne bouge pas » (0 = n'apporte rien, négatif = pire). Intervalles : bootstrap par match.
"""
from __future__ import annotations

import argparse
import bisect
import csv
import gzip
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cotes import simulation, stockage  # noqa: E402
from cotes.convergence import cle_selection  # noqa: E402
from cotes.marge import proba_justes  # noqa: E402
from cotes.temps import instant_utc  # noqa: E402

GRAINE = 20261114
COUPURE_PARIS = "2026-11-01"          # paris : appris avant, testé à partir de cette date de détection
COUPURE_REFERENCES = "2026-11-14"     # références : appris sur les matchs d'avant, testé sur ceux de ce jour
SAISON_TEST = "2425"                  # football : testé à partir de cette saison
COTE_MAX = 5.0
MARCHES_REF = ("VAINQUEUR|MATCH|", "RESULTAT_1N2|MATCH|", "TOTAL|MATCH|", "HANDICAP|MATCH|")


# ---------------------------------------------------------------- outils

def logit(p: float) -> float:
    return math.log(p / (1 - p))


def ajuster(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Moindres carrés avec constante. ``x`` : (n, k)."""
    return np.linalg.lstsq(np.c_[np.ones(len(x)), x], y, rcond=None)[0]


def predire(b: np.ndarray, x: np.ndarray) -> np.ndarray:
    return np.c_[np.ones(len(x)), x] @ b


def _grappes(cles) -> tuple[int, np.ndarray]:
    u, inv = np.unique(np.asarray([str(c) for c in cles]), return_inverse=True)
    return len(u), inv


def r2_hors_echantillon(y, prevu, base, cles, rng, tirages: int) -> tuple[float, float, float]:
    """1 − Σ(y − prévu)² / Σ(y − base)², et son intervalle à 95 % (bootstrap des matchs entiers)."""
    y, prevu = np.asarray(y, float), np.asarray(prevu, float)
    n, inv = _grappes(cles)
    a, c = np.bincount(inv, (y - prevu) ** 2, n), np.bincount(inv, (y - base) ** 2, n)
    i = rng.integers(0, n, (tirages, n))
    r = 1 - a[i].sum(1) / c[i].sum(1)
    return 1 - a.sum() / c.sum(), float(np.quantile(r, 0.025)), float(np.quantile(r, 0.975))


def moyenne(v, cles, rng, tirages: int) -> tuple[float, float, float]:
    """Moyenne et intervalle à 95 % (bootstrap des matchs entiers)."""
    v = np.asarray(v, float)
    n, inv = _grappes(cles)
    s, c = np.bincount(inv, v, n), np.bincount(inv, minlength=n)
    i = rng.integers(0, n, (tirages, n))
    r = s[i].sum(1) / c[i].sum(1)
    return float(v.mean()), float(np.quantile(r, 0.025)), float(np.quantile(r, 0.975))


def bon_sens(y: np.ndarray, prevu: np.ndarray, part: float = 1.0) -> float:
    """Part des mouvements dont le sens est bien prévu, parmi la part ``part`` des prévisions les plus fortes."""
    garde = (y != 0) & (np.abs(prevu) >= np.quantile(np.abs(prevu), 1 - part))
    return float((np.sign(prevu[garde]) == np.sign(y[garde])).mean()) if garde.any() else float("nan")


def pct(x, d=2) -> str:
    return "—" if x is None or not math.isfinite(x) else f"{100 * x:+.{d}f} %".replace(".", ",")


def ic(t, d=2) -> str:
    return f"{pct(t[0], d)} [{100 * t[1]:+.{d}f} ; {100 * t[2]:+.{d}f}]".replace(".", ",")


def r2txt(t) -> str:
    return f"{100 * t[0]:+.1f} % [{100 * t[1]:+.1f} ; {100 * t[2]:+.1f}]".replace(".", ",")


def tableau(entetes: list[str], lignes: list[list]) -> str:
    out = ["| " + " | ".join(entetes) + " |", "|" + "---|" * len(entetes)]
    return "\n".join(out + ["| " + " | ".join(str(c) for c in l) + " |" for l in lignes]) + "\n"


def essai(nom, app: dict, test: dict, variables: list[str], rng, tirages, base_test=0.0) -> tuple[list, np.ndarray]:
    """Ajuste sur ``app``, juge sur ``test``. Les tables sont des dicts de colonnes numpy avec « y » et « match »."""
    b = ajuster(np.c_[tuple(app[v] for v in variables)], app["y"])
    prevu = predire(b, np.c_[tuple(test[v] for v in variables)])
    y = test["y"]
    ligne = [nom, len(app["y"]), len(y), r2txt(r2_hors_echantillon(y, prevu, base_test, test["match"], rng, tirages)),
             f"{100 * bon_sens(y, prevu):.0f} %", f"{100 * bon_sens(y, prevu, 0.1):.0f} %",
             " ; ".join(f"{c:+.2f}".replace(".", ",") for c in b[1:])]
    return ligne, prevu


def filtrer(t: dict, masque: np.ndarray) -> dict:
    return {k: v[masque] for k, v in t.items()}


def complets(t: dict, variables: list[str]) -> dict:
    return filtrer(t, np.all([np.isfinite(t[v]) for v in variables], axis=0))


def table(lignes: list[dict]) -> dict:
    if not lignes:
        return {}
    return {k: np.array([l[k] for l in lignes], dtype=float if isinstance(lignes[0][k], (int, float)) else object)
            for k in lignes[0]}


ENTETES = ["Variables", "Appris", "Testés", "R² hors échantillon", "Bon sens", "Bon sens, 10 % les plus forts", "Coefficients"]


# ---------------------------------------------------------------- 1. football-data.co.uk

def _cote(x) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) and v > 1.0 else None


def _colonnes(marche: str, book: str, cloture: bool) -> list[str]:
    c = "C" if cloture else ""
    if marche == "1N2":
        return [f"{book}{c}H", f"{book}{c}D", f"{book}{c}A"]
    b = "P" if book == "PS" else book
    return [f"{b}{c}>2.5", f"{b}{c}<2.5"]


def lire_football(dossier: Path) -> dict:
    """Une ligne par issue (1N2 : domicile et extérieur ; total 2,5 : plus), avec le relevé d'avant-match et la clôture.

    Le handicap asiatique est écarté : sa ligne change entre les deux relevés, et ne garder que les matchs où elle
    n'a pas changé revient à choisir d'après l'avenir (les cotes « reviennent » alors vers 2,00 par construction)."""
    lignes = []
    for fichier in sorted(Path(dossier).glob("*.csv")):
        saison, division = fichier.stem.split("-")[:2]
        with open(fichier, encoding="latin-1", newline="") as f:
            brut = list(csv.reader(f))
        if not brut:
            continue
        col = {n.strip().lstrip("﻿").lstrip("ï»¿"): i for i, n in enumerate(brut[0])}
        for num, r in enumerate(brut[1:]):
            lire = lambda noms: [_cote(r[col[n]]) if n in col and col[n] < len(r) else None for n in noms]  # noqa: E731

            def justes(noms):
                c = lire(noms)
                return proba_justes(c) if all(c) and 1.0 <= sum(1 / x for x in c) <= 1.25 else None
            for marche in ("1N2", "TOT"):
                p0, pc = justes(_colonnes(marche, "PS", False)), justes(_colonnes(marche, "PS", True))
                if not p0 or not pc:
                    continue
                autres = {b: justes(_colonnes(marche, b, False)) for b in ("Avg", "B365", "BFE")}
                brutes = {(b, c): lire(_colonnes(marche, b, c)) for b in ("B365", "Max") for c in (False, True)}
                for i in ((0, 2) if marche == "1N2" else (0,)):
                    ecart = lambda b: logit(autres[b][i]) - logit(p0[i]) if autres[b] else math.nan  # noqa: E731
                    lignes.append({
                        "saison": saison, "match": f"{saison}{division}{num}", "marche": marche, "p0": p0[i], "pc": pc[i],
                        "y": logit(pc[i]) - logit(p0[i]), "moyenne": ecart("Avg"), "bet365": ecart("B365"),
                        "betfair": ecart("BFE"), "niveau": logit(p0[i]),
                        "marge": sum(1 / x for x in lire(_colonnes(marche, "PS", False))) - 1,
                        "b0": brutes["B365", False][i] or math.nan, "bc": brutes["B365", True][i] or math.nan,
                        "max0": brutes["Max", False][i] or math.nan, "maxc": brutes["Max", True][i] or math.nan})
    t = table(lignes)
    if t:
        t["meilleur"] = np.log(t["max0"] * t["p0"])            # écart du meilleur prix du marché contre Pinnacle
    return t


def partie_football(dossier: Path, rng, tirages: int) -> str:
    t = lire_football(dossier)
    if not t:
        return "_Aucun fichier football-data._\n"
    saisons = sorted(set(t["saison"]))
    out = [f"Saisons avec cotes Pinnacle : {saisons[0]} à {saisons[-1]} ; {len(set(t['match']))} matchs. "
           f"Appris avant {SAISON_TEST}, testé à partir de {SAISON_TEST}.\n"]
    for marche, nom in (("1N2", "1N2"), ("TOT", "Total 2,5 buts")):
        m = filtrer(t, t["marche"] == marche)
        lignes = []
        tout = ["moyenne", "bet365", "meilleur", "niveau", "marge"]
        for lib, variables in (("écart à la moyenne du marché", ["moyenne"]), ("écart à bet365", ["bet365"]),
                               ("moyenne, bet365, meilleur prix, niveau, marge", tout)):
            c = complets(m, variables)
            l, _ = essai(lib, filtrer(c, c["saison"] < SAISON_TEST), filtrer(c, c["saison"] >= SAISON_TEST), variables, rng, tirages)
            lignes.append(l)
        for lib, variables in (("écart à Betfair Exchange (appris 2024-25, testé 2025-26)", ["betfair"]),
                               ("écart à la moyenne (mêmes saisons)", ["moyenne"]),
                               ("Betfair Exchange et moyenne (mêmes saisons)", ["betfair", "moyenne"])):
            c = complets(m, ["betfair", "moyenne"])
            l, _ = essai(lib, filtrer(c, c["saison"] == "2425"), filtrer(c, c["saison"] == "2526"), variables, rng, tirages)
            lignes.append(l)
        out.append(f"**{nom}**\n\n" + tableau(ENTETES, lignes))
        # ce que cela change pour le parieur : dixièmes de la prévision, puis les « values »
        c = complets(m, tout + ["b0", "bc", "maxc"])
        app, test = filtrer(c, c["saison"] < SAISON_TEST), filtrer(c, c["saison"] >= SAISON_TEST)
        prevu = predire(ajuster(np.c_[tuple(app[v] for v in tout)], app["y"]), np.c_[tuple(test[v] for v in tout)])
        bornes = np.quantile(prevu, np.linspace(0, 1, 6))
        lignes = []
        for q in range(5):
            g = (prevu >= bornes[q]) & ((prevu <= bornes[q + 1]) if q == 4 else (prevu < bornes[q + 1]))
            lignes.append([q + 1, int(g.sum()), pct(float(np.mean(np.expm1(prevu[g] * (1 - test["p0"][g]))))),
                           ic(moyenne(test["pc"][g] / test["p0"][g] - 1, test["match"][g], rng, tirages)),
                           ic(moyenne(test["bc"][g] / test["b0"][g] - 1, test["match"][g], rng, tirages))])
        out.append(f"{nom}, saisons de test, par cinquième de la prévision (modèle à cinq variables) :\n\n" + tableau(
            ["Cinquième", "Issues", "Proba Pinnacle : variation prévue", "Variation réelle", "Cote bet365 : clôture / relevé"], lignes))
        lignes = []
        ecart = test["max0"] * test["p0"] - 1
        for lib, g in (("2 à 5 %", (ecart >= 0.02) & (ecart < 0.05)), ("5 % et plus", ecart >= 0.05)):
            if g.sum() >= 30:
                lignes.append([lib, int(g.sum()), pct(float(ecart[g].mean())),
                               ic(moyenne(test["max0"][g] * test["pc"][g] - 1, test["match"][g], rng, tirages)),
                               ic(moyenne(test["maxc"][g] * test["pc"][g] - 1, test["match"][g], rng, tirages)),
                               f"{100 * float((prevu[g] < 0).mean()):.0f} %"])
        if lignes:
            out.append(f"{nom}, « values » des saisons de test (meilleur prix du marché contre la cote juste Pinnacle) :\n\n" + tableau(
                ["Écart au relevé", "Issues", "Écart moyen", "CLV, pari pris au relevé", "CLV, même issue prise à la clôture",
                 "Baisse de la proba prévue par le modèle"], lignes))
    return "\n".join(out)


# ---------------------------------------------------------------- 2. paris du projet

def paris_uniques(donnees: Path) -> list[dict]:
    """Première détection de chaque cote française de référence Pinnacle dont la clôture est mesurée."""
    paris = stockage.fusionner_paris(stockage.lire_archives(donnees), json.loads((donnees / "paris.json").read_text()))
    vus, out = set(), []
    for p in sorted(paris, key=lambda p: p["detecte"]):
        if p.get("reference") != "Pinnacle" or simulation.clv_finale(p) is None:
            continue
        if not p.get("cote_juste") or not p.get("cote_juste_cloture") or cle_selection(p) in vus:
            continue
        vus.add(cle_selection(p))
        out.append(p)
    return out


def table_paris(paris: list[dict]) -> dict:
    lignes = []
    for p in paris:
        t, d = instant_utc(p["detecte"]), instant_utc(p["debut"])
        autre = p.get("ecart_polymarket")
        lignes.append({"detecte": p["detecte"], "match": p["match_id"], "bookmaker": p["bookmaker"], "sport": p["sport"],
                       "marche": p["marche"], "cote": p["cote"], "ecart": p["ecart"],
                       "clv": p["cote"] / p["cote_juste_cloture"] - 1, "y": math.log(p["cote_juste"] / p["cote_juste_cloture"]),
                       "heures": (d - t).total_seconds() / 3600, "log_ecart": math.log1p(p["ecart"]),
                       "log_delai": math.log1p(max((d - t).total_seconds() / 3600, 0)), "log_cote": math.log(p["cote"]),
                       # log(proba Polymarket / proba Pinnacle) : positif si Polymarket voit l'issue plus probable
                       "polymarket": math.log1p(autre) - math.log1p(p["ecart"]) if autre is not None else math.nan,
                       "ecart_polymarket": autre if autre is not None else math.nan})
    return table(lignes)


def partie_paris(t: dict, rng, tirages: int) -> str:
    t = filtrer(t, t["cote"] <= COTE_MAX)
    avant = np.array([d < COUPURE_PARIS for d in t["detecte"]])
    app, test = filtrer(t, avant), filtrer(t, ~avant)
    out = [f"Paris uniques de référence Pinnacle, cote ≤ {COTE_MAX:g}, clôture mesurée : {len(app['y'])} appris "
           f"({min(app['detecte'])[:10]} au {max(app['detecte'])[:10]}), {len(test['y'])} testés "
           f"({min(test['detecte'])[:10]} au {max(test['detecte'])[:10]}).\n"]
    y = test["y"]
    out.append(f"- Après la détection, la proba juste Pinnacle **baisse** pour {100 * float((y < 0).mean()):.0f} % des paris testés ; "
               f"mouvement moyen {pct(float(np.expm1(y).mean()))} (appris : {pct(float(np.expm1(app['y']).mean()))}), "
               f"médian {pct(float(np.median(np.expm1(y))))}.")
    cst = float(app["y"].mean())
    out.append(f"- Écart moyen {pct(float(test['ecart'].mean()))}, CLV moyenne {ic(moyenne(test['clv'], test['match'], rng, tirages))}.\n")
    lignes = [["constante apprise (même baisse pour tous)", len(app["y"]), len(y),
               r2txt(r2_hors_echantillon(y, np.full(len(y), cst), 0.0, test["match"], rng, tirages)), "—", "—", f"{cst:+.3f}".replace(".", ",")]]
    for lib, variables in (("écart", ["log_ecart"]), ("écart, délai", ["log_ecart", "log_delai"]),
                           ("écart, délai, cote", ["log_ecart", "log_delai", "log_cote"])):
        l, prevu = essai(lib, app, test, variables, rng, tirages)
        l[3] += " ; contre la constante : " + r2txt(r2_hors_echantillon(y, prevu, cst, test["match"], rng, tirages))
        lignes.append(l)
    out.append(tableau(ENTETES, lignes))

    def groupes(titre, decoupes):
        lg = []
        for lib, g in decoupes:
            if g.sum() < 30:
                continue
            a, b = g & avant, g & ~avant
            lg.append([lib, int(g.sum()), pct(float(t["ecart"][g].mean())), ic(moyenne(t["clv"][g], t["match"][g], rng, tirages)),
                       f"{pct(float(t['clv'][a].mean())) if a.sum() >= 20 else '—'} ({int(a.sum())})",
                       f"{pct(float(t['clv'][b].mean())) if b.sum() >= 20 else '—'} ({int(b.sum())})"])
        return tableau([titre, "Paris", "Écart moyen", "CLV Pinnacle, IC 95 %", "Appris (n)", "Testés (n)"], lg)
    e, h, pm = t["ecart"], t["heures"], t["ecart_polymarket"]
    out.append(groupes("Écart à la détection", [("2 à 3 %", e < 0.03), ("3 à 5 %", (e >= 0.03) & (e < 0.05)),
                                                 ("5 à 8 %", (e >= 0.05) & (e < 0.08)), ("8 % et plus", e >= 0.08)]))
    out.append(groupes("Délai avant le match", [("3 h au plus", h <= 3), ("3 à 12 h", (h > 3) & (h <= 12)), ("plus de 12 h", h > 12)]))
    out.append(groupes("Second avis Polymarket", [("d'accord : écart Polymarket ≥ 2 %", pm >= 0.02), ("écart Polymarket de 0 à 2 %", (pm >= 0) & (pm < 0.02)),
                                                  ("pas d'accord : écart Polymarket < 0", pm < 0), ("pas de prix Polymarket", ~np.isfinite(pm))]))
    c = complets(t, ["polymarket"])
    av = np.array([d < COUPURE_PARIS for d in c["detecte"]])
    l, prevu = essai("écart Polymarket − écart Pinnacle", filtrer(c, av), filtrer(c, ~av), ["polymarket"], rng, tirages)
    ct = filtrer(c, ~av)
    l[3] += " ; contre la constante : " + r2txt(r2_hors_echantillon(ct["y"], prevu, float(filtrer(c, av)["y"].mean()), ct["match"], rng, tirages))
    out.append("Le prix Polymarket du même pari prédit-il le mouvement de Pinnacle ?\n\n" + tableau(ENTETES, [l]))
    marches = sorted({m for m in t["marche"]}, key=lambda m: -int((t["marche"] == m).sum()))
    out.append(groupes("Marché", [(m, t["marche"] == m) for m in marches if (t["marche"] == m).sum() >= 60]))
    sports = sorted({s for s in t["sport"]}, key=lambda s: -int((t["sport"] == s).sum()))
    out.append(groupes("Sport", [(s, t["sport"] == s) for s in sports if (t["sport"] == s).sum() >= 60]))
    return "\n".join(out)


# ---------------------------------------------------------------- 3. attendre

ATTENTES = (("15 min", 900), ("1 h", 3600), ("3 h", 3 * 3600), ("jusqu'au match", None))


def _cle_historique(p: dict) -> tuple:
    k = "|".join("" if x is None else str(x) for x in (p.get("marche"), p.get("periode"), p.get("ligne"), p.get("issue")))
    return (p["bookmaker"].lower(), p["match_id"], k + ("|" + str(p["joueur"]) if p.get("joueur") else ""))


def cote_a(temps: list[float], cotes: list, t: float):
    """Dernière cote connue à l'instant ``t`` (None : retirée ou pas encore lue)."""
    i = bisect.bisect_right(temps, t) - 1
    return cotes[i] if i >= 0 else None


def mesurer_attente(p: dict, temps: list[float], cotes: list) -> dict | None:
    """CLV du pari pris à la détection et du même pari pris après chaque attente, contre la même clôture Pinnacle."""
    t0, debut = instant_utc(p["detecte"]).timestamp(), instant_utc(p["debut"]).timestamp()
    prise = cote_a(temps, cotes, t0 + 600)
    if prise is None or abs(prise - p["cote"]) > 0.011:         # la cote prise doit se retrouver dans l'historique
        return None
    r = {"match": p["match_id"], "bookmaker": p["bookmaker"], "ecart": p["ecart"], "cote": p["cote"],
         "clv": p["cote"] / p["cote_juste_cloture"] - 1}
    for nom, attente in ATTENTES:
        t = debut - 60 if attente is None else t0 + attente
        c = cote_a(temps, cotes, t) if t0 < t <= debut - 60 else None
        r[nom] = c / p["cote_juste_cloture"] - 1 if c else math.nan
        r["cote " + nom] = c or math.nan
    return r


def partie_attendre(donnees: Path, paris: list[dict], rng, tirages: int) -> str:
    jours = sorted(f.name[:10] for f in (donnees / "cotes").glob("*.jsonl.gz"))
    if not jours:
        return "_Pas d'historique des cotes._\n"
    choisis = [p for p in paris if p["detecte"][:10] >= jours[0] and p["cote"] <= COTE_MAX
               and p["marche"] not in ("CORRECT_SCORE", "HALF_TIME_FULL_TIME")]
    series = {_cle_historique(p): ([], []) for p in choisis}
    for jour in jours:
        with gzip.open(donnees / "cotes" / f"{jour}.jsonl.gz", "rt", encoding="utf-8") as f:
            for ligne in f:
                if '"k"' not in ligne:
                    continue
                d = json.loads(ligne)
                s = series.get((str(d.get("b") or "").lower(), d.get("m"), d.get("k")))
                if s is not None:
                    s[0].append(instant_utc(d["t"]).timestamp())
                    s[1].append(d.get("c"))
    t = table([m for p in choisis if (m := mesurer_attente(p, *series[_cle_historique(p)]))])
    if not t:
        return "_Aucun pari retrouvé dans l'historique des cotes._\n"
    out = [f"Paris uniques de référence Pinnacle détectés depuis le {jours[0]}, cote ≤ {COTE_MAX:g}, hors score exact : "
           f"{len(choisis)}, dont {len(t['clv'])} retrouvés dans l'historique des cotes ({len(set(t['match']))} matchs).\n"]

    def lignes_pour(masque):
        lg = []
        for nom, _ in ATTENTES:
            g = masque & np.isfinite(t[nom])
            if g.sum() < 30:
                continue
            lg.append([nom, int(g.sum()), ic(moyenne(t["clv"][g], t["match"][g], rng, tirages)), ic(moyenne(t[nom][g], t["match"][g], rng, tirages)),
                       ic(moyenne(t[nom][g] - t["clv"][g], t["match"][g], rng, tirages)),
                       f"{100 * float((t['cote ' + nom][g] > t['cote'][g] + 1e-9).mean()):.0f} %",
                       f"{100 * float((t['cote ' + nom][g] < t['cote'][g] - 1e-9).mean()):.0f} %"])
        return tableau(["Attente", "Paris", "CLV, pris à la détection", "CLV, pris après l'attente", "Différence", "Cote plus haute",
                        "Cote plus basse"], lg)
    out.append(lignes_pour(np.ones(len(t["clv"]), bool)))
    for lib, m in (("PMU", t["bookmaker"] == "PMU"), ("Betclic", t["bookmaker"] == "Betclic"),
                   ("Écart de 2 à 3 %", t["ecart"] < 0.03), ("Écart de 5 % et plus", t["ecart"] >= 0.05)):
        out.append(f"{lib} :\n\n" + lignes_pour(m))
    return "\n".join(out)


# ---------------------------------------------------------------- 4. historique des références

HORIZONS = (12.0, 6.0, 3.0, 1.0)


def lire_references(donnees: Path):
    """Séries Pinnacle des marchés principaux, description des matchs, séries des autres références rapprochées."""
    par_fr = defaultdict(dict)
    for f in sorted((donnees / "correspondances").glob("*.jsonl.gz")):
        with gzip.open(f, "rt", encoding="utf-8") as g:
            for ligne in g:
                x = json.loads(ligne)
                par_fr[x["fr"]][x["b"]] = (str(x["m"]), bool(x["inv"]))
    lien = defaultdict(dict)                 # match Pinnacle -> {référence: son match}, même sens domicile/extérieur
    for d in par_fr.values():
        if "Pinnacle" in d:
            for b, (m, inv) in d.items():
                if b != "Pinnacle" and inv == d["Pinnacle"][1]:
                    lien[d["Pinnacle"][0]][b] = m
    utiles = {(b, m) for d in lien.values() for b, m in d.items()}
    matchs, pinnacle, autres = {}, defaultdict(lambda: ([], [])), defaultdict(lambda: ([], []))
    for f in sorted((donnees / "references").glob("*.jsonl.gz")):
        with gzip.open(f, "rt", encoding="utf-8") as g:
            for ligne in g:
                if '"k":' not in ligne:
                    if '"b":"Pinnacle"' in ligne:
                        x = json.loads(ligne)
                        if x.get("debut"):
                            matchs[str(x["m"])] = (x.get("sport"), instant_utc(x["debut"]).timestamp())
                    continue
                k = ligne.split('"k":"', 1)[1].split('"', 1)[0]
                if not k.startswith(MARCHES_REF):
                    continue
                x = json.loads(ligne)
                cle = (str(x["m"]), k)
                if x["b"] == "Pinnacle":
                    s = pinnacle[cle]
                elif (x["b"], cle[0]) in utiles:
                    s = autres[(x["b"],) + cle]
                else:
                    continue
                s[0].append(instant_utc(x["t"]).timestamp())
                s[1].append(x.get("p") if x.get("c") is not None else None)
    return matchs, pinnacle, autres, lien


def points_references(matchs, pinnacle, autres, lien) -> dict:
    """Un point par cote Pinnacle et par horizon H : proba juste H heures avant le match, élan, écarts, clôture.

    Vainqueur et 1N2 pour tous les sports ; totaux et handicaps pour le football seulement (au basket, Pinnacle
    retire les lignes dont le marché s'éloigne : celles qui restent jusqu'au match sont « revenues » par construction)."""
    if not pinnacle:
        return {}
    debut_histo = min(s[0][0] for s in pinnacle.values())
    fin_histo = max(s[0][-1] for s in pinnacle.values())
    lignes = []
    for (m, k), (temps, probas) in pinnacle.items():
        sport, debut = matchs.get(m, (None, None))
        if not debut or debut > fin_histo - 600:
            continue
        marche, _, _, issue = k.split("|")[:4]
        if marche in ("TOTAL", "HANDICAP") and sport != "football":
            continue
        if issue not in ("DOM", "PLUS") and not (marche == "RESULTAT_1N2" and issue == "EXT"):
            continue
        pc = cote_a(temps, probas, debut)
        for h in HORIZONS:
            t = debut - h * 3600
            p = cote_a(temps, probas, t)
            if t < debut_histo + 3600 or p is None or pc is None or not 0.02 < p < 0.98 or not 0 < pc < 1:
                continue
            if marche in ("TOTAL", "HANDICAP") and not 0.3 <= p <= 0.7:
                continue
            avant = cote_a(temps, probas, t - 3600)
            r = {"match": m, "debut": debut, "h": h, "principal": float(marche in ("VAINQUEUR", "RESULTAT_1N2")),
                 "y": logit(pc) - logit(p), "niveau": logit(p),
                 "elan": (logit(p) - logit(avant)) if avant and 0 < avant < 1 else (0.0 if temps[0] <= t - 3600 else math.nan)}
            for b in ("Polymarket", "Matchbook", "Smarkets"):
                s = autres.get((b, lien.get(m, {}).get(b), k))
                q = cote_a(s[0], s[1], t) if s else None
                r[b] = logit(q) - logit(p) if q and 0.01 < q < 0.99 else math.nan
            lignes.append(r)
    return table(lignes)


def partie_references(donnees: Path, rng, tirages: int) -> str:
    t = points_references(*lire_references(donnees))
    if not t:
        return "_Pas d'historique des références._\n"
    coupure = instant_utc(COUPURE_REFERENCES + "T00:00:00+00:00").timestamp()
    out = [f"{len(t['y'])} points, {len(set(t['match']))} matchs Pinnacle ; appris sur les matchs d'avant le {COUPURE_REFERENCES}, "
           f"testé sur ceux de ce jour.\n"]

    def lignes_pour(base: dict, essais) -> list:
        lg = []
        for lib, variables, h in essais:
            c = complets(filtrer(base, base["h"] == h) if h else base, variables)
            app, test = filtrer(c, c["debut"] < coupure), filtrer(c, c["debut"] >= coupure)
            if len(app["y"]) < 200 or len(test["y"]) < 200:
                continue
            l, _ = essai(f"{lib}, {h:g} h avant" if h else lib, app, test, variables, rng, tirages)
            lg.append(l[:1] + [f"{l[1]} ({len(set(app['match']))} matchs)", f"{l[2]} ({len(set(test['match']))} matchs)"] + l[3:])
        return lg
    for nom, base in (("Vainqueur et 1N2, tous sports", filtrer(t, t["principal"] == 1)),
                      ("Totaux et handicaps, football", filtrer(t, t["principal"] == 0))):
        out.append(f"**{nom}**\n\n" + tableau(ENTETES, lignes_pour(base, [(lib, v, h) for h in HORIZONS for lib, v in
                                                                      (("élan de la dernière heure", ["elan"]), ("niveau", ["niveau"]))])))
    out.append("**Écart à une autre référence** (tous marchés, horizons de 1 à 12 h réunis)\n\n" + tableau(
        ENTETES, lignes_pour(t, [(f"écart à {b}", [b], None) for b in ("Polymarket", "Matchbook", "Smarkets")])))
    return "\n".join(out)


# ---------------------------------------------------------------- sortie

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--donnees", type=Path, required=True)
    ap.add_argument("--football", type=Path)
    ap.add_argument("--tirages", type=int, default=4000)
    a = ap.parse_args()
    rng = np.random.default_rng(GRAINE)
    if a.football:
        print("## 1. football-data.co.uk : du relevé d'avant-match à la clôture\n\n" + partie_football(a.football, rng, a.tirages))
    paris = paris_uniques(a.donnees)
    print("## 2. Paris du projet : de la détection à la clôture\n\n" + partie_paris(table_paris(paris), rng, a.tirages))
    print("## 3. Attendre\n\n" + partie_attendre(a.donnees, paris, rng, a.tirages))
    print("## 4. Historique des références\n\n" + partie_references(a.donnees, rng, a.tirages))
    return 0


if __name__ == "__main__":
    sys.exit(main())
