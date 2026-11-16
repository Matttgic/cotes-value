"""Stratégies recommandées : celles qui battent le plus sûrement la clôture Pinnacle, sans doublon
(docs/recommandees.md).

Critères version 2 (16/11/2026), mêmes mesures que la page Décision et le protocole (CLV contre la clôture Pinnacle
sans marge, le match comme unité de hasard, test de Student). Une stratégie est candidate si, sur son suivi depuis le
lancement (mise fixe, cote ≤ plafond) :
- elle a au moins 50 matchs réglés ;
- la clôture Pinnacle est connue pour au moins la moitié de ses paris réglés (et au moins 30 mesures) ;
- sa CLV Pinnacle est positive après correction de Holm sur toutes les stratégies testées (p < 5 %) : le nombre de
  stratégies comparées ne fabrique pas de gagnantes ;
- son rendement n'est pas nettement sous sa CLV (écart rendement − CLV : borne haute à 95 % ≥ 0) ;
- son ROI est positif.

La version 1 (note /100, ROI prudent à 80 % sans correction) retenait des stratégies chanceuses : avec une centaine
de lignes comparées, une sur dix passait par hasard (docs/avantage-reel.md).

Les candidates sont prises par borne basse à 95 % de la CLV Pinnacle, décroissante. Une candidate qui partage plus de 60 % de ses paris avec une
stratégie déjà retenue est écartée (recouvrement = paris communs / paris de la plus petite) : deux règles presque
identiques ne font pas deux recommandations. Les bases du Bilan ne sont pas candidates (elles réunissent tous les
paris d'une référence). Le classement est recalculé à chaque construction du site : il décrit le passé, il ne
garantit aucun gain futur.

Liste **stable** (``reviser``, état ``recommandees.json`` dans « donnees ») : elle n'est revue que tous les
``REVISION_JOURS`` jours. À une révision :
- une recommandée sort seulement si elle ne remplit plus un critère ;
- une place libre est prise par la meilleure candidate qui n'est pas un doublon d'une recommandée restante ;
- une candidate remplace la plus faible des recommandées seulement si sa borne basse de CLV la dépasse d'au moins
  ``ECART_REMPLACEMENT`` point.
Un changement de version des critères déclenche une révision immédiate.
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

CRITERES = 2                  # version des critères : la changer révise la liste tout de suite
MAXIMUM = 3
MIN_MATCHS = 50
MIN_CLV = 30                  # clôtures Pinnacle mesurées
PART_PINNACLE_MIN = 50.0      # % des paris réglés dont la clôture Pinnacle est connue
ALPHA = 0.05                  # CLV positive : p de Holm, unilatéral
RECOUVREMENT_MAX = 0.60
REVISION_JOURS = 7
ECART_REMPLACEMENT = 0.5      # point de borne basse de CLV
FICHIER = "recommandees.json"
ANCIENNES_GARDEES = 30
PARIS = ZoneInfo("Europe/Paris")


def raisons_refus(stats: dict | None) -> list[str]:
    """Critères non remplis (liste vide : candidate). Lit ``stats["preuve"]`` (``mesurer_preuves``)."""
    p = (stats or {}).get("preuve")
    if not p or not p.get("regles"):
        return ["aucun pari réglé"]
    out = []
    if p["matchs"] < MIN_MATCHS:
        out.append(f"moins de {MIN_MATCHS} matchs réglés")
    if p["couverture"] < PART_PINNACLE_MIN:
        out.append("clôture Pinnacle connue pour moins de la moitié des paris")
    if not p["teste"]:
        out.append("trop peu de clôtures Pinnacle mesurées")
    elif p.get("doublon_de"):
        out.append(f"doublon de {p['doublon_de']} (au moins {round(100 * DOUBLON_MIN)} % de paris communs), non testée")
    else:
        if p["clv"] <= 0 or p["p"] >= ALPHA:
            out.append("CLV Pinnacle non prouvée après correction")
        if p["ecart_haut"] < 0:
            out.append("rendement nettement sous la CLV")
    if p["roi"] is None or p["roi"] <= 0:
        out.append("ROI négatif")
    return out


def force(stats: dict | None) -> float:
    """Borne basse à 95 % de la CLV Pinnacle (en %) : le classement. −100 si elle n'est pas mesurée."""
    ic = ((stats or {}).get("preuve") or {}).get("clv_ic")
    return ic[0] if ic else -100.0


