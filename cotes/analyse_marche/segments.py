"""Tableaux par segment (bookmaker, référence, sport, marché, délai avant le match…), avec la taille de
chaque échantillon. Un segment de moins de ``ECHANTILLON_MIN`` cas est marqué insuffisant."""
from __future__ import annotations

from statistics import median

ECHANTILLON_MIN = 30
TRANCHES_H = ((1, "< 1 h"), (3, "1-3 h"), (12, "3-12 h"), (24, "12-24 h"), (float("inf"), "> 24 h"))
CAUSES = ("bookmaker", "reference", "match_commence", "inconnue", "en_cours")


def tranche(delai_h) -> str:
    """Délai avant le match, en tranches."""
    if not isinstance(delai_h, (int, float)) or delai_h < 0:
        return "inconnu"
    return next(nom for borne, nom in TRANCHES_H if delai_h < borne)


def _valeur(x: dict, champ: str):
    return tranche(x.get("delai_h")) if champ == "tranche" else x.get(champ)


def grouper(lignes: list[dict], par: tuple[str, ...]) -> dict[tuple, list[dict]]:
    out: dict[tuple, list[dict]] = {}
    for x in lignes:
        out.setdefault(tuple(_valeur(x, c) for c in par), []).append(x)
    return out


def _quantile(v: list[float], q: float) -> float | None:
    if not v:
        return None
    v = sorted(v)
    return v[min(len(v) - 1, int(q * len(v)))]


def _pct(n: int, total: int) -> float | None:
    return round(100 * n / total, 1) if total else None


def resume_opportunites(episodes: list[dict], par: tuple[str, ...] = ("b",)) -> list[dict]:
    """Par segment : nombre d'épisodes, durée (médiane et 75e centile, bornes basse et haute, sur les fins
    observées) et part de chaque cause."""
    out = []
    for seg, g in sorted(grouper(episodes, par).items(), key=lambda kv: (-len(kv[1]), str(kv[0]))):
        finis = [e for e in g if e.get("dmax") is not None]
        bas, haut = [e["dmin"] for e in finis], [e["dmax"] for e in finis]
        causes = {c: sum(1 for e in g if e.get("cause") == c) for c in CAUSES}
        out.append({**dict(zip(par, seg)), "n": len(g), "fins_observees": len(finis),
                    "mediane_min": [median(bas), median(haut)] if finis else None,
                    "p75_min": [_quantile(bas, .75), _quantile(haut, .75)] if finis else None,
                    **{f"pct_{c}": _pct(n, len(g)) for c, n in causes.items()},
                    "insuffisant": len(g) < ECHANTILLON_MIN})
    return out


def resume_meneurs(lignes: list[dict], par: tuple[str, ...] = ("a", "b")) -> list[dict]:
    """Par paire (et segment) : mouvements appariés, part menée par chacun, ensemble, délai du suiveur."""
    if "a" not in par or "b" not in par:
        par = ("a", "b", *par)
    out = []
    for seg, g in sorted(grouper(lignes, par).items(), key=lambda kv: (-len(kv[1]), str(kv[0]))):
        d = dict(zip(par, seg))
        a, b = d["a"], d["b"]
        apparies = [x for x in g if x.get("meneur")]
        menes = {qui: [x["delai_min"] for x in apparies if x["meneur"] == qui] for qui in (a, b)}
        ens = sum(1 for x in apparies if x["meneur"] == "ensemble")
        n = len(apparies)
        out.append({**d, "apparies": n,
                    "pct_a_devant": _pct(len(menes[a]), n), "pct_b_devant": _pct(len(menes[b]), n),
                    "pct_ensemble": _pct(ens, n),
                    "delai_median_min": median(menes[a] + menes[b]) if menes[a] or menes[b] else None,
                    "seuls_a": sum(1 for x in g if x.get("seul") == a),
                    "seuls_b": sum(1 for x in g if x.get("seul") == b),
                    "insuffisant": n < ECHANTILLON_MIN})
    return out
