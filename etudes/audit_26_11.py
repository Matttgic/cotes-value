"""Audit « stratégie » du 26/11/2026 : que jouer, quoi arrêter, combien miser, chiffres à l'appui. Lecture seule.

Usage : python etudes/audit_26_11.py --donnees CHEMIN [--tirages 10000] [--json FICHIER] [--markdown FICHIER]
CHEMIN = branche « donnees » extraite (paris.json, archives/, recommandees.json, bankroll.json). Demande numpy
(requirements-dev.txt). Environ 5 minutes, dont 2 pour les sélections des 97 stratégies du registre. Même graine,
mêmes données : mêmes chiffres. Rapport : docs/audit-26-11-strategie.md. Suite de docs/avantage-reel.md (13/11) et
de docs/strategie-mises.md (14/11).

Méthode :
- paris réglés ; ROI = gain / mises, 10 € fixes, remboursés comptés dans les mises (convention du site) ;
- CLV = contre la clôture Pinnacle sans marge (``cotes.protocole.clv_pinnacle``, la mesure du protocole) ;
- univers « règle » : la règle de prise actuelle (``simulation.motif_hors_regle`` : cote ≤ 5, écart ≥ 3 %, hors
  Winamax et OlyBet, au plus 24 h avant le match), une mise par cote française (première détection qui passe la
  règle, comme ``regle_principale.retenus`` mais sur toute la période). Un segment exclu par la règle est mesuré en
  relâchant sa seule contrainte ;
- stratégies : sélection officielle du registre (décisions figées), dans la règle, depuis leur lancement : les
  bilans du site ;
- unité de hasard : le match (``cotes.evenements.identites``). Intervalles à 95 % : bootstrap-t par match
  (``etudes.avantage_reel.rapport``) ; sur les sous-périodes, erreur type par match (formule). p-valeurs : ROI par
  bootstrap-t, CLV par Student par match (``cotes.protocole.moyenne_par_match``) ;
- tests multiples : Benjamini-Hochberg (BH) et Holm sur toutes les lignes testées, ROI et CLV, bilatéral ;
- robustesse : découverte sur les paris détectés avant le gel de la règle (15/11/2026), confirmation sur ceux
  d'après (hors échantillon pour la règle comme pour les stratégies, toutes lancées avant), BH sur les seules
  découvertes, et ROI pas nettement sous la CLV.
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from statistics import NormalDist
from zoneinfo import ZoneInfo

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cotes import pauses, simulation, stockage  # noqa: E402
from cotes.evenements import identites  # noqa: E402
from cotes.protocole import clv_pinnacle, moyenne_par_match  # noqa: E402
from cotes.regle_principale import GEL as GEL_REGLE, retenus  # noqa: E402
from cotes.reglement import GAIN  # noqa: E402
from cotes.strategie_recommandee import charger_fusions  # noqa: E402
from etudes.avantage_reel import benjamini_hochberg, grappes, holm, pente, rapport  # noqa: E402

PARIS_TZ = ZoneInfo("Europe/Paris")
GRAINE = 20261126
MIN_PARIS, MIN_MATCHS, MIN_CLV = 30, 10, 30     # en dessous : ligne affichée, jamais testée
ALPHA, PUISSANCE = 0.05, 0.80
EFFET_ROI = 0.03                                # mission : conclure sur un ROI de +3 %
EFFETS_CLV = (0.01, 0.02)
PLACES_PROTOCOLE = 200                          # Bonferroni du protocole (docs/protocole.md, § 4)
FIN_ETUDE_13_11 = "2026-11-13T18:42:00+00:00"   # dernières données de docs/avantage-reel.md (commit db927c7)
FRACTIONS_KELLY = (4, 8, 16)
TAILLES = (100, 300, 1000, 3000, 10000)
# Tests déjà faits sur ces données, cités avec leur phrase exacte (tests/test_audit_26_11_strategie.py la vérifie).
TESTS_ANTERIEURS = (
    ("docs/avantage-reel.md", "105 lignes regardées", 105),
    ("docs/erreurs-systematiques.md", "56 segments testés", 56),
    ("docs/regle-principale.md", "97 stratégies testées en parallèle", 97),
)


# ---------------------------------------------------------------- outils

def heure(s) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo and d.utcoffset() is not None else None


def _fini(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def dans_regle(p: dict, cote_max: float = simulation.COTE_MAX_PRISE, ecart_min: float = simulation.ECART_MIN_PRISE,
               exclus: tuple[str, ...] = simulation.BOOKMAKERS_EXCLUS,
               avance_h: float = simulation.AVANCE_MAX_PRISE_H) -> bool:
    """La règle de prise (``simulation.motif_hors_regle``), chaque contrainte relâchable. Une valeur absente
    n'exclut pas, comme dans la règle."""
    cote, ecart, sport = p.get("cote"), p.get("ecart"), p.get("sport")
    if _fini(cote) and cote > cote_max:
        return False
    if _fini(ecart) and round(ecart, 6) < ecart_min:
        return False
    if p.get("bookmaker") in exclus or sport in simulation.SPORTS_EXCLUS:
        return False
    if p.get("marche") in simulation.MARCHES_EXCLUS_PAR_SPORT.get(sport, ()):
        return False
    t, d = heure(p.get("detecte")), heure(p.get("debut"))
    return not (t and d and (d - t).total_seconds() > avance_h * 3600)


