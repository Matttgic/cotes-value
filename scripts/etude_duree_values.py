"""Durée de vie des values et « CLV maison », d'après l'historique des cotes françaises (donnees/cotes/).

Deux questions que la cote juste des références ne tranche pas :

1. **Durée de vie** : après la détection, combien de temps la cote reste-t-elle au moins égale à la cote prise ?
   C'est le temps dont on dispose pour jouer vraiment. Une cote qui ne baisse jamais avant le match est « tenue ».
2. **CLV maison** : cote prise / dernière cote du même bookmaker avant le match − 1. Si le bookmaker a baissé sa
   propre cote après notre prise, il nous donne raison lui-même, sans passer par une référence.

3. **Origine de la value** : dans l'heure qui précède la détection, le bookmaker venait-il de monter sa cote
   (la value vient de lui : il sait peut-être quelque chose), de la baisser, ou n'avait-il pas bougé (la value
   vient de la référence, qui a bougé sans lui) ? Connu au moment de parier, contrairement aux deux autres.

L'historique ne garde que les changements (cotes/historique_cotes.py), pour PMU, Unibet, Betclic et NetBet, depuis
le 30/10/2026. Paris uniques (une cote française comptée une fois), détectés avant le match. Lecture seule.

    python scripts/etude_duree_values.py --donnees donnees            # tableau par bookmaker
    python scripts/etude_duree_values.py --donnees donnees --json     # mêmes chiffres en JSON
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cotes.simulation import REGLES, clv_finale, premiers_par_selection  # noqa: E402
from cotes.stockage import fusionner_paris, lire_archives  # noqa: E402
from cotes.temps import instant_utc  # noqa: E402

PALIERS_MIN = (2, 5, 15, 60)
ORIGINE_MIN = 60
LONGUES_COTES = ("CORRECT_SCORE", "HALF_TIME_FULL_TIME")
ORIGINES = (("hausse", "le bookmaker venait de monter sa cote"), ("stable", "cote du bookmaker stable depuis une heure"),
            ("baisse", "le bookmaker venait de baisser sa cote"), ("nouvelle", "cote apparue dans l'heure"))


def cle_historique(p: dict) -> tuple:
    """(bookmaker en minuscules, match, « marché|période|ligne|issue[|joueur] ») : la clé d'une ligne d'historique."""
    k = "|".join("" if x is None else str(x) for x in (p.get("marche"), p.get("periode"), p.get("ligne"), p.get("issue")))
    if p.get("joueur"):
        k += "|" + str(p["joueur"])
    return (str(p.get("bookmaker") or "").lower(), p.get("match_id"), k)


def lire_series(dossier: Path, cles: set[tuple], jours: set[str]) -> dict[tuple, list[tuple[datetime, float]]]:
    """Changements de cote des seules lignes demandées, dans l'ordre du temps."""
    series: dict[tuple, list] = {c: [] for c in cles}
    for jour in sorted(jours):
        chemin = dossier / f"{jour}.jsonl.gz"
        if not chemin.exists():
            continue
        with gzip.open(chemin, "rt", encoding="utf-8") as f:
            for ligne in f:
                if '"k"' not in ligne:
                    continue
                try:
                    d = json.loads(ligne)
                except ValueError:
                    continue
                cle = (str(d.get("b") or "").lower(), d.get("m"), d.get("k"))
                c, t = d.get("c"), instant_utc(d.get("t"))
                if cle in series and t is not None and isinstance(c, (int, float)) and not isinstance(c, bool) and c > 1:
                    series[cle].append((t, float(c)))
    for s in series.values():
        s.sort()
    return series


def mesurer(p: dict, serie: list[tuple[datetime, float]]) -> dict | None:
    """Durée de vie (minutes) et cote de clôture du bookmaker pour un pari, ou None si l'historique ne le couvre pas."""
    t0, debut, cote = instant_utc(p.get("detecte")), instant_utc(p.get("debut")), p.get("cote")
    if t0 is None or debut is None or debut <= t0 or not isinstance(cote, (int, float)):
        return None
    # la cote prise doit se retrouver dans l'historique au moment de la détection (± 10 min) : sinon série incomplète
    avant = [c for t, c in serie if t <= t0 + timedelta(minutes=10)]
    if not avant or abs(avant[-1] - cote) > 0.011:
        return None
    # dernier changement du bookmaker avant la détection : une hausse ou une baisse dans l'heure, sinon « stable »
    passes = [(t, c) for t, c in serie if t <= t0 + timedelta(minutes=10)]
    origine = "stable"
    if len(passes) >= 2 and t0 - passes[-1][0] <= timedelta(minutes=ORIGINE_MIN):
        origine = "hausse" if passes[-1][1] > passes[-2][1] else "baisse"
    elif len(passes) == 1 and t0 - passes[-1][0] <= timedelta(minutes=ORIGINE_MIN):
        origine = "nouvelle"                      # cote apparue dans l'heure : pas d'avant à comparer
    apres = [(t, c) for t, c in serie if t0 < t < debut]
    baisse = next((t for t, c in apres if c < cote - 1e-9), None)
    cloture = apres[-1][1] if apres else cote
    return {"duree_min": None if baisse is None else (baisse - t0).total_seconds() / 60,
            "fenetre_min": (debut - t0).total_seconds() / 60, "cote_cloture": cloture,
            "clv_maison": cote / cloture - 1, "baissee": cloture < cote - 1e-9, "montee": cloture > cote + 1e-9,
            "origine": origine}


