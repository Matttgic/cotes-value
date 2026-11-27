"""Page Décision (web/decision.js) : les chiffres mesurés qui justifient « quoi jouer » et « quoi couper ».

Grille de lecture de docs/avantage-reel.md (« Règles du verdict »), refaite à chaque construction du site sur trois
familles de lignes seulement (décision 5 du document : tester moins de lignes) :

- les paris uniques (une mise par cote française) ;
- chaque bookmaker, sur les paris uniques ;
- chaque référence, sur tous ses paris.

Mesure : CLV contre la clôture Pinnacle sans marge (décision 1), le ROI en garde-fou. Paris des bilans du site : cote
≤ plafond, mise fixe. Le match est l'unité de hasard. Différence avec ``etudes/avantage_reel.py`` : intervalles et
p-valeurs par un test de Student par match (celui du protocole, sans numpy) et non par bootstrap ; à cote ≤ 5 les gains
sont assez peu asymétriques pour cela.

Ce module ne dit jamais « prouvé » : seul le protocole fixé à l'avance le peut (docs/protocole.md, § 8). Ses décisions
sont descriptives, recalculées sur tout l'historique, et ne lisent aucun test du protocole.
"""
from __future__ import annotations

from datetime import datetime
from functools import lru_cache

from .protocole import clv_pinnacle, moyenne_par_match, p_student

MIN_PARIS = 30                 # en dessous : ni test ni correction
MIN_MATCHS = 10
MIN_CLV = 30                   # CLV Pinnacle mesurées minimum pour tester la CLV
PART_PINNACLE_MIN = 0.5        # « jouer » : CLV Pinnacle mesurée sur au moins la moitié des paris réglés
ALPHA = 0.05
JOUER, COUPER, SURVEILLER, ATTENDRE = "jouer", "couper", "surveiller", "attendre"


def holm(pvals: list[float]) -> list[float]:
    """p-valeurs corrigées de Holm : aucune fausse découverte au seuil choisi."""
    m = len(pvals)
    out, courant = [0.0] * m, 0.0
    for rang, i in enumerate(sorted(range(m), key=lambda i: pvals[i])):
        courant = max(courant, min(1.0, (m - rang) * pvals[i]))
        out[i] = courant
    return out


@lru_cache(maxsize=4096)
def quantile_student(ddl: float, niveau: float = 0.975) -> float:
    """t tel que P(T ≤ t) = ``niveau`` (dichotomie sur ``p_student``). Fonction pure, mise en cache : 1 665 appels pour
    401 valeurs distinctes par construction du site (audit du 26/11/2026, docs/audit-26-11-dette.md)."""
    bas, haut = 0.0, 1000.0
    for _ in range(80):
        milieu = (bas + haut) / 2
        if p_student(milieu, ddl) > 1 - niveau:
            bas = milieu
        else:
            haut = milieu
    return (bas + haut) / 2


def mesure(valeurs: list[float], matchs: list) -> dict:
    """Moyenne par pari en %, intervalle à 95 % et p-valeurs unilatérales des deux sens (par match)."""
    m = moyenne_par_match(valeurs, matchs)
    out = {"n": m["n"], "matchs": m["matchs"], "moyenne": 100 * m["moyenne"], "ic": None, "p_pos": None, "p_neg": None}
    if m["p"] is not None:
        marge = quantile_student(m["matchs"] - 1) * m["erreur_type"]
        out.update(ic=[100 * (m["moyenne"] - marge), 100 * (m["moyenne"] + marge)], p_pos=m["p"], p_neg=1 - m["p"])
    return out


