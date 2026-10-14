"""Comparaison rétrospective figée, sans API, paris réels ou réoptimisation.

python scripts/comparer_strategies.py --donnees ../cotes-value-data-v2 --sortie docs/comparaison-strategies.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cotes.correspondance import normaliser  # noqa: E402
from cotes.laboratoire import (REGLES, DEBUT_ETUDE, PERIODES, audit, classer, evaluer,  # noqa: E402
                               heure, resume, selectionner)
from cotes.stockage import lire_archives  # noqa: E402
from cotes.strategie_chatgpt import paris_chatgpt  # noqa: E402
from cotes.strategie_gemini import paris_gemini  # noqa: E402


def claude_rejouee(paris: list[dict]) -> list[dict]:
    """Règles existantes, date de lancement remplacée par le début de l'étude.

    Dédoublonnage original par sélection/bookmaker, pas un seul pari par match.
    Comparateur descriptif : ne participe jamais au classement des 36 règles.
    """
    premiers = {}
    for p in paris:
        t, debut = heure(p.get("detecte")), heure(p.get("debut"))
        if (p.get("reference") not in ("Pinnacle", "Betfair", "Polymarket")
                or p.get("simulation") not in ("A", "B", "C", "D", "E")
                or not (p.get("cote") or 99) < 2.5 or not t or not debut
                or t < heure(DEBUT_ETUDE) or not timedelta(0) < debut-t < timedelta(hours=12)):
            continue
        noms = [normaliser(str(p.get(k) or "")) for k in ("domicile", "exterieur", "ligue")]
        if any(n[1] for n in noms) or any(n[2] for n in noms[:2]):
            continue
        key = tuple(p.get(k) for k in ("match_id", "marche", "periode", "ligne", "issue", "joueur"))
        if key not in premiers or t < heure(premiers[key]["detecte"]):
            premiers[key] = p
    return list(premiers.values())


def comparer(paris: list[dict], releve: str) -> dict:
    qualite = audit(paris)
    # Aucune conclusion financière sur des totaux incohérents ou doublés.
    if (qualite["ids_dupliques"] or qualite["gains_incoherents"] or qualite["dates_reglement_invalides"]
            or qualite["conflits_reglement_meme_selection"]):
        raise ValueError("Audit bloquant : " + json.dumps(qualite, ensure_ascii=False))
    def ensemble(rows):
        # Total descriptif au relevé, avec les règlements tardifs disponibles.
        # Il ne remplace jamais les coupures utilisées pour la décision.
        partie = [p for p in rows if heure(DEBUT_ETUDE) <= heure(p["debut"]) < heure(PERIODES[-1][2])]
        return resume(partie, releve, incertitude=False)

    resultats = []
    for r in REGLES:
        rows = selectionner(paris, r)
        resultats.append({"regle": r.dict(), **evaluer(rows, releve),
                          "ensemble": ensemble(rows),
                          "ids_selections": [p["id"] for p in rows]})
    v1 = paris_chatgpt(paris, depuis=DEBUT_ETUDE)
    v1_rows = [p for p in paris if id(p) in v1]
    gemini_ids = paris_gemini(paris, depuis=DEBUT_ETUDE)
    gemini_rows = [p for p in paris if id(p) in gemini_ids]
    claude_rows = claude_rejouee(paris)
    claude = {**evaluer(claude_rows, releve), "ensemble": ensemble(claude_rows)}
    # Plusieurs paris corrélés par rencontre : ne pas présenter un bootstrap par
    # pari comme un intervalle par événement pour ce comparateur descriptif.
    for periode in claude.values():
        periode["ic95"] = None
    return {"schema": 1, "releve": releve, "audit": qualite, "resultats": resultats,
            "decision": classer(resultats),
            "comparateurs": {"ChatGPT v1 (rejeu)": {**evaluer(v1_rows, releve), "ensemble": ensemble(v1_rows)},
                             "Gemini Argon v1 (rejeu)": {**evaluer(gemini_rows, releve), "ensemble": ensemble(gemini_rows)},
                             "Claude (rejeu)": claude}}


def produire(donnees: Path, sortie: Path) -> dict:
    brut = (donnees / "paris.json").read_bytes()
    ps = json.loads(brut) + lire_archives(donnees)
    sha = subprocess.check_output(["git", "-C", str(donnees), "rev-parse", "HEAD"], text=True).strip()
    etat = json.loads((donnees / "etat.json").read_text())
    # Le commit est la date à laquelle tous les règlements du cycle sont connus.
    releve = subprocess.check_output(["git", "-C", str(donnees), "show", "-s", "--format=%cI"], text=True).strip()
    rapport = comparer(ps, releve)
    rapport.update({"source": {"depot": "Matttgic/cotes-value", "branche": "donnees", "commit": sha,
                               "sha256_paris": hashlib.sha256(brut).hexdigest(),
                               "dernier_cycle": (etat.get("dernier_cycle") or {}).get("debut")},
                    "protocole": "docs/protocole-comparaison.md",
                    "calcule_le": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    sortie.parent.mkdir(parents=True, exist_ok=True)
    sortie.write_text(json.dumps(rapport, ensure_ascii=False, indent=2)+"\n")
    return rapport


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--donnees", type=Path, required=True)
    parser.add_argument("--sortie", type=Path, required=True)
    args = parser.parse_args()
    r = produire(args.donnees, args.sortie)
    print(json.dumps({"source": r["source"], "audit": r["audit"], "decision": r["decision"],
                      "comparateurs": r["comparateurs"]}, ensure_ascii=False, indent=2))
  
