"""Audit de la justesse des bilans : recalcule chaque chiffre de docs/audit-bilans.md. Lecture seule.

Usage : python scripts/audit_bilans.py --donnees CHEMIN [--sans-archive]
CHEMIN = branche « donnees » extraite (paris.json, archives/, resultats_manuels.json, opportunites/).
"""
from __future__ import annotations

import argparse
import gzip
import json
import math
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cotes import reglement, simulation, stockage  # noqa: E402
from cotes.evenements import identites  # noqa: E402
from cotes.marches import cle  # noqa: E402
from cotes.resultats import incoherences_freres  # noqa: E402

REGLES = reglement.GAIN
PLAFOND_LE = "2026-11-11T15:30"          # dernière prise au-dessus du plafond : 11/11/2026 15:29 UTC


def heure(s) -> datetime:
    return datetime.fromisoformat(str(s).replace("Z", "+00:00"))


def preuve(p: dict) -> dict:
    return p.get("preuve_reglement") or {}


def regles(paris: list[dict]) -> list[dict]:
    return [p for p in paris if p.get("statut") in REGLES]


def roi(paris: list[dict]) -> tuple[int, float, float | None]:
    """(paris réglés, gain, ROI en %) — mêmes conventions que simulation._cumuler (remboursés dans les mises)."""
    r = regles(paris)
    mises, gains = sum(p["mise"] for p in r), sum(p["gain"] or 0 for p in r)
    return len(r), round(gains, 2), round(100 * gains / mises, 2) if mises else None


def erreur_type(paris: list[dict], groupe=None) -> tuple[float, int]:
    """Écart-type du ROI (en points) : paris indépendants (groupe=None) ou regroupés (par match).
    Estimateur du ratio : sqrt(somme des (gain − ROI × mise)² par groupe) / mises."""
    r = regles(paris)
    mises = sum(p["mise"] for p in r)
    if not mises:
        return 0.0, 0
    taux = sum(p["gain"] or 0 for p in r) / mises
    residus: dict = defaultdict(float)
    for n, p in enumerate(r):
        residus[groupe(p) if groupe else n] += (p["gain"] or 0) - taux * p["mise"]
    return 100 * math.sqrt(sum(x * x for x in residus.values())) / mises, len(residus)


def _demi(v: float) -> float:
    return 1.0 if v > 1e-9 else -1.0 if v < -1e-9 else 0.0


def regler_independant(p: dict, score: tuple[int, int], mi_temps: tuple[int, int] | None = None) -> str | None:
    """Règlement écrit à part de cotes/reglement.py, pour le recouper : le pari est vu comme deux demi-mises
    (lignes voisines pour un quart, la même ligne deux fois sinon), chacune gagnée, perdue ou remboursée."""
    m, i, ligne = p["marche"], p["issue"], p.get("ligne")
    for prefixe in ("CORNERS_", "JEUX_", "SETS_"):
        if m.startswith(prefixe):
            m = m[len(prefixe):]
    d, e = score
    signe = lambda a, b: "DOM" if a > b else "EXT" if b > a else "NUL"  # noqa: E731
    r = signe(d, e)
    if m == "RESULTAT_1N2":
        return "gagne" if r == i else "perdu"
    if m in ("VAINQUEUR", "DRAW_NO_BET"):
        return "rembourse" if r == "NUL" else "gagne" if r == i else "perdu"
    if m == "DOUBLE_CHANCE":
        return "gagne" if r in {"HOME_DRAW": "DOM NUL", "HOME_AWAY": "DOM EXT", "DRAW_AWAY": "NUL EXT"}[i].split() else "perdu"
    if m == "HANDICAP_3":
        return "gagne" if signe(d + ligne, e) == i else "perdu"
    if m == "BOTH_TEAMS_TO_SCORE":
        return "gagne" if (min(d, e) > 0) == (i == "YES") else "perdu"
    if m == "CORRECT_SCORE":
        return "gagne" if i == f"{d}-{e}" else "perdu"
    if m == "HALF_TIME_FULL_TIME":
        return None if mi_temps is None else "gagne" if i == f"{signe(*mi_temps)}/{r}" else "perdu"
    if m == "HANDICAP":                     # ligne exprimée pour le domicile ; l'extérieur a la ligne opposée
        marge, sa_ligne = (d - e, ligne) if i == "DOM" else (e - d, -ligne)
    elif m in ("TOTAL", "TOTAL_DOM", "TOTAL_EXT"):
        total = {"TOTAL": d + e, "TOTAL_DOM": d, "TOTAL_EXT": e}[m]
        marge, sa_ligne = (total, -ligne) if i == "PLUS" else (-total, ligne)
    else:
        return None
    quart = abs(sa_ligne * 4 - round(sa_ligne * 4)) < 1e-9 and round(sa_ligne * 4) % 2 == 1
    lignes = (sa_ligne - 0.25, sa_ligne + 0.25) if quart else (sa_ligne, sa_ligne)
    net = sum(_demi(marge + x) for x in lignes) / 2
    return {1.0: "gagne", 0.5: "demi_gagne", 0.0: "rembourse", -0.5: "demi_perdu", -1.0: "perdu"}[net]


