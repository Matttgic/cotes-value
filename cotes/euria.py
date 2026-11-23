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

L'espérance d'un milieu est la somme de celles de ses deux paris. Quand Pinnacle n'a pas l'une des deux lignes, sa
probabilité est estimée (``estime``) : Poisson pour les totaux de buts (football, hockey) à partir de la ligne connue
la plus proche, loi normale ajustée sur au moins deux lignes connues ailleurs. Mises « équilibrées » (même retour hors du milieu),
100 € au total. Gardés : les deux cotes justes connues, une probabilité de milieu positive, une espérance positive ;
tous, même plusieurs par match (paires de lignes différentes), classés par espérance.

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
from statistics import NormalDist, median

from . import surebets as SB

TOTAL = 100.0
MILIEUX_MAX = 300                 # tous les milieux en value, du meilleur au moins bon (limite : poids de la page)
CONVERSIONS_PAR_BOOK = 8
VALEUR_REMBOURSEMENT = 0.75
SEUIL_ALERTE_MILIEU = 0.02
GARDER_JOURS = 60
EPISODES_MAX = 2000
REGLES_PUBLIES = 60
# euria-stats.json : tous les milieux réglés, une ligne par milieu (onglet Stats de la page Euria, filtres et
# découpages faits dans le navigateur). Colonnes dans l'ordre de STATS_COLONNES.
STATS_COLONNES = ("debut", "match", "sport", "ligue", "marche", "periode", "largeur", "reference", "bookmakers", "cotes",
                  "esperance", "p_milieu", "estime", "milieu_100", "hors_100", "avance_h", "duree_min",
                  "esperance_derniere", "resultat_100", "tombe")
# Chance estimée quand Pinnacle n'a pas l'une des deux lignes : loi de Poisson ajustée sur la ligne connue la plus
# proche (totaux de buts du football et du hockey), sinon loi normale ajustée sur au moins deux lignes connues du
# match. Une ligne estimée doit rester proche des lignes connues, et sa cote proche de sa cote estimée.
POISSON = {("football", "TOTAL"), ("hockey", "TOTAL"), ("football", "TOTAL_DOM"), ("football", "TOTAL_EXT"),
           ("hockey", "TOTAL_DOM"), ("hockey", "TOTAL_EXT")}
ECART_POISSON_MAX = 2.0           # buts entre la ligne estimée et la ligne connue
ECART_NORMALE_MAX = 1.0           # en écarts-types, hors de l'intervalle des lignes connues
UNITES = {"football": "buts", "hockey": "buts", "handball": "buts", "basket": "points", "football_americain": "points",
          "rugby": "points", "volley": "points", "badminton": "points", "tennis_de_table": "points"}


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

def _poisson_queue(lam: float, x: float) -> float:
    """P(X > x), X de Poisson de moyenne lam, x demi-entier."""
    k_max = math.floor(x)
    terme, cumul = math.exp(-lam), 0.0
    for k in range(k_max + 1):
        if k:
            terme *= lam / k
        cumul += terme
    return max(0.0, 1.0 - cumul)


def _lambda(x: float, p: float) -> float | None:
    """Moyenne de Poisson telle que P(X > x) = p (dichotomie)."""
    if not 0 < p < 1:
        return None
    bas, haut = 1e-6, 200.0
    for _ in range(80):
        mil = (bas + haut) / 2
        if _poisson_queue(mil, x) < p:
            bas = mil
        else:
            haut = mil
    return (bas + haut) / 2


def _survie(sport: str | None, marche: str, connus: dict[float, float]):
    """S(x) = P(X > x) estimée à partir des points connus {x: P(X > x)} de Pinnacle, et la règle d'éloignement ;
    None si on ne peut pas estimer."""
    if not connus:
        return None
    if (sport, marche) in POISSON:
        def s_poisson(x):
            x0 = min(connus, key=lambda c: (abs(c - x), c))
            if abs(x0 - x) > ECART_POISSON_MAX:
                return None
            lam = _lambda(x0, connus[x0])
            return _poisson_queue(lam, x) if lam else None
        return s_poisson
    if len(connus) < 2 or sport in ("football", "hockey"):
        return None                       # écart de buts : trop peu de valeurs pour une loi normale
    N = NormalDist()
    pts = [(x, N.inv_cdf(1 - p)) for x, p in connus.items() if 0 < p < 1]
    if len(pts) < 2:
        return None
    zm = sum(z for _, z in pts) / len(pts)
    xm = sum(x for x, _ in pts) / len(pts)
    vz = sum((z - zm) ** 2 for _, z in pts)
    if vz <= 0:
        return None
    sigma = sum((x - xm) * (z - zm) for x, z in pts) / vz          # x = mu + sigma × z
    if not sigma > 0:
        return None
    mu = xm - sigma * zm
    lo, hi = min(connus), max(connus)

    def s_normale(x):
        if x < lo - ECART_NORMALE_MAX * sigma or x > hi + ECART_NORMALE_MAX * sigma:
            return None
        return 1 - N.cdf((x - mu) / sigma)
    return s_normale


