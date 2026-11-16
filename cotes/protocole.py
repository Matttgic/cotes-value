"""Protocole de validation fixé à l'avance : suivi automatique de chaque stratégie (docs/protocole.md).

Tout ce qui décide du verdict est écrit avant les paris, dans ``protocole_registre.json`` : le seuil du test, le
nombre de paris à atteindre, les deux lectures (mi-parcours et finale), l'échéance, et pour chaque stratégie
l'empreinte de ses règles. Ce module applique ces règles sans choix : il ne lit que les paris détectés depuis le
début du protocole, ne teste qu'aux deux lectures prévues, et écrit chaque lecture une seule fois dans
``protocole.json`` (branche « donnees »). Une lecture écrite n'est jamais recalculée.

Mesure : CLV contre la clôture Pinnacle sans marge (docs/avantage-reel.md, décision 1). Test : Student unilatéral
sur la CLV moyenne par pari, l'unité de hasard étant le match (erreur type par grappes, matchs − 1 degrés de liberté).

Empreinte des règles : les sélecteurs sont rejoués sur un jeu de paris témoin figé (sans résultats ni décisions
figées). Mêmes paris, mêmes sélections : l'empreinte ne bouge pas quand le code est réécrit sans changer la règle,
et change dès qu'un seuil ou un filtre change.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import math
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import NormalDist

from .temps import instant

REGISTRE = Path(__file__).with_name("protocole_registre.json")
TEMOIN = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "protocole_temoin.json.gz"
FICHIER = "protocole.json"
EN_COURS, SUCCES, ECHEC, ROMPU, HORS = "en_cours", "succes", "echec", "rompu", "hors_protocole"
# Champs retirés du témoin : résultats (une sélection ne peut pas en dépendre) et décisions figées (les règles
# sont recalculées, pas relues).
CHAMPS_HORS_TEMOIN = frozenset({
    "statut", "gain", "clv", "clv_minimum", "cloture_lue", "cote_juste_cloture", "regle_le", "preuve_reglement",
    "selections_figees", "registre_version", "redecision_lecture_posterieure", "redecision_ajoutees",
    "lien", "lien_repli"})
# Champs d'une définition qui ne sont pas des règles (libellés, état d'affichage).
CHAMPS_COSMETIQUES = frozenset({"nom", "court", "auteur", "regles", "actif", "date", "n"})
MOTIFS = {
    "clv_negative": "CLV Pinnacle moyenne négative ou nulle à mi-parcours",
    "clv_non_prouvee": "CLV Pinnacle non prouvée au seuil du protocole",
    "roi_contredit": "le rendement des paris mesurés est nettement sous leur CLV",
    "couverture": "clôture Pinnacle connue pour moins de la moitié des paris réglés",
    "matchs": "trop peu de matchs différents pour le test",
    "volume": "échéance atteinte sans assez de paris mesurés",
    "pause": "stratégie mise en pause : elle perd contre la clôture",
    "regles_modifiees": "règles modifiées pendant le protocole",
    "remplacee": "remplacée par une nouvelle version, inscrite à part",
}


def registre() -> dict:
    return json.loads(REGISTRE.read_text(encoding="utf-8"))


def alpha(regles: dict) -> float:
    """Seuil unilatéral d'un test : 5 % partagés entre toutes les places du registre (Bonferroni)."""
    return regles["alpha_famille"] / regles["places"]


def taille(sigma: float, regles: dict) -> int:
    """Paris mesurés à atteindre pour prouver une CLV de ``effet`` avec la puissance voulue, arrondis à la dizaine
    supérieure. ``sigma`` : écart-type par pari de la CLV, grappes de matchs comprises."""
    z = NormalDist().inv_cdf(1 - alpha(regles)) + NormalDist().inv_cdf(regles["puissance"])
    n = (z * sigma / regles["effet"]) ** 2
    return max(regles["n_min"], 10 * math.ceil(n / 10 - 1e-9))


