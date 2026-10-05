"""Règlement des paris simulés à partir des scores.

Source des scores : les résultats PulseScore du bookmaker du pari (même identifiant de match, pas de
comparaison de noms), avec le score par période. À défaut, le fichier donnees/resultats_manuels.json
(résultats retrouvés à la main) : {"<id du pari>": "gagne" | "perdu" | "rembourse"} ou
{"<match_id>": {"score": [2, 1], "mi_temps": [1, 0], "corners": [7, 3]}}.

Règles : handicaps asiatiques et totaux en quart (x,25 / x,75) partagés en deux demi-mises ;
ligne entière = remboursement en cas d'égalité ; 1N2 et totaux de foot sur le temps réglementaire.
Les corners ne sont pas dans les résultats : réglés avec la saisie manuelle.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

GAIN = {"gagne": 1.0, "demi_gagne": 0.5, "rembourse": 0.0, "demi_perdu": -0.5, "perdu": -1.0}


def gain(statut: str, mise: float, cote: float) -> float:
    f = GAIN[statut]
    return round(mise * f * (cote - 1) if f > 0 else mise * f, 2)


def _ligne_simple(valeur: float) -> str:
    """Résultat d'une ligne non fractionnée : valeur > 0 gagné, = 0 remboursé, < 0 perdu."""
    if abs(valeur) < 1e-9:
        return "rembourse"
    return "gagne" if valeur > 0 else "perdu"


def _ligne_asiatique(valeur: float, ligne: float) -> str:
    """Ligne en quart (ex. -0,75) : moitié de mise sur chaque ligne voisine."""
    if abs((ligne * 4) % 2 - 1) < 1e-9:          # ligne en x,25 ou x,75
        a, b = _ligne_simple(valeur - 0.25), _ligne_simple(valeur + 0.25)
        if a == b:
            return a
        r = {a, b}
        if r == {"gagne", "rembourse"}:
            return "demi_gagne"
        if r == {"perdu", "rembourse"}:
            return "demi_perdu"
        return "rembourse"
    return _ligne_simple(valeur)


def scores_par_periode(sport: str, score: tuple[int, int], periodes: list[tuple[int, int]],
                       libelles: list[str]) -> dict[str, tuple[int, int]]:
    """Scores (domicile, extérieur) pour chaque période commune, d'après le score par période."""
    out: dict[str, tuple[int, int]] = {}
    lab = [str(x).upper() for x in libelles]
    reg = [p for p, l in zip(periodes, lab) if l not in ("OT", "SO", "ET", "AP", "P", "PEN", "TAB")]
    somme = lambda ps: (sum(p[0] for p in ps), sum(p[1] for p in ps))  # noqa: E731
    if sport == "football":
        if len(reg) >= 1:
            out["MT1"] = reg[0]
        if len(reg) >= 2:
            out["MT2"] = reg[1]
            out["MATCH"] = somme(reg[:2])          # temps réglementaire (hors prolongation)
        elif score and not periodes:
            out["MATCH"] = score
    elif sport == "hockey":
        for i, p in enumerate(reg[:3]):
            out[f"P{i + 1}"] = p
        if len(reg) >= 3:
            out["TEMPS_REG"] = somme(reg[:3])
        out["MATCH"] = score                       # prolongation et tirs au but inclus
    elif sport in ("basket", "football_americain"):
        for i, p in enumerate(reg[:4]):
            out[f"QT{i + 1}"] = p
        if len(reg) >= 2:
            out["MT1"] = somme(reg[:2])
        if len(periodes) >= 4:
            out["MT2"] = somme(periodes[2:])       # la 2e mi-temps inclut la prolongation
        out["MATCH"] = score
    elif sport == "tennis":
        for i, p in enumerate(periodes[:2]):
            out[f"SET{i + 1}"] = p
        out["MATCH"] = score                       # sets gagnés
        out["JEUX"] = somme(periodes)              # jeux du match
    else:
        out["MATCH"] = score
    return out


