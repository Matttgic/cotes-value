"""Avantage réel : ROI, incertitude, tests corrigés et CLV de chaque stratégie et de chaque bookmaker. Lecture seule.

Usage : python scripts/avantage_reel.py --donnees CHEMIN [--tirages 50000] [--json FICHIER] [--markdown FICHIER]
CHEMIN = branche « donnees » extraite (paris.json, archives/, recommandees.json). Demande numpy
(requirements-dev.txt). Environ 8 minutes avec 50 000 tirages ; « --tirages 5000 » pour un aperçu en une minute
(les p-valeurs corrigées sont alors plafonnées). Même graine, mêmes données : mêmes chiffres.
Sortie standard : le tableau court de docs/avantage-reel.md ; « --markdown » : docs/avantage-reel-tableaux.md.

Résumé de la méthode :
- paris réglés seulement ; ROI = gain / mises, remboursés comptés dans les mises (convention du site) ;
- l'unité de hasard est le match (cotes/evenements.identites), jamais le pari : bootstrap par match ;
- intervalle à 95 % et p-valeurs : bootstrap studentisé (bootstrap-t), qui tient compte des gains très asymétriques ;
- correction sur toutes les lignes testées (stratégies, seuils du laboratoire, bookmakers, références, tranches),
  dans les deux sens (ROI > 0 et ROI < 0) : Holm (aucune fausse découverte) et Benjamini-Hochberg (5 % de fausses
  découvertes) ;
- CLV : clôture Pinnacle sans marge quand elle existe (la référence du pari, ou celle du même pari repéré aussi par
  Pinnacle), sinon clôture de la référence du pari ; lue dans les 30 minutes avant le début (simulation.clv_finale).
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from statistics import NormalDist
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cotes import pauses, reglement, simulation, stockage  # noqa: E402
from cotes.convergence import CONVERGENCE, STRATEGIES, cle_selection, paris_convergence  # noqa: E402
from cotes.evenements import identites  # noqa: E402
from cotes.laboratoire import DEBUT_SUIVI, REGLES as REGLES_LABO, selectionner  # noqa: E402
from cotes.strategie_recommandee import charger_fusions  # noqa: E402
from cotes.strategies_prudentes import VARIANTES, selections_prudentes  # noqa: E402

REGLES = tuple(reglement.GAIN)
PLAFOND_LE = "2026-11-11T15:30"     # plafond de cote à 5 décidé le 11/11/2026 (docs/audit-bilans.md, problème 1)
GRAINE = 20261113
MIN_PARIS = 30                      # en dessous : ni test ni correction, « trop peu de paris »
MIN_MATCHS = 10
MIN_CLV = 30                        # CLV mesurées minimum pour tester la CLV
PART_PINNACLE_MIN = 0.5             # « probable » : CLV Pinnacle mesurée sur au moins la moitié des paris réglés
ALPHA = 0.05
PUISSANCE = 0.80


def heure(s) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else None


# ---------------------------------------------------------------- statistiques

def grappes(valeurs: np.ndarray, poids: np.ndarray, cles: list) -> tuple[np.ndarray, np.ndarray]:
    """Somme des valeurs et des poids par match."""
    rang: dict = {}
    idx = np.fromiter((rang.setdefault(c, len(rang)) for c in cles), dtype=np.int64, count=len(cles))
    return np.bincount(idx, weights=valeurs, minlength=len(rang)), np.bincount(idx, weights=poids, minlength=len(rang))


def rapport(num: np.ndarray, den: np.ndarray, tirages: int, rng: np.random.Generator) -> dict | None:
    """Rapport somme(num) / somme(den) sur des matchs, avec bootstrap par match.

    ROI : num = gain du match, den = mises du match. CLV moyenne : num = somme des CLV, den = nombre de paris.
    Rend l'estimation, l'erreur type (estimateur du ratio), l'intervalle à 95 % et les deux p-valeurs unilatérales
    du bootstrap-t : p_pos teste « le vrai rapport est ≤ 0 », p_neg teste « il est ≥ 0 ». L'intervalle exclut zéro
    exactement quand la p-valeur de son sens est sous 2,5 %.
    """
    k = len(num)
    total = float(den.sum())
    if k < 2 or total <= 0:
        return None
    r = float(num.sum()) / total
    residus = num - r * den
    et = math.sqrt(float((residus ** 2).sum()) * k / (k - 1)) / total
    base = np.column_stack([num, den, num * num, num * den, den * den])
    stats = []
    proba = np.full(k, 1.0 / k)
    lot = max(1, min(tirages, 4_000_000 // k))
    fait = 0
    while fait < tirages:
        n = min(lot, tirages - fait)
        s = rng.multinomial(k, proba, size=n) @ base
        sd = s[:, 1]
        ok = sd > 0
        rb = np.where(ok, s[:, 0] / np.where(ok, sd, 1.0), np.nan)
        var = np.clip(s[:, 2] - 2 * rb * s[:, 3] + rb * rb * s[:, 4], 0, None) * k / (k - 1)
        etb = np.sqrt(var) / np.where(ok, sd, 1.0)
        with np.errstate(divide="ignore", invalid="ignore"):
            stats.append(np.where(etb > 0, (rb - r) / etb, np.nan))
        fait += n
    tb = np.concatenate(stats)
    tb = tb[~np.isnan(tb)]
    out = {"valeur": r, "erreur_type": et, "ic": None, "matchs": k, "p_pos": None, "p_neg": None}
    if et > 0 and len(tb) >= 0.9 * tirages:        # sinon trop de tirages dégénérés : ni intervalle ni test
        t = r / et
        bas, haut = np.percentile(tb, [2.5, 97.5])
        out["ic"] = [float(r - haut * et), float(r - bas * et)]
        out["p_pos"] = float((1 + (tb >= t).sum()) / (len(tb) + 1))
        out["p_neg"] = float((1 + (tb <= t).sum()) / (len(tb) + 1))
    return out


def holm(pvals: list[float]) -> list[float]:
    m = len(pvals)
    ordre = sorted(range(m), key=lambda i: pvals[i])
    out, courant = [0.0] * m, 0.0
    for rang, i in enumerate(ordre):
        courant = max(courant, min(1.0, (m - rang) * pvals[i]))
        out[i] = courant
    return out


def benjamini_hochberg(pvals: list[float]) -> list[float]:
    m = len(pvals)
    ordre = sorted(range(m), key=lambda i: pvals[i], reverse=True)
    out, courant = [0.0] * m, 1.0
    for rang, i in enumerate(ordre):
        courant = min(courant, pvals[i] * m / (m - rang))
        out[i] = courant
    return out


def paris_necessaires(ecart_type_pari: float, effet: float | None, tests: int = 1) -> int | None:
    """Paris réglés qu'il faut au total pour distinguer ``effet`` de zéro avec une puissance de 80 %.
    ``tests`` = 1 : seuil de 5 % bilatéral, sans correction. Sinon : seuil unilatéral de 5 % / tests (Bonferroni,
    le premier pas de Holm), celui qu'un « avantage prouvé » doit passer."""
    if not effet or not ecart_type_pari:
        return None
    alpha = ALPHA / 2 if tests <= 1 else ALPHA / tests
    z = NormalDist().inv_cdf(1 - alpha) + NormalDist().inv_cdf(PUISSANCE)
    return math.ceil((z * ecart_type_pari / abs(effet)) ** 2)


