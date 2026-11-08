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

Liste **stable** (``reviser``, état ``recommandees.json`` dans « donnees ») : elle n'est revue que tous les
``REVISION_JOURS`` jours. À une révision :
- une recommandée sort seulement si elle ne remplit plus un critère (ROI prudent négatif, trop dépendante d'un
  match, CLV par match négative…) ;
- une place libre est prise par la meilleure candidate qui n'est pas un doublon d'une recommandée restante ;
- une candidate remplace la plus faible des recommandées seulement si sa note la dépasse d'au moins
  ``ECART_REMPLACEMENT`` points.
Entre deux révisions, rien ne bouge. Chaque recommandée garde sa date d'entrée ; les sorties sont gardées
avec leur date et leur raison.

Fusions : si une révision change la liste (et qu'il reste au moins deux recommandées), une nouvelle fusion est
créée (Fusion 2, puis 3…) avec les recommandées du jour, membres figés, suivie depuis l'instant de la révision
(cotes/strategie_recommandee.py). Fusion 1 (8/11/2026) est la première. Les fusions ne sont jamais candidates.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

MAXIMUM = 3
MIN_MATCHS = 50
PART_MEILLEUR_MAX = 25.0      # %
RECOUVREMENT_MAX = 0.60
REVISION_JOURS = 7
ECART_REMPLACEMENT = 5        # points de note
FICHIER = "recommandees.json"
ANCIENNES_GARDEES = 30
PARIS = ZoneInfo("Europe/Paris")


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


def _note(l: dict | None) -> int:
    return ((l or {}).get("stats") or {}).get("note", {}).get("total", -1) if l else -1


def est_fusion(id_) -> bool:
    return str(id_).startswith("Fusion ")


def reviser(etat: dict | None, lignes: list[dict], aujourd_hui: date, maximum: int = MAXIMUM,
            instant: str | None = None) -> dict:
    """État suivant de la liste stable. ``etat`` : {"derniere_revision", "actuelles": [{id, depuis, note_entree}],
    "anciennes": [{id, depuis, jusqua, raison}], "journal": [...]}. Ne révise que si la dernière révision a au moins
    ``REVISION_JOURS`` jours (ou s'il n'y en a jamais eu). Pur : ne lit ni n'écrit aucun fichier."""
    etat = {"actuelles": [], "anciennes": [], "journal": [], "fusions": [], **(etat or {})}
    derniere = etat.get("derniere_revision")
    if derniere and (aujourd_hui - date.fromisoformat(derniere)).days < REVISION_JOURS:
        return etat
    jour = aujourd_hui.isoformat()
    par_id = {l["id"]: l for l in lignes}
    restantes, anciennes, entrees, sorties = [], list(etat["anciennes"]), [], []

    def sortir(a, raison):
        anciennes.append({**a, "jusqua": jour, "raison": raison})
        sorties.append({"id": a["id"], "raison": raison})

    for a in etat["actuelles"]:
        l = par_id.get(a["id"])
        raisons = raisons_refus(l.get("stats")) if l else ["stratégie disparue du classement"]
        if raisons:
            sortir(a, raisons[0])
        else:
            restantes.append(a)
    ensemble = lambda a: par_id[a["id"]]["ensemble"]  # noqa: E731
    candidates = sorted((l for l in lignes if not l.get("base") and not est_fusion(l["id"])
                         and not raisons_refus(l.get("stats"))
                         and l["id"] not in {a["id"] for a in restantes}),
                        key=lambda l: (-_note(l), -l["stats"]["note"]["matchs"], str(l["id"])))
    for c in candidates:
        doublon = lambda autres: any(recouvrement(c["ensemble"], ensemble(a)) > RECOUVREMENT_MAX  # noqa: E731
                                     for a in autres)
        nouvelle = {"id": c["id"], "depuis": jour, "note_entree": _note(c)}
        if len(restantes) < maximum:
            if not doublon(restantes):
                restantes.append(nouvelle)
                entrees.append(c["id"])
            continue
        faible = min(restantes, key=lambda a: (_note(par_id.get(a["id"])), a["id"]))
        autres = [a for a in restantes if a is not faible]
        if _note(c) >= _note(par_id.get(faible["id"])) + ECART_REMPLACEMENT and not doublon(autres):
            restantes = autres + [nouvelle]
            sortir(faible, f"remplacée par {c['id']} (note {_note(c)} contre {_note(par_id.get(faible['id']))})")
            entrees.append(c["id"])
    # Nouvelle fusion si la liste a changé depuis la dernière fusion (Fusion 1 : membres du 8/11/2026).
    from .strategie_recommandee import FUSIONS_AUTO, MEMBRES
    fusions = list(etat["fusions"])
    derniers = set(fusions[-1]["membres"]) if fusions else set(MEMBRES)
    ids = [a["id"] for a in restantes]
    n = (fusions[-1]["n"] if fusions else 1) + 1
    nouvelle_fusion = None
    if len(ids) >= 2 and set(ids) != derniers and n <= FUSIONS_AUTO[-1]["n"]:
        nouvelle_fusion = {"n": n, "membres": ids, "date": jour,
                           "debut": instant or datetime.combine(aujourd_hui, datetime.min.time(), PARIS).isoformat()}
        fusions.append(nouvelle_fusion)
    journal = etat["journal"] + [{"date": jour, "entrees": entrees, "sorties": sorties,
                                  "fusion": nouvelle_fusion["n"] if nouvelle_fusion else None}]
    return {"derniere_revision": jour, "actuelles": restantes, "anciennes": anciennes[-ANCIENNES_GARDEES:],
            "journal": journal[-ANCIENNES_GARDEES:], "fusions": fusions}


def mettre_a_jour(donnees: Path, lignes: list[dict], maintenant: datetime) -> dict:
    """Lit ``recommandees.json``, révise si c'est le moment, réécrit de façon atomique et renvoie l'état, avec la date
    de la prochaine révision. Une erreur d'écriture n'est pas propagée (le site se construit quand même)."""
    chemin = Path(donnees) / FICHIER
    try:
        etat = json.loads(chemin.read_text(encoding="utf-8"))
        etat = etat if isinstance(etat, dict) and isinstance(etat.get("actuelles"), list) else None
    except (OSError, ValueError):
        etat = None
    nouveau = reviser(etat, lignes, maintenant.astimezone(PARIS).date(),
                      instant=maintenant.astimezone(PARIS).isoformat(timespec="seconds"))
    if nouveau != etat:
        try:
            tmp = chemin.with_name(chemin.name + ".tmp")
            tmp.write_text(json.dumps(nouveau, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            os.replace(tmp, chemin)
        except OSError:
            pass
    prochaine = date.fromisoformat(nouveau["derniere_revision"]) + timedelta(days=REVISION_JOURS)
    return {**nouveau, "prochaine_revision": prochaine.isoformat()}
