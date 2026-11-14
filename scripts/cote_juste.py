"""Cote juste : comparaison des méthodes de retrait de la marge et des pondérations du consensus. Lecture seule.

Usage :
    python scripts/cote_juste.py marge --football DOSSIER [--donnees CHEMIN] [--tirages 2000]
    python scripts/cote_juste.py consensus --donnees CHEMIN [--tirages 2000]

``--football`` : dossier des fichiers CSV de football-data.co.uk nommés ``SAISON-DIVISION.csv`` (p. ex.
``2425-E0.csv``), cotes Pinnacle et bet365 avec le score final (2 minutes). ``--donnees`` : branche « donnees »
extraite en entier (paris.json, archives/, references/, correspondances/ ; une minute par commande). Demande numpy
(requirements-dev.txt). Même graine, mêmes données : mêmes chiffres. La sortie est en Markdown ; les conclusions
sont dans docs/cote-juste.md.

Rien ici ne sert à la détection : c'est une mesure. Le consensus est jugé sur la clôture (dernier prix avant le
début) faute de résultats en nombre : ``references/`` n'existe que depuis le 12/11/2026.

Méthodes de retrait de la marge (q_i = 1/cote, B = Σ q_i, n issues) :
- multiplicative : p_i = q_i / B ;
- additive : p_i = q_i − (B − 1) / n (peut devenir négative sur un gros outsider) ;
- puissance : p_i = q_i^k, k tel que Σ p_i = 1 (méthode du site, cotes/marge.py) ;
- Shin : p_i = (√(z² + 4 (1 − z) q_i² / B) − z) / (2 (1 − z)), z tel que Σ p_i = 1 ;
- odds ratio : p_i = q_i / (c + q_i − c q_i), c tel que Σ p_i = 1.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

GRAINE = 20261114
METHODES = ("multiplicative", "additive", "puissance", "shin", "odds_ratio")
NOMS = {"multiplicative": "Multiplicative", "additive": "Additive", "puissance": "Puissance (actuelle)",
        "shin": "Shin", "odds_ratio": "Odds ratio"}
PLANCHER = 1e-4          # probabilité minimale pour le calcul du log-loss (l'additive peut passer sous zéro)


# ---------------------------------------------------------------- retrait de la marge

def _bissection(f, bas: np.ndarray, haut: np.ndarray, tours: int = 80) -> np.ndarray:
    """Racine de f (décroissante en x, ligne par ligne) entre bas et haut."""
    for _ in range(tours):
        milieu = (bas + haut) / 2
        positif = f(milieu) > 0
        bas = np.where(positif, milieu, bas)
        haut = np.where(positif, haut, milieu)
    return (bas + haut) / 2


def retirer_marge(cotes: np.ndarray, methode: str) -> np.ndarray:
    """Probabilités sans marge. ``cotes`` : tableau (marchés, issues) de cotes décimales > 1, marge ≥ 0.

    Une somme des 1/cote sous 1 (pas de marge) est simplement normalisée, comme cotes/marge.py."""
    q = 1.0 / np.asarray(cotes, dtype=float)
    b = q.sum(axis=1, keepdims=True)
    n = q.shape[1]
    simple = q / b
    if methode == "multiplicative":
        return simple
    sans_marge = (b <= 1.0 + 1e-12)[:, 0]
    if methode == "additive":
        p = q - (b - 1.0) / n
    elif methode == "puissance":
        k = _bissection(lambda k: (q ** k[:, None]).sum(axis=1) - 1.0, np.full(len(q), 0.2), np.full(len(q), 5.0))
        p = q ** k[:, None]
    elif methode == "shin":
        def somme(z):
            z = z[:, None]
            return ((np.sqrt(z * z + 4 * (1 - z) * q * q / b) - z) / (2 * (1 - z))).sum(axis=1) - 1.0
        z = _bissection(somme, np.zeros(len(q)), np.full(len(q), 0.6))[:, None]
        p = (np.sqrt(z * z + 4 * (1 - z) * q * q / b) - z) / (2 * (1 - z))
    elif methode == "odds_ratio":
        c = _bissection(lambda c: (q / (c[:, None] + q - c[:, None] * q)).sum(axis=1) - 1.0,
                        np.ones(len(q)), np.full(len(q), 50.0))[:, None]
        p = q / (c + q - c * q)
    else:
        raise ValueError(methode)
    p = np.where(sans_marge[:, None], simple, p)
    if methode != "additive":
        p = p / p.sum(axis=1, keepdims=True)
    return p


def cotes_depuis_puissance(p: np.ndarray, marge: np.ndarray) -> np.ndarray:
    """Cotes brutes d'un marché dont on connaît les probabilités « puissance » et la marge : q_i = p_i^(1/k),
    1/k tel que Σ q_i = 1 + marge. C'est ce que garde references/ (cotes/historique_references.py)."""
    cible = 1.0 + np.asarray(marge, dtype=float)
    a = _bissection(lambda a: (p ** a[:, None]).sum(axis=1) - cible, np.full(len(p), 0.2), np.full(len(p), 5.0))
    return 1.0 / (p ** a[:, None])


# ---------------------------------------------------------------- mesures

def _borne(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, PLANCHER, None)
    return p / p.sum(axis=1, keepdims=True)


def log_loss(p: np.ndarray, gagnant: np.ndarray) -> np.ndarray:
    """Log-loss de chaque marché (une issue gagnante)."""
    return -np.log(_borne(p)[np.arange(len(p)), gagnant])


def brier(p: np.ndarray, gagnant: np.ndarray) -> np.ndarray:
    y = np.zeros_like(p)
    y[np.arange(len(p)), gagnant] = 1.0
    return ((p - y) ** 2).sum(axis=1)


def pente_calibration(p: np.ndarray, gagnant: np.ndarray) -> float:
    """β qui maximise la vraisemblance de P_i ∝ p_i^β. β = 1 : calibré ; β > 1 : les favoris gagnent plus souvent
    qu'annoncé (biais favori/outsider restant) ; β < 1 : le retrait de marge a trop corrigé."""
    lp = np.log(_borne(p))
    idx = np.arange(len(p))

    def derivee(beta: float) -> float:
        w = np.exp(beta * lp)
        w /= w.sum(axis=1, keepdims=True)
        return float((lp[idx, gagnant] - (w * lp).sum(axis=1)).sum())
    bas, haut = 0.3, 3.0
    for _ in range(60):
        milieu = (bas + haut) / 2
        if derivee(milieu) > 0:
            bas = milieu
        else:
            haut = milieu
    return (bas + haut) / 2


def intervalle(valeurs: np.ndarray, rng: np.random.Generator, tirages: int, grappes: np.ndarray | None = None
               ) -> tuple[float, float, float]:
    """Moyenne et intervalle à 95 % (bootstrap, par grappe quand ``grappes`` est donné)."""
    valeurs = np.asarray(valeurs, dtype=float)
    if grappes is None:
        sommes, tailles = valeurs, np.ones(len(valeurs))
    else:
        _, inv = np.unique(grappes, return_inverse=True)
        sommes = np.bincount(inv, weights=valeurs)
        tailles = np.bincount(inv).astype(float)
    k = len(sommes)
    moyenne = float(sommes.sum() / tailles.sum())
    if k < 2:
        return moyenne, float("nan"), float("nan")
    tir = np.empty(tirages)
    for debut in range(0, tirages, 200):
        fin = min(tirages, debut + 200)
        i = rng.integers(0, k, size=(fin - debut, k))
        tir[debut:fin] = sommes[i].sum(axis=1) / tailles[i].sum(axis=1)
    bas, haut = np.quantile(tir, [0.025, 0.975])
    return moyenne, float(bas), float(haut)


