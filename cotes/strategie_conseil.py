"""Stratégies du conseil : règles décrites par un dictionnaire, moteur commun, suivi prospectif seulement.

Les règles sont proposées par plusieurs « conseillers » (angles différents), relues entre elles de façon
anonyme, puis retenues par une synthèse. Elles sont construites et validées sur l'historique, puis confirmées
sur une fenêtre de test qu'aucun conseiller n'a vue (docs/strategie-conseil.md). Seul le suivi à partir de
``debut`` compte : le rejeu sur le passé est optimiste et ne prouve rien.

Le moteur ne lit que des informations connues à la détection. Il ne consulte jamais statut, gain, CLV ni
cote de clôture. Une règle peut exiger qu'un ou plusieurs autres bookmakers français aient montré le même
écart avant ou au même instant (``convergence_min``) : seules les prises déjà enregistrées comptent.
"""
from __future__ import annotations

from .correspondance import normaliser
from .laboratoire import heure
from .strategie_commune import correspondance_prouvee, edge_coherent, ligne_non_quart, nombre_fini

ISSUES = {
    "RESULTAT_1N2": ("DOM", "EXT", "NUL"),
    "VAINQUEUR": ("DOM", "EXT"),
    "HANDICAP": ("DOM", "EXT"),
    "DRAW_NO_BET": ("DOM", "EXT"),
    "DOUBLE_CHANCE": ("HOME_DRAW", "HOME_AWAY", "DRAW_AWAY"),
    "TOTAL": ("PLUS", "MOINS"),
    "TOTAL_DOM": ("PLUS", "MOINS"),
    "TOTAL_EXT": ("PLUS", "MOINS"),
}
LIGNES = ("TOTAL", "HANDICAP", "TOTAL_DOM", "TOTAL_EXT")
DEFAUTS = {
    "periodes": ("MATCH", "TEMPS_REG"), "avance_min_minutes": 15, "avance_max_h": 36, "fraicheur_max_minutes": 15,
    "ressemblance_min": 0.85, "exclure_jeunes": True, "exclure_feminin": False, "maximum_jour": None,
}


def _r(regle: dict, cle: str):
    return regle.get(cle, DEFAUTS.get(cle))


def _selection_cle(p: dict) -> tuple:
    """Même sélection vue par plusieurs bookmakers : match de la référence, marché, période, ligne, issue."""
    preuve = p.get("preuve_prise") if isinstance(p.get("preuve_prise"), dict) else {}
    return (p.get("reference"), str(preuve.get("match_id_reference") or ""), p.get("marche"), p.get("periode"),
            p.get("ligne"), p.get("issue"))


def index_convergence(paris: list[dict]) -> dict[int, int]:
    """id(pari) -> nombre de bookmakers français distincts ayant vu le même écart à cet instant ou avant."""
    vus: dict[tuple, dict[str, object]] = {}
    for p in paris:
        t = heure(p.get("detecte"))
        if t is None or not _selection_cle(p)[1]:
            continue
        premiers = vus.setdefault(_selection_cle(p), {})
        b = p.get("bookmaker")
        if b not in premiers or t < premiers[b]:
            premiers[b] = t
    out = {}
    for p in paris:
        t = heure(p.get("detecte"))
        premiers = vus.get(_selection_cle(p)) if t else None
        out[id(p)] = sum(1 for d in premiers.values() if d <= t) if premiers else 0
    return out


def motif_refus(p: dict, regle: dict, convergence: dict[int, int] | None = None) -> str | None:
    """Raison du refus, ou None si le pari entre dans la règle. Uniquement des données de la détection."""
    if p.get("reference") not in regle["references"]:
        return "référence hors périmètre"
    if p.get("bookmaker") not in regle["bookmakers"] or p.get("sport") not in regle["sports"]:
        return "bookmaker ou sport hors périmètre"
    if p.get("suspect"):
        return "opportunité suspecte"
    marche, periode = p.get("marche"), p.get("periode")
    if marche not in regle["marches"] or periode not in _r(regle, "periodes"):
        return "marché ou période hors périmètre"
    if p.get("sport") in ("tennis", "volley") and (marche != "VAINQUEUR" or periode != "MATCH"):
        return "tennis et volley : vainqueur du match uniquement"
    if p.get("issue") not in ISSUES.get(marche, ()) or p.get("issue") not in regle.get("issues", ISSUES[marche]):
        return "issue hors périmètre"
    if marche in LIGNES and not ligne_non_quart(p.get("ligne")):
        return "ligne absente ou en quarts"
    t, debut, lu = heure(p.get("detecte")), heure(p.get("debut")), heure(p.get("lu_reference"))
    if not t or not debut or not lu:
        return "date absente ou invalide"
    avance = (debut - t).total_seconds()
    if not _r(regle, "avance_min_minutes") * 60 <= avance <= _r(regle, "avance_max_h") * 3600:
        return "détection hors fenêtre avant le match"
    if abs((t - lu).total_seconds()) > _r(regle, "fraicheur_max_minutes") * 60:
        return "référence trop ancienne"
    cote, juste, edge = (nombre_fini(p.get(k)) for k in ("cote", "cote_juste", "ecart"))
    if cote is None or not regle["cote_min"] <= cote <= regle["cote_max"]:
        return "cote hors intervalle"
    if edge is None or not regle["edge_min"] <= edge <= regle["edge_max"]:
        return "écart hors intervalle"
    if not edge_coherent(cote, juste, edge):
        return "écart incohérent avec la cote juste"
    if not correspondance_prouvee(p, _r(regle, "ressemblance_min")):
        return "preuve de correspondance insuffisante"
    equipes = [normaliser(str(p.get(k) or "")) for k in ("domicile", "exterieur")]
    if _r(regle, "exclure_jeunes") and any(n[2] for n in equipes):
        return "jeunes ou réserve"
    if _r(regle, "exclure_feminin") and any(n[1] for n in equipes):
        return "match féminin exclu"
    if regle.get("accord_polymarket_min") is not None:
        accord = nombre_fini(p.get("ecart_polymarket"))
        if accord is None or accord < regle["accord_polymarket_min"]:
            return "Polymarket ne confirme pas l'écart"
    if regle.get("convergence_min"):
        if convergence is None or convergence.get(id(p), 0) < regle["convergence_min"]:
            return "pas assez de bookmakers sur le même écart"
    return None


def paris_conseil(paris: list[dict], regle: dict, depuis: str | None = None) -> set[int]:
    """Première prise admissible par événement, depuis ``debut`` (ou ``depuis`` pour un rejeu explicite)."""
    from .strategies_prudentes import selection_unique  # import local : évite le cycle
    convergence = index_convergence(paris) if regle.get("convergence_min") else None
    eligibles = {id(p) for p in paris if motif_refus(p, regle, convergence) is None}
    return selection_unique(paris, eligibles, depuis or regle["debut"], _r(regle, "maximum_jour"))["selection"]
