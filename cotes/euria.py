"""Opportunités automatiques de la page Euria (dépôt Euria, GitHub Pages) : milieux et conversions de freebets.

Calculées à chaque cycle avec les cotes françaises du cycle et les garde-fous des surebets (cotes/surebets.py ›
``candidates`` : cote lue depuis moins de 10 min, match pas commencé, cote proche de sa cote juste, intitulé contrôlé,
match relié à sa rencontre de référence). Écrit ``donnees/euria.json`` ; le site en publie la partie à venir dans
``euria.json`` (même origine que la page Euria, https://matttgic.github.io), que la page lit.

Milieux. « Plus de L1 » chez un bookmaker et « Moins de L2 » chez un autre, L1 < L2 (demi-lignes) ; handicaps :
domicile à h1 et extérieur à h2, h1 > h2 (écart domicile − extérieur entre −h1 et −h2). Les deux paris gagnent si le
résultat tombe entre les deux lignes. Avec les probabilités justes de la référence à chaque ligne, p1 = P(Plus de L1)
et p2 = P(Moins de L2) :

    P(milieu) = p1 + p2 − 1
    espérance = m1 × (c1 × p1 − 1) + m2 × (c2 × p2 − 1)

L'espérance d'un milieu est la somme de celles de ses deux paris. Mises « équilibrées » (même retour hors du milieu),
100 € au total. Gardés : les deux cotes justes connues, une probabilité de milieu positive, une espérance positive ;
le meilleur par match, marché et période.

Conversions de freebets. Pour chaque bookmaker B et chaque issue d'un marché complet (1N2, vainqueur, les deux
équipes marquent, handicaps et totaux à demi-ligne ; 1N2 aussi contre la double chance des deux autres issues), le
freebet joué chez B, les autres issues couvertes aux meilleures cotes françaises du cycle (S = Σ 1/cote de couverture) :

    freebet (mise non rendue) : gain garanti / freebet = (cote − 1) × (1 − S)
    pari remboursé si perdant : gain garanti / mise = cote − 1 − (cote − 0,75) × S   (remboursement compté 75 %)

Les ``CONVERSIONS_PAR_BOOK`` meilleures de chaque calcul, un pari par match, sont publiées ; la page refait les mises
pour le montant saisi. Un marché dont les cotes feraient un surebet suspect (règles de cotes/surebets.py) ou dont les
probabilités justes ne font pas 1 est écarté (``marche_credible``).
"""
from __future__ import annotations

import hashlib
import math
from datetime import datetime, timedelta
from itertools import product
from statistics import median

from . import surebets as SB

TOTAL = 100.0
MILIEUX_MAX = 40
CONVERSIONS_PAR_BOOK = 8
VALEUR_REMBOURSEMENT = 0.75
SEUIL_ALERTE_MILIEU = 0.02
GARDER_JOURS = 21
EPISODES_MAX = 2000
UNITES = {"football": "buts", "hockey": "buts", "handball": "buts", "basket": "points", "football_americain": "points",
          "rugby": "points", "volley": "points"}


def _t(s) -> datetime | None:
    return SB._t(s)


def unite(marche: str, sport: str | None) -> str:
    if marche.startswith("JEUX_"):
        return "jeux"
    if marche.startswith("SETS_"):
        return "sets"
    return UNITES.get(sport or "", "")


def bornes(marche: str, ligne_haute: float, ligne_basse: float) -> tuple[float, float]:
    """(bas, haut) du résultat X pour lequel les deux paris gagnent : X = total, ou écart domicile − extérieur pour
    un handicap (domicile à h gagne si X > −h, extérieur à h si X < −h)."""
    if marche.endswith("HANDICAP"):
        return -ligne_haute, -ligne_basse
    return ligne_haute, ligne_basse


# --------------------------------------------------------------------------- milieux