def regle(p: dict) -> bool:
    return p.get("statut") in GAIN and bool(p.get("mise"))


def univers(paris: list[dict], **relache) -> list[dict]:
    """Paris réglés de la règle (éventuellement relâchée) : la première détection de chaque cote française."""
    passent = [p for p in paris if dans_regle(p, **relache)]
    premiers = simulation.premiers_par_selection(passent)
    return [p for p in passent if id(p) in premiers and regle(p)]


def delai_h(p: dict) -> float | None:
    t, d = heure(p.get("detecte")), heure(p.get("debut"))
    return (d - t).total_seconds() / 3600 if t and d else None


def tranche_delai(p: dict) -> str:
    h = delai_h(p)
    if h is None:
        return "inconnu"
    return next((nom for borne, nom in ((1, "≤ 1 h"), (3, "1–3 h"), (6, "3–6 h"), (12, "6–12 h"), (24, "12–24 h"))
                 if h <= borne), "> 24 h")


def tranche_age(p: dict) -> str:
    """Âge réel du prix Pinnacle à la détection (en-tête du cache, ``age_prix_pinnacle_s``), pas l'heure de lecture."""
    a = p.get("age_prix_pinnacle_s")
    if not _fini(a) or a < 0:
        return "inconnu"
    return next((nom for borne, nom in ((60, "≤ 1 min"), (120, "1–2 min"), (300, "2–5 min")) if a <= borne),
                "> 5 min")


def tranche_heure(p: dict) -> str:
    t = heure(p.get("detecte"))
    if not t:
        return "inconnue"
    h = t.astimezone(PARIS_TZ).hour
    return next((nom for borne, nom in ((8, "0 h – 8 h"), (12, "8 h – 12 h"), (16, "12 h – 16 h"),
                                        (20, "16 h – 20 h")) if h < borne), "20 h – 24 h")


def tranche_ecart(p: dict) -> str:
    s = simulation.SIMULATIONS.get(p.get("simulation"))
    return f"{p['simulation']} ({s['nom']})" if s else "autre"


def periode(p: dict) -> str:
    return "avant" if heure(p["detecte"]) < heure(GEL_REGLE) else "apres"


# ---------------------------------------------------------------- statistiques

def p_bilaterale(p_pos: float | None) -> float | None:
    return None if p_pos is None else min(1.0, 2 * min(p_pos, 1 - p_pos))


def roi_par_match(gains: np.ndarray, mises: np.ndarray, cles: list) -> dict:
    """ROI et erreur type par match (estimateur du rapport, celui de ``rapport``), intervalle normal."""
    g, m = grappes(gains, mises, cles)
    k, total = len(g), float(m.sum())
    r = float(g.sum()) / total
    et = math.sqrt(float(((g - r * m) ** 2).sum()) * k / (k - 1)) / total if k >= 2 else None
    z = NormalDist().inv_cdf(0.975)
    p = p_bilaterale(1 - NormalDist().cdf(r / et)) if et else None
    return {"roi": r, "et": et, "ic": [r - z * et, r + z * et] if et else None, "p": p}


def mesurer(famille: str, nom: str, paris: list[dict], match_de, clv_pin: dict, tirages: int,
            rng: np.random.Generator | None) -> dict:
    """ROI et CLV d'une ligne. ``rng`` absent : intervalles par formule (sous-périodes), sinon bootstrap-t."""
    out = {"famille": famille, "nom": nom, "paris": len(paris), "teste": False, "clv_teste": False}
    if not paris:
        return out
    cles = [match_de(p) for p in paris]
    gains = np.array([float(p.get("gain") or 0.0) for p in paris])
    mises = np.array([float(p["mise"]) for p in paris])
    cotes = np.array([float(p["cote"]) for p in paris])
    out.update(matchs=len(set(cles)), mises=float(mises.sum()), gain=float(gains.sum()),
               roi=float(gains.sum() / mises.sum()), cote_moyenne=float(cotes.mean()),
               du=min(p["detecte"] for p in paris)[:10], au=max(p["detecte"] for p in paris)[:10],
               # ROI ± ceci si chaque pari était juste (variance cote − 1) et indépendant : le bruit seul
               et_hasard=math.sqrt(float((cotes - 1).sum())) / len(paris))
    out["teste"] = len(paris) >= MIN_PARIS and out["matchs"] >= MIN_MATCHS
    if out["teste"]:
        if rng is not None:
            b = rapport(*grappes(gains, mises, cles), tirages, rng)
            out.update(roi_et=b["erreur_type"], roi_ic=b["ic"],
                       roi_p=None if b["p_pos"] is None else min(1.0, 2 * min(b["p_pos"], b["p_neg"])))
        else:
            a = roi_par_match(gains, mises, cles)
            out.update(roi_et=a["et"], roi_ic=a["ic"], roi_p=a["p"])
        if out["roi_et"] and out["et_hasard"]:
            out["effet_plan"] = (out["roi_et"] / out["et_hasard"]) ** 2
    avec = [(p, clv_pin[id(p)], k) for p, k in zip(paris, cles) if id(p) in clv_pin]
    out.update(clv_n=len(avec), clv_part=len(avec) / len(paris))
    if not avec:
        return out
    v = np.array([c for _, c, _ in avec])
    k = [c for _, _, c in avec]
    m = moyenne_par_match(list(v), k)
    out.update(clv=m["moyenne"], clv_et=m["erreur_type"], clv_p_pos=m["p"], clv_ecart_type=float(v.std(ddof=1))
               if len(v) > 1 else None, clv_matchs=m["matchs"])
    if len(avec) >= MIN_CLV and m["matchs"] >= MIN_MATCHS and m["p"] is not None:
        out.update(clv_teste=True, clv_p=p_bilaterale(m["p"]))
        y = np.array([float(p.get("gain") or 0.0) / float(p["mise"]) for p, _, _ in avec])
        out["roi_mesures"] = float(y.mean())
        if rng is not None:
            out["clv_ic"] = rapport(*grappes(v, np.ones(len(v)), k), tirages, rng)["ic"]
            e = rapport(*grappes(y - v, np.ones(len(v)), k), tirages, rng)
            out.update(roi_moins_clv=e["valeur"], roi_moins_clv_ic=e["ic"])
        else:
            z = NormalDist().inv_cdf(0.975)
            out["clv_ic"] = [m["moyenne"] - z * m["erreur_type"], m["moyenne"] + z * m["erreur_type"]]
            e = moyenne_par_match(list(y - v), k)
            if e["erreur_type"]:
                out.update(roi_moins_clv=e["moyenne"], roi_moins_clv_ic=[e["moyenne"] - z * e["erreur_type"],
                                                                       e["moyenne"] + z * e["erreur_type"]])
    return out