def lignes_a_mesurer(paris: list[dict]) -> list[dict]:
    """Les lignes de la page : {id, famille, nom, paris}. Bookmakers et références du plus au moins fourni."""
    from collections import Counter
    from .simulation import REFERENCES, premiers_par_selection
    uniques = premiers_par_selection(paris)
    u = [p for p in paris if id(p) in uniques]
    lignes = [{"id": "ensemble", "famille": "ensemble", "nom": "Paris uniques", "paris": u}]
    for b, _ in Counter(p["bookmaker"] for p in u if p.get("bookmaker")).most_common():
        lignes.append({"id": "bookmaker:" + b, "famille": "bookmaker", "nom": b, "cle": b,
                       "paris": [p for p in u if p.get("bookmaker") == b]})
    for ref in REFERENCES:
        rows = [p for p in paris if p.get("reference") == ref]
        if rows:
            lignes.append({"id": "reference:" + ref, "famille": "reference", "nom": "Référence " + ref, "cle": ref,
                           "paris": rows})
    return lignes


def mesurer(ligne: dict, match_de, clvs: dict[int, float]) -> dict:
    """ROI et CLV Pinnacle d'une ligne, sans correction (``corriger`` l'ajoute)."""
    from .reglement import GAIN
    regles = [p for p in ligne["paris"] if p.get("statut") in GAIN and p.get("mise")]
    out = {k: ligne[k] for k in ("id", "famille", "nom", "cle") if k in ligne}
    out.update(paris=len(ligne["paris"]), regles=len(regles), teste=False, clv_teste=False)
    if not regles:
        return out
    matchs = [match_de(p) for p in regles]
    roi = mesure([(p.get("gain") or 0.0) / p["mise"] for p in regles], matchs)
    out.update(matchs=roi["matchs"], gain=round(sum(p.get("gain") or 0.0 for p in regles), 2), roi=roi["moyenne"])
    if len(regles) >= MIN_PARIS and roi["matchs"] >= MIN_MATCHS and roi["ic"]:
        out.update(teste=True, roi_ic=roi["ic"], roi_p_pos=roi["p_pos"], roi_p_neg=roi["p_neg"])
    avec = [(p, clvs[id(p)], k) for p, k in zip(regles, matchs) if id(p) in clvs]
    out.update(clv_n=len(avec), couverture=len(avec) / len(regles))
    if avec:
        cles = [k for _, _, k in avec]
        clv = mesure([c for _, c, _ in avec], cles)
        out["clv"] = clv["moyenne"]
        if out["teste"] and len(avec) >= MIN_CLV and clv["matchs"] >= MIN_MATCHS and clv["ic"]:
            # Le rendement des paris mesurés est-il compatible avec leur CLV ? (rendement − CLV, par match)
            ecart = mesure([(p.get("gain") or 0.0) / p["mise"] - c for p, c, _ in avec], cles)
            out.update(clv_teste=True, clv_ic=clv["ic"], clv_p_pos=clv["p_pos"], clv_p_neg=clv["p_neg"],
                       ecart_ic=ecart["ic"])
    return out


def corriger(resultats: list[dict]) -> dict:
    """p-valeurs corrigées, une famille par mesure : toutes les lignes testées, dans les deux sens."""
    from .analyste import benjamini_hochberg
    tests = {}
    for mesure_, drapeau in (("roi", "teste"), ("clv", "clv_teste")):
        testees = [x for x in resultats if x[drapeau]]
        p = [x[f"{mesure_}_p_{sens}"] for x in testees for sens in ("pos", "neg")]
        h, q = holm(p), benjamini_hochberg(p)
        for i, x in enumerate(testees):
            x.update({f"{mesure_}_p_pos_holm": h[2 * i], f"{mesure_}_p_neg_holm": h[2 * i + 1],
                      f"{mesure_}_p_pos_bh": q[2 * i], f"{mesure_}_p_neg_bh": q[2 * i + 1]})
        tests[mesure_] = len(p)
    return tests


