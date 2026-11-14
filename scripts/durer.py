"""Durer : ce que coûte un profil de paris discret (limitation des comptes). Lecture seule.

Usage : python scripts/durer.py --donnees CHEMIN [--tirages 10000] [--json FICHIER] [--markdown FICHIER]
CHEMIN = branche « donnees » extraite. Demande numpy. Environ deux minutes. Même graine, mêmes données : mêmes
chiffres. Conclusions : docs/durer.md.

Méthode : celle de scripts/strategie_mises.py (paris uniques réglés, cote ≤ plafond du site, bootstrap par match,
périodes A et B, stratégie figée recalculée par la même règle). Le profil discret est une suite de règles tirées de ce
qui est publié sur le repérage des comptes (docs/durer.md, partie 1), fixées avant de regarder leur résultat :
marchés principaux, sports grand public, pari pris près du match, pas d'écart énorme, peu de paris par jour et par
bookmaker. Chaque règle est mesurée seule puis cumulée, sur les paris du site et sur la stratégie figée.
« Avantage gardé » = paris × CLV Pinnacle moyenne du profil, rapporté à celui de la base.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cotes import simulation, stockage  # noqa: E402
from scripts import strategie_mises as sm  # noqa: E402

GRAINE = 20261114
MARCHES_PRINCIPAUX = {"RESULTAT_1N2", "VAINQUEUR", "TOTAL", "HANDICAP"}
PERIODES_PRINCIPALES = {"MATCH", "TEMPS_REG"}
SPORTS_GRAND_PUBLIC = {"football", "tennis", "basket"}
DELAI_H = 6.0
ECART_MAX = 0.07
PAR_JOUR = 3                        # paris par jour et par bookmaker ; un seul par match et par bookmaker
BOOKMAKERS = ("Winamax", "Betclic", "Unibet", "PMU", "OlyBet")
DELAIS = (24.0, 12.0, 6.0, 3.0, 1.0)
PLAFONDS_JOUR = (1, 2, 3, 5, 10, None)
SEUILS = (0.03, 0.04, 0.05, 0.07, 0.10)     # moins de paris par un seuil d'écart plus haut, sans plafond par jour
LIQUIDITE = ((100, "≤ 100"), (500, "101 à 500"), (float("inf"), "> 500"))


def charger(donnees: Path) -> list[dict]:
    """Les lignes de strategie_mises.charger, avec bookmaker, sport, marché, avance et limite Pinnacle."""
    lignes = sm.charger(donnees)
    paris = {p["id"]: p for p in stockage.fusionner_paris(stockage.lire_archives(donnees),
                                                          json.loads((donnees / "paris.json").read_text()))}
    for x in lignes:
        p = paris[x["id"]]
        debut = sm.heure(p["debut"])
        x.update(bookmaker=p["bookmaker"], sport=p["sport"], marche=p["marche"], periode_jeu=p["periode"],
                 avance_h=(debut - x["detecte"]).total_seconds() / 3600, limite=p.get("limite_pinnacle"))
    return lignes


def frequence(lignes: list[dict], par_jour: int | None, un_par_match: bool = True) -> list[dict]:
    """Dans l'ordre de détection : un pari par match et par bookmaker, ``par_jour`` au plus par jour et bookmaker."""
    pris, jours, vus = [], Counter(), set()
    for x in sorted(lignes, key=lambda x: (x["detecte"], x["id"])):
        jour, match = (x["bookmaker"], x["detecte"].date()), (x["bookmaker"], x["match"])
        if (un_par_match and match in vus) or (par_jour is not None and jours[jour] >= par_jour):
            continue
        vus.add(match)
        jours[jour] += 1
        pris.append(x)
    return pris


