"""Transmet le flux public à l'expéditeur, authentifié par l'identité GitHub Actions.

Aucune clé Web Push ou donnée d'abonnement n'est nécessaire dans GitHub.
Une panne de notification ne doit pas interrompre la collecte ni le règlement.
"""
from __future__ import annotations

import argparse
import base64
import json
import math
import os
import sys
import time
from pathlib import Path
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from zoneinfo import ZoneInfo
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cotes.notifications import API, NOMS, PIN2  # noqa: E402

WEBHOOK_TIMEOUT_S = 5            # par requête
WEBHOOK_BUDGET_S = 25            # pour tout le passage : ne jamais retarder le scan ni les alertes Chrome
WEBHOOK_MAX = 20
ENVOYES = "webhook_envoyes.json"
PUSHOVER_URL = "https://api.pushover.net/1/messages.json"
PUSHOVER_ENVOYES = "pushover_envoyes.json"
PUSHOVER_BUDGET_S = 20           # pour tout le passage
PUSHOVER_TTL_MAX_S = 86400       # le message reste sur le téléphone jusqu'au coup d'envoi, 24 h au plus (1 h le faisait disparaître avant lecture)
CHAMPS_WEBHOOK = ("id", "match", "ligue", "debut", "marche", "selection", "bookmaker", "cote", "cote_min",
                  "cote_juste", "cote_pinnacle", "ecart", "recheck")


def lire_paris(donnees: Path) -> list[dict]:
    """``paris.json`` tel qu'écrit par le cycle. Lu une seule fois par passage (8 Mo) : la sélection, Pushover et
    le webhook ne font que lire ces objets, aucun ne les modifie."""
    return json.loads((donnees / "paris.json").read_text())


def preparer(donnees: Path, maintenant: datetime | None = None, retenues: list | None = None,
             paris_bruts: list[dict] | None = None) -> dict:
    """Même sélection que le site, sans attendre sa génération ni les résultats."""
    from cotes import stockage
    from cotes.convergence import selections
    from cotes.strategies_prudentes import selections_prudentes
    from cotes.notifications import flux, selections_labo
    paris = stockage.fusionner_paris(lire_paris(donnees) if paris_bruts is None else paris_bruts,
                                     stockage.lire_archives(donnees))
    actuelles = json.loads((donnees / "opportunites_actuelles.json").read_text())
    retenus = selections(paris)
    retenus.update(selections_prudentes(paris, bases=retenus))
    retenus.update(selections_labo(paris))
    return flux(actuelles, paris, retenus, maintenant, retenues=retenues)


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


def est_ntfy(url: str) -> bool:
    """ntfy.sh (ou un sous-domaine) : le corps est du texte, pas du JSON."""
    h = (urlparse(url).hostname or "").lower()
    return h == "ntfy.sh" or h.endswith(".ntfy.sh")


def _fr(x, decimales: int) -> str:
    return f"{x:.{decimales}f}".replace(".", ",") if isinstance(x, (int, float)) and not isinstance(x, bool) else "—"


def _min_affichee(x) -> str:
    """Cote minimale arrondie au centième supérieur : le bookmaker affiche 2 décimales, jamais sous le seuil."""
    if not isinstance(x, (int, float)) or isinstance(x, bool):
        return "—"
    return _fr(math.ceil(round(x * 100, 6)) / 100, 2)


SPORTS = {"football": "Football", "basket": "Basket", "hockey": "Hockey", "tennis": "Tennis",
          "handball": "Handball", "volley": "Volley", "rugby": "Rugby", "rugby_league": "Rugby à XIII",
          "baseball": "Baseball", "tennis_de_table": "Tennis de table", "football_americain": "Football américain",
          "football_australien": "Football australien", "mma": "MMA", "boxe": "Boxe", "snooker": "Snooker",
          "badminton": "Badminton", "golf": "Golf", "cyclisme": "Cyclisme"}
