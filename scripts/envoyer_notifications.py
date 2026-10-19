"""Transmet le flux public à l'expéditeur, authentifié par l'identité GitHub Actions.

Aucune clé Web Push ou donnée d'abonnement n'est nécessaire dans GitHub.
Une panne de notification ne doit pas interrompre la collecte ni le règlement.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cotes.notifications import API, PIN2  # noqa: E402

WEBHOOK_TIMEOUT_S = 5            # par requête
WEBHOOK_BUDGET_S = 25            # pour tout le passage : ne jamais retarder le scan ni les alertes Chrome
WEBHOOK_MAX = 20
ENVOYES = "webhook_envoyes.json"
CHAMPS_WEBHOOK = ("id", "match", "ligue", "debut", "marche", "selection", "bookmaker", "cote", "cote_min",
                  "cote_juste", "cote_pinnacle", "ecart", "recheck")


def preparer(donnees: Path, maintenant: datetime | None = None) -> dict:
    """Même sélection que le site, sans attendre sa génération ni les résultats."""
    from cotes import stockage
    from cotes.convergence import selections
    from cotes.strategies_prudentes import selections_prudentes
    from cotes.notifications import flux, selections_labo
    paris = stockage.fusionner_paris(json.loads((donnees / "paris.json").read_text()), stockage.lire_archives(donnees))
    actuelles = json.loads((donnees / "opportunites_actuelles.json").read_text())
    retenus = selections(paris)
    retenus.update(selections_prudentes(paris, bases=retenus))
    retenus.update(selections_labo(paris))
    return flux(actuelles, paris, retenus, maintenant)


def charge_utile(a: dict) -> dict:
    """Corps JSON d'une alerte : champs convenus, début du match en UTC."""
    out = {k: a.get(k) for k in CHAMPS_WEBHOOK}
    try:
        d = datetime.fromisoformat(str(a.get("debut")).replace("Z", "+00:00"))
        out["debut"] = d.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    except ValueError:
        pass
    out["recheck"] = bool(a.get("recheck"))
    return out


def alertes_webhook(flux: dict, paris: list[dict], envoyes: dict, maintenant: datetime | None = None) -> list[dict]:
    """Alertes Pinnacle 2 pas encore envoyées : celles du scan, puis les paris re-décidés (même s'ils datent)."""
    from cotes.notifications import alertes_recheck
    vues, out = set(envoyes), []
    for a in [x for x in flux.get("alertes", []) if PIN2 in x.get("strategies", [])] + alertes_recheck(paris, PIN2, maintenant):
        if a["id"] not in vues:
            vues.add(a["id"])
            out.append(a)
    return out


def poster_webhook(alertes: list[dict], env=None, ouvrir=urlopen, horloge=time.monotonic) -> dict:
    """Une requête par alerte. Ne lève jamais ; ni l'URL ni la clé n'apparaissent dans le résultat."""
    env = os.environ if env is None else env
    url, cle = env.get("ALERTE_WEBHOOK_URL", "").strip(), env.get("ALERTE_WEBHOOK_KEY", "").strip()
    bilan = {"envoyees": [], "echecs": 0, "erreurs": []}
    if not url:
        return {**bilan, "actif": False}
    if not url.startswith("https://"):
        return {**bilan, "actif": False, "erreurs": ["URL refusée (https obligatoire)"]}
    entete = env.get("ALERTE_WEBHOOK_CLE_ENTETE", "").strip() or "x-api-key"
    debut = horloge()
    for a in alertes[:WEBHOOK_MAX]:
        if horloge() - debut > WEBHOOK_BUDGET_S:
            bilan["erreurs"].append("budget de temps atteint")
            break
        en_tetes = {"Content-Type": "application/json", "User-Agent": "cotes-value"}
        if cle:
            en_tetes[entete] = cle
        try:
            requete = Request(url, data=json.dumps(charge_utile(a), ensure_ascii=False).encode(), headers=en_tetes, method="POST")
            with ouvrir(requete, timeout=WEBHOOK_TIMEOUT_S) as r:
                code = getattr(r, "status", 200)
            if 200 <= code < 300:
                bilan["envoyees"].append(a["id"])
                continue
            bilan["erreurs"].append(f"HTTP {code}")
        except HTTPError as e:
            bilan["erreurs"].append(f"HTTP {e.code}")
        except (URLError, OSError, ValueError, TypeError) as e:
            bilan["erreurs"].append(type(e).__name__)
        bilan["echecs"] += 1
    bilan["erreurs"] = sorted(set(bilan["erreurs"]))[:5]
    return {**bilan, "actif": True}