def regler(p: dict, scores: dict[str, tuple[int, int]]) -> str | None:
    """Statut du pari, ou None si les scores ne suffisent pas."""
    m, per, i, ligne = p["marche"], p["periode"], p["issue"], p.get("ligne")
    unite_jeux = m.startswith("JEUX_")
    if m.startswith("CARTONS_"):
        return None
    if m.startswith("CORNERS_"):                   # corners : seulement si saisis à la main
        m = m[8:]
        s = scores.get("CORNERS" if per == "MATCH" else f"CORNERS_{per}")
    elif unite_jeux:
        m = m[5:]
        s = scores.get("JEUX") if per == "MATCH" else scores.get(per)
    elif m.startswith("SETS_"):
        m = m[5:]
        s = scores.get("MATCH")
    else:
        s = scores.get(per)
    if not s:
        return None
    d, e = s
    if m in ("RESULTAT_1N2", "VAINQUEUR"):
        gagnant = "DOM" if d > e else "EXT" if e > d else "NUL"
        if m == "VAINQUEUR" and gagnant == "NUL":
            return "rembourse"
        return "gagne" if gagnant == i else "perdu"
    if m == "DRAW_NO_BET":
        if d == e:
            return "rembourse"
        return "gagne" if (d > e) == (i == "DOM") else "perdu"
    if m == "DOUBLE_CHANCE":
        r = "DOM" if d > e else "EXT" if e > d else "NUL"
        return "gagne" if r in {"HOME_DRAW": ("DOM", "NUL"), "HOME_AWAY": ("DOM", "EXT"),
                                "DRAW_AWAY": ("NUL", "EXT")}[i] else "perdu"
    if m == "HANDICAP":
        v = (d - e + ligne) if i == "DOM" else (e - d - ligne)
        return _ligne_asiatique(v, ligne)
    if m == "HANDICAP_3":
        v = d + ligne - e
        r = "DOM" if v > 0 else "EXT" if v < 0 else "NUL"
        return "gagne" if r == i else "perdu"
    if m in ("TOTAL", "TOTAL_DOM", "TOTAL_EXT"):
        t = {"TOTAL": d + e, "TOTAL_DOM": d, "TOTAL_EXT": e}[m]
        v = (t - ligne) if i == "PLUS" else (ligne - t)
        return _ligne_asiatique(v, ligne)
    if m == "BOTH_TEAMS_TO_SCORE":
        return "gagne" if (d > 0 and e > 0) == (i == "YES") else "perdu"
    if m == "CORRECT_SCORE":
        return "gagne" if f"{d}-{e}" == i else "perdu"
    if m == "HALF_TIME_FULL_TIME":
        mt = scores.get("MT1")
        if not mt:
            return None
        r = lambda a, b: "DOM" if a > b else "EXT" if b > a else "NUL"  # noqa: E731
        return "gagne" if f"{r(*mt)}/{r(d, e)}" == i else "perdu"
    return None


def appliquer(paris: list[dict], resultats: dict[str, dict], manuels: dict, maintenant: datetime | None = None):
    """Règle les paris en cours. `resultats` : match_id -> {"sport", "score", "periodes", "libelles", "final"}."""
    maintenant = maintenant or datetime.now(timezone.utc)
    for p in paris:
        if p["statut"] not in ("en_cours", "a_regler"):
            continue
        statut = manuels.get(p["id"]) if isinstance(manuels.get(p["id"]), str) else None
        if statut is None:
            r = resultats.get(p["match_id"])
            m = manuels.get(p["match_id"])
            if isinstance(m, dict) and m.get("score"):
                sc = {"MATCH": tuple(m["score"])}
                if m.get("mi_temps"):
                    sc["MT1"] = tuple(m["mi_temps"])
                    sc["MT2"] = (sc["MATCH"][0] - sc["MT1"][0], sc["MATCH"][1] - sc["MT1"][1])
                if m.get("temps_reglementaire"):
                    sc["TEMPS_REG"] = tuple(m["temps_reglementaire"])
                if m.get("corners"):
                    sc["CORNERS"] = tuple(m["corners"])
                if m.get("corners_mi_temps"):
                    sc["CORNERS_MT1"] = tuple(m["corners_mi_temps"])
                statut = regler(p, sc)
            elif r and r.get("final"):
                statut = regler(p, scores_par_periode(p["sport"], r["score"], r["periodes"], r["libelles"]))
        if statut in GAIN:
            p["statut"] = statut
            p["gain"] = gain(statut, p["mise"], p["cote"])
            p["regle_le"] = maintenant.isoformat(timespec="seconds")
            continue
        try:
            debut = datetime.fromisoformat(p["debut"].replace("Z", "+00:00"))
        except (AttributeError, ValueError):
            continue
        if maintenant - debut > timedelta(hours=6):
            p["statut"] = "a_regler"              # résultat introuvable : à régler à la main


def lire_resultats_pulsescore(client, bookmaker: str, sport_api: str, sport: str, pages: int = 5) -> dict[str, dict]:
    """Résultats récents d'un bookmaker (archive PulseScore de 30 jours)."""
    out = {}
    for page in range(1, pages + 1):
        d = client.get(f"{bookmaker}/results", {"sport": sport_api, "page": page, "limit": 30})
        if not d or not d.get("results"):
            break
        for r in d["results"]:
            st = r.get("settlement") or {}
            sc = r.get("score") or {}
            ps = r.get("periodScores") or {}
            try:
                score = (int(sc.get("home")), int(sc.get("away")))
            except (TypeError, ValueError):
                continue
            periodes = list(zip(ps.get("home") or [], ps.get("away") or []))
            out[f"{bookmaker}|{r.get('eventId')}"] = {"sport": sport, "score": score, "periodes": periodes,
                                                      "libelles": ps.get("labels") or [],
                                                      "final": bool(st.get("final"))}
        if not d.get("hasNextPage"):
            break
    return out
