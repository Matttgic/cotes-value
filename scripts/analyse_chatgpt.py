"""Diagnostic descriptif reproductible ; ne modifie ni règles, ni paris, ni site.

python scripts/analyse_chatgpt.py --donnees chemin/vers/donnees
Rejouer sur le commit de données cité dans docs/strategie-chatgpt.md pour obtenir
exactement les chiffres de conception. Les résultats futurs ne sont pas un backtest.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cotes.simulation import REGLES, clv_finale, paris_strategie, premiers_par_selection  # noqa: E402
from cotes.stockage import lire_archives, fusionner_paris  # noqa: E402
from cotes.strategie_chatgpt import CHATGPT, _heure, motif_refus, paris_chatgpt  # noqa: E402


def resume(rows: list[dict], arrete: str) -> dict:
    cutoff = _heure(arrete)
    regles = [p for p in rows if p.get("statut") in REGLES and _heure(p.get("regle_le"))
              and _heure(p["regle_le"]) < cutoff]
    clvs = [clv_finale(p) for p in regles if clv_finale(p) is not None]
    mises = sum(p["mise"] for p in regles)
    gain = sum(p.get("gain") or 0 for p in regles)
    courant = sommet = drawdown = 0.0
    for p in sorted(regles, key=lambda p: (_heure(p["regle_le"]), p.get("id", ""))):
        courant += p.get("gain") or 0
        sommet = max(sommet, courant)
        drawdown = max(drawdown, sommet - courant)
    return {"paris": len(rows), "regles": len(regles), "non_regles_a_la_coupure": len(rows)-len(regles),
            "gagnes": sum(p["statut"] == "gagne" for p in regles),
            "rembourses": sum(p["statut"] == "rembourse" for p in regles),
            "gain_euros": round(gain, 2), "roi_pct": round(100*gain/mises, 2) if mises else None,
            "clv_n": len(clvs), "clv_pct": round(100*sum(clvs)/len(clvs), 2) if clvs else None,
            "baisse_max_euros": round(drawdown, 2)}


def analyser(paris: list[dict]) -> dict:
    avant = [p for p in paris if _heure(p.get("detecte"))
             and _heure(p["detecte"]) < _heure(CHATGPT["debut"])]
    uniques, claude = premiers_par_selection(avant), paris_strategie(avant)
    cg = paris_chatgpt(avant, depuis="2026-10-05T00:00:00+00:00")
    base = [p for p in avant if p.get("reference") == "Pinnacle"
            and 1.5 <= p.get("cote", 0) <= 3 and .03 <= p.get("ecart", 0) <= .12]
    groupes = {"uniques": [p for p in avant if id(p) in uniques],
               "claude_depuis_son_lancement": [p for p in avant if id(p) in claude],
               "pinnacle_cotes_intermediaires_non_dedoublonne": base,
               "chatgpt_retro_exploratoire": [p for p in avant if id(p) in cg]}
    return {"arrete_avant": CHATGPT["debut"], "lignes_sources": len(avant),
            "avertissement": "Échantillon de conception, pas une validation indépendante ni une comparaison à dates égales.",
            "groupes": {nom: resume(rows, CHATGPT["debut"]) for nom, rows in groupes.items()},
            "refus_pinnacle": dict(Counter(motif_refus(p, depuis="2026-10-05T00:00:00+00:00")
                                            or "admissible_avant_plafonds" for p in avant if p.get("reference") == "Pinnacle"))}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--donnees", type=Path, required=True)
    args = parser.parse_args()
    paris = fusionner_paris(json.loads((args.donnees / "paris.json").read_text()), lire_archives(args.donnees))
    print(json.dumps(analyser(paris), ensure_ascii=False, indent=2))