def scelle(doc: dict, k: int | None = None) -> str:
    """Empreinte des règles communes et des ``k`` premières inscriptions : le registre ne peut que s'allonger."""
    corps = {"regles": doc["regles"], "inscrites": doc["inscrites"][:k]}
    return hashlib.sha256(json.dumps(corps, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


# ---------------------------------------------------------------- statistiques (sans numpy : calculées à chaque site)

def _beta_incomplete(a: float, b: float, x: float) -> float:
    """Fonction bêta incomplète régularisée (fraction continue de Lentz)."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    if x > (a + 1) / (a + b + 2):
        return 1 - _beta_incomplete(b, a, 1 - x)
    devant = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1 - x))
    petit = 1e-300
    c, d = 1.0, 1 - (a + b) * x / (a + 1)
    d = 1 / (d if abs(d) > petit else petit)
    h = d
    for m in range(1, 500):
        for num in (m * (b - m) * x / ((a + 2 * m - 1) * (a + 2 * m)),
                    -(a + m) * (a + b + m) * x / ((a + 2 * m) * (a + 2 * m + 1))):
            d = 1 + num * d
            d = 1 / (d if abs(d) > petit else petit)
            c = 1 + num / c
            c = c if abs(c) > petit else petit
            h *= d * c
        if abs(d * c - 1) < 1e-14:
            break
    return devant * h / a


def p_student(t: float, ddl: float) -> float:
    """P(T ≥ t) pour une loi de Student à ``ddl`` degrés de liberté."""
    queue = 0.5 * _beta_incomplete(ddl / 2, 0.5, ddl / (ddl + t * t))
    return queue if t >= 0 else 1 - queue


def moyenne_par_match(valeurs: list[float], matchs: list) -> dict:
    """Moyenne par pari et son erreur type quand les paris d'un même match varient ensemble (même estimateur que
    scripts/avantage_reel.rapport). ``t`` et ``p`` (unilatérale, moyenne > 0) absents sous deux matchs."""
    n = len(valeurs)
    m = sum(valeurs) / n
    somme, compte = defaultdict(float), defaultdict(int)
    for v, c in zip(valeurs, matchs):
        somme[c] += v
        compte[c] += 1
    k = len(somme)
    out = {"n": n, "matchs": k, "moyenne": m, "erreur_type": None, "t": None, "p": None}
    if k >= 2:
        et = math.sqrt(sum((somme[c] - m * compte[c]) ** 2 for c in somme) * k / (k - 1)) / n
        if et > 0:
            out.update(erreur_type=et, t=m / et, p=p_student(m / et, k - 1))
    return out


# ---------------------------------------------------------------- sélections, clôture Pinnacle

def selections_officielles(paris: list[dict]) -> dict[str, set[int]]:
    """Prises de chaque stratégie suivie, par clé : 7 de base, convergence, variantes, règles du laboratoire."""
    from .convergence import paris_convergence, selections
    from .laboratoire import DEBUT_SUIVI, REGLES, selectionner
    from .protection import calculer
    from .strategies_prudentes import selections_prudentes
    out = selections(paris)
    out["convergence"] = paris_convergence(paris, out)
    out.update(selections_prudentes(paris, bases=out))
    for r in REGLES:
        out["labo:" + r.id] = calculer(r.id, lambda r=r: {id(p) for p in selectionner(paris, r, DEBUT_SUIVI)})
    return out


def clv_pinnacle(paris: list[dict]) -> dict[int, float]:
    """CLV des paris réglés contre la clôture Pinnacle : celle du pari si Pinnacle est sa référence, sinon celle du
    même pari (même bookmaker, match, marché, issue) repéré aussi par Pinnacle, recalculée à la cote du pari, sinon
    la clôture Pinnacle lue sur le pari lui-même (``cote_juste_cloture_pinnacle``, enregistrée depuis le 16/11/2026)."""
    from .convergence import cle_selection
    from .reglement import GAIN
    from .simulation import clv_finale, clv_pinnacle_propre
    juste: dict[tuple, tuple[str, float]] = {}
    for p in paris:
        if p.get("reference") == "Pinnacle" and clv_finale(p) is not None and p.get("match_id"):
            lu, k = p["cloture_lue"], cle_selection(p)
            if k not in juste or lu > juste[k][0]:
                juste[k] = (lu, p["cote_juste_cloture"])
    out = {}
    for p in paris:
        if p.get("statut") not in GAIN:
            continue
        if p.get("reference") == "Pinnacle":
            c = clv_finale(p)
            if c is not None:
                out[id(p)] = c
        elif p.get("match_id") and cle_selection(p) in juste:
            out[id(p)] = p["cote"] / juste[cle_selection(p)][1] - 1
        elif (c := clv_pinnacle_propre(p)) is not None:       # clôture Pinnacle lue sur le pari (depuis le 16/11/2026)
            out[id(p)] = c
    return out


# ---------------------------------------------------------------- empreintes des règles

def definitions() -> dict[str, dict]:
    """Paramètres déclarés de chaque stratégie, sans les libellés. Entrée de l'empreinte, avec ses prises témoin."""
    from dataclasses import asdict
    from .convergence import CONVERGENCE, STRATEGIES
    from .laboratoire import REGLES
    from .simulation import STRATEGIE
    from .strategie_chatgpt import CHATGPT
    from .strategie_eden import EDEN
    from .strategie_gemini import GEMINI
    from .strategie_jules import JULES
    from .strategie_jules_v2 import JULES_V2
    from .strategie_m3 import M3
    from .strategies_prudentes import VARIANTES
    bases = {"strategie": STRATEGIE, "chatgpt": CHATGPT, "gemini": GEMINI, "jules": JULES, "jules_v2": JULES_V2,
             "eden": EDEN, "m3": M3}
    out = {cle: {**bases[cle], "ligne": nom, "nom": nom.replace(" (rejeu)", "")} for cle, _, _, nom, _ in STRATEGIES}
    out["convergence"] = {"ligne": CONVERGENCE["nom"], **CONVERGENCE}
    out.update({v["cle"]: {"ligne": v["nom"], **v} for v in VARIANTES if v.get("actif", True)})
    out.update({"labo:" + r.id: {"ligne": r.id, "nom": r.nom, "version": "1", **asdict(r)} for r in REGLES})
    return out


def _json(x) -> str:
    return json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      default=lambda o: sorted(o) if isinstance(o, (set, frozenset)) else str(o))


