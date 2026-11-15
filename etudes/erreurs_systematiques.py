"""Erreurs systématiques des bookmakers français : sur quels marchés leurs cotes battent-elles la clôture Pinnacle ?

    python etudes/erreurs_systematiques.py --donnees CHEMIN [--markdown docs/erreurs-systematiques-tableaux.md]

CHEMIN = branche « donnees » extraite, avec tous les jours de ``opportunites/`` (pour la cause « modèle copié »).
Lecture seule, graine fixe : deux exécutions donnent les mêmes chiffres. Demande numpy (requirements-dev.txt).

Mesure principale : la CLV contre la clôture Pinnacle (cotes/protocole.py › clv_pinnacle) des paris uniques réglés,
par segment (type de marché, période, sport, liquidité, délai, issue, bookmaker × marché). Une CLV positive veut
dire que la cote française était au-dessus de la cote juste où le marché sharp a fini : une vraie erreur du
bookmaker, pas un bruit de la référence. Intervalle et p-valeur : bootstrap studentisé par match (comme
etudes/avantage_reel.py), correction de Holm sur tous les segments testés, dans les deux sens.

Stabilité : même mesure sur la première et la seconde moitié de la période (coupée à la date médiane des paris
mesurés), et part des semaines où la CLV du segment est positive.

Cause probable, sur les paris depuis le 25/10/2026 (mouvement Pinnacle enregistré) :
- « modèle copié » : la même cote (même cycle, même sélection de référence) est repérée chez un autre bookmaker
  français ;
- « mise à jour lente » : la probabilité juste Pinnacle de l'issue a monté d'au moins 0,5 % peu avant la prise
  (cotes/mouvement.py) et le bookmaker ne l'a pas suivie ;
- « marge mal répartie » : ni l'un ni l'autre, alors que le marché du bookmaker garde une marge normale (TRJ ≤ 97 %).

Population entière (pas seulement les paris) : ``controle.json`` garde, par bookmaker × sport × marché × période, les
300 derniers rapports cote française / cote juste Pinnacle de toutes les cotes appariées ; part au-dessus de 1.
"""
from __future__ import annotations

import argparse
import gzip
import json
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import timedelta
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cotes import reglement, simulation, stockage  # noqa: E402
from cotes.evenements import identites  # noqa: E402
from cotes.protocole import clv_pinnacle  # noqa: E402
from etudes.avantage_reel import grappes, heure, holm, rapport  # noqa: E402

GRAINE = 20261115
TIRAGES = 20000
MIN_PARIS = 40                    # CLV mesurées minimum pour tester un segment
MIN_MATCHS = 15
DEBUT_CAUSES = "2026-10-25T16:00"  # mouvement Pinnacle et limite de mise enregistrés depuis
MOUVEMENT_MIN = 0.005              # probabilité juste Pinnacle +0,5 % avant la prise
TRJ_NORMAL = 0.97

FAMILLES_MARCHE = {
    "RESULTAT_1N2": "1N2 / vainqueur", "VAINQUEUR": "1N2 / vainqueur",
    "TOTAL": "Total", "JEUX_TOTAL": "Total", "SETS_TOTAL": "Total",
    "TOTAL_DOM": "Total d'une équipe", "TOTAL_EXT": "Total d'une équipe", "JEUX_TOTAL_DOM": "Total d'une équipe",
    "JEUX_TOTAL_EXT": "Total d'une équipe",
    "HANDICAP": "Handicap", "HANDICAP_3": "Handicap à 3 issues", "JEUX_HANDICAP": "Handicap", "SETS_HANDICAP": "Handicap",
    "CORRECT_SCORE": "Score exact", "HALF_TIME_FULL_TIME": "Mi-temps / fin", "BOTH_TEAMS_TO_SCORE": "Les deux marquent",
    "DOUBLE_CHANCE": "Double chance", "DRAW_NO_BET": "Remboursé si nul",
}
PERIODES = {"MATCH": "Match entier", "TEMPS_REG": "Temps réglementaire", "MT1": "1re mi-temps"}


def famille_marche(p: dict) -> str:
    return FAMILLES_MARCHE.get(p.get("marche"), "Autre marché")


def periode(p: dict) -> str:
    return PERIODES.get(p.get("periode"), "Autre partie (MT2, quart-temps, set, période)")