def corriger(lignes: list[dict]) -> dict:
    """BH et Holm sur toutes les lignes testées, pour le ROI et pour la CLV (bilatéral). Rend le décompte."""
    out = {}
    for mesure, teste, champ in (("roi", "teste", "roi_p"), ("clv", "clv_teste", "clv_p")):
        avec = [x for x in lignes if x.get(teste) and x.get(champ) is not None]
        p = [x[champ] for x in avec]
        q, h = benjamini_hochberg(p), holm(p)
        for x, qi, hi in zip(avec, q, h):
            x[f"{mesure}_q"], x[f"{mesure}_holm"] = qi, hi
        valeur = "roi" if mesure == "roi" else "clv"
        out[mesure] = {"tests": len(avec), "p_brute_5": sum(pi < ALPHA for pi in p),
                       "bh_positif": sum(x[f"{mesure}_q"] < ALPHA and x[valeur] > 0 for x in avec),
                       "bh_negatif": sum(x[f"{mesure}_q"] < ALPHA and x[valeur] < 0 for x in avec),
                       "holm_positif": sum(x[f"{mesure}_holm"] < ALPHA and x[valeur] > 0 for x in avec),
                       "holm_negatif": sum(x[f"{mesure}_holm"] < ALPHA and x[valeur] < 0 for x in avec),
                       "attendus_par_hasard": round(ALPHA * len(avec), 1)}
    return out


def decouvrir_confirmer(lignes: list[dict], sens: int = 1) -> dict:
    """Découverte (paris d'avant le gel), confirmation (paris d'après) sur la CLV, dans le sens ``sens`` (+1 / −1).

    Découverte : CLV unilatérale dans le sens voulu, BH < 5 % sur toutes les lignes testables avant le gel.
    Confirmation : même test sur les paris d'après le gel, BH sur les seules découvertes testables. « Robuste » :
    confirmée, et (sens positif) ROI des paris mesurés pas nettement sous leur CLV sur toute la période."""
    def p_sens(b):
        return b["clv_p_pos"] if sens > 0 else 1 - b["clv_p_pos"]
    avant = [x for x in lignes if x["avant"].get("clv_teste")]
    q = benjamini_hochberg([p_sens(x["avant"]) for x in avant]) if avant else []
    decouvertes = [x for x, qi in zip(avant, q) if qi < ALPHA and sens * x["avant"]["clv"] > 0]
    testables = [x for x in decouvertes if x["apres"].get("clv_teste")]
    q2 = benjamini_hochberg([p_sens(x["apres"]) for x in testables]) if testables else []
    for x in decouvertes:
        x.setdefault("robustesse", {})[sens] = "en attente (moins de 30 CLV après le gel)"
    confirmees = []
    for x, qi in zip(testables, q2):
        ok = qi < ALPHA and sens * x["apres"]["clv"] > 0
        contredit = sens > 0 and bool(x["tout"].get("roi_moins_clv_ic")) and x["tout"]["roi_moins_clv_ic"][1] < 0
        x["robustesse"][sens] = ("robuste" if ok and not contredit else
                                 "contredite par le ROI" if ok else "non confirmée après le gel")
        x["robustesse_q"] = qi
        if ok and not contredit:
            confirmees.append(x["tout"]["nom"])
    return {"testables_avant": len(avant), "decouvertes": [x["tout"]["nom"] for x in decouvertes],
            "testables_apres": len(testables), "robustes": confirmees}