def _scores(p: dict) -> dict | None:
    sc = preuve(p).get("scores")
    return {k: (tuple(v) if isinstance(v, list) else v) for k, v in sc.items()} if sc else None


def _score_du_pari(p: dict, sc: dict):
    m, per = p["marche"], p["periode"]
    if m.startswith("CORNERS_"):
        return sc.get("CORNERS" if per == "MATCH" else f"CORNERS_{per}")
    if m.startswith("JEUX_"):
        return sc.get("JEUX") if per == "MATCH" else sc.get(per)
    if m.startswith("SETS_"):
        return sc.get("MATCH")
    return sc.get(per)


def lire_opportunites(donnees: Path) -> tuple[dict, dict]:
    """Première vue de chaque pari possible (id -> opportunité) et heures de début vues par match."""
    premiers: dict[str, dict] = {}
    debuts: dict[str, set] = defaultdict(set)
    for f in sorted((donnees / "opportunites").glob("*.jsonl.gz")):
        with gzip.open(f, "rt") as flux:
            for ligne in flux:
                try:
                    o = json.loads(ligne)
                    pid = simulation._id(o["reference"], o["match_id"], *cle(o))
                except (ValueError, KeyError, TypeError):
                    continue
                premiers.setdefault(pid, o)
                debuts[o["match_id"]].add(o.get("debut"))
    return premiers, debuts


def titre(t: str) -> None:
    print(f"\n== {t}")


