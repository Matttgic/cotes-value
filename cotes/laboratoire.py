"""Famille figée de 36 règles, sélection causale et métriques auditables.

La sélection ne lit jamais gain, statut, règlement ou CLV. Les coupures de
connaissance s'appliquent seulement à l'évaluation et au choix des finalistes.
"""
from __future__ import annotations

import random
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from math import isfinite
from statistics import mean
from zoneinfo import ZoneInfo

from .reglement import GAIN, gain

PARIS = ZoneInfo("Europe/Paris")
SEED = 20261014
MISE = 10.0
DEBUT_ETUDE = "2026-10-07T00:00:00+02:00"
DEBUT_SUIVI = "2026-10-14T12:00:00+00:00"
PERIODES = (
    ("construction", DEBUT_ETUDE, "2026-10-11T00:00:00+02:00"),
    ("validation", "2026-10-11T00:00:00+02:00", "2026-10-13T00:00:00+02:00"),
    ("test", "2026-10-13T00:00:00+02:00", "2026-10-14T00:00:00+02:00"),
)
BOOKMAKERS = {"Winamax", "Betclic", "Unibet", "PMU"}
MARCHES = {"RESULTAT_1N2", "VAINQUEUR", "DOUBLE_CHANCE", "DRAW_NO_BET", "TOTAL", "HANDICAP"}


def heure(value) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo is not None else None
    except (ValueError, TypeError):
        return None


def nombre(value) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        n = float(value)
        return n if isfinite(n) else None
    except (ValueError, TypeError):
        return None


@dataclass(frozen=True)
class Regle:
    id: str
    reference: str
    cote_min: float
    cote_max: float
    edge_min: float
    avance_max_h: int
    edge_max: float = .12

    @property
    def nom(self) -> str:
        return (f"{self.reference} · {self.cote_min:g}–{self.cote_max:g} · "
                f"≥ {100*self.edge_min:g} % · ≤ {self.avance_max_h} h")

    def dict(self) -> dict:
        return {**asdict(self), "nom": self.nom}


REGLES = tuple(Regle(f"{code}-{bas:g}-{haut:g}-e{round(edge*100)}-h{h}", ref, bas, haut, edge, h)
               for code, ref in (("PIN", "Pinnacle"), ("BET", "Betfair"), ("POL", "Polymarket"))
               for bas, haut in ((1.3, 2.0), (1.5, 3.0), (2.0, 5.0))
               for edge in (.02, .05) for h in (12, 36))


def refus_qualite(p: dict) -> str | None:
    if p.get("bookmaker") not in BOOKMAKERS or p.get("suspect"):
        return "bookmaker_ou_suspect"
    t, debut, lu = (heure(p.get(k)) for k in ("detecte", "debut", "lu_reference"))
    if not t or not debut or not lu or not 0 <= (t-lu).total_seconds() <= 900 or debut <= t:
        return "dates_ou_fraicheur"
    cote, juste, edge = (nombre(p.get(k)) for k in ("cote", "cote_juste", "ecart"))
    if cote is None or juste is None or edge is None or cote <= 1 or juste <= 1:
        return "cotes_invalides"
    if abs(cote/juste - 1 - edge) > .002:
        return "edge_incoherent"
    preuve = p.get("preuve_prise") or {}
    score = nombre(preuve.get("ressemblance_noms"))
    if (not preuve.get("match_id_reference") or score is None or score < .85
            or (preuve.get("controle") or {}).get("statut") != "conforme"):
        return "preuve_insuffisante"
    marche = p.get("marche")
    if marche not in MARCHES or p.get("periode") not in ("MATCH", "TEMPS_REG"):
        return "marche_ou_periode"
    if p.get("sport") in ("tennis", "volley") and marche != "VAINQUEUR":
        return "unite_ambigue"
    if marche in ("TOTAL", "HANDICAP"):
        ligne = nombre(p.get("ligne"))
        if ligne is None or not (ligne*2).is_integer():
            return "ligne_fractionnee_ou_absente"
    issues = {"TOTAL": ("PLUS", "MOINS"), "RESULTAT_1N2": ("DOM", "EXT", "NUL"),
              "DOUBLE_CHANCE": ("HOME_DRAW", "HOME_AWAY", "DRAW_AWAY")}
    if p.get("issue") not in issues.get(marche, ("DOM", "EXT")):
        return "issue_invalide"
    return None