def n_paris(ecart_type: float, effet: float, alpha: float, unilateral: bool = True, effet_plan: float = 1.0) -> int:
    """Paris nécessaires pour distinguer ``effet`` de zéro avec une puissance de 80 % ; ``effet_plan`` corrige la
    corrélation des paris d'un même match."""
    z = NormalDist().inv_cdf(1 - (alpha if unilateral else alpha / 2)) + NormalDist().inv_cdf(PUISSANCE)
    return math.ceil(effet_plan * (z * ecart_type / effet) ** 2)


def kelly(avantage: float, cote: float) -> float:
    """Fraction de Kelly d'un pari à la cote ``cote`` dont l'espérance de rendement vaut ``avantage`` ; 0 sinon."""
    return max(0.0, avantage) / (cote - 1) if cote > 1 else 0.0


# ---------------------------------------------------------------- lignes

def groupes(paris: list[dict], cle, minimum: int = MIN_PARIS) -> dict[str, list[dict]]:
    """Paris par catégorie ; les catégories de moins de ``minimum`` paris vont dans « autres »."""
    comptes = Counter(cle(p) for p in paris)
    out: dict[str, list[dict]] = {}
    for p in paris:
        c = cle(p)
        out.setdefault(c if comptes[c] >= minimum else "autres", []).append(p)
    return dict(sorted(out.items(), key=lambda kv: (kv[0] == "autres", -len(kv[1]))))


def dimensions(paris: list[dict], sources: dict) -> dict:
    nb = lambda p: len(sources.get(simulation.cle_selection_unique(p), ()))  # noqa: E731
    return {
        "Référence": lambda p: p.get("reference") or "inconnue",
        "Bookmaker": lambda p: p.get("bookmaker") or "inconnu",
        "Sport": lambda p: p.get("sport") or "inconnu",
        "Marché": lambda p: p.get("marche") or "inconnu",
        "Tranche d'écart": tranche_ecart,
        "Plage de cote": lambda p: simulation.tranche(p["cote"]),
        "Délai avant match": tranche_delai,
        "Âge du prix Pinnacle": tranche_age,
        "Heure de détection (Paris)": tranche_heure,
        "Mois": lambda p: p["detecte"][:7],
        "Sources de la cote": lambda p: "2 références ou plus" if nb(p) >= 2 else "1 référence",
    }


def exclusions(paris: list[dict]) -> list[tuple[str, list[dict]]]:
    """Ce que la règle écarte, mesuré en relâchant sa seule contrainte (même univers sinon)."""
    autre = {"Winamax": ("OlyBet",), "OlyBet": ("Winamax",)}
    out = [(f"{b} (exclu)", [p for p in univers(paris, exclus=autre[b]) if p.get("bookmaker") == b])
           for b in ("Winamax", "OlyBet")]
    out.append(("Écart 2–3 % (A, exclu)", [p for p in univers(paris, ecart_min=0.02) if round(p["ecart"], 6) < 0.03]))
    out.append(("Cote 5–10 (exclue)", [p for p in univers(paris, cote_max=10.0) if p["cote"] > 5]))
    out.append(("Cote > 10 (exclue)", [p for p in univers(paris, cote_max=math.inf) if p["cote"] > 10]))
    out.append(("Plus de 24 h avant le match (exclu)",
                [p for p in univers(paris, avance_h=math.inf) if (delai_h(p) or 0) > 24]))
    return out


def selections_strategies(paris: list[dict]) -> list[dict]:
    """Stratégies du registre : paris réglés de leur sélection officielle dans la règle, depuis leur lancement."""
    from cotes.strategies import registre
    dedans = {id(p) for p in paris if dans_regle(p)}
    out = []
    for s in registre.toutes():
        ids = s.selectionner(paris)
        debut = heure(s.debut)
        membres = [p for p in paris if id(p) in ids and id(p) in dedans and regle(p)
                   and (debut is None or heure(p["detecte"]) >= debut)]
        if membres:
            retiree = pauses.RETIREES.get(s.cle)
            out.append({"cle": s.cle, "nom": s.ligne.replace(" (rejeu)", ""), "famille": s.famille,
                        "debut": s.debut, "retiree": (retiree or {}).get("depuis", pauses.RETIREES_DEPUIS)[:10]
                        if retiree else None, "paris": membres})
    return out


def triple(famille: str, nom: str, paris: list[dict], match_de, clv_pin, tirages, rng, debut=None) -> dict:
    """La ligne sur toute la période (bootstrap), avant le gel de la règle et après (formule)."""
    coupe = max(heure(GEL_REGLE), heure(debut) or heure(GEL_REGLE))
    avant = [p for p in paris if heure(p["detecte"]) < heure(GEL_REGLE)]
    apres = [p for p in paris if heure(p["detecte"]) >= coupe]
    return {"tout": mesurer(famille, nom, paris, match_de, clv_pin, tirages, rng),
            "avant": mesurer(famille, nom, avant, match_de, clv_pin, tirages, None),
            "apres": mesurer(famille, nom, apres, match_de, clv_pin, tirages, None)}


# ---------------------------------------------------------------- la CLV prédit-elle le ROI ?

