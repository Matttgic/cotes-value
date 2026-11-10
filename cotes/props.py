"""Rapprochement des paris joueurs : un book français contre une référence sharp.

Pinnacle (cote juste, marge retirée), Betfair ou Polymarket. Jamais un book français
contre un autre. Les stratégies décorées ``@figer_selecteur`` ne voient pas ces lignes :
``comparaison.comparer`` les ignore, et ``pariable`` reste faux.
"""
from __future__ import annotations

from .comparaison import ECART_MIN, _t, indexer
from .controle import contemporaines
from .joueurs import cle_joueur, est_joueur
from .marches import cle

REFERENCES = ("Pinnacle", "Betfair", "Polymarket")


def _sharp(references: dict[str, list[dict]]) -> dict[str, list[dict]]:
    out = {}
    for nom in REFERENCES:
        lignes = [l for l in (references.get(nom) or []) if est_joueur(l.get("marche"))]
        if lignes:
            out[nom] = lignes
    return out


def comparer(francais: list[dict], references: dict[str, list[dict]],
             ecart_min: float = ECART_MIN) -> list[dict]:
    """Une ligne par cote française joueur qui a la même clé chez une référence sharp.

    L'écart est ``cote × probabilité juste − 1``. ``valeur`` est vrai au seuil habituel
    (2 %). Aucune de ces lignes n'est un pari.
    """
    fr = [l for l in francais if est_joueur(l.get("marche")) and cle_joueur(l.get("joueur"))]
    refs = _sharp(references)
    if not fr or not refs:
        return []
    index = indexer(fr, refs)
    out = []
    for l in fr:
        if l.get("periode") in (None, "") or str(l.get("periode")).endswith("?") or not l.get("cote"):
            continue
        if not _t(l.get("collecte")):
            continue
        k = cle(l)
        for nom in refs:
            r = index.get(nom, {}).get(l.get("match_id"), {}).get(k)
            if not r or not contemporaines(l, r):
                continue
            if not r.get("proba_juste"):
                continue
            ecart = round(l["cote"] * r["proba_juste"] - 1, 4)
            out.append({
                "bookmaker": l.get("source"), "sport": l.get("sport"), "ligue": l.get("ligue"),
                "match_id": l.get("match_id"), "domicile": l.get("domicile"), "exterieur": l.get("exterieur"),
                "debut": l.get("debut"), "joueur": l.get("joueur"), "marche": l.get("marche"),
                "periode": l.get("periode"), "ligne": l.get("ligne"), "issue": l.get("issue"),
                "cote": l.get("cote"), "reference": nom, "cote_juste": round(1 / r["proba_juste"], 3),
                "cote_reference": r.get("cote"), "proba_juste": round(r["proba_juste"], 5),
                "ecart": ecart, "valeur": ecart >= ecart_min, "pariable": False,
                "detecte": l.get("collecte"), "lu_reference": r.get("collecte"),
                "match_reference": f'{r.get("domicile")} - {r.get("exterieur")}',
            })
    return out


def compter(lignes: list[dict]) -> dict[str, int]:
    """Nombre de lignes JOUEUR par source (pinnacle, Winamax, Unibet, …)."""
    out: dict[str, int] = {}
    for l in lignes:
        if not est_joueur(l.get("marche")):
            continue
        nom = str(l.get("source") or l.get("bookmaker") or "?")
        out[nom] = out.get(nom, 0) + 1
    return out