def lire_temoin(chemin: Path = TEMOIN) -> tuple[list[dict], str] | None:
    """(paris témoin, SHA-256 du fichier), ou None s'il est absent ou illisible."""
    try:
        brut = chemin.read_bytes()
        return json.loads(gzip.decompress(brut)), hashlib.sha256(brut).hexdigest()
    except (OSError, ValueError, EOFError):
        return None


def empreintes(temoin: list[dict]) -> dict[str, str]:
    """Empreinte de chaque stratégie : ses paramètres déclarés et les paris qu'elle prend dans le témoin."""
    prises = selections_officielles(temoin)
    out = {}
    for cle, d in definitions().items():
        declare = {k: v for k, v in d.items() if k not in CHAMPS_COSMETIQUES and k != "ligne"}
        ids = sorted(p["id"] for p in temoin if id(p) in prises.get(cle, ()))
        out[cle] = hashlib.sha256(_json({"definition": declare, "prises": ids}).encode()).hexdigest()[:16]
    return out


def empreintes_actuelles(doc: dict | None = None) -> dict[str, str] | None:
    """Empreintes du code en place, ou None si le témoin manque ou n'est plus celui du registre."""
    doc = doc or registre()
    lu = lire_temoin()
    if lu is None or lu[1] != doc["regles"]["temoin_sha256"]:
        return None
    return empreintes(lu[0])


# ---------------------------------------------------------------- lectures et verdict

def _ordre(p: dict):
    """Ordre des paris d'une lecture : début du match, puis détection, puis identifiant."""
    return (instant(p.get("debut")) or datetime.max.replace(tzinfo=timezone.utc), str(p.get("detecte")), str(p.get("id")))