# ---------------------------------------------------------------- CLV

def cloture_pinnacle(paris: list[dict]) -> dict[int, float]:
    """CLV contre la clôture Pinnacle : celle du pari si Pinnacle est sa référence, sinon celle du même pari
    (même bookmaker, même match, même marché, même issue) repéré aussi par Pinnacle, recalculée à la cote du pari."""
    juste: dict[tuple, tuple[str, float]] = {}
    for p in paris:
        if p.get("reference") == "Pinnacle" and simulation.clv_finale(p) is not None and p.get("match_id"):
            lu, k = p["cloture_lue"], cle_selection(p)
            if k not in juste or lu > juste[k][0]:
                juste[k] = (lu, p["cote_juste_cloture"])
    out = {}
    for p in paris:
        if p.get("statut") not in REGLES:
            continue
        if p.get("reference") == "Pinnacle":
            c = simulation.clv_finale(p)
            if c is not None:
                out[id(p)] = c
        elif p.get("match_id") and cle_selection(p) in juste:
            out[id(p)] = p["cote"] / juste[cle_selection(p)][1] - 1
    return out


# ---------------------------------------------------------------- lignes à tester

def lignes_a_tester(paris: list[dict], maintenant: datetime) -> list[dict]:
    """Chaque ligne : famille, nom, paris. Les stratégies reprennent les sélections officielles du site
    (scripts/site_web.py : décisions figées quand elles existent, suivi depuis le 14/10/2026 ou leur lancement)."""
    uniques = simulation.premiers_par_selection(paris)
    u = [p for p in paris if id(p) in uniques]
    plafond = simulation.COTE_MAX_PRISE
    lignes = [
        {"famille": "base", "nom": "Paris uniques, toutes cotes", "paris": u},
        {"famille": "base", "nom": f"Paris uniques, cote ≤ {plafond:g} (vue du site)", "paris": [p for p in u if p["cote"] <= plafond]},
        {"famille": "base", "nom": f"Paris uniques, cote > {plafond:g}", "paris": [p for p in u if p["cote"] > plafond]},
        {"famille": "base", "nom": "Paris uniques pris depuis le plafond (11/11)", "paris": [p for p in u if p["detecte"] >= PLAFOND_LE]},
    ]
    for b, _ in Counter(p["bookmaker"] for p in paris).most_common():
        lignes.append({"famille": "bookmaker", "nom": f"{b}, toutes cotes", "paris": [p for p in u if p["bookmaker"] == b]})
        lignes.append({"famille": "bookmaker", "nom": f"{b}, cote ≤ {plafond:g}",
                       "paris": [p for p in u if p["bookmaker"] == b and p["cote"] <= plafond]})
    for ref in simulation.REFERENCES:
        lignes.append({"famille": "reference", "nom": f"Référence {ref}", "paris": [p for p in paris if p["reference"] == ref]})
    for code, nom in (("A", "écart 2 à 3 %"), ("B", "écart 3 à 4 %"), ("C", "écart 4 à 5 %"), ("D", "écart 5 à 7 %"),
                      ("E", "écart 7 % et plus"), ("X", "cote > 10")):
        lignes.append({"famille": "seuil", "nom": f"Seuil {code} ({nom})", "paris": [p for p in u if p.get("simulation") == code]})
    for bas, haut, nom in simulation.TRANCHES:
        lignes.append({"famille": "seuil", "nom": f"Cote {nom}", "paris": [p for p in u if bas < p["cote"] <= haut]})

    debut_suivi = heure(DEBUT_SUIVI)
    suivis = [p for p in paris if heure(p.get("detecte")) and debut_suivi <= heure(p["detecte"]) < maintenant]
    ids_suivis = {id(p) for p in suivis}
    officiels = {nom: selecteur(paris) for _, _, _, nom, selecteur in STRATEGIES}
    bases = {cle: officiels[nom] for cle, _, _, nom, _ in STRATEGIES}
    officiels[CONVERGENCE["nom"]] = paris_convergence(paris)
    prudentes = selections_prudentes(paris, bases=bases)
    officiels.update({v["nom"]: prudentes[v["cle"]] for v in VARIANTES})
    for nom, ids in officiels.items():
        membres = [p for p in suivis if id(p) in ids]
        if membres:                          # places libres des fusions automatiques : aucune ligne
            lignes.append({"famille": "strategie", "nom": nom.replace(" (rejeu)", ""), "paris": membres})
    for r in REGLES_LABO:
        lignes.append({"famille": "laboratoire", "nom": r.nom, "paris": [p for p in selectionner(suivis, r, DEBUT_SUIVI)
                                                                         if id(p) in ids_suivis]})
    return lignes