def milieux(familles: dict, matchs: dict, maintenant: datetime, total: float = TOTAL) -> list[dict]:
    """Milieux en value du cycle, de la meilleure espérance à la moins bonne (``familles`` et ``matchs`` :
    ``surebets.candidates``)."""
    groupes: dict[tuple, dict] = {}
    for (nom, mid, marche, periode, ligne), issues in familles.items():
        if marche in SB.DEMI_LIGNE and SB.demi_ligne(ligne):
            groupes.setdefault((nom, mid, marche, periode), {})[ligne] = issues
    meilleurs: dict[tuple, dict] = {}
    for (nom, mid, marche, periode), lignes in groupes.items():
        haut_i, bas_i = SB.DEMI_LIGNE[marche]          # issue qui gagne quand X est haut (Plus, domicile), bas
        for l1, l2 in product(lignes, lignes):
            bas, haut = bornes(marche, l1, l2)
            if not bas < haut:
                continue
            a = SB._meilleures(lignes[l1].get(haut_i) or [])
            b = SB._meilleures(lignes[l2].get(bas_i) or [])
            if not a or not b or not a[0].get("proba_juste") or not b[0].get("proba_juste"):
                continue
            a, b = a[0], b[0]
            p1, p2 = a["proba_juste"], b["proba_juste"]
            p_milieu = p1 + p2 - 1
            if p_milieu <= 0:
                continue                                 # cotes justes incohérentes entre les deux lignes
            c1, c2 = a["cote"], b["cote"]
            m1 = total * c2 / (c1 + c2)
            m2 = total - m1
            esperance = m1 * (c1 * p1 - 1) + m2 * (c2 * p2 - 1)
            if esperance <= 0:
                continue
            k = (nom, mid, marche, periode)
            if k in meilleurs and meilleurs[k]["esperance_100"] >= esperance:
                continue
            match = matchs.get((nom, mid)) or {}
            cle_m = "|".join(str(x) for x in (nom, mid, marche, periode, l1, l2))
            meilleurs[k] = {
                "id": hashlib.sha1(cle_m.encode()).hexdigest()[:16], "cle": cle_m,
                "detecte": maintenant.isoformat(timespec="seconds"), **match,
                "match": f'{match.get("domicile")} – {match.get("exterieur")}', "reference": nom, "marche": marche,
                "periode": periode, "ecart": marche.endswith("HANDICAP"), "unite": unite(marche, match.get("sport")),
                "bornes": [bas, haut], "de": math.ceil(bas), "a": math.floor(haut),
                "jambes": [{**a, "ligne": l1}, {**b, "ligne": l2}],
                "p_milieu": round(p_milieu, 4), "p_dessous": round(1 - p1, 4), "p_dessus": round(1 - p2, 4),
                "mises_100": [round(m1, 2), round(m2, 2)], "milieu_100": round(m1 * c1 + m2 * c2 - total, 2),
                "hors_100": round(m1 * c1 - total, 2), "esperance_100": round(esperance, 2)}
    out = sorted(meilleurs.values(), key=lambda x: -x["esperance_100"])
    return out[:MILIEUX_MAX]


# --------------------------------------------------------------------------- conversions de freebets

