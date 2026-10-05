"""Un cycle complet : collecte -> comparaison -> paris simulés -> suivi de la clôture -> règlement -> site.

Lancé toutes les 15 minutes par GitHub Actions (.github/workflows/collecte.yml).

    python scripts/cycle.py                 # cycle complet (5 bookmakers français + Betfair, 36 h)
    python scripts/cycle.py --mode test     # cycle réduit : Winamax + Betclic, foot, 1 page (≈ 4 requêtes)
    python scripts/cycle.py --regler        # force le règlement (sinon : une fois par heure)

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
from cotes import comparaison, kalshi, pinnacle, polymarket, pulsescore, reglement, simulation  # noqa: E402
from cotes.marches import harmoniser_pinnacle  # noqa: E402

FRANCAIS = ["winamax", "betclic", "unibet-fr", "pmu", "netbet"]
SPORTS_FR = ["soccer", "basketball", "tennis", "ice-hockey", "handball", "volleyball", "rugby-union",
             "american-football", "baseball"]
SPORTS_BETFAIR = ["soccer", "tennis"]
HORIZON_H = 36
API = {v: k for k, v in pulsescore.SPORTS.items()}          # « football » -> « soccer »


def lire_json(chemin: Path, defaut):
    try:
        return json.loads(chemin.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return defaut


def ecrire_json(chemin: Path, donnees) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps(donnees, ensure_ascii=False, indent=1), encoding="utf-8")


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
    a.add_argument("--regler", action="store_true")
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
            lignes_ps, requetes = r
    else:
        journal["etapes"]["pulsescore"] = {"ok": False, "erreur": "PULSESCORE_KEY absente"}
    francais = [l for l in lignes_ps if l["bookmaker"] != "orbitxch"]
    betfair = comparaison.reference_betfair([l for l in lignes_ps if l["bookmaker"] == "orbitxch"])
    references = {"Pinnacle": pin, "Betfair": betfair, "Polymarket": poly, "Kalshi": kal}

    # 3. comparaison et paris simulés
    opportunites = etape("comparaison", journal, comparaison.comparer, francais, references) or []
    paris = lire_json(donnees / "paris.json", [])
    nouveaux = simulation.placer(opportunites, paris)
    justes = etape("cotes_cloture", journal, comparaison.index_cotes_justes, francais, references) or {}
    simulation.suivre_cloture(paris, justes, maintenant)

    # 4. règlement (une fois par heure, ou sur demande)
    if cle and (args.regler or maintenant.minute < 15):
        a_regler = {}
        for p in paris:
            if p["statut"] in ("en_cours", "a_regler"):
                debut = comparaison._t(p["debut"])
                if debut and maintenant - debut > timedelta(hours=2):
                    a_regler.setdefault((p["match_id"].split("|")[0], p["sport"]), True)
        resultats = {}
        client = pulsescore.Client(cle)
        for (bm, sport) in a_regler:
            if sport in API:
                resultats |= etape(f"resultats_{bm}_{sport}", journal, reglement.lire_resultats_pulsescore,
                                   client, bm, API[sport], sport) or {}
        requetes["resultats"] = client.requetes
        reglement.appliquer(paris, resultats, lire_json(donnees / "resultats_manuels.json", {}), maintenant)

    # 5. sauvegarde
    ecrire_json(donnees / "paris.json", paris)
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
        "matchs_francais": len({l["match_id"] for l in francais}), "opportunites": len(opportunites),
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
                                               "requetes_pulsescore", "etapes")}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