def decider(x: dict) -> tuple[str, str]:
    """Décision d'une ligne corrigée et sa raison (docs/avantage-reel.md, « Règles du verdict »)."""
    if not x["teste"]:
        return ATTENDRE, f"trop peu de paris ({x['regles']} réglés)"
    clv_negative = x["clv_teste"] and x["clv"] < 0 and x["clv_p_neg_bh"] < ALPHA
    if x["roi"] < 0 and x["roi_p_neg_bh"] < ALPHA:
        return COUPER, "ROI négatif après correction"
    if x["roi"] < 0 and clv_negative:
        return COUPER, "ROI négatif et CLV Pinnacle négative après correction"
    clv_prouvee = (x["clv_teste"] and x["clv"] > 0 and x["clv_p_pos_holm"] < ALPHA
                   and x["couverture"] >= PART_PINNACLE_MIN)
    contredit = x["clv_teste"] and x["ecart_ic"][1] < 0
    if x["roi"] > 0 and x["roi_p_pos_bh"] < ALPHA:
        return JOUER, "ROI positif après correction"
    if x["roi"] > 0 and clv_prouvee and not contredit:
        return JOUER, "CLV Pinnacle prouvée, ROI positif mais non prouvé"
    if x["roi_ic"][1] < 0:
        return SURVEILLER, "tendance négative : intervalle du ROI sous zéro, non confirmé après correction"
    if clv_negative:
        return SURVEILLER, "CLV Pinnacle négative après correction, ROI positif"
    if clv_prouvee and contredit:
        return ATTENDRE, "CLV Pinnacle prouvée mais contredite par le ROI"
    if clv_prouvee:
        return ATTENDRE, "CLV Pinnacle prouvée, ROI négatif"
    return ATTENDRE, "ni le ROI ni la CLV Pinnacle ne tiennent après correction"


def _publier(x: dict) -> dict:
    """Ligne publiée : pourcentages arrondis, p corrigée dans le sens de la valeur observée."""
    arrondi = lambda v, d=2: None if v is None else round(v, d)  # noqa: E731
    ic = lambda v: None if v is None else [round(v[0], 2), round(v[1], 2)]  # noqa: E731
    out = {k: x.get(k) for k in ("id", "famille", "nom", "cle", "paris", "regles", "matchs", "gain", "clv_n",
                                 "decision", "raison")}
    out.update(roi=arrondi(x.get("roi")), roi_ic=ic(x.get("roi_ic")), clv=arrondi(x.get("clv")),
               clv_ic=ic(x.get("clv_ic")),
               couverture=None if x.get("couverture") is None else round(100 * x["couverture"], 1))
    if x["teste"]:
        out["roi_p"] = x["roi_p_pos_holm" if x["roi"] > 0 else "roi_p_neg_holm"]
    if x["clv_teste"]:
        out["clv_p"] = x["clv_p_pos_holm" if x["clv"] > 0 else "clv_p_neg_holm"]
    return out


def evaluer(paris: list[dict], match_de, clvs: dict[int, float]) -> tuple[list[dict], dict]:
    """Lignes mesurées, corrigées et décidées sur ``paris`` ; nombre de tests par mesure."""
    resultats = [mesurer(l, match_de, clvs) for l in lignes_a_mesurer(paris)]
    tests = corriger(resultats)
    for x in resultats:
        x["decision"], x["raison"] = decider(x)
    return resultats, tests


def _bilan(paris: list[dict], match_de, clvs: dict[int, float]) -> dict:
    """ROI et CLV Pinnacle d'un groupe de paris réglés, intervalles à 95 % par match (comme une ligne de la page)."""
    out = {"regles": len(paris), "matchs": 0, "gain": 0.0, "roi": None, "roi_ic": None, "roi_p": None,
           "clv": None, "clv_ic": None, "clv_n": 0, "couverture": None}
    if not paris:
        return out
    matchs = [match_de(p) for p in paris]
    roi = mesure([(p.get("gain") or 0.0) / p["mise"] for p in paris], matchs)
    avec = [(clvs[id(p)], k) for p, k in zip(paris, matchs) if id(p) in clvs]
    out.update(matchs=roi["matchs"], gain=round(sum(p.get("gain") or 0.0 for p in paris), 2), roi=round(roi["moyenne"], 2),
               clv_n=len(avec), couverture=round(100 * len(avec) / len(paris), 1))
    if roi["ic"]:
        out.update(roi_ic=[round(v, 2) for v in roi["ic"]], roi_p=roi["p_pos"] if roi["moyenne"] > 0 else roi["p_neg"])
    if avec:
        clv = mesure([c for c, _ in avec], [k for _, k in avec])
        out["clv"] = round(clv["moyenne"], 2)
        if clv["ic"]:
            out["clv_ic"] = [round(v, 2) for v in clv["ic"]]
    return out


