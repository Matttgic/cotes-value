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

import math
import re
import statistics
import unicodedata

from .marches import cle
from .pulsescore import PERIODE_VERIFIEE

MESURES_MIN = 8
MEDIANE_MIN, MEDIANE_MAX = 0.70, 1.02
# marchés à beaucoup d'issues : les bookmakers français y prennent 25 à 40 % de marge
MEDIANE_MIN_PAR_MARCHE = {"CORRECT_SCORE": 0.55, "HALF_TIME_FULL_TIME": 0.55}
HAUT, PART_HAUTE_MAX = 1.12, 0.10
GARDER = 300                       # mesures conservées par groupe (les plus récentes)
# par match : seules des cotes françaises systématiquement AU-DESSUS du juste trahissent une mauvaise
# association (des cotes basses = simplement un match à forte marge, ex. grand favori)
MATCH_MESURES_MIN, MATCH_MEDIANE_MIN, MATCH_MEDIANE_MAX = 6, 0.50, 1.04
ORDRE_REFERENCES = ("Pinnacle", "Betfair", "Polymarket", "Kalshi")
# Temps réglementaire et prolongation incluse donnent des cotes proches : le rapport médian ne suffit pas à
# les distinguer. On compare donc aussi chaque cote à l'autre version de Pinnacle : une cote française suit
# de plus près (dispersion plus faible) la version qu'elle cote vraiment.
AUTRE_PERIODE = {"MATCH": "TEMPS_REG", "TEMPS_REG": "MATCH"}
DISPERSION_RATIO_MAX = 0.8          # autre version nettement plus proche -> période douteuse


