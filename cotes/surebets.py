"""Surebets : des cotes de bookmakers français différents qui, ensemble, gagnent quoi qu'il arrive.

Même match chez plusieurs bookmakers : l'association du cycle (``comparaison.indexer``, cotes/correspondance.py)
relie chaque match français à une rencontre de référence. Deux matchs français reliés à la même rencontre de la même
référence (Pinnacle d'abord, voir ``ORDRE_REFERENCES``) sont le même match ; un match relié à l'envers est retourné
(``marches.inverser``) avant d'être comparé.

Pour chaque marché (période, ligne), on garde la meilleure cote de chaque issue. Si les issues couvrent tous les
résultats et que Σ 1/cote < 1, miser sur chaque issue une part proportionnelle à 1/cote rend la même somme quel que
soit le résultat :

    rendement = 1 / Σ(1/cote) − 1        (100 € répartis rendent 100 × (1 + rendement) €)

Issues retenues (tous les résultats couverts, aucun remboursement possible) :
- 1N2 et handicap à trois issues : domicile, nul, extérieur ;
- vainqueur et « les deux équipes marquent » ; handicaps et totaux à demi-ligne (2,5, −1,5…) : deux issues ;
- double chance contre l'issue qui lui manque au 1N2 (1X + 2, X2 + 1, 12 + N), même période.
Lignes entières et quarts de ligne (remboursement possible), remboursé si nul, score exact et mi-temps/fin : écartés.

Garde-fous (un gros surebet est presque toujours une erreur de lecture ou un prix déjà parti) :
- au moins deux bookmakers ; match pas commencé ;
- chaque cote lue depuis moins de ``AGE_MAX`` à l'heure du cycle (``AGE_MAX_LOINTAIN`` pour un match à plus de 6 h
  chez les bookmakers qui le relisent par tranches) ;
- une cote qui a sa cote juste chez la référence du match (lue au même moment, règle de la comparaison) doit en être
  proche (``ECART_JUSTE_BAS`` à ``comparaison.ECART_SUSPECT``). Quand toutes les jambes en ont une, leurs
  probabilités justes doivent faire 1 à ``TOLERANCE_PARTITION`` près (les issues couvrent bien tous les résultats) et
  le surebet est « vérifié ». Sans cote juste pour une jambe (ligne que la référence ne propose pas), il reste
  affiché mais « non vérifié » : à contrôler avant de miser ;
- intitulé contrôlé conforme et match bien associé (cotes/controle.py) ;
- rendement au-delà de ``RENDEMENT_SUSPECT`` (``RENDEMENT_SUSPECT_NON_VERIFIE`` sans cote juste) : gardé, mais marqué
  suspect (jamais suivi ni envoyé en alerte).
Une cote qui échoue un garde-fou est retirée avant le choix de la meilleure cote de son issue : le surebet gardé est
le meilleur qui reste valable.

Suivi (``suivre``) : un épisode par match et marché, du premier cycle où le surebet existe au dernier (un trou de
moins de ``REPRISE_MAX`` ne le coupe pas). « Gain si pris à la détection » : 100 € répartis aux cotes du premier
cycle. Garanti sur le papier seulement : la cote peut bouger avant la deuxième mise, la mise peut être plafonnée et
les comptes qui jouent les surebets sont limités.
"""
from __future__ import annotations

import hashlib
import math
from datetime import datetime, timedelta
from itertools import product
from statistics import median

from . import controle as CT
from .comparaison import ECART_SUSPECT, ECART_SUSPECT_GROSSES, hors_perimetre_anj, libelle_pari
from .liens import lien_info
from .marches import cle, inverser