def courbe(p: np.ndarray, gagnant: np.ndarray, bornes: tuple[float, ...]) -> list[tuple[float, float, int, float, float]]:
    """Par tranche de probabilité annoncée (toutes issues confondues) : bornes, nombre d'issues, probabilité
    annoncée moyenne, fréquence observée."""
    y = np.zeros_like(p)
    y[np.arange(len(p)), gagnant] = 1.0
    pf, yf = p.ravel(), y.ravel()
    out = []
    for a, b in zip(bornes[:-1], bornes[1:]):
        m = (pf >= a) & (pf < b)
        if m.sum():
            out.append((a, b, int(m.sum()), float(pf[m].mean()), float(yf[m].mean())))
    return out


def erreur_pente(p: np.ndarray, beta: float) -> float:
    """Erreur type de la pente de calibration (information observée)."""
    lp = np.log(_borne(p))
    w = np.exp(beta * lp)
    w /= w.sum(axis=1, keepdims=True)
    m = (w * lp).sum(axis=1, keepdims=True)
    info = float((w * (lp - m) ** 2).sum())
    return 1 / math.sqrt(info) if info > 0 else float("nan")


# ---------------------------------------------------------------- football-data.co.uk

# marché -> (colonnes des cotes, colonne de la ligne ou None)
MARCHES_FOOT = {
    ("Pinnacle", "1N2", "avant-match"): (("PSH", "PSD", "PSA"), None),
    ("Pinnacle", "1N2", "clôture"): (("PSCH", "PSCD", "PSCA"), None),
    ("Pinnacle", "Total 2,5 buts", "avant-match"): (("P>2.5", "P<2.5"), None),
    ("Pinnacle", "Total 2,5 buts", "clôture"): (("PC>2.5", "PC<2.5"), None),
    ("Pinnacle", "Handicap asiatique", "avant-match"): (("PAHH", "PAHA"), "AHh"),
    ("Pinnacle", "Handicap asiatique", "clôture"): (("PCAHH", "PCAHA"), "AHCh"),
    ("bet365", "1N2", "avant-match"): (("B365H", "B365D", "B365A"), None),
    ("bet365", "1N2", "clôture"): (("B365CH", "B365CD", "B365CA"), None),
    ("bet365", "Total 2,5 buts", "avant-match"): (("B365>2.5", "B365<2.5"), None),
    ("bet365", "Total 2,5 buts", "clôture"): (("B365C>2.5", "B365C<2.5"), None),
    ("bet365", "Handicap asiatique", "avant-match"): (("B365AHH", "B365AHA"), "AHh"),
    ("bet365", "Handicap asiatique", "clôture"): (("B365CAHH", "B365CAHA"), "AHCh"),
}


def _reel(x) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def lire_football(dossier: Path) -> dict[tuple, dict]:
    """{(bookmaker, marché, moment): {"cotes": tableau, "gagnant": indices, "saison": ..., "match": ...}}.

    Handicap asiatique : seules les lignes entières et demies sont gardées (un quart de but partage la mise entre
    deux lignes : ce n'est plus une probabilité de gagner) ; sur une ligne entière, les matchs remboursés sont
    écartés (la cote porte sur « gagné sachant non remboursé »)."""
    brut: dict[tuple, list] = defaultdict(list)
    for fichier in sorted(Path(dossier).glob("*.csv")):
        saison = fichier.name.split("-")[0]
        with open(fichier, encoding="latin-1", newline="") as f:
            lignes = list(csv.reader(f))
        if not lignes:
            continue
        col = {nom.strip().lstrip("﻿").lstrip("ï»¿"): i for i, nom in enumerate(lignes[0])}
        for num, r in enumerate(lignes[1:]):
            lire = lambda nom: _reel(r[col[nom]]) if nom in col and col[nom] < len(r) else None  # noqa: E731
            d, e = lire("FTHG"), lire("FTAG")
            if d is None or e is None:
                continue
            for cle, (colonnes, col_ligne) in MARCHES_FOOT.items():
                cotes = [lire(c) for c in colonnes]
                if any(c is None or c <= 1.0 for c in cotes):
                    continue
                if sum(1 / c for c in cotes) < 1.0:       # pas de marge : saisie douteuse, rien à comparer
                    continue
                if cle[1] == "1N2":
                    gagnant = 0 if d > e else 1 if d == e else 2
                elif cle[1].startswith("Total"):
                    gagnant = 0 if d + e > 2.5 else 1
                else:
                    ligne = lire(col_ligne)
                    if ligne is None or (ligne * 2) != round(ligne * 2):
                        continue
                    v = d - e + ligne
                    if v == 0:
                        continue
                    gagnant = 0 if v > 0 else 1
                brut[cle].append((cotes, gagnant, saison, f"{fichier.name}:{num}"))
    out = {}
    for cle, lot in brut.items():
        out[cle] = {"cotes": np.array([x[0] for x in lot]), "gagnant": np.array([x[1] for x in lot]),
                    "saison": np.array([x[2] for x in lot]), "match": np.array([x[3] for x in lot])}
    return out


BORNES_COURBE = (0.0, 0.05, 0.10, 0.15, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 1.0001)


def mesurer_marche(cotes: np.ndarray, gagnant: np.ndarray, rng: np.random.Generator, tirages: int,
                   grappes: np.ndarray | None = None, reference: str = "puissance") -> dict:
    """Mesures de chaque méthode sur un lot de marchés complets réglés."""
    probas = {m: retirer_marge(cotes, m) for m in METHODES}
    ll = {m: log_loss(p, gagnant) for m, p in probas.items()}
    br = {m: brier(p, gagnant) for m, p in probas.items()}
    out = {"marches": len(cotes), "marge": float((1 / cotes).sum(axis=1).mean() - 1), "methodes": {}}
    for m in METHODES:
        beta = pente_calibration(probas[m], gagnant)
        d = {"log_loss": float(ll[m].mean()), "brier": float(br[m].mean()), "pente": beta,
             "pente_et": erreur_pente(probas[m], beta),
             "negatives": int((probas[m] <= 0).any(axis=1).sum()),
             "courbe": courbe(probas[m], gagnant, BORNES_COURBE)}
        if m != reference:
            d["ecart_log_loss"] = intervalle(ll[m] - ll[reference], rng, tirages, grappes)
            d["ecart_brier"] = intervalle(br[m] - br[reference], rng, tirages, grappes)
        out["methodes"][m] = d
    return out


# ---------------------------------------------------------------- données du site

def lire_jsonl(chemin: Path):
    with gzip.open(chemin, "rt", encoding="utf-8") as f:
        for ligne in f:
            ligne = ligne.strip()
            if ligne:
                yield json.loads(ligne)


def instant(s) -> float | None:
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d.timestamp() if d.tzinfo else None


def charger_paris(donnees: Path) -> list[dict]:
    from cotes import stockage
    return stockage.fusionner_paris(json.loads((donnees / "paris.json").read_text(encoding="utf-8")),
                                    stockage.lire_archives(donnees))


REGLES_NETTES = ("gagne", "perdu", "rembourse", "demi_gagne", "demi_perdu")


def scores_et_liens(donnees: Path, paris: list[dict]) -> tuple[dict, dict]:
    """(scores par match français, {(référence, match de la référence): {match français: équipes inversées}})."""
    scores, liens = {}, {}
    for p in paris:
        preuve = p.get("preuve_reglement") or {}
        if p.get("statut") in REGLES_NETTES and preuve.get("scores"):
            scores.setdefault(p["match_id"], {
                "sport": p.get("sport"),
                "scores": {k: tuple(v) if isinstance(v, list) else v for k, v in preuve["scores"].items()}})
        prise = p.get("preuve_prise") or {}
        if prise.get("match_id_reference") is not None and p.get("reference") not in (None, "Consensus"):
            liens.setdefault((p["reference"], str(prise["match_id_reference"])), {})[p["match_id"]] = bool(
                prise.get("equipes_inversees"))
    for fichier in sorted((donnees / "correspondances").glob("*.jsonl.gz")):
        for x in lire_jsonl(fichier):
            liens.setdefault((x["b"], str(x["m"])), {})[x["fr"]] = bool(x.get("inv"))
    return scores, liens