def mesurer_preuves(lignes: list[dict], paris: list[dict]) -> bool:
    """Ajoute ``stats["preuve"]`` à chaque stratégie (ni base ni fusion) : ROI et CLV Pinnacle par match sur ses paris
    (``ensemble``), comme une ligne de la page Décision, puis p de Holm (CLV positive) sur toutes les testées.
    Faux si les paris ne permettent pas la mesure (clôture incomplète) : la liste n'est alors pas révisée."""
    from .decision import holm, mesurer
    from .evenements import identites
    from .protocole import clv_pinnacle
    try:
        liens, clvs = identites(paris), clv_pinnacle(paris)
    except (KeyError, TypeError, ValueError):
        return False
    match_de = lambda p: liens.get(id(p), ("ligne", p.get("id")))  # noqa: E731
    par_id = {p["id"]: p for p in paris if p.get("id")}
    testees = []
    for l in lignes:
        if l.get("base") or est_fusion(l["id"]) or not isinstance(l.get("stats"), dict):
            continue
        x = mesurer({"id": l["id"], "paris": [par_id[i] for i in l.get("ensemble") or () if i in par_id]},
                    match_de, clvs)
        r = lambda v, d=2: None if v is None else round(v, d)  # noqa: E731
        preuve = {"regles": x["regles"], "matchs": x.get("matchs", 0), "roi": r(x.get("roi")), "clv": r(x.get("clv")),
                  "clv_n": x.get("clv_n", 0), "couverture": round(100 * x.get("couverture", 0), 1),
                  "teste": x["clv_teste"], "clv_ic": None, "p": None, "ecart_haut": None}
        if x["clv_teste"]:
            preuve.update(clv_ic=[r(v) for v in x["clv_ic"]], ecart_haut=r(x["ecart_ic"][1]))
        l["stats"]["preuve"] = preuve
        if x["clv_teste"]:
            testees.append((l, preuve, x["clv_p_pos"]))
    # Tester moins de lignes (docs/avantage-reel.md, décision 5) : une stratégie qui partage au moins ``DOUBLON_MIN``
    # de ses paris avec une autre plus fournie n'entre pas dans la correction. Choix sur le nombre de paris, jamais
    # sur un résultat.
    gardees = []
    for l, preuve, p in sorted(testees, key=lambda t: (-len(t[0].get("ensemble") or ()), str(t[0]["id"]))):
        proche = next((g for g, _, _ in gardees if recouvrement(l.get("ensemble") or set(), g.get("ensemble") or set())
                       >= DOUBLON_MIN), None)
        if proche is not None:
            preuve["doublon_de"] = proche["id"]
        else:
            gardees.append((l, preuve, p))
    for (_, preuve, _), p in zip(gardees, holm([p for _, _, p in gardees])):
        preuve["p"] = round(p, 5)
    for _, preuve, _ in testees:
        preuve["testees"] = len(gardees)
    return True


def recouvrement(a: set, b: set) -> float:
    return len(a & b) / min(len(a), len(b)) if a and b else 0.0


def recommander(lignes: list[dict], maximum: int = MAXIMUM) -> dict:
    """``lignes`` : {id, stats, ensemble (identifiants stables des paris), base (bool)}.

    Renvoie {"liste": [{rang, id, note, mesures}], "ecartees": [{id, note, raison}]} : les recommandées dans l'ordre,
    puis les candidates écartées comme doublons."""
    candidates = [l for l in lignes if not l.get("base") and not raisons_refus(l.get("stats"))]
    candidates.sort(key=lambda l: (-force(l["stats"]), str(l["id"])))
    retenues, ecartees = [], []
    for l in candidates:
        proche = next((r for r in retenues if recouvrement(l["ensemble"], r["ensemble"]) > RECOUVREMENT_MAX), None)
        if proche is not None:
            ecartees.append({"id": l["id"], "force": force(l["stats"]),
                             "raison": f"{round(100 * recouvrement(l['ensemble'], proche['ensemble']))} % de paris "
                                       f"communs avec {proche['id']}", "proche": proche["id"]})
            continue
        if len(retenues) < maximum:
            retenues.append(l)
        else:
            ecartees.append({"id": l["id"], "force": force(l["stats"]), "raison": "hors des premières"})
    return {"liste": [{"rang": i + 1, "id": l["id"], "force": force(l["stats"]), "preuve": l["stats"]["preuve"]}
                      for i, l in enumerate(retenues)],
            "ecartees": ecartees}


