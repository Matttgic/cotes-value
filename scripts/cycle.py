"""Un cycle complet : collecte -> comparaison -> paris simulés -> suivi de la clôture -> règlement -> site.

Lancé toutes les 15 minutes par GitHub Actions (.github/workflows/collecte.yml).

    python scripts/cycle.py                 # cycle complet (4 bookmakers français + Betfair, 36 h)
    python scripts/cycle.py --mode test     # cycle réduit : Winamax + Betclic, foot, 1 page

Le règlement des paris a lieu à chaque cycle.

Données (branche « donnees ») : paris.json, etat.json, opportunites/AAAA-MM-JJ.jsonl,
resultats_manuels.json (règlements faits à la main). Site : dossier site/.
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cotes import (comparaison, controle, kalshi, pinnacle, polymarket, pulsescore, reglement,  # noqa: E402
                   simulation, stockage)
from cotes import resultats as resultats_mod  # noqa: E402
from cotes.marches import harmoniser_pinnacle  # noqa: E402

# NetBet retiré le 6/10/2026 : le flux « netbet » de PulseScore est le site international (netbet.com :
# intitulés anglais, corners, handicaps asiatiques en quart, compétitions hors liste ANJ), pas netbet.fr.
FRANCAIS = ["winamax", "betclic", "unibet-fr", "pmu"]
SPORTS_FR = ["soccer", "basketball", "tennis", "ice-hockey", "handball", "volleyball", "rugby-union",
             "american-football", "baseball"]
SPORTS_BETFAIR = ["soccer", "tennis"]
HORIZON_H = 36
API = {v: k for k, v in pulsescore.SPORTS.items()}          # « football » -> « soccer »


def lire_json(chemin: Path, defaut):
    """Contenu d'un fichier de données, ou `defaut` s'il n'existe pas encore. Un fichier illisible arrête le
    cycle (erreur JSON) : le traiter comme vide écraserait, par exemple, tous les paris à la sauvegarde."""
    try:
        texte = chemin.read_text(encoding="utf-8")
    except FileNotFoundError:
        return defaut
    return json.loads(texte)


def ecrire_json(chemin: Path, donnees) -> None:
    """Écriture atomique : un cycle interrompu ne laisse jamais un fichier à moitié écrit."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    tmp = chemin.with_name(chemin.name + ".tmp")
    tmp.write_text(json.dumps(donnees, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, chemin)


def etape(nom: str, journal: dict, fonction, *args, **kwargs):
    """Exécute une étape ; une source en panne n'arrête pas le cycle (l'erreur est notée)."""
    t = time.time()
    try:
        r = fonction(*args, **kwargs)
        journal["etapes"][nom] = {"secondes": round(time.time() - t, 1), "ok": True}
        return r
    except Exception as e:                                       # noqa: BLE001
        journal["etapes"][nom] = {"secondes": round(time.time() - t, 1), "ok": False, "erreur": repr(e)[:300]}
        traceback.print_exc()
        return None


def main() -> int:
    a = argparse.ArgumentParser()
    a.add_argument("--mode", choices=["complet", "test"], default=os.environ.get("MODE_COLLECTE", "complet"))
    a.add_argument("--donnees", default="donnees")
    a.add_argument("--site", default="site")
    args = a.parse_args()
    cle = os.environ.get("PULSESCORE_KEY", "").strip()
    donnees = Path(args.donnees)
    maintenant = datetime.now(timezone.utc)
    journal = {"debut": maintenant.isoformat(timespec="seconds"), "mode": args.mode, "etapes": {}}

    # 1. références (gratuites)
    pin = etape("pinnacle", journal, lambda: harmoniser_pinnacle(pinnacle.collecter())) or []
    poly = etape("polymarket", journal, polymarket.collecter, HORIZON_H) or []
    kal = etape("kalshi", journal, kalshi.collecter, HORIZON_H) or []

    # 2. bookmakers français + Betfair (PulseScore) : seulement les sports où une référence a des matchs
    limite = maintenant + timedelta(hours=HORIZON_H)
    sports_ref = {l["sport"] for l in pin + poly + kal
                  if l.get("debut") and comparaison._t(l["debut"]) and comparaison._t(l["debut"]) <= limite}
    if args.mode == "test":
        plan = {"winamax": ["soccer"], "betclic": ["soccer"], "orbitxch": ["soccer"]}
        pages_max, horizon = 1, 12
    else:
        sports = [s for s in SPORTS_FR if pulsescore.SPORTS[s] in sports_ref]
        plan = {bm: sports for bm in FRANCAIS} | {"orbitxch": [s for s in SPORTS_BETFAIR if s in sports]}
        pages_max, horizon = 40, HORIZON_H
    lignes_ps, requetes = [], {}
    if cle:
        r = etape("pulsescore", journal, pulsescore.collecter, cle, plan, horizon, pages_max)
        if r:
            lignes_ps, requetes, erreurs_ps = r
            if erreurs_ps:                       # fonctionnement dégradé : visible dans le journal (etat.json)
                journal["etapes"]["pulsescore"] |= {"degrade": True,
                                                    "erreurs": {bm: e[:5] for bm, e in erreurs_ps.items()}}
    else:
        journal["etapes"]["pulsescore"] = {"ok": False, "erreur": "PULSESCORE_KEY absente"}
    francais = [l for l in lignes_ps if l["bookmaker"] != "orbitxch"]
    betfair = comparaison.reference_betfair([l for l in lignes_ps if l["bookmaker"] == "orbitxch"])
    references = {"Pinnacle": pin, "Betfair": betfair, "Polymarket": poly, "Kalshi": kal}

    # 3. contrôle de conformité des marchés (cumulé d'un cycle à l'autre), comparaison et paris simulés :
    #    seules les cotes dont l'intitulé est contrôlé conforme peuvent donner un pari
    index = etape("association", journal, comparaison.indexer, francais, references) or {}
    mesures = controle.mesurer(francais, index)
    etat_controle = controle.mettre_a_jour(lire_json(donnees / "controle.json", {}), mesures,
                                           journal["debut"])
    suspects = controle.matchs_suspects(mesures)
    etat_controle["matchs_suspects"] = [
        {"match_id": l["match_id"], "bookmaker": l["source"], "match": f'{l["domicile"]} – {l["exterieur"]}',
         "rapport_median": suspects[l["match_id"]]}
        for l in {l["match_id"]: l for l, *_ in mesures if l["match_id"] in suspects}.values()]
    journal["controle"] = controle.resume(etat_controle) | {"mesures": len(mesures),
                                                            "matchs_suspects": len(suspects)}
    opportunites = etape("comparaison", journal, comparaison.comparer, francais, references,
                         index=index, controle=(etat_controle, suspects)) or []
    paris = lire_json(donnees / "paris.json", [])
    nouveaux = simulation.placer(opportunites, paris)
    justes = etape("cotes_cloture", journal, comparaison.index_cotes_justes, francais, references) or {}
    simulation.suivre_cloture(paris, justes)      # heure réelle : un match peut commencer pendant le cycle

    # 4. règlement, à chaque cycle (offre PulseScore PRO : requêtes illimitées). Sans clé PulseScore, ESPN
    #    et les résultats saisis à la main règlent quand même ce qu'ils peuvent.
    enregistrements = []
    client = pulsescore.Client(cle) if cle else None
    for sport, depuis in resultats_mod.a_lire(paris, maintenant).items():
        # résultats validés par des bookmakers dont le flux marque les matchs terminés (cotes/resultats.py)
        for bm in (resultats_mod.VALIDATEURS if client and sport in API else []):
            enregistrements += etape(f"resultats_{bm}_{sport}", journal, resultats_mod.lire,
                                     client, bm, API[sport], sport, depuis) or []
        enregistrements += etape(f"resultats_espn_{sport}", journal, resultats_mod.lire_espn,
                                 sport, depuis, datetime.now(timezone.utc)) or []
    resultats = {}
    for p in paris:
        if p["statut"] in ("en_cours", "a_regler") and p["match_id"] not in resultats:
            r = resultats_mod.consensus(p, enregistrements, maintenant)
            if r:
                resultats[p["match_id"]] = r
    # mi-temps ESPN pour les paris qui en ont besoin (mi-temps/fin, 1re ou 2e mi-temps)
    for p in paris:
        r = resultats.get(p["match_id"])
        if r and p["statut"] in ("en_cours", "a_regler") and (
                p["periode"] in reglement.SOUS_PERIODES or p["marche"] == "HALF_TIME_FULL_TIME"):
            resultats[p["match_id"]] = resultats_mod.completer_periodes(p, r, enregistrements)
    journal["resultats"] = {"enregistrements": len(enregistrements), "matchs_valides": len(resultats)}
    if client:
        requetes["resultats"] = client.requetes
    reglement.appliquer(paris, resultats, lire_json(donnees / "resultats_manuels.json", {}), maintenant)
    # pourquoi les paris « à régler » ne se règlent pas (pour le diagnostic)
    vus = set()
    journal["resultats"]["non_regles"] = [
        resultats_mod.diagnostic(p, enregistrements) for p in paris
        if p["statut"] == "a_regler" and p["match_id"] not in vus and not vus.add(p["match_id"])][:80]

    # 5. sauvegarde
    paris = stockage.archiver(donnees, paris, maintenant)      # réglés depuis plus de 30 jours -> archives
    ecrire_json(donnees / "paris.json", paris)
    ecrire_json(donnees / "controle.json", etat_controle)
    ecrire_json(donnees / "opportunites_actuelles.json", sorted(opportunites, key=lambda o: -o["ecart"]))
    if opportunites:
        jour = donnees / "opportunites" / f"{maintenant:%Y-%m-%d}.jsonl.gz"
        jour.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(jour, "at", encoding="utf-8") as f:
            for o in opportunites:
                f.write(json.dumps(o, ensure_ascii=False) + "\n")
    etat = lire_json(donnees / "etat.json", {})
    mois = f"{maintenant:%Y-%m}"
    compteur = etat.get("requetes_par_mois", {})
    compteur[mois] = compteur.get(mois, 0) + sum(requetes.values())
    journal.update({
        "fin": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "requetes_pulsescore": requetes, "cotes": {"francaises": len(francais), "pinnacle": len(pin),
                                                    "betfair": len(betfair), "polymarket": len(poly),
                                                    "kalshi": len(kal)},
        "matchs_francais": len({l["match_id"] for l in francais}),
        "opportunites": sum(not o.get("suspect") for o in opportunites),
        "opportunites_suspectes": sum(bool(o.get("suspect")) for o in opportunites),
        "nouveaux_paris": len(nouveaux)})
    etat.update({"dernier_cycle": journal, "requetes_par_mois": compteur})
    historique = etat.get("historique", [])[-200:] + [{k: journal[k] for k in ("debut", "mode", "opportunites",
                                                                                "nouveaux_paris", "requetes_pulsescore")}]
    etat["historique"] = historique
    ecrire_json(donnees / "etat.json", etat)

    # 6. site
    from site_web import construire                                     # noqa: E402
    construire(donnees, Path(args.site))
    print(json.dumps({k: journal[k] for k in ("mode", "cotes", "matchs_francais", "opportunites", "nouveaux_paris",
                                               "requetes_pulsescore", "controle", "etapes")}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