def charger_references(donnees: Path) -> tuple[dict, dict]:
    """({(référence, match): {clé: [(instant, cote juste, proba, marge, liquidité, écart achat/vente, limite,
    périmée)]}}, {(référence, match): description}). Les séries sont triées par instant."""
    hist: dict = {}
    desc: dict = {}
    for fichier in sorted((donnees / "references").glob("*.jsonl.gz")):
        for x in lire_jsonl(fichier):
            cle = (x["b"], str(x["m"]))
            if "k" not in x:
                desc[cle] = {k: x.get(k) for k in ("sport", "ligue", "dom", "ext", "debut")}
                continue
            t = instant(x.get("t"))
            if t is None:
                continue
            hist.setdefault(cle, {}).setdefault(x["k"], []).append(
                (t, x.get("c"), x.get("p"), x.get("mg"), x.get("liq"), x.get("ea"), x.get("max"), x.get("per", 0)))
    for series in hist.values():
        for serie in series.values():
            serie.sort(key=lambda e: e[0])
    return hist, desc


def etat(serie: list[tuple], t: float) -> tuple | None:
    """Dernière ligne écrite à l'instant t ou avant ; None si la cote était retirée ou pas encore vue."""
    bas, haut = 0, len(serie)
    while bas < haut:
        milieu = (bas + haut) // 2
        if serie[milieu][0] <= t:
            bas = milieu + 1
        else:
            haut = milieu
    if bas == 0:
        return None
    e = serie[bas - 1]
    return None if e[1] is None or e[2] is None else e


def decouper(k: str) -> dict:
    x = k.split("|")
    return {"marche": x[0], "periode": x[1], "ligne": float(x[2]) if x[2] != "" else None, "issue": x[3],
            "joueur": x[4] if len(x) > 4 else None, "domicile": "", "exterieur": ""}


FAMILLES = ("1N2", "Deux issues", "Totaux", "Handicaps", "Props joueurs")


def famille(marche: str) -> str | None:
    """Type de marché de l'étude ; None : marché à liste ouverte ou dérivé (score exact, double chance…)."""
    if marche.startswith("JOUEUR:"):
        return "Props joueurs"
    if marche.endswith("RESULTAT_1N2"):
        return "1N2"
    if marche.endswith("VAINQUEUR") or marche in ("DRAW_NO_BET", "BOTH_TEAMS_TO_SCORE"):
        return "Deux issues"
    if "TOTAL" in marche:
        return "Totaux"
    if marche.endswith("HANDICAP"):
        return "Handicaps"
    return None


ISSUES = {"1N2": ("DOM", "NUL", "EXT"), "Totaux": ("PLUS", "MOINS"), "Handicaps": ("DOM", "EXT"),
          "Props joueurs": ("PLUS", "MOINS")}


def marches_pinnacle(series: dict, t: float) -> list[dict]:
    """Marchés complets d'un match Pinnacle à l'instant t, avec leurs cotes brutes reconstruites."""
    groupes: dict[tuple, dict] = {}
    for k, serie in series.items():
        e = etat(serie, t)
        if e is None or e[3] is None:
            continue
        l = decouper(k)
        fam = famille(l["marche"])
        if fam is None:
            continue
        groupes.setdefault((l["marche"], l["periode"], l["ligne"], l["joueur"]), {})[l["issue"]] = (l, e)
    out = []
    for cle, issues in groupes.items():
        fam = famille(cle[0])
        attendues = ISSUES.get(fam) or (("YES", "NO") if cle[0] == "BOTH_TEAMS_TO_SCORE" else ("DOM", "EXT"))
        if set(issues) != set(attendues):
            continue
        p = np.array([[issues[i][1][2] for i in attendues]])
        marges = {issues[i][1][3] for i in attendues}
        if len(marges) != 1 or abs(p.sum() - 1) > 5e-4:      # lignes écrites à des instants différents
            continue
        marge = marges.pop()
        if not 0 < marge <= 0.2:
            continue
        out.append({"famille": fam, "marche": cle[0], "issues": attendues, "lignes": [issues[i][0] for i in attendues],
                    "marge": marge, "cotes": cotes_depuis_puissance(p, np.array([marge]))[0]})
    return out


def ecarts_methodes(cotes: np.ndarray) -> dict[str, np.ndarray]:
    """|cote juste de la méthode / cote juste « puissance » − 1| par issue (issues à probabilité > 0)."""
    base = retirer_marge(cotes, "puissance")
    out = {}
    for m in METHODES:
        if m == "puissance":
            continue
        p = retirer_marge(cotes, m)
        out[m] = np.where(p > 0, np.abs(base / np.where(p > 0, p, 1) - 1), np.inf).ravel()
    return out


def rapport_marge_interne(donnees: Path, tirages: int, rng: np.random.Generator) -> None:
    from cotes import reglement
    paris = charger_paris(donnees)
    scores, liens = scores_et_liens(donnees, paris)
    hist, desc = charger_references(donnees)
    fin = max(s[-1][0] for (b, _), series in hist.items() if b == "Pinnacle" for s in series.values())
    # a. enjeu : tous les marchés Pinnacle, au dernier état connu avant le début
    lots: dict[str, list] = defaultdict(list)
    regles: dict[str, list] = defaultdict(list)
    for (b, m), series in hist.items():
        if b != "Pinnacle":
            continue
        debut = instant((desc.get((b, m)) or {}).get("debut"))
        if debut is None:
            continue
        marches = marches_pinnacle(series, min(debut, fin))
        for x in marches:
            lots[x["famille"]].append(x)
        # b. marchés réglés : match commencé, relié à un match français dont le score est connu
        fr = next((f for f in liens.get((b, m), {}) if f in scores), None)
        if fr is None or debut > fin:
            continue
        inverse = liens[(b, m)][fr]
        sc = {k: (v[1], v[0]) if inverse and isinstance(v, tuple) and len(v) == 2 else v
              for k, v in scores[fr]["scores"].items()}
        for x in marches:
            statuts = [reglement.regler({**l, "sport": scores[fr]["sport"]}, sc) for l in x["lignes"]]
            if sorted(statuts, key=str) == sorted(["gagne"] + ["perdu"] * (len(statuts) - 1)):
                regles[x["famille"]].append((x["cotes"], statuts.index("gagne"), m))
    print("## Données du site : enjeu par type de marché (marchés Pinnacle de references/)\n")
    print("Écart : |cote juste de la méthode / cote juste « puissance » − 1|, par issue.\n")
    lignes = []
    for fam in FAMILLES:
        lot = lots.get(fam) or []
        if not lot:
            continue
        cotes = np.array([x["cotes"] for x in lot])
        marges = np.array([x["marge"] for x in lot])
        favori = retirer_marge(cotes, "multiplicative").max(axis=1)
        e = ecarts_methodes(cotes)
        ligne = [fam, str(len(lot)), pct(float(np.median(marges))).lstrip("+"), pct(float(np.quantile(marges, 0.9))).lstrip("+"),
                 f"{100 * float((favori >= 0.75).mean()):.0f} %"]
        for m in ("multiplicative", "additive", "shin", "odds_ratio"):
            fini = e[m][np.isfinite(e[m])]
            ligne.append(f"{100 * float(np.median(fini)):.2f} % · {100 * float(np.quantile(fini, 0.95)):.1f} % · "
                         f"{100 * float((e[m] > 0.02).mean()):.0f} %".replace(".", ","))
        lignes.append(ligne)
    print(tableau(["Type", "Marchés", "Marge médiane", "Marge, 9e décile", "Favori ≥ 75 %"]
                  + [f"{NOMS[m]} : médiane · 95e centile · part > 2 %" for m in ("multiplicative", "additive", "shin", "odds_ratio")],
                  lignes) + "\n")
    print("## Données du site : marchés Pinnacle réglés (dernière cote avant le début, non sélectionnés)\n")
    for fam in FAMILLES:
        lot = regles.get(fam) or []
        if len(lot) < 30:
            print(f"### {fam} : {len(lot)} marchés réglés, trop peu pour une mesure\n")
            continue
        cotes = np.array([x[0] for x in lot])
        r = mesurer_marche(cotes, np.array([x[1] for x in lot]), rng, tirages, grappes=np.array([x[2] for x in lot]))
        print(f"### {fam} : {r['marches']} marchés, {len({x[2] for x in lot})} matchs, marge moyenne {pct(r['marge']).lstrip('+')}\n")
        print(tableau(ENTETES_METHODES, lignes_methodes(r)) + "\n")
    rapport_bourses(hist, desc, fin, tirages, rng)
    rapport_paris_marge(paris, tirages, rng)