def sport(p: dict) -> str:
    return p["sport"] if p["sport"] in ("football", "basket", "hockey", "tennis", "volley", "handball") else "autres sports"


def liquidite(p: dict) -> str | None:
    lim = p.get("limite_pinnacle")
    if not isinstance(lim, (int, float)) or isinstance(lim, bool):
        return None
    return "limite Pinnacle ≤ 300 €" if lim <= 300 else ("limite Pinnacle 300 à 1 500 €" if lim <= 1500
                                                          else "limite Pinnacle > 1 500 €")


def delai(p: dict) -> str | None:
    t, d = heure(p.get("detecte")), heure(p.get("debut"))
    if not t or not d:
        return None
    h = (d - t).total_seconds() / 3600
    return "moins d'1 h avant" if h < 1 else ("1 à 6 h avant" if h < 6 else ("6 à 24 h avant" if h < 24 else "plus de 24 h avant"))


PLAFOND = 5.0      # au-dessus, la CLV ne s'est pas montrée liée au ROI (docs/avantage-reel.md, 3)


def segments(paris: list[dict]) -> list[tuple[str, str, list[dict]]]:
    """Familles mesurées sur les cotes ≤ 5 ; les marchés à grosses cotes (score exact…) à part."""
    out = []
    grosses = [p for p in paris if p["cote"] > PLAFOND]
    paris = [p for p in paris if p["cote"] <= PLAFOND]

    def par(famille, cle, filtre=lambda p: True, minimum=MIN_PARIS):
        groupes = defaultdict(list)
        for p in paris:
            if filtre(p):
                k = cle(p)
                if k is not None:
                    groupes[k].append(p)
        for k, ps in sorted(groupes.items(), key=lambda kv: -len(kv[1])):
            if len(ps) >= minimum:
                out.append((famille, k, ps))

    par("Type de marché", famille_marche)
    par("Période", periode)
    par("Sport", sport)
    par("Liquidité du match", liquidite)
    par("Délai avant le match", delai)
    par("Issue (1N2)", lambda p: {"DOM": "1N2 : domicile", "NUL": "1N2 : nul", "EXT": "1N2 : extérieur"}.get(p["issue"]),
        lambda p: p["marche"] == "RESULTAT_1N2")
    par("Issue (totaux)", lambda p: {"PLUS": "Total : plus", "MOINS": "Total : moins"}.get(p["issue"]),
        lambda p: famille_marche(p) in ("Total", "Total d'une équipe"))
    par("Bookmaker × marché", lambda p: f"{p['bookmaker']} · {famille_marche(p)}")
    par("Bookmaker × période", lambda p: f"{p['bookmaker']} · {periode(p)}", lambda p: p["periode"] != "MATCH")
    paris = grosses
    par("Grosses cotes (> 5) par marché", famille_marche)
    par("Grosses cotes (> 5) par bookmaker", lambda p: p["bookmaker"])
    return out


# ---------------------------------------------------------------- causes

def index_opportunites(donnees: Path) -> tuple[dict, dict]:
    """(pari -> cycle et sélection de référence, sélection de référence d'un cycle -> {bookmaker: cote})."""
    vers_cycle, par_selection = {}, defaultdict(dict)
    for f in sorted((donnees / "opportunites").glob("*.jsonl.gz")):
        with gzip.open(f, "rt", encoding="utf-8") as g:
            for ligne in g:
                o = json.loads(ligne)
                if not o.get("cycle_id") or not o.get("match_id_reference"):
                    continue
                ref = (o["cycle_id"], str(o["match_id_reference"]), o["marche"], o["periode"], o.get("ligne"), o["issue"],
                       o.get("reference"))
                par_selection[ref][o["bookmaker"]] = o["cote"]
                vers_cycle[(o["bookmaker"], o["match_id"], o["marche"], o["periode"], o.get("ligne"), o["issue"],
                            o["detecte"])] = ref
    return vers_cycle, par_selection


def paires_copiees(paris: list[dict], vers_cycle: dict, par_selection: dict) -> dict:
    """Pour les paris dont le cycle est connu : part où un autre bookmaker affiche la même cote, par paire."""
    connus, paires = Counter(), Counter()
    for p in paris:
        ref = vers_cycle.get((p["bookmaker"], p["match_id"], p["marche"], p["periode"], p.get("ligne"), p["issue"],
                              p["detecte"]))
        if ref is None:
            continue
        connus[p["bookmaker"]] += 1
        for b, c in (par_selection.get(ref) or {}).items():
            if b != p["bookmaker"] and abs(c - p["cote"]) < 1e-9:
                paires[f"{p['bookmaker']} = {b}"] += 1
    return {"connus": dict(connus), "paires": dict(paires.most_common(12))}