def auditer(donnees: Path, avec_archive: bool = True) -> None:
    paris = stockage.fusionner_paris(stockage.lire_archives(donnees), json.loads((donnees / "paris.json").read_text()))
    manuels = json.loads((donnees / "resultats_manuels.json").read_text())
    reg = regles(paris)
    liens = identites(paris)
    evenement = lambda p: liens[id(p)]  # noqa: E731
    uniques = simulation.premiers_par_selection(paris)
    plafond = simulation.COTE_MAX_PRISE
    site = [p for p in paris if p["cote"] <= plafond]
    uniques_site = simulation.premiers_par_selection(site)
    vues = {"Toutes": paris, "Uniques": [p for p in paris if id(p) in uniques],
            f"Toutes ≤ {plafond:g}": site, f"Uniques ≤ {plafond:g} (site)": [p for p in site if id(p) in uniques_site],
            f"cotes > {plafond:g}": [p for p in paris if p["cote"] > plafond]}

    titre("Base")
    print(f"paris {len(paris)} | réglés {len(reg)} | statuts {dict(Counter(p['statut'] for p in paris))}")
    print(f"détectés du {min(p['detecte'] for p in paris)[:16]} au {max(p['detecte'] for p in paris)[:16]}")
    for nom, l in vues.items():
        s1, _ = erreur_type(l)
        s2, n2 = erreur_type(l, evenement)
        n, g, r = roi(l)
        print(f"{nom:24} n={n:5} gain={g:9.1f} ROI={r:6.2f} % | écart-type : paris indépendants {s1:.2f}, par match "
              f"{s2:.2f} ({n2} matchs) | IC 95 % par match [{r - 1.96 * s2:.1f} ; {r + 1.96 * s2:.1f}]")

    titre("Anticipation")
    apres = lambda a, b: sum(1 for p in paris if p.get(a) and p.get(b) and heure(p[a]) >= heure(p[b]))  # noqa: E731
    print(f"cote lue après le début {apres('detecte', 'debut')} | référence lue après le début "
          f"{apres('lu_reference', 'debut')} | clôture lue après le début {apres('cloture_lue', 'debut')} | "
          f"référence lue après la décision {sum(1 for p in paris if p.get('decide_le') and heure(p['lu_reference']) > heure(p['decide_le']))} | "
          f"réglé avant le début {sum(1 for p in reg if p.get('regle_le') and heure(p['regle_le']) < heure(p['debut']))}")
    print(f"plafond de cote {plafond:g} appliqué après coup (scripts/site_web.py) : par tranche de cote")
    for bas, haut in ((1, 1.5), (1.5, 2), (2, 3), (3, 4), (4, 5), (5, 10), (10, 1e9)):
        l = [p for p in paris if bas < p["cote"] <= haut]
        s2, _ = erreur_type(l, evenement)
        print(f"  ]{bas:g} ; {haut:g}] {roi(l)} ± {1.96 * s2:.1f}")
    for debut in ("2026-10-05", "2026-10-12", "2026-10-19", "2026-10-26", "2026-11-02", "2026-11-09"):
        fin = (heure(debut + "T00:00:00+00:00") + timedelta(days=7)).isoformat()[:10]
        l = [p for p in paris if debut <= p["detecte"][:10] < fin]
        print(f"  semaine du {debut} : tous {roi(l)} | ≤ {plafond:g} {roi([p for p in l if p['cote'] <= plafond])}")
    hors = [p for p in paris if p["detecte"] >= PLAFOND_LE]
    print(f"  hors échantillon (pris après {PLAFOND_LE}) : {roi(hors)}")
    print(f"sélections non figées à la prise (avant le registre du 17/10) : {sum('selections_figees' not in p for p in paris)}")

    titre("Survivant")
    maintenant = heure(max(p["detecte"] for p in paris))
    ouverts = [p for p in paris if p["statut"] in ("en_cours", "a_regler") and heure(p["debut"]) < maintenant]
    mises = sum(p["mise"] for p in reg) + sum(p["mise"] for p in ouverts)
    gains = sum(p["gain"] for p in reg)
    print(f"match commencé, pari non réglé : {len(ouverts)} | ROI si tous perdus "
          f"{100 * (gains - sum(p['mise'] for p in ouverts)) / mises:.2f} %, si tous gagnés "
          f"{100 * (gains + sum(p['mise'] * (p['cote'] - 1) for p in ouverts)) / mises:.2f} %")

    def cause(p: dict) -> str:
        q = preuve(p)
        if q.get("annule"):
            return "forfait automatique"
        if q.get("origine") == "statut saisi à la main":
            return "saisi à la main"
        if (q.get("scores") or {}).get("ABANDON"):
            return "abandon tennis"
        return f"égalité ou ligne entière ({p['marche']}, {p['sport']})" if q.get("origine") else "sans preuve"
    rembourses = [p for p in reg if p["statut"] == "rembourse"]
    print(f"remboursés {len(rembourses)} : {dict(Counter(cause(p) for p in rembourses).most_common())}")
    print(f"ROI hors remboursés (mises réellement risquées) : {roi([p for p in reg if p['statut'] != 'rembourse'])}")
    ids = {p["id"]: p for p in paris}
    a_la_main = {ids[k]["match_id"] for k, v in manuels.items() if v == "rembourse" and k in ids}
    mixtes = [m for m in a_la_main if any(p["match_id"] == m and p["statut"] in ("gagne", "perdu") for p in paris)]
    print(f"statuts à la main : {dict(Counter(v for v in manuels.values() if isinstance(v, str)))} | matchs remboursés à la "
          f"main {len(a_la_main)}, dont avec aussi des paris gagnés ou perdus {len(mixtes)}")
    sans_preuve = [p for p in reg if not preuve(p).get("origine")]
    print(f"sans trace de règlement : {roi(sans_preuve)} | dont ≤ {plafond:g} : {roi([p for p in sans_preuve if p['cote'] <= plafond])}")
    une_source = [p for p in reg if len(preuve(p).get("sources") or []) == 1]
    print(f"réglés sur une seule source : {roi(une_source)}")
    for nom, l in (("Toutes", reg), ("Uniques site", regles(vues[f"Uniques ≤ {plafond:g} (site)"]))):
        avec = [p for p in l if simulation.clv_finale(p) is not None]
        sans = [p for p in l if simulation.clv_finale(p) is None]
        print(f"CLV de clôture {nom} : mesurée {roi(avec)}, moyenne {100 * sum(simulation.clv_finale(p) for p in avec) / len(avec):.2f} % "
              f"| non mesurée {roi(sans)} ({100 * len(sans) / len(l):.0f} % des réglés)")

    titre("Double comptage")
    par_cote = defaultdict(list)
    for p in paris:
        par_cote[tuple(p.get(c) for c in ("match_id", "marche", "periode", "ligne", "issue", "joueur"))].append(p)
    print(f"identifiants en double {sum(1 for v in Counter(p['id'] for p in paris).values() if v > 1)} | cotes françaises "
          f"{len(par_cote)}, dont vues par plusieurs références {sum(1 for v in par_cote.values() if len(v) > 1)} "
          f"= {sum(len(v) - 1 for v in par_cote.values())} paris en plus dans « Toutes »")
    exemple = max(par_cote.values(), key=len)
    print(f"  exemple : {exemple[0]['bookmaker']} {exemple[0]['domicile']} - {exemple[0]['exterieur']} «{exemple[0]['pari']}» "
          f"cote {exemple[0]['cote']} : {len(exemple)} paris ({', '.join(sorted(p['reference'] for p in exemple))}), {exemple[0]['statut']}")
    par_selection = defaultdict(set)
    par_evenement = Counter()
    for p in vues["Uniques"]:
        par_selection[(evenement(p), p["marche"], p["periode"], p["ligne"], p["issue"])].add(p["bookmaker"])
        par_evenement[evenement(p)] += 1
    print(f"même sélection chez plusieurs bookmakers (Uniques) : {sum(1 for v in par_selection.values() if len(v) > 1)} "
          f"sélections, {sum(len(v) - 1 for v in par_selection.values())} paris en plus | paris uniques par match : "
          f"moyenne {sum(par_evenement.values()) / len(par_evenement):.2f}, maximum {max(par_evenement.values())}")
    premier = {}
    for p in sorted(vues["Uniques"], key=lambda p: p["detecte"]):
        premier.setdefault(evenement(p), p)
    print(f"un seul pari par match (le premier) : {roi(list(premier.values()))}")

    titre("Règlement")
    ecarts, sans_scores, independants = [], 0, []
    for p in reg:
        sc = _scores(p)
        if not sc:
            sans_scores += 1
            continue
        if reglement.regler(p, sc) != p["statut"]:
            ecarts.append((p, reglement.regler(p, sc)))
        s = _score_du_pari(p, sc)
        if s and not sc.get("ABANDON"):
            ind = regler_independant(p, s, sc.get("MT1"))
            if ind is not None and ind != p["statut"]:
                independants.append((p, ind))
    print(f"re-règlement par le code actuel : {len(reg) - sans_scores} paris avec scores, {len(ecarts)} changent de statut")
    for p, s in ecarts:
        print(f"  {p['id']} {p['bookmaker']} {p['sport']} {p['domicile']} - {p['exterieur']} {p['debut'][:10]} «{p['pari']}» "
              f"cote {p['cote']} : {p['statut']} -> {s or 'à régler'} | score {preuve(p).get('score')} sources {preuve(p).get('sources')}")
    print(f"moteur indépendant : {len(independants)} désaccords avec le statut enregistré")
    for p, s in independants[:10]:
        print(f"  {p['id']} {p['marche']} {p['periode']} {p['ligne']} {p['issue']} : {p['statut']} / indépendant {s}")
    lignes = [p for p in paris if p.get("ligne") is not None and p["marche"] in ("HANDICAP", "TOTAL", "TOTAL_DOM", "TOTAL_EXT")]
    quarts = [p for p in lignes if round(p["ligne"] * 4) % 2 == 1]
    entieres = regles([p for p in lignes if p["ligne"] == round(p["ligne"])])
    print(f"handicaps et totaux {len(lignes)} : quarts de ligne {len(quarts)}, lignes entières réglées {len(entieres)} "
          f"dont remboursées {sum(p['statut'] == 'rembourse' for p in entieres)}")
    nombre = re.compile(r"([+\-−]\s?\d+(?:[.,]\d+)?)")
    faux = 0
    for p in paris:
        if p["marche"] == "HANDICAP" and p["ligne"]:
            equipe = p["domicile"] if p["issue"] == "DOM" else p["exterieur"]
            vus = nombre.findall(p["pari"].replace(equipe, ""))
            attendu = p["ligne"] if p["issue"] == "DOM" else -p["ligne"]
            faux += not vus or abs(float(vus[-1].replace(" ", "").replace(",", ".").replace("−", "-")) - attendu) > 1e-9
        elif p["marche"] in ("TOTAL", "TOTAL_DOM", "TOTAL_EXT", "JEUX_TOTAL", "SETS_TOTAL"):
            t = p["pari"].lower()
            vus = re.findall(r"\d+(?:[.,]\d+)?", t)
            faux += not vus or abs(float(vus[0].replace(",", ".")) - p["ligne"]) > 1e-9 or \
                t.startswith("plus") != (p["issue"] == "PLUS")
    print(f"libellé du pari contre ligne et sens enregistrés (handicaps non nuls, totaux) : {faux} incohérences")
    reglementaire = re.compile(r"r[ée]glementaire|regular|tps r[ée]g", re.I)
    mal_ranges = [p for p in reg if p["sport"] in ("hockey", "basket") and p["periode"] == "MATCH"
                  and reglementaire.search(p.get("libelle_bookmaker") or "")]
    changent = [p for p in mal_ranges if _scores(p) and _scores(p).get("TEMPS_REG")
                and reglement.regler({**p, "periode": "TEMPS_REG"}, _scores(p)) != p["statut"]]
    print(f"libellé « temps réglementaire » réglé prolongation incluse : {len(mal_ranges)} paris "
          f"(lignes {sorted({abs(p['ligne']) for p in mal_ranges if p.get('ligne')})}), statut différent sur 60 min : {len(changent)}")
    nuls = [p for p in reg if p["sport"] in ("hockey", "basket", "baseball", "volley") and p["periode"] == "MATCH"
            and (_scores(p) or {}).get("MATCH") and _scores(p)["MATCH"][0] == _scores(p)["MATCH"][1]]
    print(f"score final nul dans un sport sans nul : {len(nuls)} paris {dict(Counter((p['sport'], p['marche'], p['statut']) for p in nuls))}")
    anticipes = [p for p in paris if re.search(r"\d+UP|anticip", p.get("libelle_bookmaker") or "", re.I)]
    print(f"marchés « paiement anticipé » réglés comme une simple victoire : {len(anticipes)} {roi(anticipes)} "
          f"{dict(Counter(p['statut'] for p in anticipes))}")
    mi_temps_basket = [p for p in reg if p["sport"] == "basket" and p["marche"] == "VAINQUEUR" and p["periode"] == "MT1"
                       and p["statut"] == "rembourse"]
    print(f"basket, vainqueur de la 1re mi-temps remboursé sur égalité : {len(mi_temps_basket)} "
          f"({dict(Counter(p['bookmaker'] for p in mi_temps_basket))})")
    abandons = [p for p in reg if (_scores(p) or {}).get("ABANDON")]
    print(f"tennis, abandons : {len(abandons)} paris {dict(Counter((p['bookmaker'], p['marche'], p['statut']) for p in abandons))}")
    foot = [p for p in reg if p["sport"] == "football" and preuve(p).get("origine") == "automatique" and not preuve(p).get("periodes")]
    coupe = re.compile(r"coupe|cup|beker|pokal|copa|ta[cç]a|kupa", re.I)
    coupes = [p for p in foot if coupe.search(p.get("ligue") or "") and "monde" not in (p.get("ligue") or "").lower()]
    print(f"football réglé sur le score final sans mi-temps : {roi(foot)} sur {len({p['match_id'] for p in foot})} matchs | "
          f"dont coupes : {roi(coupes)} sur {len({p['match_id'] for p in coupes})} matchs")
    for i in incoherences_freres(paris, limite=500):
        print(f"même match, scores différents : {i['a']['match']} {i['debut'][:10]} | {i['a']['bookmaker']} {i['a']['score']} "
              f"{i['a']['sources']} | {i['b']['bookmaker']} {i['b']['score']} {i['b']['sources']}")
    print(f"« avance ou gagne » : {sum(p['marche'] == 'AVANCE_OU_GAGNE' for p in paris)} paris en base")

    if not avec_archive:
        return
    titre("Archive des opportunités (opportunites/*.jsonl.gz)")
    premiers, debuts = lire_opportunites(donnees)
    retrouves = [p for p in paris if p["id"] in premiers]
    memes = [p for p in retrouves if premiers[p["id"]]["detecte"] == p["detecte"]]
    print(f"paris retrouvés {len(retrouves)} / {len(paris)} | pris à la première vue {len(memes)} : cote différente "
          f"{sum(abs(premiers[p['id']]['cote'] - p['cote']) > 1e-9 for p in memes)}, début différent "
          f"{sum(premiers[p['id']]['debut'] != p['debut'] for p in memes)}")
    en_jeu = [p for p in paris if any(x and heure(x) <= heure(p["detecte"]) for x in debuts.get(p["match_id"], ()))]
    print(f"pris après une heure de début annoncée plus tôt pour le même match : {roi(en_jeu)}")
    par_match = defaultdict(list)
    for p in reg:
        if (_scores(p) or {}).get("MATCH"):
            par_match[p["match_id"]].append(p)
    supprimes = [k for k, v in manuels.items() if v == "supprime"]
    mise = gain = 0.0
    statuts = Counter()
    for k in supprimes:
        o = premiers.get(k)
        freres = par_match.get(o["match_id"]) if o else None
        statut = reglement.regler({**o, "id": k}, _scores(freres[0])) if freres else None
        statuts[statut or "inconnu"] += 1
        if statut in REGLES:
            mise += simulation.MISE
            gain += reglement.gain(statut, simulation.MISE, o["cote"])
    print(f"paris supprimés à la main {len(supprimes)}, retrouvés {sum(k in premiers for k in supprimes)} : "
          f"{dict(Counter((premiers[k]['domicile'], premiers[k]['reference']) for k in supprimes if k in premiers))}")
    print(f"  réglés avec le score de leurs frères : {dict(statuts)} | mises {mise:.0f}, gain {gain:.1f} | "
          f"ROI « Toutes » avec eux : {100 * (gains + gain) / (sum(p['mise'] for p in reg) + mise):.2f} %")


if __name__ == "__main__":
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--donnees", type=Path, required=True)
    a.add_argument("--sans-archive", action="store_true", help="ne lit pas opportunites/ (plus rapide)")
    args = a.parse_args()
    auditer(args.donnees, avec_archive=not args.sans_archive)
