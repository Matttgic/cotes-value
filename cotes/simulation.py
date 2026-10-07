"""Paris simulés : 10 € misés à la première détection d'une erreur de cote, par référence.

Simulations = tranches d'écart qui ne se chevauchent pas (écart = cote française × probabilité juste − 1),
à la première détection :
    A 2 à 3 %, B 3 à 4 %, C 4 à 5 %, D 5 à 7 %, E 7 % et plus   (cotes jusqu'à 10)
    X « cotes > 10 », écart ≥ 3 %                               (à part : cote juste imprécise, gros aléa)
Un pari n'est pris qu'une fois par référence, bookmaker et sélection (à la cote vue à la première
détection) et appartient à une seule simulation : « A+B » = les paris de 2 à 4 %, chacun compté une fois.
Chaque référence (Pinnacle, Betfair, Polymarket, Kalshi, Consensus, témoin Pinnacle brut) a ses paris.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from .marches import cle

MISE = 10.0
INF = float("inf")
SIMULATIONS = {     # écart dans [ecart, ecart_max[, cote dans [cote_min, cote_max]
    "A": {"ecart": 0.02, "ecart_max": 0.03, "cote_min": 1.0, "cote_max": 10.0, "nom": "2 à 3 %"},
    "B": {"ecart": 0.03, "ecart_max": 0.04, "cote_min": 1.0, "cote_max": 10.0, "nom": "3 à 4 %"},
    "C": {"ecart": 0.04, "ecart_max": 0.05, "cote_min": 1.0, "cote_max": 10.0, "nom": "4 à 5 %"},
    "D": {"ecart": 0.05, "ecart_max": 0.07, "cote_min": 1.0, "cote_max": 10.0, "nom": "5 à 7 %"},
    "E": {"ecart": 0.07, "ecart_max": INF, "cote_min": 1.0, "cote_max": 10.0, "nom": "7 % et plus"},
    "X": {"ecart": 0.03, "ecart_max": INF, "cote_min": 10.0001, "cote_max": INF, "nom": "cotes > 10, ≥ 3 %"},
}


def simulation_de(ecart: float, cote: float) -> str | None:
    """La simulation (une seule) d'une opportunité, ou None."""
    for code, s in SIMULATIONS.items():
        if s["ecart"] <= ecart < s["ecart_max"] and s["cote_min"] <= cote <= s["cote_max"]:
            return code
    return None
REFERENCES = ["Pinnacle", "Betfair", "Polymarket", "Kalshi", "Consensus", "Pinnacle brut"]


def _id(*parts) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:16]


def placer(opportunites: list[dict], paris: list[dict]) -> list[dict]:
    """Ajoute les nouveaux paris (modifie `paris`) et renvoie ceux qui viennent d'être pris. Un pari par
    référence, bookmaker et sélection, à la première détection, rangé dans la tranche de son écart. Un même
    pari vu chez plusieurs bookmakers = paris distincts (on sait ainsi lequel se trompe le plus souvent)."""
    deja = {p["id"] for p in paris}
    nouveaux = []
    for o in sorted(opportunites, key=lambda o: -o["ecart"]):
        if o.get("suspect"):
            continue
        code = simulation_de(o["ecart"], o["cote"])
        if code is None:
            continue
        pid = _id(o["reference"], o["match_id"], *cle(o))
        if pid in deja:
            continue
        deja.add(pid)
        p = {"id": pid, "simulation": code, "reference": o["reference"], "detecte": o["detecte"],
             "bookmaker": o["bookmaker"], "sport": o["sport"], "ligue": o.get("ligue"),
             "match_id": o["match_id"], "domicile": o["domicile"], "exterieur": o["exterieur"],
             "debut": o["debut"], "marche": o["marche"], "periode": o["periode"], "ligne": o.get("ligne"),
             "issue": o["issue"], "pari": o["pari"], "libelle_bookmaker": o.get("libelle_bookmaker"),
             "cote": o["cote"], "cote_juste": o["cote_juste"], "cote_reference": o.get("cote_reference"),
             "lu_reference": o.get("lu_reference"), "ecart": o["ecart"], "mise": MISE,
             "statut": "en_cours", "gain": None, "cote_juste_cloture": o["cote_juste"], "clv": None,
             "match_reference": o.get("match_reference"), "lien": o.get("lien")}
        paris.append(p)
        nouveaux.append(p)
    return nouveaux


FRAICHEUR_CLOTURE_MIN = 15
TOLERANCE_HORLOGE_S = 60
# CLV « de clôture » : dernière observation à moins de CLOTURE_MAX_MIN minutes du coup d'envoi. Une
# observation plus ancienne (marché retiré tôt, référence absente ensuite) reste affichée sur le pari mais
# n'entre pas dans la CLV moyenne du bilan.
CLOTURE_MAX_MIN = 30


