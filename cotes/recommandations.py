"""Stratégies recommandées : les mieux notées parmi celles dont le résultat est solide, sans doublon
(docs/recommandees.md).

Une stratégie est candidate si, sur son suivi depuis le lancement (mise fixe) :
- sa note /100 (version 2, par match) n'est pas provisoire : au moins 50 matchs réglés ;
- la borne basse à 80 % de son ROI (calculée par match) est positive ;
- son ROI reste positif sans ses meilleurs matchs (5 %, au moins un) ;
- son meilleur match apporte au plus 25 % de ses gains ;
- sa CLV moyenne par match est positive.

Les candidates sont prises par note décroissante. Une candidate qui partage plus de 60 % de ses paris avec une
stratégie déjà retenue est écartée (recouvrement = paris communs / paris de la plus petite) : deux règles presque
identiques ne font pas deux recommandations. Les bases du Bilan ne sont pas candidates (elles réunissent tous les
paris d'une référence). Le classement est recalculé à chaque construction du site : il décrit le passé, il ne
garantit aucun gain futur.
"""
from __future__ import annotations

MAXIMUM = 3
MIN_MATCHS = 50
PART_MEILLEUR_MAX = 25.0      # %
RECOUVREMENT_MAX = 0.60


def raisons_refus(stats: dict | None) -> list[str]:
    """Critères non remplis (liste vide : candidate)."""
    note = (stats or {}).get("note")
    if not isinstance(note, dict):
        return ["moins de 10 matchs réglés"]
    m = note.get("mesures") or {}
    out = []
    if (note.get("matchs") or 0) < MIN_MATCHS:
        out.append(f"moins de {MIN_MATCHS} matchs réglés")
    if (m.get("roi_borne_basse_80") is None) or m["roi_borne_basse_80"] <= 0:
        out.append("borne basse du ROI négative")
    if (m.get("roi_sans_meilleurs") is None) or m["roi_sans_meilleurs"] <= 0:
        out.append("ROI négatif sans ses meilleurs matchs")
    if (m.get("part_meilleur_match") or 100) > PART_MEILLEUR_MAX:
        out.append("trop dépendante d'un match")
    if (m.get("clv_ajustee") is None) or m["clv_ajustee"] <= 0:
        out.append("CLV par match négative")
    return out


def recouvrement(a: set, b: set) -> float:
    return len(a & b) / min(len(a), len(b)) if a and b else 0.0


def recommander(lignes: list[dict], maximum: int = MAXIMUM) -> dict:
    """``lignes`` : {id, stats, ensemble (identifiants stables des paris), base (bool)}.

    Renvoie {"liste": [{rang, id, note, mesures}], "ecartees": [{id, note, raison}]} : les recommandées dans l'ordre,
    puis les candidates écartées comme doublons."""
    candidates = [l for l in lignes if not l.get("base") and not raisons_refus(l.get("stats"))]
    candidates.sort(key=lambda l: (-l["stats"]["note"]["total"], -l["stats"]["note"]["matchs"], str(l["id"])))
    retenues, ecartees = [], []
    for l in candidates:
        proche = next((r for r in retenues if recouvrement(l["ensemble"], r["ensemble"]) > RECOUVREMENT_MAX), None)
        if proche is not None:
            ecartees.append({"id": l["id"], "note": l["stats"]["note"]["total"],
                             "raison": f"{round(100 * recouvrement(l['ensemble'], proche['ensemble']))} % de paris "
                                       f"communs avec {proche['id']}", "proche": proche["id"]})
            continue
        if len(retenues) < maximum:
            retenues.append(l)
        else:
            ecartees.append({"id": l["id"], "note": l["stats"]["note"]["total"], "raison": "hors des premières"})
    return {"liste": [{"rang": i + 1, "id": l["id"], "note": l["stats"]["note"]["total"],
                       "mesures": l["stats"]["note"].get("mesures"), "matchs": l["stats"]["note"]["matchs"]}
                      for i, l in enumerate(retenues)],
            "ecartees": ecartees,
            "criteres": {"min_matchs": MIN_MATCHS, "part_meilleur_max": PART_MEILLEUR_MAX,
                         "recouvrement_max": RECOUVREMENT_MAX, "maximum": maximum}}
