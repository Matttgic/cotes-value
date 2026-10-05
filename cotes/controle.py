"""Contrôle de conformité des marchés : chaque type d'intitulé de chaque bookmaker est mesuré contre la
référence, à chaque cycle, avant de pouvoir donner un pari.

Principe : quand un marché français est bien traduit, sa cote est en général un peu SOUS la cote juste
(marge du bookmaker) : rapport cote française / cote juste ≈ 0,85 à 0,98. Un marché mal traduit (tirs
cadrés pris pour des buts, handicap inversé, mauvaise période, autre match…) donne des rapports
aberrants ou très dispersés. On regroupe les cotes par (bookmaker, sport, marché, période, type
d'intitulé) — le type d'intitulé est l'intitulé sans les noms d'équipes ni les nombres — et on cumule
les mesures d'un cycle à l'autre :

- « conforme » : au moins MESURES_MIN mesures, rapport médian entre MEDIANE_MIN et MEDIANE_MAX, et pas
  plus de PART_HAUTE_MAX des cotes au-dessus de HAUT ;
- « non_conforme » : au moins MESURES_MIN mesures, et une de ces conditions non remplie ;
- « a_verifier » : pas encore assez de mesures.

Seuls les marchés « conformes » peuvent donner un pari simulé. Même contrôle par match (tous marchés
d'un même match) pour repérer une mauvaise association de matchs.
"""
from __future__ import annotations

import re
import statistics
import unicodedata

from .marches import cle

MESURES_MIN = 8
MEDIANE_MIN, MEDIANE_MAX = 0.70, 1.02
HAUT, PART_HAUTE_MAX = 1.12, 0.10
GARDER = 300                       # mesures conservées par groupe (les plus récentes)
MATCH_MESURES_MIN, MATCH_MEDIANE_MIN, MATCH_MEDIANE_MAX = 6, 0.75, 1.04
ORDRE_REFERENCES = ("Pinnacle", "Betfair", "Polymarket", "Kalshi")


def _sans_accents(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()


def type_intitule(libelle: str | None, domicile: str | None, exterieur: str | None) -> str:
    """« Plus / Moins Tirs cadrés - Italie [2,5] » -> « plus / moins tirs cadres - {eq} [#] »."""
    s = _sans_accents(libelle or "")
    for nom in sorted({_sans_accents(domicile or ""), _sans_accents(exterieur or "")}, key=len, reverse=True):
        if len(nom) >= 2:
            s = s.replace(nom, "{eq}")
    s = re.sub(r"[-+]?\d+(?:[.,]\d+)?", "#", s)
    return re.sub(r"\s+", " ", s).strip()


def cle_groupe(l: dict) -> str:
    return "|".join(str(x) for x in (l["bookmaker"], l["sport"], l["marche"], l["periode"],
                                     type_intitule(l.get("libelle"), l.get("domicile"), l.get("exterieur"))))


def mesurer(francais: list[dict], index: dict[str, dict]) -> list[tuple[dict, str, float, float]]:
    """(ligne française, référence, cote juste, rapport cote / cote juste) pour chaque cote française qui
    a une cote juste en face (Pinnacle de préférence)."""
    out = []
    for l in francais:
        if l["periode"].endswith("?") or not l.get("cote"):
            continue
        k = cle(l)
        for nom in ORDRE_REFERENCES:
            r = index.get(nom, {}).get(l["match_id"], {}).get(k)
            if r and r.get("proba_juste"):
                out.append((l, nom, 1 / r["proba_juste"], l["cote"] * r["proba_juste"]))
                break
    return out


def statut(rapports: list[float]) -> str:
    if len(rapports) < MESURES_MIN:
        return "a_verifier"
    med = statistics.median(rapports)
    haute = sum(r > HAUT for r in rapports) / len(rapports)
    if not (MEDIANE_MIN <= med <= MEDIANE_MAX) or haute > PART_HAUTE_MAX:
        return "non_conforme"
    return "conforme"


def mettre_a_jour(etat: dict, mesures: list[tuple[dict, str, float, float]], moment: str) -> dict:
    """Ajoute les mesures du cycle à l'état cumulé et recalcule le statut de chaque groupe."""
    groupes = etat.setdefault("groupes", {})
    for l, nom, juste, rapport in mesures:
        g = groupes.setdefault(cle_groupe(l), {
            "bookmaker": l["bookmaker"], "sport": l["sport"], "marche": l["marche"], "periode": l["periode"],
            "type": type_intitule(l.get("libelle"), l.get("domicile"), l.get("exterieur")),
            "n": 0, "rapports": [], "exemples": []})
        g["n"] += 1
        g["rapports"].append(round(rapport, 4))
        g["maj"] = moment
        if len(g["exemples"]) < 3 and not any(x["libelle"] == l.get("libelle") for x in g["exemples"]):
            g["exemples"].append({"libelle": l.get("libelle"), "match": f'{l["domicile"]} – {l["exterieur"]}',
                                  "ligne": l.get("ligne"), "issue": l["issue"], "cote": l["cote"],
                                  "reference": nom, "cote_juste": round(juste, 3)})
    for g in groupes.values():
        g["rapports"] = g["rapports"][-GARDER:]
        g["statut"] = statut(g["rapports"])
        g["mediane"] = round(statistics.median(g["rapports"]), 4) if g["rapports"] else None
        g["part_haute"] = round(sum(r > HAUT for r in g["rapports"]) / len(g["rapports"]), 3) if g["rapports"] else None
    return etat


def matchs_suspects(mesures: list[tuple[dict, str, float, float]]) -> dict[str, float]:
    """Matchs (identifiant français) dont l'ensemble des cotes s'écarte de la référence : mauvaise
    association probable. -> {match_id: rapport médian}."""
    par_match: dict[str, list[float]] = {}
    for l, _, _, rapport in mesures:
        par_match.setdefault(l["match_id"], []).append(rapport)
    out = {}
    for mid, rs in par_match.items():
        if len(rs) >= MATCH_MESURES_MIN:
            med = statistics.median(rs)
            if not (MATCH_MEDIANE_MIN <= med <= MATCH_MEDIANE_MAX):
                out[mid] = round(med, 3)
    return out


def raison(l: dict, etat: dict, suspects: dict[str, float]) -> str | None:
    """Pourquoi une cote française ne peut pas encore donner de pari (None = elle peut)."""
    if l["match_id"] in suspects:
        return "match mal associé ?"
    g = etat.get("groupes", {}).get(cle_groupe(l))
    if not g or g.get("statut") == "a_verifier":
        return "intitulé à vérifier"
    if g.get("statut") == "non_conforme":
        return "intitulé non conforme"
    return None


def resume(etat: dict) -> dict:
    groupes = etat.get("groupes", {}).values()
    compte = {"conforme": 0, "a_verifier": 0, "non_conforme": 0}
    for g in groupes:
        compte[g.get("statut", "a_verifier")] += 1
    return compte
