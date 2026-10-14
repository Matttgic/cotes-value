"""Rejeu descriptif commun et reproductible de Jules v2 reconstruite.

Pas d'optimisation des seuils ni d'appel à une API sportive. Les résultats
historiques déjà vus ne constituent pas une validation indépendante.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cotes.laboratoire import DEBUT_ETUDE, PERIODES, PARIS, audit, heure, resume  # noqa: E402
from cotes.reglement import GAIN, gain  # noqa: E402
from cotes.stockage import lire_archives  # noqa: E402
from cotes.strategie_chatgpt import paris_chatgpt  # noqa: E402
from cotes.strategie_gemini import paris_gemini  # noqa: E402
from cotes.strategie_jules import paris_jules  # noqa: E402
from cotes.strategie_jules_v2 import JULES_V2, analyser_jules_v2, paris_jules_v2  # noqa: E402
from cotes.strategie_m3 import paris_m3  # noqa: E402
from scripts.comparer_strategies import claude_rejouee  # noqa: E402

LIVREE = "b3e8e8c927b51747170e21892815f0903653a52c"
RELEVE = "2026-10-14T10:09:28+00:00"


def mesures(rows, cutoff):
    s = resume(rows, cutoff, incertitude=False)
    jours = defaultdict(list)
    for p in rows:
        if p.get("statut") in GAIN and heure(p.get("regle_le")) and heure(p["detecte"]) <= heure(p["regle_le"]) < heure(cutoff):
            jours[heure(p["debut"]).astimezone(PARIS).date().isoformat()].append(gain(p["statut"], 10, p["cote"]))
    groupes = [(sum(g), len(g)) for _, g in sorted(jours.items())]
    s["jours_regles"] = len(groupes)
    s["ic95_jours"] = None
    if len(groupes) >= 2:
        rng, tirages = random.Random(20261015), []
        for _ in range(5000):
            echantillon = rng.choices(groupes, k=len(groupes))
            tirages.append(100*sum(g for g, _ in echantillon)/(10*sum(n for _, n in echantillon)))
        tirages.sort()
        s["ic95_jours"] = [round(tirages[124], 2), round(tirages[4874], 2)]
    return s


def rapport(paris, releve=RELEVE, selection_livree=None):
    cutoff = heure(releve)
    if not cutoff:
        raise ValueError("Relevé invalide")
    qualite = audit(paris)
    if any(qualite[k] for k in ("ids_dupliques", "gains_incoherents", "dates_reglement_invalides", "conflits_reglement_meme_selection")):
        raise ValueError("Audit des données bloquant")
    observes = [p for p in paris if heure(p.get("detecte")) and heure(p["detecte"]) <= cutoff]
    selecteurs = {"JULES EDGE v1": paris_jules, "JULES EDGE v2 reconstruite": paris_jules_v2,
                  "Claude": None, "ChatGPT v1": paris_chatgpt, "Gemini Argon v1": paris_gemini, "M3": paris_m3}
    if selection_livree:
        selecteurs["JULES EDGE v2 livrée (doublons possibles)"] = selection_livree
    comparateurs = {}
    for nom, selecteur in selecteurs.items():
        if selecteur:
            ids = selecteur(observes, depuis=DEBUT_ETUDE)
            lignes = [p for p in observes if id(p) in ids]
        else:
            lignes = claude_rejouee(observes)
        # Les matchs hors fenêtre ont aussi consommé leurs places journalières.
        ensemble = [p for p in lignes if heure(DEBUT_ETUDE) <= heure(p["debut"]) < heure(PERIODES[-1][2])]
        r = {"ensemble": mesures(ensemble, releve), "ids_selections": [p["id"] for p in ensemble]}
        for periode, debut, fin in PERIODES:
            partie = [p for p in lignes if heure(debut) <= heure(p["debut"]) < heure(fin)]
            r[periode] = mesures(partie, releve if periode == "test" else fin)
        comparateurs[nom] = r
    diagnostic = analyser_jules_v2(observes, depuis=DEBUT_ETUDE)
    diagnostic.pop("selection")
    return {"schema": 1, "releve": releve, "debut_etude": DEBUT_ETUDE,
            "fin_etude": PERIODES[-1][2], "strategie": JULES_V2,
            "nature": "Rejeu exploratoire ; bootstrap par jour descriptif ; aucune rentabilité future démontrée.",
            "audit": qualite, "identite": diagnostic, "comparateurs": comparateurs,
            "source_sha256": hashlib.sha256(json.dumps(paris, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
            "selecteur_sha256": hashlib.sha256((Path(__file__).resolve().parent.parent/"cotes/strategie_jules_v2.py").read_bytes()).hexdigest(),
            "protocole_sha256": hashlib.sha256((Path(__file__).resolve().parent.parent/"docs/protocole-jules-v2.md").read_bytes()).hexdigest()}


def main():
    a = argparse.ArgumentParser(description=__doc__)
    a.add_argument("--donnees", type=Path, required=True)
    a.add_argument("--sortie", type=Path, required=True)
    a.add_argument("--releve", default=RELEVE)
    a.add_argument("--livree-commit", default=LIVREE)
    args = a.parse_args()
    source = subprocess.check_output(["git", "show", args.livree_commit+":cotes/strategie_jules.py"], text=True)
    namespace = {"__name__": "jules_livree"}
    exec(compile(source, args.livree_commit, "exec"), namespace)
    paris = json.loads((args.donnees/"paris.json").read_text())+lire_archives(args.donnees)
    r = rapport(paris, args.releve, namespace["paris_jules_v2"])
    r["source_commit"] = subprocess.check_output(["git", "-C", str(args.donnees), "rev-parse", "HEAD"], text=True).strip()
    r["livree_commit"] = args.livree_commit
    r["livree_code_sha256"] = hashlib.sha256(source.encode()).hexdigest()
    args.sortie.parent.mkdir(parents=True, exist_ok=True)
    args.sortie.write_text(json.dumps(r, ensure_ascii=False, indent=2)+"\n")
    for nom, s in r["comparateurs"].items():
        print(nom, json.dumps({k:s["ensemble"][k] for k in ("paris", "regles", "gain", "roi", "clv", "drawdown", "ic95_jours")}, ensure_ascii=False))
    print("Identité", json.dumps(r["identite"], ensure_ascii=False))


if __name__ == "__main__":
    main()