def clv_predit_roi(paris: list[dict], strategies: list[dict], segments: list[dict], match_de, clv_pin: dict,
                   tirages: int, rng: np.random.Generator) -> dict:
    avec = [(p, clv_pin[id(p)]) for p in paris if id(p) in clv_pin]
    fin = heure(FIN_ETUDE_13_11)

    def bloc(sel):
        if len(sel) < MIN_PARIS:
            return None
        x = np.array([c for _, c in sel])
        y = np.array([float(p.get("gain") or 0.0) / float(p["mise"]) for p, _ in sel])
        cles = [match_de(p) for p, _ in sel]
        roi = rapport(*grappes(y, np.ones(len(y)), cles), tirages, rng)
        return {"paris": len(sel), "matchs": len(set(cles)), "clv": float(x.mean()), "roi": roi["valeur"],
                "roi_ic": roi["ic"], "pente": pente(x, y, cles, tirages, rng)}

    out = {"tout": bloc(avec),
           "jusqu_au_13_11": bloc([a for a in avec if heure(a[0]["detecte"]) <= fin]),
           "apres_13_11": bloc([a for a in avec if heure(a[0]["detecte"]) > fin])}
    tries = sorted(avec, key=lambda a: a[1])
    out["cinquiemes"] = []
    for i in range(5):
        part = tries[i * len(tries) // 5:(i + 1) * len(tries) // 5]
        b = bloc(part)
        if b:
            out["cinquiemes"].append({"clv_de": part[0][1], "clv_a": part[-1][1],
                                      **{k: b[k] for k in ("paris", "clv", "roi", "roi_ic")}})

    def entre(lignes, minimum):
        pts = [x for x in lignes if x.get("teste") and x["paris"] >= minimum and x.get("clv_n", 0) >= 50
               and x.get("roi_et")]
        if len(pts) < 5:
            return None
        a = np.array([x["clv"] for x in pts])
        b = np.array([x["roi"] for x in pts])
        rangs = lambda v: np.argsort(np.argsort(v)).astype(float)  # noqa: E731
        z = np.array([(x["roi"] - x["clv"]) / x["roi_et"] for x in pts])
        return {"lignes": len(pts), "correlation": float(np.corrcoef(a, b)[0, 1]),
                "correlation_rangs": float(np.corrcoef(rangs(a), rangs(b))[0, 1]),
                "ecart_type_roi": float(b.std(ddof=1)), "ecart_type_clv": float(a.std(ddof=1)),
                "erreur_type_roi_mediane": float(np.median([x["roi_et"] for x in pts])),
                # (ROI − CLV) / erreur type du ROI : si la CLV est l'avantage, ces z suivent ~N(0, 1)
                "z_moyen": float(z.mean()), "z_carre_moyen": float((z ** 2).mean()),
                "roi_sous_clv": int((z < 0).sum())}
    out["entre_strategies"] = entre(strategies, 100)
    out["entre_segments"] = entre(segments, MIN_PARIS)
    return out


# ---------------------------------------------------------------- puissance, rythme, mises

def rythme(paris: list[dict], fin: datetime, jours: int = 7) -> dict:
    """Paris de la règle principale (``retenus``) détectés par jour, sur les ``jours`` jours pleins (Paris) avant
    ``fin``, et depuis le gel."""
    pris = retenus(paris)
    dernier = fin.astimezone(PARIS_TZ).date()
    debut = dernier - timedelta(days=jours)
    par_jour = Counter(heure(p["detecte"]).astimezone(PARIS_TZ).date() for p in pris)
    fenetre = [par_jour.get(debut + timedelta(days=i), 0) for i in range(jours)]
    depuis = heure(GEL_REGLE).astimezone(PARIS_TZ).date()
    pleins = [par_jour.get(depuis + timedelta(days=i), 0) for i in range((dernier - depuis).days)]
    return {"jours": jours, "du": debut.isoformat(), "au": (dernier - timedelta(days=1)).isoformat(),
            "par_jour": sum(fenetre) / jours, "detail": fenetre,
            "depuis_gel_par_jour": sum(pleins) / len(pleins) if pleins else None, "jours_depuis_gel": len(pleins)}


def puissance(ligne: dict, paris: list[dict], cadence: float) -> dict:
    """Paris (et jours) nécessaires pour conclure sur un ROI de +3 % et sur une CLV de +1 / +2 %."""
    cotes = np.array([float(p["cote"]) for p in paris])
    y = np.array([float(p.get("gain") or 0.0) / float(p["mise"]) for p in paris])
    et_juste = math.sqrt(float((cotes - 1).mean()))          # écart type d'un pari juste à ces cotes
    deff = ligne.get("effet_plan") or 1.0
    out = {"paris": len(paris), "cote_moyenne": float(cotes.mean()), "ecart_type_pari_juste": et_juste,
           "ecart_type_pari_observe": float(y.std(ddof=1)), "effet_plan_roi": deff, "cadence_par_jour": cadence,
           "roi": {}, "clv": {}, "erreur_type_roi_selon_n": {}}
    for nom, alpha, uni in (("unilatéral 5 %", ALPHA, True), ("bilatéral 5 %", ALPHA, False),
                            (f"protocole ({PLACES_PROTOCOLE} places)", ALPHA / PLACES_PROTOCOLE, True)):
        n = n_paris(et_juste, EFFET_ROI, alpha, uni, deff)
        out["roi"][nom] = {"paris": n, "jours": round(n / cadence) if cadence else None}
    for n in TAILLES:
        out["erreur_type_roi_selon_n"][n] = math.sqrt(deff) * et_juste / math.sqrt(n)
    if ligne.get("clv_ecart_type") and ligne.get("clv_et"):
        deff_clv = (ligne["clv_et"] / (ligne["clv_ecart_type"] / math.sqrt(ligne["clv_n"]))) ** 2
        out["ecart_type_clv"], out["effet_plan_clv"] = ligne["clv_ecart_type"], deff_clv
        part = ligne.get("clv_part") or 1.0
        for effet in EFFETS_CLV:
            for nom, alpha in (("unilatéral 5 %", ALPHA), (f"protocole ({PLACES_PROTOCOLE} places)",
                                                           ALPHA / PLACES_PROTOCOLE)):
                n = n_paris(ligne["clv_ecart_type"], effet, alpha, True, deff_clv)
                out["clv"][f"+{round(100 * effet)} % · {nom}"] = {
                    "paris_mesures": n, "jours": round(n / (cadence * part)) if cadence else None}
    return out


def mises(ligne_apres: dict, ligne_tout: dict, paris: list[dict], match_de, bankroll: float | None) -> dict:
    """Kelly fractionné sur l'avantage mesuré (CLV) et corrélation des paris d'un même match."""
    par_match = Counter(match_de(p) for p in paris)
    tailles = np.array(list(par_match.values()), dtype=float)
    m_pondere = float((tailles ** 2).sum() / tailles.sum())          # taille moyenne vue par un pari
    deff = ligne_tout.get("effet_plan") or 1.0
    rho = (deff - 1) / (m_pondere - 1) if m_pondere > 1 else None
    cote = ligne_apres.get("cote_moyenne") or ligne_tout["cote_moyenne"]
    scenarios = {"CLV après le gel": ligne_apres.get("clv"),
                 "borne basse de la CLV après le gel": (ligne_apres.get("clv_ic") or [None])[0],
                 "CLV sur toute la période": ligne_tout.get("clv"),
                 "borne basse sur toute la période": (ligne_tout.get("clv_ic") or [None])[0]}
    out = {"cote": cote, "bankroll": bankroll, "matchs": len(par_match), "paris_par_match": len(paris) / len(par_match),
           "part_matchs_plusieurs_paris": float((tailles >= 2).mean()), "max_paris_match": int(tailles.max()),
           "taille_ponderee": m_pondere, "correlation_meme_match": rho, "scenarios": {}}
    for nom, avantage in scenarios.items():
        if avantage is None:
            continue
        f = kelly(avantage, cote)
        out["scenarios"][nom] = {"avantage": avantage, "kelly": f,
                                 **{f"1/{d}": {"fraction": f / d, "euros": round(f / d * bankroll, 2) if bankroll
                                               else None} for d in FRACTIONS_KELLY}}
    return out


# ---------------------------------------------------------------- analyse

def charger(donnees: Path) -> list[dict]:
    charger_fusions(donnees)
    pauses.charger(donnees)
    return stockage.fusionner_paris(stockage.lire_archives(donnees),
                                    json.loads((donnees / "paris.json").read_text(encoding="utf-8")))


def date_donnees(donnees: Path, paris: list[dict]) -> tuple[str, datetime]:
    try:
        sortie = subprocess.run(["git", "-C", str(donnees), "log", "-1", "--format=%h %cI"], capture_output=True,
                                text=True, check=True).stdout.split()
        return sortie[0], heure(sortie[1])
    except (OSError, subprocess.CalledProcessError, IndexError):
        return "inconnu", max(heure(p["detecte"]) for p in paris)


def analyser(donnees: Path, tirages: int = 10000, graine: int = GRAINE) -> dict:
    paris = charger(donnees)
    commit, fin = date_donnees(donnees, paris)
    liens = identites(paris)
    match_de = lambda p: liens[id(p)]  # noqa: E731
    clv_pin = clv_pinnacle(paris)
    rng = np.random.default_rng(graine)
    base = univers(paris)
    sources = simulation.sources_par_selection(paris)

    regle_ligne = triple("règle", "Règle de prise, une mise par cote", base, match_de, clv_pin, tirages, rng)
    segments = []
    for dim, cle in dimensions(paris, sources).items():
        for nom, membres in groupes(base, cle).items():
            segments.append({"dimension": dim, **triple(dim, nom, membres, match_de, clv_pin, tirages, rng)})
    exclus = [{"dimension": "Exclu par la règle", **triple("exclusion", nom, membres, match_de, clv_pin, tirages, rng)}
              for nom, membres in exclusions(paris)]
    strategies = []
    for s in selections_strategies(paris):
        t = triple("stratégie", s["nom"], s["paris"], match_de, clv_pin, tirages, rng, debut=s["debut"])
        strategies.append({"dimension": "Stratégie", "cle": s["cle"], "famille_registre": s["famille"],
                           "debut": s["debut"], "retiree": s["retiree"], **t})
    toutes = segments + exclus + strategies
    tests = corriger([x["tout"] for x in toutes])
    robustesse = {"positif": decouvrir_confirmer(toutes, +1), "negatif": decouvrir_confirmer(toutes, -1)}
    try:
        bankroll = float(json.loads((donnees / "bankroll.json").read_text(encoding="utf-8"))["bankroll"])
    except (OSError, ValueError, KeyError, TypeError):
        bankroll = None
    cadence = rythme(paris, fin)
    apres = [p for p in base if heure(p["detecte"]) >= heure(GEL_REGLE)]
    return {
        "commit_donnees": commit, "mesure_le": fin.isoformat(), "tirages": tirages, "graine": graine,
        "paris": len(paris), "regles": sum(regle(p) for p in paris),
        "du": min(p["detecte"] for p in paris)[:10], "au": max(p["detecte"] for p in paris)[:10],
        "clv_pinnacle": len(clv_pin), "gel_regle": GEL_REGLE,
        "regle": regle_ligne, "segments": segments, "exclusions": exclus, "strategies": strategies,
        "tests": tests, "lignes_testees": len([x for x in toutes if x["tout"]["teste"]]),
        "tests_anterieurs": [{"doc": d, "phrase": ph, "n": n} for d, ph, n in TESTS_ANTERIEURS],
        "robustesse": robustesse,
        "clv_predit_roi": clv_predit_roi(base, [x["tout"] for x in strategies], [x["tout"] for x in segments],
                                         match_de, clv_pin, tirages, rng),
        "rythme": cadence,
        "puissance": puissance(regle_ligne["tout"], base, cadence["par_jour"]),
        "mises": mises(regle_ligne["apres"], regle_ligne["tout"], apres or base, match_de, bankroll),
    }


# ---------------------------------------------------------------- sorties

def pct(x, d=1, signe=True) -> str:
    if x is None:
        return "—"
    s = f"{100 * x:+.{d}f}" if signe else f"{100 * x:.{d}f}"
    return s.replace("-", "−").replace(".", ",") + " %"


def ic(v, d=1) -> str:
    return "—" if not v else f"[{pct(v[0], d)[:-2]} ; {pct(v[1], d)[:-2]}]"


def pv(x) -> str:
    return "—" if x is None else (f"{x:.3f}".replace(".", ",") if x >= 0.001 else "< 0,001")


def ligne_md(x: dict, nom: str | None = None) -> str:
    return (f"| {nom or x['nom']} | {x['paris']} ({x.get('matchs', 0)}) | {pct(x.get('roi'))} {ic(x.get('roi_ic'))} "
            f"| {pct(x.get('clv'), 2)} {ic(x.get('clv_ic'), 2)} | {x.get('clv_n', 0)} | {pv(x.get('clv_q'))} "
            f"| {pct(x.get('roi_moins_clv'))} {ic(x.get('roi_moins_clv_ic'))} |")


ENTETE = ("| Ligne | Réglés (matchs) | ROI [IC 95 %] | CLV Pinnacle [IC 95 %] | CLV mesurées | q BH (CLV) "
          "| ROI − CLV [IC 95 %] |\n|---|---|---|---|---|---|---|")


def _periodes_md(x: dict) -> str:
    av, ap = x["avant"], x["apres"]
    return (f"| {x['tout']['nom']} | {av['paris']} | {pct(av.get('roi'))} | {pct(av.get('clv'), 2)} "
            f"| {ap['paris']} | {pct(ap.get('roi'))} | {pct(ap.get('clv'), 2)} {ic(ap.get('clv_ic'), 2)} "
            f"| {pv(ap.get('clv_p_pos'))} | {x.get('robustesse', {}).get(1, '—')} |")


def markdown(r: dict) -> str:
    out = [f"Données : commit `{r['commit_donnees']}` du {r['mesure_le']}, {r['paris']} paris dont {r['regles']} "
           f"réglés ({r['du']} au {r['au']}), {r['tirages']} tirages, graine {r['graine']}.", "",
           "## Règle de prise", "", ENTETE]
    out += [ligne_md(r["regle"][k], n) for k, n in (("tout", "Toute la période"), ("avant", "Avant le gel (≤ 14/11)"),
                                                    ("apres", "Après le gel (≥ 15/11, hors échantillon)"))]
    par_dim: dict[str, list] = {}
    for x in r["segments"] + r["exclusions"] + r["strategies"]:
        par_dim.setdefault(x["dimension"], []).append(x)
    for dim, xs in par_dim.items():
        if dim == "Stratégie":
            xs = sorted(xs, key=lambda x: -(x["tout"].get("clv") or -9))
        out += ["", f"## {dim}", "", ENTETE] + [ligne_md(x["tout"], (x["tout"]["nom"] + (f" (retirée {x['retiree']})"
                                                                     if x.get("retiree") else ""))) for x in xs]
        out += ["", "| Ligne | Réglés avant | ROI avant | CLV avant | Réglés après | ROI après | CLV après [IC 95 %] "
                    "| p (CLV > 0) après | Robustesse |", "|---|---|---|---|---|---|---|---|---|"]
        out += [_periodes_md(x) for x in xs]
    t = r["tests"]
    out += ["", "## Tests multiples", "", "| Mesure | Tests | p brute < 5 % | Attendus par hasard | BH + | BH − "
            "| Holm + | Holm − |", "|---|---|---|---|---|---|---|---|"]
    out += [f"| {m.upper()} | {b['tests']} | {b['p_brute_5']} | {b['attendus_par_hasard']} | {b['bh_positif']} "
            f"| {b['bh_negatif']} | {b['holm_positif']} | {b['holm_negatif']} |" for m, b in t.items()]
    for sens, b in r["robustesse"].items():
        out += ["", f"Robustesse ({sens}) : {b['testables_avant']} lignes testables avant le gel, découvertes : "
                f"{', '.join(b['decouvertes']) or 'aucune'} ; testables après : {b['testables_apres']} ; robustes : "
                f"{', '.join(b['robustes']) or 'aucune'}."]
    c = r["clv_predit_roi"]
    out += ["", "## La CLV prédit-elle le ROI ?", "", "| Paris | Réglés (matchs) | CLV | ROI [IC 95 %] | Pente [IC 95 %] |",
            "|---|---|---|---|---|"]
    for k, n in (("tout", "Règle, toute la période"), ("jusqu_au_13_11", "Jusqu'au 13/11 (étude avantage réel)"),
                 ("apres_13_11", "Après le 13/11 (nouveaux)")):
        b = c[k]
        if b:
            out.append(f"| {n} | {b['paris']} ({b['matchs']}) | {pct(b['clv'], 2)} | {pct(b['roi'])} {ic(b['roi_ic'])} "
                       f"| {b['pente']['pente']:.2f} [{b['pente']['ic'][0]:.2f} ; {b['pente']['ic'][1]:.2f}] |"
                       .replace(".", ","))
    out += ["", "| Cinquième de CLV | Paris | CLV moyenne | ROI [IC 95 %] |", "|---|---|---|---|"]
    out += [f"| {pct(q['clv_de'], 1)} à {pct(q['clv_a'], 1)} | {q['paris']} | {pct(q['clv'], 2)} | {pct(q['roi'])} "
            f"{ic(q['roi_ic'])} |" for q in c["cinquiemes"]]
    for k in ("entre_strategies", "entre_segments"):
        if c.get(k):
            e = c[k]
            out.append(f"\n{k} : {e['lignes']} lignes, corrélation CLV–ROI {e['correlation']:+.2f} (rangs "
                       f"{e['correlation_rangs']:+.2f}), écart type du ROI entre lignes {pct(e['ecart_type_roi'], 1, False)}"
                       f", erreur type médiane d'un ROI {pct(e['erreur_type_roi_mediane'], 1, False)}, écart type de la "
                       f"CLV {pct(e['ecart_type_clv'], 2, False)} ; (ROI − CLV) / erreur type : moyenne {e['z_moyen']:+.2f}, "
                       f"carré moyen {e['z_carre_moyen']:.2f}, {e['roi_sous_clv']} lignes sous leur CLV.")
    p, ry = r["puissance"], r["rythme"]
    out += ["", "## Puissance", "", f"Rythme : {ry['par_jour']:.1f} paris de la règle par jour du {ry['du']} au {ry['au']} "
            f"({ry['detail']}), {ry['depuis_gel_par_jour']:.1f} depuis le gel ({ry['jours_depuis_gel']} jours pleins).",
            f"Cote moyenne {p['cote_moyenne']:.2f}, écart type d'un pari juste {p['ecart_type_pari_juste']:.3f} "
            f"(observé {p['ecart_type_pari_observe']:.3f}), effet de plan ROI {p['effet_plan_roi']:.2f}, CLV "
            f"{p.get('effet_plan_clv', 0):.2f} ; écart type de la CLV {pct(p.get('ecart_type_clv'), 1, False)}.", ""]
    out += [f"- ROI +3 %, {k} : {v['paris']} paris, {v['jours']} jours" for k, v in p["roi"].items()]
    out += [f"- CLV {k} : {v['paris_mesures']} paris mesurés, {v['jours']} jours" for k, v in p["clv"].items()]
    out += [f"- erreur type du ROI à {n} paris : {pct(v, 1, False)}" for n, v in p["erreur_type_roi_selon_n"].items()]
    m = r["mises"]
    out += ["", "## Mises", "", f"Bankroll {m['bankroll']} €, cote moyenne {m['cote']:.2f}, {m['paris_par_match']:.2f} "
            f"paris par match, {pct(m['part_matchs_plusieurs_paris'], 0, False)} des matchs avec plusieurs paris "
            f"(au plus {m['max_paris_match']}), corrélation entre paris d'un même match "
            f"{m['correlation_meme_match'] if m['correlation_meme_match'] is None else round(m['correlation_meme_match'], 2)}.", ""]
    for nom, s in m["scenarios"].items():
        out.append(f"- {nom} ({pct(s['avantage'], 2)}) : Kelly {pct(s['kelly'], 2, False)} ; "
                   + " ; ".join(f"{k} : {pct(v['fraction'], 2, False)} = {v['euros']} €" for k, v in s.items()
                                if k.startswith("1/")))
    return "\n".join(out) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--donnees", type=Path, required=True)
    ap.add_argument("--tirages", type=int, default=10000)
    ap.add_argument("--graine", type=int, default=GRAINE)
    ap.add_argument("--json", type=Path, help="écrit tous les chiffres dans ce fichier")
    ap.add_argument("--markdown", type=Path, help="écrit tous les tableaux dans ce fichier")
    a = ap.parse_args()
    r = analyser(a.donnees, a.tirages, a.graine)
    if a.json:
        a.json.write_text(json.dumps(r, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    texte = markdown(r)
    if a.markdown:
        a.markdown.write_text(texte, encoding="utf-8")
    else:
        print(texte)


if __name__ == "__main__":
    main()