def _heure(s) -> datetime | None:
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def clv_finale(p: dict) -> float | None:
    """CLV du pari si elle est mesurée près du coup d'envoi et que le match est joué (pari réglé), sinon None.
    Pour les paris d'avant le 7/10/2026, `cloture_lue` est l'heure du cycle (à quelques minutes près celle
    de la cote, toutes les références étant relues à chaque cycle)."""
    if p.get("clv") is None or p.get("statut") in ("en_cours", "a_regler"):
        return None
    t, debut = _heure(p.get("cloture_lue")), _heure(p.get("debut"))
    if not t or not debut or t.tzinfo is None or debut.tzinfo is None:
        return None
    return p["clv"] if 0 < (debut - t).total_seconds() <= CLOTURE_MAX_MIN * 60 else None


def suivre_cloture(paris: list[dict], justes: dict[tuple, dict[str, tuple]], maintenant: datetime | None = None):
    """Met à jour la cote juste « de clôture » des paris dont le match n'a pas commencé (pour la CLV).

    Seule une cote de référence lue avant le coup d'envoi et depuis moins de FRAICHEUR_CLOTURE_MIN minutes
    est retenue ; sinon la dernière valeur valide est gardée. `cloture_lue` est l'heure de lecture de la
    référence (et non celle du traitement)."""
    maintenant = maintenant or datetime.now(timezone.utc)
    for p in paris:
        if p["statut"] != "en_cours":
            continue
        try:
            debut = datetime.fromisoformat(p["debut"].replace("Z", "+00:00"))
        except (AttributeError, ValueError):
            continue
        if debut <= maintenant:
            continue
        proba, lue = justes.get((p["match_id"], cle(p)), {}).get(p["reference"]) or (None, None)
        t = _heure(lue)
        if not proba or not t or t.tzinfo is None or t >= debut:
            continue
        age = (maintenant - t).total_seconds()
        if not -TOLERANCE_HORLOGE_S <= age <= FRAICHEUR_CLOTURE_MIN * 60:      # périmée, ou dans le futur
            continue
        avant = _heure(p.get("cloture_lue"))
        if avant and avant.tzinfo and t < avant:        # jamais revenir à une observation plus ancienne
            continue
        p["cote_juste_cloture"] = round(1 / proba, 4)
        p["clv"] = round(p["cote"] * proba - 1, 4)
        p["cloture_lue"] = t.isoformat(timespec="seconds")


TEMOIN = "Pinnacle brut"
# tranches de cote (bornes basses exclues, hautes incluses)
TRANCHES = [(1.0, 1.5, "1,01 – 1,50"), (1.5, 2.0, "1,51 – 2,00"), (2.0, 3.0, "2,01 – 3,00"),
            (3.0, 5.0, "3,01 – 5,00"), (5.0, 10.0, "5,01 – 10"), (10.0, float("inf"), "plus de 10")]


def tranche(cote: float) -> str:
    return next(nom for bas, haut, nom in TRANCHES if bas < cote <= haut)


def _cumuler(paris: list[dict], groupe) -> dict:
    """Résumé par (groupe, référence) et (groupe, « Toutes ») : nombre, mises, gains, ROI, CLV moyenne.
    « Toutes » = les vraies références ; le témoin « Pinnacle brut » n'a que sa propre ligne."""
    out: dict[str, dict] = {}
    for p in paris:
        clefs = [f'{groupe(p)}|{p["reference"]}']
        if p["reference"] != TEMOIN:
            clefs.append(f'{groupe(p)}|Toutes')
        for clef in clefs:
            b = out.setdefault(clef, {"paris": 0, "regles": 0, "en_cours": 0, "mises": 0.0, "gains": 0.0,
                                      "clv_somme": 0.0, "clv_n": 0, "gagnes": 0})
            b["paris"] += 1
            if p["statut"] in ("en_cours", "a_regler"):
                b["en_cours"] += 1
            else:
                b["regles"] += 1
                b["mises"] += p["mise"]
                b["gains"] += p["gain"] or 0
                b["gagnes"] += p["statut"] in ("gagne", "demi_gagne")
            clv = clv_finale(p)
            if clv is not None:
                b["clv_somme"] += clv
                b["clv_n"] += 1
    for b in out.values():
        b["roi"] = round(b["gains"] / b["mises"], 4) if b["mises"] else None
        b["clv_moyenne"] = round(b["clv_somme"] / b["clv_n"], 4) if b["clv_n"] else None
        b["gains"] = round(b["gains"], 2)
    return out


def bilan(paris: list[dict]) -> dict:
    """Par simulation (« A|Pinnacle », « A|Toutes »…)."""
    return _cumuler(paris, lambda p: p["simulation"])


def bilan_tranches(paris: list[dict]) -> dict:
    """Par tranche de cote (« 1,51 – 2,00|Pinnacle »…) ; chaque pari n'appartient qu'à une simulation."""
    return _cumuler(paris, lambda p: tranche(p["cote"]))
