"""Votes des sélections officielles, connus à la prise, sans consulter les résultats.

Deux versions Jules représentent une seule famille. Une convergence exige la
même cote française, le même prix et le même instant de détection (UTC), même
si les références diffèrent. Une sélection plus tardive ne réécrit pas le passé.
"""
from __future__ import annotations

from math import isfinite

from cotes.laboratoire import heure
from cotes.simulation import paris_strategie, REFERENCES
from cotes.strategie_chatgpt import paris_chatgpt
from cotes.strategie_gemini import paris_gemini
from cotes.strategie_jules import paris_jules
from cotes.strategie_jules_v2 import paris_jules_v2
from cotes.strategie_m3 import paris_m3

CONVERGENCE = {"nom": "Convergence ≥ 2", "debut": "2026-10-14T23:00:00+00:00"}
# clé de badge, famille de vote, libellé, clé du comparateur, sélecteur
STRATEGIES = (
    ("strategie", "claude", "Claude", "Claude (rejeu)", paris_strategie),
    ("chatgpt", "chatgpt", "ChatGPT v1", "ChatGPT v1 (rejeu)", paris_chatgpt),
    ("gemini", "gemini", "Gemini Argon v1", "Gemini Argon v1 (rejeu)", paris_gemini),
    ("jules", "jules", "Jules v1", "JULES EDGE v1 (rejeu)", paris_jules),
    ("jules_v2", "jules", "Jules v2", "JULES EDGE v2 (rejeu)", paris_jules_v2),
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
        if (not t or isinstance(p.get("cote"), bool) or not isinstance(p.get("cote"), (int, float))
                or not isfinite(p["cote"]) or p["cote"] <= 1 or not p.get("match_id")
                or not p.get("bookmaker")):
            continue
        cles = {cle for cle, ids in retenus.items() if id(p) in ids}
        if not cles:
            continue
        key = (cle_selection(p), t, p["cote"])
        groupe = groupes.setdefault(key, {"paris": [], "strategies": set(), "familles": set()})
        groupe["paris"].append(p)
        groupe["strategies"].update(cles)
        groupe["familles"].update(famille for cle, famille, *_ in STRATEGIES if cle in cles)
    return groupes


def paris_convergence(paris: list[dict], retenus: dict[str, set[int]] | None = None,
                      depuis: str | None = None) -> set[int]:
    retenus = retenus if retenus is not None else selections(paris, depuis=depuis)
    debut = heure(depuis or CONVERGENCE["debut"])
    ordre = {ref: i for i, ref in enumerate(REFERENCES)}
    premiers = {}
    for (cle, t, _), groupe in sorted(votes(paris, retenus).items(), key=lambda kv: kv[0][1]):
        if t < debut or len(groupe["familles"]) < 2 or cle in premiers:
            continue
        premiers[cle] = min(groupe["paris"], key=lambda p: (
            ordre.get(p.get("reference"), 99), str(p.get("id") or "")))
    return {id(p) for p in premiers.values()}


def valider_actuelles(actuelles: list[dict], paris: list[dict], retenus: dict[str, set[int]]) -> list[dict]:
    """Badges des prises enregistrées dont le prix est toujours proposé au dernier cycle.

    Aucun nouveau pari n'est inventé en réappliquant les seuils : les plafonds et
    dédoublonnages réels des sélecteurs restent respectés. La date est affichée.
    """
    par_prix = {}
    convergents = paris_convergence(paris, retenus)
    for (cle, t, prix), groupe in votes(paris, retenus).items():
        item = par_prix.setdefault((cle, prix), {"strategies": set(), "convergence": False, "validation_detecte": t})
        item["strategies"].update(groupe["strategies"])
        item["convergence"] |= any(id(p) in convergents for p in groupe["paris"])
        item["validation_detecte"] = max(item["validation_detecte"], t)
    out = []
    for o in actuelles:
        item = par_prix.get((cle_selection(o), o.get("cote")))
        out.append({**o, "strategies": sorted(item["strategies"]) if item else [],
                    "convergence": bool(item and item["convergence"]),
                    "validation_detecte": item["validation_detecte"].isoformat() if item else None})
    return out
