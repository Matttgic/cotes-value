"""Résultats des matchs pour le règlement des paris, validés par des sources fiables.

Les flux de résultats PulseScore des bookmakers français ne disent pas quand un match est fini (Winamax,
Unibet : dernier score vu en direct ; Betclic, NetBet : aucun état ; Unibet : champ score parfois faux).
On règle donc avec des « validateurs », des bookmakers dont le flux marque explicitement les matchs
terminés (sonde du 6/10/2026) : Betfair (Orbit, terminé quand tous ses marchés sont réglés), DraftKings,
Unibet UK, Interwetten, BetMGM (« Finished ») et PMU quand il marque le match terminé.

Un match est retrouvé chez chaque validateur par les noms d'équipes (dans un sens ou l'autre) et l'heure
de début. Le score n'est retenu que si au moins SOURCES_MIN validateurs ont le match terminé et que TOUS
donnent le même score ; les corners, seulement si au moins SOURCES_MIN sources les donnent identiques
(Betfair renvoie 0-0 quand il ne les compte pas). Sinon le pari attend, puis passe « à régler à la main ».
"""
from __future__ import annotations

from datetime import datetime, timedelta

from .correspondance import ressemblance

VALIDATEURS = ["orbitxch", "draftkings", "unibet-uk", "interwetten-de", "betmgm", "pmu"]
ECART_HEURE_MIN = 45
RESSEMBLANCE_MIN = 0.75
PAGES_MAX = 15
SOURCES_MIN = 2


def _heure(s) -> datetime | None:
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def termine(r: dict) -> bool:
    st = r.get("settlement") or {}
    info = str((r.get("score") or {}).get("info") or "").strip().lower()
    return bool(st.get("final")) or info in ("final", "finished", "ended", "ft")


def _corners(r: dict) -> tuple[int, int] | None:
    foot = (r.get("statistics") or {}).get("football") or {}
    try:
        return int(foot["home"]["corners"]), int(foot["away"]["corners"])
    except (KeyError, TypeError, ValueError):
        return None


def libelles_periodes(sport: str, libelles: list | None, n: int) -> list[str]:
    """Libellés des périodes ; quand la source n'en donne pas, déduits du rang (au-delà du temps
    réglementaire : prolongation, tirs au but, manches supplémentaires)."""
    if libelles and len(libelles) == n:
        return [str(x).upper() for x in libelles]
    reg = {"football": 2, "hockey": 3, "basket": 4, "football_americain": 4, "baseball": 9, "handball": 2}.get(sport)
    out = []
    for i in range(n):
        if reg is None or i < reg:
            out.append(str(i + 1))
        elif sport == "hockey":
            out.append("OT" if i == reg else "SO")
        elif sport == "baseball":
            out.append("X")
        elif sport == "football":
            out.append("ET" if i < reg + 2 else "PEN")
        else:
            out.append("OT")
    return out


def lire(client, bookmaker: str, sport_api: str, sport: str, depuis: datetime) -> list[dict]:
    """Matchs terminés d'un validateur, du plus récent jusqu'à `depuis` (début des matchs)."""
    out = []
    for page in range(1, PAGES_MAX + 1):
        d = client.get(f"{bookmaker}/results", {"sport": sport_api, "page": page, "limit": 30})
        if not d or not d.get("results"):
            break
        for r in d["results"]:
            sc = r.get("score") or {}
            try:
                score = (int(sc.get("home")), int(sc.get("away")))
            except (TypeError, ValueError):
                continue
            if not termine(r):
                continue
            ps = r.get("periodScores") or {}
            periodes = list(zip(ps.get("home") or [], ps.get("away") or []))
            out.append({"source": bookmaker, "sport": sport, "domicile": r.get("home"), "exterieur": r.get("away"),
                        "debut": _heure(r.get("startTime")), "score": score, "periodes": periodes,
                        "libelles": libelles_periodes(sport, ps.get("labels"), len(periodes)),
                        "corners": _corners(r)})
        dernier = _heure(d["results"][-1].get("startTime"))
        if not d.get("hasNextPage") or (dernier and dernier < depuis):
            break
    return out