def _sans_accents(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()


# mots des noms d'équipes trop courants pour être remplacés dans un intitulé (« Les Herbiers » -> « les »)
PETITS_MOTS = {"de", "du", "la", "le", "les", "des", "et", "of", "the", "fc", "sc", "ac", "cf", "cd", "ca", "sk", "fk",
               "bk", "if", "ik", "un", "en", "au", "by", "to", "set", "but", "buts", "points", "total", "match"}


def type_intitule(libelle: str | None, domicile: str | None, exterieur: str | None) -> str:
    """« Plus / Moins Tirs cadrés - Italie [2,5] » -> « plus / moins tirs cadres - {eq} [#] » ; les noms
    écrits autrement que dans le match (« D. Snigur » pour « Daria Snigur ») sont aussi remplacés."""
    s = _sans_accents(libelle or "")
    noms = {_sans_accents(domicile or ""), _sans_accents(exterieur or "")}
    for nom in sorted(noms, key=len, reverse=True):
        if len(nom) >= 2:
            s = s.replace(nom, "{eq}")
    mots = {m for nom in noms for m in re.findall(r"[a-z0-9]+", nom) if len(m) >= 2 and m not in PETITS_MOTS}
    for m in sorted(mots, key=len, reverse=True):
        s = re.sub(rf"\b{re.escape(m)}\b", "{eq}", s)
    s = re.sub(r"\b[a-z]\.\s*(?:(?:de|van|von|da|di|del|le|la|du)\s+)*(?=\{eq\})", "", s)   # « a. de {eq} »
    s = re.sub(r"\{eq\}(?:[\s-]*\{eq\})+", "{eq}", s)
    s = re.sub(r"[-+]?\d+(?:[.,]\d+)?", "#", s)
    return re.sub(r"\s+", " ", s).strip()


def cle_groupe(l: dict) -> str:
    return "|".join(str(x) for x in (l["bookmaker"], l["sport"], l["marche"], l["periode"],
                                     type_intitule(l.get("libelle"), l.get("domicile"), l.get("exterieur"))))


def mesurer(francais: list[dict], index: dict[str, dict]) -> list[tuple]:
    """(ligne française, référence, cote juste, rapport cote / cote juste, rapport avec l'autre version
    temps réglementaire / prolongation de Pinnacle ou None) pour chaque cote française qui a une cote juste
    en face (Pinnacle de préférence)."""
    out = []
    for l in francais:
        if l["periode"].endswith("?") or not l.get("cote"):
            continue
        k = cle(l)
        for nom in ORDRE_REFERENCES:
            r = index.get(nom, {}).get(l["match_id"], {}).get(k)
            if r and r.get("proba_juste"):
                alt = None
                if nom == "Pinnacle" and l["periode"] in AUTRE_PERIODE:
                    ra = index[nom][l["match_id"]].get((k[0], AUTRE_PERIODE[l["periode"]], *k[2:]))
                    if ra and ra.get("proba_juste"):
                        alt = l["cote"] * ra["proba_juste"]
                out.append((l, nom, 1 / r["proba_juste"], l["cote"] * r["proba_juste"], alt))
                break
    return out


def _dispersion(rapports: list[float]) -> float:
    """Écart absolu médian du logarithme des rapports (robuste aux quelques vraies erreurs de cote)."""
    logs = [math.log(r) for r in rapports if r > 0]
    m = statistics.median(logs)
    return statistics.median(abs(x - m) for x in logs)


def statut(rapports: list[float], marche: str = "", paires_alt: list[tuple[float, float]] | None = None) -> str:
    """paires_alt : (rapport, rapport avec l'autre version de la période) pour les cotes qui ont les deux ;
    None quand la période a été vérifiée à la main (pas de test de période)."""
    if len(rapports) < MESURES_MIN:
        return "a_verifier"
    med = statistics.median(rapports)
    haute = sum(r > HAUT for r in rapports) / len(rapports)
    if not (MEDIANE_MIN_PAR_MARCHE.get(marche, MEDIANE_MIN) <= med <= MEDIANE_MAX) or haute > PART_HAUTE_MAX:
        return "non_conforme"
    if paires_alt and len(paires_alt) >= MESURES_MIN:
        d, d_alt = _dispersion([a for a, _ in paires_alt]), _dispersion([b for _, b in paires_alt])
        if d > 0 and d_alt < DISPERSION_RATIO_MAX * d:
            return "non_conforme"           # la cote suit mieux l'autre version : période douteuse
    return "conforme"


def mettre_a_jour(etat: dict, mesures: list[tuple[dict, str, float, float]], moment: str) -> dict:
    """Ajoute les mesures du cycle à l'état cumulé et recalcule le statut de chaque groupe."""
    groupes = etat.setdefault("groupes", {})
    for l, nom, juste, rapport, *alt in mesures:
        g = groupes.setdefault(cle_groupe(l), {
            "bookmaker": l["bookmaker"], "sport": l["sport"], "marche": l["marche"], "periode": l["periode"],
            "type": type_intitule(l.get("libelle"), l.get("domicile"), l.get("exterieur")),
            "n": 0, "rapports": [], "exemples": []})
        g["n"] += 1
        g["rapports"].append(round(rapport, 4))
        if alt and alt[0]:
            g.setdefault("paires_alt", []).append([round(rapport, 4), round(alt[0], 4)])
        g["maj"] = moment
        if len(g["exemples"]) < 3 and not any(x["libelle"] == l.get("libelle") for x in g["exemples"]):
            g["exemples"].append({"libelle": l.get("libelle"), "match": f'{l["domicile"]} – {l["exterieur"]}',
                                  "ligne": l.get("ligne"), "issue": l["issue"], "cote": l["cote"],
                                  "reference": nom, "cote_juste": round(juste, 3)})
    for g in groupes.values():
        g["rapports"] = g["rapports"][-GARDER:]
        if "paires_alt" in g:
            g["paires_alt"] = g["paires_alt"][-GARDER:]
        verifiee = PERIODE_VERIFIEE.get((g["bookmaker"], g["sport"]), {}).get(g["marche"]) == g["periode"]
        g["periode_verifiee"] = verifiee
        g["statut"] = statut(g["rapports"], g["marche"], None if verifiee else g.get("paires_alt"))
        if len(g.get("paires_alt") or []) >= MESURES_MIN:
            g["dispersion"] = round(_dispersion([a for a, _ in g["paires_alt"]]), 4)
            g["dispersion_autre_periode"] = round(_dispersion([b for _, b in g["paires_alt"]]), 4)
        g["mediane"] = round(statistics.median(g["rapports"]), 4) if g["rapports"] else None
        g["part_haute"] = round(sum(r > HAUT for r in g["rapports"]) / len(g["rapports"]), 3) if g["rapports"] else None
    return etat


# marchés où domicile et extérieur ne jouent pas le même rôle : une inversion des équipes s'y voit
MARCHES_ORIENTES = {"RESULTAT_1N2", "VAINQUEUR", "DRAW_NO_BET", "HANDICAP", "HANDICAP_3", "TOTAL_DOM", "TOTAL_EXT",
                    "DOUBLE_CHANCE", "JEUX_HANDICAP", "SETS_HANDICAP", "JEUX_TOTAL_DOM", "JEUX_TOTAL_EXT"}


def matchs_suspects(mesures: list[tuple]) -> dict[str, float]:
    """Matchs (identifiant français) dont les cotes s'écartent de la référence : mauvaise association
    probable. Contrôlé sur tous les marchés, puis sur les seuls marchés orientés (équipes inversées : les
    totaux, symétriques, masqueraient l'erreur). -> {match_id: rapport médian}."""
    tous: dict[str, list[float]] = {}
    orientes: dict[str, list[float]] = {}
    for l, _, _, rapport, *_ in mesures:
        tous.setdefault(l["match_id"], []).append(rapport)
        if l["marche"] in MARCHES_ORIENTES:
            orientes.setdefault(l["match_id"], []).append(rapport)
    out = {}
    for groupe in (tous, orientes):
        for mid, rs in groupe.items():
            if len(rs) >= MATCH_MESURES_MIN and mid not in out:
                med = statistics.median(rs)
                haute = sum(r > HAUT for r in rs) / len(rs)
                if not (MATCH_MEDIANE_MIN <= med <= MATCH_MEDIANE_MAX) or haute > 0.25:
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
