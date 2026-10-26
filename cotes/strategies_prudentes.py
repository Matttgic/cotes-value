"""Variantes de simulation figées après les audits des 15 et 17 octobre.

Elles ne participent jamais aux votes des stratégies de base. La sélection ne
consulte ni résultat, ni gain, ni CLV. Protocole : docs/variantes-prudentes.md.
"""
from __future__ import annotations

from collections import Counter
from itertools import groupby
from math import isfinite
from zoneinfo import ZoneInfo

from .decisions import appliquer
from .strategie_m3_structure import M3_STRUCTURE, paris_m3_structure
from .strategie_qwen import QWEN, paris_qwen
from .strategie_coeur import COEUR, paris_coeur
from .strategie_liquidite import LIQUIDITE, paris_liquidite
from .strategie_grok import GROKS, GROKS_V2, GROKS_V3, paris_grok
from .strategie_conseil import CONSEILS, paris_conseil
from .convergence import STRATEGIES, selections, votes
from .laboratoire import heure
from .simulation import REFERENCES, paris_strategie
from .strategie_jules_v2 import _cles

DEBUT_VARIANTES = "2026-10-15T04:00:00+00:00"  # 06 h à Paris, avant toute prise officielle
CLAUDE_PRUDENT = {
    "cle": "claude_prudent", "nom": "Claude 1/match · max 10/j", "court": "Claude 1/match",
    "debut": DEBUT_VARIANTES, "version": "1", "mise": 10, "maximum_jour": 10,
    "regles": "Critères Claude · première prise par match · max 10/j · mise fictive 10 €",
}
CONVERGENCE_3 = {
    "cle": "convergence_3", "nom": "Convergence ≥ 3 hors M3", "court": "Conv. ≥3 hors M3",
    "debut": DEBUT_VARIANTES, "version": "1", "mise": 10,
    "regles": "≥3 familles parmi Claude, ChatGPT, Gemini, Jules · 1 pari/match · mise fictive 10 €",
}
VARIANTES = (CLAUDE_PRUDENT, CONVERGENCE_3, M3_STRUCTURE, QWEN, COEUR, LIQUIDITE, *GROKS, *GROKS_V2, *GROKS_V3, *CONSEILS)
PARIS = ZoneInfo("Europe/Paris")


def _cles_match(p: dict) -> list[tuple]:
    """Liens vérifiés connus à cette détection, sans rapprochement flou ajouté.

    L'ID du bookmaker reste disponible si la preuve de référence manque. Les
    alias sont liés avec un score ≥0,85 ; les IDs fournisseurs exigent aussi un
    contrôle conforme. Un marché refusé peut néanmoins apprendre un alias.
    Les catégories et le caractère féminin restent dans les clés normalisées.
    """
    if not p.get("match_id"):
        return [("ligne", p.get("id") or id(p))]
    out = [("bookmaker", p.get("sport"), p.get("bookmaker"), p["match_id"])]
    preuve = p.get("preuve_prise") or {}
    score = preuve.get("ressemblance_noms")
    if (isinstance(score, bool) or not isinstance(score, (int, float)) or not isfinite(score)
            or score < .85):
        return out
    try:
        for cle in _cles(p):
            if cle[0] == "equipes" or (cle[0] == "reference"
                    and (preuve.get("controle") or {}).get("statut") == "conforme"):
                out.append(cle)
    except (KeyError, TypeError, ValueError):
        pass
    return out


def _signature_selection(p: dict) -> tuple:
    """Sélection exacte : marché (type, période, ligne, joueur) et issue.

    Le match n'est pas dans cette signature : il vient de l'alias déjà appris.
    Le bookmaker n'y est pas : deux passages, ou deux books, du même choix ne
    comptent qu'une fois.
    """
    return (p.get("marche"), p.get("periode"), p.get("ligne"), p.get("joueur"), p.get("issue"))