ORDRE_REFERENCES = ("Pinnacle", "Polymarket", "Matchbook", "Smarkets", "Betfair")
AGE_MAX = timedelta(minutes=10)
# Matchs à plus de 6 h : PMU, Unibet et Betclic les relisent par tranches tournantes (même règle que les alertes,
# cotes/notifications.py) ; leur dernière lecture reste le bon prix.
LOINTAIN = timedelta(hours=6)
AGE_MAX_LOINTAIN = {"PMU": timedelta(minutes=25), "Unibet": timedelta(minutes=32), "Betclic": timedelta(minutes=39)}
ECART_JUSTE_BAS = -0.30
TOLERANCE_PARTITION = 0.03
RENDEMENT_SUSPECT = 0.15
# Sans cote juste pour contrôler, au-delà de 5 % c'est presque toujours une erreur de lecture : rejeu des 13-14/11/2026,
# huit « surebets » de 9 à 12 % sur les handicaps d'un même match de basket (Winamax contre Betclic), aucun vérifiable.
RENDEMENT_SUSPECT_NON_VERIFIE = 0.05
SEUIL_ALERTE = 0.01
TOTAL = 100.0
MEILLEURES = 3                     # cotes gardées par issue pour chercher une combinaison à deux bookmakers
REPRISE_MAX = timedelta(minutes=11)
GARDER_JOURS = 21
EPISODES_MAX = 2500

TROIS_ISSUES = {"RESULTAT_1N2": ("DOM", "NUL", "EXT"), "HANDICAP_3": ("DOM", "NUL", "EXT")}
DEUX_ISSUES = {"VAINQUEUR": ("DOM", "EXT"), "BOTH_TEAMS_TO_SCORE": ("YES", "NO")}
DEMI_LIGNE = {"HANDICAP": ("DOM", "EXT"), "JEUX_HANDICAP": ("DOM", "EXT"), "SETS_HANDICAP": ("DOM", "EXT"),
              **{m: ("PLUS", "MOINS") for m in ("TOTAL", "TOTAL_DOM", "TOTAL_EXT", "JEUX_TOTAL", "JEUX_TOTAL_DOM",
                                                "JEUX_TOTAL_EXT", "SETS_TOTAL")}}
CROISES = (("HOME_DRAW", "EXT"), ("DRAW_AWAY", "DOM"), ("HOME_AWAY", "NUL"))


def _t(s) -> datetime | None:
    return CT._lue(s)


def demi_ligne(x) -> bool:
    """2,5 ou −1,5 : aucune égalité possible avec la ligne, donc aucun remboursement."""
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
        return False
    d = 2 * x
    return abs(d - round(d)) < 1e-9 and round(d) % 2 == 1


# --------------------------------------------------------------------------- calculs

def rendement(cotes: list[float]) -> float:
    """1 / Σ(1/cote) − 1 : positif = surebet."""
    return 1 / sum(1 / c for c in cotes) - 1


def repartir(cotes: list[float], total: float = TOTAL, pas: float = 1.0) -> dict:
    """Mises arrondies à ``pas`` près pour ``total`` euros, choisies pour que le pire résultat rapporte le plus.

    Rend {"mises", "mise_totale", "gain_min", "gain_max"} (gains nets, en euros)."""
    s = sum(1 / c for c in cotes)
    exactes = [total / c / s for c in cotes]
    meilleur = None
    for choix in product(*[(math.floor(x / pas) * pas, math.ceil(x / pas) * pas) for x in exactes]):
        mises = [round(m, 2) for m in choix]
        if min(mises) <= 0:
            continue
        mise = sum(mises)
        if mise > total + 1e-9:                # jamais plus que la somme prévue
            continue
        retours = [m * c for m, c in zip(mises, cotes)]
        cle_tri = (round(min(retours) - mise, 6), -mise)
        if meilleur is None or cle_tri > meilleur[0]:
            meilleur = (cle_tri, mises, mise, retours)
    if meilleur is None:                       # mises trop petites pour le pas : sans arrondi
        mises = [round(x, 2) for x in exactes]
        mise, retours = sum(mises), [m * c for m, c in zip(mises, cotes)]
    else:
        _, mises, mise, retours = meilleur
    return {"mises": mises, "mise_totale": round(mise, 2), "gain_min": round(min(retours) - mise, 2),
            "gain_max": round(max(retours) - mise, 2)}


# --------------------------------------------------------------------------- détection

