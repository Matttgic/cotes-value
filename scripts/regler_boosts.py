"""Règle à la main les boosts « jouer » (page Bilan › Boosts) dans ``donnees/boosts_resultats.json``.

Usage :
  python scripts/regler_boosts.py --donnees CHEMIN                     liste les boosts à régler (codes B-XXXXXX)
  python scripts/regler_boosts.py --donnees CHEMIN B-3F2A0C=gagne:2-1 B-91C4D2=perdu B-0A1B2C=rembourse

Statuts : gagne, perdu, rembourse ; le score après « : » est facultatif. Un code déjà réglé est remplacé.
CHEMIN = branche « donnees » extraite (scripts/cloner_donnees.sh).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cotes import boosts as B  # noqa: E402


def lire(chemin: Path, defaut):
    try:
        return json.loads(chemin.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return defaut


def regler(donnees: Path, consignes: list[str], maintenant: datetime) -> list[str]:
    """Applique ``CODE=statut[:score]`` ; renvoie une ligne de compte rendu par consigne. Code inconnu : erreur."""
    episodes = (lire(donnees / "boosts.json", {}) or {}).get("episodes") or []
    resultats = lire(donnees / "boosts_resultats.json", {})
    par_code = {B.code_boost(e["id"]): e for e in episodes if isinstance(e, dict) and e.get("id")}
    par_code.update({r["code"]: {**r, "mise_max": r.get("mise")} for r in resultats.values() if r.get("code")})
    lignes = []
    for c in consignes:
        code, _, reste = c.partition("=")
        statut, _, score = reste.partition(":")
        code, statut = code.strip().upper(), statut.strip().lower().replace("é", "e")
        e = par_code.get(code)
        if e is None:
            raise SystemExit(f"code inconnu : {code}")
        r = B.regler_boost(e, statut, maintenant, score.strip() or None)
        resultats[e["id"]] = r
        lignes.append(f"{code} {B.STATUTS_BOOST[statut]} · {r['libelle']} · {r['gain']:+.2f} €")
    (donnees / "boosts_resultats.json").write_text(json.dumps(resultats, ensure_ascii=False, indent=1) + "\n",
                                                   encoding="utf-8")
    return lignes


def main(argv=None):
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--donnees", type=Path, required=True)
    a.add_argument("consignes", nargs="*")
    args = a.parse_args(argv)
    maintenant = datetime.now(timezone.utc)
    if not args.consignes:
        episodes = (lire(args.donnees / "boosts.json", {}) or {}).get("episodes") or []
        for x in B.boosts_a_regler(episodes, lire(args.donnees / "boosts_resultats.json", {}), maintenant):
            print(x["code"], x["debut"], x["bookmaker"], x["domicile"], "–", x["exterieur"], "·", x["libelle"],
                  "· cote", x["cote"], "· mise", x["mise"])
        return
    print("\n".join(regler(args.donnees, args.consignes, maintenant)))


if __name__ == "__main__":
    main()
