"""Votes des sélections officielles, connus à la prise, sans consulter les résultats.

Deux versions Jules représentent une seule famille. Une convergence exige la
même cote française, le même prix et le même instant de détection (UTC), même
si les références diffèrent. Une sélection plus tardive ne réécrit pas le passé.
"""
from __future__ import annotations

from math import isfinite
from .decisions import figer_selecteur

from cotes.laboratoire import heure
from cotes.simulation import paris_strategie, REFERENCES
from cotes.strategie_chatgpt import paris_chatgpt
from cotes.strategie_gemini import paris_gemini
from cotes.strategie_jules import paris_jules
from cotes.strategie_jules_v2 import paris_jules_v2
from cotes.strategie_eden import paris_eden
from cotes.strategie_m3 import paris_m3

CONVERGENCE = {"nom": "Convergence ≥ 2", "debut": "2026-10-14T23:00:00+00:00"}
# clé de badge, famille de vote, libellé, clé du comparateur, sélecteur
STRATEGIES = (
    ("strategie", "claude", "Claude", "Claude (rejeu)", paris_strategie),
    ("chatgpt", "chatgpt", "ChatGPT v1", "ChatGPT v1 (rejeu)", paris_chatgpt),
    ("gemini", "gemini", "Gemini Argon v1", "Gemini Argon v1 (rejeu)", paris_gemini),
    ("jules", "jules", "Jules v1", "JULES EDGE v1 (rejeu)", paris_jules),
    ("jules_v2", "jules", "Jules v2", "JULES EDGE v2 (rejeu)", paris_jules_v2),
    ("eden", "eden", "Eden", "Eden (rejeu)", paris_eden),
    ("m3", "m3", "M3", "M3 (rejeu)", paris_m3),
)


def cle_selection(p: dict) -> tuple:
    return tuple(p.get(k) for k in
                 ("bookmaker", "match_id", "marche", "periode", "ligne", "issue", "joueur"))


def selections(paris: list[dict], depuis: str | None = None) -> dict[str, set[int]]:
    return {cle: (selecteur(paris, depuis=depuis) if depuis is not None else selecteur(paris))
            for cle, _, _, _, selecteur in STRATEGIES}


def votes(paris: list[dict], retenus: dict[str, set[int]]) -> dict[tuple, dict]:
    groupes = {}
    for p in paris:
        t = heure(p.get("detecte"))
        if (not t or not _prix_valide(p.get("cote")) or not p.get("match_id")
                or not p.get("bookmaker")):
            continue
        # Les variantes peuvent être présentes pour les badges. Elles ne
        # modifient ni les votes ni la prise représentative des convergences.
        cles = {cle for cle, *_ in STRATEGIES if id(p) in retenus.get(cle, set())}
        if not cles:
            continue
        key = (cle_selection(p), t, p["cote"])
        groupe = groupes.setdefault(key, {"paris": [], "strategies": set(), "familles": set()})
        groupe["paris"].append(p)
        groupe["strategies"].update(cles)
        groupe["familles"].update(famille for cle, famille, *_ in STRATEGIES if cle in cles)
    return groupes


def _prix_valide(prix) -> bool:
    return isinstance(prix, (int, float)) and not isinstance(prix, bool) and isfinite(prix) and prix > 1


@figer_selecteur("convergence")
def paris_convergence(paris: list[dict], retenus: dict[str, set[int]] | None = None,
                      depuis: str | None = None) -> set[int]:
    retenus = retenus if retenus is not None else selections(paris, depuis=depuis)
    debut = heure(depuis or CONVERGENCE["debut"])
    if debut is None:
        return set()
    ordre = {ref: i for i, ref in enumerate(REFERENCES)}
    representant = lambda p: (ordre.get(p.get("reference"), 99), str(p.get("id") or ""))
    premiers = {}
    # Même instant, plusieurs prix : départage déterministe, sans dépendre de l'ordre du fichier.
    groupes = sorted(votes(paris, retenus).items(), key=lambda kv: (
        kv[0][1], min(representant(p) for p in kv[1]["paris"]), kv[0][2]))
    for (cle, t, _), groupe in groupes:
        if t < debut or len(groupe["familles"]) < 2 or cle in premiers:
            continue
        premiers[cle] = min(groupe["paris"], key=representant)
    return {id(p) for p in premiers.values()}


def valider_actuelles(actuelles: list[dict], paris: list[dict], retenus: dict[str, set[int]]) -> list[dict]:
    """Badges des prises enregistrées dont le prix est toujours proposé au dernier cycle.

    Aucun nouveau pari n'est inventé en réappliquant les seuils : les plafonds et
    dédoublonnages réels des sélecteurs restent respectés. La date est affichée.
    """
    par_prix = {}
    dernieres = {}
    convergents = paris_convergence(paris, retenus)
    for p in paris:
        t = heure(p.get("detecte"))
        strategies = {cle for cle, ids in retenus.items() if id(p) in ids}
        if t is None or not strategies or not _prix_valide(p.get("cote")):
            continue
        cle, prix = cle_selection(p), p.get("cote")
        item = par_prix.setdefault((cle, prix), {"strategies": set(), "convergence": False, "validation_detecte": t})
        item["strategies"].update(strategies)
        item["convergence"] |= id(p) in convergents
        item["validation_detecte"] = max(item["validation_detecte"], t)
        rang = (t, prix)
        if cle not in dernieres or rang > dernieres[cle][0]:
            dernieres[cle] = (rang, prix, item)
    out = []
    for o in actuelles:
        cle, prix = cle_selection(o), o.get("cote")
        item = par_prix.get((cle, prix)) if _prix_valide(prix) else None
        precedent = dernieres.get(cle)
        t_actuel = heure(o.get("detecte"))
        change = bool(_prix_valide(prix) and item is None and precedent and t_actuel is not None
                      and precedent[2]["validation_detecte"] <= t_actuel)
        out.append({**o, "strategies": sorted(item["strategies"]) if item else [],
                    "convergence": bool(item and item["convergence"]),
                    "prix_change": change, "prix_precedent": precedent[1] if change else None,
                    "strategies_precedentes": sorted(precedent[2]["strategies"]) if change else [],
                    "convergence_precedente": bool(change and precedent[2]["convergence"]),
                    "validation_precedente": precedent[2]["validation_detecte"].isoformat() if change else None,
                    "validation_detecte": item["validation_detecte"].isoformat() if item else None})
    return out