def _par_bookmaker(jambes: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for j in jambes:
        a = out.get(j["bookmaker"])
        if a is None or (j["cote"], j["lu"] or "") > (a["cote"], a["lu"] or ""):
            out[j["bookmaker"]] = j
    return out


def _couvertures(familles: dict, fam: tuple, issue: str, attendues: tuple) -> list[list[dict]]:
    """Façons de couvrir les autres issues aux meilleures cotes : une jambe par issue restante ; pour le 1N2, aussi la
    double chance des deux autres issues."""
    issues = familles[fam]
    out = []
    autres = [SB._meilleures(issues.get(i) or []) for i in attendues if i != issue]
    if all(autres):
        out.append([x[0] for x in autres])
    if fam[2] == "RESULTAT_1N2":
        dc = {"DOM": "DRAW_AWAY", "EXT": "HOME_DRAW", "NUL": "HOME_AWAY"}[issue]
        jambes_dc = SB._meilleures((familles.get((fam[0], fam[1], "DOUBLE_CHANCE", fam[3], None)) or {}).get(dc) or [])
        if jambes_dc:
            out.append([jambes_dc[0]])
    return out


def marche_credible(jambes: list[dict]) -> bool:
    """Mêmes règles que les surebets : un marché dont les cotes feraient un gros surebet est presque toujours mal lu
    (relevé du 16/11/2026 : « Grèce U21 – Islande U21 » chez Unibet, « U21 » pris pour un handicap de +21, cotes
    20 / 17 / 6,7) ; quand toutes les jambes ont une cote juste, leurs probabilités doivent faire 1."""
    if SB.suspicion(jambes, SB.rendement([j["cote"] for j in jambes])):
        return False
    return not SB.verifie(jambes) or abs(sum(j["proba_juste"] for j in jambes) - 1) <= SB.TOLERANCE_PARTITION


def conversions(familles: dict, matchs: dict, maintenant: datetime, par_book: int = CONVERSIONS_PAR_BOOK,
                valeur: float = VALEUR_REMBOURSEMENT) -> dict[str, list[dict]]:
    """Bookmaker -> meilleurs paris pour convertir un freebet ou un pari remboursé si perdant chez lui."""
    tous: dict[str, list[dict]] = {}
    for fam, issues in familles.items():
        nom, mid, marche, periode, ligne = fam
        attendues = SB.TROIS_ISSUES.get(marche) or SB.DEUX_ISSUES.get(marche) or (
            SB.DEMI_LIGNE.get(marche) if SB.demi_ligne(ligne) else None)
        if not attendues or any(i not in issues for i in attendues):
            continue
        match = matchs.get((nom, mid)) or {}
        for issue in attendues:
            options = _couvertures(familles, fam, issue, attendues)
            if not options:
                continue
            for book, jambe in _par_bookmaker(issues[issue]).items():
                valables = [o for o in options if marche_credible([jambe, *o])]
                if not valables:
                    continue
                couverture = min(valables, key=lambda o: sum(1 / j["cote"] for j in o))
                s = sum(1 / j["cote"] for j in couverture)
                c = jambe["cote"]
                tous.setdefault(book, []).append({
                    "bookmaker": book, **{k: match.get(k) for k in ("sport", "ligue", "domicile", "exterieur", "debut")},
                    "match": f'{match.get("domicile")} – {match.get("exterieur")}', "cle_match": f"{nom}|{mid}",
                    "pari": SB.libelle_famille(marche, periode, ligne, match.get("sport")),
                    "jambes": [jambe, *couverture], "somme_couverture": round(s, 5),
                    "conversion": round((c - 1) * (1 - s), 4),
                    "rembourse": round(c - 1 - (c - valeur) * s, 4)})
    out: dict[str, list[dict]] = {}
    for book, liste in tous.items():
        garde: list[dict] = []
        for cle_tri in ("conversion", "rembourse"):
            vus = set()
            for x in sorted(liste, key=lambda x: -x[cle_tri]):
                if x["cle_match"] in vus:
                    continue
                vus.add(x["cle_match"])
                if x not in garde:
                    garde.append(x)
                if len(vus) >= par_book:
                    break
        out[book] = sorted(garde, key=lambda x: -x["conversion"])
    return out


# --------------------------------------------------------------------------- cycle, suivi, publication

def calculer(francais: list[dict], index: dict, maintenant: datetime,
             controle: tuple[dict, dict] | None = None) -> dict:
    familles, matchs, _ = SB.candidates(francais, index, maintenant, controle)
    return {"milieux": milieux(familles, matchs, maintenant), "conversions": conversions(familles, matchs, maintenant)}


def suivre(etat: dict | None, actuels: list[dict], maintenant: datetime) -> list[dict]:
    """Un épisode par milieu (même match, marché, période et lignes) : première et dernière lecture, espérance et
    probabilité du milieu à la première lecture."""
    episodes = {e["cle"]: e for e in ((etat or {}).get("episodes_milieux") or []) if isinstance(e, dict) and e.get("cle")}
    t = maintenant.isoformat(timespec="seconds")
    for m in actuels:
        e = episodes.get(m["cle"])
        if e is None:
            e = episodes[m["cle"]] = {
                "cle": m["cle"], "id": m["id"], "premier": t, "cycles": 0,
                **{k: m.get(k) for k in ("sport", "ligue", "match", "debut", "marche", "periode", "de", "a", "unite")},
                "esperance_initiale": m["esperance_100"], "p_milieu_initiale": m["p_milieu"],
                "bookmakers": sorted({j["bookmaker"] for j in m["jambes"]}),
                "cotes": [j["cote"] for j in m["jambes"]], "lignes": [j["ligne"] for j in m["jambes"]]}
        e["dernier"], e["cycles"] = t, e["cycles"] + 1
        e["esperance_derniere"] = m["esperance_100"]
    limite = maintenant - timedelta(days=GARDER_JOURS)
    garde = sorted((e for e in episodes.values() if (_t(e.get("dernier")) or maintenant) >= limite),
                   key=lambda e: e.get("premier") or "")
    return garde[-EPISODES_MAX:]


def bilan(episodes: list[dict], maintenant: datetime, jours: int = 7) -> dict:
    """Milieux vus sur ``jours`` jours : nombre, espérance totale et médiane pour 100 € par milieu, chance médiane du
    milieu. Une espérance, pas un résultat : les milieux ne sont pas réglés."""
    es = [e for e in episodes if (maintenant - (_t(e.get("premier")) or maintenant)) <= timedelta(days=jours)]
    if not es:
        return {"jours": jours, "n": 0}
    return {"jours": jours, "n": len(es), "esperance": round(sum(e["esperance_initiale"] for e in es), 2),
            "esperance_mediane": round(median(e["esperance_initiale"] for e in es), 2),
            "p_milieu_mediane": round(median(e["p_milieu_initiale"] for e in es), 4)}


def publier(calcul: dict, episodes: list[dict], maintenant: datetime) -> dict:
    """Document ``donnees/euria.json``."""
    return {"maj": maintenant.isoformat(timespec="seconds"), **calcul, "episodes_milieux": episodes}


def _a_venir(x: dict, maintenant: datetime) -> bool:
    debut = _t(x.get("debut"))
    return debut is not None and debut > maintenant


def publie(doc: dict | None, surebets_publies: dict | None, boosts_publies: dict | None, maintenant: datetime) -> dict:
    """Fichier ``euria.json`` du site, lu par la page Euria : milieux et conversions à venir, bilan des milieux, nombre de
    surebets et de boosts couverts du moment (onglet Boosts de Cote Value)."""
    doc = doc if isinstance(doc, dict) else {}
    episodes = [e for e in doc.get("episodes_milieux") or [] if isinstance(e, dict) and e.get("premier")]
    conv = {b: [x for x in liste if isinstance(x, dict) and _a_venir(x, maintenant)]
            for b, liste in (doc.get("conversions") or {}).items() if isinstance(liste, list)}
    sb = [s for s in (surebets_publies or {}).get("actuels") or [] if not s.get("suspect")]
    bc = [c for c in (boosts_publies or {}).get("couverts") or [] if not c.get("suspect")]
    return {"maj": doc.get("maj"), "seuil_alerte_milieu": SEUIL_ALERTE_MILIEU,
            "milieux": [m for m in doc.get("milieux") or [] if isinstance(m, dict) and _a_venir(m, maintenant)],
            "conversions": {b: liste for b, liste in sorted(conv.items()) if liste},
            "bilan_milieux": {str(j): bilan(episodes, maintenant, j) for j in (7, 30)},
            "autres": {"surebets": len(sb), "boosts_couverts": len(bc)}}
