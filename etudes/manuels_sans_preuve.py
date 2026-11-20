"""Revue des règlements manuels sans preuve (audit du 20/11/2026, priorité 10). Lecture seule.

Usage : python etudes/manuels_sans_preuve.py --donnees CHEMIN [--sortie FICHIER.md]
CHEMIN = branche « donnees » extraite (paris.json, resultats_manuels.json).

Pour chaque pari réglé par un statut saisi à la main sans source ni score, cherche un score connu du même match
(saisie par match de resultats_manuels.json, ou preuve d'un autre pari du même match réglé automatiquement) et
rejoue le règlement avec ce score. Trois verdicts : « confirmé » (le score donne le même statut), « contredit »
(il en donne un autre : à corriger sous l'identifiant du pari, avec source et score) et « sans score » (à vérifier à
la main). Rien n'est écrit dans les données.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cotes import reglement  # noqa: E402

MANUEL = "statut saisi à la main"


def _scores_connus(paris: list[dict], manuels: dict) -> dict[str, tuple[dict, str]]:
    """match_id → (scores par période, d'où vient le score)."""
    connus: dict[str, tuple[dict, str]] = {}
    for p in paris:
        q = p.get("preuve_reglement") or {}
        if q.get("origine") != MANUEL and isinstance(q.get("scores"), dict) and p.get("match_id") not in connus:
            sc = {k: tuple(v) if isinstance(v, list) else v for k, v in q["scores"].items()}
            connus[p["match_id"]] = (sc, f"pari {p['id']} ({q.get('origine')})")
    for mid, m in manuels.items():
        if isinstance(m, dict) and m.get("score") and mid not in connus:
            sc = {"MATCH": tuple(m["score"])}
            if m.get("mi_temps"):
                sc["MT1"] = tuple(m["mi_temps"])
                sc["MT2"] = (sc["MATCH"][0] - sc["MT1"][0], sc["MATCH"][1] - sc["MT1"][1])
            if m.get("temps_reglementaire"):
                sc["TEMPS_REG"] = tuple(m["temps_reglementaire"])
            connus[mid] = (sc, f"saisie par match ({m.get('source')})")
    return connus


def revoir(paris: list[dict], manuels: dict) -> list[dict]:
    connus = _scores_connus(paris, manuels)
    lignes = []
    for p in paris:
        q = p.get("preuve_reglement") or {}
        if q.get("origine") != MANUEL or q.get("source"):
            continue
        sc, origine = connus.get(p.get("match_id"), (None, None))
        rejoue = reglement.regler(p, sc) if sc else None
        verdict = "sans score" if rejoue is None else "confirmé" if rejoue == p.get("statut") else "contredit"
        lignes.append({"id": p["id"], "detecte": (p.get("detecte") or "")[:16], "bookmaker": p.get("bookmaker"),
                       "match": f"{p.get('domicile')} – {p.get('exterieur')}", "marche": p.get("marche"),
                       "periode": p.get("periode"), "issue": p.get("issue"), "ligne": p.get("ligne"),
                       "statut": p.get("statut"), "gain": p.get("gain"), "rejoue": rejoue, "verdict": verdict,
                       "score_de": origine})
    return lignes


def rapport(lignes: list[dict]) -> str:
    par = Counter((x["statut"], x["verdict"]) for x in lignes)
    gains = defaultdict(float)
    for x in lignes:
        gains[x["verdict"]] += x["gain"] or 0.0
    out = ["# Règlements manuels sans preuve", "",
           f"{len(lignes)} paris réglés par un statut saisi à la main, sans source ni score.", "",
           "| Statut | Verdict | Paris |", "| --- | --- | --- |"]
    out += [f"| {s} | {v} | {n} |" for (s, v), n in sorted(par.items())]
    out += ["", "Gain compté par verdict : " + " · ".join(f"{v} {g:+.2f} €" for v, g in sorted(gains.items())), "",
            "| Pari | Détecté | Bookmaker | Match | Marché | Statut | Rejoué | Verdict | Score lu |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    ordre = {"contredit": 0, "sans score": 1, "confirmé": 2}
    for x in sorted(lignes, key=lambda x: (ordre[x["verdict"]], x["detecte"])):
        marche = " ".join(str(v) for v in (x["marche"], x["periode"], x["issue"], x["ligne"]) if v is not None)
        out.append(f"| `{x['id']}` | {x['detecte']} | {x['bookmaker']} | {x['match']} | {marche} | {x['statut']} | "
                   f"{x['rejoue'] or '—'} | {x['verdict']} | {x['score_de'] or '—'} |")
    return "\n".join(out) + "\n"


def main() -> None:
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--donnees", required=True, type=Path)
    a.add_argument("--sortie", type=Path)
    args = a.parse_args()
    paris = json.loads((args.donnees / "paris.json").read_text(encoding="utf-8"))
    manuels = json.loads((args.donnees / "resultats_manuels.json").read_text(encoding="utf-8"))
    texte = rapport(revoir(paris, manuels))
    if args.sortie:
        args.sortie.write_text(texte, encoding="utf-8")
    else:
        print(texte)


if __name__ == "__main__":
    main()
