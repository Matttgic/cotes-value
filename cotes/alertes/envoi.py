"""Transmet le flux public à l'expéditeur, authentifié par l'identité GitHub Actions.

Aucune clé Web Push ou donnée d'abonnement n'est nécessaire dans GitHub.
Une panne de notification ne doit pas interrompre la collecte ni le règlement.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from cotes.notifications import API, NOMS, PIN2  # noqa: E402,F401  (PIN2 : lu par les tests)
from cotes.recap_jouables import mise_arrondie  # noqa: E402,F401
# fonctions sans réseau déplacées dans cotes/alertes/ (E5.1) ; noms gardés sur le module
from cotes.alertes.webhook import (CHAMPS_WEBHOOK, charge_utile, est_ntfy, _fr, _min_affichee,  # noqa: E402,F401
                                   SPORTS, JOURS, _sport, _ligne_pinnacle, message_ntfy, _lignes_mise, _entete_utf8,
                                   alertes_webhook)
from cotes.alertes.pushover import (PUSHOVER_TTL_MAX_S, strategies_pushover, alertes_pushover,  # noqa: E402,F401
                                    BANKROLL_REFERENCE, _bankroll, METHODE_CLAUDE, METHODE_ECART_MIN, METHODE_MISE,
                                    ligne_methode_claude, message_pushover)
from cotes.alertes.chrome import lire_paris, preparer  # noqa: E402,F401

WEBHOOK_TIMEOUT_S = 5            # par requête
WEBHOOK_BUDGET_S = 25            # pour tout le passage : ne jamais retarder le scan ni les alertes Chrome
WEBHOOK_MAX = 20
ENVOYES = "webhook_envoyes.json"
PUSHOVER_URL = "https://api.pushover.net/1/messages.json"
PUSHOVER_ENVOYES = "pushover_envoyes.json"
PUSHOVER_BUDGET_S = 20           # pour tout le passage


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
    ntfy = est_ntfy(url)
    debut = horloge()
    for a in alertes[:WEBHOOK_MAX]:
        if horloge() - debut > WEBHOOK_BUDGET_S:
            bilan["erreurs"].append("budget de temps atteint")
            break
        en_tetes = {"Content-Type": "application/json", "User-Agent": "cotes-value"}
        if cle:                                   # clé facultative : sans elle, aucun en-tête d'authentification
            en_tetes[entete] = cle
        try:
            if ntfy:
                titre, corps = message_ntfy(a)
                en_tetes.update({"Content-Type": "text/plain; charset=utf-8", "Title": _entete_utf8(titre),
                                 "Priority": "high", "Tags": "moneybag"})
                if a.get("lien"):
                    en_tetes["Click"] = a["lien"]          # toucher la notification ouvre le match
                donnees = corps.encode()
            else:
                donnees = json.dumps(charge_utile(a), ensure_ascii=False).encode()
            requete = Request(url, data=donnees, headers=en_tetes, method="POST")
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


def webhook_pinnacle2(donnees: Path, flux: dict, paris: list[dict] | None = None) -> dict:
    """Envoie les nouvelles alertes Pinnacle 2 et mémorise leurs id. Toute erreur est journalisée, jamais levée."""
    from cotes.depot.json_io import ecrire_json
    try:
        chemin = donnees / ENVOYES
        try:
            envoyes = json.loads(chemin.read_text()) if chemin.exists() else {}
        except ValueError:
            envoyes = {}
        maintenant = datetime.now(timezone.utc)
        limite = (maintenant - timedelta(days=3)).isoformat(timespec="seconds")
        recents = {k: v for k, v in envoyes.items() if isinstance(v, str) and v >= limite}
        paris = lire_paris(donnees) if paris is None else paris
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


ORIGINE_SITE = "https://matttgic.github.io"


def choix_pushover_public(ouvrir=urlopen) -> list[str] | None:
    """Choix du bloc « Alertes Pushover », par la lecture publique du site (de simples clés de stratégie, sans jeton).
    Pour le serveur en direct, qui n'a pas l'identité GitHub Actions. ``None`` sans choix enregistré ou injoignable."""
    try:
        with ouvrir(Request(API + "/pushover-lire", data=b"{}", method="POST",
                            headers={"Content-Type": "application/json", "Origin": ORIGINE_SITE}), timeout=10) as r:
            d = json.load(r)
        cles = d.get("strategies") if d.get("defini") is True else None
        return [c for c in cles if isinstance(c, str)] if isinstance(cles, list) else None
    except (HTTPError, URLError, OSError, ValueError, TypeError, AttributeError):
        return None


def strategies_du_site(env=None, ouvrir=urlopen) -> list[str] | None:
    """Stratégies cochées sur le site (appareils actifs), lues auprès du service de notifications avec l'identité GitHub
    Actions. ``None`` si le service est injoignable ou n'a pas encore l'action (fonction non redéployée).
    Serveur en direct (``SERVEUR_DIRECT=oui``, sans cette identité) : le choix Pushover enregistré sur le site, par sa
    lecture publique."""
    env = os.environ if env is None else env
    url, credential = env.get("ACTIONS_ID_TOKEN_REQUEST_URL", ""), env.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN", "")
    if not url.startswith("https://") or not credential:
        return choix_pushover_public(ouvrir) if env.get("SERVEUR_DIRECT") == "oui" else None
    try:
        sep = "&" if "?" in url else "?"
        with ouvrir(Request(url + sep + urlencode({"audience": "cotes-value-notifications"}),
                            headers={"Authorization": f"Bearer {credential}"}), timeout=10) as r:
            jeton = json.load(r).get("value")
        if not isinstance(jeton, str) or not jeton:
            return None
        with ouvrir(Request(API + "/strategies", data=b"{}", method="POST",
                            headers={"Authorization": f"Bearer {jeton}", "Content-Type": "application/json"}),
                    timeout=10) as r:
            cles = json.load(r).get("strategies")
        return [c for c in cles if isinstance(c, str)] if isinstance(cles, list) else None
    except (HTTPError, URLError, OSError, ValueError, TypeError, AttributeError):
        return None


def choix_pushover(env=None, ouvrir=urlopen) -> tuple[set[str], list[str], str]:
    """(stratégies, clés inconnues, source). ``PUSHOVER_STRATEGIES`` rempli (et différent de « auto ») : cette liste.
    Vide ou « auto » : le choix fait sur le site (bloc « Alertes Pushover », sinon les cases de l'abonnement Chrome) ;
    si le service ne répond pas, aucune alerte (jamais de liste inventée)."""
    env = os.environ if env is None else env
    brut = env.get("PUSHOVER_STRATEGIES", "").strip()
    if brut and brut.lower() != "auto":
        choisies, inconnues = strategies_pushover(env)
        return choisies, inconnues, "variable"
    cles = strategies_du_site(env, ouvrir)
    if cles is None:
        return set(), [], "site indisponible"
    from cotes.alertes.promos import SPECIALES
    return {c for c in cles if c in NOMS or c in SPECIALES}, [], "site"


def poster_pushover(alertes: list[dict], env=None, ouvrir=urlopen, horloge=time.monotonic) -> dict:
    """Une requête par alerte. Ne lève jamais ; ni le jeton ni la clé n'apparaissent dans le résultat."""
    env = os.environ if env is None else env
    jeton, cle = env.get("PUSHOVER_APP_TOKEN", "").strip(), env.get("PUSHOVER_USER_KEY", "").strip()
    bilan = {"envoyees": [], "echecs": 0, "erreurs": []}
    if not jeton or not cle:
        return {**bilan, "actif": False}
    debut = horloge()
    for a in alertes[:WEBHOOK_MAX]:
        if horloge() - debut > PUSHOVER_BUDGET_S:
            bilan["erreurs"].append("budget de temps atteint")
            break
        try:
            donnees = urlencode({"token": jeton, "user": cle, **message_pushover(a, env)}).encode()
            with ouvrir(Request(PUSHOVER_URL, data=donnees, method="POST",
                                headers={"User-Agent": "cotes-value"}), timeout=WEBHOOK_TIMEOUT_S) as r:
                code, corps = getattr(r, "status", 200), json.load(r)
            if 200 <= code < 300 and corps.get("status") == 1:
                bilan["envoyees"].append(a["id"])
                continue
            bilan["erreurs"].append(f"HTTP {code}")
        except HTTPError as e:
            bilan["erreurs"].append(f"HTTP {e.code}")
            if e.code == 429:                   # quota mensuel : inutile d'insister
                bilan["echecs"] += 1
                break
        except (URLError, OSError, ValueError, TypeError, AttributeError) as e:
            bilan["erreurs"].append(type(e).__name__)
        bilan["echecs"] += 1
    bilan["erreurs"] = sorted(set(bilan["erreurs"]))[:5]
    return {**bilan, "actif": True}


def pushover(donnees: Path, flux: dict, env=None, paris: list[dict] | None = None) -> dict:
    """Envoie les nouvelles alertes des stratégies cochées et mémorise leurs id. Jamais de levée."""
    from cotes.depot.json_io import ecrire_json
    env = os.environ if env is None else env
    try:
        actif = bool(env.get("PUSHOVER_APP_TOKEN", "").strip() and env.get("PUSHOVER_USER_KEY", "").strip())
        if not actif:                    # sans secrets, on n'interroge même pas le service
            return {"actif": False, "strategies": 0, "envoyees": 0, "echecs": 0, "source": "secrets absents"}
        choisies, inconnues, source = choix_pushover(env)
        base = {"actif": bool(choisies), "strategies": len(choisies), "source": source, "envoyees": 0, "echecs": 0}
        if inconnues:
            base["inconnues"] = inconnues
        if not base["actif"]:
            return base
        chemin = donnees / PUSHOVER_ENVOYES
        amorcage = not chemin.exists()
        try:
            envoyes = json.loads(chemin.read_text()) if chemin.exists() else {}
        except ValueError:
            envoyes, amorcage = {}, True
        maintenant = datetime.now(timezone.utc)
        limite = (maintenant - timedelta(days=3)).isoformat(timespec="seconds")
        recents = {k: v for k, v in envoyes.items() if isinstance(v, str) and (v >= limite or v == "")}
        paris = lire_paris(donnees) if paris is None else paris
        a_envoyer = alertes_pushover(flux, paris, recents, choisies, maintenant, amorcage)
        from cotes.alertes import promos                  # surebets et cotes boostées, cases à part
        a_envoyer += promos.alertes(donnees, recents, choisies, maintenant)
        # Bankroll automatique (cotes/alertes/bankroll.py) : les mises suivent la bankroll calculée, pas le chiffre fixe.
        from cotes.alertes import bankroll as bankroll_auto
        etat_bk = None
        if bankroll_auto.actif(env):
            try:
                etat_bk = bankroll_auto.mettre_a_jour(bankroll_auto.lire(donnees), paris, env, maintenant)
                env = {**env, "PUSHOVER_BANKROLL": str(etat_bk["mise_sur"])}
            except Exception:  # noqa: BLE001 - sans bankroll calculée, les mises restent sur PUSHOVER_BANKROLL
                etat_bk = None
        bilan = poster_pushover(a_envoyer, env) if a_envoyer else {"envoyees": [], "echecs": 0, "erreurs": []}
        for pid in bilan["envoyees"]:
            recents[pid] = maintenant.isoformat(timespec="seconds")
        if bilan["envoyees"] or amorcage or len(recents) != len(envoyes):
            ecrire_json(chemin, recents)
        if etat_bk is not None:
            envoyees = set(bilan["envoyees"])
            bankroll_auto.noter(etat_bk, [a for a in a_envoyer if a["id"] in envoyees], maintenant)
            bankroll_auto.ecrire(donnees, etat_bk)
        recap = recap_pushover(donnees, paris, recents, env, maintenant)
        retour = {**base, "envoyees": len(bilan["envoyees"]), "echecs": bilan["echecs"],
                  "erreurs": bilan["erreurs"], "recap": recap}
        if etat_bk is not None:
            retour["bankroll"] = {"calculee": etat_bk["bankroll"], "mise_sur": etat_bk["mise_sur"],
                                  "ouvertes": len(etat_bk["ouvertes"])}
        return retour
    except Exception as e:  # noqa: BLE001 - le scan ne doit jamais dépendre de Pushover
        return {"actif": False, "envoyees": 0, "echecs": 0, "erreurs": [type(e).__name__]}


def recap_pushover(donnees: Path, paris: list[dict], envoyes: dict, env, maintenant: datetime,
                   ouvrir=urlopen) -> dict:
    """Récapitulatif « encore jouables » (cotes/recap_jouables.py), une fois par jour à ``PUSHOVER_RECAP_HEURE``.
    Jamais de levée ; l'état (dernier jour, dernière heure) est dans ``pushover_recap.json``."""
    from cotes import recap_jouables as R
    from cotes.depot.json_io import ecrire_json
    try:
        heure = R.heure_recap(env)
        if heure is None:
            return {"actif": False}
        chemin = donnees / R.ETAT
        try:
            etat = json.loads(chemin.read_text()) if chemin.exists() else {}
        except ValueError:
            etat = {}
        if not R.est_l_heure(maintenant, heure, etat.get("jour")):
            return {"actif": True, "envoye": False}
        depuis = (datetime.fromisoformat(etat["le"]) if etat.get("le") else maintenant - R.FENETRE_MAX)
        depuis = max(depuis, maintenant - R.FENETRE_MAX)
        cands = R.candidats(paris, envoyes, depuis, maintenant)
        cotes = R.dernieres_cotes(donnees, {R.cle_historique(p) for p in cands}, maintenant)
        lignes = R.jouables(cands, cotes)
        msgs = R.messages(lignes, _bankroll(env), maintenant) if lignes else [{
            "title": f"Encore jouables · {maintenant.astimezone(R.PARIS):%d/%m %Hh}",
            "message": f"Aucune alerte encore jouable ({len(cands)} alerte(s) revue(s) depuis le dernier récapitulatif)."}]
        jeton, cle = env.get("PUSHOVER_APP_TOKEN", "").strip(), env.get("PUSHOVER_USER_KEY", "").strip()
        envoyes_n = 0
        for m in msgs[:5]:
            donnees_req = urlencode({"token": jeton, "user": cle, **m}).encode()
            with ouvrir(Request(PUSHOVER_URL, data=donnees_req, method="POST",
                                headers={"User-Agent": "cotes-value"}), timeout=WEBHOOK_TIMEOUT_S) as r:
                if json.load(r).get("status") == 1:
                    envoyes_n += 1
        ecrire_json(chemin, {"jour": maintenant.astimezone(R.PARIS).date().isoformat(),
                             "le": maintenant.isoformat(timespec="seconds")})
        return {"actif": True, "envoye": True, "revues": len(cands), "jouables": len(lignes), "messages": envoyes_n}
    except Exception as e:  # noqa: BLE001 - le récapitulatif ne doit jamais bloquer les alertes
        return {"actif": True, "envoye": False, "erreur": type(e).__name__}


def envoyer_et_journaliser(donnees: Path, destination: Path) -> dict:
    from cotes.depot.json_io import ecrire_json
    retenues: list = []
    try:
        paris = lire_paris(donnees)                 # une seule lecture pour les trois usages
    except (OSError, ValueError):
        paris = None                                # chacun relit et gère l'erreur comme avant
    flux = preparer(donnees, retenues=retenues, paris_bruts=paris)
    ecrire_json(destination, flux)
    push = pushover(donnees, flux, paris=paris)     # d'abord : c'est le canal le plus rapide
    webhook = webhook_pinnacle2(donnees, flux, paris=paris)
    debut = datetime.now(timezone.utc)
    if os.environ.get("SERVEUR_DIRECT") == "oui":
        # Serveur en direct : le service n'accepte l'envoi Chrome que de GitHub Actions. Pushover part, rien n'échoue.
        bilan = {"ok": True, "chrome": "non transmises ici (serveur en direct)"}
    else:
        bilan = transmettre(flux)
    fin = datetime.now(timezone.utc)
    # Données publiques de diagnostic uniquement, jamais d'abonnement ni de jeton.
    journal = {"prepare_le": flux["generated_at"], "envoi_demande_le": debut.isoformat(),
               "envoi_termine_le": fin.isoformat(), "resultat": bilan, "webhook": webhook, "pushover": push,
               "retenues": retenues[:20],         # alertes écartées : cote française trop ancienne
               "alertes": [{k:a.get(k) for k in ("id","match","pari","bookmaker","cote","collecte_le","age_prix_secondes","detecte")}
                            for a in flux["alertes"]]}
    ancien = donnees / "notifications_diagnostic.json"
    historique = json.loads(ancien.read_text()) if ancien.exists() else {"cycles": []}
    ecrire_json(ancien, {"cycles": (historique.get("cycles", [])+[journal])[-100:]})
    return bilan


def signaler_echec(donnees: Path | None, erreur) -> None:
    """L'étape reste non bloquante (continue-on-error), mais l'échec se voit : annotation ``::warning::`` et
    ``etat.json`` › ``echecs_recents`` (page Santé). Message court, jamais de jeton (cotes/echecs.py)."""
    from cotes import echecs
    if donnees is not None:
        echecs.enregistrer(donnees, "alertes_chrome", erreur)
    else:
        echecs.annoter("alertes_chrome", echecs.message_court(erreur))


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


def main(argv: list[str] | None = None) -> int:
    """`python -m cotes alertes` et scripts/envoyer_notifications.py."""
    p = argparse.ArgumentParser(prog="alertes")
    p.add_argument("--flux", type=Path, default=Path("site/notifications.json"))
    p.add_argument("--donnees", type=Path, help="Préparer les alertes immédiatement depuis les données sauvegardées")
    p.add_argument("--strategies", action="store_true",
                   help="Lister les clés à cocher dans la variable PUSHOVER_STRATEGIES, puis quitter")
    args = p.parse_args(argv)
    if args.strategies:
        for cle, nom in sorted(NOMS.items(), key=lambda x: x[1]):
            print(f"{cle}\t{nom}")
        return 0
    try:
        bilan = envoyer_et_journaliser(args.donnees,args.flux) if args.donnees else transmettre(json.loads(args.flux.read_text(encoding="utf-8")))
    except Exception as e:  # noqa: BLE001 - noté et annoncé, puis code 1 comme avant (étape non bloquante)
        signaler_echec(args.donnees, e)
        raise
    print(json.dumps(bilan, ensure_ascii=False))
    if not bilan.get("ok"):
        signaler_echec(args.donnees, bilan.get("erreur") or "Envoi des alertes Chrome en échec")
    return 0 if bilan.get("ok") else 1