def pivots(index: dict) -> dict[str, tuple[str, object, bool]]:
    """Match français -> (référence, rencontre de la référence, inversé ?), la première référence de
    ``ORDRE_REFERENCES`` qui connaît le match."""
    noms = [n for n in ORDRE_REFERENCES if n in (index or {})] + sorted(n for n in (index or {})
                                                                     if n not in ORDRE_REFERENCES)
    out: dict[str, tuple[str, object, bool]] = {}
    for nom in noms:
        par_match = index.get(nom)
        if not isinstance(par_match, dict):
            continue
        for mid_fr, par_cle in par_match.items():
            if mid_fr in out or not isinstance(par_cle, dict):
                continue
            ligne = next((x for x in par_cle.values() if isinstance(x, dict) and x.get("match_id") is not None), None)
            if ligne is not None:
                out[mid_fr] = (nom, ligne["match_id"], bool(ligne.get("inverse")))
    return out


def juste_utilisable(l: dict, juste: dict | None) -> bool:
    """Cote juste de la même sélection, lue au même moment que la cote française, au milieu du carnet."""
    return bool(juste and not juste.get("prix_prudent") and 0 < (juste.get("proba_juste") or 0) < 1
                and CT.contemporaines(l, juste))


def _raison(l: dict, juste: dict | None, maintenant: datetime, controle) -> str | None:
    """Pourquoi une cote française ne peut pas entrer dans un surebet (None = elle peut)."""
    c = l.get("cote")
    if isinstance(c, bool) or not isinstance(c, (int, float)) or not math.isfinite(c) or c <= 1:
        return "cote"
    lu, debut = _t(l.get("collecte")), _t(l.get("debut"))
    if lu is None or debut is None:
        return "heure"
    if debut <= max(lu, maintenant):
        return "commencé"
    age_max = AGE_MAX_LOINTAIN.get(l.get("source"), AGE_MAX) if debut - maintenant > LOINTAIN else AGE_MAX
    if maintenant - lu > age_max or lu - maintenant > timedelta(minutes=2):
        return "cote ancienne"
    if juste_utilisable(l, juste):
        ecart = c * juste["proba_juste"] - 1
        if not ECART_JUSTE_BAS <= ecart <= (ECART_SUSPECT if c <= 10 else ECART_SUSPECT_GROSSES):
            return "loin de la cote juste"
    if controle:
        r = CT.raison(l, *controle)
        if r:
            return r
    return None


def _jambe(l: dict, issue: str, juste: dict | None) -> dict:
    lien, repli = lien_info({"bookmaker": l.get("source"), "match_id": l.get("match_id"), "lien": l.get("lien"),
                             "sport": l.get("sport"), "domicile": l.get("domicile"), "exterieur": l.get("exterieur"),
                             "ligue": l.get("ligue")})
    p = juste["proba_juste"] if juste_utilisable(l, juste) else None
    return {"bookmaker": l.get("source"), "match_id": l.get("match_id"), "issue": issue, "pari": libelle_pari(l),
            "libelle_bookmaker": l.get("libelle"), "cote": float(l["cote"]), "lu": l.get("collecte"),
            "proba_juste": round(p, 5) if p else None, "cote_juste": round(1 / p, 3) if p else None,
            "ecart": round(l["cote"] * p - 1, 4) if p else None, "lien": lien, "lien_repli": repli}


def candidates(francais: list[dict], index: dict, maintenant: datetime,
               controle: tuple[dict, dict] | None = None) -> tuple[dict[tuple, dict[str, list]], dict, dict]:
    """(famille -> issue -> jambes possibles, famille -> description du match, raisons d'exclusion comptées).

    Famille = (référence, rencontre, marché, période, ligne), écrite dans le sens de la référence."""
    piv = pivots(index)
    familles: dict[tuple, dict[str, list]] = {}
    matchs: dict[tuple, dict] = {}
    raisons: dict[str, int] = {}
    for l in francais:
        marche = str(l.get("marche") or "")
        if marche.startswith("JOUEUR:") or str(l.get("periode") or "").endswith("?") or hors_perimetre_anj(l):
            continue
        p = piv.get(l.get("match_id"))
        if p is None:
            continue
        nom, mid_ref, inverse = p
        lc = inverser(l) if inverse else l
        m, ligne = lc["marche"], lc.get("ligne")
        if not (m in TROIS_ISSUES or m in DEUX_ISSUES or m == "DOUBLE_CHANCE" or (m in DEMI_LIGNE and demi_ligne(ligne))):
            continue
        juste = (index.get(nom) or {}).get(l["match_id"], {}).get(cle(l))
        r = _raison(l, juste, maintenant, controle)
        if r:
            raisons[r] = raisons.get(r, 0) + 1
            continue
        fam = (nom, mid_ref, m, lc["periode"], None if ligne is None else round(float(ligne), 2))
        familles.setdefault(fam, {}).setdefault(lc["issue"], []).append(_jambe(l, lc["issue"], juste))
        matchs.setdefault((nom, mid_ref), {"sport": l.get("sport"), "ligue": l.get("ligue"),
                                           "domicile": lc.get("domicile"), "exterieur": lc.get("exterieur"),
                                           "debut": l.get("debut")})
    return familles, matchs, raisons


