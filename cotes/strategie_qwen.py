"""Qwen (qwen_persistence) : Pinnacle, favoris à valeur persistante sur deux cycles consécutifs.

Règles : référence Pinnacle seule (cote juste, marge retirée) ; résultat 1N2, vainqueur, handicap et total du
match ; cote française de 1,45 à 3,20 ; edge (`ecart`) ≥ 3,5 % ; de 15 min à 2 h avant le match ; Winamax et
Betclic seulement ; 3 paris validés par jour au plus ; mise fictive de 10 €.

Persistance : une prise (bookmaker, match, marché, période, ligne, issue) n'est validée que si elle a tenu les
critères (cote, edge) à deux cycles consécutifs. L'état tient dans un petit fichier (`persistance_qwen.json`) :
seules les prises vues au cycle précédent y figurent. Un trou de plus de 12 minutes entre deux cycles remet tous
les compteurs à zéro.

Le pari simulé est celui de la première détection (prix de la première détection, enregistré par ``placer``).
« Pas de dérive négative » : la validation est refusée si la cote actuelle est inférieure à cette cote.

La décision est prise à la validation, pas à la détection : elle est ajoutée aux sélections figées du pari avec sa
date. Aucun rejeu historique n'existe (la persistance ne se déduit pas d'une prise seule).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .decisions import appliquer
from .laboratoire import heure
from .strategie_commune import correspondance_prouvee, edge_coherent, nombre_fini

QWEN = {
    "cle": "qwen_persistence", "nom": "Qwen", "court": "Qwen", "version": "1", "mise": 10,
    "debut": "2026-10-20T00:00:00+00:00", "prospectif_seulement": True,
    "regles": "Pinnacle · 1N2, vainqueur, handicap, total · 1,45–3,20 · edge ≥ 3,5 % · 15 min–2 h · Winamax et Betclic · "
              "2 cycles consécutifs · max 3/jour · mise fictive 10 €",
}
# Paramètres de la règle (hors du dictionnaire publié sur le site, qui doit rester sérialisable en JSON)
REGLE = {
    "references": {"Pinnacle"}, "bookmakers": {"Winamax", "Betclic"},
    "marches": {"RESULTAT_1N2", "VAINQUEUR", "HANDICAP", "TOTAL"}, "periodes": {"MATCH", "TEMPS_REG"},
    "cote_min": 1.45, "cote_max": 3.20, "edge_min": 0.035,
    "avance_min_minutes": 15, "avance_max_h": 2, "cycles": 2, "trou_max_minutes": 12, "max_par_jour": 3,
}
PARIS = ZoneInfo("Europe/Paris")


def cle_prise(p: dict) -> tuple:
    return tuple(p.get(k) for k in ("bookmaker", "match_id", "marche", "periode", "ligne", "issue", "joueur"))


def _texte_cle(p: dict) -> str:
    return "|".join("" if v is None else str(v) for v in cle_prise(p))


def motif_refus_ligne(p: dict) -> str | None:
    """Critères d'une ligne (pari enregistré ou opportunité du cycle), sans fenêtre ni persistance."""
    if p.get("reference") not in REGLE["references"]:
        return "référence hors périmètre"
    if p.get("bookmaker") not in REGLE["bookmakers"]:
        return "bookmaker hors périmètre"
    if p.get("suspect") or p.get("pariable") is False:
        return "opportunité suspecte"
    marche = p.get("marche")
    if marche not in REGLE["marches"] or p.get("periode") not in REGLE["periodes"]:
        return "marché ou période hors périmètre"
    if p.get("sport") in ("tennis", "volley") and marche != "VAINQUEUR":
        return "unité ambiguë (sets ou jeux)"
    cote, edge = nombre_fini(p.get("cote")), nombre_fini(p.get("ecart"))
    if cote is None or not REGLE["cote_min"] <= cote <= REGLE["cote_max"]:
        return "cote hors intervalle 1,45–3,20"
    if edge is None or edge < REGLE["edge_min"]:
        return "edge inférieur à 3,5 %"
    return None