def lecture(mesures: list[tuple[dict, float]], regles_: list[dict], match_de, r: dict, finale: bool) -> dict:
    """Chiffres et verdict d'une lecture sur ``mesures`` (paris réglés avec leur CLV Pinnacle, déjà triés et coupés).
    ``regles_`` : tous les paris réglés du protocole jusqu'au dernier pari mesuré (couverture, ROI)."""
    matchs = [match_de(p) for p, _ in mesures]
    clv = moyenne_par_match([c for _, c in mesures], matchs)
    ecart = moyenne_par_match([(p.get("gain") or 0.0) / p["mise"] - c for p, c in mesures], matchs)
    mises = sum(p["mise"] for p in regles_)
    p_ecart = None if ecart["t"] is None else 1 - ecart["p"]        # P(T ≤ t) : rendement sous la CLV
    out = {"n": clv["n"], "matchs": clv["matchs"], "clv": round(100 * clv["moyenne"], 3),
           "t": None if clv["t"] is None else round(clv["t"], 3), "p": clv["p"],
           "couverture": round(100 * len(mesures) / len(regles_), 1), "regles": len(regles_),
           "roi": round(100 * sum(p.get("gain") or 0.0 for p in regles_) / mises, 2) if mises else None,
           "ecart": round(100 * ecart["moyenne"], 2), "p_ecart": p_ecart}
    contredit = p_ecart is not None and p_ecart < r["alpha_roi"]
    if not finale:
        motif = "clv_negative" if clv["moyenne"] <= 0 else "roi_contredit" if contredit else None
    elif clv["matchs"] < r["matchs_min"]:
        motif = "matchs"
    elif len(mesures) < r["couverture_min"] * len(regles_):
        motif = "couverture"
    elif clv["p"] is None or clv["moyenne"] <= 0 or clv["p"] >= alpha(r):
        motif = "clv_non_prouvee"
    else:
        motif = "roi_contredit" if contredit else None
    out["motif"] = motif
    return out


