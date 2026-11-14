"""Stratégie de mises : segments qui perdent, stratégie figée (choisie sur une période, validée sur l'autre) et
mise de Kelly fractionnée simulée contre la mise fixe. Lecture seule.

Usage : python scripts/strategie_mises.py --donnees CHEMIN [--tirages 10000] [--trajectoires 2000] [--json FICHIER]
        [--markdown FICHIER]
CHEMIN = branche « donnees » extraite (scripts/cloner_donnees.sh suffit). Demande numpy (requirements-dev.txt).
Environ une minute. Même graine, mêmes données : mêmes chiffres. Conclusions : docs/strategie-mises.md.

Méthode, dans l'ordre où elle a été fixée :
- paris uniques réglés ; l'unité de hasard est le match (bootstrap par match, scripts/avantage_reel.py) ;
- période de choix (A) : matchs dont la première détection est avant COUPURE ; période de validation (B) : les autres.
  Tout ce qui est choisi (segments écartés, modèle d'avantage, corrélation) l'est sur A, par une règle mécanique ;
- règle d'exclusion : parmi les cotes ≤ plafond du site, un segment est écarté si sa CLV contre la clôture Pinnacle
  est négative sur A avec au moins MIN_MESURES mesures. La stratégie figée garde les paris d'aucun segment écarté ;
- avantage d'un pari : a + b × min(écart annoncé, ECART_MAX), ajusté sur la CLV Pinnacle des paris retenus de A,
  puis comparé à la CLV des paris retenus de B ;
- modèle proposé pour les mises : la même droite réajustée sur A et B, l'écart de niveau entre les deux périodes
  compté comme une incertitude de plus (ce réajustement n'est pas validé hors échantillon) ;
- mise de Kelly : fraction × facteur d'incertitude × avantage / (cote − 1), moins l'exposition déjà prise sur le
  même match (corrélation mesurée sur A), plafonnée par pari et en exposition totale ;
- simulation : rejeu des paris réels dans l'ordre, puis trajectoires d'un an tirées avec un avantage réel supposé
  (celui du modèle proposé, sa moitié, nul, négatif) et la corrélation mesurée entre paris d'un même match.
"""
from __future__ import annotations

import argparse
import heapq
import json
import math
import subprocess
import sys
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from statistics import NormalDist

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cotes import reglement, simulation, stockage  # noqa: E402
from cotes.evenements import identites  # noqa: E402
from scripts.avantage_reel import cloture_pinnacle, grappes, heure, rapport  # noqa: E402

REGLES = tuple(reglement.GAIN)
COUPURE = "2026-10-26T00:00"        # A : première détection du match avant cette heure UTC ; B : après
GRAINE = 20261114
MIN_MESURES = 50                    # CLV Pinnacle mesurées qu'il faut sur A pour juger un segment
MIN_PARIS, MIN_MATCHS = 30, 10      # en dessous : pas d'intervalle
ECART_MAX = 0.10                    # au-delà, l'écart annoncé ne compte pas plus (cotes fantômes, erreurs de ligne)
MISE_FIXE = simulation.MISE
BANKROLL = 1000.0                   # bankroll de départ des simulations : la mise fixe en vaut 1 %
FRACTIONS = (0.5, 0.25, 0.125, 0.0625, 0.03125)
SANS_CORRELATION = (0.125, 0.0625)  # fractions simulées aussi sans la correction de corrélation
PLAFOND_PARI = 0.02                 # mise maximale d'un pari, en part de la bankroll
PLAFOND_OUVERT = 0.50               # mises en cours maximales, en part de la bankroll
PERTE_MOITIE, RUINE = 0.5, 0.1      # seuils de bankroll (part du départ) : « perd la moitié », « ruine »
RISQUE_ACCEPTE = 0.05               # fraction retenue : la plus grande qui perd la moitié moins d'une fois sur 20 sans avantage
SCENARIOS = (("modele", "Avantage du modèle proposé"), ("moitie", "Moitié du modèle proposé"), ("nul", "Aucun avantage"),
             ("negatif", "Avantage de −2 %"))
JOURS = 365

MARCHES = {"RESULTAT_1N2": "1N2", "VAINQUEUR": "Vainqueur", "TOTAL": "Total", "HANDICAP": "Handicap",
           "HANDICAP_3": "Handicap à 3 issues", "TOTAL_DOM": "Total d'équipe", "TOTAL_EXT": "Total d'équipe",
           "CORRECT_SCORE": "Score exact", "HALF_TIME_FULL_TIME": "Mi-temps / fin", "DOUBLE_CHANCE": "Double chance",
           "DRAW_NO_BET": "Remboursé si nul", "BOTH_TEAMS_TO_SCORE": "Les deux marquent"}
PERIODES = {"MATCH": "Match entier", "MT1": "1re mi-temps", "TEMPS_REG": "Temps réglementaire"}


# ---------------------------------------------------------------- lecture

def _ecart(e: float) -> str:
    for borne, nom in ((.03, "2 à 3 %"), (.04, "3 à 4 %"), (.05, "4 à 5 %"), (.07, "5 à 7 %"), (.10, "7 à 10 %")):
        if e < borne:
            return nom
    return "10 % et plus"


def _avance(h: float) -> str:
    for borne, nom in ((1, "moins d'1 h"), (6, "1 à 6 h"), (12, "6 à 12 h"), (24, "12 à 24 h")):
        if h < borne:
            return nom
    return "plus de 24 h"


def _tranche(cote: float) -> str:
    return next(nom for bas, haut, nom in simulation.TRANCHES if bas < cote <= haut)


DIMENSIONS = ("Tranche de cote", "Écart annoncé", "Sport", "Marché", "Période de jeu", "Bookmaker", "Référence",
              "Avance sur le match")
JUGEES = DIMENSIONS[1:]             # la règle d'exclusion ne s'applique qu'aux cotes ≤ plafond


