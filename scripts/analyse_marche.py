"""Analyse du marché (cotes/analyse_marche/) : durée des opportunités et qui bouge en premier, par segment.

Lecture seule de la branche « donnees ». Chaque jour terminé est résumé une fois dans le cache (par défaut
``<donnees>/analyse_marche/``) ; les deux derniers jours sont recalculés à chaque appel.

    python scripts/analyse_marche.py --donnees donnees                         # tableaux
    python scripts/analyse_marche.py --donnees donnees --par b,tranche         # opportunités par bookmaker et délai
    python scripts/analyse_marche.py --donnees donnees --par-meneurs sport     # paires de bookmakers par sport
    python scripts/analyse_marche.py --donnees donnees --json                  # mêmes chiffres en JSON

Segments possibles : b (bookmaker), ref (référence), sport, ligue, marche, periode, cause, tranche (délai avant
le match), pariable ; pour les meneurs : sport, ligue, marche, periode, tranche.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cotes.analyse_marche import cache, segments  # noqa: E402


def _cellule(v) -> str:
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "oui" if v else ""
    if isinstance(v, list):
        return "-".join(_cellule(x) for x in v)
    if isinstance(v, float):
        return f"{v:g}".replace(".", ",")
    return str(v)


def tableau(lignes: list[dict], limite: int) -> str:
    if not lignes:
        return "_aucune donnée_\n"
    cols = list(lignes[0])
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    out += ["| " + " | ".join(_cellule(x.get(c)) for c in cols) + " |" for x in lignes[:limite]]
    if len(lignes) > limite:
        out.append(f"\n_{len(lignes) - limite} segments de plus (--limite)_")
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--donnees", default="donnees")
    a.add_argument("--cache", default=None, help="dossier du cache (défaut : <donnees>/analyse_marche ; « non » : aucun)")
    a.add_argument("--depuis", default=None, help="premier jour (AAAA-MM-JJ)")
    a.add_argument("--jusqu", default=None, help="dernier jour (AAAA-MM-JJ)")
    a.add_argument("--par", default="b", help="segments des opportunités, séparés par des virgules")
    a.add_argument("--par-meneurs", default="", help="segments en plus de la paire de bookmakers")
    a.add_argument("--limite", type=int, default=40)
    a.add_argument("--json", action="store_true")
    args = a.parse_args(argv)
    donnees = Path(args.donnees)
    dossier_cache = None if args.cache == "non" else Path(args.cache or donnees / "analyse_marche")
    jours = [j for j in cache.jours_disponibles(donnees)
             if (not args.depuis or j >= args.depuis) and (not args.jusqu or j <= args.jusqu)]
    episodes, meneurs, etats = [], [], {}
    for j in jours:
        doc, etat = cache.resume(donnees, j, dossier_cache)
        etats[j] = etat
        episodes += doc["episodes"]
        meneurs += doc["meneurs"]
    par = tuple(x for x in args.par.split(",") if x)
    par_m = tuple(x for x in args.par_meneurs.split(",") if x)
    res = {"jours": etats, "opportunites": segments.resume_opportunites(episodes, par),
           "meneurs": segments.resume_meneurs(meneurs, par_m)}
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
        return 0
    print(f"Jours : {len(jours)} ({sum(1 for e in etats.values() if e == 'provisoire')} provisoires). "
          f"Segments de moins de {segments.ECHANTILLON_MIN} cas : « insuffisant ».\n")
    print(f"## Durée des opportunités ({len(episodes)} épisodes) — minutes, bornes basse-haute\n")
    print(tableau(res["opportunites"], args.limite))
    print("## Qui bouge en premier (mouvements d'au moins 1 point de probabilité)\n")
    print(tableau(res["meneurs"], args.limite))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