def _connus(lignes: dict, marche: str) -> dict[float, float]:
    """Points connus de la survie S(x) = P(X > x) : X = total (Plus à L gagne si X > L) ou écart domicile −
    extérieur (domicile à h gagne si X > −h)."""
    haut_i, bas_i = SB.DEMI_LIGNE[marche]
    out: dict[float, float] = {}
    for ligne, issues in lignes.items():
        x = -ligne if marche.endswith("HANDICAP") else ligne
        for issue, gagne_haut in ((haut_i, True), (bas_i, False)):
            p = next((j["proba_juste"] for j in issues.get(issue) or [] if j.get("proba_juste")), None)
            if p:
                out.setdefault(x, p if gagne_haut else 1 - p)
    return out


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
        match = matchs.get((nom, mid)) or {}
        connus = _connus(lignes, marche)
        survie = _survie(match.get("sport"), marche, connus)
        for l1, l2 in product(lignes, lignes):
            bas, haut = bornes(marche, l1, l2)
            if not bas < haut:
                continue
            a = SB._meilleures(lignes[l1].get(haut_i) or [])
            b = SB._meilleures(lignes[l2].get(bas_i) or [])
            if not a or not b:
                continue
            a, b = a[0], b[0]
            # P(Plus de l1) = S(bas), P(Moins de l2) = 1 − S(haut) ; Pinnacle d'abord, sinon estimée
            p1 = connus.get(bas)
            p2 = None if haut not in connus else 1 - connus[haut]
            estime = []
            if p1 is None and survie:
                s = survie(bas)
                p1 = s if s is not None and 0 < s < 1 else None
                estime.append(0)
            if p2 is None and survie:
                s = survie(haut)
                p2 = 1 - s if s is not None and 0 < s < 1 else None
                estime.append(1)
            if not p1 or not p2:
                continue
            c1, c2 = a["cote"], b["cote"]
            if any(not (SB.ECART_JUSTE_BAS <= c * p - 1 <= SB.ECART_JAMBE_MAX)
                   for i, (c, p) in enumerate(((c1, p1), (c2, p2))) if i in estime):
                continue                                 # cote loin de sa cote estimée : mal lue ou modèle faux
            p_milieu = p1 + p2 - 1
            if p_milieu <= 0:
                continue                                 # cotes justes incohérentes entre les deux lignes
            m1 = total * c2 / (c1 + c2)
            m2 = total - m1
            esperance = m1 * (c1 * p1 - 1) + m2 * (c2 * p2 - 1)
            if esperance <= 0:
                continue
            cle_m = "|".join(str(x) for x in (nom, mid, marche, periode, l1, l2))
            jambes = []
            for i, (j, ligne, p) in enumerate(((a, l1, p1), (b, l2, p2))):
                j = {**j, "ligne": ligne}
                if i in estime:
                    j.update(proba_juste=round(p, 5), cote_juste=round(1 / p, 3), ecart=round(j["cote"] * p - 1, 4),
                             estimee=True)
                jambes.append(j)
            meilleurs[cle_m] = {
                "id": hashlib.sha1(cle_m.encode()).hexdigest()[:16], "cle": cle_m,
                "detecte": maintenant.isoformat(timespec="seconds"), **match,
                "match": f'{match.get("domicile")} – {match.get("exterieur")}', "reference": nom, "marche": marche,
                "periode": periode, "ecart": marche.endswith("HANDICAP"), "unite": unite(marche, match.get("sport")),
                "bornes": [bas, haut], "de": math.ceil(bas), "a": math.floor(haut),
                "jambes": jambes, "estime": bool(estime),
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
                **{k: m.get(k) for k in ("sport", "ligue", "match", "debut", "marche", "periode", "de", "a", "unite",
                                         "reference")},
                "esperance_initiale": m["esperance_100"], "p_milieu_initiale": m["p_milieu"], "estime": bool(m.get("estime")),
                "bookmakers": sorted({j["bookmaker"] for j in m["jambes"]}),
                "cotes": [j["cote"] for j in m["jambes"]], "lignes": [j["ligne"] for j in m["jambes"]],
                # pour le règlement (bilan) : équipes dans le sens de la référence, issues, mises et résultats prévus
                "domicile": m.get("domicile"), "exterieur": m.get("exterieur"),
                "issues": [j["issue"] for j in m["jambes"]], "mises_100": m["mises_100"],
                "milieu_100": m["milieu_100"], "hors_100": m["hors_100"]}
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


