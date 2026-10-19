"""Jules v2 reconstruite : paramètres de Jules, sélection causale et identité liée.

Le protocole est dans docs/protocole-jules-v2.md. La v1 reste inchangée.
"""
from __future__ import annotations

from .decisions import figer_selecteur

from collections import Counter
from datetime import timezone

from .correspondance import avec_marqueurs_ligue, normaliser
from .strategie_jules import PARIS, _heure
from .strategie_commune import (nombre_fini as _nombre, preuve_de, correspondance_prouvee,
                               edge_coherent, ligne_non_quart, issue_valide)

JULES_V2 = {
    "nom": "JULES EDGE v2", "version": "2-reconstruite",
    "debut": "2026-10-14T22:30:00+00:00",
    "references": ("Pinnacle", "Betfair", "Polymarket"),
    "bookmakers": ("Winamax", "Betclic", "Unibet", "PMU"),
    "sports": ("football", "basket", "hockey", "baseball", "rugby", "handball",
               "football_americain", "tennis", "volley"),
    "marches": ("RESULTAT_1N2", "VAINQUEUR", "TOTAL", "HANDICAP"),
    "cote_min": 1.30, "cote_max": 2.80, "edge_min": .025, "edge_max": .12,
    "avance_min_minutes": 15, "avance_max_h": 18, "fraicheur_max_minutes": 5,
    "ressemblance_min": .85, "paris_max_jour": 8, "mise": 10.0,
}


def _correspondance(p):
    return (p.get("reference") in JULES_V2["references"]
            and p.get("bookmaker") in JULES_V2["bookmakers"]
            and p.get("sport") in JULES_V2["sports"] and not p.get("suspect")
            and _heure(p.get("detecte")) is not None and _heure(p.get("debut")) is not None
            and correspondance_prouvee(p, JULES_V2["ressemblance_min"]))


def motif_refus_jules_v2(p, depuis=JULES_V2["debut"]):
    """Ne lit ni statut, ni gain, ni résultat, ni CLV."""
    if not _correspondance(p):
        return "correspondance, source ou périmètre non validé"
    t, d, lu = (_heure(p.get(k)) for k in ("detecte", "debut", "lu_reference"))
    lancement = _heure(depuis)
    if not lancement or t < lancement:
        return "détection antérieure au lancement"
    if not JULES_V2["avance_min_minutes"]*60 <= (d-t).total_seconds() <= JULES_V2["avance_max_h"]*3600:
        return "détection hors fenêtre de 15 minutes à 18 heures"
    if not lu or abs((t-lu).total_seconds()) > JULES_V2["fraicheur_max_minutes"]*60:
        return "référence absente ou éloignée"
    cote, juste, edge = (_nombre(p.get(k)) for k in ("cote", "cote_juste", "ecart"))
    if (cote is None or juste is None or edge is None or juste <= 1
            or not JULES_V2["cote_min"] <= cote <= JULES_V2["cote_max"]
            or not JULES_V2["edge_min"] <= edge <= JULES_V2["edge_max"]
            or not edge_coherent(cote, juste, edge)):
        return "cote ou edge incohérent / hors bornes"
    marche, periode = p.get("marche"), p.get("periode")
    if marche not in JULES_V2["marches"] or periode not in ("MATCH", "TEMPS_REG"):
        return "marché ou période hors périmètre"
    if p["sport"] in ("tennis", "volley") and (marche != "VAINQUEUR" or periode != "MATCH"):
        return "tennis et volley : vainqueur du match seulement"
    if marche in ("TOTAL", "HANDICAP"):
        ligne = _nombre(p.get("ligne"))
        if not ligne_non_quart(ligne):
            return "ligne absente ou fractionnée en quarts"
    if not issue_valide(marche, p.get("issue")):
        return "issue invalide"
    return None


