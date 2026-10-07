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


def _set_termine(a: int, b: int) -> bool:
    haut, bas = max(a, b), min(a, b)
    return (haut >= 6 and haut - bas >= 2) or (haut == 7 and bas == 6) or (haut >= 10 and haut - bas >= 2)


def scores_par_periode(sport: str, score: tuple[int, int], periodes: list[tuple[int, int]],
                       libelles: list[str]) -> dict:
    """Scores (domicile, extérieur) pour chaque période commune, d'après le score par période.

    Règles appliquées (docs/reglements.md) : au hockey, le vainqueur des tirs au but reçoit un but de plus
    pour les marchés « prolongation incluse » ; au tennis, un super tie-break compte pour un jeu et un set,
    et un abandon est signalé (clé ABANDON) pour appliquer les règles d'abandon.
    """
    out: dict = {}
    lab = [str(x).upper() for x in libelles]
    hors_reg = ("OT", "SO", "ET", "AP", "P", "PEN", "TAB", "EI", "X")
    reg = [p for p, l in zip(periodes, lab) if l not in hors_reg]
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
            prol = [p for p, l in zip(periodes, lab) if l in ("OT", "AP")]
            tab = [p for p, l in zip(periodes, lab) if l in ("SO", "TAB", "PEN")]
            d, e = somme(reg[:3] + prol)
            if tab and tab[0][0] != tab[0][1]:
                d, e = (d + 1, e) if tab[0][0] > tab[0][1] else (d, e + 1)   # un but au vainqueur des tirs au but
            # score final validé (but des tirs au but compris) quand le détail de la séance manque
            out["MATCH"] = tuple(score) if score and not tab else (d, e)
        else:
            out["MATCH"] = score
    elif sport in ("basket", "football_americain"):
        for i, p in enumerate(reg[:4]):
            out[f"QT{i + 1}"] = p
        if len(reg) >= 2:
            out["MT1"] = somme(reg[:2])
        if len(reg) >= 4:
            out["MT2"] = somme(reg[2:4])
            out["TEMPS_REG"] = somme(reg[:4])
        out["MATCH"] = somme(periodes) if periodes else score   # prolongation incluse
    elif sport == "baseball":
        if len(reg) >= 9:
            out["TEMPS_REG"] = somme(reg[:9])     # 9 manches
        if len(reg) >= 5:
            out["5_MANCHES"] = somme(reg[:5])
        out["MATCH"] = score                       # manches supplémentaires incluses
    elif sport == "tennis" and not periodes:
        # score final en sets sans le détail des sets : seuls les marchés sur les sets gagnés sont réglables
        # (jeux et sets précis inconnus, et rien ne permet de conclure à un abandon)
        if score:
            out["MATCH"] = tuple(score)
    elif sport == "tennis":
        sets = []
        for i, (a, b) in enumerate(periodes):
            if max(a, b) >= 10 and i == len(periodes) - 1:   # super tie-break : un jeu, un set
                sets.append(((1, 0) if a > b else (0, 1), True, True))
            else:
                sets.append(((a, b), _set_termine(a, b), False))
        for i, (jeux, termine, _) in enumerate(sets[:2]):
            if termine:
                out[f"SET{i + 1}"] = jeux
        gagnes = (sum(1 for (a, b), t, _ in sets if t and a > b), sum(1 for (a, b), t, _ in sets if t and b > a))
        out["MATCH"] = gagnes
        out["JEUX"] = somme([j for j, _, _ in sets])
        out["SETS_TERMINES"] = sum(1 for _, t, _ in sets if t)
        if sets and (not all(t for _, t, _ in sets) or max(gagnes) < 2):
            out["ABANDON"] = True
    else:
        out["MATCH"] = score
    return out