def cle_match(p: dict) -> tuple:
    return p.get("sport"), p.get("reference"), str(p["preuve_prise"]["match_id_reference"])


def admissible(p: dict, r: Regle, depuis: str) -> bool:
    if p.get("reference") != r.reference or not heure(p.get("detecte")):
        return False
    if heure(p["detecte"]) < heure(depuis) or refus_qualite(p):
        return False
    return (r.cote_min <= p["cote"] <= r.cote_max and r.edge_min <= p["ecart"] <= r.edge_max
            and (heure(p["debut"])-heure(p["detecte"])).total_seconds() <= r.avance_max_h*3600)


def selectionner(paris: list[dict], r: Regle, depuis: str = DEBUT_ETUDE) -> list[dict]:
    rows = [p for p in paris if admissible(p, r, depuis)]
    rows.sort(key=lambda p: (heure(p["detecte"]), -p["ecart"], -p["cote"], p["bookmaker"], str(p["id"])))
    vus, out = set(), []
    for p in rows:
        key = cle_match(p)
        if key not in vus:
            vus.add(key)
            out.append(p)
    return out


def clv(p: dict) -> float | None:
    c = nombre(p.get("clv"))
    lu, debut = heure(p.get("cloture_lue")), heure(p.get("debut"))
    return c if c is not None and lu and debut and 0 < (debut-lu).total_seconds() <= 1800 else None


def intervalle_roi(retours: list[float], repetitions: int = 5000) -> list[float] | None:
    """IC percentile par match (une mise par match), conditionnel à la règle fixée.

    Ni correction des essais multiples ni modélisation de la dépendance entre
    rencontres d'une même journée. Ne pas interpréter comme une preuve de profit.
    """
    if len(retours) < 2:
        return None
    rng = random.Random(SEED)
    n = len(retours)
    sims = sorted(sum(rng.choices(retours, k=n))/n for _ in range(repetitions))
    return [round(sims[int((repetitions-1)*q)]*100, 2) for q in (.025, .975)]


def resume(rows: list[dict], connu_avant: str, incertitude: bool = True) -> dict:
    cutoff = heure(connu_avant)
    assert cutoff is not None
    regles = [p for p in rows if p.get("statut") in GAIN and heure(p.get("regle_le"))
              and heure(p["detecte"]) <= heure(p["regle_le"]) < cutoff]
    gains = [gain(p["statut"], MISE, p["cote"]) for p in regles]
    cs = [clv(p) for p in regles if clv(p) is not None]
    ids = {p["id"] for p in regles}
    attente = [p for p in rows if p["id"] not in ids]
    n, total = len(regles), sum(gains)
    mises = n*MISE
    par_jour = defaultdict(float)
    exposition = Counter(heure(p["detecte"]).astimezone(PARIS).date().isoformat() for p in rows)
    cumul = sommet = dd = 0.0
    for p in sorted(regles, key=lambda p: (heure(p["regle_le"]), p["id"])):
        g = gain(p["statut"], MISE, p["cote"])
        cumul += g
        sommet = max(sommet, cumul)
        dd = max(dd, sommet-cumul)
        par_jour[heure(p["debut"]).astimezone(PARIS).date().isoformat()] += g
    best = max([0]+gains)
    g_degrade = sum(gain(p["statut"], MISE, max(1.01, p["cote"]*.99)) for p in regles)
    full_stakes = len(rows)*MISE
    return {"paris": len(rows), "regles": n, "attente": len(attente),
            "gagnes": sum(p["statut"] in ("gagne", "demi_gagne") for p in regles),
            "perdus": sum(p["statut"] in ("perdu", "demi_perdu") for p in regles),
            "rembourses": sum(p["statut"] == "rembourse" for p in regles),
            "gain": round(total, 2), "mise": mises, "roi": round(100*total/mises, 2) if n else None,
            "ic95": intervalle_roi([g/MISE for g in gains]) if incertitude else None,
            "clv": round(100*mean(cs), 2) if cs else None, "clv_n": len(cs),
            "couverture_clv": round(100*len(cs)/n, 1) if n else None,
            "drawdown": round(dd, 2), "meilleur_gain": best, "gain_sans_meilleur": round(total-best, 2),
            "roi_cote_moins_1pct": round(100*g_degrade/mises, 2) if n else None,
            "roi_attente_pessimiste": round(100*(total-MISE*len(attente))/full_stakes, 2) if rows else None,
            "roi_attente_optimiste": round(100*(total+sum(MISE*(p["cote"]-1) for p in attente))/full_stakes, 2) if rows else None,
            "profit_journalier": {d: round(g, 2) for d, g in sorted(par_jour.items())},
            "jours_positifs": sum(g > 0 for g in par_jour.values()), "jours_actifs": len(par_jour),
            "mise_max_jour": max(exposition.values(), default=0)*MISE,
            "reglements_manuels": sum((p.get("preuve_reglement") or {}).get("origine") != "automatique" for p in regles)}