def _oriente(r: dict, inverse: bool) -> dict:
    if not inverse:
        return r
    sw = lambda t: (t[1], t[0]) if t else t       # noqa: E731
    return {**r, "domicile": r["exterieur"], "exterieur": r["domicile"], "score": sw(r["score"]),
            "periodes": [sw(p) for p in r["periodes"]], "corners": sw(r["corners"])}


def retrouver(p: dict, enregistrements: list[dict]) -> list[dict]:
    """Le match du pari chez chaque validateur (le meilleur par source), orienté comme le pari."""
    debut = _heure(p.get("debut"))
    if not debut:
        return []
    meilleurs: dict[str, tuple[float, dict]] = {}
    for r in enregistrements:
        if r["sport"] != p["sport"] or not r["debut"] or abs((r["debut"] - debut).total_seconds()) > ECART_HEURE_MIN * 60:
            continue
        direct = min(ressemblance(p["domicile"], r["domicile"]), ressemblance(p["exterieur"], r["exterieur"]))
        inverse = min(ressemblance(p["domicile"], r["exterieur"]), ressemblance(p["exterieur"], r["domicile"]))
        score = max(direct, inverse)
        if score < RESSEMBLANCE_MIN:
            continue
        if r["source"] not in meilleurs or score > meilleurs[r["source"]][0]:
            meilleurs[r["source"]] = (score, _oriente(r, inverse > direct))
    return [r for _, r in meilleurs.values()]


def _periodes_coherentes(sport: str, r: dict) -> bool:
    if not r["periodes"]:
        return False
    d, e = sum(x[0] for x in r["periodes"]), sum(x[1] for x in r["periodes"])
    if (d, e) == r["score"]:
        return True
    # hockey : le vainqueur des tirs au but peut être crédité d'un but dans le score final
    return sport == "hockey" and abs(d - r["score"][0]) + abs(e - r["score"][1]) == 1


def consensus(p: dict, enregistrements: list[dict]) -> dict | None:
    """Résultat validé du match d'un pari, ou None (pas encore terminé chez un validateur, ou désaccord)."""
    trouves = retrouver(p, enregistrements)
    if len(trouves) < SOURCES_MIN or len({r["score"] for r in trouves}) > 1:
        return None
    score = trouves[0]["score"]
    avec_periodes = [r for r in trouves if _periodes_coherentes(p["sport"], r)]
    if len({tuple(r["periodes"]) for r in avec_periodes}) > 1:
        avec_periodes = []                           # sources en désaccord sur les périodes : on s'en passe
    corners = [r["corners"] for r in trouves if r["corners"] is not None and r["corners"] != (0, 0)]
    base = avec_periodes[0] if avec_periodes else None
    return {"sport": p["sport"], "score": score, "final": True,
            "periodes": base["periodes"] if base else [], "libelles": base["libelles"] if base else [],
            "corners": corners[0] if len(corners) >= SOURCES_MIN and len(set(corners)) == 1 else None,
            "sources": sorted(r["source"] for r in trouves)}


def a_lire(paris: list[dict], maintenant: datetime, apres_debut_h: float = 2) -> dict[str, datetime]:
    """Sports à lire chez les validateurs -> début du plus ancien match encore à régler."""
    out: dict[str, datetime] = {}
    for p in paris:
        if p["statut"] not in ("en_cours", "a_regler"):
            continue
        debut = _heure(p.get("debut"))
        if debut and maintenant - debut > timedelta(hours=apres_debut_h) and maintenant - debut < timedelta(days=7):
            out[p["sport"]] = min(out.get(p["sport"], debut), debut - timedelta(hours=1))
    return out