ECART_BOURSE_MAX = 0.03       # prix de bourse retenus : fiables selon le site et écart achat/vente ≤ 3 points


def rapport_bourses(hist: dict, desc: dict, fin: float, tirages: int, rng: np.random.Generator) -> None:
    """Chaque méthode appliquée aux cotes Pinnacle, comparée au prix de Polymarket ou de Matchbook lu au même instant
    (une heure avant le début). Un prix de bourse n'a pas de marge à retirer, mais ce n'est pas la vérité."""
    from cotes import comparaison
    assoc = associer_references(hist, desc)
    lots: dict[tuple, list] = defaultdict(list)
    for b in ("Polymarket", "Matchbook"):
        for mp, (mr, inverse, _) in assoc[b].items():
            debut = instant(desc[("Pinnacle", mp)].get("debut"))
            if debut is None or debut > fin:
                continue
            t = debut - 3600
            bourse = _series(hist[(b, mr)], inverse)
            for x in marches_pinnacle(hist[("Pinnacle", mp)], t):
                if x["famille"] == "Props joueurs" or x["marge"] > comparaison.MARGE_MAX_PINNACLE:
                    continue
                cible = []
                for l in x["lignes"]:
                    k = (l["marche"], l["periode"], None if l["ligne"] is None else round(l["ligne"], 2), l["issue"])
                    e = etat(bourse[k], t) if k in bourse else None
                    if (e is None or (e[5] or 0) > ECART_BOURSE_MAX or not comparaison._fiable(
                            b, {"proba_juste": e[2], "liquidite": e[4], "ecart_achat_vente": e[5]})):
                        cible = None
                        break
                    cible.append(e[2])
                if cible is None or abs(sum(cible) - 1) > 0.03:
                    continue
                lots[(b, x["famille"])].append((x["cotes"], np.array(cible) / sum(cible), mp))
    print("## Données du site : chaque méthode face au prix des bourses, une heure avant le début\n")
    print("Divergence de Kullback-Leibler du prix de bourse vers la probabilité de la méthode, ×10⁴ ; écart avec la "
          "puissance et intervalle à 95 % par match. Dernière colonne : probabilité du favori selon la méthode moins "
          "celle de la bourse, en points.\n")
    lignes = []
    for (b, fam), lot in sorted(lots.items()):
        cotes = np.array([x[0] for x in lot])
        cible = np.array([x[1] for x in lot])
        grappes = np.array([x[2] for x in lot])
        favori = retirer_marge(cotes, "multiplicative").max(axis=1)
        for nom, m in (("tous", np.ones(len(lot), dtype=bool)), ("favori ≥ 75 %", favori >= 0.75)):
            if m.sum() < 60:
                continue
            kl = {meth: (cible[m] * np.log(np.clip(cible[m], PLANCHER, 1) / _borne(retirer_marge(cotes[m], meth)))).sum(axis=1)
                  for meth in METHODES}
            i, r = cotes[m].argmin(axis=1), np.arange(int(m.sum()))
            ligne = [b, fam, nom, f"{int(m.sum())} / {len(set(grappes[m]))}", nb(1e4 * float(kl["puissance"].mean()), 2)]
            for meth in ("multiplicative", "additive", "shin", "odds_ratio"):
                ligne.append(ecart_ic(intervalle(kl[meth] - kl["puissance"], rng, tirages, grappes[m])))
            ligne.append(" · ".join(f"{100 * float(np.mean(retirer_marge(cotes[m], meth)[r, i] - cible[m][r, i])):+.2f}".replace(".", ",")
                                    for meth in METHODES))
            lignes.append(ligne)
    print(tableau(["Bourse", "Type", "Marchés", "Marchés / matchs", "Puissance"]
                  + [f"{NOMS[m]} − puissance" for m in ("multiplicative", "additive", "shin", "odds_ratio")]
                  + ["Favori : " + " · ".join(NOMS[m].split(" ")[0] for m in METHODES)], lignes) + "\n")


def rapport_paris_marge(paris: list[dict], tirages: int, rng: np.random.Generator) -> None:
    """Paris réglés dont Pinnacle est la référence, marchés à deux issues : la cote de l'autre issue se déduit de la
    cote lue et de la marge enregistrée (1/c2 = 1 + marge − 1/c1), ou de la cote juste quand la marge manque.
    Échantillon sélectionné par la méthode actuelle."""
    from cotes.evenements import identites
    match = identites(paris)
    lots: dict[str, list] = defaultdict(list)
    for p in paris:
        fam = famille(str(p.get("marche") or ""))
        c, mg, juste = p.get("cote_reference"), p.get("marge_pinnacle"), p.get("cote_juste")
        if (p.get("reference") != "Pinnacle" or p.get("statut") not in ("gagne", "perdu") or fam in (None, "1N2")
                or not isinstance(c, (int, float)) or c <= 1):
            continue
        if isinstance(mg, (int, float)):
            q2 = 1 + mg - 1 / c
        elif isinstance(juste, (int, float)) and juste > c:
            # avant le 25/10 la marge n'est pas enregistrée : p1 = q1^k (puissance) donne k, puis q2 = (1 − p1)^(1/k)
            q2 = (1 - 1 / juste) ** (math.log(1 / c) / math.log(1 / juste))
        else:
            continue
        if not 0 < q2 < 1 or not 0 < 1 / c + q2 - 1 <= 0.2:
            continue
        lots[fam].append((c, 1 / q2, p["statut"] == "gagne", p["cote"], match.get(id(p), p["match_id"])))
    print("## Données du site : paris réglés de référence Pinnacle, marchés à deux issues (échantillon sélectionné)\n")
    print("Log-loss de l'issue jouée ; « gardés » : paris dont l'écart reste ≥ 2 % avec la méthode ; ROI à mise fixe.\n")
    for fam in ("Deux issues", "Totaux", "Handicaps", "Tous"):
        lot = [x for f in lots.values() for x in f] if fam == "Tous" else lots.get(fam) or []
        if len(lot) < 30:
            continue
        cotes = np.array([[x[0], x[1]] for x in lot])
        gagne = np.array([x[2] for x in lot])
        cote_fr = np.array([x[3] for x in lot])
        grappes = np.array([str(x[4]) for x in lot])
        gain = np.where(gagne, cote_fr - 1, -1.0)
        ll = {m: -np.log(np.clip(np.where(gagne, retirer_marge(cotes, m)[:, 0], 1 - retirer_marge(cotes, m)[:, 0]),
                                 PLANCHER, 1)) for m in METHODES}
        lignes = []
        for m in METHODES:
            p = retirer_marge(cotes, m)[:, 0]
            garde = cote_fr * p - 1 >= 0.02
            roi_g = intervalle(gain[garde], rng, tirages, grappes[garde]) if garde.sum() >= 20 else None
            roi_e = intervalle(gain[~garde], rng, tirages, grappes[~garde]) if (~garde).sum() >= 20 else None
            lignes.append([NOMS[m], nb(float(ll[m].mean()), 5),
                           ecart_ic(intervalle(ll[m] - ll["puissance"], rng, tirages, grappes)) if m != "puissance" else "référence",
                           f"{100 * float(p.mean()):.2f} %".replace(".", ","), str(int(garde.sum())),
                           ecart_ic(roi_g, 100, 1) if roi_g else "—", str(int((~garde).sum())),
                           ecart_ic(roi_e, 100, 1) if roi_e else "—"])
        print(f"### {fam} : {len(lot)} paris, {len(set(grappes))} matchs, {100 * float(gagne.mean()):.2f} % gagnés\n".replace(".", ","))
        print(tableau(["Méthode", "Log-loss", "Écart avec la puissance ×10⁴, IC 95 %", "Probabilité annoncée moyenne",
                       "Gardés", "ROI des gardés en %, IC 95 %", "Écartés", "ROI des écartés en %, IC 95 %"], lignes) + "\n")