# --------------------------------------------------------------------------- règlement des milieux (bilan)

def a_regler(episodes: list[dict], maintenant: datetime) -> list[dict]:
    """Milieux commencés et pas encore réglés, au format d'un pari (cotes/reglement.py, cotes/resultats.py) pour
    retrouver le score du match. Les épisodes d'avant l'ajout des issues et des équipes ne sont pas réglables."""
    out = []
    for e in episodes:
        debut = _t(e.get("debut"))
        if "resultat_100" in e or not e.get("issues") or not e.get("domicile") or not e.get("exterieur") \
                or debut is None or debut > maintenant:
            continue
        out.append({"id": e["id"], "match_id": f"euria|{e['id']}", "sport": e.get("sport"), "ligue": e.get("ligue"),
                    "domicile": e["domicile"], "exterieur": e["exterieur"], "debut": e["debut"],
                    "marche": e.get("marche"), "periode": e.get("periode"), "statut": "en_cours"})
    return out


def bilan_regle(episodes: list[dict], maintenant: datetime, jours: int | None = None) -> dict:
    """Milieux réglés (matchs des ``jours`` derniers jours, ou tous) : ce qu'ils auraient rapporté pour 100 € par
    milieu, comparé à ce qu'ils promettaient (espérance) ; nombre de milieux tombés contre le nombre attendu."""
    es = [e for e in episodes if "resultat_100" in e
          and (jours is None or maintenant - (_t(e.get("debut")) or maintenant) <= timedelta(days=jours))]
    n = len(es)
    out = {"jours": jours, "n": n,
           "en_attente": sum(1 for e in episodes if "resultat_100" not in e and e.get("issues")
                             and (_t(e.get("debut")) or maintenant) <= maintenant)}
    if not n:
        return out
    return {**out, "resultat": round(sum(e["resultat_100"] for e in es), 2),
            "esperance": round(sum(e["esperance_initiale"] for e in es), 2),
            "tombes": sum(1 for e in es if e.get("tombe")),
            "tombes_attendus": round(sum(e["p_milieu_initiale"] for e in es), 2)}


def _heures(a: str | None, b: str | None, par: float) -> float | None:
    ta, tb = _t(a), _t(b)
    return None if ta is None or tb is None else round((tb - ta).total_seconds() / par, 1)


def stats(episodes: list[dict]) -> dict:
    """Fichier ``euria-stats.json`` : chaque milieu réglé, du plus récent au plus ancien, pour l'onglet Stats de la page
    Euria (résultat par sport, type de pari, largeur du milieu, espérance, chance, bookmaker…). ``largeur`` : nombre de
    résultats entiers dans le milieu ; ``avance_h`` : heures entre le premier relevé et le début du match ;
    ``duree_min`` : minutes pendant lesquelles le milieu est resté affiché ; ``milieu_100`` et ``hors_100`` donnent la
    variance de chaque milieu (écart à l'espérance en écarts-types)."""
    lignes = []
    for e in sorted((e for e in episodes if isinstance(e, dict) and "resultat_100" in e),
                    key=lambda e: e.get("debut") or "", reverse=True):
        de, a = e.get("de"), e.get("a")
        x = {**e, "esperance": e.get("esperance_initiale"), "p_milieu": e.get("p_milieu_initiale"),
             "largeur": a - de + 1 if isinstance(de, (int, float)) and isinstance(a, (int, float)) else None,
             "avance_h": _heures(e.get("premier"), e.get("debut"), 3600),
             "duree_min": _heures(e.get("premier"), e.get("dernier"), 60), "tombe": bool(e.get("tombe"))}
        lignes.append([x.get(k) for k in STATS_COLONNES])
    return {"colonnes": list(STATS_COLONNES), "lignes": lignes}


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
            "bilan_regle": {str(j or "tout"): bilan_regle(episodes, maintenant, j) for j in (7, 30, None)},
            "regles": [{k: e.get(k) for k in ("id", "sport", "ligue", "match", "domicile", "exterieur", "debut",
                                                "marche", "periode", "de", "a", "unite", "bookmakers", "esperance_initiale", "p_milieu_initiale", "estime",
                                                "resultat_100", "tombe", "score")}
                       for e in sorted((e for e in episodes if "resultat_100" in e),
                                       key=lambda e: e.get("debut") or "", reverse=True)[:REGLES_PUBLIES]],
            "autres": {"surebets": len(sb), "boosts_couverts": len(bc)}}