REGLES = (
    ("Marchés principaux, match entier", lambda l: [x for x in l if x["marche"] in MARCHES_PRINCIPAUX
                                                    and x["periode_jeu"] in PERIODES_PRINCIPALES]),
    ("Football, tennis, basket", lambda l: [x for x in l if x["sport"] in SPORTS_GRAND_PUBLIC]),
    (f"Pris au plus {DELAI_H:.0f} h avant", lambda l: [x for x in l if x["avance_h"] <= DELAI_H]),
    (f"Écart < {ECART_MAX * 100:.0f} %", lambda l: [x for x in l if x["ecart"] < ECART_MAX]),
    (f"1 par match, {PAR_JOUR} par jour, par bookmaker", lambda l: frequence(l, PAR_JOUR)),
)


def jours(lignes: list[dict]) -> float:
    t = [x["detecte"] for x in lignes]
    return max((max(t) - min(t)).total_seconds() / 86400, 1.0) if t else 1.0


def resumer(sous: list[dict], base: list[dict], duree: float, tirages: int, rng) -> dict:
    m = sm.mesurer(sous, tirages, rng)
    clv_base = [x["clv"] for x in base if x["clv"] is not None]
    total_base = len(base) * float(np.mean(clv_base)) if clv_base else 0.0
    m["par_jour"] = len(sous) / duree
    m["part"] = len(sous) / len(base) if base else None
    m["avantage_garde"] = m["paris"] * m["clv"] / total_base if m["clv"] is not None and total_base > 0 else None
    ids = {x["id"] for x in sous}
    reste = [x for x in base if x["id"] not in ids]
    if sous is not base and len(sous) >= sm.MIN_PARIS and len(reste) >= sm.MIN_PARIS:
        m["contre_reste"] = {c: sm.difference(sous, reste, c, tirages, rng) for c in ("clv", "rendement")}
    return m


def profil(base: list[dict], tirages: int, rng) -> dict:
    duree = jours(base)
    out = {"base": resumer(base, base, duree, tirages, rng), "seules": [], "cumul": []}
    courant = base
    for nom, regle in REGLES:
        out["seules"].append({"regle": nom, **resumer(regle(base), base, duree, tirages, rng)})
        courant = regle(courant)
        out["cumul"].append({"regle": nom, **resumer(courant, base, duree, tirages, rng)})
    out["delais"] = [{"regle": f"≤ {h:.0f} h", **resumer([x for x in base if x["avance_h"] <= h], base, duree, tirages, rng)}
                     for h in DELAIS]
    out["frequences"] = [{"regle": "1 par match, sans plafond" if n is None else f"1 par match, {n} par jour",
                          **resumer(frequence(base, n), base, duree, tirages, rng)} for n in PLAFONDS_JOUR]
    out["seuils"] = [{"regle": f"Écart ≥ {s * 100:.0f} %", **resumer([x for x in base if x["ecart"] >= s], base, duree, tirages, rng)}
                     for s in SEUILS]
    connus = [x for x in base if x["limite"] is not None]
    out["liquidite"], bas = [], -1.0
    for haut, nom in LIQUIDITE:
        out["liquidite"].append({"regle": nom, **resumer([x for x in connus if bas < x["limite"] <= haut], connus,
                                                         jours(connus), tirages, rng)})
        bas = haut
    out["bookmakers"] = [{"regle": b, **resumer([x for x in base if x["bookmaker"] == b], base, duree, tirages, rng)}
                         for b in BOOKMAKERS]
    return out


def analyser(donnees: Path, tirages: int = 10000, graine: int = GRAINE) -> dict:
    rng = np.random.default_rng(graine)
    plafond = simulation.COTE_MAX_PRISE
    lignes = charger(donnees)
    exclus = sm.ecartes(sm.segments(lignes, plafond, 200, np.random.default_rng(graine)))
    site = [x for x in lignes if x["cote"] <= plafond]
    figee = [x for x in site if sm.retenu(x, exclus, plafond)]
    # La stratégie figée sans son exclusion de bookmakers : pour juger les cinq bookmakers de la question.
    sans_book = [e for e in exclus if e[0] != "Bookmaker"]
    cinq = [x for x in site if sm.retenu(x, sans_book, plafond) and x["bookmaker"] in BOOKMAKERS]
    out = {"paris": len(lignes), "plafond": plafond, "exclus": exclus,
           "du": min(x["detecte"] for x in lignes).isoformat(), "au": max(x["detecte"] for x in lignes).isoformat()}
    for nom, base in (("site", site), ("figee", figee), ("figee_cinq_bookmakers", cinq)):
        out[nom] = {"tout": profil(base, tirages, rng),
                    "B": profil([x for x in base if x["periode"] == "B"], tirages, rng)}
    return out