def webhook_pinnacle2(donnees: Path, flux: dict) -> dict:
    """Envoie les nouvelles alertes Pinnacle 2 et mémorise leurs id. Toute erreur est journalisée, jamais levée."""
    from scripts.cycle import ecrire_json
    try:
        chemin = donnees / ENVOYES
        try:
            envoyes = json.loads(chemin.read_text()) if chemin.exists() else {}
        except ValueError:
            envoyes = {}
        maintenant = datetime.now(timezone.utc)
        limite = (maintenant - timedelta(days=3)).isoformat(timespec="seconds")
        recents = {k: v for k, v in envoyes.items() if isinstance(v, str) and v >= limite}
        paris = json.loads((donnees / "paris.json").read_text())
        a_envoyer = alertes_webhook(flux, paris, recents, maintenant)
        if not a_envoyer:
            return {"actif": bool(os.environ.get("ALERTE_WEBHOOK_URL", "").strip()), "envoyees": 0, "echecs": 0}
        bilan = poster_webhook(a_envoyer)
        for pid in bilan["envoyees"]:
            recents[pid] = maintenant.isoformat(timespec="seconds")
        if bilan["envoyees"]:
            ecrire_json(chemin, recents)
        return {"actif": bilan["actif"], "envoyees": len(bilan["envoyees"]), "echecs": bilan["echecs"],
                "recheck": sum(1 for a in a_envoyer if a.get("recheck")), "erreurs": bilan["erreurs"]}
    except Exception as e:  # noqa: BLE001 - le scan ne doit jamais dépendre du webhook
        return {"actif": False, "envoyees": 0, "echecs": 0, "erreurs": [type(e).__name__]}


def envoyer_et_journaliser(donnees: Path, destination: Path) -> dict:
    from scripts.cycle import ecrire_json
    flux = preparer(donnees)
    ecrire_json(destination, flux)
    webhook = webhook_pinnacle2(donnees, flux)
    debut = datetime.now(timezone.utc)
    bilan = transmettre(flux)
    fin = datetime.now(timezone.utc)
    # Données publiques de diagnostic uniquement, jamais d'abonnement ni de jeton.
    journal = {"prepare_le": flux["generated_at"], "envoi_demande_le": debut.isoformat(),
               "envoi_termine_le": fin.isoformat(), "resultat": bilan, "webhook": webhook,
               "alertes": [{k:a.get(k) for k in ("id","match","pari","bookmaker","cote","collecte_le","age_prix_secondes","detecte")}
                            for a in flux["alertes"]]}
    ancien = donnees / "notifications_diagnostic.json"
    historique = json.loads(ancien.read_text()) if ancien.exists() else {"cycles": []}
    ecrire_json(ancien, {"cycles": (historique.get("cycles", [])+[journal])[-100:]})
    return bilan


def transmettre(flux: dict, env=None, ouvrir=urlopen) -> dict:
    env = os.environ if env is None else env
    url = env.get("ACTIONS_ID_TOKEN_REQUEST_URL", "")
    credential = env.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN", "")
    if not url.startswith("https://") or not credential:
        return {"ok": False, "erreur": "Identité GitHub Actions indisponible"}
    try:
        sep = "&" if "?" in url else "?"
        requete = Request(url + sep + urlencode({"audience": "cotes-value-notifications"}),
                          headers={"Authorization": f"Bearer {credential}"})
        with ouvrir(requete, timeout=20) as r:
            token = json.load(r).get("value")
        if not isinstance(token, str) or not token:
            return {"ok": False, "erreur": "Identité GitHub invalide"}
        requete = Request(API + "/dispatch", data=json.dumps(flux, ensure_ascii=False).encode(),
                          headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        with ouvrir(requete, timeout=60) as r:
            d = json.load(r)
        # Liste blanche : ne jamais imprimer des jetons ou abonnements renvoyés par erreur.
        return {k: d[k] for k in ("ok", "sent", "expired", "failed", "devices") if k in d}
    except HTTPError as e:
        return {"ok": False, "erreur": f"Service notifications HTTP {e.code}"}
    except (URLError, OSError, ValueError, TypeError):
        return {"ok": False, "erreur": "Service notifications indisponible"}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--flux", type=Path, default=Path("site/notifications.json"))
    p.add_argument("--donnees", type=Path, help="Préparer les alertes immédiatement depuis les données sauvegardées")
    args = p.parse_args()
    bilan = envoyer_et_journaliser(args.donnees,args.flux) if args.donnees else transmettre(json.loads(args.flux.read_text(encoding="utf-8")))
    print(json.dumps(bilan, ensure_ascii=False))
    sys.exit(0 if bilan.get("ok") else 1)