def etudier(donnees: Path, cote_max: float | None = 5.0) -> dict:
    """``cote_max`` : zone où les cotes justes sont calibrées (cote ≤ 5, ni score exact ni mi-temps/fin) ; None pour
    tous les paris."""
    paris = fusionner_paris(json.loads((donnees / "paris.json").read_text(encoding="utf-8")), lire_archives(donnees))
    uniques = premiers_par_selection(paris)
    jours_dispo = {f.name[:10] for f in (donnees / "cotes").glob("*.jsonl.gz")}
    if not jours_dispo:
        return {"paris": 0, "bookmakers": {}}
    premier = min(jours_dispo)
    retenus = [p for p in paris if id(p) in uniques and str(p.get("detecte") or "")[:10] >= premier and p.get("match_id")
               and (cote_max is None or (isinstance(p.get("cote"), (int, float)) and p["cote"] <= cote_max
                                         and p.get("marche") not in LONGUES_COTES))]
    cles = {cle_historique(p) for p in retenus}
    jours = set()
    for p in retenus:
        a, b = instant_utc(p.get("detecte")), instant_utc(p.get("debut"))
        while a is not None and b is not None and a.date() <= b.date() and len(jours) < 400:
            jours.add(a.date().isoformat())
            a += timedelta(days=1)
    series = lire_series(donnees / "cotes", cles, jours & jours_dispo)
    par_book: dict[str, list[tuple[dict, dict]]] = {}
    for p in retenus:
        m = mesurer(p, series.get(cle_historique(p), []))
        if m:
            par_book.setdefault(p["bookmaker"], []).append((p, m))

    def resume(lot: list[tuple[dict, dict]]) -> dict:
        n = len(lot)
        durees = sorted(m["duree_min"] for _, m in lot if m["duree_min"] is not None)

        def roi(sous):
            regles = [p for p, _ in sous if p.get("statut") in REGLES]
            return {"n": len(regles), "roi": round(sum(p.get("gain") or 0 for p in regles) / sum(p["mise"] for p in regles), 4)
                    if regles else None,
                    "clv_reference": (lambda v: round(sum(v) / len(v), 4) if v else None)(
                        [c for c in (clv_finale(p) for p in regles) if c is not None])}
        # encore jouable après x minutes : pas de baisse avant, et le match n'a pas commencé
        tenues = {f"encore_jouable_{x}_min": round(sum(1 for _, m in lot if m["fenetre_min"] > x and (
            m["duree_min"] is None or m["duree_min"] > x)) / max(1, sum(1 for _, m in lot if m["fenetre_min"] > x)), 3)
            for x in PALIERS_MIN}
        return {"paris": n, **tenues,
                "tenue_jusqu_au_match": round(sum(m["duree_min"] is None for _, m in lot) / n, 3),
                "duree_mediane_des_baisses_min": round(durees[len(durees) // 2], 1) if durees else None,
                "clv_maison_moyenne": round(sum(m["clv_maison"] for _, m in lot) / n, 4),
                "cote_baissee_par_le_book": roi([x for x in lot if x[1]["baissee"]]),
                "cote_inchangee": roi([x for x in lot if not x[1]["baissee"] and not x[1]["montee"]]),
                "cote_montee_par_le_book": roi([x for x in lot if x[1]["montee"]]),
                "origine": {o: roi([x for x in lot if x[1]["origine"] == o]) for o, _ in ORIGINES}}
    tous = [x for lot in par_book.values() for x in lot]
    return {"depuis": premier, "cote_max": cote_max, "paris": len(tous), "paris_sans_historique": len(retenus) - len(tous),
            "ensemble": resume(tous) if tous else {},
            "bookmakers": {b: resume(lot) for b, lot in sorted(par_book.items()) if len(lot) >= 20}}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--donnees", default="donnees")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--toutes-cotes", action="store_true", help="aussi les cotes > 5, le score exact et la mi-temps/fin")
    args = ap.parse_args()
    r = etudier(Path(args.donnees), None if args.toutes_cotes else 5.0)
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
        return 0
    pct = lambda x: "—" if x is None else f"{100 * x:+.1f} %".replace(".", ",")  # noqa: E731
    part = lambda x: "—" if x is None else f"{100 * x:.0f} %"  # noqa: E731
    print(f"Paris uniques mesurés depuis le {r.get('depuis')} : {r['paris']} (sans historique exploitable : {r.get('paris_sans_historique')})")
    for nom, s in [("Ensemble", r.get("ensemble") or {})] + list(r["bookmakers"].items()):
        if not s:
            continue
        print(f"\n{nom} · {s['paris']} paris")
        print("  encore jouable après " + ", ".join(f"{x} min : {part(s[f'encore_jouable_{x}_min'])}" for x in PALIERS_MIN)
              + f" · tenue jusqu'au match : {part(s['tenue_jusqu_au_match'])}")
        print(f"  quand elle baisse : médiane {s['duree_mediane_des_baisses_min']} min · CLV maison moyenne {pct(s['clv_maison_moyenne'])}")
        for cle, titre in (("cote_baissee_par_le_book", "cote baissée ensuite par le bookmaker"),
                           ("cote_inchangee", "cote inchangée"), ("cote_montee_par_le_book", "cote montée ensuite")):
            x = s[cle]
            print(f"  {titre} : {x['n']} réglés, ROI {pct(x['roi'])}, CLV référence {pct(x['clv_reference'])}")
        for o, titre in ORIGINES:
            x = s["origine"][o]
            if x["n"]:
                print(f"  origine, {titre} : {x['n']} réglés, ROI {pct(x['roi'])}, CLV référence {pct(x['clv_reference'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