# ---------------------------------------------------------------- consensus

SOURCES = ("Pinnacle", "Polymarket", "Matchbook", "Smarkets")
AVANCES_H = (1, 3, 6, 12)
VIE_MAX_S = 2 * 3600          # Pinnacle doit avoir écrit une ligne du match dans les 2 h avant le début
COUPURE = "2026-11-13T12:00:00+00:00"     # ajustement : matchs commencés avant ; test : après
GEL = "2026-11-14T00:20:00+00:00"         # dernière donnée lue quand la méthode a été arrêtée : après, jamais vu


def associer_references(hist: dict, desc: dict) -> dict[str, dict]:
    """{autre référence: {match Pinnacle: (match de la référence, équipes inversées, ressemblance)}}, avec la règle
    d'association du site (cotes/correspondance.py)."""
    from cotes import correspondance as C

    def matchs(b: str) -> dict:
        lignes = [{"match_id": m, "sport": d.get("sport"), "domicile": d["dom"], "exterieur": d["ext"],
                   "debut": d["debut"], "ligue": d.get("ligue"), "source": b.lower()}
                  for (bb, m), d in desc.items()
                  if bb == b and d.get("dom") and d.get("ext") and d.get("debut") and (bb, m) in hist]
        return C.matchs_de(lignes)
    pinnacle = matchs("Pinnacle")
    return {b: C.associer(pinnacle, matchs(b)) for b in SOURCES[1:]}


def _series(series: dict, inverse: bool) -> dict[tuple, list]:
    from cotes.marches import inverser
    out = {}
    for k, serie in series.items():
        l = decouper(k)
        if l["marche"].startswith("JOUEUR:") or l["marche"] == "DOUBLE_CHANCE":     # dérivée du 1N2
            continue
        if inverse:
            l = inverser(l)
        out[(l["marche"], l["periode"], None if l["ligne"] is None else round(l["ligne"], 2), l["issue"])] = serie
    return out


def instantanes(hist: dict, desc: dict, fin: float) -> dict[str, np.ndarray]:
    """Une ligne par (match Pinnacle commencé, pari, avance) où Pinnacle et au moins une autre référence cotent.

    Colonnes par source (NaN si absente) : p, ea (écart achat/vente), liq, age (secondes depuis le dernier
    changement du prix), clo (dernier prix avant le début), fiable (règle du site, comparaison._fiable).
    Pinnacle : mg (marge), lim (mise maximale)."""
    from cotes import comparaison
    assoc = associer_references(hist, desc)
    par_pinnacle: dict[str, dict] = defaultdict(dict)
    for b, a in assoc.items():
        for mp, (mr, inverse, _) in a.items():
            par_pinnacle[mp][b] = (mr, inverse)
    lignes = []
    for mp, autres in par_pinnacle.items():
        debut = instant(desc[("Pinnacle", mp)].get("debut"))
        if debut is None or debut > fin:
            continue
        series = {"Pinnacle": _series(hist[("Pinnacle", mp)], False)}
        for b, (mr, inverse) in autres.items():
            series[b] = _series(hist[(b, mr)], inverse)
        avant = [e[0] for s in series["Pinnacle"].values() for e in s if e[0] <= debut]
        if not avant or debut - max(avant) > VIE_MAX_S:
            continue
        connu = {b: min(s[0][0] for s in sb.values()) for b, sb in series.items() if sb}
        for k, serie_p in series["Pinnacle"].items():
            presents = [b for b in autres if k in series[b]]
            cloture = {b: etat(series[b][k], debut) for b in ["Pinnacle"] + presents}
            if not presents or cloture["Pinnacle"] is None:
                continue
            for av in AVANCES_H:
                t = debut - av * 3600
                x = {"match": mp, "pari": "|".join("" if v is None else str(v) for v in k), "debut": debut, "av": av,
                     "sport": desc[("Pinnacle", mp)].get("sport"), "marche": k[0]}
                for b in ["Pinnacle"] + presents:
                    e = etat(series[b][k], t) if t >= connu[b] + 600 else None
                    if e is None:
                        continue
                    ligne = {"proba_juste": e[2], "marge_pinnacle": e[3], "liquidite": e[4], "ecart_achat_vente": e[5],
                             "cote_perimee": bool(e[7])}
                    x[b] = {"p": e[2], "ea": e[5], "liq": e[4], "age": t - e[0], "mg": e[3], "lim": e[6],
                            "clo": cloture[b][2] if cloture[b] else None, "fiable": comparaison._fiable(b, ligne)}
                if "Pinnacle" in x and len([b for b in presents if b in x]) >= 1:
                    lignes.append(x)
    n = len(lignes)
    t: dict[str, np.ndarray] = {c: np.array([x[c] for x in lignes]) for c in ("match", "pari", "sport", "marche")}
    t["debut"] = np.array([x["debut"] for x in lignes], dtype=float)
    t["av"] = np.array([x["av"] for x in lignes], dtype=float)
    for c in ("p", "ea", "liq", "age", "clo", "mg", "lim"):
        a = np.full((n, len(SOURCES)), np.nan)
        for i, x in enumerate(lignes):
            for j, b in enumerate(SOURCES):
                v = (x.get(b) or {}).get(c)
                if v is not None:
                    a[i, j] = v
        t[c] = a
    t["fiable"] = np.array([[bool((x.get(b) or {}).get("fiable")) for b in SOURCES] for x in lignes], dtype=bool)
    return t


def melange(p: np.ndarray, poids: np.ndarray) -> np.ndarray:
    """Consensus : moyenne des probabilités pondérée, sur les sources de poids > 0."""
    w = np.where(np.isnan(p), 0.0, poids)
    return (w * np.nan_to_num(p)).sum(axis=1) / w.sum(axis=1)


def variables(t: dict[str, np.ndarray]) -> np.ndarray:
    """Variables des poids, (lignes, sources, variables) : constante de la source, écart achat/vente en points,
    liquidité (log10, centrée sur 1 000), âge du prix (log des heures), marge Pinnacle en points au-delà de 5,
    limite Pinnacle (log10, centrée sur 500)."""
    n, s = t["p"].shape
    x = np.zeros((n, s, 6))
    x[:, :, 0] = 1.0
    x[:, 1:, 1] = np.nan_to_num(t["ea"][:, 1:]) / 0.01
    x[:, 1:, 2] = np.log10(np.clip(np.nan_to_num(t["liq"][:, 1:], nan=1.0), 1.0, None) / 1000.0)
    x[:, :, 3] = np.log1p(np.nan_to_num(t["age"]) / 3600.0)
    x[:, 0, 4] = (np.nan_to_num(t["mg"][:, 0], nan=0.05) - 0.05) / 0.01
    x[:, 0, 5] = np.log10(np.clip(np.nan_to_num(t["lim"][:, 0], nan=500.0), 1.0, None) / 500.0)
    return x


