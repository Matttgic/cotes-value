"""M3 : strategie descriptive optimisee a posteriori sur le releve du 14/10/2026.

Selection uniquement sur des informations disponibles a la detection.
Le rejeu du 7-13 octobre ne prouve pas une rentabilite future.
La selection prospective commence le 15/10/2026 (heure de Paris).

Variante prospective « M3 · Max 3/match » (M3_STRUCTURE, paris_m3_structure) : trois familles de marchés par
événement, aucune substitution d'une prise passée.
"""
from __future__ import annotations

from .decisions import appliquer, figer_selecteur

from datetime import datetime
from itertools import groupby
from math import isfinite
from .laboratoire import heure
from .temps import instant

M3 = {
    "nom": "M3 · MultiSport Value",
    "version": "1",
    "debut": "2026-10-14T22:00:00+00:00",
    "references": ("Pinnacle", "Betfair", "Polymarket"),
    "bookmakers": ("Winamax", "Betclic", "Unibet", "PMU"),
    "sports": ("basket", "baseball", "handball"),
    "marches": ("VAINQUEUR", "HANDICAP", "TOTAL", "TOTAL_EXT"),
    "cote_min": 1.30,
    "cote_max": 3.0,
    "edge_min": 0.02,
    "edge_max": 0.12,
    "avance_max_h": 36,
    "fraicheur_max_minutes": 15,
    "mise": 10.0,
}


def _heure(s) -> datetime | None:
    return instant(s)


def _nombre(v) -> float | None:
    if isinstance(v, bool):
        return None
    try:
        n = float(v)
        return n if isfinite(n) else None
    except (ValueError, TypeError):
        return None


def motif_refus_m3(p: dict, depuis: str | None = None) -> str | None:
    """Ne lit jamais statut, gain, CLV ou resultat pour choisir un pari."""
    if p.get("reference") not in M3["references"] or p.get("bookmaker") not in M3["bookmakers"]:
        return "reference ou bookmaker hors perimetre"
    if p.get("sport") not in M3["sports"] or p.get("marche") not in M3["marches"]:
        return "sport ou marche hors perimetre"
    if p.get("periode") != "MATCH" or p.get("suspect"):
        return "periode ou correspondance suspecte"
    t, d, lu, depart = (_heure(p.get("detecte")), _heure(p.get("debut")),
                        _heure(p.get("lu_reference")), _heure(depuis or M3["debut"]))
    if not t or not d or not lu or not depart or t < depart:
        return "date invalide ou detection avant lancement"
    if not (0 < (d-t).total_seconds() <= 3600 * M3["avance_max_h"]):
        return "match trop lointain ou deja commence"
    if not (abs((t-lu).total_seconds()) <= 60 * M3["fraicheur_max_minutes"]):
        return "reference trop ancienne"
    cote, juste, edge = (_nombre(p.get(k)) for k in ("cote", "cote_juste", "ecart"))
    if (cote is None or juste is None or edge is None or juste <= 1
            or not M3["cote_min"] <= cote <= M3["cote_max"]
            or not M3["edge_min"] <= edge <= M3["edge_max"]
            or abs(cote / juste - 1 - edge) > 0.002):
        return "cote ou edge hors bornes / incoherent"
    preuve = p.get("preuve_prise") or {}
    if not preuve.get("match_id_reference") or (preuve.get("controle") or {}).get("statut") != "conforme":
        return "preuve du match ou du marche non conforme"
    if p.get("marche") in ("TOTAL", "TOTAL_EXT", "HANDICAP"):
        ligne = _nombre(p.get("ligne"))
        if ligne is None or not (ligne * 2).is_integer():
            return "ligne absente ou fractionnee"
    issues = {
        "VAINQUEUR": ("DOM", "EXT"),
        "HANDICAP": ("DOM", "EXT"),
        "TOTAL": ("PLUS", "MOINS"),
        "TOTAL_EXT": ("PLUS", "MOINS"),
    }
    if p.get("issue") not in issues[p["marche"]]:
        return "issue hors perimetre"
    return None


@figer_selecteur("m3")
def paris_m3(paris: list[dict], depuis: str | None = None) -> set[int]:
    """Une mise fictive par selection/bookmaker, premier prix disponible.

    Les paris d'un meme match peuvent rester correles s'ils portent sur
    differents marches. Ne pas interpreter la serie comme 100% independante.
    """
    lignes = [p for p in paris if motif_refus_m3(p, depuis) is None]
    lignes.sort(key=lambda p: (_heure(p["detecte"]), -float(p["ecart"]),
                               str(p.get("bookmaker") or ""), str(p.get("id") or "")))
    deja, out = set(), set()
    for p in lignes:
        cle = tuple(p.get(k) for k in
                    ("match_id", "marche", "periode", "ligne", "issue", "joueur"))
        if cle in deja:
            continue
        deja.add(cle)
        out.add(id(p))
    return out


# --------------------------------------------------------------------------- variante « M3 · Max 3/match »

M3_STRUCTURE = {
    'cle': 'm3_structure', 'nom': 'M3 · Max 3/match', 'court': 'M3 Max 3',
    'debut': '2026-10-17T01:00:00+00:00',  # 03 h Paris, lancement annoncé avant les prises
    'version': '1', 'mise': 10, 'prospectif_seulement': True,
    'regles': 'Critères M3 · 1 vainqueur + 1 handicap + 1 total (match ou équipe) · max 30 €/événement · meilleur edge du lot disponible',
}


def famille_marche(p):
    return {'VAINQUEUR':'vainqueur','HANDICAP':'handicap','TOTAL':'total','TOTAL_EXT':'total'}.get(p.get('marche'))


def paris_m3_structure(paris, depuis=None):
    # Cette variante n'a pas de bilan rétrospectif officiel.
    from .strategies_prudentes import _cles_match  # import local : évite le cycle
    depart = heure(M3_STRUCTURE['debut'])
    eligibles = {id(p) for p in paris if motif_refus_m3(p) is None}
    parents, utilises, selection = {}, {}, set()
    def racine(c):
        parents.setdefault(c,c)
        r=c
        while parents[r]!=r:
            r=parents[r]
        while parents[c]!=c:
            suivant=parents[c];parents[c]=r;c=suivant
        return r
    def instant(p):
        return heure(p.get('lot_decision') or p.get('decide_le') or p.get('detecte'))
    rows=sorted((p for p in paris if p.get('reference')!='Pinnacle brut' and instant(p)),key=instant)
    for t, batch in groupby(rows,key=instant):
        batch=list(batch)
        for p in batch:
            cles=_cles_match(p); root=racine(cles[0])
            for cle in cles[1:]:
                autre=racine(cle)
                if autre!=root:
                    parents[autre]=root
                    utilises.setdefault(root,set()).update(utilises.get(autre,set()))
        if t<depart:
            continue
        # Les décisions déjà prises occupent leur famille, même après fusion
        # tardive d'alias. Une fusion ne supprime jamais une prise antérieure.
        for p in batch:
            if M3_STRUCTURE['cle'] in p.get('selections_figees',{}):
                utilises.setdefault(racine(_cles_match(p)[0]),set()).add(famille_marche(p))
                selection.add(id(p))
        for p in sorted(batch,key=lambda p:(-(p.get('ecart') or 0),str(p.get('id') or ''))):
            if 'selections_figees' in p or id(p) not in eligibles:
                continue
            famille=famille_marche(p);root=racine(_cles_match(p)[0])
            if famille and famille not in utilises.get(root,set()):
                utilises.setdefault(root,set()).add(famille);selection.add(id(p))
    return appliquer(paris,selection,M3_STRUCTURE['cle'])