JOURS = ("lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim.")


def _sport(s) -> str:
    s = str(s or "").strip()
    return SPORTS.get(s.lower(), s.replace("_", " ").capitalize() or "—")


def message_ntfy(a: dict) -> tuple[str, str]:
    """(titre, corps) en texte brut ; l'heure du match est celle de Paris (« mar. 20/10 20h00 »)."""
    try:
        d = datetime.fromisoformat(str(a.get("debut")).replace("Z", "+00:00")).astimezone(ZoneInfo("Europe/Paris"))
        heure = f'{JOURS[d.weekday()]} {d:%d/%m} {d:%H}h{d:%M}'
    except ValueError:
        heure = "heure inconnue"
    dom, ext = a.get("domicile"), a.get("exterieur")
    match = f"{dom} – {ext}" if dom and ext else str(a.get("match") or "")
    pari = str(a.get("selection") or a.get("pari") or "").split("\n")[0]
    lignes = [match, f'{pari} @ {_fr(a.get("cote"), 2)} (min {_min_affichee(a.get("cote_min"))})', heure]
    age = a.get("age_prix_secondes")
    if isinstance(age, (int, float)) and age > 300:          # match lointain, lu à son rythme : on le dit
        lignes.append(f"Prix relevé il y a {round(age / 60)} min")
    kelly = a.get("mise_kelly")
    if isinstance(kelly, (int, float)) and not isinstance(kelly, bool) and kelly > 0:
        lignes.append(f"Mise Kelly ¼ : {_fr(kelly, 2)} €")
    return f'{a.get("bookmaker") or "—"} – {_sport(a.get("sport"))}', "\n".join(lignes)


def _entete_utf8(texte: str) -> str:
    """En-tête HTTP non latin-1 (tiret demi-cadratin) : encodage RFC 2047, lu par ntfy."""
    return "=?UTF-8?B?" + base64.b64encode(texte.encode()).decode() + "?="


def alertes_webhook(flux: dict, paris: list[dict], envoyes: dict, maintenant: datetime | None = None) -> list[dict]:
    """Alertes Pinnacle 2 pas encore envoyées, quel que soit le bookmaker : celles du scan, puis les paris
    re-décidés (même s'ils datent)."""
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


def strategies_pushover(env=None) -> tuple[set[str], list[str]]:
    """(stratégies cochées, clés inconnues) d'après ``PUSHOVER_STRATEGIES`` : clés séparées par des virgules ou
    des espaces. Liste vide : aucune alerte Pushover. Les clés s'obtiennent avec ``--strategies``."""
    env = os.environ if env is None else env
    voulues = [x for x in env.get("PUSHOVER_STRATEGIES", "").replace(",", " ").split() if x]
    return {x for x in voulues if x in NOMS}, sorted({x for x in voulues if x not in NOMS})


def strategies_du_site(env=None, ouvrir=urlopen) -> list[str] | None:
    """Stratégies cochées sur le site (appareils actifs), lues auprès du service de notifications avec l'identité GitHub
    Actions. ``None`` si le service est injoignable ou n'a pas encore l'action (fonction non redéployée)."""
    env = os.environ if env is None else env
    url, credential = env.get("ACTIONS_ID_TOKEN_REQUEST_URL", ""), env.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN", "")
    if not url.startswith("https://") or not credential:
        return None
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
    return {c for c in cles if c in NOMS}, [], "site"