def masque_parametres(mode: str) -> np.ndarray:
    """Paramètres libres, (sources, variables). « fixes » : un poids par source ; « complets » : en plus, écart
    achat/vente, liquidité et âge du prix (mêmes coefficients pour toutes les bourses), et pour Pinnacle l'âge
    du prix, la marge et la limite (son poids de base reste 1)."""
    libre = np.zeros((len(SOURCES), 6), dtype=bool)
    libre[1:, 0] = True
    if mode == "complets":
        libre[1:, 1:4] = True
        libre[0, 3:6] = True
    return libre


def poids_de(theta: np.ndarray, x: np.ndarray, actif: np.ndarray) -> np.ndarray:
    return np.where(actif, np.exp(np.clip((x * theta[None, :, :]).sum(axis=2), -8, 8)), 0.0)


def ajuster(t: dict[str, np.ndarray], lignes: np.ndarray, actif: np.ndarray, cible: np.ndarray, mode: str,
            tours: int = 3000, pas: float = 0.03) -> np.ndarray:
    """Paramètres des poids qui minimisent l'erreur quadratique du consensus contre la cible (descente Adam)."""
    x = variables(t)[lignes]
    p = np.nan_to_num(t["p"][lignes])
    a = actif[lignes]
    c = cible[lignes]
    libre = masque_parametres(mode)
    theta = np.zeros(libre.shape)
    m1, m2 = np.zeros_like(theta), np.zeros_like(theta)
    for i in range(1, tours + 1):
        w = poids_de(theta, x, a)
        total = w.sum(axis=1, keepdims=True)
        estime = (w * p).sum(axis=1, keepdims=True) / total
        # d estime / d log w_s = w_s (p_s − estime) / total
        d = 2 * (estime - c[:, None]) * w * (p - estime) / total
        grad = (d[:, :, None] * x).mean(axis=0) * libre
        if mode == "complets":       # un seul coefficient d'écart, de liquidité et d'âge pour les bourses
            grad[1:, 1:4] = grad[1:, 1:4].sum(axis=0, keepdims=True)
        m1 = 0.9 * m1 + 0.1 * grad
        m2 = 0.999 * m2 + 0.001 * grad * grad
        theta -= pas * (m1 / (1 - 0.9 ** i)) / (np.sqrt(m2 / (1 - 0.999 ** i)) + 1e-12)
    return theta


def divergence(cible: np.ndarray, p: np.ndarray) -> np.ndarray:
    """Divergence de Kullback-Leibler de la cible vers la prévision (le log-loss, quand la cible est une probabilité)."""
    c = np.clip(cible, 1e-4, 1 - 1e-4)
    q = np.clip(p, 1e-4, 1 - 1e-4)
    return c * np.log(c / q) + (1 - c) * np.log((1 - c) / (1 - q))


def _rmse(e: np.ndarray) -> str:
    return f"{100 * math.sqrt(float(np.mean(e ** 2))):.2f}".replace(".", ",") if len(e) else "—"


def _ecart_carre(est: np.ndarray, base: np.ndarray, cible: np.ndarray, lignes: np.ndarray, matchs: np.ndarray,
                 rng: np.random.Generator, tirages: int) -> str:
    """Écart d'erreur quadratique (×10⁴) entre deux estimations, avec intervalle par match. Négatif : est meilleur."""
    ok = lignes & ~np.isnan(cible) & ~np.isnan(est) & ~np.isnan(base)
    if ok.sum() < 150:
        return "—"
    return ecart_ic(intervalle((est[ok] - cible[ok]) ** 2 - (base[ok] - cible[ok]) ** 2, rng, tirages, matchs[ok]))


def poids_optimal(a: np.ndarray, b: np.ndarray, cible: np.ndarray, lignes: np.ndarray, matchs: np.ndarray,
                  rng: np.random.Generator, tirages: int) -> tuple[float, float, float]:
    """Poids de b dans a + w (b − a) qui minimise l'erreur quadratique contre la cible, intervalle par match."""
    da, x = (a - cible)[lignes], (b - a)[lignes]
    _, inv = np.unique(matchs[lignes], return_inverse=True)
    num, den = np.bincount(inv, weights=-(da * x)), np.bincount(inv, weights=x * x)
    i = rng.integers(0, len(num), size=(tirages, len(num)))
    w = num[i].sum(axis=1) / den[i].sum(axis=1)
    return float(num.sum() / den.sum()), float(np.quantile(w, 0.025)), float(np.quantile(w, 0.975))


TRANCHES = {
    "Écart achat/vente (points)": ("ea", 100.0, (0, 2, 3, 5, 8, 12)),
    "Liquidité": ("liq", 1.0, (0, 100, 1000, 3000, 10000, 1e12)),
    "Âge du prix (heures)": ("age", 1 / 3600.0, (0, 0.1, 0.5, 2, 6, 48)),
}