def _selection_par_selection(paris: list[dict], eligibles: set[int], depuis: str) -> dict:
    """Première prise par sélection, sans plafond journalier.

    Même apprentissage d'alias que ``selection_unique`` : deux bookmakers du même
    match partagent la sélection. Une fusion tardive est comptée et ne retire
    jamais une mise déjà retenue. Les autres marchés du match restent jouables.
    """
    depart = heure(depuis)
    if depart is None:
        return {"selection": set(), "fusions_tardives": 0, "par_jour": {}}
    lignes = sorted((p for p in paris if p.get("reference") != "Pinnacle brut"
                     and heure(p.get("detecte"))), key=lambda p: heure(p["detecte"]))
    parents, vues, jours, retenus = {}, {}, Counter(), set()
    fusions = 0

    def racine(cle):
        parents.setdefault(cle, cle)
        r = cle
        while parents[r] != r:
            r = parents[r]
        while parents[cle] != cle:
            prochain = parents[cle]
            parents[cle] = r
            cle = prochain
        return r

    for t, batch in groupby(lignes, key=lambda p: heure(p["detecte"])):
        batch = list(batch)
        for p in batch:
            cles = _cles_match(p)
            root = racine(cles[0])
            for cle in cles[1:]:
                autre = racine(cle)
                if root != autre:
                    a, b = vues.get(root), vues.get(autre)
                    fusions += bool(a and b)
                    parents[autre] = root
                    if b:
                        vues[root] = (a or set()) | b
                        del vues[autre]
        if t < depart:
            continue
        candidats = sorted((p for p in batch if id(p) in eligibles),
                            key=lambda p: (-(p.get("ecart") or 0), str(p.get("id") or "")))
        jour = t.astimezone(PARIS).date().isoformat()
        for p in candidats:
            root = racine(_cles_match(p)[0])
            sig = _signature_selection(p)
            deja = vues.setdefault(root, set())
            if sig in deja:
                continue
            deja.add(sig)
            retenus.add(id(p))
            jours[jour] += 1
    return {"selection": retenus, "fusions_tardives": fusions, "par_jour": dict(jours)}


def selection_unique(paris: list[dict], eligibles: set[int], depuis: str,
                     maximum_jour: int | None = None, *, portee: str = "match") -> dict:
    """Première prise par événement ; edge départage seulement les prises simultanées.

    ``portee="match"`` (défaut, toutes les stratégies déjà lancées) : une mise par
    match, puis le plafond journalier. ``portee="selection"`` : une mise par
    sélection exacte, sans plafond. Les alias sont appris sur toutes les
    observations, y compris avant lancement et sur les prix écartés. Une fusion
    tardive est comptée et ne retire jamais une mise passée. Un match non
    identifiable reste une limite des données.
    """
    if portee == "selection":
        return _selection_par_selection(paris, eligibles, depuis)
    if portee != "match":
        raise ValueError("portée de dédoublonnage inconnue")
    depart = heure(depuis)
    if depart is None:
        return {"selection": set(), "fusions_tardives": 0, "par_jour": {}}
    lignes = sorted((p for p in paris if p.get("reference") != "Pinnacle brut"
                     and heure(p.get("detecte"))), key=lambda p: heure(p["detecte"]))
    parents, prises, rencontres, jours, retenus = {}, {}, {}, Counter(), set()
    fusions = 0

    def racine(cle):
        parents.setdefault(cle, cle)
        r = cle
        while parents[r] != r:
            r = parents[r]
        while parents[cle] != cle:
            prochain = parents[cle]
            parents[cle] = r
            cle = prochain
        return r

    for t, batch in groupby(lignes, key=lambda p: heure(p["detecte"])):
        batch = list(batch)
        # Toutes les références d'un même cycle sont disponibles simultanément.
        for p in batch:
            cles = _cles_match(p)
            root = racine(cles[0])
            for cle in cles[1:]:
                autre = racine(cle)
                if root != autre:
                    a, b = prises.get(root, 0), prises.get(autre, 0)
                    fusions += bool(a and b)
                    parents[autre] = root
                    prises[root] = a+b
                    rencontres[root] = rencontres.get(root, False) or rencontres.get(autre, False)
        if t < depart:
            continue
        candidats = sorted((p for p in batch if id(p) in eligibles),
                            key=lambda p: (-(p.get("ecart") or 0), str(p.get("id") or "")))
        jour = t.astimezone(PARIS).date().isoformat()
        for p in candidats:
            root = racine(_cles_match(p)[0])
            if rencontres.get(root):
                continue
            # La première occasion consomme l'événement, même si le plafond
            # impose l'abstention. Pas de seconde chance sur une prise ultérieure.
            rencontres[root] = True
            if maximum_jour is not None and jours[jour] >= maximum_jour:
                continue
            retenus.add(id(p))
            prises[root] = 1
            jours[jour] += 1
    return {"selection": retenus, "fusions_tardives": fusions, "par_jour": dict(jours)}


