"""Paris simulés : 10 € misés à la première détection d'une erreur de cote, par simulation et par référence.

Simulations (écart = cote française × probabilité juste − 1) :
    A ≥ 2 %, B ≥ 3 %, C ≥ 4 %, D ≥ 5 %, E ≥ 7 %   (cotes jusqu'à 10)
    X « cotes > 10 » ≥ 3 %                          (à part : cote juste imprécise, gros aléa)
Chaque simulation est jouée séparément pour chaque référence (Pinnacle, Betfair, Polymarket, Kalshi,
Consensus) : on voit ainsi quel seuil et quelle référence gagnent vraiment.
Un pari n'est pris qu'une fois par simulation, référence, bookmaker et sélection, à la cote vue
au moment où l'écart atteint le seuil de la simulation.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from .marches import cle

MISE = 10.0
SIMULATIONS = {
    "A": {"ecart": 0.02, "cote_max": 10.0, "cote_min": 1.0, "nom": "≥ 2 %"},
    "B": {"ecart": 0.03, "cote_max": 10.0, "cote_min": 1.0, "nom": "≥ 3 %"},
    "C": {"ecart": 0.04, "cote_max": 10.0, "cote_min": 1.0, "nom": "≥ 4 %"},
    "D": {"ecart": 0.05, "cote_max": 10.0, "cote_min": 1.0, "nom": "≥ 5 %"},
    "E": {"ecart": 0.07, "cote_max": 10.0, "cote_min": 1.0, "nom": "≥ 7 %"},
    "X": {"ecart": 0.03, "cote_max": 1e9, "cote_min": 10.0001, "nom": "Cotes > 10 (≥ 3 %)"},
}
REFERENCES = ["Pinnacle", "Betfair", "Polymarket", "Kalshi", "Consensus", "Pinnacle brut"]


def _id(*parts) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:16]


def placer(opportunites: list[dict], paris: list[dict]) -> list[dict]:
    """Ajoute les nouveaux paris (modifie `paris`) et renvoie ceux qui viennent d'être pris."""
    deja = {p["id"] for p in paris}
    nouveaux = []
    # à écart égal, la meilleure cote d'abord ; un même pari peut être vu chez plusieurs bookmakers :
    # chaque bookmaker est un pari distinct (on sait ainsi lequel se trompe le plus souvent)
    for o in sorted(opportunites, key=lambda o: -o["ecart"]):
        if o.get("suspect"):
            continue
        for code, s in SIMULATIONS.items():
            if o["ecart"] < s["ecart"] or not (s["cote_min"] <= o["cote"] <= s["cote_max"]):
                continue
            pid = _id(code, o["reference"], o["match_id"], *cle(o))
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


def suivre_cloture(paris: list[dict], justes: dict[tuple, dict[str, float]], maintenant: datetime | None = None):
    """Met à jour la cote juste « de clôture » des paris dont le match n'a pas commencé (pour la CLV)."""
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
        proba = justes.get((p["match_id"], cle(p)), {}).get(p["reference"])
        if proba:
            p["cote_juste_cloture"] = round(1 / proba, 4)
            p["clv"] = round(p["cote"] * proba - 1, 4)
            p["cloture_lue"] = maintenant.isoformat(timespec="seconds")


def bilan(paris: list[dict]) -> dict:
    """Résumé par simulation et par référence : nombre, mises, gains, ROI, CLV moyenne."""
    out: dict[str, dict] = {}
    for p in paris:
        # « Toutes » = les vraies références ; le témoin « Pinnacle brut » n'a que sa propre ligne
        clefs = [f'{p["simulation"]}|{p["reference"]}']
        if p["reference"] != "Pinnacle brut":
            clefs.append(f'{p["simulation"]}|Toutes')
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
            if p.get("clv") is not None:
                b["clv_somme"] += p["clv"]
                b["clv_n"] += 1
    for b in out.values():
        b["roi"] = round(b["gains"] / b["mises"], 4) if b["mises"] else None
        b["clv_moyenne"] = round(b["clv_somme"] / b["clv_n"], 4) if b["clv_n"] else None
        b["gains"] = round(b["gains"], 2)
    return out