def _ic(v, d=1) -> str:
    return "" if not v else f"[{v[0] * 100:+.{d}f} ; {v[1] * 100:+.{d}f}]".replace("-", "−").replace(".", ",")


def _pct(x, d=1) -> str:
    return "" if x is None else f"{x * 100:+.{d}f} %".replace("-", "−").replace(".", ",")


def tableau(titre: str, lignes: list[dict]) -> str:
    out = [f"\n{titre}\n", "| Règle | Paris | Par jour | ROI | IC 95 % | CLV | IC 95 % | Avantage gardé |",
           "|---|---|---|---|---|---|---|---|"]
    for m in lignes:
        garde = "" if m.get("avantage_garde") is None else f"{m['avantage_garde'] * 100:.0f} %".replace("-", "−")
        jour = f"{m['par_jour']:.1f}".replace(".", ",")
        out.append(f"| {m.get('regle', 'Base')} | {m['paris']} | {jour} | {_pct(m['roi'])} | {_ic(m['roi_ic'])} "
                   f"| {_pct(m['clv'], 2)} | {_ic(m['clv_ic'], 2)} | {garde} |")
    return "\n".join(out)


BASES = (("figee", "Stratégie figée"), ("site", "Paris du site, cote ≤ plafond"),
         ("figee_cinq_bookmakers", "Règles de la stratégie figée, avec Winamax et OlyBet, sans NetBet"))
PERIODES = (("tout", "toute la période"), ("B", "période B"))


def texte(r: dict) -> str:
    exclus = ", ".join(f"{d} : {s}" for d, s in r["exclus"])
    out = ["# Durer : tableaux du profil discret", "",
           "Produit par `python scripts/durer.py --donnees <dossier> --markdown docs/durer-tableaux.md`. Lecture : "
           "[durer.md](durer.md).", "",
           f"{r['paris']} paris uniques réglés, détectés du {r['du'][:10]} au {r['au'][:10]}. Segments écartés par la "
           f"stratégie figée : {exclus}. « Avantage gardé » : paris × CLV Pinnacle moyenne, rapporté à la base du "
           "tableau. Intervalles à 95 % par bootstrap sur les matchs."]
    for cle_base, nom in BASES:
        for cle_per, per in PERIODES:
            p = r[cle_base][cle_per]
            out.append(tableau(f"## {nom}, {per} : règles cumulées", [p["base"]] + p["cumul"]))
            dernier = p["cumul"][-1].get("contre_reste")
            if dernier:
                out.append(f"\nProfil − reste : CLV {_pct(dernier['clv']['valeur'], 2)} {_ic(dernier['clv']['ic'], 2)}, "
                           f"ROI {_pct(dernier['rendement']['valeur'])} {_ic(dernier['rendement']['ic'])}")
            for cle, titre in (("seules", "règles seules"), ("delais", "délai"), ("frequences", "fréquence"),
                               ("seuils", "seuil d'écart"),
                               ("liquidite", "limite Pinnacle (paris où elle est connue)"), ("bookmakers", "bookmaker")):
                out.append(tableau(f"### {nom}, {per} : {titre}", p[cle]))
    return "\n".join(out)


def main() -> None:
    a = argparse.ArgumentParser()
    a.add_argument("--donnees", required=True)
    a.add_argument("--tirages", type=int, default=10000)
    a.add_argument("--json")
    a.add_argument("--markdown")
    args = a.parse_args()
    r = analyser(Path(args.donnees), args.tirages)
    if args.json:
        Path(args.json).write_text(json.dumps(r, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    if args.markdown:
        Path(args.markdown).write_text(texte(r) + "\n", encoding="utf-8")
    else:
        print(texte(r))


if __name__ == "__main__":
    main()