def mesurer(ligne: dict, evenement, clv_pin: dict, tirages: int, rng: np.random.Generator) -> dict:
    tous = ligne["paris"]
    r = [p for p in tous if p.get("statut") in REGLES]
    out = {"famille": ligne["famille"], "nom": ligne["nom"], "paris": len(tous), "regles": len(r),
           "en_attente": len(tous) - len(r), "figes": sum(isinstance(p.get("selections_figees"), dict) for p in r),
           "cote_moyenne": round(float(np.mean([p["cote"] for p in r])), 2) if r else None,
           "hors_plafond": sum(p["cote"] > simulation.COTE_MAX_PRISE for p in r), "teste": False}
    if not r:
        return out
    cles = [evenement(p) for p in r]
    gains = np.array([p["gain"] or 0.0 for p in r])
    mises = np.array([p["mise"] for p in r])
    out.update(matchs=len(set(cles)), mises=float(mises.sum()), gain=round(float(gains.sum()), 2),
               roi=float(gains.sum() / mises.sum()), du=min(p["detecte"] for p in r)[:10], au=max(p["detecte"] for p in r)[:10])
    if len(r) >= MIN_PARIS and out["matchs"] >= MIN_MATCHS:
        b = rapport(*grappes(gains, mises, cles), tirages, rng)
        out.update(teste=b["p_pos"] is not None, roi_et=b["erreur_type"], roi_ic=b["ic"], roi_p_pos=b["p_pos"],
                   roi_p_neg=b["p_neg"], ecart_type_pari=b["erreur_type"] * math.sqrt(len(r)))

    # CLV : contre la clôture Pinnacle, contre la référence du pari, et la meilleure des deux (Pinnacle d'abord).
    propre = {id(p): simulation.clv_finale(p) for p in r}
    series = {"clv_pinnacle": {id(p): clv_pin.get(id(p)) for p in r}, "clv_reference": propre,
              "clv": {i: clv_pin.get(i, propre[i]) for i in propre}}
    for champ, valeurs in series.items():
        avec = [(p, valeurs[id(p)], k) for p, k in zip(r, cles) if valeurs[id(p)] is not None]
        bloc = {"mesures": len(avec), "part_mesuree": len(avec) / len(r)}
        if avec:
            v = np.array([c for _, c, _ in avec])
            k = [k for _, _, k in avec]
            bloc.update(moyenne=float(v.mean()), part_positive=float((v > 0).mean()), mediane=float(np.median(v)))
            if len(avec) >= MIN_CLV and len(set(k)) >= MIN_MATCHS:
                b = rapport(*grappes(v, np.ones(len(v)), k), tirages, rng)
                bloc.update(ic=b["ic"], p_pos=b["p_pos"], p_neg=b["p_neg"], erreur_type=b["erreur_type"])
                # Le ROI des paris mesurés est-il compatible avec leur CLV ? (rendement − CLV, par match)
                y = np.array([(p["gain"] or 0.0) / p["mise"] for p, _, _ in avec])
                e = rapport(*grappes(y - v, np.ones(len(v)), k), tirages, rng)
                bloc.update(roi_des_mesures=float(y.mean()), roi_moins_clv=e["valeur"], roi_moins_clv_ic=e["ic"])
            sans = [p for p in r if valeurs[id(p)] is None]
            bloc["roi_sans_mesure"] = (sum(p["gain"] or 0 for p in sans) / sum(p["mise"] for p in sans)) if sans else None
        out[champ] = bloc
    out["clv"]["pinnacle"] = out["clv_pinnacle"]["mesures"]
    return out