def charger(donnees: Path) -> list[dict]:
    """Paris uniques réglés, une ligne par pari : match, période A ou B, rendement, CLV Pinnacle, segments."""
    paris = stockage.fusionner_paris(stockage.lire_archives(donnees), json.loads((donnees / "paris.json").read_text()))
    liens, clv = identites(paris), cloture_pinnacle(paris)
    premiere: dict = {}
    for p in paris:
        k = liens[id(p)]
        premiere[k] = min(premiere.get(k, p["detecte"]), p["detecte"])
    uniques = simulation.premiers_par_selection(paris)
    regles = [p for p in paris if id(p) in uniques and p.get("statut") in REGLES]
    petits = {s for s, n in Counter(p["sport"] for p in regles).items() if n < 100}
    lignes = []
    for p in regles:
        ev, debut, detecte = liens[id(p)], heure(p["debut"]), heure(p["detecte"])
        lignes.append({
            "id": p["id"], "match": ev, "periode": "A" if premiere[ev] < COUPURE else "B", "jour": premiere[ev][:10],
            "detecte": detecte, "regle": heure(p.get("regle_le")) or debut, "cote": p["cote"], "ecart": p["ecart"],
            "rendement": (p["gain"] or 0.0) / p["mise"], "clv": clv.get(id(p)), "binaire": p["statut"] in ("gagne", "perdu"),
            "gagne": p["statut"] == "gagne", "proba_juste": 1 / p["cote_juste"],
            "selection": (ev, p["marche"], p["periode"], p["ligne"], p["issue"]), "marche_brut": (p["marche"], p["periode"]),
            "segments": {
                "Tranche de cote": _tranche(p["cote"]), "Écart annoncé": _ecart(p["ecart"]),
                "Sport": "autres sports" if p["sport"] in petits else p["sport"],
                "Marché": MARCHES.get(p["marche"], "Tennis : jeux et sets"),
                "Période de jeu": PERIODES.get(p["periode"], "Autres périodes"),
                "Bookmaker": p["bookmaker"], "Référence": p["reference"],
                "Avance sur le match": _avance((debut - detecte).total_seconds() / 3600)}})
    lignes.sort(key=lambda x: (x["detecte"], x["id"]))
    return lignes


# ---------------------------------------------------------------- mesures

def mesurer(lignes: list[dict], tirages: int, rng: np.random.Generator, mises: np.ndarray | None = None) -> dict:
    """ROI et CLV Pinnacle moyenne, intervalles à 95 % par bootstrap studentisé sur les matchs."""
    out = {"paris": len(lignes), "matchs": len({x["match"] for x in lignes}), "roi": None, "roi_ic": None,
           "mesures": 0, "clv": None, "clv_ic": None}
    if not lignes:
        return out
    cles = [x["match"] for x in lignes]
    m = np.full(len(lignes), MISE_FIXE) if mises is None else mises
    g = m * np.array([x["rendement"] for x in lignes])
    if m.sum() > 0:
        out["roi"] = float(g.sum() / m.sum())
        if len(lignes) >= MIN_PARIS and out["matchs"] >= MIN_MATCHS:
            out["roi_ic"] = rapport(*grappes(g, m, cles), tirages, rng)["ic"]
    avec = [(x["clv"], k) for x, k in zip(lignes, cles) if x["clv"] is not None]
    out["mesures"] = len(avec)
    if avec:
        v, k = np.array([c for c, _ in avec]), [k for _, k in avec]
        out["clv"] = float(v.mean())
        if len(avec) >= MIN_PARIS and len(set(k)) >= MIN_MATCHS:
            out["clv_ic"] = rapport(*grappes(v, np.ones(len(v)), k), tirages, rng)["ic"]
    return out


def difference(a: list[dict], b: list[dict], champ: str, tirages: int, rng: np.random.Generator) -> dict:
    """Moyenne de ``champ`` (« clv » ou « rendement ») sur a moins celle sur b, intervalle à 95 % par bootstrap sur les
    matchs (percentiles). Un match peut avoir des paris des deux côtés : il est tiré en entier."""
    rang: dict = {}
    table = []
    for groupe, colonne in ((a, 0), (b, 2)):
        for x in groupe:
            if x[champ] is not None:
                i = rang.setdefault(x["match"], len(rang))
                if i == len(table):
                    table.append([0.0, 0.0, 0.0, 0.0])
                table[i][colonne] += x[champ]
                table[i][colonne + 1] += 1
    t = np.array(table)
    diff = lambda s: s[..., 0] / s[..., 1] - s[..., 2] / s[..., 3]  # noqa: E731
    tires = np.array([diff(t[rng.integers(0, len(t), len(t))].sum(axis=0)) for _ in range(min(tirages, 5000))])
    return {"valeur": float(diff(t.sum(axis=0))), "ic": [float(q) for q in np.percentile(tires, [2.5, 97.5])]}


def segments(lignes: list[dict], plafond: float, tirages: int, rng: np.random.Generator) -> list[dict]:
    """Chaque segment mesuré sur A, sur B et sur l'ensemble. Hors « Tranche de cote » : cotes ≤ plafond seulement."""
    out = []
    for dim in DIMENSIONS:
        base = lignes if dim == "Tranche de cote" else [x for x in lignes if x["cote"] <= plafond]
        groupes = defaultdict(list)
        for x in base:
            groupes[x["segments"][dim]].append(x)
        for nom, membres in sorted(groupes.items(), key=lambda kv: -len(kv[1])):
            out.append({"dimension": dim, "segment": nom,
                        "A": mesurer([x for x in membres if x["periode"] == "A"], tirages, rng),
                        "B": mesurer([x for x in membres if x["periode"] == "B"], tirages, rng),
                        "tout": mesurer(membres, tirages, rng)})
    return out


