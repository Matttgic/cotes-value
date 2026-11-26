"""Suivi de la CLV des values Winamax (décidé le 26/11/2026), sans aucun pari.

Winamax reste hors de la règle de prise (CLV Pinnacle négative, docs/strategie-mises.md). Pour pouvoir revoir cette
exclusion avec des données neuves, ses values qui passeraient la règle sans elle sont notées comme le serait un pari
(``simulation.placer`` : une par référence et cote, à la première détection, lectures de moins de 5 min), puis leur
clôture est lue comme celle d'un pari (``simulation.suivre_cloture``). Aucune mise, aucun règlement, aucun bilan des
paris : une mesure, dans ``donnees/winamax_suivi.json``.

Mesure : CLV contre la clôture Pinnacle lue dans les 30 min avant le match, une par cote française (la première
détection, comme la règle), moyenne et erreur type par match (``protocole.moyenne_par_match``).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import simulation
from .protocole import moyenne_par_match

FICHIER = "winamax_suivi.json"
DEBUT = "2026-11-26"
BOOKMAKER = "Winamax"
REVOIR_LE = "2026-12-05"
Z95 = 1.96
CLOS_APRES_H = 1        # plus de lecture de clôture une heure après le coup d'envoi
CHAMPS = ("id", "reference", "detecte", "bookmaker", "sport", "ligue", "match_id", "domicile", "exterieur", "debut",
          "marche", "periode", "ligne", "issue", "joueur", "pari", "cote", "cote_juste", "ecart", "statut",
          "cote_juste_cloture", "clv", "cloture_lue", "clv_minimum", "cote_juste_cloture_pinnacle",
          "cloture_pinnacle_lue", "age_cote_prise_s", "ecart_minimum", "prix_prudent")


def _alleger(p: dict) -> dict:
    return {k: p[k] for k in CHAMPS if p.get(k) is not None}


def noter(suivi: list[dict], opportunites: list[dict], decision: datetime | None = None) -> list[dict]:
    """Ajoute à ``suivi`` les nouvelles values Winamax dans la règle (sans l'exclusion du bookmaker) ; les renvoie.
    ``decision`` : l'heure réelle par défaut, comme pour les paris."""
    winamax = [o for o in opportunites or [] if isinstance(o, dict) and o.get("bookmaker") == BOOKMAKER]
    nouveaux = [_alleger(p) for p in simulation.placer(winamax, list(suivi), decision,
                                                       sans_exclusion_bookmaker=True)]
    suivi.extend(nouveaux)
    return nouveaux


def suivre(suivi: list[dict], justes: dict, maintenant: datetime | None = None, prudentes: set | None = None) -> int:
    """Clôtures lues comme celles des paris ; une entrée est close une heure après le coup d'envoi. Renvoie le
    nombre d'entrées closes à ce passage."""
    maintenant = maintenant or datetime.now(timezone.utc)
    simulation.suivre_cloture(suivi, justes, maintenant, prudentes=prudentes)
    closes = 0
    for p in suivi:
        debut = simulation._heure(p.get("debut"))
        if p.get("statut") == "en_cours" and debut and debut.tzinfo and maintenant > debut + timedelta(hours=CLOS_APRES_H):
            p["statut"] = "clos"
            closes += 1
    return closes


def clv(p: dict) -> float | None:
    """CLV contre la clôture Pinnacle lue dans les 30 min avant le match, ou None : celle de la référence si c'est
    Pinnacle, sinon la clôture Pinnacle lue sur l'entrée (même fenêtre que ``simulation.clv_finale``)."""
    if p.get("reference") == "Pinnacle":
        juste, lue = p.get("cote_juste_cloture"), p.get("cloture_lue")
    else:
        juste, lue = p.get("cote_juste_cloture_pinnacle"), p.get("cloture_pinnacle_lue")
    t, debut = simulation._heure(lue), simulation._heure(p.get("debut"))
    if not juste or not p.get("cote") or not t or not debut or not t.tzinfo or not debut.tzinfo:
        return None
    if not 0 < (debut - t).total_seconds() <= simulation.CLOTURE_MAX_MIN * 60:
        return None
    return p["cote"] / juste - 1


def bilan(suivi: list[dict]) -> dict:
    """CLV Pinnacle des values closes, une par cote française (première détection), avec son intervalle à 95 %."""
    clos = [p for p in suivi if isinstance(p, dict) and p.get("statut") == "clos"]
    premiers = simulation.premiers_par_selection(clos)
    mesures = [(c, p["match_id"]) for p in clos if id(p) in premiers and (c := clv(p)) is not None]
    out = {"bookmaker": BOOKMAKER, "depuis": DEBUT, "revoir_le": REVOIR_LE, "notees": len(suivi),
           "en_cours": sum(p.get("statut") == "en_cours" for p in suivi if isinstance(p, dict)),
           "closes": len(clos), "n": len(mesures), "matchs": 0, "moyenne": None, "ic95": None, "p": None}
    if mesures:
        m = moyenne_par_match([c for c, _ in mesures], [k for _, k in mesures])
        out.update(matchs=m["matchs"], moyenne=round(m["moyenne"], 5), p=m["p"])
        if m["erreur_type"] is not None:
            out["ic95"] = [round(m["moyenne"] - Z95 * m["erreur_type"], 5),
                           round(m["moyenne"] + Z95 * m["erreur_type"], 5)]
    return out
