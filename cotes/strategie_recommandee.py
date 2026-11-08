"""Fusion 1 : réunion des trois stratégies recommandées le 8/11/2026, un seul pari par match
(docs/recommandees.md).

Membres figés au lancement : les trois stratégies retenues ce jour-là par cotes/recommandations.py (note /100
version 2, calculée par match ; critères et choix dans la documentation). Ce sont trois règles du laboratoire :

- Polymarket · cotes 1,5–3 · écart ≥ 2 % · ≤ 36 h (POL-1.5-3-e2-h36) ;
- Pinnacle · cotes 1,3–2 · écart ≥ 2 % · ≤ 36 h (PIN-1.3-2-e2-h36) ;
- Polymarket · cotes 2–5 · écart ≥ 2 % · ≤ 36 h (POL-2-5-e2-h36).

Fusion 1 ne suit pas la liste des recommandées : si une recommandée est remplacée plus tard, Fusion 1 garde ses
trois membres d'origine. Une autre combinaison serait une nouvelle stratégie (Fusion 2), avec sa propre date de départ.

Un pari est pris quand l'une d'elles le prend, à condition que le match n'ait encore aucun pari de la fusion : la
première prise du match l'emporte (à la même seconde, le plus gros écart). Pas de plafond par jour. La sélection
ne lit ni statut, ni gain, ni CLV. Les membres ne changent pas quand le classement change : le suivi compte depuis
DEBUT. Le rejeu depuis le 14/10 est optimiste (membres choisis après avoir vu ces résultats).
"""
from __future__ import annotations

DEBUT = "2026-11-08T08:00:00+00:00"           # 9 h à Paris, après la mise en ligne
MEMBRES = ("POL-1.5-3-e2-h36", "PIN-1.3-2-e2-h36", "POL-2-5-e2-h36")

RECOMMANDEE_FUSION = {
    "cle": "recommandee_fusion", "nom": "Fusion 1 · recommandées du 8/11", "court": "Fusion 1",
    "debut": DEBUT, "version": "1", "mise": 10.0, "maximum_jour": None, "auteur": "Claude",
    "prospectif_seulement": True, "membres": MEMBRES,
    "regles": "Pinnacle 1,3–2 ou Polymarket 1,5–5 · écart ≥ 2 % · ≤ 36 h avant le match · un seul pari par "
              "match (la première prise d'un des trois membres) · mise fictive 10 € · membres figés le 8/11/2026",
}


def selection_membres(paris: list[dict]) -> set[int]:
    """Paris pris par au moins un membre (prises figées de chaque règle du laboratoire, depuis le 14/10)."""
    from .laboratoire import DEBUT_SUIVI, REGLES, selectionner
    regles = {r.id: r for r in REGLES}
    out: set[int] = set()
    for cle in MEMBRES:
        out |= {id(p) for p in selectionner(paris, regles[cle], DEBUT_SUIVI)}
    return out


def paris_fusion(paris: list[dict], depuis: str | None = None) -> set[int]:
    """Prises de la fusion. Sans ``depuis`` : suivi depuis DEBUT, décisions figées (cotes/decisions.py).
    Avec ``depuis`` : rejeu non figé (affiché comme tel, optimiste)."""
    from .decisions import appliquer
    from .strategies_prudentes import selection_unique
    choisis = selection_unique(paris, frozenset(selection_membres(paris)), depuis or DEBUT)["selection"]
    return choisis if depuis is not None else appliquer(paris, choisis, RECOMMANDEE_FUSION["cle"])


# --------------------------------------------------------------------------- fusions automatiques (Fusion 2, 3…)
# À chaque révision des recommandées (cotes/recommandations.py, tous les 7 jours), si la liste a changé, une nouvelle
# fusion est créée avec les recommandées du jour, un pari par match, membres figés, suivie depuis sa création. Les
# places sont déclarées ici (pour les notifications et la page) et activées par l'état ``recommandees.json`` :
# ``charger_fusions`` remplit les places actives. Une place inactive ne prend aucun pari et n'est pas affichée.
# La sélection relit les prises figées des membres (cotes/decisions.py) : elle ne lit ni statut, ni gain, ni CLV.
PLACE_LIBRE = "2100-01-01T00:00:00+00:00"
FUSIONS_AUTO = tuple({
    "cle": f"fusion_{n}", "nom": f"Fusion {n}", "court": f"Fusion {n}", "n": n, "debut": PLACE_LIBRE,
    "version": "1", "mise": 10.0, "maximum_jour": None, "auteur": "Claude (automatique)",
    "prospectif_seulement": True, "membres": (), "actif": False,
    "regles": "Place libre : créée automatiquement quand la liste des recommandées change"} for n in range(2, 22))


def charger_fusions(source) -> list[dict]:
    """Active les places des fusions créées (``source`` : dossier « donnees » ou état déjà lu). Renvoie les actives."""
    import json
    from pathlib import Path
    etat = source
    if not isinstance(source, dict):
        try:
            etat = json.loads((Path(source) / "recommandees.json").read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            etat = {}
    creees = {f.get("n"): f for f in (etat or {}).get("fusions") or [] if isinstance(f, dict)}
    for place in FUSIONS_AUTO:
        f = creees.get(place["n"])
        if f and f.get("membres") and f.get("debut"):
            jour = str(f.get("date") or f["debut"][:10])
            place.update(debut=f["debut"], membres=tuple(f["membres"]), actif=True, date=jour,
                         regles=f"Recommandées du {jour[8:10]}/{jour[5:7]} réunies · un seul pari par match (la "
                                f"première prise d'un des membres) · membres figés · mise fictive 10 € · créée "
                                f"automatiquement")
        else:
            place.update(debut=PLACE_LIBRE, membres=(), actif=False)
    return [p for p in FUSIONS_AUTO if p["actif"]]


def selection_fusion_auto(paris: list[dict], place: dict, ids_membres: dict[str, set[int]]) -> set[int]:
    """Prises d'une fusion automatique : réunion des prises de ses membres depuis sa création, première par match."""
    if not place.get("actif"):
        return set()
    from .strategies_prudentes import selection_unique
    union: set[int] = set()
    for m in place["membres"]:
        union |= ids_membres.get(m, set())
    return selection_unique(paris, frozenset(union), place["debut"])["selection"] if union else set()