def _regler_abandon(p: dict, scores: dict) -> str:
    """Tennis, abandon ou disqualification : seuls les paris déjà décidés sont réglés, les autres remboursés.

    Winamax, Unibet, NetBet, PMU : les paris sur une période terminée sont maintenus ; un « plus de X jeux »
    déjà dépassé est gagnant (et le « moins » perdant). Nombre de sets : validé s'il est certain à la fin d'un
    set chez Winamax et Unibet, remboursé chez NetBet (« le set en question n'a pas été mené à son terme »).
    """
    m, per, i, ligne = p["marche"], p["periode"], p["issue"], p.get("ligne")
    if per.startswith("SET"):
        if per in scores:
            return regler({**p}, {k: v for k, v in scores.items() if k != "ABANDON"}) or "rembourse"
        return "rembourse"
    if m in ("JEUX_TOTAL", "JEUX_TOTAL_DOM", "JEUX_TOTAL_EXT"):
        d, e = scores.get("JEUX", (0, 0))
        t = {"JEUX_TOTAL": d + e, "JEUX_TOTAL_DOM": d, "JEUX_TOTAL_EXT": e}[m]
        if t > ligne:
            return "gagne" if i == "PLUS" else "perdu"
        return "rembourse"
    if m == "SETS_TOTAL" and (p.get("bookmaker") or "").lower() != "netbet":
        certains = scores.get("SETS_TERMINES", 0) + 1
        if certains > ligne:
            return "gagne" if i == "PLUS" else "perdu"
        return "rembourse"
    return "rembourse"


SOUS_PERIODES = {"MT1", "MT2", "P1", "P2", "P3", "QT1", "QT2", "QT3", "QT4"}


def regler(p: dict, scores: dict[str, tuple[int, int]]) -> str | None:
    """Statut du pari, ou None si les scores ne suffisent pas."""
    statut = _regler(p, scores)
    if statut is None and p.get("sport") != "tennis":
        statut = _deduire_sans_periode(p, scores)
    return statut


def _deduire_sans_periode(p: dict, scores: dict) -> str | None:
    """Quand le score d'une période manque, certains paris sont quand même tranchés par le score final :
    une équipe ne marque jamais plus dans une période que dans tout le match. Exemples : match fini 0-0 ->
    toutes les périodes à 0-0 ; « mi-temps/fin : X / Y » perdu si Y n'a pas gagné le match ; « score exact
    2-1 à la mi-temps » perdu si le match a fini 1-1 ; « plus de 2,5 buts en 1re mi-temps » perdu s'il y a
    eu 2 buts dans le match."""
    fin = scores.get("MATCH")
    m, per, i, ligne = p["marche"], p["periode"], p["issue"], p.get("ligne")
    if not fin or m.startswith(("CORNERS_", "CARTONS_", "JEUX_", "SETS_")):
        return None
    d, e = fin
    if m == "HALF_TIME_FULL_TIME" and per == "MATCH":
        if (d, e) == (0, 0):
            return _regler(p, {**scores, "MT1": (0, 0)})
        r = "DOM" if d > e else "EXT" if e > d else "NUL"
        return "perdu" if i.split("/")[-1] != r else None
    if per not in SOUS_PERIODES:
        return None
    if (d, e) == (0, 0):
        return _regler(p, {**scores, per: (0, 0)})
    if m == "CORRECT_SCORE" and "-" in i:
        a, b = (int(x) for x in i.split("-"))
        return "perdu" if a > d or b > e else None
    if m == "BOTH_TEAMS_TO_SCORE" and (d == 0 or e == 0):
        return "perdu" if i == "YES" else "gagne"
    if m in ("TOTAL", "TOTAL_DOM", "TOTAL_EXT") and ligne is not None:
        maxi = {"TOTAL": d + e, "TOTAL_DOM": d, "TOTAL_EXT": e}[m]
        if maxi == 0:
            return _regler(p, {**scores, per: (0, 0)})
        if maxi <= ligne - 0.5:                       # même en marquant tout dans la période, sous la ligne
            return "perdu" if i == "PLUS" else "gagne"
    return None


def _regler(p: dict, scores: dict[str, tuple[int, int]]) -> str | None:
    if scores.get("ABANDON"):
        return _regler_abandon(p, scores)
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
                if m.get("periodes"):                 # score de chaque période réglementaire (ex. manches)
                    ps = [tuple(x) for x in m["periodes"]]
                    sc = {**scores_par_periode(p["sport"], sc["MATCH"], ps, [str(i + 1) for i in range(len(ps))]), **sc}
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
                sc = scores_par_periode(p["sport"], r["score"], r["periodes"], r["libelles"])
                if r.get("corners"):
                    sc["CORNERS"] = tuple(r["corners"])
                statut = regler(p, sc)
        if statut in GAIN:
            p["statut"] = statut
            p["gain"] = gain(statut, p["mise"], p["cote"])
            p["regle_le"] = maintenant.isoformat(timespec="seconds")
            continue
        try:
            debut = datetime.fromisoformat(p["debut"].replace("Z", "+00:00"))
        except (AttributeError, ValueError):
            continue
        if maintenant - debut > timedelta(hours=12):
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