def _meilleures(jambes: list[dict]) -> list[dict]:
    """Les meilleures cotes de l'issue, une par bookmaker, de la plus haute à la plus basse."""
    par_book: dict[str, dict] = {}
    for j in jambes:
        a = par_book.get(j["bookmaker"])
        if a is None or (j["cote"], j["lu"] or "") > (a["cote"], a["lu"] or ""):
            par_book[j["bookmaker"]] = j
    return sorted(par_book.values(), key=lambda j: (-j["cote"], j["bookmaker"]))[:MEILLEURES]


def verifie(combo: list[dict]) -> bool:
    """Toutes les jambes ont une cote juste (même référence) : la combinaison est contrôlée."""
    return all(j.get("proba_juste") for j in combo)


def meilleure_combinaison(listes: list[list[dict]]) -> list[dict] | None:
    """La combinaison (une jambe par issue) au plus grand rendement, avec au moins deux bookmakers ; quand toutes
    les jambes ont une cote juste, leurs probabilités justes doivent faire 1. À rendement égal, une combinaison
    vérifiée passe devant."""
    meilleur = None
    for combo in product(*listes):
        if len({j["bookmaker"] for j in combo}) < 2:
            continue
        ok = verifie(combo)
        if ok and abs(sum(j["proba_juste"] for j in combo) - 1) > TOLERANCE_PARTITION:
            continue
        cle_tri = (round(rendement([j["cote"] for j in combo]), 6), ok)
        if meilleur is None or cle_tri > meilleur[0]:
            meilleur = (cle_tri, list(combo))
    return meilleur[1] if meilleur else None


def _nombre(x) -> str:
    return (f"{x:+g}" if x else "0").replace(".", ",")


def libelle_famille(marche: str, periode: str, ligne, sport: str | None, croise: str | None = None) -> str:
    """« 1N2 », « Plus/moins de 2,5 buts », « Handicap −1,5 (domicile) », « Double chance 1X + 2 »…"""
    from .comparaison import PERIODES
    unite = {"football": " buts", "hockey": " buts", "handball": " buts", "basket": " points",
             "football_americain": " points", "rugby": " points", "volley": " points"}.get(sport or "", "")
    l = str(ligne).replace(".", ",") if ligne is not None else ""
    if croise:
        s = {"HOME_DRAW": "Double chance 1X + 2", "DRAW_AWAY": "Double chance X2 + 1",
             "HOME_AWAY": "Double chance 12 + nul"}[croise]
    elif marche == "RESULTAT_1N2":
        s = "1N2"
    elif marche == "HANDICAP_3":
        s = f"Handicap à 3 issues {_nombre(ligne)} (domicile)"
    elif marche == "VAINQUEUR":
        s = "Vainqueur"
    elif marche == "BOTH_TEAMS_TO_SCORE":
        s = "Les deux équipes marquent"
    elif marche.endswith("HANDICAP"):
        s = f"Handicap {_nombre(ligne)} (domicile)" + {"JEUX_HANDICAP": " en jeux", "SETS_HANDICAP": " en sets"}.get(marche, "")
    else:
        u = " jeux" if marche.startswith("JEUX_") else " sets" if marche.startswith("SETS_") else unite
        qui = " (domicile)" if marche.endswith("_DOM") else " (extérieur)" if marche.endswith("_EXT") else ""
        s = f"Plus/moins de {l}{u}{qui}"
    return s + PERIODES.get(periode, f" ({periode})")