def ecartes(segs: list[dict]) -> list[tuple[str, str]]:
    """La règle d'exclusion, lue sur la période A seulement."""
    return [(s["dimension"], s["segment"]) for s in segs if s["dimension"] in JUGEES
            and s["A"]["mesures"] >= MIN_MESURES and s["A"]["clv"] < 0]


def retenu(x: dict, exclus: list[tuple[str, str]], plafond: float) -> bool:
    return x["cote"] <= plafond and not any(x["segments"][d] == s for d, s in exclus)


def confirmation(s: dict) -> str:
    """Un segment écarté sur A l'est-il aussi par B ?"""
    b = s["B"]
    if b["mesures"] < MIN_MESURES:
        return "non mesurable sur B"
    return "confirmé sur B" if b["clv"] < 0 else "non confirmé sur B"


# ---------------------------------------------------------------- modèle d'avantage et corrélation

def droite(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    dx = x - x.mean()
    b = float((dx * (y - y.mean())).sum() / (dx ** 2).sum())
    return float(y.mean() - b * x.mean()), b


def ajuster_avantage(lignes: list[dict], tirages: int, rng: np.random.Generator) -> dict:
    """CLV Pinnacle = a + b × min(écart, ECART_MAX) ; incertitude de (a, b) par bootstrap sur les matchs."""
    m = [x for x in lignes if x["clv"] is not None]
    x = np.array([min(l["ecart"], ECART_MAX) for l in m])
    y = np.array([l["clv"] for l in m])
    par_match = defaultdict(list)
    for i, l in enumerate(m):
        par_match[l["match"]].append(i)
    blocs = [np.array(v) for v in par_match.values()]
    tires = []
    for _ in range(tirages):
        t = np.concatenate([blocs[j] for j in rng.integers(0, len(blocs), len(blocs))])
        tires.append(droite(x[t], y[t]))
    cov = np.cov(np.array(tires).T)
    a, b = droite(x, y)
    return {"a": a, "b": b, "var_a": float(cov[0, 0]), "var_b": float(cov[1, 1]), "cov_ab": float(cov[0, 1]), "var_periode": 0.0,
            "mesures": len(m), "matchs": len(blocs), "ecart_type_clv": float(y.std()), "ecart_moyen": float(x.mean())}


def avantage(modele: dict, ecart: float) -> tuple[float, float]:
    """Avantage prévu d'un pari et son erreur type."""
    e = min(ecart, ECART_MAX)
    var = modele["var_a"] + 2 * e * modele["cov_ab"] + e * e * modele["var_b"] + modele["var_periode"]
    return modele["a"] + modele["b"] * e, math.sqrt(max(var, 0.0))


def facteur_incertitude(mu: float, erreur_type: float) -> float:
    """Part de la mise de Kelly à garder quand l'avantage n'est connu qu'à son erreur type près : mu² / (mu² + se²)
    (Baker et McHale, 2013). Vaut 1 pour un avantage sûr, tend vers 0 quand l'erreur dépasse l'avantage."""
    if mu <= 0:
        return 0.0
    return mu * mu / (mu * mu + erreur_type * erreur_type)


def correlation_match(lignes: list[dict], tirages: int, rng: np.random.Generator) -> dict:
    """Corrélation des résultats de deux paris d'un même match (résultats centrés sur la probabilité juste),
    moyenne par match : même sélection chez un autre bookmaker, même marché, autre marché."""
    par_match = defaultdict(list)
    for x in lignes:
        if x["binaire"]:
            par_match[x["match"]].append(x)

    def z(x):
        q = min(max(x["proba_juste"], .02), .98)
        return (x["gagne"] - q) / math.sqrt(q * (1 - q))

    types: dict[str, dict] = {k: defaultdict(list) for k in ("meme_selection", "meme_marche", "autre_marche", "autres")}
    for ev, membres in par_match.items():
        for u, v in combinations(membres, 2):
            if u["selection"] == v["selection"]:
                t = "meme_selection"
            else:
                t = "meme_marche" if u["marche_brut"] == v["marche_brut"] else "autre_marche"
                types["autres"][ev].append(z(u) * z(v))
            types[t][ev].append(z(u) * z(v))
    out = {}
    for t, par_ev in types.items():
        m = np.array([np.mean(v) for v in par_ev.values()])
        if len(m) < 2:
            out[t] = {"paires": int(sum(len(v) for v in par_ev.values())), "matchs": len(m), "rho": None, "ic": None}
            continue
        boot = m[rng.integers(0, len(m), (tirages, len(m)))].mean(axis=1)
        out[t] = {"paires": int(sum(len(v) for v in par_ev.values())), "matchs": len(m), "rho": float(m.mean()),
                  "ic": [float(q) for q in np.percentile(boot, [2.5, 97.5])]}
    return out


# ---------------------------------------------------------------- mise de Kelly

def variance(mu: float, cote: float) -> float:
    """Variance du rendement d'un pari d'avantage mu : p (1 − p) cote², avec p = (1 + mu) / cote."""
    return max((1 + mu) * (cote - 1 - mu), 1e-9)


def mise_kelly(mu: float, erreur_type: float, cote: float, fraction: float, ouverts: list[tuple[float, float, float]],
               expose: float = 0.0) -> float:
    """Part de la bankroll à miser sur un pari.

    mu, erreur_type : avantage prévu et son incertitude. ouverts : paris déjà pris sur le même match, chacun
    (part misée, variance du rendement, corrélation avec ce pari). expose : part de la bankroll déjà en jeu, tous
    matchs confondus.
    Kelly fractionné sur l'avantage rétréci, moins ce que les paris corrélés portent déjà (optimum moyenne-variance
    pour un pari ajouté à des mises qu'on ne peut plus changer) : deux paris parfaitement corrélés se partagent
    une seule mise de Kelly.
    """
    k = facteur_incertitude(mu, erreur_type)
    if k <= 0 or cote <= 1:
        return 0.0
    v = variance(mu, cote)
    f = fraction * k * mu / (cote - 1) - sum(rho * math.sqrt(vj / v) * fj for fj, vj, rho in ouverts)
    return max(0.0, min(f, PLAFOND_PARI, PLAFOND_OUVERT - expose))


def preparer(lignes: list[dict], modele: dict, champ: str = "") -> None:
    for x in lignes:
        x["mu" + champ], x["se" + champ] = avantage(modele, x["ecart"])


def variance_entre_periodes(ecart_vu: float, erreur_b: float, erreur_a: float) -> float:
    """Variance du niveau d'avantage d'une période à l'autre, lue sur l'écart entre la CLV de B et la prévision
    faite sur A : cet écart mêle deux niveaux de période et deux erreurs de mesure."""
    return max(0.0, (ecart_vu ** 2 - erreur_b ** 2 - erreur_a ** 2) / 2)


def _rho(x: dict, y: dict, rho: float) -> float:
    return 1.0 if x["selection"] == y["selection"] else rho


def rejouer(lignes: list[dict], fraction: float | None, rho: float, champ: str = "", bankroll: float = BANKROLL) -> dict:
    """Rejoue les paris dans l'ordre réel. fraction None : mise fixe. La bankroll qui sert à calculer une mise est
    celle des paris déjà réglés à l'heure de la détection."""
    w, pic, creux, perte_max, perte_max_eur = bankroll, bankroll, bankroll, 0.0, 0.0
    attente: list = []                     # (heure de règlement, rang, gain, mise, match)
    en_jeu, par_match = 0.0, defaultdict(list)
    mises = np.zeros(len(lignes))
    for i, x in enumerate(lignes):
        while attente and attente[0][0] <= x["detecte"]:
            _, j, gain, mise, ev = heapq.heappop(attente)
            w += gain
            en_jeu -= mise
            par_match[ev] = [o for o in par_match[ev] if o[0] != j]
            pic, creux = max(pic, w), min(creux, w)
            perte_max, perte_max_eur = max(perte_max, 1 - w / pic), max(perte_max_eur, pic - w)
        if fraction is None:
            mise = MISE_FIXE
        elif w <= 0:
            mise = 0.0
        else:
            mu, se = "mu" + champ, "se" + champ
            ouverts = [(m / w, variance(o[mu], o["cote"]), _rho(x, o, rho)) for _, o, m in par_match[x["match"]]]
            mise = w * mise_kelly(x[mu], x[se], x["cote"], fraction, ouverts, en_jeu / w)
        mises[i] = mise
        if mise > 0:
            en_jeu += mise
            par_match[x["match"]].append((i, x, mise))
            heapq.heappush(attente, (x["regle"], i, mise * x["rendement"], mise, x["match"]))
    while attente:
        _, j, gain, mise, ev = heapq.heappop(attente)
        w += gain
        pic, creux = max(pic, w), min(creux, w)
        perte_max, perte_max_eur = max(perte_max, 1 - w / pic), max(perte_max_eur, pic - w)
    joues = mises > 0
    return {"mises": mises, "paris": int(joues.sum()), "total_mises": float(mises.sum()), "gain": float(w - bankroll),
            "finale": float(w), "creux": float(creux), "perte_max": float(perte_max), "perte_max_eur": float(perte_max_eur),
            "mise_moyenne": float(mises[joues].mean()) if joues.any() else 0.0}


# ---------------------------------------------------------------- trajectoires d'un an

def parts_du_jour(jour: list[dict], fraction: float, rho: float) -> np.ndarray:
    """Parts de bankroll misées sur les paris d'un jour, tous ouverts en même temps, dans l'ordre de détection."""
    parts, par_match, expose = np.zeros(len(jour)), defaultdict(list), 0.0
    for i, x in enumerate(jour):
        ouverts = [(parts[j], variance(o["mu"], o["cote"]), _rho(x, o, rho)) for j, o in par_match[x["match"]]]
        parts[i] = mise_kelly(x["mu"], x["se"], x["cote"], fraction, ouverts, expose)
        expose += parts[i]
        par_match[x["match"]].append((i, x))
    return parts


def tirer_jour(jour: list[dict], avantage_reel: np.ndarray, rho: float, n: int, rng: np.random.Generator) -> np.ndarray:
    """n tirages des rendements des paris d'un jour (n × paris). Un pari gagne avec la probabilité
    (1 + avantage réel) / cote ; les paris d'un même match partagent un facteur commun (copule gaussienne dont la
    corrélation rend celle des résultats pour deux paris à 50 %), une même sélection partage tout."""
    r = math.sin(math.pi * rho / 2)
    normale = NormalDist()
    cotes = np.array([x["cote"] for x in jour])
    seuils = np.array([normale.inv_cdf(min(max((1 + a) / c, 1e-6), 1 - 1e-6)) for a, c in zip(avantage_reel, cotes)])
    matchs = {m: i for i, m in enumerate(dict.fromkeys(x["match"] for x in jour))}
    selections = {s: i for i, s in enumerate(dict.fromkeys(x["selection"] for x in jour))}
    zm = rng.standard_normal((n, len(matchs)))[:, [matchs[x["match"]] for x in jour]]
    zs = rng.standard_normal((n, len(selections)))[:, [selections[x["selection"]] for x in jour]]
    gagne = math.sqrt(r) * zm + math.sqrt(1 - r) * zs < seuils
    return np.where(gagne, cotes - 1, -1.0)


def resumer_trajectoires(w: np.ndarray, depart: float, roi: np.ndarray) -> dict:
    """w : bankroll en fin de chaque jour (trajectoires × jours)."""
    avec_depart = np.column_stack([np.full(len(w), depart), w])
    pic = np.maximum.accumulate(avec_depart, axis=1)
    perte = (1 - avec_depart / pic).max(axis=1)
    perte_eur = (pic - avec_depart).max(axis=1)
    creux = avec_depart.min(axis=1)
    return {"roi_median": float(np.median(roi)), "finale_mediane": float(np.median(w[:, -1])),
            "finale_5": float(np.percentile(w[:, -1], 5)), "finale_95": float(np.percentile(w[:, -1], 95)),
            "perte_max_mediane": float(np.median(perte)), "perte_max_95": float(np.percentile(perte, 95)),
            "perte_max_eur_mediane": float(np.median(perte_eur)), "perte_max_eur_95": float(np.percentile(perte_eur, 95)),
            "perd_moitie": float((creux <= PERTE_MOITIE * depart).mean()), "ruine": float((creux <= RUINE * depart).mean()),
            "finit_en_perte": float((w[:, -1] < depart).mean())}


def simuler(lignes: list[dict], rho: float, trajectoires: int, rng: np.random.Generator) -> dict:
    """Trajectoires d'un an : chaque jour est un jour réel tiré au hasard (ses matchs, ses paris, leurs cotes), les
    résultats sont tirés selon le scénario. Les mises du jour se calculent sur la bankroll du matin."""
    par_jour = defaultdict(list)
    for x in lignes:
        par_jour[x["jour"]].append(x)
    jours = [par_jour[j] for j in sorted(par_jour)]
    methodes = {"fixe": None, **{f"kelly_{f:g}": (f, rho) for f in FRACTIONS},
                **{f"kelly_{f:g}_sans_correlation": (f, 0.0) for f in SANS_CORRELATION}}
    parts = {nom: [np.full(len(j), np.nan) if m is None else parts_du_jour(_sans_lien(j) if m[1] == 0 else j, m[0], m[1])
                   for j in jours] for nom, m in methodes.items()}
    tirage = rng.integers(0, len(jours), (trajectoires, JOURS))
    out = {"jours_reels": len(jours), "paris_par_jour": len(lignes) / len(jours), "trajectoires": trajectoires,
           "parts": {nom: _resume_parts(np.concatenate(p)) for nom, p in parts.items() if nom != "fixe"}, "scenarios": {}}
    for cle, _ in SCENARIOS:
        rend = {nom: np.zeros((trajectoires, JOURS)) for nom in methodes}       # rendement du jour, en part de bankroll
        mise = {nom: np.zeros((trajectoires, JOURS)) for nom in methodes}
        for d, jour in enumerate(jours):
            ou = tirage == d
            if not ou.any():
                continue
            mu = np.array([x["mu"] for x in jour])
            reel = {"modele": mu, "moitie": mu / 2, "nul": np.zeros(len(jour)), "negatif": np.full(len(jour), -0.02)}[cle]
            r = tirer_jour(jour, reel, rho, int(ou.sum()), rng)
            for nom in methodes:
                if nom == "fixe":
                    rend[nom][ou], mise[nom][ou] = MISE_FIXE * r.sum(axis=1), MISE_FIXE * len(jour)
                else:
                    rend[nom][ou], mise[nom][ou] = r @ parts[nom][d], parts[nom][d].sum()
        bloc = {}
        for nom in methodes:
            if nom == "fixe":
                bloc[nom] = {str(int(b)): resumer_trajectoires(*_mise_fixe(rend[nom], mise[nom], b))
                             for b in (BANKROLL, 2 * BANKROLL, 5 * BANKROLL)}
            else:
                w = BANKROLL * np.cumprod(1 + rend[nom], axis=1)
                avant = np.column_stack([np.full(trajectoires, BANKROLL), w[:, :-1]])
                roi = (avant * rend[nom]).sum(axis=1) / (avant * mise[nom]).sum(axis=1)
                bloc[nom] = resumer_trajectoires(w, BANKROLL, roi)
        out["scenarios"][cle] = bloc
    return out


def _mise_fixe(gains: np.ndarray, mises: np.ndarray, depart: float) -> tuple[np.ndarray, float, np.ndarray]:
    """Bankroll à mise fixe, jour par jour : on arrête de parier le jour où elle ne couvre plus une mise, et elle
    ne descend pas sous zéro. Le ROI rendu est celui de tous les paris de l'année, joués ou non."""
    w = depart + np.cumsum(gains, axis=1)
    avant = np.column_stack([np.full(len(w), depart), w[:, :-1]])
    joue = np.logical_and.accumulate(avant >= MISE_FIXE, axis=1)
    w = np.maximum(depart + np.cumsum(np.where(joue, gains, 0.0), axis=1), 0.0)
    return w, depart, gains.sum(axis=1) / mises.sum(axis=1)


def _sans_lien(jour: list[dict]) -> list[dict]:
    """Les mêmes paris, chacun traité comme un match et une sélection à part : Kelly sans correction."""
    return [{**x, "match": i, "selection": i} for i, x in enumerate(jour)]


def _resume_parts(p: np.ndarray) -> dict:
    joues = p[p > 0]
    return {"joues": float((p > 0).mean()), "moyenne": float(joues.mean()) if len(joues) else 0.0,
            "mediane": float(np.median(joues)) if len(joues) else 0.0,
            "plafonnes": float((joues >= PLAFOND_PARI - 1e-12).mean()) if len(joues) else 0.0}


def fraction_retenue(simu: dict) -> float | None:
    """La plus grande fraction qui, sans aucun avantage réel, perd la moitié de la bankroll en un an dans moins de
    RISQUE_ACCEPTE des trajectoires."""
    for f in FRACTIONS:
        if simu["scenarios"]["nul"][f"kelly_{f:g}"]["perd_moitie"] <= RISQUE_ACCEPTE:
            return f
    return None


# ---------------------------------------------------------------- analyse

def nom_fraction(f: float) -> str:
    return f"Kelly 1/{round(1 / f)}"


def analyser(donnees: Path, tirages: int = 10000, trajectoires: int = 2000, graine: int = GRAINE) -> dict:
    rng = np.random.default_rng(graine)
    plafond = simulation.COTE_MAX_PRISE
    lignes = charger(donnees)
    segs = segments(lignes, plafond, tirages, rng)
    exclus = ecartes(segs)
    for s in segs:
        s["ecarte"] = (s["dimension"], s["segment"]) in exclus
        s["confirmation"] = confirmation(s) if s["ecarte"] else None
    for x in lignes:
        x["retenu"] = retenu(x, exclus, plafond)
    a = [x for x in lignes if x["periode"] == "A"]
    b = [x for x in lignes if x["periode"] == "B"]
    figee = [x for x in lignes if x["retenu"]]
    correlation = correlation_match([x for x in a if x["cote"] <= plafond], tirages, rng)
    rho = correlation["autres"]["rho"]

    ensembles, differences = {}, {}
    for nom, groupe in (("A", a), ("B", b), ("tout", lignes)):
        sous = {"Site actuel : paris uniques, cote ≤ plafond": [x for x in groupe if x["cote"] <= plafond],
                "Stratégie figée": [x for x in groupe if x["retenu"]],
                "Écartés (cote ≤ plafond)": [x for x in groupe if x["cote"] <= plafond and not x["retenu"]],
                "Cote > plafond": [x for x in groupe if x["cote"] > plafond],
                "Stratégie figée, référence Pinnacle": [x for x in groupe if x["retenu"] and x["segments"]["Référence"] == "Pinnacle"],
                "Stratégie figée, autres références": [x for x in groupe if x["retenu"] and x["segments"]["Référence"] != "Pinnacle"]}
        ensembles[nom] = {k: mesurer(v, tirages, rng) for k, v in sous.items()}
        differences[nom] = {c: difference(sous["Stratégie figée"], sous["Écartés (cote ≤ plafond)"], c, tirages, rng)
                            for c in ("clv", "rendement")}

    # Le modèle d'avantage ajusté sur A tient-il sur B ?
    modele_a = ajuster_avantage([x for x in a if x["retenu"]], min(tirages, 5000), rng)
    preparer(lignes, modele_a, "_a")
    vb = [x for x in b if x["retenu"] and x["clv"] is not None]
    prevu, vu = np.array([x["mu_a"] for x in vb]), np.array([x["clv"] for x in vb])
    tiers = [{"paris": len(t), "prevu": float(prevu[t].mean()), "clv": float(vu[t].mean())}
             for t in np.array_split(np.argsort(prevu), 3)]
    ecart = rapport(*grappes(vu - prevu, np.ones(len(vb)), [x["match"] for x in vb]), tirages, rng)
    erreur_a = avantage(modele_a, float(np.mean([min(x["ecart"], ECART_MAX) for x in vb])))[1]
    validation = {"mesures": len(vb), "prevu": float(prevu.mean()), "clv": float(vu.mean()), "pente": droite(prevu, vu)[1],
                  "tiers": tiers, "ecart": ecart["valeur"], "ecart_ic": ecart["ic"], "ecart_erreur_type": ecart["erreur_type"]}

    # Modèle proposé : même droite sur A et B, l'instabilité entre périodes comptée dans l'incertitude.
    modele = ajuster_avantage(figee, min(tirages, 5000), rng)
    modele["var_periode"] = variance_entre_periodes(ecart["valeur"], ecart["erreur_type"], erreur_a)
    preparer(lignes, modele)

    rejeux = {}
    for nom, groupe in (("B", b), ("tout", lignes)):
        retenus = [x for x in groupe if x["retenu"]]
        site = [x for x in groupe if x["cote"] <= plafond]
        essais = [("Mise fixe, site actuel (cote ≤ plafond)", site, None, rho, ""), ("Mise fixe, stratégie figée", retenus, None, rho, "")]
        essais += [(f"{nom_fraction(f)}, modèle de A", retenus, f, rho, "_a") for f in FRACTIONS[1:4]]
        essais += [(f"{nom_fraction(f)}, modèle proposé", retenus, f, rho, "") for f in FRACTIONS[1:]]
        essais += [(f"{nom_fraction(f)}, modèle proposé, sans correction de corrélation", retenus, f, None, "")
                   for f in SANS_CORRELATION]
        bloc = {}
        for cle, paris_, fraction, r, champ in essais:
            jeu = _sans_lien(paris_) if r is None else paris_
            res = rejouer(jeu, fraction, r or 0.0, champ)
            mises = res.pop("mises")
            m = mesurer(paris_, tirages, rng, mises)
            bloc[cle] = {**res, "roi": m["roi"], "roi_ic": m["roi_ic"]}
        rejeux[nom] = bloc

    simu = simuler(figee, rho, trajectoires, rng)
    try:
        commit = subprocess.run(["git", "-C", str(donnees), "log", "-1", "--format=%h du %cI"], capture_output=True,
                                text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        commit = "inconnu"
    grille = (.03, .04, .05, .07, .10)
    return {"commit_donnees": commit, "tirages": tirages, "graine": graine, "coupure": COUPURE, "plafond": plafond,
            "paris": len(lignes), "du": lignes[0]["detecte"].date().isoformat(), "au": lignes[-1]["detecte"].date().isoformat(),
            "periodes": {k: {"paris": len(g), "matchs": len({x["match"] for x in g})} for k, g in (("A", a), ("B", b))},
            "segments": segs, "ecartes": [list(e) for e in exclus], "ensembles": ensembles, "differences": differences,
            "modele_a": modele_a, "avantages_a": {f"{e:g}": list(avantage(modele_a, e)) for e in grille},
            "validation_modele": validation, "modele": modele, "avantages": {f"{e:g}": list(avantage(modele, e)) for e in grille},
            "correlation": correlation, "rho": rho, "rejeux": rejeux, "simulation": simu, "fraction_retenue": fraction_retenue(simu)}


# ---------------------------------------------------------------- sortie

def nb(x, d=2, signe=False) -> str:
    return "—" if x is None else f"{x:{'+' if signe else ''}.{d}f}".replace(".", ",").replace("-", "−")


def pct(x, d=1) -> str:
    return "—" if x is None else nb(x * 100, d, True) + " %"


def part(x, d=1) -> str:
    return "—" if x is None else nb(x * 100, d) + " %"


def ic(v, d=1, facteur=100) -> str:
    return "—" if not v else f"[{nb(v[0] * facteur, d, True)} ; {nb(v[1] * facteur, d, True)}]"


def eur(x, d=0) -> str:
    return f"{x:,.{d}f} €".replace(",", " ").replace(".", ",").replace("-", "−")


def _ligne_mesure(m: dict) -> str:
    return f"{m['paris']} | {pct(m['roi'])} | {ic(m['roi_ic'])} | {pct(m['clv'], 2)} | {ic(m['clv_ic'], 2)} | {m['mesures']}"


def _modele(m: dict, avantages: dict, titre: str) -> list[str]:
    out = [f"{titre} : {m['mesures']} paris avec clôture Pinnacle ({m['matchs']} matchs). Avantage = {pct(m['a'], 2)} + "
           f"{nb(m['b'])} × min(écart, {part(ECART_MAX, 0)}) ; erreurs types {part(math.sqrt(m['var_a']), 2)} et "
           f"{nb(math.sqrt(m['var_b']))} ; écart-type d'une période à l'autre {part(math.sqrt(m['var_periode']), 2)} ; "
           f"écart-type de la CLV d'un pari {part(m['ecart_type_clv'])}.", "",
           "| Écart annoncé | Avantage prévu | Erreur type | Facteur d'incertitude | Avantage compté dans la mise |", "|---|---|---|---|---|"]
    for e, (mu, se) in avantages.items():
        k = facteur_incertitude(mu, se)
        out.append(f"| {part(float(e), 0)} | {pct(mu, 2)} | {part(se, 2)} | {nb(k)} | {pct(k * mu, 2)} |")
    return out + [""]


def markdown(r: dict) -> str:
    p = f"{r['plafond']:g}"
    out = ["# Stratégie de mises : tableaux complets", "",
           f"Produit par `scripts/strategie_mises.py` sur le commit `{r['commit_donnees']}` de `donnees`, graine {r['graine']}, "
           f"{r['tirages']} tirages. {r['paris']} paris uniques réglés du {r['du']} au {r['au']}. "
           f"A : matchs détectés avant le {r['coupure'][:10]} ({r['periodes']['A']['paris']} paris, {r['periodes']['A']['matchs']} "
           f"matchs) ; B : les autres ({r['periodes']['B']['paris']} paris, {r['periodes']['B']['matchs']} matchs). "
           "Lecture : [strategie-mises.md](strategie-mises.md).", "",
           "## Segments", "",
           f"Hors « Tranche de cote » : cotes ≤ {p} seulement. ROI à mise fixe. CLV : contre la clôture Pinnacle ; "
           "« Mes. » = paris qui l'ont. Intervalles à 95 % par match. « écarté » : CLV négative sur A avec au moins "
           f"{MIN_MESURES} mesures.", ""]
    for dim in DIMENSIONS:
        out += [f"### {dim}", "",
                "| Segment | Pér. | Paris | ROI | IC 95 % | CLV Pinnacle | IC 95 % | Mes. | Règle |", "|---|---|---|---|---|---|---|---|---|"]
        for s in (s for s in r["segments"] if s["dimension"] == dim):
            for per in ("A", "B", "tout"):
                regle = ("**écarté**" if per == "A" else s["confirmation"] if per == "B" else "") if s["ecarte"] else ""
                out.append(f"| {s['segment'] if per == 'A' else ''} | {per} | {_ligne_mesure(s[per])} | {regle} |")
        out.append("")
    out += ["## Ensembles", "", "| Ensemble | Pér. | Paris | ROI | IC 95 % | CLV Pinnacle | IC 95 % | Mes. |", "|---|---|---|---|---|---|---|---|"]
    for nom in r["ensembles"]["A"]:
        for per in ("A", "B", "tout"):
            out.append(f"| {nom.replace('plafond', p) if per == 'A' else ''} | {per} | {_ligne_mesure(r['ensembles'][per][nom])} |")
    out += ["", "Stratégie figée moins écartés (cote ≤ " + p + "). CLV Pinnacle : " + " ; ".join(
        f"{per} {pct(d['clv']['valeur'], 2)} {ic(d['clv']['ic'], 2)}" for per, d in r["differences"].items()) + ". ROI : " + " ; ".join(
        f"{per} {pct(d['rendement']['valeur'])} {ic(d['rendement']['ic'])}" for per, d in r["differences"].items()) + ".", ""]
    v = r["validation_modele"]
    out += ["## Modèle d'avantage", ""] + _modele(r["modele_a"], r["avantages_a"], "Ajusté sur les paris retenus de A")
    out += [f"Sur B ({v['mesures']} paris retenus avec clôture Pinnacle) : avantage prévu {pct(v['prevu'], 2)}, CLV observée "
            f"{pct(v['clv'], 2)}, observé − prévu {pct(v['ecart'], 2)} {ic(v['ecart_ic'], 2)}, pente {nb(v['pente'])}.", "",
            "| Tiers d'avantage prévu (B) | Paris | Prévu | CLV observée |", "|---|---|---|---|"]
    out += [f"| {n} | {t['paris']} | {pct(t['prevu'], 2)} | {pct(t['clv'], 2)} |" for n, t in zip(("bas", "moyen", "haut"), v["tiers"])]
    out += [""] + _modele(r["modele"], r["avantages"], "Modèle proposé, réajusté sur les paris retenus de A et de B")
    out += ["## Corrélation entre paris d'un même match (période A)", "",
            "| Paire | Paires | Matchs | Corrélation | IC 95 % |", "|---|---|---|---|---|"]
    for cle, nom in (("meme_selection", "Même sélection, autre bookmaker"), ("meme_marche", "Même marché, autre ligne ou issue"),
                     ("autre_marche", "Autre marché ou période"), ("autres", "Toutes sauf même sélection (valeur utilisée)")):
        c = r["correlation"][cle]
        out.append(f"| {nom} | {c['paires']} | {c['matchs']} | {nb(c['rho'], 2, True)} | {ic(c['ic'], 2, 1)} |")
    out += ["", f"## Rejeu des paris réels (bankroll de départ {eur(BANKROLL)})", "",
            "« Modèle de A » sur B : test hors échantillon. « Modèle proposé » : ajusté sur ces mêmes paris.", "",
            "| Mise | Pér. | Paris joués | Mises | Mise moyenne | Gain | ROI | IC 95 % | Perte maximale | Bankroll au plus bas |",
            "|---|---|---|---|---|---|---|---|---|---|"]
    for nom in r["rejeux"]["B"]:
        for per in ("B", "tout"):
            x = r["rejeux"][per][nom]
            out.append(f"| {nom.replace('plafond', p) if per == 'B' else ''} | {per} | {x['paris']} | {eur(x['total_mises'])} | "
                       f"{eur(x['mise_moyenne'], 2)} | {eur(x['gain'])} | {pct(x['roi'])} | {ic(x['roi_ic'])} | "
                       f"{eur(x['perte_max_eur'])} ({part(x['perte_max'])}) | {eur(x['creux'])} |")
    s = r["simulation"]
    kelly = lambda nom: nom_fraction(float(nom.split("_")[1])) + (" sans correction de corrélation" if "sans" in nom else "")  # noqa: E731
    out += ["", "## Trajectoires d'un an", "",
            f"{s['trajectoires']} trajectoires de {JOURS} jours, {nb(s['paris_par_jour'], 0)} paris par jour en moyenne, tirés parmi "
            f"{s['jours_reels']} jours réels. Bankroll de départ {eur(BANKROLL)} sauf mention. « Perd la moitié » : la bankroll "
            f"passe sous {part(PERTE_MOITIE, 0)} du départ au moins une fois ; « ruine » : sous {part(RUINE, 0)}. La mise fixe "
            "s'arrête quand la bankroll ne couvre plus une mise.", "",
            "| Mise de Kelly (modèle proposé) | Paris joués | Mise moyenne | Mise médiane | Au plafond par pari |", "|---|---|---|---|---|"]
    out += [f"| {kelly(nom)} | {part(x['joues'], 0)} | {part(x['moyenne'], 2)} | {part(x['mediane'], 2)} | "
            f"{part(x['plafonnes'], 0)} |" for nom, x in s["parts"].items()]
    for cle, nom in SCENARIOS:
        out += ["", f"### {nom}", "",
                "| Mise | ROI médian | Bankroll finale médiane | 5 % – 95 % | Perte maximale médiane | Perte maximale, 1 an sur 20 | "
                "Finit en perte | Perd la moitié | Ruine |", "|---|---|---|---|---|---|---|---|---|"]
        for m_, x in s["scenarios"][cle].items():
            lignes_ = [(f"Fixe {MISE_FIXE:g} €, bankroll {eur(float(b))}", y) for b, y in x.items()] if m_ == "fixe" else [(kelly(m_), x)]
            for titre, y in lignes_:
                out.append(f"| {titre} | {pct(y['roi_median'])} | {eur(y['finale_mediane'])} | {eur(y['finale_5'])} – {eur(y['finale_95'])} | "
                           f"{eur(y['perte_max_eur_mediane'])} ({part(y['perte_max_mediane'], 0)}) | "
                           f"{eur(y['perte_max_eur_95'])} ({part(y['perte_max_95'], 0)}) | {part(y['finit_en_perte'])} | "
                           f"{part(y['perd_moitie'])} | {part(y['ruine'])} |")
    return "\n".join(out) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--donnees", type=Path, required=True)
    ap.add_argument("--tirages", type=int, default=10000)
    ap.add_argument("--trajectoires", type=int, default=2000)
    ap.add_argument("--graine", type=int, default=GRAINE)
    ap.add_argument("--json", type=Path, help="écrit tous les chiffres dans ce fichier")
    ap.add_argument("--markdown", type=Path, help="écrit les tableaux complets dans ce fichier")
    a = ap.parse_args()
    r = analyser(a.donnees, a.tirages, a.trajectoires, a.graine)
    if a.json:
        a.json.write_text(json.dumps(r, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if a.markdown:
        a.markdown.write_text(markdown(r), encoding="utf-8")
    print(f"{r['paris']} paris uniques réglés ({r['du']} au {r['au']}) | écartés sur A : "
          + ", ".join(f"{d} {s}" for d, s in r["ecartes"]))
    for per in ("A", "B"):
        m = r["ensembles"][per]["Stratégie figée"]
        print(f"  Stratégie figée, {per} : {m['paris']} paris, ROI {pct(m['roi'])} {ic(m['roi_ic'])}, "
              f"CLV Pinnacle {pct(m['clv'], 2)} {ic(m['clv_ic'], 2)}")
    v = r["validation_modele"]
    print(f"  Modèle de A sur B : prévu {pct(v['prevu'], 2)}, observé {pct(v['clv'], 2)} | corrélation dans un match : "
          f"{nb(r['rho'])} | fraction de Kelly retenue : {r['fraction_retenue']}")


if __name__ == "__main__":
    main()