def rapport_consensus(donnees: Path, tirages: int, rng: np.random.Generator) -> None:
    hist, desc = charger_references(donnees)
    fin = max(s[-1][0] for (b, _), series in hist.items() if b == "Pinnacle" for s in series.values())
    t = instantanes(hist, desc, fin)
    matchs, p, clo = t["match"], t["p"], t["clo"]
    ok = ~np.isnan(p) & t["fiable"]
    ajustement = t["debut"] < instant(COUPURE)
    jamais_vu = t["debut"] > instant(GEL)
    parts = (("Tout", np.ones(len(matchs), dtype=bool)), ("Ajustement", ajustement), ("Test", ~ajustement),
             ("Test, après le gel", jamais_vu))
    jour = lambda x: datetime.fromtimestamp(x, timezone.utc).strftime("%d/%m %H:%M")  # noqa: E731
    print(f"## Consensus : {len(set(matchs))} matchs commencés du {jour(t['debut'].min())} au {jour(t['debut'].max())} UTC, "
          f"{len(matchs)} lignes (pari × avance de {', '.join(str(a) for a in AVANCES_H)} h)\n")
    print(f"Ajustement : matchs commencés avant le {COUPURE[:16].replace('T', ' ')} UTC ({len(set(matchs[ajustement]))}) ; "
          f"test : après ({len(set(matchs[~ajustement]))}), dont {len(set(matchs[jamais_vu]))} commencés après le gel de la "
          f"méthode ({GEL[:16].replace('T', ' ')} UTC). Erreurs en points de probabilité (racine de l'erreur "
          "quadratique moyenne) ; écarts d'erreur quadratique ×10⁴, intervalle à 95 % par match, négatif = mieux.\n")

    print("### Chaque source et la moyenne simple à deux, lignes fiables selon la règle du site\n")
    lignes = []
    for j in (1, 2, 3):
        for nom, part in parts:
            m = ok[:, 0] & ok[:, j] & part & ~np.isnan(clo[:, 0]) & ~np.isnan(clo[:, j])
            if m.sum() < 150:
                continue
            moyenne, neutre = (p[:, 0] + p[:, j]) / 2, (clo[:, 0] + clo[:, j]) / 2
            lignes.append([SOURCES[j], nom, f"{int(m.sum())} / {len(set(matchs[m]))}",
                           _rmse((p[:, 0] - clo[:, 0])[m]), _rmse((p[:, j] - clo[:, 0])[m]), _rmse((moyenne - clo[:, 0])[m]),
                           _ecart_carre(moyenne, p[:, 0], clo[:, 0], m, matchs, rng, tirages),
                           _ecart_carre(moyenne, p[:, 0], neutre, m, matchs, rng, tirages)])
    print(tableau(["Source", "Période", "Lignes / matchs", "Pinnacle → clôture Pinnacle", "Source → clôture Pinnacle",
                   "Moyenne → clôture Pinnacle", "Moyenne − Pinnacle, cible clôture Pinnacle",
                   "Moyenne − Pinnacle, cible moyenne des deux clôtures"], lignes) + "\n")

    print("### Fraîcheur, liquidité, écart achat/vente : la moyenne simple contre Pinnacle seul, par tranche\n")
    print("Les autres conditions de la règle du site sont respectées ; seule la variable étudiée sort de la règle.\n")
    minimum = {"Polymarket": 100.0, "Matchbook": 0.0}
    lignes = []
    for j in (1, 2):
        ea, liq = t["ea"][:, j], np.nan_to_num(t["liq"][:, j])
        relatif = ea / np.minimum(p[:, j], 1 - p[:, j])
        regle = {"ea": (ea >= 0) & (ea <= 0.05) & (relatif <= 0.25), "liq": liq >= minimum[SOURCES[j]]}
        present = ok[:, 0] & ~np.isnan(p[:, j]) & ~np.isnan(clo[:, 0]) & ~np.isnan(clo[:, j])
        moyenne, neutre = (p[:, 0] + p[:, j]) / 2, (clo[:, 0] + clo[:, j]) / 2
        for titre, (col, facteur, bornes) in TRANCHES.items():
            v = np.nan_to_num(t[col][:, j]) * facteur
            base = present & (ok[:, j] if col == "age" else regle["liq"] & (relatif <= 0.25) if col == "ea" else regle["ea"])
            for a, b in zip(bornes[:-1], bornes[1:]):
                m = base & (v >= a) & (v < b)
                if m.sum() < 150:
                    continue
                lignes.append([SOURCES[j], titre, f"{a:g} à {b:g}".replace("1e+12", "∞").replace(".", ","),
                               f"{int(m.sum())} / {len(set(matchs[m]))}",
                               _rmse((p[:, 0] - clo[:, 0])[m]), _rmse((p[:, j] - clo[:, 0])[m]),
                               _ecart_carre(moyenne, p[:, 0], clo[:, 0], m, matchs, rng, tirages),
                               _ecart_carre(moyenne, p[:, 0], neutre, m, matchs, rng, tirages)])
    print(tableau(["Source", "Variable", "Tranche", "Lignes / matchs", "Pinnacle → clôture Pinnacle", "Source → clôture Pinnacle",
                   "Moyenne − Pinnacle, cible clôture Pinnacle", "Moyenne − Pinnacle, cible moyenne des deux clôtures"],
                  lignes) + "\n")

    print("### Poids d'une source face à une autre, jugé par la clôture d'une troisième\n")
    lignes = []
    for a, b, c in ((1, 2, 0), (0, 1, 2), (0, 2, 1), (0, 1, 3), (0, 2, 3), (0, 3, 2)):
        for nom, part in parts:
            m = ok[:, a] & ok[:, b] & part & ~np.isnan(clo[:, c])
            if m.sum() < 300:
                continue
            w = poids_optimal(p[:, a], p[:, b], clo[:, c], m, matchs, rng, tirages)
            lignes.append([f"{SOURCES[a]} + {SOURCES[b]}", SOURCES[c], nom, f"{int(m.sum())} / {len(set(matchs[m]))}",
                           _rmse((p[:, a] - clo[:, c])[m]), _rmse((p[:, b] - clo[:, c])[m]),
                           f"{w[0]:.2f} [{w[1]:.2f} ; {w[2]:.2f}]".replace(".", ",")])
    print(tableau(["Mélange", "Clôture cible", "Période", "Lignes / matchs", "Erreur de la 1re", "Erreur de la 2e",
                   "Poids optimal de la 2e, IC 95 %"], lignes) + "\n")

    print("### Pondérations ajustées puis testées (Pinnacle, Polymarket, Matchbook)\n")
    actif = ok.copy()
    actif[:, 3] = False
    lot = actif[:, 0] & (actif[:, 1] | actif[:, 2]) & ~np.isnan(clo[:, 0])
    clo_actif = np.where(actif, clo, np.nan)
    neutre = np.where(np.isnan(clo_actif) & actif, np.nan, np.nansum(clo_actif, axis=1, keepdims=True) / actif.sum(axis=1, keepdims=True))[:, 0]
    neutre = np.where((np.isnan(clo) & actif).any(axis=1), np.nan, neutre)
    x = variables(t)
    actuel_actif = actif.copy()
    actuel_actif[:, 2] = False
    estimations = {"Pinnacle seul": p[:, 0],
                   "Actuel : moyenne simple Pinnacle + Polymarket": melange(p, actuel_actif.astype(float)),
                   "Moyenne simple avec Matchbook": melange(p, actif.astype(float))}
    for mode, titre in (("fixes", "Poids fixes par source, ajustés"), ("complets", "Poids selon fraîcheur, liquidité et écart, ajustés")):
        theta = ajuster(t, lot & ajustement, actif, clo[:, 0], mode)
        estimations[titre] = melange(p, poids_de(theta, x, actif))
        if mode == "fixes":
            print("Poids fixes ajustés sur la clôture Pinnacle : Pinnacle 1, "
                  + ", ".join(f"{SOURCES[j]} {math.exp(theta[j, 0]):.2f}".replace(".", ",") for j in (1, 2)) + ".\n")
        else:
            c = theta
            print("Poids complets ajustés : poids d'une bourse = "
                  f"base (Polymarket {math.exp(c[1, 0]):.2f}, Matchbook {math.exp(c[2, 0]):.2f}) × exp({c[1, 1]:+.2f} × écart en points "
                  f"{c[1, 2]:+.2f} × log10(liquidité / 1 000) {c[1, 3]:+.2f} × ln(1 + âge en heures)) ; poids de Pinnacle = "
                  f"exp({c[0, 3]:+.2f} × ln(1 + âge en heures) {c[0, 4]:+.2f} × (marge − 5 points) "
                  f"{c[0, 5]:+.2f} × log10(limite / 500)).\n".replace(".", ",").replace(",\n", ".\n"))
    base = estimations["Actuel : moyenne simple Pinnacle + Polymarket"]
    lignes = []
    for nom, part in parts[1:]:
        m = lot & part
        if m.sum() < 150:
            continue
        for titre, est in estimations.items():
            lignes.append([nom, titre, f"{int(m.sum())} / {len(set(matchs[m]))}", _rmse((est - clo[:, 0])[m]),
                           "référence" if est is base else _ecart_carre(est, base, clo[:, 0], m, matchs, rng, tirages),
                           _rmse((est - neutre)[m & ~np.isnan(neutre)]),
                           "référence" if est is base else _ecart_carre(est, base, neutre, m, matchs, rng, tirages)])
    print(tableau(["Période", "Pondération", "Lignes / matchs", "Erreur, clôture Pinnacle", "Écart avec l'actuel, clôture Pinnacle",
                   "Erreur, moyenne des clôtures", "Écart avec l'actuel, moyenne des clôtures"], lignes) + "\n")
    rapport_paris_consensus(charger_paris(donnees), tirages, rng)