def corriger(resultats: list[dict]) -> int:
    """Ajoute les p-valeurs corrigées (Holm, Benjamini-Hochberg) et le nombre de paris nécessaires.
    Une seule famille par mesure : toutes les lignes testées, dans les deux sens. Rend le nombre de tests du ROI."""
    testees = [x for x in resultats if x["teste"]]
    p = [x[c] for x in testees for c in ("roi_p_pos", "roi_p_neg")]
    h, q = holm(p), benjamini_hochberg(p)
    for i, x in enumerate(testees):
        x.update(roi_p_pos_holm=h[2 * i], roi_p_neg_holm=h[2 * i + 1], roi_p_pos_bh=q[2 * i], roi_p_neg_bh=q[2 * i + 1])
    for champ in ("clv", "clv_pinnacle", "clv_reference"):
        avec = [x[champ] for x in testees if x[champ].get("p_pos") is not None]
        p = [b[c] for b in avec for c in ("p_pos", "p_neg")]
        h, q = holm(p), benjamini_hochberg(p)
        for i, b in enumerate(avec):
            b.update(p_pos_holm=h[2 * i], p_neg_holm=h[2 * i + 1], p_pos_bh=q[2 * i], p_neg_bh=q[2 * i + 1])
    tests = 2 * len(testees)
    for x in testees:
        e = x["ecart_type_pari"]
        clv = x["clv"].get("moyenne")
        x["necessaires"] = {"roi_observe": paris_necessaires(e, x["roi"], tests),
                            "roi_observe_sans_correction": paris_necessaires(e, x["roi"]),
                            "clv": paris_necessaires(e, clv, tests) if clv and clv > 0 else None,
                            "clv_sans_correction": paris_necessaires(e, clv) if clv and clv > 0 else None}
    return tests


PROUVE, PROBABLE, NON_PROUVE, NEGATIF = "avantage prouvé", "avantage probable", "non prouvé", "négatif"


def verdict(x: dict) -> tuple[str, str]:
    """Grille de lecture de docs/avantage-reel.md (« Règles du verdict »)."""
    if not x["teste"]:
        return NON_PROUVE, f"trop peu de paris ({x['regles']} réglés)"
    clv, pin = x["clv"], x["clv_pinnacle"]
    if x["roi"] > 0 and x["roi_p_pos_holm"] < ALPHA:
        return PROUVE, "ROI positif après correction de Holm"
    if x["roi"] < 0 and x["roi_p_neg_bh"] < ALPHA:
        return NEGATIF, "ROI négatif après correction"
    clv_negative = next((nom for bloc, nom in ((pin, "Pinnacle"), (clv, "de la meilleure référence"))
                         if bloc.get("p_neg_bh") is not None and bloc["moyenne"] < 0 and bloc["p_neg_bh"] < ALPHA), None)
    if x["roi"] < 0 and clv_negative:
        return NEGATIF, f"ROI négatif et CLV {clv_negative} négative après correction"
    contredit = bool(pin.get("roi_moins_clv_ic")) and pin["roi_moins_clv_ic"][1] < 0
    clv_prouvee = (pin.get("p_pos_holm") is not None and pin["moyenne"] > 0 and pin["p_pos_holm"] < ALPHA
                   and pin["part_mesuree"] >= PART_PINNACLE_MIN)
    if x["roi"] > 0 and x["roi_p_pos_bh"] < ALPHA:
        return PROBABLE, "ROI positif après correction de Benjamini-Hochberg"
    if x["roi"] > 0 and clv_prouvee and not contredit:
        return PROBABLE, "CLV Pinnacle prouvée, ROI positif mais non prouvé"
    if x["roi_ic"][1] < 0:
        return NON_PROUVE, "tendance négative, non confirmée après correction"
    if clv_negative:
        return NON_PROUVE, f"CLV {clv_negative} négative après correction, ROI positif"
    if clv_prouvee and contredit:
        return NON_PROUVE, "CLV Pinnacle prouvée mais contredite par le ROI"
    if clv_prouvee:
        return NON_PROUVE, "CLV Pinnacle prouvée, ROI négatif"
    return NON_PROUVE, "ni le ROI ni la CLV ne se distinguent de zéro"