def _surebet(fam: tuple, combo: list[dict], match: dict, maintenant: datetime, croise: str | None = None) -> dict:
    nom, mid_ref, marche, periode, ligne = fam
    combo = [dict(j) for j in combo]          # une jambe peut servir à deux combinaisons (1N2 et double chance)
    cotes = [j["cote"] for j in combo]
    r = rendement(cotes)
    cle_s = "|".join(str(x) for x in (nom, mid_ref, marche, periode, ligne, croise or ""))
    lus = sorted(j["lu"] for j in combo)
    rep = repartir(cotes)
    for j, m in zip(combo, rep["mises"]):
        j["mise_100"] = m
    return {"id": hashlib.sha1(cle_s.encode()).hexdigest()[:16], "cle": cle_s, "detecte": maintenant.isoformat(timespec="seconds"),
            **match, "match": f'{match.get("domicile")} – {match.get("exterieur")}',
            "marche": "DOUBLE_CHANCE+1N2" if croise else marche, "periode": periode, "ligne": ligne,
            "pari": libelle_famille(marche, periode, ligne, match.get("sport"), croise),
            "reference": nom, "match_id_reference": mid_ref, "jambes": combo,
            "bookmakers": sorted({j["bookmaker"] for j in combo}),
            "verifie": verifie(combo), "somme_inverses": round(sum(1 / c for c in cotes), 5), "rendement": round(r, 5),
            "gain_100": rep["gain_min"], "mise_100": rep["mise_totale"], "lu_premier": lus[0], "lu_dernier": lus[-1],
            "suspect": "rendement trop grand" if r > RENDEMENT_SUSPECT else
            "trop beau sans cote juste pour vérifier" if r > RENDEMENT_SUSPECT_NON_VERIFIE and not verifie(combo) else None}


def detecter(francais: list[dict], index: dict, maintenant: datetime,
             controle: tuple[dict, dict] | None = None) -> tuple[list[dict], dict]:
    """(surebets du cycle, du plus rentable au moins rentable ; journal : familles vues, raisons d'exclusion)."""
    familles, matchs, raisons = candidates(francais, index, maintenant, controle)
    out = []
    for fam, issues in familles.items():
        m = fam[2]
        attendues = TROIS_ISSUES.get(m) or DEUX_ISSUES.get(m) or DEMI_LIGNE.get(m)
        if not attendues or any(i not in issues for i in attendues):
            continue
        combo = meilleure_combinaison([_meilleures(issues[i]) for i in attendues])
        if combo and rendement([j["cote"] for j in combo]) > 0:
            out.append(_surebet(fam, combo, matchs[fam[:2]], maintenant))
    for fam, issues in familles.items():           # double chance + issue restante du 1N2, même période
        if fam[2] != "DOUBLE_CHANCE":
            continue
        un_n_deux = familles.get((fam[0], fam[1], "RESULTAT_1N2", fam[3], None)) or {}
        for dc, reste in CROISES:
            if dc in issues and reste in un_n_deux:
                combo = meilleure_combinaison([_meilleures(issues[dc]), _meilleures(un_n_deux[reste])])
                if combo and rendement([j["cote"] for j in combo]) > 0:
                    out.append(_surebet((fam[0], fam[1], "RESULTAT_1N2", fam[3], None), combo, matchs[fam[:2]],
                                        maintenant, croise=dc))
    # Un seul surebet par match et période pour le 1N2 et ses doubles chances : le meilleur (mêmes résultats couverts).
    out.sort(key=lambda s: -s["rendement"])
    vus, garde = set(), []
    for s in out:
        k = (s["reference"], s["match_id_reference"], s["periode"]) if s["marche"] in ("RESULTAT_1N2", "DOUBLE_CHANCE+1N2") \
            else s["cle"]
        if k in vus:
            continue
        vus.add(k)
        garde.append(s)
    return garde, {"familles": len(familles), "surebets": len(garde),
                   "suspects": sum(bool(s["suspect"]) for s in garde), "exclues": raisons}


# --------------------------------------------------------------------------- suivi