def _lire_etat(donnees) -> dict:
    try:
        etat = json.loads((Path(donnees) / FICHIER).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return etat if isinstance(etat, dict) and isinstance(etat.get("lectures"), dict) else {}


def suivre(paris: list[dict], selections: dict[str, set[int]], donnees, maintenant: datetime,
           actuelles: dict[str, str] | None = None, doc: dict | None = None, ecrire: bool = True,
           indisponibles=()) -> dict:
    """État du protocole de chaque stratégie, publié dans le site (``D.protocole``).

    ``paris`` : ceux des bilans (cote ≤ plafond, mise fixe) ; ``selections`` : prises par clé ;
    ``actuelles`` : empreintes du code en place (None ou clé absente : non vérifiée) ; ``indisponibles`` : clés des stratégies
    en erreur à cette construction (aucune lecture nouvelle). Écrit dans ``protocole.json`` les lectures franchies
    depuis la dernière construction ; une erreur d'écriture n'est pas propagée."""
    from . import pauses
    from .evenements import identites
    from .reglement import GAIN
    doc = doc or registre()
    r = doc["regles"]
    etat = _lire_etat(donnees)
    lectures = {k: dict(v) for k, v in (etat.get("lectures") or {}).items()}
    avant = json.dumps(lectures, sort_keys=True)
    liens = identites(paris)
    match_de = lambda p: liens.get(id(p), ("ligne", p.get("id")))  # noqa: E731
    clvs = clv_pinnacle(paris)
    en_pause = pauses.actives()
    quand = maintenant.isoformat(timespec="seconds")
    dernieres = {e["cle"]: i for i, e in enumerate(doc["inscrites"])}
    lignes, par_cle = {}, {}
    for i, e in enumerate(doc["inscrites"]):
        cle, ident = e["cle"], f"{e['cle']}@{e['version']}"
        debut = instant(e["debut"])
        fin = debut + timedelta(days=r["duree_jours"])
        memoire = lectures.setdefault(ident, {})
        prises = selections.get(cle, ())
        rows = [p for p in paris if id(p) in prises and instant(p.get("detecte")) is not None
                and debut <= instant(p["detecte"]) < maintenant]
        regles_ = sorted((p for p in rows if p.get("statut") in GAIN and p.get("mise")), key=_ordre)
        mesures = [(p, clvs[id(p)]) for p in regles_ if id(p) in clvs]
        mi = math.ceil(e["n"] * r["part_mi_parcours"])

        def lire(k: int, finale: bool) -> dict:
            coupe = mesures[:k]
            dernier = _ordre(coupe[-1][0])
            return {"le": quand, **lecture(coupe, [p for p in regles_ if _ordre(p) <= dernier], match_de, r, finale)}

        if "finale" not in memoire and cle not in indisponibles:
            if dernieres[cle] != i:
                memoire["finale"] = {"le": quand, "motif": "remplacee"}
            elif actuelles is not None and cle in actuelles and actuelles[cle] != e["empreinte"]:
                memoire.setdefault("rompu", {"le": quand, "empreinte": actuelles[cle]})
            elif "rompu" not in memoire:
                if cle in en_pause:
                    memoire["finale"] = {"le": quand, "motif": "pause"}
                else:
                    if "mi_parcours" not in memoire and len(mesures) >= mi:
                        memoire["mi_parcours"] = lire(mi, finale=False)
                        if memoire["mi_parcours"]["motif"]:
                            memoire["finale"] = {"le": quand, "motif": memoire["mi_parcours"]["motif"], "anticipe": True}
                    if "finale" not in memoire and len(mesures) >= e["n"]:
                        memoire["finale"] = lire(e["n"], finale=True)
                    elif "finale" not in memoire and maintenant >= fin:
                        memoire["finale"] = (lire(len(mesures), finale=True) if "mi_parcours" in memoire
                                             else {"le": quand, "motif": "volume"})
        finale = memoire.get("finale")
        if finale:
            statut, motif = (ECHEC, finale["motif"]) if finale["motif"] else (SUCCES, None)
        elif "rompu" in memoire:
            statut, motif = ROMPU, "regles_modifiees"
        else:
            statut, motif = EN_COURS, None
        jours = max((maintenant - debut).total_seconds() / 86400, 0.0)
        fin_estimee = None
        if statut == EN_COURS and jours >= 7 and mesures:
            estimee = debut + timedelta(days=jours * e["n"] / len(mesures))
            fin_estimee = estimee.date().isoformat() if estimee < fin else "après l'échéance"
        ligne = {"cle": cle, "nom": e["nom"], "version": e["version"], "debut": e["debut"], "echeance": fin.isoformat(),
                 "n": e["n"], "mi": mi, "statut": statut, "motif": motif and MOTIFS[motif], "paris": len(rows),
                 "regles": len(regles_), "mesures": len(mesures),
                 "couverture": round(100 * len(mesures) / len(regles_), 1) if regles_ else None,
                 "fin_estimee": fin_estimee, "mi_parcours": memoire.get("mi_parcours"), "finale": finale}
        if dernieres[cle] == i:
            lignes[e["ligne"]] = ligne
            par_cle[cle] = ligne
    # Stratégie suivie par le site mais absente du registre : aucune conclusion permise.
    for cle, d in definitions().items():
        if cle not in par_cle:
            lignes[d["ligne"]] = {"cle": cle, "nom": d.get("nom") or d["ligne"], "statut": HORS,
                                  "motif": "pas encore inscrite au registre du protocole"}
    lectures = {k: v for k, v in lectures.items() if v}
    if ecrire and json.dumps(lectures, sort_keys=True) != avant:
        chemin = Path(donnees) / FICHIER
        try:
            tmp = chemin.with_name(chemin.name + ".tmp")
            tmp.write_text(json.dumps({"version": 1, "lectures": lectures}, ensure_ascii=False, indent=1) + "\n",
                           encoding="utf-8")
            os.replace(tmp, chemin)
        except OSError:
            pass
    compte = defaultdict(int)
    for l in lignes.values():
        compte[l["statut"]] += 1
    return {"regles": {**{k: r[k] for k in ("debut", "duree_jours", "places", "effet", "puissance", "couverture_min",
                                             "alpha_roi", "matchs_min", "part_mi_parcours")},
                       "alpha": alpha(r), "inscrites": len(doc["inscrites"]), "scelle": scelle(doc)[:12],
                       "empreintes_verifiees": actuelles is not None},
            "resume": dict(compte), "lignes": lignes}