def selections_prudentes(paris: list[dict], depuis: str | None = None,
                         bases: dict[str, set[int]] | None = None) -> dict[str, set[int]]:
    depart = depuis or DEBUT_VARIANTES
    # Le lancement de cette variante remplace seulement le début de la variante
    # Claude. Les votes de convergence restent ceux des moteurs officiels, avec
    # leurs propres dates, plafonds et dédoublonnages (sauf rejeu explicite).
    claude = bases.get("strategie") if depuis is not None and bases is not None else None
    if claude is None:
        claude = paris_strategie(paris, depuis=depart)
    prudent = selection_unique(paris, claude, depart, CLAUDE_PRUDENT["maximum_jour"])["selection"]
    bases = bases if bases is not None else selections(paris, depuis=depuis)
    # Eden ne rejoint pas cette variante : le texte figé ne nomme que Claude,
    # ChatGPT, Gemini et Jules. L'y ajouter changerait une règle déjà lancée.
    familles = {cle for cle, famille, *_ in STRATEGIES if famille not in ("m3", "eden")}
    retenus = {cle: ids for cle, ids in bases.items() if cle in familles}
    ordre = {ref: i for i, ref in enumerate(REFERENCES)}
    candidats = set()
    for (_, t, _), groupe in votes(paris, retenus).items():
        if t < heure(depart) or len(groupe["familles"]) < 3:
            continue
        p = min(groupe["paris"], key=lambda p: (ordre.get(p.get("reference"), 99), str(p.get("id") or "")))
        candidats.add(id(p))
    convergence = selection_unique(paris, candidats, depart)["selection"]
    resultat = {"claude_prudent": prudent, "convergence_3": convergence}
    if depuis is None:
        resultat = {cle: appliquer(paris, ids, cle) for cle, ids in resultat.items()}
    resultat["m3_structure"] = paris_m3_structure(paris) if depuis is None else set()
    resultat["qwen_persistence"] = paris_qwen(paris, depuis)
    resultat["coeur_value"] = appliquer(paris, paris_coeur(paris, depuis), "coeur_value") if depuis is None else set()
    resultat["liquidite_sure"] = appliquer(paris, paris_liquidite(paris, depuis), "liquidite_sure") if depuis is None else set()
    for g in GROKS:
        resultat[g["cle"]] = appliquer(paris, paris_grok(paris, g), g["cle"]) if depuis is None else set()
    for g in GROKS_V2:
        resultat[g["cle"]] = appliquer(paris, paris_grok(paris, g), g["cle"]) if depuis is None else set()
    for g in GROKS_V3:
        resultat[g["cle"]] = appliquer(paris, paris_grok(paris, g), g["cle"]) if depuis is None else set()
    for c in CONSEILS:
        resultat[c["cle"]] = appliquer(paris, paris_conseil(paris, c), c["cle"]) if depuis is None else set()
    return resultat


def suivis_prudents(paris: list[dict], maintenant: str) -> dict:
    """Export commun, sans réécrire les statistiques historiques ni antidater les règles."""
    from .laboratoire import DEBUT_SUIVI, resume
    fin = heure(maintenant)
    observes = [p for p in paris if heure(p.get("detecte")) and heure(p["detecte"]) < fin]
    officiel = selections_prudentes(observes)
    rejoue = selections_prudentes(observes, depuis=DEBUT_SUIVI)
    def lignes(selection, reconstitution=False):
        return {v["cle"]: {"nom": v["nom"], "ids": [p["id"] for p in observes if id(p) in selection[v["cle"]]],
                           "debut": v["debut"], "stats": resume([p for p in observes if id(p) in selection[v["cle"]]],
                                           maintenant, incertitude=False)} for v in VARIANTES
                if not (reconstitution and v.get("prospectif_seulement"))}
    return {"debut_prospectif": DEBUT_VARIANTES, "officiel": lignes(officiel),
            "reconstitution_depuis": DEBUT_SUIVI, "reconstitution_exploratoire": lignes(rejoue, reconstitution=True)}