def rejouer(paris: list[dict], match_de, clvs: dict[int, float]) -> dict:
    """« Quoi jouer » rejoué jour par jour, sans regard vers l'avenir : chaque jour (UTC), les décisions sont refaites
    avec les seuls paris réglés avant minuit, puis appliquées aux paris uniques détectés ce jour-là. Retenus : bookmaker
    ET référence « jouer » (la règle de la page, hors stratégies validées par le protocole). Écartés : les autres paris
    uniques des jours où la règle retenait au moins un bookmaker et une référence, pour comparer à période égale."""
    from collections import defaultdict
    from datetime import time, timezone

    from .laboratoire import heure, regles_avant
    from .reglement import GAIN
    from .simulation import premiers_par_selection
    uniques = premiers_par_selection(paris)
    par_jour = defaultdict(list)
    for p in paris:
        t = heure(p.get("detecte"))
        if id(p) in uniques and t and p.get("statut") in GAIN and p.get("mise"):
            par_jour[t.astimezone(timezone.utc).date()].append(p)
    retenus, ecartes, jours, premier = [], [], 0, None
    for jour in sorted(par_jour):
        passe = regles_avant(paris, datetime.combine(jour, time(), tzinfo=timezone.utc))
        if not passe:
            continue
        jouables = {x["id"] for x in evaluer(passe, match_de, clvs)[0] if x["decision"] == JOUER}
        if not any(i.startswith("bookmaker:") for i in jouables) or not any(i.startswith("reference:") for i in jouables):
            continue
        pris = [p for p in par_jour[jour]
                if "bookmaker:" + str(p.get("bookmaker")) in jouables and "reference:" + str(p.get("reference")) in jouables]
        if pris:
            jours += 1
            premier = premier or jour.isoformat()
        retenus += pris
        ids = {id(p) for p in pris}
        ecartes += [p for p in par_jour[jour] if id(p) not in ids]
    return {"debut": premier, "jours": jours, "retenus": _bilan(retenus, match_de, clvs),
            "ecartes": _bilan(ecartes, match_de, clvs)}


def construire(paris: list[dict], maintenant: datetime) -> dict:
    """Bloc publié dans le site (``D.decision``) : règles appliquées et lignes mesurées, avec leur décision, et le
    bilan de la règle « Quoi jouer » rejouée sans regard vers l'avenir (``rejouer``)."""
    from . import filtres_observes, regle_principale
    from .evenements import identites
    liens = identites(paris)
    match_de = lambda p: liens.get(id(p), ("ligne", p.get("id")))  # noqa: E731
    clvs = clv_pinnacle(paris)
    resultats, tests = evaluer(paris, match_de, clvs)
    return {"calcule_le": maintenant.isoformat(timespec="seconds"),
            "regles": {"alpha": ALPHA, "min_paris": MIN_PARIS, "min_matchs": MIN_MATCHS, "min_clv": MIN_CLV,
                       "part_pinnacle_min": PART_PINNACLE_MIN, "tests_roi": tests["roi"], "tests_clv": tests["clv"]},
            "lignes": [_publier(x) for x in resultats],
            "rejeu": rejouer(paris, match_de, clvs),
            "principale": regle_principale.construire(paris, match_de, clvs),
            "observes": filtres_observes.construire(paris, match_de, clvs)}