def causes(ps: list[dict], vers_cycle: dict, par_selection: dict) -> dict:
    recents = [p for p in ps if p["detecte"] >= DEBUT_CAUSES and p.get("mouvement_pinnacle") is not None]
    if not recents:
        return {"paris": 0}
    copie = lent = marge = 0
    for p in recents:
        ref = vers_cycle.get((p["bookmaker"], p["match_id"], p["marche"], p["periode"], p.get("ligne"), p["issue"],
                              p["detecte"]))
        autres = {b: c for b, c in (par_selection.get(ref) or {}).items() if b != p["bookmaker"]}
        if any(abs(c - p["cote"]) < 1e-9 for c in autres.values()):
            copie += 1
        elif (p.get("mouvement_pinnacle") or 0) >= MOUVEMENT_MIN:
            lent += 1
        elif (p.get("trj_bookmaker") or 1) <= TRJ_NORMAL:
            marge += 1
    n = len(recents)
    return {"paris": n, "copie": copie / n, "lent": lent / n, "marge": marge / n, "autre": 1 - (copie + lent + marge) / n}


# ---------------------------------------------------------------- mesures

def mesurer(ps: list[dict], clv: dict, evenement, coupure: str, rng) -> dict:
    avec = [p for p in ps if id(p) in clv]
    out = {"paris": len(ps), "mesures": len(avec), "matchs": len({evenement(p) for p in avec}),
           "ecart_prise": float(np.mean([p["ecart"] for p in ps])),
           "cote_moyenne": float(np.mean([p["cote"] for p in ps])),
           "roi": sum(p["gain"] or 0 for p in ps) / sum(p["mise"] for p in ps)}
    if not avec:
        return out
    v = np.array([clv[id(p)] for p in avec])
    out.update(clv=float(v.mean()), part_positive=float((v > 0).mean()))
    if len(avec) >= MIN_PARIS and out["matchs"] >= MIN_MATCHS:
        cles = [evenement(p) for p in avec]
        b = rapport(*grappes(v, np.ones(len(v)), cles), TIRAGES, rng)
        out.update(ic=b["ic"], p_pos=b["p_pos"], p_neg=b["p_neg"])
        g = rapport(*grappes(np.array([p["gain"] or 0.0 for p in ps]), np.array([p["mise"] for p in ps]),
                             [evenement(p) for p in ps]), TIRAGES, rng)
        out["roi_ic"] = g["ic"]
        y = np.array([(p["gain"] or 0.0) / p["mise"] for p in avec])
        e = rapport(*grappes(y - v, np.ones(len(v)), cles), TIRAGES, rng)
        out["roi_moins_clv_ic"] = e["ic"]
    for nom, partie in (("avant", [p for p in avec if p["detecte"] < coupure]),
                        ("apres", [p for p in avec if p["detecte"] >= coupure])):
        if len(partie) >= 20 and len({evenement(p) for p in partie}) >= 8:
            w = np.array([clv[id(p)] for p in partie])
            b = rapport(*grappes(w, np.ones(len(w)), [evenement(p) for p in partie]), TIRAGES, rng)
            out[nom] = {"n": len(partie), "clv": float(w.mean()), "ic": b["ic"]}
        elif partie:
            out[nom] = {"n": len(partie), "clv": float(np.mean([clv[id(p)] for p in partie])), "ic": None}
    semaines = defaultdict(list)
    for p in avec:
        t = heure(p["detecte"])
        semaines[(t - timedelta(days=t.weekday())).date().isoformat()].append(clv[id(p)])
    pleines = {s: float(np.mean(x)) for s, x in semaines.items() if len(x) >= 10}
    out["semaines"] = {"positives": sum(x > 0 for x in pleines.values()), "total": len(pleines)}
    return out