# ---------------------------------------------------------------- la CLV prédit-elle le ROI ?

def pente(x: np.ndarray, y: np.ndarray, cles: list, tirages: int, rng: np.random.Generator) -> dict:
    """Pente de y (rendement du pari) sur x (CLV), intervalle par bootstrap de matchs. 1 = la CLV est un prix juste."""
    rang: dict = {}
    idx = np.fromiter((rang.setdefault(c, len(rang)) for c in cles), dtype=np.int64, count=len(cles))
    k = len(rang)
    base = np.column_stack([np.bincount(idx, weights=w, minlength=k) for w in (np.ones(len(x)), x, y, x * x, x * y)])
    n, sx, sy, sxx, sxy = base.sum(axis=0)
    b = (n * sxy - sx * sy) / (n * sxx - sx * sx)
    pentes = []
    lot = max(1, min(tirages, 4_000_000 // k))
    fait = 0
    while fait < tirages:
        m = min(lot, tirages - fait)
        s = rng.multinomial(k, np.full(k, 1.0 / k), size=m) @ base
        pentes.append((s[:, 0] * s[:, 4] - s[:, 1] * s[:, 2]) / (s[:, 0] * s[:, 3] - s[:, 1] ** 2))
        fait += m
    bas, haut = np.nanpercentile(np.concatenate(pentes), [2.5, 97.5])
    return {"pente": float(b), "ic": [float(bas), float(haut)], "ordonnee": float((sy - b * sx) / n), "paris": len(x), "matchs": k}


def clv_predit_roi(paris: list[dict], evenement, clv_pin: dict, resultats: list[dict], tirages: int,
                   rng: np.random.Generator) -> dict:
    uniques = simulation.premiers_par_selection(paris)
    r = [p for p in paris if id(p) in uniques and p.get("statut") in REGLES]
    lignes = []
    for p in r:
        c = clv_pin.get(id(p))
        source = "Pinnacle" if c is not None else p["reference"]
        c = c if c is not None else simulation.clv_finale(p)
        if c is not None:
            lignes.append((p, c, source))
    out = {"paris_uniques_regles": len(r), "avec_clv": len(lignes)}

    def bloc(sel: list) -> dict | None:
        if len(sel) < MIN_PARIS:
            return None
        x = np.array([c for _, c, _ in sel])
        y = np.array([(p["gain"] or 0.0) / p["mise"] for p, _, _ in sel])
        cles = [evenement(p) for p, _, _ in sel]
        roi = rapport(*grappes(y, np.ones(len(y)), cles), tirages, rng)
        ecart = rapport(*grappes(y - x, np.ones(len(y)), cles), tirages, rng)
        return {"paris": len(sel), "clv_moyenne": float(x.mean()), "roi": roi["valeur"], "roi_ic": roi["ic"],
                "roi_moins_clv": ecart["valeur"], "roi_moins_clv_ic": ecart["ic"], "regression": pente(x, y, cles, tirages, rng)}

    plafond = simulation.COTE_MAX_PRISE
    out["ensemble"] = bloc(lignes)
    out["cote_max_5"] = bloc([l for l in lignes if l[0]["cote"] <= plafond])
    out["cote_plus_de_5"] = bloc([l for l in lignes if l[0]["cote"] > plafond])
    out["cloture_pinnacle"] = bloc([l for l in lignes if l[2] == "Pinnacle"])
    out["cloture_pinnacle_cote_max_5"] = bloc([l for l in lignes if l[2] == "Pinnacle" and l[0]["cote"] <= plafond])
    out["autres_clotures"] = bloc([l for l in lignes if l[2] != "Pinnacle"])
    out["autres_clotures_cote_max_5"] = bloc([l for l in lignes if l[2] != "Pinnacle" and l[0]["cote"] <= plafond])
    # Par cinquième de CLV (bornes sur les paris uniques).
    tries = sorted(lignes, key=lambda l: l[1])
    out["cinquiemes"] = []
    for i in range(5):
        part = tries[i * len(tries) // 5:(i + 1) * len(tries) // 5]
        b = bloc(part)
        out["cinquiemes"].append({"clv_de": part[0][1], "clv_a": part[-1][1],
                                  **{k: b[k] for k in ("paris", "clv_moyenne", "roi", "roi_ic")}})
    out["signe"] = {}
    pin5 = sorted((l for l in lignes if l[2] == "Pinnacle" and l[0]["cote"] <= plafond), key=lambda l: l[1])
    for nom, test in (("clv_positive", lambda c: c > 0), ("clv_negative_ou_nulle", lambda c: c <= 0)):
        b = bloc([l for l in lignes if test(l[1])])
        out["signe"][nom] = b and {k: b[k] for k in ("paris", "clv_moyenne", "roi", "roi_ic")}
    out["cinquiemes_pinnacle_cote_max_5"] = []
    for i in range(5):
        part = pin5[i * len(pin5) // 5:(i + 1) * len(pin5) // 5]
        b = bloc(part)
        out["cinquiemes_pinnacle_cote_max_5"].append({"clv_de": part[0][1], "clv_a": part[-1][1],
                                                      **{k: b[k] for k in ("paris", "clv_moyenne", "roi", "roi_ic")}})
    # Entre lignes : la CLV moyenne d'une ligne annonce-t-elle son ROI ? Descriptif, les lignes partagent des paris.
    pts = [(x["clv"]["moyenne"], x["roi"]) for x in resultats
           if x["teste"] and x["famille"] in ("strategie", "laboratoire") and x["regles"] >= 100
           and x["clv"].get("mesures", 0) >= 50]
    if len(pts) >= 5:
        a, b_ = np.array(pts).T
        rangs = lambda v: np.argsort(np.argsort(v)).astype(float)  # noqa: E731
        out["entre_strategies"] = {"lignes": len(pts), "correlation": float(np.corrcoef(a, b_)[0, 1]),
                                   "correlation_rangs": float(np.corrcoef(rangs(a), rangs(b_))[0, 1])}
    return out


# ---------------------------------------------------------------- sorties

def pct(x, d=1, signe=True) -> str:
    if x is None:
        return "—"
    return f"{100 * x:+.{d}f} %".replace(".", ",") if signe else f"{100 * x:.{d}f} %".replace(".", ",")


def ic(v, d=1) -> str:
    return "—" if not v else f"[{100 * v[0]:+.{d}f} ; {100 * v[1]:+.{d}f}]".replace(".", ",")


def pv(x) -> str:
    if x is None:
        return "—"
    return "< 0,001" if x < 0.001 else f"{x:.3f}".replace(".", ",")


def nombre(n) -> str:
    if n is None:
        return "—"
    return "> 1 000 000" if n > 1_000_000 else f"{n:,}".replace(",", " ")


def encore(x: dict, champ: str) -> str:
    n = (x.get("necessaires") or {}).get(champ)
    if n is None:
        return "—"
    return "0" if n <= x["regles"] else nombre(n - x["regles"])


def tableau_roi(resultats: list[dict], famille: str) -> str:
    out = ["| Ligne | Réglés (matchs) | Cote moy. | ROI | IC 95 % | p | Holm | BH | Encore, si le ROI observé est le vrai "
           "| Encore, si la CLV est le vrai ROI | Verdict |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for x in resultats:
        if x["famille"] != famille:
            continue
        sens = "roi_p_pos" if x.get("roi", 0) > 0 else "roi_p_neg"
        note = "" if x["raison"].startswith(("ni le ROI", "ROI positif après", "ROI négatif après")) else f" ({x['raison']})"
        out.append(
            f"| {x['nom']} | {x['regles']} ({x.get('matchs', 0)}) | {str(x['cote_moyenne'] or '—').replace('.', ',')} | {pct(x.get('roi'))} "
            f"| {ic(x.get('roi_ic'))} | {pv(x.get(sens))} | {pv(x.get(sens + '_holm'))} | {pv(x.get(sens + '_bh'))} "
            f"| {encore(x, 'roi_observe')} | {encore(x, 'clv')} | **{x['verdict']}**{note} |")
    return "\n".join(out)


def tableau_clv(resultats: list[dict], famille: str) -> str:
    out = ["| Ligne | CLV Pinnacle : mesures (part des réglés) | Moyenne | IC 95 % | Part > 0 | Holm | ROI − CLV, IC 95 % "
           "| Meilleure référence : mesures (part) | Moyenne | IC 95 % | Part > 0 |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for x in resultats:
        if x["famille"] != famille:
            continue
        p, m = x["clv_pinnacle"], x["clv"]
        sens = "p_pos_holm" if p.get("moyenne", 0) > 0 else "p_neg_holm"
        out.append(
            f"| {x['nom']} | {p['mesures']} ({pct(p['part_mesuree'], 0, False)}) | {pct(p.get('moyenne'), 2)} "
            f"| {ic(p.get('ic'), 2)} | {pct(p.get('part_positive'), 0, False)} | {pv(p.get(sens))} "
            f"| {ic(p.get('roi_moins_clv_ic'))} | {m['mesures']} ({pct(m['part_mesuree'], 0, False)}) "
            f"| {pct(m.get('moyenne'), 2)} | {ic(m.get('ic'), 2)} | {pct(m.get('part_positive'), 0, False)} |")
    return "\n".join(out)


FAMILLES = (("base", "Ensemble"), ("bookmaker", "Bookmakers (paris uniques)"), ("reference", "Références (tous leurs paris)"),
            ("seuil", "Seuils d'écart et tranches de cote (paris uniques)"), ("strategie", "Stratégies (suivi officiel)"),
            ("laboratoire", "Laboratoire (24 règles de seuils)"))


def markdown(rapport_: dict) -> str:
    r, c = rapport_["lignes"], rapport_["clv_predit_roi"]
    out = ["# Avantage réel : tous les tableaux", "",
           f"Produit par `scripts/avantage_reel.py --markdown` : données `{rapport_['commit_donnees']}`, "
           f"{rapport_['regles']} paris réglés sur {rapport_['paris']}, {rapport_['tirages']} tirages, graine "
           f"{rapport_['graine']}, {rapport_['tests']} tests du ROI ({rapport_['lignes_testees']} lignes, deux sens). "
           "Lecture et conclusions : [avantage-reel.md](avantage-reel.md).", "",
           "« p » : p-valeur unilatérale dans le sens du ROI observé. « Encore » : paris réglés qu'il manque pour passer "
           "le seuil corrigé (5 % / nombre de tests) avec une puissance de 80 %. « — » : trop peu de mesures.", "",
           "## ROI", ""]
    for famille, titre in FAMILLES:
        out += [f"### {titre}", "", tableau_roi(r, famille), ""]
    out += ["## CLV", ""]
    for famille, titre in FAMILLES:
        out += [f"### {titre}", "", tableau_clv(r, famille), ""]
    out += ["## La CLV prédit-elle le ROI ?", "",
            "| Paris uniques réglés avec CLV | Paris | CLV moyenne | ROI | IC 95 % du ROI | ROI − CLV | IC 95 % | Pente du rendement sur la CLV | IC 95 % |",
            "|---|---|---|---|---|---|---|---|---|"]
    for cle, nom in (("ensemble", "Tous"), ("cote_max_5", "Cote ≤ 5"), ("cote_plus_de_5", "Cote > 5"),
                     ("cloture_pinnacle", "Clôture Pinnacle"),
                     ("cloture_pinnacle_cote_max_5", "Clôture Pinnacle, cote ≤ 5"), ("autres_clotures", "Autre clôture"),
                     ("autres_clotures_cote_max_5", "Autre clôture, cote ≤ 5")):
        b = c.get(cle)
        if b:
            g = b["regression"]
            pente_ = f"{g['pente']:.2f} | [{g['ic'][0]:.2f} ; {g['ic'][1]:.2f}]".replace(".", ",")
            out.append(f"| {nom} | {b['paris']} | {pct(b['clv_moyenne'], 2)} | {pct(b['roi'])} | {ic(b['roi_ic'])} "
                       f"| {pct(b['roi_moins_clv'])} | {ic(b['roi_moins_clv_ic'])} | {pente_} |")
    for cle, titre in (("cinquiemes", "Cinquième de CLV, tous"),
                       ("cinquiemes_pinnacle_cote_max_5", "Cinquième de CLV, clôture Pinnacle et cote ≤ 5")):
        out += ["", f"| {titre} | Paris | CLV moyenne | ROI | IC 95 % |", "|---|---|---|---|---|"]
        for q in c[cle]:
            out.append(f"| {pct(q['clv_de'], 1)} à {pct(q['clv_a'], 1)} | {q['paris']} | {pct(q['clv_moyenne'], 2)} "
                       f"| {pct(q['roi'])} | {ic(q['roi_ic'])} |")
    out += ["", "| Signe de la CLV, tous | Paris | CLV moyenne | ROI | IC 95 % |", "|---|---|---|---|---|"]
    for cle, nom in (("clv_positive", "CLV > 0"), ("clv_negative_ou_nulle", "CLV ≤ 0")):
        q = c["signe"].get(cle)
        if q:
            out.append(f"| {nom} | {q['paris']} | {pct(q['clv_moyenne'], 2)} | {pct(q['roi'])} | {ic(q['roi_ic'])} |")
    e = c.get("entre_strategies")
    if e:
        out += ["", f"Entre {e['lignes']} stratégies et règles d'au moins 100 paris réglés : corrélation entre CLV moyenne et "
                    f"ROI {e['correlation']:+.2f} (rangs : {e['correlation_rangs']:+.2f}).".replace(".", ",")[:-2] + ")."]
    return "\n".join(out) + "\n"


def synthese(rapport_: dict) -> str:
    """Tableau court par famille : ce qu'il faut pour lire le verdict de chaque ligne."""
    out = []
    for famille, titre in FAMILLES:
        out += [f"### {titre}", "", "| Ligne | Réglés | ROI | IC 95 % | p corrigée (Holm) | CLV Pinnacle | IC 95 % | Verdict |",
                "|---|---|---|---|---|---|---|---|"]
        for x in rapport_["lignes"]:
            if x["famille"] != famille:
                continue
            sens = "roi_p_pos_holm" if x.get("roi", 0) > 0 else "roi_p_neg_holm"
            p = x["clv_pinnacle"] if x["regles"] else {}
            out.append(f"| {x['nom']} | {x['regles']} | {pct(x.get('roi'))} | {ic(x.get('roi_ic'))} | {pv(x.get(sens))} "
                       f"| {pct(p.get('moyenne'), 2)} | {ic(p.get('ic'), 2)} | **{x['verdict']}** : {x['raison']} |")
        out.append("")
    return "\n".join(out)


def analyser(donnees: Path, tirages: int = 50000, graine: int = GRAINE) -> dict:
    charger_fusions(donnees)
    pauses.charger(donnees)
    paris = stockage.fusionner_paris(stockage.lire_archives(donnees), json.loads((donnees / "paris.json").read_text()))
    maintenant = datetime.now(timezone.utc)
    liens = identites(paris)
    evenement = lambda p: liens[id(p)]  # noqa: E731
    clv_pin = cloture_pinnacle(paris)
    rng = np.random.default_rng(graine)
    resultats = [mesurer(l, evenement, clv_pin, tirages, rng) for l in lignes_a_tester(paris, maintenant)]
    tests = corriger(resultats)
    for x in resultats:
        x["verdict"], x["raison"] = verdict(x)
    regles = [p for p in paris if p.get("statut") in REGLES]
    try:
        commit = subprocess.run(["git", "-C", str(donnees), "log", "-1", "--format=%h du %cI"], capture_output=True,
                                text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        commit = "inconnu"
    return {"commit_donnees": commit, "tirages": tirages, "graine": graine, "tests": tests,
            "lignes_testees": tests // 2,
            "paris": len(paris), "regles": len(regles), "du": min(p["detecte"] for p in paris)[:10],
            "au": max(p["detecte"] for p in paris)[:10],
            "clv": {"propre": sum(simulation.clv_finale(p) is not None for p in regles),
                    "pinnacle": len(clv_pin), "pinnacle_par_frere": sum(1 for p in regles if id(p) in clv_pin
                                                                         and p["reference"] != "Pinnacle"),
                    "aucune": sum(1 for p in regles if id(p) not in clv_pin and simulation.clv_finale(p) is None)},
            "verdicts": {f"{f} | {v}": n for (f, v), n in Counter((x["famille"], x["verdict"]) for x in resultats).items()},
            "lignes": resultats,
            "clv_predit_roi": clv_predit_roi(paris, evenement, clv_pin, resultats, tirages, rng)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--donnees", type=Path, required=True)
    ap.add_argument("--tirages", type=int, default=50000)
    ap.add_argument("--graine", type=int, default=GRAINE)
    ap.add_argument("--json", type=Path, help="écrit tous les chiffres dans ce fichier")
    ap.add_argument("--markdown", type=Path, help="écrit les tableaux complets dans ce fichier")
    a = ap.parse_args()
    rapport_ = analyser(a.donnees, a.tirages, a.graine)
    if a.json:
        a.json.write_text(json.dumps(rapport_, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if a.markdown:
        a.markdown.write_text(markdown(rapport_), encoding="utf-8")
    print(synthese(rapport_))
    print(f"{rapport_['regles']} paris réglés sur {rapport_['paris']} ({rapport_['du']} au {rapport_['au']}), "
          f"{rapport_['lignes_testees']} lignes testées | CLV : {rapport_['clv']}", file=sys.stderr)
    for cle, n in sorted(rapport_["verdicts"].items()):
        print(f"  {cle} : {n}", file=sys.stderr)


if __name__ == "__main__":
    main()