def _cles(p):
    sport = p.get("sport")
    reference = preuve_de(p).get("match_id_reference")
    cles = [("reference", sport, p.get("reference"), str(reference))] if reference else []
    if p.get("match_id"):
        cles.append(("bookmaker", sport, p["bookmaker"], str(p["match_id"])))
    ligue = p.get("ligue") if isinstance(p.get("ligue"), str) else None
    noms = [avec_marqueurs_ligue(p.get(k) if isinstance(p.get(k), str) else None, ligue) or ""
            for k in ("domicile", "exterieur")]
    debut = _heure(p.get("debut"))
    normes = [normaliser(n) for n in noms]
    feminin = any(n[1] for n in normes)
    jeunes = set().union(*(n[2] for n in normes))
    paires = [noms]
    ref = p.get("match_reference") if isinstance(p.get("match_reference"), str) else ""
    if ref.count(" - ") == 1:
        paires.append(ref.split(" - "))
    for paire in paires:
        normalises = []
        for n in paire:
            mots, fem, categorie = normaliser(n)
            normalises.append((mots, fem or feminin, tuple(sorted(categorie or jeunes))))
        if debut and all(n[0] for n in normalises):
            cles.append(("equipes", sport, debut.astimezone(timezone.utc), tuple(sorted(normalises))))
    return cles


def analyser_jules_v2(paris, depuis=JULES_V2["debut"]):
    """Les liens sont appris à la détection, y compris sur une cote écartée.

    Une fusion tardive de deux groupes déjà sélectionnés est signalée. Elle ne
    supprime jamais rétroactivement une mise. Les alias inconnus restent une limite.
    """
    paris = list(paris)
    lignes = sorted((p for p in paris if _correspondance(p)), key=lambda p: (
        _heure(p["detecte"]), -(_nombre(p.get("ecart")) or 0), -(_nombre(p.get("cote")) or 0),
        p["bookmaker"], str(p.get("id") or p.get("match_id") or "")))
    parents, prises, selection, jours = {}, {}, set(), Counter()
    refus, doublons, plafond, fusions_tardives = Counter(), 0, 0, 0

    def racine(cle):
        parents.setdefault(cle, cle)
        # Compression itérative : pas de limite de récursion sur de longs alias.
        r = cle
        while parents[r] != r:
            r = parents[r]
        while parents[cle] != cle:
            suivant = parents[cle]
            parents[cle] = r
            cle = suivant
        return r

    for p in lignes:
        cles = _cles(p)
        root = racine(cles[0])
        for cle in cles[1:]:
            autre = racine(cle)
            if autre != root:
                a, b = prises.get(root, 0), prises.get(autre, 0)
                if a and b:
                    fusions_tardives += 1
                parents[autre] = root
                prises[root] = a+b
        motif = motif_refus_jules_v2(p, depuis)
        if motif:
            refus[motif] += 1
            continue
        jour = _heure(p["detecte"]).astimezone(PARIS).date().isoformat()
        if prises.get(root):
            doublons += 1
        elif jours[jour] >= JULES_V2["paris_max_jour"]:
            plafond += 1
        else:
            prises[root] = 1
            jours[jour] += 1
            selection.add(id(p))
    return {"selection": selection, "lignes_examinees": len(paris),
            "hors_correspondance": len(paris) - len(lignes), "doublons_ecartes": doublons, "plafond_ecartes": plafond,
            "fusions_tardives": fusions_tardives, "par_jour": dict(jours), "refus": dict(refus)}


@figer_selecteur("jules_v2")
def paris_jules_v2(paris, depuis=JULES_V2["debut"]):
    return analyser_jules_v2(paris, depuis)["selection"]


def diagnostic_jules_v2(paris, depuis=JULES_V2["debut"]):
    """Diagnostic JSON d'un rejeu des règles, sans écriture ni résultat futur lu.

    Les décisions prospectives font foi via paris_jules_v2() et le registre.
    Ce rejeu peut différer de celles-ci si les données d'entrée ont été corrigées.
    """
    resultat = analyser_jules_v2(paris, depuis)
    return {"mode": "rejeu_diagnostic", "strategie": "jules_v2", "version": JULES_V2["version"],
            "depuis": depuis, "selectionnes": len(resultat["selection"]),
            **{k: v for k, v in resultat.items() if k != "selection"}}