def evaluer(rows: list[dict], releve: str) -> dict:
    out = {}
    for nom, debut, fin in PERIODES:
        partie = [p for p in rows if heure(debut) <= heure(p["debut"]) < heure(fin)]
        out[nom] = resume(partie, fin if nom != "test" else releve)
    return out


def passe(s: dict, minimum: int) -> bool:
    return (s["regles"] >= minimum and s["roi"] is not None and s["roi"] > 0
            and s["clv"] is not None and s["clv"] > 0 and (s["couverture_clv"] or 0) >= 50)


def classer(resultats: list[dict]) -> dict:
    def rang(x, periode):
        s = x[periode]
        return (-(s["ic95"] or [-100, 100])[0], -s["regles"], x["regle"]["id"])
    finalistes = sorted([r for r in resultats if passe(r["construction"], 20)],
                        key=lambda r: rang(r, "construction"))[:3]
    candidats = sorted([r for r in finalistes if passe(r["validation"], 10)],
                       key=lambda r: rang(r, "validation"))
    choix = candidats[0] if candidats else None
    return {"finalistes": [r["regle"]["id"] for r in finalistes],
            "candidate": choix["regle"]["id"] if choix else None,
            "test_reussi": bool(choix and passe(choix["test"], 10)),
            "rentabilite_demontree": False}


def audit(paris: list[dict]) -> dict:
    vrais = [p for p in paris if p.get("reference") != "Pinnacle brut"]
    refs = {r.reference for r in REGLES}
    donnees = [p for p in vrais if p.get("reference") in refs]
    incoherents, dates, groupes = [], [], defaultdict(list)
    for p in vrais:
        if p.get("statut") in GAIN:
            mise, cote, g = (nombre(p.get(k)) for k in ("mise", "cote", "gain"))
            if mise is None or cote is None or g is None or abs(g-gain(p["statut"], mise, cote)) > .011:
                incoherents.append(p["id"])
            if (not heure(p.get("regle_le")) or not heure(p.get("detecte"))
                    or heure(p["regle_le"]) < heure(p["detecte"])):
                dates.append(p["id"])
            key = tuple(p.get(k) for k in ("match_id", "marche", "periode", "ligne", "issue"))
            groupes[key].append(p)
    conflits = [sorted({p["id"] for p in group}) for group in groupes.values()
                if len({p["statut"] for p in group}) > 1]
    return {"lignes": len(paris), "temoin_brut": len(paris)-len(vrais), "vraies_references": len(vrais),
            "ids_dupliques": len(paris)-len({p["id"] for p in paris}),
            "premiere_detection": min((p["detecte"] for p in paris), default=None),
            "derniere_detection": max((p["detecte"] for p in paris), default=None),
            "par_reference": dict(Counter(p["reference"] for p in vrais)),
            "qualite_3_references": dict(Counter(refus_qualite(p) or "admissible" for p in donnees)),
            "gains_incoherents": incoherents, "dates_reglement_invalides": dates,
            "conflits_reglement_meme_selection": conflits}


def suivi_futur(paris: list[dict], depuis: str, maintenant: str | None = None) -> list[dict]:
    """Évalue les 36 règles indépendamment ; leurs mises ne doivent pas être additionnées.

    Filtre de date avant les 36 sélections pour garder le coût du site faible.
    Aucun choix automatique de gagnante ni modification des paramètres.
    """
    cutoff = maintenant or datetime.now(timezone.utc).isoformat()
    rows = [p for p in paris if heure(p.get("detecte")) and heure(depuis) <= heure(p["detecte"]) < heure(cutoff)]
    out = []
    for r in REGLES:
        selection = selectionner(rows, r, depuis)
        out.append({"id": r.id, **resume(selection, cutoff, incertitude=False),
                    "ids_recents": [p["id"] for p in selection[-30:]]})
    return out