def rapport_paris_consensus(paris: list[dict], tirages: int, rng: np.random.Generator) -> None:
    """Résultats réels : paris réglés dont on connaît à la fois la probabilité de Pinnacle et celle de Polymarket à la
    détection (champs ecart_pinnacle, ecart_polymarket avant le prix prudent du 8/11, composantes du Consensus)."""
    from cotes.evenements import identites
    match = identites(paris)
    selections: dict[tuple, dict] = {}
    for q in sorted(paris, key=lambda q: q.get("detecte") or ""):
        if q.get("statut") not in ("gagne", "perdu") or not q.get("cote"):
            continue
        cle = (q["bookmaker"], q["match_id"], q["marche"], q["periode"], q.get("ligne"), q["issue"])
        d = selections.setdefault(cle, {"gagne": q["statut"] == "gagne", "cote": q["cote"],
                                        "match": str(match.get(id(q), q["match_id"])), "p": {}, "tables": set()})
        d["tables"].add(q["reference"])
        juste = q.get("cote_juste")
        if q["reference"] == "Consensus":
            composantes = q.get("composantes") or (q.get("preuve_prise") or {}).get("composantes") or {}
            for nom, c in composantes.items():
                if isinstance(c, (int, float)) and c > 1:
                    d["p"].setdefault(nom, 1 / c)
        elif isinstance(juste, (int, float)) and juste > 1 and not q.get("prix_prudent"):
            d["p"].setdefault(q["reference"], 1 / juste)
        if isinstance(q.get("ecart_pinnacle"), (int, float)):
            d["p"].setdefault("Pinnacle", (1 + q["ecart_pinnacle"]) / q["cote"])
        if isinstance(q.get("ecart_polymarket"), (int, float)) and (q.get("detecte") or "") < "2026-11-08":
            d["p"].setdefault("Polymarket", (1 + q["ecart_polymarket"]) / q["cote"])

    def perte(pr: np.ndarray, y: np.ndarray) -> np.ndarray:
        pr = np.clip(pr, PLANCHER, 1 - PLANCHER)
        return -np.where(y, np.log(pr), np.log(1 - pr))

    def table(d: dict) -> str:
        s = d["tables"] & {"Pinnacle", "Polymarket"}
        return "les deux" if len(s) == 2 else f"{next(iter(s))} seul" if s else "Consensus seul"
    print("### Résultats réels : paris réglés où Pinnacle et une autre source cotent le même pari (échantillon sélectionné)\n")
    lignes = []
    for autre in ("Polymarket", "Matchbook"):
        lot = [d for d in selections.values() if "Pinnacle" in d["p"] and autre in d["p"]]
        cas = ("tous", "Pinnacle seul", "Polymarket seul", "les deux") if autre == "Polymarket" else ("tous",)
        for nom in cas:
            sous = [d for d in lot if nom == "tous" or table(d) == nom]
            if len(sous) < 40:
                continue
            pa = np.array([d["p"]["Pinnacle"] for d in sous])
            pb = np.array([d["p"][autre] for d in sous])
            y = np.array([d["gagne"] for d in sous])
            g = np.array([d["match"] for d in sous])
            la, lb, lm = perte(pa, y), perte(pb, y), perte((pa + pb) / 2, y)
            lignes.append([autre, nom, f"{len(sous)} / {len(set(g))}", f"{100 * y.mean():.1f} %".replace(".", ","),
                           f"{100 * pa.mean():.1f} %".replace(".", ","), f"{100 * pb.mean():.1f} %".replace(".", ","),
                           nb(float(la.mean())), nb(float(lb.mean())), nb(float(lm.mean())),
                           ecart_ic(intervalle(lb - la, rng, tirages, g), 1e4, 0),
                           ecart_ic(intervalle(lm - la, rng, tirages, g), 1e4, 0)])
    print(tableau(["Autre source", "Pari présent dans la table de", "Paris / matchs", "Gagnés", "Probabilité Pinnacle",
                   "Probabilité de l'autre", "Log-loss Pinnacle", "Log-loss de l'autre", "Log-loss de la moyenne",
                   "Autre − Pinnacle ×10⁴, IC 95 %", "Moyenne − Pinnacle ×10⁴, IC 95 %"], lignes) + "\n")


# ---------------------------------------------------------------- affichage

def pct(x: float, d: int = 2) -> str:
    return f"{100 * x:+.{d}f} %".replace(".", ",")


def nb(x: float, d: int = 4) -> str:
    return f"{x:.{d}f}".replace(".", ",")


def ecart_ic(t: tuple[float, float, float], facteur: float = 1e4, d: int = 2) -> str:
    m, a, b = (facteur * v for v in t)
    gras = "**" if (a > 0 or b < 0) else ""
    return f"{gras}{m:+.{d}f} [{a:+.{d}f} ; {b:+.{d}f}]{gras}".replace(".", ",")


def tableau(entetes: list[str], lignes: list[list[str]]) -> str:
    return "\n".join(["| " + " | ".join(entetes) + " |", "|" + "---|" * len(entetes)]
                     + ["| " + " | ".join(l) + " |" for l in lignes])


def lignes_methodes(r: dict) -> list[list[str]]:
    out = []
    for m in METHODES:
        x = r["methodes"][m]
        out.append([NOMS[m], nb(x["log_loss"], 5), nb(x["brier"], 5),
                    ecart_ic(x["ecart_log_loss"]) if "ecart_log_loss" in x else "référence",
                    f"{nb(x['pente'], 3)} ± {nb(1.96 * x['pente_et'], 3)}", str(x["negatives"])])
    return out


ENTETES_METHODES = ["Méthode", "Log-loss", "Brier", "Écart de log-loss avec la puissance ×10⁴, IC 95 %",
                    "Pente de calibration ± IC", "Marchés à probabilité ≤ 0"]


def rapport_football(dossier: Path, tirages: int, rng: np.random.Generator) -> None:
    donnees = lire_football(dossier)
    print("## Football : cotes et résultats de football-data.co.uk\n")
    for cle in MARCHES_FOOT:
        v = donnees.get(cle)
        if v is None or len(v["cotes"]) < 500:
            continue
        r = mesurer_marche(v["cotes"], v["gagnant"], rng, tirages)
        saisons = sorted(set(v["saison"]))
        print(f"### {cle[0]} · {cle[1]} · {cle[2]} : {r['marches']} matchs, saisons {saisons[0]} à {saisons[-1]}, "
              f"marge moyenne {pct(r['marge']).lstrip('+')}\n")
        print(tableau(ENTETES_METHODES, lignes_methodes(r)) + "\n")
        if cle[0] == "Pinnacle" and (cle[1] == "1N2" or cle[2] == "clôture"):
            print("Courbe de calibration (toutes issues) : probabilité annoncée moyenne → fréquence observée, en %.\n")
            courbes = {m: r["methodes"][m]["courbe"] for m in METHODES}
            lignes = []
            for i, (a, b, n, _, obs) in enumerate(courbes["puissance"]):
                et = math.sqrt(max(obs * (1 - obs), 1e-9) / n)
                lignes.append([f"{100 * a:.0f} à {100 * min(b, 1):.0f} %", str(n), f"{100 * obs:.2f} ± {196 * et:.2f}".replace(".", ",")]
                              + [f"{100 * courbes[m][i][3]:.2f}".replace(".", ",") if i < len(courbes[m]) else "—"
                                 for m in METHODES])
            print(tableau(["Tranche (puissance)", "Issues", "Observée ± IC"] + [NOMS[m] for m in METHODES], lignes) + "\n")
        # marchés déséquilibrés : là où les méthodes diffèrent le plus
        favori = retirer_marge(v["cotes"], "multiplicative").max(axis=1)
        seuil = 0.75 if cle[1] == "1N2" else 0.65
        m = favori >= seuil
        if m.sum() >= 500:
            rs = mesurer_marche(v["cotes"][m], v["gagnant"][m], rng, tirages)
            print(f"Favori à {100 * seuil:.0f} % ou plus ({rs['marches']} matchs) :\n")
            print(tableau(ENTETES_METHODES, lignes_methodes(rs)) + "\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("commande", choices=("marge", "consensus"))
    ap.add_argument("--football", type=Path)
    ap.add_argument("--donnees", type=Path)
    ap.add_argument("--tirages", type=int, default=2000)
    args = ap.parse_args(argv)
    rng = np.random.default_rng(GRAINE)
    if args.commande == "marge":
        if args.football:
            rapport_football(args.football, args.tirages, rng)
        if args.donnees:
            rapport_marge_interne(args.donnees, args.tirages, rng)
    else:
        if not args.donnees:
            ap.error("--donnees est obligatoire pour « consensus »")
        rapport_consensus(args.donnees, args.tirages, rng)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