def controle_population(donnees: Path) -> list[dict]:
    """Rapports cote française / cote juste Pinnacle de toutes les cotes appariées (controle.json)."""
    doc = json.loads((donnees / "controle.json").read_text(encoding="utf-8"))
    groupes = defaultdict(list)
    for g in (doc.get("groupes") or {}).values():
        fam = FAMILLES_MARCHE.get(g.get("marche"), None)
        if fam is None or g.get("statut") != "conforme":
            continue
        per = PERIODES.get(g.get("periode"), "Autre partie (MT2, quart-temps, set, période)")
        r = [x for x in g.get("rapports") or [] if isinstance(x, (int, float))]
        groupes[(g["bookmaker"], fam, per)] += r
        groupes[("tous", fam, per)] += r
    out = []
    for (b, fam, per), r in groupes.items():
        if len(r) >= 100:
            a = np.array(r)
            out.append({"bookmaker": b, "marche": fam, "periode": per, "n": len(a), "mediane": float(np.median(a)),
                        "au_dessus": float((a > 1).mean()), "au_dessus_3": float((a > 1.03).mean())})
    return sorted(out, key=lambda x: -x["au_dessus"])


def props(donnees: Path, rng) -> dict:
    doc = json.loads((donnees / "props_papier.json").read_text(encoding="utf-8"))
    regles = [p for p in doc.get("paris") or [] if p.get("statut") in reglement.GAIN]
    mes = [p for p in regles if isinstance(p.get("clv"), (int, float))]
    out = {"papiers": len(doc.get("paris") or []), "regles": len(regles), "mesures": len(mes),
           "du": min((p.get("debut") or "")[:10] for p in doc.get("paris") or [{}]) if doc.get("paris") else None}
    if len(mes) >= 20:
        v = np.array([p["clv"] for p in mes])
        b = rapport(*grappes(v, np.ones(len(v)), [p.get("match_id_reference") or p["match_id"] for p in mes]),
                    TIRAGES, rng)
        out.update(clv=float(v.mean()), ic=b["ic"], part_positive=float((v > 0).mean()),
                   roi=sum(p["gain"] or 0 for p in regles) / sum(p["mise"] for p in regles),
                   par_bookmaker=dict(Counter(p["bookmaker"] for p in mes)))
    return out


def props_instantane(donnees: Path) -> dict:
    """Props du dernier cycle (props_joueurs.json) : rapport cote française / cote juste, par bookmaker."""
    doc = json.loads((donnees / "props_joueurs.json").read_text(encoding="utf-8"))
    out = {"maj": doc.get("maj")}
    par = defaultdict(list)
    for x in doc.get("lignes") or []:
        if x.get("cote_juste"):
            par[x["bookmaker"]].append(x["cote"] / x["cote_juste"])
    for b, r in par.items():
        a = np.array(r)
        out[b] = {"n": len(a), "mediane": float(np.median(a)), "au_dessus": float((a > 1).mean())}
    return out