DOUBLON_MIN = 0.80
DOUBLON_MIN_PARIS = 30
DOUBLONS_MAX = 40


def doublons(lignes: list[dict]) -> list[dict]:
    """Paires de stratégies qui partagent au moins ``DOUBLON_MIN`` de leurs paris (part de la plus petite). Les bases
    et les fusions (qui réunissent leurs membres) sont exclues. Triées par part puis nombre de paris communs."""
    sel = sorted((l for l in lignes if not l.get("base") and not est_fusion(l["id"])
                  and len(l.get("ensemble") or ()) >= DOUBLON_MIN_PARIS), key=lambda l: str(l["id"]))
    out = []
    for i, a in enumerate(sel):
        for b in sel[i + 1:]:
            part = recouvrement(a["ensemble"], b["ensemble"])
            if part >= DOUBLON_MIN:
                out.append({"a": a["id"], "b": b["id"], "part": round(100 * part, 1),
                            "communs": len(a["ensemble"] & b["ensemble"]),
                            "paris_a": len(a["ensemble"]), "paris_b": len(b["ensemble"]),
                            "note_a": _note(a), "note_b": _note(b)})
    out.sort(key=lambda d: (-d["part"], -d["communs"], str(d["a"]), str(d["b"])))
    return out[:DOUBLONS_MAX]


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
    if derniere and etat.get("criteres", 1) == CRITERES and (aujourd_hui - date.fromisoformat(derniere)).days < REVISION_JOURS:
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
            sortir(a, ", ".join(raisons) + (" (critères version 2)" if etat.get("criteres", 1) != CRITERES else ""))
        else:
            restantes.append(a)
    ensemble = lambda a: par_id[a["id"]]["ensemble"]  # noqa: E731
    candidates = sorted((l for l in lignes if not l.get("base") and not est_fusion(l["id"])
                         and not raisons_refus(l.get("stats"))
                         and l["id"] not in {a["id"] for a in restantes}),
                        key=lambda l: (-force(l["stats"]), str(l["id"])))
    for c in candidates:
        doublon = lambda autres: any(recouvrement(c["ensemble"], ensemble(a)) > RECOUVREMENT_MAX  # noqa: E731
                                     for a in autres)
        nouvelle = {"id": c["id"], "depuis": jour, "note_entree": _note(c), "force_entree": force(c["stats"])}
        if len(restantes) < maximum:
            if not doublon(restantes):
                restantes.append(nouvelle)
                entrees.append(c["id"])
            continue
        f_de = lambda a: force(par_id[a["id"]]["stats"])  # noqa: E731
        faible = min(restantes, key=lambda a: (f_de(a), a["id"]))
        autres = [a for a in restantes if a is not faible]
        if force(c["stats"]) >= f_de(faible) + ECART_REMPLACEMENT and not doublon(autres):
            restantes = autres + [nouvelle]
            v = lambda x: f"{x:+.2f}".replace(".", ",")  # noqa: E731
            sortir(faible, f"remplacée par {c['id']} (CLV Pinnacle au moins {v(force(c['stats']))} % contre "
                           f"{v(f_de(faible))} %)")
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
    return {"derniere_revision": jour, "criteres": CRITERES, "actuelles": restantes, "anciennes": anciennes[-ANCIENNES_GARDEES:],
            "journal": journal[-ANCIENNES_GARDEES:], "fusions": fusions}


def mettre_a_jour(donnees: Path, lignes: list[dict], maintenant: datetime, reviser_permis: bool = True) -> dict:
    """Lit ``recommandees.json``, révise si c'est le moment (et si ``reviser_permis`` : mesures disponibles), réécrit
    de façon atomique et renvoie l'état, avec la date de la prochaine révision. Une erreur d'écriture n'est pas
    propagée (le site se construit quand même)."""
    chemin = Path(donnees) / FICHIER
    try:
        etat = json.loads(chemin.read_text(encoding="utf-8"))
        etat = etat if isinstance(etat, dict) and isinstance(etat.get("actuelles"), list) else None
    except (OSError, ValueError):
        etat = None
    if not reviser_permis and etat:
        nouveau = etat
    else:
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
