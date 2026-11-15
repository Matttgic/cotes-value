"""Modèle de prix indépendant des bookmakers (football) et mesure contre Pinnacle. Lecture seule.

Usage :
    python etudes/modele_prix.py regler  --football DOSSIER --football-plus DOSSIER2
    python etudes/modele_prix.py mesurer --football DOSSIER --football-plus DOSSIER2 [--tirages 2000]

``--football`` : fichiers de football-data.co.uk nommés ``SAISON-DIVISION.csv`` (22 divisions, les mêmes que
etudes/cote_juste.py). ``--football-plus`` : fichiers ``PAYS.csv`` des 16 ligues supplémentaires du même site
(``new/ARG.csv``, etc.). Demande numpy. Même graine, mêmes données : mêmes chiffres. Sortie en Markdown ; les
conclusions sont dans docs/modele-prix.md.

Trois modèles, tous calculés match après match avec les seuls matchs joués avant la date du match :
- **Elo** : une note par équipe, mise à jour après chaque match (écart de buts, avantage du terrain par division) ;
  la différence de notes donne 1N2 par un logit ordonné ;
- **Poisson** (Dixon-Coles) : attaque et défense par équipe, avantage du terrain par division, matchs pondérés par
  leur ancienneté, correction des petits scores ; donne 1N2, total de buts et handicap ;
- **Poisson + tirs** : un second modèle de Poisson prévoit les tirs cadrés de chaque équipe ; les buts attendus
  sont une combinaison des deux prévisions, ajustée sur la période de réglage.

Les réglages (constantes ``ELO`` et ``POISSON``) ont été choisis par ``regler`` sur les matchs d'avant le
01/07/2019 uniquement ; ``mesurer`` juge les modèles sur les matchs joués depuis, qu'aucun réglage n'a vus.

Rien ici ne sert à la détection : c'est une mesure.
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from datetime import date
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from etudes.cote_juste import (brier, erreur_pente, intervalle, log_loss, pente_calibration,  # noqa: E402
                                retirer_marge, tableau)

GRAINE = 20261115
DEBUT_REGLAGE = date(2014, 7, 1).toordinal()      # avant : deux saisons de rodage, jamais notées
DEBUT_TEST = date(2019, 7, 1).toordinal()         # réglages choisis avant, mesure après
MILIEU_TEST = date(2022, 7, 1).toordinal()        # totaux et handicaps Pinnacle : poids ajustés avant, jugés après
BUTS_MAX = 12

# Réglages choisis par ``regler`` (matchs d'avant le 01/07/2019).
ELO = {"k": 10.0, "gamma": 0.9, "terrain": 60.0, "k_terrain": 1.2, "retour": 0.2, "ecart_niveau": 150.0,
       "ecart_nouveau": 50.0}
POISSON = {"xi": 0.0026, "kappa": 6.0, "nouveau": 0.9, "fenetre": 1460, "rho": -0.06}
XI_TIRS = 0.008                                    # oubli par jour du modèle des tirs cadrés

# division -> (groupe de pays, niveau dans le pays)
DIVISIONS = {"E0": ("ENG", 0), "E1": ("ENG", 1), "E2": ("ENG", 2), "E3": ("ENG", 3), "EC": ("ENG", 4),
             "SC0": ("SCO", 0), "SC1": ("SCO", 1), "SC2": ("SCO", 2), "SC3": ("SCO", 3),
             "D1": ("GER", 0), "D2": ("GER", 1), "I1": ("ITA", 0), "I2": ("ITA", 1),
             "SP1": ("ESP", 0), "SP2": ("ESP", 1), "F1": ("FRA", 0), "F2": ("FRA", 1),
             "N1": ("NED", 0), "B1": ("BEL", 0), "P1": ("POR", 0), "T1": ("TUR", 0), "G1": ("GRE", 0)}
FAMILLES = (("Cinq grands championnats, 1re division", {"E0", "D1", "I1", "SP1", "F1"}),
            ("Cinq grands championnats, 2e division", {"E1", "D2", "I2", "SP2", "F2"}),
            ("Divisions inférieures (Angleterre 3 à 5, Écosse 2 à 4)", {"E2", "E3", "EC", "SC1", "SC2", "SC3"}),
            ("Autres 1res divisions d'Europe (Écosse, Pays-Bas, Belgique, Portugal, Turquie, Grèce)",
             {"SC0", "N1", "B1", "P1", "T1", "G1"}))
FAMILLE_PLUS = "16 ligues supplémentaires (Amériques, Asie, Nord et Est de l'Europe)"

# cotes lues : nom -> colonnes (fichiers principaux)
COTES_1N2 = {"pin_c": ("PSCH", "PSCD", "PSCA"), "pin_o": ("PSH", "PSD", "PSA"),
             "b365_c": ("B365CH", "B365CD", "B365CA"), "b365_o": ("B365H", "B365D", "B365A"),
             "moy_c": ("AvgCH", "AvgCD", "AvgCA"), "max_c": ("MaxCH", "MaxCD", "MaxCA"),
             "bfe_c": ("BFECH", "BFECD", "BFECA")}
COTES_TOTAL = {"pin_c": ("PC>2.5", "PC<2.5"), "pin_o": ("P>2.5", "P<2.5"), "b365_c": ("B365C>2.5", "B365C<2.5"),
               "max_c": ("MaxC>2.5", "MaxC<2.5")}
COTES_HANDICAP = {"pin_c": ("PCAHH", "PCAHA", "AHCh"), "pin_o": ("PAHH", "PAHA", "AHh")}
SANS_MARGE = {"max_c", "bfe_c"}                    # meilleure cote et bourse : la somme des 1/cote peut passer sous 1


# ---------------------------------------------------------------- lecture

def _reel(x) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return math.nan
    return v if math.isfinite(v) else math.nan


def _jour(s: str) -> int | None:
    try:
        j, m, a = (int(x) for x in s.strip().split("/"))
    except ValueError:
        return None
    if a < 100:
        a += 2000
    try:
        return date(a, m, j).toordinal()
    except ValueError:
        return None


def _cotes(lire, colonnes: tuple[str, ...], marge_exigee: bool) -> list[float]:
    c = [lire(x) for x in colonnes]
    if any(not (v > 1.0) for v in c):
        return [math.nan] * len(colonnes)
    if marge_exigee and sum(1 / v for v in c) < 1.0:            # pas de marge : saisie douteuse
        return [math.nan] * len(colonnes)
    return c


def lire_matchs(principal: Path | None, plus: Path | None) -> dict[str, np.ndarray]:
    """Tous les matchs joués, triés par date. Tableaux parallèles : jour, groupe, division, niveau, saison, équipes,
    buts, tirs cadrés, famille, et les cotes (NaN quand elles manquent)."""
    lignes: list[dict] = []
    if principal is not None:
        for fichier in sorted(Path(principal).glob("*.csv")):
            saison, div = fichier.stem.split("-")
            if div not in DIVISIONS:
                continue
            groupe, niveau = DIVISIONS[div]
            with open(fichier, encoding="latin-1", newline="") as f:
                brut = list(csv.reader(f))
            if not brut:
                continue
            col = {nom.strip().lstrip("﻿").lstrip("ï»¿"): i for i, nom in enumerate(brut[0])}
            for r in brut[1:]:
                lire = lambda nom: _reel(r[col[nom]]) if nom in col and col[nom] < len(r) else math.nan  # noqa: E731
                texte = lambda nom: r[col[nom]].strip() if nom in col and col[nom] < len(r) else ""       # noqa: E731
                jour, bd, be = _jour(texte("Date")), lire("FTHG"), lire("FTAG")
                if jour is None or math.isnan(bd) or math.isnan(be) or not texte("HomeTeam"):
                    continue
                m = {"jour": jour, "groupe": groupe, "division": div, "niveau": niveau, "saison": saison,
                     "dom": texte("HomeTeam"), "ext": texte("AwayTeam"), "bd": bd, "be": be,
                     "td": lire("HST"), "te": lire("AST")}
                for nom, colonnes in COTES_1N2.items():
                    m["1n2_" + nom] = _cotes(lire, colonnes, nom not in SANS_MARGE)
                for nom, colonnes in COTES_TOTAL.items():
                    m["tot_" + nom] = _cotes(lire, colonnes, nom not in SANS_MARGE)
                for nom, (c1, c2, cl) in COTES_HANDICAP.items():
                    m["han_" + nom] = _cotes(lire, (c1, c2), True) + [lire(cl)]
                lignes.append(m)
    if plus is not None:
        for fichier in sorted(Path(plus).glob("*.csv")):
            with open(fichier, encoding="utf-8-sig", errors="replace", newline="") as f:
                for r in csv.DictReader(f):
                    lire = lambda nom: _reel(r.get(nom))                                                # noqa: E731
                    jour, bd, be = _jour(r.get("Date") or ""), lire("HG"), lire("AG")
                    if jour is None or math.isnan(bd) or math.isnan(be) or not (r.get("Home") or "").strip():
                        continue
                    m = {"jour": jour, "groupe": fichier.stem, "division": fichier.stem, "niveau": 0,
                         "saison": (r.get("Season") or "").strip(), "dom": r["Home"].strip(),
                         "ext": (r.get("Away") or "").strip(), "bd": bd, "be": be, "td": math.nan, "te": math.nan}
                    for nom, colonnes in COTES_1N2.items():
                        ok = nom.endswith("_c")
                        m["1n2_" + nom] = _cotes(lire, colonnes, nom not in SANS_MARGE) if ok else [math.nan] * 3
                    for nom in COTES_TOTAL:
                        m["tot_" + nom] = [math.nan] * 2
                    for nom in COTES_HANDICAP:
                        m["han_" + nom] = [math.nan] * 3
                    lignes.append(m)
    lignes.sort(key=lambda m: (m["jour"], m["groupe"], m["division"], m["dom"]))
    t: dict[str, np.ndarray] = {}
    for cle in ("jour", "niveau"):
        t[cle] = np.array([m[cle] for m in lignes], dtype=np.int64)
    for cle in ("groupe", "division", "saison", "dom", "ext"):
        t[cle] = np.array([m[cle] for m in lignes])
    for cle in ("bd", "be", "td", "te"):
        t[cle] = np.array([m[cle] for m in lignes], dtype=float)
    for cle in lignes[0]:
        if cle[:4] in ("1n2_", "tot_", "han_"):
            t[cle] = np.array([m[cle] for m in lignes], dtype=float)
    fam = np.full(len(lignes), FAMILLE_PLUS, dtype=object)
    for nom, divs in FAMILLES:
        fam[np.isin(t["division"], list(divs))] = nom
    t["famille"] = fam.astype(str)
    return t


# ---------------------------------------------------------------- Elo

def elo(t: dict[str, np.ndarray], r: dict) -> dict[str, np.ndarray]:
    """Avance match après match. Rend, par match : ``x`` (différence de notes + terrain, en centaines de points),
    ``neuf`` (une des deux équipes n'avait jamais joué dans le groupe) et ``joues`` (matchs déjà joués dans la
    saison par l'équipe qui en a le moins)."""
    n = len(t["jour"])
    x, neuf, joues = np.zeros(n), np.zeros(n, dtype=bool), np.zeros(n, dtype=np.int64)
    note: dict[tuple, float] = {}
    saison_de: dict[tuple, str] = {}
    compte: dict[tuple, int] = {}
    membres: dict[tuple, dict] = defaultdict(dict)        # (groupe, division) -> {équipe: note}
    division_de: dict[tuple, str] = {}
    terrain: dict[tuple, float] = defaultdict(lambda: r["terrain"])
    i = 0
    while i < n:
        j = i
        while j < n and t["jour"][j] == t["jour"][i]:
            j += 1
        prevus = []
        for m in range(i, j):
            g, d = t["groupe"][m], t["division"][m]
            cles = []
            for eq in (t["dom"][m], t["ext"][m]):
                cle = (g, eq)
                if cle not in note:
                    connus = membres[(g, d)]
                    base = (sum(connus.values()) / len(connus) if connus
                            else 1500.0 - r["ecart_niveau"] * t["niveau"][m])
                    note[cle] = base - (r["ecart_nouveau"] if connus else 0.0)
                    neuf[m] = True
                if saison_de.get(cle) != t["saison"][m]:
                    connus = membres[(g, d)]
                    if connus and r["retour"]:
                        note[cle] += r["retour"] * (sum(connus.values()) / len(connus) - note[cle])
                    saison_de[cle] = t["saison"][m]
                    compte[cle] = 0
                if division_de.get(cle) != d:
                    if cle in division_de:
                        membres[(g, division_de[cle])].pop(eq, None)
                    division_de[cle] = d
                membres[(g, d)][eq] = note[cle]
                cles.append(cle)
            x[m] = (note[cles[0]] - note[cles[1]] + terrain[(g, d)]) / 100.0
            joues[m] = min(compte[cles[0]], compte[cles[1]])
            prevus.append((m, cles, (g, d)))
        for m, cles, gd in prevus:
            ecart = t["bd"][m] - t["be"][m]
            s = 1.0 if ecart > 0 else 0.5 if ecart == 0 else 0.0
            e = 1.0 / (1.0 + 10 ** (-x[m] / 4.0))
            delta = r["k"] * max(abs(ecart), 1.0) ** r["gamma"] * (s - e)
            note[cles[0]] += delta
            note[cles[1]] -= delta
            terrain[gd] += r["k_terrain"] * (s - e)
            for cle in cles:
                compte[cle] += 1
                membres[gd][cle[1]] = note[cle]
        i = j
    return {"x": x, "neuf": neuf, "joues": joues}


def proba_elo(x: np.ndarray, pente: float, seuil: float) -> np.ndarray:
    """Logit ordonné : P(extérieur) = σ(−seuil − pente·x), P(domicile) = σ(−seuil + pente·x), le reste au nul."""
    dom = 1.0 / (1.0 + np.exp(seuil - pente * x))
    ext = 1.0 / (1.0 + np.exp(seuil + pente * x))
    return np.column_stack([dom, np.clip(1.0 - dom - ext, 1e-6, None), ext])


def minimiser(f, x0: list[float], pas: float = 0.2, tours: int = 400) -> np.ndarray:
    """Nelder-Mead (peu de paramètres, fonction lisse)."""
    k = len(x0)
    pts = [np.array(x0, dtype=float)] + [np.array(x0, dtype=float) + pas * np.eye(k)[i] for i in range(k)]
    val = [f(p) for p in pts]
    for _ in range(tours):
        ordre = np.argsort(val)
        pts, val = [pts[i] for i in ordre], [val[i] for i in ordre]
        if abs(val[-1] - val[0]) < 1e-10:
            break
        centre = np.mean(pts[:-1], axis=0)
        refl = centre + (centre - pts[-1])
        v = f(refl)
        if v < val[0]:
            etendu = centre + 2 * (centre - pts[-1])
            ve = f(etendu)
            pts[-1], val[-1] = (etendu, ve) if ve < v else (refl, v)
        elif v < val[-2]:
            pts[-1], val[-1] = refl, v
        else:
            contr = centre + 0.5 * (pts[-1] - centre)
            vc = f(contr)
            if vc < val[-1]:
                pts[-1], val[-1] = contr, vc
            else:
                pts = [pts[0]] + [pts[0] + 0.5 * (p - pts[0]) for p in pts[1:]]
                val = [val[0]] + [f(p) for p in pts[1:]]
    return pts[int(np.argmin(val))]


def ajuster_elo(x: np.ndarray, gagnant: np.ndarray) -> tuple[float, float]:
    f = lambda v: float(log_loss(proba_elo(x, v[0], v[1]), gagnant).mean())      # noqa: E731
    pente, seuil = minimiser(f, [0.6, 0.9])
    return float(pente), float(seuil)


# ---------------------------------------------------------------- Poisson (Dixon-Coles)

def _poisson_groupe(arg: tuple) -> tuple:
    """Un groupe de pays : attaque, défense et terrain réajustés avant chaque journée, sur les matchs passés."""
    jour, dom, ext, div, bd, be, td, te, nb_eq, nb_div, r, cible = arg
    n = len(jour)
    lam_d, lam_e, neuf = np.full(n, np.nan), np.full(n, np.nan), np.zeros(n, dtype=bool)
    att, dfs, ter = np.ones(nb_eq), np.full(nb_eq, 1.2), np.full(nb_div, 1.3)
    div_eq = np.full(nb_eq, -1)
    avec_tirs = ~np.isnan(td) & ~np.isnan(te)
    kappa = r["kappa"]
    i = 0
    while i < n:
        j = i
        while j < n and jour[j] == jour[i]:
            j += 1
        a = int(np.searchsorted(jour, jour[i] - r["fenetre"]))
        if i - a >= 20:
            h, e, d = dom[a:i], ext[a:i], div[a:i]
            w = np.exp(-r["xi"] * (jour[i] - jour[a:i]))
            yd, ye = bd[a:i], be[a:i]
            if cible == "tirs":                       # mêmes équations, les tirs cadrés à la place des buts
                s = avec_tirs[a:i]
                w = w * s
                yd, ye = np.where(s, td[a:i], 0.0), np.where(s, te[a:i], 0.0)
            num_a = np.bincount(h, w * yd, nb_eq) + np.bincount(e, w * ye, nb_eq)
            num_d = np.bincount(e, w * yd, nb_eq) + np.bincount(h, w * ye, nb_eq)
            num_t = np.bincount(d, w * yd, nb_div)
            present = (np.bincount(h, w, nb_eq) + np.bincount(e, w, nb_eq)) > 0
            if present.sum() < 4:
                div_eq[dom[i:j]] = div[i:j]
                div_eq[ext[i:j]] = div[i:j]
                i = j
                continue
            connue = div_eq >= 0
            for _ in range(200):
                den_a = np.bincount(h, w * ter[d] * dfs[e], nb_eq) + np.bincount(e, w * dfs[h], nb_eq)
                idx = np.where(present & connue)[0]
                moy_a = np.ones(nb_div)
                moy_d = np.full(nb_div, 1.2)
                if len(idx):
                    pa = np.bincount(div_eq[idx], den_a[idx], nb_div)
                    ok = pa > 0
                    moy_a[ok] = (np.bincount(div_eq[idx], den_a[idx] * att[idx], nb_div))[ok] / pa[ok]
                    moy_d[ok] = (np.bincount(div_eq[idx], den_a[idx] * dfs[idx], nb_div))[ok] / pa[ok]
                pri_a = np.where(connue, moy_a[np.maximum(div_eq, 0)], 1.0)
                pri_d = np.where(connue, moy_d[np.maximum(div_eq, 0)], 1.2)
                att2 = (num_a + kappa * pri_a) / (den_a + kappa)
                den_d = np.bincount(e, w * ter[d] * att2[h], nb_eq) + np.bincount(h, w * att2[e], nb_eq)
                dfs2 = (num_d + kappa * pri_d) / (den_d + kappa)
                ter2 = (num_t + 5 * 1.3) / (np.bincount(d, w * att2[h] * dfs2[e], nb_div) + 5)
                poids = den_a * present
                c = math.exp(float((poids * np.log(att2)).sum() / max(poids.sum(), 1e-9)))
                att2, dfs2 = att2 / c, dfs2 * c
                ecart = max(float(np.abs(att2 - att)[present].max()), float(np.abs(dfs2 - dfs)[present].max()))
                att, dfs, ter = att2, dfs2, ter2
                if ecart < 2e-4:
                    break
            # niveau moyen de chaque division, pour une équipe jamais vue
            idx = np.where(present & connue)[0]
            moy_a, moy_d = np.ones(nb_div), np.full(nb_div, float(dfs[present].mean()))
            if len(idx):
                pa = np.bincount(div_eq[idx], None, nb_div)
                ok = pa > 0
                moy_a[ok] = np.bincount(div_eq[idx], att[idx], nb_div)[ok] / pa[ok]
                moy_d[ok] = np.bincount(div_eq[idx], dfs[idx], nb_div)[ok] / pa[ok]
            for m in range(i, j):
                ad, dd = att[dom[m]], dfs[dom[m]]
                ae, de = att[ext[m]], dfs[ext[m]]
                if not present[dom[m]]:
                    ad, dd, neuf[m] = moy_a[div[m]] * r["nouveau"], moy_d[div[m]] / r["nouveau"], True
                if not present[ext[m]]:
                    ae, de, neuf[m] = moy_a[div[m]] * r["nouveau"], moy_d[div[m]] / r["nouveau"], True
                lam_d[m] = ter[div[m]] * ad * de
                lam_e[m] = ae * dd
        div_eq[dom[i:j]] = div[i:j]
        div_eq[ext[i:j]] = div[i:j]
        i = j
    return lam_d, lam_e, neuf


def poisson(t: dict[str, np.ndarray], r: dict, cible: str = "buts", fin: int | None = None,
            processus: int = 4) -> dict[str, np.ndarray]:
    """Buts (ou tirs cadrés) attendus de chaque match (NaN tant que le groupe n'a pas 20 matchs)."""
    n = len(t["jour"])
    lam_d, lam_e, neuf = np.full(n, np.nan), np.full(n, np.nan), np.zeros(n, dtype=bool)
    taches, places = [], []
    for g in np.unique(t["groupe"]):
        ou = np.where((t["groupe"] == g) & ((t["jour"] < fin) if fin else True))[0]
        if not len(ou):
            continue
        equipes, dom = np.unique(np.concatenate([t["dom"][ou], t["ext"][ou]]), return_inverse=True)
        divs, div = np.unique(t["division"][ou], return_inverse=True)
        k = len(ou)
        taches.append((t["jour"][ou], dom[:k], dom[k:], div, t["bd"][ou], t["be"][ou], t["td"][ou], t["te"][ou],
                       len(equipes), len(divs), r, cible))
        places.append(ou)
    if processus > 1:
        with ProcessPoolExecutor(processus) as ex:
            sorties = list(ex.map(_poisson_groupe, taches))
    else:
        sorties = [_poisson_groupe(x) for x in taches]
    for ou, (a, b, c) in zip(places, sorties):
        lam_d[ou], lam_e[ou], neuf[ou] = a, b, c
    return {"lam_d": lam_d, "lam_e": lam_e, "neuf": neuf}


def ajuster_tirs(lam: np.ndarray, lam_tirs: np.ndarray, buts: np.ndarray) -> np.ndarray:
    """Buts attendus = exp(c0) · (buts attendus du modèle des buts)^c1 · (tirs cadrés attendus)^c2 : les trois
    coefficients du maximum de vraisemblance de Poisson."""
    x1, x2 = np.log(lam), np.log(lam_tirs)

    def f(c):
        z = c[0] + c[1] * x1 + c[2] * x2
        return float((np.exp(z) - buts * z).mean())
    return minimiser(f, [0.0, 1.0, 0.0])


def grille_scores(lam_d: np.ndarray, lam_e: np.ndarray, rho: float) -> np.ndarray:
    """Probabilité de chaque score (matchs, buts domicile, buts extérieur), correction Dixon-Coles des petits scores."""
    k = np.arange(BUTS_MAX + 1)
    fact = np.array([math.lgamma(v + 1) for v in k])
    pd_ = np.exp(k[None, :] * np.log(lam_d[:, None]) - lam_d[:, None] - fact[None, :])
    pe = np.exp(k[None, :] * np.log(lam_e[:, None]) - lam_e[:, None] - fact[None, :])
    g = pd_[:, :, None] * pe[:, None, :]
    g[:, 0, 0] *= np.clip(1 - lam_d * lam_e * rho, 0.01, None)
    g[:, 0, 1] *= np.clip(1 + lam_d * rho, 0.01, None)
    g[:, 1, 0] *= np.clip(1 + lam_e * rho, 0.01, None)
    g[:, 1, 1] *= 1 - rho
    return g / g.sum(axis=(1, 2), keepdims=True)


def marches_poisson(lam_d: np.ndarray, lam_e: np.ndarray, rho: float, lignes: dict[str, np.ndarray] | None = None
                    ) -> dict[str, np.ndarray]:
    """1N2, total 2,5 buts et, pour chaque jeu de lignes donné, handicap asiatique (domicile, extérieur, sachant
    non remboursé ; NaN hors lignes entières et demies)."""
    n = len(lam_d)
    out = {"1n2": np.full((n, 3), np.nan), "tot": np.full((n, 2), np.nan)}
    for nom in (lignes or {}):
        out["han_" + nom] = np.full((n, 2), np.nan)
    i, j = np.indices((BUTS_MAX + 1, BUTS_MAX + 1))
    ecart, total = (i - j).ravel(), (i + j).ravel()
    ok = np.where(~np.isnan(lam_d) & ~np.isnan(lam_e))[0]
    for debut in range(0, len(ok), 20000):
        m = ok[debut:debut + 20000]
        g = grille_scores(lam_d[m], lam_e[m], rho).reshape(len(m), -1)
        out["1n2"][m] = np.column_stack([g[:, ecart > 0].sum(1), g[:, ecart == 0].sum(1), g[:, ecart < 0].sum(1)])
        plus = g[:, total > 2.5].sum(1)
        out["tot"][m] = np.column_stack([plus, 1 - plus])
        for nom, lig in (lignes or {}).items():
            l = lig[m]
            valide = ~np.isnan(l) & (np.round(l * 2) == l * 2)
            v = ecart[None, :] + np.where(valide, l, 0.0)[:, None]
            gagne, perd = (g * (v > 0)).sum(1), (g * (v < 0)).sum(1)
            p = gagne / (gagne + perd)
            out["han_" + nom][m] = np.where(valide[:, None], np.column_stack([p, 1 - p]), np.nan)
    return out


# ---------------------------------------------------------------- mesures

def gagnants(t: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    ecart, total = t["bd"] - t["be"], t["bd"] + t["be"]
    out = {"1n2": np.where(ecart > 0, 0, np.where(ecart == 0, 1, 2)), "tot": np.where(total > 2.5, 0, 1)}
    for nom in COTES_HANDICAP:
        v = ecart + t["han_" + nom][:, 2]
        out["han_" + nom] = np.where(v > 0, 0, np.where(v < 0, 1, -1))       # −1 : remboursé ou ligne absente
    return out


def melange(ref: np.ndarray, mod: np.ndarray, a: float, b: float) -> np.ndarray:
    """Mélange log-linéaire : p ∝ ref^a · mod^b."""
    z = a * np.log(ref) + b * np.log(mod)
    p = np.exp(z - z.max(axis=1, keepdims=True))
    return p / p.sum(axis=1, keepdims=True)


def ajuster_melange(ref: np.ndarray, mod: np.ndarray, gagnant: np.ndarray, libre: tuple[bool, bool] = (True, True)
                    ) -> tuple[np.ndarray, np.ndarray]:
    """Exposants (a, b) du maximum de vraisemblance, par Newton, et leur erreur type. ``libre`` : exposants ajustés
    (un exposant figé vaut 1 pour la référence, 0 pour le modèle)."""
    x = np.stack([np.log(ref), np.log(mod)], axis=2)             # (n, issues, 2)
    theta = np.array([1.0, 0.0])
    actif = np.array(libre)
    idx = np.arange(len(ref))
    cov = np.zeros((2, 2))
    for _ in range(50):
        z = x @ theta
        p = np.exp(z - z.max(axis=1, keepdims=True))
        p /= p.sum(axis=1, keepdims=True)
        moy = (p[:, :, None] * x).sum(axis=1)
        grad = (x[idx, gagnant] - moy).sum(axis=0)
        cen = x - moy[:, None, :]
        hess = np.einsum("nk,nki,nkj->ij", p, cen, cen)
        h = hess[np.ix_(actif, actif)]
        pas = np.linalg.solve(h, grad[actif])
        theta[actif] += pas
        cov = np.zeros((2, 2))
        cov[np.ix_(actif, actif)] = np.linalg.inv(h)
        if np.abs(pas).max() < 1e-9:
            break
    return theta, np.sqrt(np.diag(cov))


def p_bilaterale(z: float) -> float:
    return math.erfc(abs(z) / math.sqrt(2))


def holm(p: list[float]) -> list[float]:
    ordre = np.argsort(p)
    out, courant = [0.0] * len(p), 0.0
    for rang, i in enumerate(ordre):
        courant = max(courant, min(1.0, (len(p) - rang) * p[i]))
        out[i] = courant
    return out


def pente_ols(x: np.ndarray, y: np.ndarray) -> tuple[float, float, float]:
    """Pente de y sur x (avec constante), erreur type robuste, R²."""
    xc, yc = x - x.mean(), y - y.mean()
    sxx = float((xc * xc).sum())
    b = float((xc * yc).sum()) / sxx
    res = yc - b * xc
    et = math.sqrt(float((xc * xc * res * res).sum())) / sxx
    return b, et, 1 - float((res * res).sum()) / float((yc * yc).sum())


# ---------------------------------------------------------------- affichage

def f4(x: float) -> str:
    return f"{x:.4f}".replace(".", ",")


def f2(x: float, d: int = 2) -> str:
    return f"{x:.{d}f}".replace(".", ",")


def pc(x: float, d: int = 1) -> str:
    return f"{100 * x:+.{d}f} %".replace(".", ",")


def ic(tr: tuple[float, float, float], facteur: float = 1e4, d: int = 1) -> str:
    m, a, b = (facteur * v for v in tr)
    gras = "**" if (a > 0 or b < 0) else ""
    return f"{gras}{m:+.{d}f} [{a:+.{d}f} ; {b:+.{d}f}]{gras}".replace(".", ",")


def entier(x: int) -> str:
    return f"{x:,}".replace(",", " ")


# ---------------------------------------------------------------- calcul des modèles

def calculer(t: dict[str, np.ndarray], fin: int | None = None, elo_r: dict | None = None,
             poisson_r: dict | None = None, xi_tirs: float | None = None, quoi: str = "tout") -> dict:
    """Prévisions des trois modèles pour chaque match. ``fin`` : ne rien calculer à partir de ce jour (réglage)."""
    elo_r, poisson_r = elo_r or ELO, poisson_r or POISSON
    xi_tirs = XI_TIRS if xi_tirs is None else xi_tirs
    gagne = gagnants(t)
    reglage = (t["jour"] >= DEBUT_REGLAGE) & (t["jour"] < DEBUT_TEST)
    out: dict = {"gagnant": gagne, "reglage": reglage}
    if quoi in ("tout", "elo"):
        e = elo(t, elo_r)
        pente, seuil = ajuster_elo(e["x"][reglage], gagne["1n2"][reglage])
        out["elo"] = {"1n2": proba_elo(e["x"], pente, seuil)}
        out["elo_etat"], out["elo_logit"] = e, (pente, seuil)
    lignes = {nom: t["han_" + nom][:, 2] for nom in COTES_HANDICAP}
    po = poisson(t, poisson_r, "buts", fin)
    out["poisson"] = marches_poisson(po["lam_d"], po["lam_e"], poisson_r["rho"], lignes)
    out["poisson_etat"] = po
    if quoi == "tout":
        pt = poisson(t, dict(poisson_r, xi=xi_tirs), "tirs", fin)
        ok = reglage & ~np.isnan(po["lam_d"]) & ~np.isnan(pt["lam_d"])
        c = ajuster_tirs(np.concatenate([po["lam_d"][ok], po["lam_e"][ok]]),
                         np.concatenate([pt["lam_d"][ok], pt["lam_e"][ok]]),
                         np.concatenate([t["bd"][ok], t["be"][ok]]))
        lam_d = np.exp(c[0] + c[1] * np.log(po["lam_d"]) + c[2] * np.log(pt["lam_d"]))
        lam_e = np.exp(c[0] + c[1] * np.log(po["lam_e"]) + c[2] * np.log(pt["lam_e"]))
        out["tirs"] = marches_poisson(lam_d, lam_e, poisson_r["rho"], lignes)
        out["tirs_coef"] = c
    return out


def perte(p: np.ndarray, gagnant: np.ndarray, ou: np.ndarray) -> float:
    ou = ou & ~np.isnan(p[:, 0])
    return float(log_loss(p[ou], gagnant[ou]).mean())


# ---------------------------------------------------------------- réglage (matchs d'avant le 01/07/2019)

def regler(t: dict[str, np.ndarray]) -> None:
    avant = t["jour"] < DEBUT_TEST
    t = {k: v[avant] for k, v in t.items()}
    gagne = gagnants(t)["1n2"]
    note = (t["jour"] >= DEBUT_REGLAGE)
    print(f"Matchs d'avant le 01/07/2019 : {entier(len(gagne))}, dont notés (depuis le 01/07/2014) : "
          f"{entier(int(note.sum()))}\n")

    def perte_elo(r: dict) -> float:
        e = elo(t, r)
        pente, seuil = ajuster_elo(e["x"][note], gagne[note])
        return float(log_loss(proba_elo(e["x"][note], pente, seuil), gagne[note]).mean())

    grilles = {"k": [7, 10, 14, 18], "gamma": [0.3, 0.6, 0.9, 1.2], "terrain": [60, 80, 100],
               "k_terrain": [0.2, 0.6, 1.2, 2.5], "retour": [0.1, 0.2, 0.3, 0.4], "ecart_niveau": [50, 100, 150, 250],
               "ecart_nouveau": [0, 50, 100]}
    r = dict(ELO)
    meilleur = perte_elo(r)
    print("## Elo\n")
    for tour in range(2):
        for cle, valeurs in grilles.items():
            for v in valeurs:
                if v == r[cle]:
                    continue
                essai = dict(r, **{cle: float(v)})
                p = perte_elo(essai)
                if p < meilleur - 1e-6:
                    r, meilleur = essai, p
            print(f"tour {tour + 1}, {cle} : {r[cle]} -> log-loss {f4(meilleur)}", flush=True)
    print(f"\nElo retenu : {r}, log-loss {f4(meilleur)}\n")

    def perte_poisson(rp: dict) -> float:
        po = poisson(t, rp)
        return perte(marches_poisson(po["lam_d"], po["lam_e"], rp["rho"])["1n2"], gagne, note)

    print("## Poisson\n")
    grilles = {"xi": [0.0012, 0.0018, 0.0026, 0.0035, 0.005], "kappa": [3.0, 6.0, 12.0], "nouveau": [0.8, 0.9, 1.0]}
    rp = dict(POISSON)
    meilleur = perte_poisson(rp)
    for cle, valeurs in grilles.items():
        for v in valeurs:
            if v == rp[cle]:
                continue
            essai = dict(rp, **{cle: v})
            p = perte_poisson(essai)
            if p < meilleur - 1e-6:
                rp, meilleur = essai, p
        print(f"{cle} : {rp[cle]} -> log-loss {f4(meilleur)}", flush=True)
    po = poisson(t, rp)
    for rho in (-0.12, -0.09, -0.06, -0.03, 0.0):
        p = marches_poisson(po["lam_d"], po["lam_e"], rho)["1n2"]
        print(f"rho {rho} : log-loss {f4(perte(p, gagne, note))}")
    print(f"\nPoisson retenu (hors rho) : {rp}\n\n## Poisson + tirs cadrés (matchs avec tirs)\n")
    avec = note & ~np.isnan(po["lam_d"])
    for xi in (0.0026, 0.005, 0.008, 0.012, 0.02):
        pt = poisson(t, dict(rp, xi=xi), "tirs")
        ok = avec & ~np.isnan(pt["lam_d"])
        c = ajuster_tirs(np.concatenate([po["lam_d"][ok], po["lam_e"][ok]]),
                         np.concatenate([pt["lam_d"][ok], pt["lam_e"][ok]]),
                         np.concatenate([t["bd"][ok], t["be"][ok]]))
        ld = np.exp(c[0] + c[1] * np.log(po["lam_d"]) + c[2] * np.log(pt["lam_d"]))
        le = np.exp(c[0] + c[1] * np.log(po["lam_e"]) + c[2] * np.log(pt["lam_e"]))
        p2 = marches_poisson(ld, le, rp["rho"])["1n2"]
        p1 = marches_poisson(po["lam_d"], po["lam_e"], rp["rho"])["1n2"]
        print(f"oubli des tirs {xi} : {entier(int(ok.sum()))} matchs, coefficients {np.round(c, 3)}, log-loss "
              f"{f4(perte(p2, gagne, ok))} (buts seuls, mêmes matchs : {f4(perte(p1, gagne, ok))})", flush=True)


# ---------------------------------------------------------------- rapport

MODELES = (("elo", "Elo"), ("poisson", "Poisson (Dixon-Coles)"), ("tirs", "Poisson + tirs cadrés"))
REFERENCES = (("pin_c", "Pinnacle, clôture"), ("pin_o", "Pinnacle, avant-match"), ("b365_c", "bet365, clôture"),
              ("b365_o", "bet365, avant-match"), ("moy_c", "Moyenne du marché, clôture"),
              ("bfe_c", "Betfair Exchange, clôture"))


def justes(t: dict[str, np.ndarray], cle: str) -> np.ndarray:
    """Probabilités sans marge (méthode puissance, celle du site) ; NaN quand la cote manque."""
    c = t[cle][:, :2] if cle.startswith("han_") else t[cle]
    out = np.full(c.shape, np.nan)
    ok = ~np.isnan(c[:, 0])
    if ok.any():
        out[ok] = retirer_marge(c[ok], "puissance")
    return out


def rapport(t: dict[str, np.ndarray], tirages: int) -> None:
    rng = np.random.default_rng(GRAINE)
    s = calculer(t)
    gagne = s["gagnant"]
    test, reglage = t["jour"] >= DEBUT_TEST, s["reglage"]
    ref = {m + "_" + nom: justes(t, m + "_" + nom) for m, groupe in (("1n2", COTES_1N2), ("tot", COTES_TOTAL),
                                                                    ("han", COTES_HANDICAP)) for nom in groupe}
    tirs_connus = ~np.isnan(t["td"])
    print(f"Matchs lus : {entier(len(test))} du {date.fromordinal(int(t['jour'][0])):%d/%m/%Y} au "
          f"{date.fromordinal(int(t['jour'][-1])):%d/%m/%Y}. Réglage : {entier(int(reglage.sum()))} matchs "
          f"(01/07/2014 au 30/06/2019). Test : {entier(int(test.sum()))} matchs depuis le 01/07/2019, dont "
          f"{entier(int((test & ~np.isnan(ref['1n2_pin_c'][:, 0])).sum()))} avec la clôture Pinnacle.")
    pente, seuil = s["elo_logit"]
    c = s["tirs_coef"]
    print(f"Elo : P(domicile) = σ({f2(pente, 3)}·x − {f2(seuil, 3)}), x en centaines de points. Poisson + tirs : "
          f"buts attendus = exp({f2(c[0], 3)}) · (buts attendus)^{f2(c[1], 3)} · (tirs cadrés attendus)^{f2(c[2], 3)}.\n")

    # ---- 1. niveau des modèles
    print("## 1. Les modèles face à Pinnacle (test, matchs jamais vus par les réglages)\n")
    print("Écart de log-loss avec la référence, ×10⁴, intervalle à 95 % par bootstrap sur les matchs ; positif = "
          "le modèle est moins bon. Pente : 1 = calibré, moins de 1 = probabilités trop tranchées.\n")
    lig = []
    for marche, nom_marche, cle_g in (("1n2", "1N2", "1n2"), ("tot", "Total 2,5 buts", "tot"),
                                      ("han", "Handicap asiatique", "han_pin_c")):
        r = ref[marche + "_pin_c"]
        for cle, nom in MODELES:
            cle_p = "han_pin_c" if marche == "han" else marche
            if cle_p not in s[cle]:
                continue
            p = s[cle][cle_p]
            ou = test & ~np.isnan(r[:, 0]) & ~np.isnan(p[:, 0]) & (gagne[cle_g] >= 0)
            if cle == "tirs":
                ou &= tirs_connus
            g = gagne[cle_g][ou]
            lm, lr = log_loss(p[ou], g), log_loss(r[ou], g)
            beta = pente_calibration(p[ou], g)
            beta_r = pente_calibration(r[ou], g)
            lig.append([nom_marche, nom, entier(int(ou.sum())), f4(float(lm.mean())), f4(float(lr.mean())),
                        ic(intervalle(lm - lr, rng, tirages)), f4(float(brier(p[ou], g).mean())),
                        f4(float(brier(r[ou], g).mean())),
                        f"{f2(beta, 3)} ± {f2(1.96 * erreur_pente(p[ou], beta), 3)}",
                        f"{f2(beta_r, 3)} ± {f2(1.96 * erreur_pente(r[ou], beta_r), 3)}"])
    print(tableau(["Marché", "Modèle", "Matchs", "Log-loss modèle", "Log-loss Pinnacle", "Écart", "Brier modèle",
                   "Brier Pinnacle", "Pente modèle", "Pente Pinnacle"], lig))

    morceaux = []
    for marche, nom_marche in (("1n2", "1N2"), ("tot", "total 2,5 buts")):
        a, b = s["tirs"][marche], s["poisson"][marche]
        ou = test & ~np.isnan(ref[marche + "_pin_c"][:, 0]) & ~np.isnan(a[:, 0]) & ~np.isnan(b[:, 0]) & tirs_connus
        ecart = log_loss(a[ou], gagne[marche][ou]) - log_loss(b[ou], gagne[marche][ou])
        morceaux.append(f"{nom_marche} {ic(intervalle(ecart, rng, tirages))} ({entier(int(ou.sum()))} matchs)")
    print("\nPoisson + tirs moins Poisson, sur les mêmes matchs : " + " ; ".join(morceaux) + ".")

    # repère : que vaut un modèle sans information (fréquences de la période de réglage)
    r = ref["1n2_pin_c"]
    ou = test & ~np.isnan(r[:, 0]) & ~np.isnan(s["poisson"]["1n2"][:, 0])
    freq = np.bincount(gagne["1n2"][reglage], minlength=3) / reglage.sum()
    base = float(log_loss(np.tile(freq, (int(ou.sum()), 1)), gagne["1n2"][ou]).mean())
    lr = float(log_loss(r[ou], gagne["1n2"][ou]).mean())
    print(f"\nRepère 1N2 : fréquences fixes (domicile {pc(freq[0]).lstrip('+')}, nul {pc(freq[1]).lstrip('+')}, "
          f"extérieur {pc(freq[2]).lstrip('+')}) : log-loss {f4(base)}. Pinnacle gagne {f4(base - lr)} sur ce "
          "repère ; part de ce gain obtenue par chaque modèle :", end=" ")
    print(" ; ".join(f"{nom} {pc(1 - (perte(s[cle]['1n2'], gagne['1n2'], ou) - lr) / (base - lr), 0).lstrip('+')}"
                     for cle, nom in MODELES[:2]) + ".\n")

    # ---- calibration par tranche
    print("### Calibration par tranche (1N2, toutes issues, test, modèle Poisson)\n")
    bornes = (0.0, 0.05, 0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 1.0001)
    ou = test & ~np.isnan(r[:, 0]) & ~np.isnan(s["poisson"]["1n2"][:, 0])
    y = np.zeros((int(ou.sum()), 3))
    y[np.arange(len(y)), gagne["1n2"][ou]] = 1
    lig = []
    for a, b in zip(bornes[:-1], bornes[1:]):
        ligne = [f"{round(100 * a)} à {min(100, round(100 * b))} %"]
        for p in (s["poisson"]["1n2"][ou], r[ou]):
            m = (p >= a) & (p < b)
            k = int(m.sum())
            obs = float(y[m].mean()) if k else math.nan
            et = 1.96 * math.sqrt(obs * (1 - obs) / k) if k else math.nan
            ligne += [entier(k), f2(100 * float(p[m].mean())) if k else "—",
                      f"{f2(100 * obs)} ± {f2(100 * et)}" if k else "—"]
        lig.append(ligne)
    print(tableau(["Tranche", "Issues (modèle)", "Annoncé par le modèle", "Observé", "Issues (Pinnacle)",
                   "Annoncé par Pinnacle", "Observé"], lig))

    # ---- 2. information ajoutée
    print("\n## 2. Le modèle apporte-t-il une information que la référence n'a pas ?\n")
    print("Mélange p ∝ référence^a · modèle^b. « b » : poids du modèle (0 = il n'apporte rien), ajusté sur la "
          "période d'ajustement puis figé. « Gain hors échantillon » : log-loss du mélange figé moins celui de la "
          "référence recalibrée seule (a ajusté sur la même période, b = 0), ×10⁴, sur la période de jugement ; "
          "négatif = le modèle ajoute de l'information. « b sur la période de jugement » : ajusté sur elle-même, "
          "± 1,96 erreur type.\n")
    lig = []
    for marche, nom_marche in (("1n2", "1N2"), ("tot", "Total 2,5 buts"), ("han", "Handicap asiatique")):
        for nom_ref, libelle in REFERENCES:
            cle_ref = marche + "_" + nom_ref
            if cle_ref not in ref:
                continue
            r = ref[cle_ref]
            cle_p = ("han_" + nom_ref) if marche == "han" else marche
            cle_g = cle_p if marche == "han" else marche
            for cle, nom in MODELES:
                if cle_p not in s[cle]:
                    continue
                p = s[cle][cle_p]
                ok = ~np.isnan(r[:, 0]) & ~np.isnan(p[:, 0]) & (gagne[cle_g] >= 0) & (t["jour"] >= DEBUT_REGLAGE)
                if cle == "tirs":
                    ok &= tirs_connus
                coupe = DEBUT_TEST if (ok & ~test).sum() > 5000 else MILIEU_TEST
                aj, ju = ok & (t["jour"] < coupe), ok & (t["jour"] >= coupe)
                if aj.sum() < 3000 or ju.sum() < 3000:
                    if ok.sum() < 3000:
                        continue
                    th, et = ajuster_melange(r[ok], p[ok], gagne[cle_g][ok])
                    gras = "**" if abs(th[1]) > 1.96 * et[1] else ""
                    lig.append([nom_marche, libelle, nom, "—", "—", "—", entier(int(ok.sum())),
                                f"{gras}{f2(th[1], 3)} ± {f2(1.96 * et[1], 3)}{gras}"])
                    continue
                th, _ = ajuster_melange(r[aj], p[aj], gagne[cle_g][aj])
                th0, _ = ajuster_melange(r[aj], p[aj], gagne[cle_g][aj], (True, False))
                g = gagne[cle_g][ju]
                gain = log_loss(melange(r[ju], p[ju], *th), g) - log_loss(melange(r[ju], p[ju], *th0), g)
                thj, etj = ajuster_melange(r[ju], p[ju], g)
                lig.append([nom_marche, libelle, nom, entier(int(aj.sum())), f"{f2(th[0], 3)} · {f2(th[1], 3)}",
                            ic(intervalle(gain, rng, tirages)), entier(int(ju.sum())),
                            f"{'**' if abs(thj[1]) > 1.96 * etj[1] else ''}{f2(thj[1], 3)} ± {f2(1.96 * etj[1], 3)}"
                            f"{'**' if abs(thj[1]) > 1.96 * etj[1] else ''}"])
    print(tableau(["Marché", "Référence", "Modèle", "Matchs d'ajustement", "a · b ajustés", "Gain hors échantillon",
                   "Matchs de jugement", "b sur la période de jugement"], lig))

    # ---- 3. par segment
    print("\n## 3. Où ? Poids du modèle par segment (1N2, clôture Pinnacle, test)\n")
    print("Modèle : Poisson (toutes les ligues). « b » ajusté sur le segment lui-même (descriptif) ; p corrigée de "
          "Holm sur tous les segments du tableau. « Écart » : log-loss du modèle moins celui de Pinnacle, ×10⁴.\n")
    r, p = ref["1n2_pin_c"], s["poisson"]["1n2"]
    ok = test & ~np.isnan(r[:, 0]) & ~np.isnan(p[:, 0])
    g = gagne["1n2"]
    favori = r.max(axis=1)
    desaccord = np.abs(p - r).max(axis=1)
    joues = s["elo_etat"]["joues"]
    mois = np.array([date.fromordinal(int(j)).month for j in t["jour"]])
    annee = np.array([date.fromordinal(int(j)).year for j in t["jour"]])
    segments: list[tuple[str, np.ndarray]] = [("Tous", ok)]
    segments += [(nom, ok & (t["famille"] == nom)) for nom, _ in FAMILLES] + [(FAMILLE_PLUS, ok & (t["famille"] == FAMILLE_PLUS))]
    segments += [("Début de saison (une équipe à moins de 6 matchs joués)", ok & (joues < 6)),
                 ("Reste de la saison", ok & (joues >= 6)),
                 ("Une équipe jamais vue (promue de hors fichiers)", ok & s["poisson_etat"]["neuf"]),
                 ("Favori Pinnacle à moins de 45 %", ok & (favori < 0.45)),
                 ("Favori de 45 à 60 %", ok & (favori >= 0.45) & (favori < 0.60)),
                 ("Favori à 60 % et plus", ok & (favori >= 0.60)),
                 ("Désaccord modèle / Pinnacle sous 5 points", ok & (desaccord < 0.05)),
                 ("Désaccord de 5 à 10 points", ok & (desaccord >= 0.05) & (desaccord < 0.10)),
                 ("Désaccord de 10 points et plus", ok & (desaccord >= 0.10)),
                 ("Matchs à huis clos (mars 2020 à juin 2021)",
                  ok & (t["jour"] >= date(2020, 3, 15).toordinal()) & (t["jour"] < date(2021, 7, 1).toordinal())),
                 ("Décembre à février", ok & np.isin(mois, (12, 1, 2)))]
    segments += [(f"Année {a}", ok & (annee == a)) for a in sorted(set(annee[ok]))]
    resultats = []
    for nom, m in segments:
        if m.sum() < 500:
            continue
        th, et = ajuster_melange(r[m], p[m], g[m])
        ecart = intervalle(log_loss(p[m], g[m]) - log_loss(r[m], g[m]), rng, tirages)
        resultats.append((nom, int(m.sum()), th, et, ecart))
    corr = holm([p_bilaterale(th[1] / et[1]) for _, _, th, et, _ in resultats])
    lig = [[nom, entier(k), ic(ecart), f"{f2(th[1], 3)} ± {f2(1.96 * et[1], 3)}", f2(pcorr, 3)]
           for (nom, k, th, et, ecart), pcorr in zip(resultats, corr)]
    print(tableau(["Segment", "Matchs", "Écart modèle − Pinnacle", "b (poids du modèle)", "p corrigée (Holm)"], lig))

    # ---- 4. mouvement de la cote
    print("\n## 4. Le modèle annonce-t-il le mouvement de Pinnacle entre l'avant-match et la clôture ?\n")
    print("Régression de (clôture − avant-match) sur (modèle − avant-match), en logit de la victoire à domicile "
          "(ou du « plus de 2,5 »). Pente 0 : le modèle ne sait rien que l'avant-match ne sache ; pente 1 : la "
          "clôture rejoint le modèle.\n")
    logit = lambda v: np.log(v / (1 - v))            # noqa: E731
    lig = []
    for marche, nom_marche in (("1n2", "1N2, domicile"), ("tot", "Total 2,5 buts, plus")):
        for cle, nom in MODELES:
            if marche not in s[cle]:
                continue
            o, c, p = ref[marche + "_pin_o"][:, 0], ref[marche + "_pin_c"][:, 0], s[cle][marche][:, 0]
            for periode, masque in (("réglage", reglage), ("test", test)):
                m = masque & ~np.isnan(o) & ~np.isnan(c) & ~np.isnan(p)
                if cle == "tirs":
                    m &= tirs_connus
                if m.sum() < 3000:
                    continue
                b, et, r2 = pente_ols(logit(p[m]) - logit(o[m]), logit(c[m]) - logit(o[m]))
                lig.append([nom_marche, nom, periode, entier(int(m.sum())),
                            f"{'**' if abs(b) > 1.96 * et else ''}{f2(b, 3)} ± {f2(1.96 * et, 3)}"
                            f"{'**' if abs(b) > 1.96 * et else ''}", pc(r2, 2).lstrip("+")])
    print(tableau(["Marché", "Modèle", "Période", "Matchs", "Pente", "Part du mouvement expliquée"], lig))

    # ---- 5. paris
    print("\n## 5. Parier avec ou contre le modèle (test, cote ≤ 5, 1N2)\n")
    print("Un pari par issue retenue, mise fixe. ROI par pari, intervalle à 95 % par bootstrap sur les matchs. "
          "« Avec le modèle » : la cote dépasse la cote juste du modèle d'au moins le seuil. « Contre le modèle » : "
          "Pinnacle (sans marge, au même moment) donne à l'issue une probabilité supérieure d'au moins le seuil à "
          "celle du modèle. « Pinnacle (méthode du site) » : la cote dépasse la cote juste Pinnacle du seuil.\n")
    lig = []
    modeles_5 = (("Poisson", s["poisson"]["1n2"], None), ("Poisson + tirs", s["tirs"]["1n2"], tirs_connus))
    for nom_cote, cle_cote, cle_pin in (("Pinnacle, clôture", "1n2_pin_c", "1n2_pin_c"),
                                        ("bet365, avant-match", "1n2_b365_o", "1n2_pin_o"),
                                        ("bet365, clôture", "1n2_b365_c", "1n2_pin_c"),
                                        ("Meilleure cote du marché, clôture", "1n2_max_c", "1n2_pin_c")):
        cotes, pin = t[cle_cote], ref[cle_pin]
        base = test & ~np.isnan(cotes[:, 0]) & ~np.isnan(pin[:, 0]) & ~np.isnan(s["poisson"]["1n2"][:, 0])
        essais = [("Toutes les issues", "—", base[:, None] & (cotes <= 5.0), None)]
        for nom_mod, p, filtre in modeles_5:
            m = base & ~np.isnan(p[:, 0]) & (filtre if filtre is not None else True)
            essais += [(f"Avec le modèle {nom_mod}", f"≥ {round(100 * x)} %", m[:, None] & (p * cotes - 1 >= x)
                        & (cotes <= 5.0), p) for x in (0.02, 0.05, 0.10)]
            essais += [(f"Contre le modèle {nom_mod}", f"≥ {round(100 * x)} %", m[:, None] & (pin / p - 1 >= x)
                        & (cotes <= 5.0), p) for x in (0.10, 0.25, 0.50)]
        if cle_cote != cle_pin:
            essais += [("Pinnacle (méthode du site)", f"≥ {round(100 * x)} %", base[:, None] & (pin * cotes - 1 >= x)
                        & (cotes <= 5.0), None) for x in (0.02, 0.05, 0.10)]
        for nom_sig, seuil_, pari, p in essais:
            if pari.sum() < 200:
                continue
            lignes_, issues = np.where(pari)
            gain = np.where(g[lignes_] == issues, cotes[lignes_, issues] - 1, -1.0)
            lig.append([nom_cote, nom_sig, seuil_, entier(len(gain)), f2(float(cotes[lignes_, issues].mean())),
                        "—" if p is None else pc(float((p[lignes_, issues] * cotes[lignes_, issues] - 1).mean())),
                        pc(float((pin[lignes_, issues] * cotes[lignes_, issues] - 1).mean())),
                        ic(intervalle(gain, rng, tirages, lignes_), 100, 1)])
    print(tableau(["Cotes jouées", "Sélection", "Seuil", "Paris", "Cote moyenne", "Écart moyen selon le modèle",
                   "Écart moyen selon Pinnacle", "ROI en % [IC 95 %]"], lig))

    # ---- 6. le modèle trie-t-il les values du site ?
    print("\n## 6. Le modèle trie-t-il les values repérées par Pinnacle ? (même moment)\n")
    print("Paris que la méthode du site aurait pris (cote ≥ cote juste Pinnacle + 2 %, cote ≤ 5), séparés selon "
          "l'avis du modèle Poisson sur la même issue. « Avis » : probabilité du modèle / probabilité Pinnacle − 1. "
          "La meilleure cote du marché est celle du plus offrant parmi des dizaines de bookmakers : personne ne "
          "l'obtient à chaque pari.\n")
    lig = []
    for moment, cle_cote, cle_pin in (("bet365, avant-match", "1n2_b365_o", "1n2_pin_o"),
                                      ("bet365, clôture", "1n2_b365_c", "1n2_pin_c"),
                                      ("Meilleure cote du marché, clôture", "1n2_max_c", "1n2_pin_c")):
        cotes, pin, p = t[cle_cote], ref[cle_pin], s["poisson"]["1n2"]
        m = test & ~np.isnan(cotes[:, 0]) & ~np.isnan(pin[:, 0]) & ~np.isnan(p[:, 0])
        pari = m[:, None] & (pin * cotes - 1 >= 0.02) & (cotes <= 5.0)
        lignes_, issues = np.where(pari)
        gain = np.where(g[lignes_] == issues, cotes[lignes_, issues] - 1, -1.0)
        avis = p[lignes_, issues] / pin[lignes_, issues] - 1
        for nom, sel in (("Tous", np.ones(len(gain), dtype=bool)), ("Le modèle donne plus que Pinnacle", avis > 0),
                         ("Le modèle donne moins que Pinnacle", avis <= 0),
                         ("Le modèle voit aussi ≥ 2 % d'écart sur la cote", p[lignes_, issues] * cotes[lignes_, issues] - 1 >= 0.02),
                         ("Le modèle donne au moins 10 % de moins que Pinnacle", avis <= -0.10)):
            if sel.sum() < 100:
                continue
            lig.append([moment, nom, entier(int(sel.sum())), ic(intervalle(gain[sel], rng, tirages, lignes_[sel]), 100, 1)])
        b, et, _ = pente_ols(avis, gain)
        lig.append([moment, "Pente du gain sur l'avis du modèle", entier(len(gain)),
                    f"{'**' if abs(b) > 1.96 * et else ''}{f2(b, 2)} ± {f2(1.96 * et, 2)}"
                    f"{'**' if abs(b) > 1.96 * et else ''}"])
    print(tableau(["Cotes jouées", "Paris", "Nombre", "ROI en % [IC 95 %]"], lig))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("commande", choices=("regler", "mesurer"))
    ap.add_argument("--football", type=Path, required=True)
    ap.add_argument("--football-plus", type=Path)
    ap.add_argument("--tirages", type=int, default=2000)
    args = ap.parse_args(argv)
    t = lire_matchs(args.football, args.football_plus)
    if args.commande == "regler":
        regler(t)
    else:
        rapport(t, args.tirages)
    return 0


if __name__ == "__main__":
    sys.exit(main())