def analyser(donnees: Path) -> dict:
    rng = np.random.default_rng(GRAINE)
    tous = stockage.fusionner_paris(stockage.lire_archives(donnees), json.loads((donnees / "paris.json").read_text()))
    clv = clv_pinnacle(tous)
    liens = identites(tous)
    evenement = lambda p: liens[id(p)]  # noqa: E731
    uniques = simulation.premiers_par_selection(tous)
    paris = [p for p in tous if id(p) in uniques and p.get("statut") in reglement.GAIN]
    mesures = sorted(p["detecte"] for p in paris if id(p) in clv)
    coupure = mesures[len(mesures) // 2]
    vers_cycle, par_selection = index_opportunites(donnees)
    lignes = []
    for famille, nom, ps in segments(paris):
        x = mesurer(ps, clv, evenement, coupure, rng)
        x.update(famille=famille, nom=nom, causes=causes(ps, vers_cycle, par_selection))
        lignes.append(x)
    testees = [x for x in lignes if x.get("p_pos") is not None]
    corrigees = holm([min(1.0, 2 * min(x["p_pos"], x["p_neg"])) for x in testees])
    for x, p in zip(testees, corrigees):
        x["p_holm"] = p
    tout = mesurer(paris, clv, evenement, coupure, rng)
    tout["causes"] = causes(paris, vers_cycle, par_selection)
    copies = paires_copiees(paris, vers_cycle, par_selection)
    try:
        commit = subprocess.run(["git", "-C", str(donnees), "log", "-1", "--format=%h du %cI"], capture_output=True,
                                text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        commit = "inconnu"
    return {"commit_donnees": commit, "paris_uniques_regles": len(paris), "clv_pinnacle": len(mesures),
            "du": paris and min(p["detecte"] for p in paris)[:10], "au": paris and max(p["detecte"] for p in paris)[:10],
            "coupure": coupure[:16], "tests": len(testees), "ensemble": tout, "lignes": lignes,
            "copies": copies, "controle": controle_population(donnees), "props": props(donnees, rng),
            "props_instantane": props_instantane(donnees),
            "cotes_boostees": sum("boost" in (p.get("libelle_bookmaker") or "").lower() for p in tous)}


# ---------------------------------------------------------------- sortie

def pct(x, d=2, signe=True) -> str:
    if x is None:
        return "—"
    return (f"{100 * x:+.{d}f} %" if signe else f"{100 * x:.{d}f} %").replace(".", ",").replace("-", "−")


def ic(v) -> str:
    return "—" if not v else f"[{pct(v[0])} ; {pct(v[1])}]"


def moitie(x: dict | None) -> str:
    if not x:
        return "—"
    return f"{pct(x['clv'])} {ic(x['ic'])} ({x['n']})"


def markdown(r: dict) -> str:
    out = [f"# Erreurs systématiques : tableaux complets\n\nProduit par `python etudes/erreurs_systematiques.py` sur "
           f"« donnees » au commit {r['commit_donnees']} : {r['paris_uniques_regles']} paris uniques réglés du "
           f"{r['du']} au {r['au']}, dont {r['clv_pinnacle']} avec une clôture Pinnacle. Coupure des deux moitiés : "
           f"{r['coupure']}. {r['tests']} segments testés (correction de Holm, deux sens). Familles mesurées sur les "
           f"cotes ≤ 5 ; « Grosses cotes (> 5) » à part. Causes (copie, lent, marge) : paris depuis le 25/10/2026. "
           f"Conclusions : [erreurs-systematiques.md](erreurs-systematiques.md).\n",
           "| Famille | Segment | Paris | CLV mesurées | Écart à la prise | CLV Pinnacle | IC 95 % | p Holm | % > 0 | "
           "1re moitié | 2de moitié | Semaines > 0 | Copie | Lent | Marge | ROI | IC 95 % du ROI | ROI − CLV, IC 95 % |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for x in r["lignes"]:
        c = x["causes"]
        ph = "—" if x.get("p_holm") is None else f"{x['p_holm']:.3f}".replace(".", ",")
        sem = f"{x['semaines']['positives']}/{x['semaines']['total']}" if "semaines" in x else "—"
        out.append(f"| {x['famille']} | {x['nom']} | {x['paris']} | {x['mesures']} | {pct(x['ecart_prise'], 1)} | "
                   f"{pct(x.get('clv'))} | {ic(x.get('ic'))} | {ph} | {pct(x.get('part_positive'), 0, False)} | "
                   f"{moitie(x.get('avant'))} | {moitie(x.get('apres'))} | {sem} | {pct(c.get('copie'), 0, False)} | "
                   f"{pct(c.get('lent'), 0, False)} | {pct(c.get('marge'), 0, False)} | {pct(x['roi'], 1)} | "
                   f"{ic(x.get('roi_ic'))} | {ic(x.get('roi_moins_clv_ic'))} |")
    out += ["", "## Population entière (controle.json, intitulés conformes)", "",
            "| Bookmaker | Marché | Période | Rapports | Médiane cote / juste | Part > 1 | Part > 1,03 |", "|---|---|---|---|---|---|---|"]
    for c in r["controle"]:
        mediane = f"{c['mediane']:.3f}".replace(".", ",")
        out.append(f"| {c['bookmaker']} | {c['marche']} | {c['periode']} | {c['n']} | {mediane} | "
                   f"{pct(c['au_dessus'], 1, False)} | {pct(c['au_dessus_3'], 1, False)} |")
    return "\n".join(out) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--donnees", type=Path, required=True)
    ap.add_argument("--markdown", type=Path)
    ap.add_argument("--json", type=Path)
    a = ap.parse_args()
    r = analyser(a.donnees)
    if a.json:
        a.json.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    texte = markdown(r)
    if a.markdown:
        a.markdown.write_text(texte, encoding="utf-8")
    print(texte)


if __name__ == "__main__":
    main()