def alertes_pushover(flux: dict, paris: list[dict], envoyes: dict, choisies: set[str],
                     maintenant: datetime | None = None, amorcage: bool = False) -> list[dict]:
    """Alertes des stratégies cochées pas encore envoyées, les plus récentes d'abord. ``amorcage`` (premier passage,
    aucun fichier d'envois) : les re-décisions anciennes sont seulement mémorisées, pour ne pas inonder le téléphone."""
    from cotes.notifications import alertes_recheck
    vues, out = set(envoyes), []
    rechecks = alertes_recheck(paris, PIN2, maintenant) if PIN2 in choisies else []
    for a in [x for x in flux.get("alertes", []) if set(x.get("strategies", [])) & choisies] + rechecks:
        if a["id"] in vues:
            continue
        vues.add(a["id"])
        if amorcage and a.get("recheck"):
            envoyes[a["id"]] = ""             # mémorisé sans envoi
            continue
        cles, noms = a.get("strategies") or [], a.get("labels") or []
        if len(cles) == len(noms):          # seules les stratégies cochées sont nommées (une mise chacune)
            a = {**a, "labels": [n for k, n in zip(cles, noms) if k in choisies]}
        out.append(a)
    return out


def message_pushover(a: dict, env=None, maintenant: datetime | None = None) -> dict:
    """Champs de l'API Pushover : le pari en texte, le lien du match dessous (cliquable)."""
    env = os.environ if env is None else env
    maintenant = maintenant or datetime.now(timezone.utc)
    titre, corps = message_ntfy(a)
    noms = [str(x) for x in (a.get("labels") or [])]
    ligne = f"\n{len(noms)} stratégie{'s' if len(noms) > 1 else ''} : {', '.join(noms)}" if noms else ""
    champs = {"title": titre[:250], "message": (corps[:1000 - len(ligne)] + ligne)[:1000]}
    lien = a.get("lien")
    if isinstance(lien, str) and lien.startswith("https://") and len(lien) <= 500:
        champs["url"] = lien
        chez = a.get('bookmaker') or 'le bookmaker'
        champs["url_title"] = (f"Page du sport chez {chez} (match à chercher)" if a.get("lien_repli")
                               else f"Ouvrir le match chez {chez}")[:100]
    try:
        reste = (datetime.fromisoformat(str(a.get("debut")).replace("Z", "+00:00")) - maintenant).total_seconds()
        champs["ttl"] = int(max(60, min(PUSHOVER_TTL_MAX_S, reste)))
    except ValueError:
        pass
    try:                         # 0 (défaut) respecte les heures calmes ; 1 les ignore. 2 (accusé) est refusé.
        priorite = int(env.get("PUSHOVER_PRIORITY", "0") or 0)
    except ValueError:
        priorite = 0
    champs["priority"] = priorite if priorite in (-1, 0, 1) else 0
    return champs


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
    from scripts.cycle import ecrire_json
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
        bilan = poster_pushover(a_envoyer, env) if a_envoyer else {"envoyees": [], "echecs": 0, "erreurs": []}
        for pid in bilan["envoyees"]:
            recents[pid] = maintenant.isoformat(timespec="seconds")
        if bilan["envoyees"] or amorcage or len(recents) != len(envoyes):
            ecrire_json(chemin, recents)
        return {**base, "envoyees": len(bilan["envoyees"]), "echecs": bilan["echecs"],
                "erreurs": bilan["erreurs"]}
    except Exception as e:  # noqa: BLE001 - le scan ne doit jamais dépendre de Pushover
        return {"actif": False, "envoyees": 0, "echecs": 0, "erreurs": [type(e).__name__]}


def envoyer_et_journaliser(donnees: Path, destination: Path) -> dict:
    from scripts.cycle import ecrire_json
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
    p.add_argument("--strategies", action="store_true",
                   help="Lister les clés à cocher dans la variable PUSHOVER_STRATEGIES, puis quitter")
    args = p.parse_args()
    if args.strategies:
        for cle, nom in sorted(NOMS.items(), key=lambda x: x[1]):
            print(f"{cle}\t{nom}")
        sys.exit(0)
    bilan = envoyer_et_journaliser(args.donnees,args.flux) if args.donnees else transmettre(json.loads(args.flux.read_text(encoding="utf-8")))
    print(json.dumps(bilan, ensure_ascii=False))
    sys.exit(0 if bilan.get("ok") else 1)