def motif_refus_pari(p: dict) -> str | None:
    """Pari enregistré : critères de ligne, cohérence de l'edge et preuve de correspondance."""
    motif = motif_refus_ligne(p)
    if motif:
        return motif
    if not edge_coherent(p.get("cote"), p.get("cote_juste"), p.get("ecart")):
        return "edge incohérent avec la cote juste"
    if not correspondance_prouvee(p, 0.85):
        return "preuve de correspondance ou de conformité insuffisante"
    return None


def suivre(etat: dict | None, opportunites: list[dict], maintenant: datetime, cycle_id: str) -> tuple[dict, dict]:
    """Compteurs de persistance du cycle. Retourne (nouvel état, {clé de prise : (cycles, opportunité)}).

    Une prise continue si elle figurait au cycle précédent et que celui-ci date de 12 minutes au plus."""
    etat = etat if isinstance(etat, dict) else {}
    avant = etat.get("prises") if isinstance(etat.get("prises"), dict) else {}
    precedent = heure(etat.get("cycle_le"))
    if precedent is None or not timedelta(0) <= maintenant - precedent <= timedelta(minutes=REGLE["trou_max_minutes"]):
        avant = {}
    vues: dict[str, tuple[int, dict]] = {}
    for o in sorted(opportunites, key=lambda o: -(nombre_fini(o.get("ecart")) or 0)):
        if motif_refus_ligne(o) is not None:
            continue
        cle = _texte_cle(o)
        if cle not in vues:
            vues[cle] = ((avant.get(cle) or {}).get("cycles", 0) + 1, o)
    nouvel = {"cycle_id": cycle_id, "cycle_le": maintenant.isoformat(timespec="seconds"),
              "prises": {cle: {"cycles": n} for cle, (n, _) in vues.items()}}
    return nouvel, vues


def valider(paris: list[dict], vues: dict, maintenant: datetime) -> dict:
    """Ajoute la sélection aux paris dont la prise tient depuis deux cycles. Retourne un résumé du cycle."""
    resume = {"candidates": 0, "validees": 0, "refus": {}}
    if maintenant < heure(QWEN["debut"]):
        return resume
    par_prise = {}
    for p in paris:
        if p.get("reference") in REGLE["references"] and isinstance(p.get("selections_figees"), dict):
            par_prise.setdefault(_texte_cle(p), p)
    jour = maintenant.astimezone(PARIS).date()
    pris = sum(1 for p in paris if isinstance(p.get("selections_figees"), dict)
               and QWEN["cle"] in p["selections_figees"]
               and (heure(p["selections_figees"][QWEN["cle"]].get("decide_le")) or maintenant).astimezone(PARIS).date() == jour)

    def refuser(motif):
        resume["refus"][motif] = resume["refus"].get(motif, 0) + 1

    for cle, (cycles, o) in vues.items():
        if cycles < REGLE["cycles"]:
            continue
        resume["candidates"] += 1
        p = par_prise.get(cle)
        if p is None:
            refuser("pari absent du registre")
            continue
        if QWEN["cle"] in p["selections_figees"]:
            continue
        debut = heure(p.get("debut"))
        delai = (debut - maintenant).total_seconds() if debut else None
        if p.get("statut") != "en_cours" or delai is None:
            refuser("pari clos")
        elif not REGLE["avance_min_minutes"] * 60 <= delai <= REGLE["avance_max_h"] * 3600:
            refuser("hors fenêtre de 15 min à 2 h")
        elif motif_refus_pari(p):
            refuser(motif_refus_pari(p))
        elif (nombre_fini(o.get("cote")) or 0) < p["cote"]:
            refuser("cote en baisse depuis la première détection")
        elif pris >= REGLE["max_par_jour"]:
            refuser("plafond de 3 paris par jour")
        else:
            p["selections_figees"][QWEN["cle"]] = {
                "version": QWEN["version"], "decide_le": maintenant.isoformat(timespec="microseconds"),
                "cycles": cycles, "cote_confirmee": o["cote"]}
            pris += 1
            resume["validees"] += 1
    return resume


def paris_qwen(paris: list[dict], depuis: str | None = None) -> set[int]:
    """Paris validés (décision figée). Aucun rejeu : la persistance ne se déduit pas d'une prise isolée."""
    return set() if depuis is not None else appliquer(paris, set(), QWEN["cle"])