def _compact(j: dict) -> dict:
    return {k: j.get(k) for k in ("bookmaker", "issue", "pari", "cote", "cote_juste", "mise_100")}


def suivre(etat: dict | None, actuels: list[dict], maintenant: datetime) -> dict:
    """Épisodes mis à jour avec les surebets du cycle (les suspects ne sont pas suivis)."""
    episodes = [e for e in ((etat or {}).get("episodes") or []) if isinstance(e, dict) and e.get("cle")]
    ouverts = {e["cle"]: e for e in episodes
               if _t(e.get("dernier")) and maintenant - _t(e["dernier"]) <= REPRISE_MAX}
    t = maintenant.isoformat(timespec="seconds")
    for s in actuels:
        if s.get("suspect"):
            continue
        e = ouverts.get(s["cle"])
        if e is None:
            e = {"cle": s["cle"], "id": s["id"], "premier": t, "cycles": 0, "sport": s.get("sport"),
                 "ligue": s.get("ligue"), "match": s.get("match"), "debut": s.get("debut"), "pari": s.get("pari"),
                 "rendement_initial": s["rendement"], "gain_100": s["gain_100"],
                 "jambes": [_compact(j) for j in s["jambes"]], "bookmakers": s["bookmakers"],
                 "verifie": bool(s.get("verifie")), "rendement_max": 0.0}
            episodes.append(e)
            ouverts[s["cle"]] = e
        e["dernier"], e["cycles"] = t, e["cycles"] + 1
        e["rendement_dernier"] = s["rendement"]
        if s["rendement"] > e["rendement_max"]:
            e["rendement_max"], e["jambes_max"] = s["rendement"], [_compact(j) for j in s["jambes"]]
    limite = maintenant - timedelta(days=GARDER_JOURS)
    episodes = [e for e in episodes if (_t(e.get("dernier")) or maintenant) >= limite]
    episodes.sort(key=lambda e: e.get("premier") or "")
    return {"episodes": episodes[-EPISODES_MAX:]}


def _jours(e: dict, maintenant: datetime) -> float:
    return (maintenant - (_t(e.get("premier")) or maintenant)).total_seconds() / 86400


def bilan(episodes: list[dict], maintenant: datetime, jours: int = 7) -> dict:
    """Ce que les surebets auraient donné sur ``jours`` jours : nombre, rendement, durée vue, gain à 100 € répartis
    pris à la première détection, par paire de bookmakers et par sport."""
    es = [e for e in episodes if _jours(e, maintenant) <= jours]
    if not es:
        return {"jours": jours, "n": 0}

    def resume(groupe: list[dict]) -> dict:
        durees = [((_t(e["dernier"]) - _t(e["premier"])).total_seconds() / 60) for e in groupe
                  if _t(e.get("dernier")) and _t(e.get("premier"))]
        return {"n": len(groupe), "gain_100": round(sum(e.get("gain_100") or 0 for e in groupe), 2),
                "rendement_median": round(median(e["rendement_initial"] for e in groupe), 4),
                "un_pour_cent": sum(e["rendement_initial"] >= SEUIL_ALERTE for e in groupe),
                "duree_mediane_min": round(median(durees), 1) if durees else None,
                "un_seul_cycle": sum(e.get("cycles") == 1 for e in groupe)}

    def par(cle_f) -> list[dict]:
        groupes: dict[str, list[dict]] = {}
        for e in es:
            groupes.setdefault(cle_f(e), []).append(e)
        return sorted(({"cle": k, **resume(g)} for k, g in groupes.items()), key=lambda x: -x["n"])[:12]

    return {"jours": jours, **resume(es), "par_bookmakers": par(lambda e: " + ".join(e.get("bookmakers") or [])),
            "par_sport": par(lambda e: e.get("sport") or "?")}


def publier(actuels: list[dict], etat: dict, maintenant: datetime, journal: dict | None = None) -> dict:
    """Document ``donnees/surebets.json`` : surebets du cycle, épisodes suivis, journal du cycle."""
    return {"maj": maintenant.isoformat(timespec="seconds"), "actuels": actuels, "journal": journal or {},
            "episodes": etat.get("episodes", [])}
