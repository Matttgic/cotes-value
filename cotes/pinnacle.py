"""Collecte de toutes les cotes d'avant-match Pinnacle (API « guest » publique, sans compte).

Deux appels par sport : /sports/{id}/matchups (matchs, sous-matchs, marchés spéciaux) et
/sports/{id}/markets/straight (prix). Tout est converti en lignes au format commun :

    sport, ligue, match_id, domicile, exterieur, debut, marche, periode, ligne, issue, cote

puis chaque marché complet reçoit sa probabilité juste (marge retirée, méthode power).

Vocabulaire des marchés (commun à toutes les sources) :
- RESULTAT_1N2 (issues DOM, NUL, EXT), VAINQUEUR (DOM, EXT)
- HANDICAP (ligne = handicap de l'équipe à domicile ; issues DOM, EXT)
- TOTAL, TOTAL_DOM, TOTAL_EXT (issues PLUS, MOINS)
- préfixe d'unité quand ce ne sont pas les buts/points : CORNERS_, CARTONS_, JEUX_ (tennis),
  SETS_ (tennis, volley), POINTS_ (points d'un set au volley)
- marchés spéciaux du football (score exact, mi-temps/fin de match…) : nom normalisé de Pinnacle
- JOUEUR:<stat> (paris joueurs, issues PLUS/MOINS, colonne joueur)

Un marché sans champ ``status`` est traité comme ouvert (les spéciaux n'en ont pas).
Seul un ``status`` présent et différent de ``open`` est ignoré. Le délai depuis le
réchauffeur ne compte comme âge que s'il a renouvelé le cache (``fresh``). Sinon l'âge
est l'en-tête HTTP ``Age`` de la lecture, ou à défaut ``age_s`` vu à Paris. Au-delà de
``PINNACLE_AGE_MAX_MIN`` minutes (10 par défaut), ou si aucune de ces mesures n'existe,
``cote_perimee`` est vrai et la cote ne sert pas de référence. La clé guest est lue sur
https://www.pinnacle.com/config/app.json (``api.haywire.apiKey``), puis
``PINNACLE_API_KEY``, puis la valeur historique. Elle n'est jamais journalisée.
``PINNACLE_RECHAUFFEUR_URL`` et ``PINNACLE_RECHAUFFEUR_SECRET`` appellent la fonction
Supabase qui remplit le cache Cloudflare depuis Paris. ``PINNACLE_PROXY_URL`` peut
remplacer l'hôte de l'API guest.
"""
from __future__ import annotations

import re
import logging
import os
import time
from math import isfinite
from datetime import datetime, timezone

import requests

from .marge import marge, proba_justes

BASE = "https://guest.api.arcadia.pinnacle.com/0.1"
URL_CONFIG = "https://www.pinnacle.com/config/app.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (cotes-value)", "Accept": "application/json",
           "Referer": "https://www.pinnacle.com/"}
CLE_GUEST_PAR_DEFAUT = "CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R"
ERREURS: list[str] = []
logger = logging.getLogger(__name__)
_bloque = False
_cle_cache: str | None = None
_cle_resolue = False
origine_cle = "guest_historique"
_ages: dict[str, int | None] = {}
_statuts: dict[str, str] = {}
etat_rechauffeur = "absent"      # absent | ok | indisponible | url_refusee
sonde_cache: dict | None = None  # mesure : GitHub profite-t-il du cache rempli depuis Paris ?
SPORT_SONDE = 29
ORTHO_SONDE = ("", "?primaryOnly=false", "?withSpecials=true", "?withSpecials=true&primaryOnly=false")
_plans: dict[int, dict] = {}


def oublier_cle() -> None:
    """Oublie la clé du cycle précédent (à appeler au début de chaque collecte)."""
    global _cle_cache, _cle_resolue, origine_cle
    _cle_cache, _cle_resolue, origine_cle = None, False, "guest_historique"


def _cle_depuis_config(payload) -> str | None:
    if not isinstance(payload, dict):
        return None
    api = payload.get("api")
    haywire = api.get("haywire") if isinstance(api, dict) else None
    cle = haywire.get("apiKey") if isinstance(haywire, dict) else None
    if isinstance(cle, str) and cle.strip():
        return cle.strip()
    return None


def _lire_cle_site() -> str | None:
    """Clé publique du site. Le corps de la réponse n'est jamais journalisé."""
    try:
        r = requests.get(URL_CONFIG, headers={"User-Agent": HEADERS["User-Agent"],
                                              "Accept": "application/json"}, timeout=5)
        if getattr(r, "status_code", None) != 200:
            return None
        return _cle_depuis_config(r.json())
    except (requests.RequestException, ValueError, TypeError, AttributeError):
        return None


def _cle_dynamique() -> str | None:
    return _lire_cle_site()


def cle_du_cycle() -> str:
    """Site, puis variable d'environnement, puis valeur historique. Mise en cache pour le cycle."""
    global _cle_cache, _cle_resolue, origine_cle
    if _cle_resolue and _cle_cache:
        return _cle_cache
    site = _cle_dynamique()
    if site:
        _cle_cache, _cle_resolue, origine_cle = site, True, "site"
        return site
    env = os.environ.get("PINNACLE_API_KEY", "").strip()
    if env:
        _cle_cache, _cle_resolue, origine_cle = env, True, "environnement"
        return env
    _cle_cache, _cle_resolue, origine_cle = CLE_GUEST_PAR_DEFAUT, True, "guest_historique"
    return CLE_GUEST_PAR_DEFAUT


def headers() -> dict:
    """Surcharge à l'exécution, y compris pour les sondes ; aucun secret dans les diagnostics."""
    return {**HEADERS, "X-API-Key": cle_du_cycle()}


def age_max_secondes() -> int:
    """Seuil de fraîcheur du cache Pinnacle. Défaut : 10 minutes. Valeur illisible : le défaut."""
    brut = os.environ.get("PINNACLE_AGE_MAX_MIN", "10").strip() or "10"
    try:
        minutes = int(brut)
    except ValueError:
        minutes = 10
    if minutes < 0:
        minutes = 10
    return minutes * 60


def _erreur(message: str) -> None:
    if message not in ERREURS and len(ERREURS) < 30:
        ERREURS.append(message)
        logger.warning("Pinnacle : %s", message)

# identifiant Pinnacle -> nom commun. L'ordre du dictionnaire est l'ordre des requêtes.
# Vérifié sur GET /sports le 18/10/2026. Retirés (hors ANJ) : esport 12, cricket 8, fléchettes 10.
# 13 est le hockey sur gazon ; le snooker est 28.
SPORTS = {
    29: "football", 33: "tennis", 4: "basket", 19: "hockey",
    18: "handball", 34: "volley", 27: "rugby", 15: "football_americain",
    3: "baseball", 22: "mma", 6: "boxe", 32: "tennis_de_table", 28: "snooker",
    26: "rugby_league", 17: "golf", 9: "curling", 45: "cyclisme",
    5: "beach_volley", 1: "badminton", 37: "padel", 39: "football_australien",
    13: "hockey_sur_gazon",
}

# période Pinnacle -> période commune, par sport (le reste est ignoré)
PERIODES = {
    "football": {0: "MATCH", 1: "MT1"},
    "basket": {0: "MATCH", 1: "MT1", 2: "MT2", 3: "QT1", 4: "QT2", 5: "QT3", 6: "QT4"},
    "hockey": {0: "MATCH", 6: "TEMPS_REG", 1: "P1", 2: "P2", 3: "P3"},
    "football_americain": {0: "MATCH", 1: "MT1", 2: "MT2", 3: "QT1", 4: "QT2", 5: "QT3", 6: "QT4"},
    "baseball": {0: "MATCH", 1: "5_MANCHES"},
    "tennis": {0: "MATCH", 1: "SET1", 2: "SET2"},
    "volley": {0: "MATCH", 1: "SET1", 2: "SET2", 3: "SET3"},
    "handball": {0: "MATCH", 1: "MT1"},
    "rugby": {0: "MATCH", 1: "MT1"},
    "rugby_league": {0: "MATCH", 1: "MT1"},
    "hockey_sur_gazon": {0: "MATCH", 1: "MT1"},
}
UNITES = {"Corners": "CORNERS_", "Bookings": "CARTONS_", "Games": "JEUX_", "Points": "POINTS_"}


def base_api() -> str:
    """Hôte des lectures. PINNACLE_PROXY_URL, s'il est défini, remplace l'API guest."""
    brut = os.environ.get("PINNACLE_PROXY_URL", "").strip().rstrip("/")
    if brut.startswith("https://") or brut.startswith("http://"):
        return brut
    return BASE


def _chemin_matchups(sid: int) -> str:
    # URL fixes : le 18/10/2026, les chemins proposés par le réchauffeur (cache-buster « &_= »,
    # orthographes tournantes) faisaient répondre Pinnacle en 204/403 et la collecte tombait à 0.
    return f"/sports/{sid}/matchups?withSpecials=true"


def _chemin_marches(sid: int) -> str:
    return f"/sports/{sid}/markets/straight?primaryOnly=false&withSpecials=true"


def sonder_cache() -> dict | None:
    """Relit depuis GitHub l'URL alternative que le réchauffeur vient de lire à Paris.

    Mesure seulement (statut, cache, âge, taille) : les données lues ne servent pas à la collecte.
    """
    plan = _plans.get(SPORT_SONDE) or {}
    sonde = plan.get("sonde")
    if _bloque or not isinstance(sonde, dict):
        return None
    chemin = sonde.get("path")
    permis = {f"/sports/{SPORT_SONDE}/markets/straight{q}" for q in ORTHO_SONDE}
    if chemin not in permis:
        return None
    paris = {k: sonde.get(k) for k in ("status", "cache", "age", "octets", "t")}
    debut = datetime.now(timezone.utc)
    try:
        r = requests.get(base_api() + chemin, headers=headers(), timeout=60)
        github = {"status": r.status_code, "cache": _lire_statut_cache(r), "age": _lire_age(r),
                  "octets": len(getattr(r, "content", b"") or b"")}
    except requests.RequestException:
        github = {"status": 0, "cache": "", "age": None, "octets": 0}
    lu_paris = _instant(sonde.get("t"))
    ecart = int((debut - lu_paris).total_seconds()) if lu_paris else None
    return {"chemin": chemin, "ecart_s": ecart, "paris": paris, "github": github}


def resume_rechauffeur() -> dict:
    """Statuts HTTP vus par le réchauffeur (ex. {"matchups_403": 1}) et le premier extrait de refus."""
    statuts: dict[str, int] = {}
    extrait = None
    for plan in _plans.values():
        for genre, code in (plan.get("statuts") or {}).items():
            if code is None or isinstance(code, bool) or not isinstance(code, int):
                continue
            cle = f"{genre}_{code}"
            statuts[cle] = statuts.get(cle, 0) + 1
        if extrait is None and isinstance(plan.get("extrait"), str):
            extrait = plan["extrait"][:160]
    sautes = sum(1 for plan in _plans.values() if plan.get("cache") == "SAUTE")
    return {"statuts": statuts, "sautes": sautes, "extrait": extrait}


def _demander_rechauffe(sports: dict) -> None:
    """Demande à Paris de remplir le cache Cloudflare. Un échec laisse les URL habituelles."""
    global _plans, etat_rechauffeur
    _plans = {}
    etat_rechauffeur = "absent"
    url = os.environ.get("PINNACLE_RECHAUFFEUR_URL", "").strip()
    secret = os.environ.get("PINNACLE_RECHAUFFEUR_SECRET", "").strip()
    if not url or not secret:
        return
    if not url.lower().startswith("https://"):
        logger.warning("Pinnacle : URL du réchauffeur refusée (https obligatoire)")
        etat_rechauffeur = "url_refusee"
        return
    try:
        r = requests.post(url, json={"sports": [int(s) for s in sports], "key": cle_du_cycle()},
                          headers={"x-region": "eu-west-3", "x-secret": secret,
                                   "Content-Type": "application/json"}, timeout=120)
        if getattr(r, "status_code", None) != 200:
            logger.warning("Pinnacle : réchauffeur indisponible")
            etat_rechauffeur = "indisponible"
            return
        payload = r.json()
    except (requests.RequestException, ValueError, TypeError, AttributeError):
        logger.warning("Pinnacle : réchauffeur indisponible")
        etat_rechauffeur = "indisponible"
        return
    if not isinstance(payload, dict):
        logger.warning("Pinnacle : réchauffeur indisponible")
        etat_rechauffeur = "indisponible"
        return
    plans: dict[int, dict] = {}
    for cle, plan in payload.items():
        try:
            sid = int(cle)
        except (TypeError, ValueError):
            continue
        if isinstance(plan, dict):
            plans[sid] = plan
    _plans = plans
    etat_rechauffeur = "ok"


def _get(path: str, essais: int = 3):
    global _bloque
    if _bloque:
        return None
    m = re.match(r"^/sports/(\d+)/(matchups|markets/straight)(?:\?|$)", path)
    contexte = f"sport {m[1]} {m[2]}" if m else "requête"
    for i in range(essais):
        try:
            r = requests.get(base_api() + path, headers=headers(), timeout=90)
            if r.status_code == 200:
                try:
                    d = r.json()
                except ValueError:
                    _erreur(f"{contexte} : JSON invalide")
                    return None
                if isinstance(d, list):
                    _ages[path] = _lire_age(r)
                    _statuts[path] = _lire_statut_cache(r)
                    return d
                _erreur(f"{contexte} : liste JSON attendue")
                return None
            _erreur(f"{contexte} : HTTP {r.status_code}")
            if r.status_code == 403:
                return None                   # ce sport seulement ; les autres sports du cycle continuent
            if r.status_code in (401, 429):
                _bloque = True                # clé refusée ou quota : pas de rafale sur le reste du cycle
                return None
            if r.status_code != 408 and not 500 <= r.status_code <= 599:
                return None
        except requests.RequestException:
            _erreur(f"{contexte} : réseau indisponible")
        if i + 1 < essais:
            time.sleep(2 * (i + 1))
    return None


def _instant(valeur) -> datetime | None:
    if not isinstance(valeur, str) or not valeur.strip():
        return None
    try:
        d = datetime.fromisoformat(valeur.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


def _entier_age(valeur) -> int | None:
    if isinstance(valeur, bool) or not isinstance(valeur, int) or valeur < 0:
        return None
    return valeur


def _age_ligne(path: str, sid: int, maintenant: datetime) -> tuple[int | None, bool]:
    """Âge en secondes et péremption.

    ``now - t`` seulement si le réchauffeur a renouvelé cette URL (``fresh``).
    Sinon : en-tête Age de la lecture, puis ``age_s`` annoncé. Rien de connu : périmé.
    """
    candidats: list[int] = []
    entete = _ages[path] if path in _ages else None
    statut = _statuts.get(path, "")
    if statut == "HIT" and _entier_age(entete) is None:
        return None, True                 # servi par le cache sans âge : fraîcheur non prouvée
    if statut in ("MISS", "EXPIRED", "DYNAMIC"):
        candidats.append(0)               # lu à l'origine par cette requête : frais
    if _entier_age(entete) is not None:
        candidats.append(entete)
    plan = _plans.get(sid) or {}
    if plan.get("markets") == path and plan.get("fresh") is True:
        instant = _instant(plan.get("t"))
        if instant is not None:
            candidats.append(max(0, int((maintenant - instant).total_seconds())))
    elif plan.get("markets") == path:
        annonce = _entier_age(plan.get("age_s"))
        if annonce is not None:
            candidats.append(annonce)
    if not candidats:
        return None, True
    age = max(candidats)
    return age, age > age_max_secondes()


def _lire_statut_cache(r) -> str:
    """Valeur de cf-cache-status en majuscules, ou chaîne vide si absente."""
    entetes = getattr(r, "headers", None) or {}
    try:
        brut = entetes.get("cf-cache-status")
    except AttributeError:
        return ""
    return brut.strip().upper() if isinstance(brut, str) else ""


def _lire_age(r) -> int | None:
    """Secondes de l'en-tête Age, ou None si l'en-tête manque ou n'est pas un entier positif."""
    entetes = getattr(r, "headers", None) or {}
    brut = entetes.get("Age")
    if brut is None or str(brut).strip() == "":
        return None
    try:
        n = int(str(brut).strip())
    except (TypeError, ValueError):
        return None
    return n if n >= 0 else None


def _nombre(x) -> float | None:
    if isinstance(x, bool):
        return None
    try:
        n = float(x)
        return n if isfinite(n) else None
    except (TypeError, ValueError, OverflowError):
        return None


def americaine_vers_decimale(p) -> float | None:
    p = _nombre(p)
    if p is None or p == 0:
        return None
    cote = round(1 + p / 100.0 if p > 0 else 1 + 100.0 / abs(p), 4)
    return cote if isfinite(cote) and cote > 1 else None


def _equipes(m: dict) -> tuple[str | None, str | None]:
    parts = {p.get("alignment"): p.get("name") for p in m.get("participants") or [] if isinstance(p, dict)}
    return parts.get("home"), parts.get("away")


def _norm_special(desc: str, dom: str, ext: str) -> tuple[str, str]:
    """« Lazio Goals Odd/Even 1st Half » -> (marché « DOM Goals Odd/Even », période « MT1 »)."""
    periode = "MATCH"
    if re.search(r"\b1st Half\b", desc):
        periode, desc = "MT1", re.sub(r"\s*\b1st Half\b", "", desc)
    if dom:
        desc = desc.replace(dom, "DOM")
    if ext:
        desc = desc.replace(ext, "EXT")
    return desc.strip(), periode


def collecter(sports: dict | None = None) -> list[dict]:
    """Toutes les cotes ouvertes (avant-match), une ligne par issue, avec probabilité juste."""
    global _bloque, sonde_cache
    ERREURS.clear()
    _bloque = False
    _ages.clear()
    _statuts.clear()
    sonde_cache = None
    oublier_cle()
    sports = sports or SPORTS
    _demander_rechauffe(sports)
    lignes: list[dict] = []
    for sid, sport in sports.items():
        matchups = _get(_chemin_matchups(sid)) or []
        if _bloque:
            break
        if not matchups:
            continue
        requete_debut = datetime.now(timezone.utc).isoformat(timespec="seconds")
        chemin_prix = _chemin_marches(sid)
        marches = _get(chemin_prix) or []
        maintenant_dt = datetime.now(timezone.utc)
        maintenant = maintenant_dt.isoformat(timespec="seconds")
        if not matchups or not marches:
            continue
        age, perimee = _age_ligne(chemin_prix, sid, maintenant_dt)
        par_id = {m["id"]: m for m in matchups if isinstance(m, dict)
                  and isinstance(m.get("id"), (str, int)) and not isinstance(m.get("id"), bool)}
        if len(par_id) != len(matchups):
            _erreur(f"sport {sid} : événements invalides ou dupliqués")
        periodes = PERIODES.get(sport, {0: "MATCH"})
        for mk in marches:
            if not isinstance(mk, dict):
                _erreur(f"sport {sid} : marché non objet")
                continue
            statut = mk.get("status")
            if statut is not None and statut != "open":
                continue
            mid = mk.get("matchupId")
            if not isinstance(mid, (str, int)) or isinstance(mid, bool):
                _erreur(f"sport {sid} : identifiant de marché invalide")
                continue
            mu = par_id.get(mid)
            if mu is None or mu.get("isLive"):
                continue
            prix = mk.get("prices")
            special = mu.get("type") == "special"
            if not isinstance(prix, list) or len(prix) < 2 or any(not isinstance(p, dict) for p in prix):
                if not special:
                    _erreur(f"sport {sid} : liste de prix invalide")
                continue
            limites = mk.get("limits")
            maximum = limites[0].get("amount") if isinstance(limites, list) and limites and isinstance(limites[0], dict) else None
            base = {"source": "pinnacle", "sport": sport, "collecte": maintenant,
                    "collecte_debut": requete_debut, "collecte_recue": maintenant,
                    "mise_max": _nombre(maximum),
                    "age_cache_s": age, "cote_perimee": perimee}
            try:
                if mu.get("type") == "matchup":
                    lignes += _lignes_match(mu, mk, prix, par_id, periodes, base)
                elif mu.get("type") == "special":
                    lignes += _lignes_special(mu, mk, prix, par_id, base)
            except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
                _erreur(f"sport {sid} : schéma de marché invalide")
    _ajouter_proba_justes(lignes)
    sonde_cache = sonder_cache()
    return lignes


def _lignes_match(mu, mk, prix, par_id, periodes, base) -> list[dict]:
    parent = par_id.get(mu.get("parentId")) if mu.get("parentId") else mu
    if parent is None:
        return []
    unite = UNITES.get(mu.get("units"), "") if mu.get("parentId") else ""
    if mu.get("parentId") and mu.get("units") not in UNITES and mu.get("units") != "Regular":
        return []                      # sous-matchs exotiques (kills…) : ignorés
    if mu.get("parentId") and mu.get("units") == "Regular":
        return []                      # doublons « Regular » (prolongations…) : ignorés
    periode = periodes.get(mk.get("period", 0))
    if periode is None:
        return []
    dom, ext = _equipes(parent)
    if not isinstance(dom, str) or not isinstance(ext, str) or not dom or not ext or dom == ext:
        return []
    typ = mk["type"]
    if base["sport"] == "tennis" and not unite and typ in ("spread", "total"):
        unite = "SETS_"                # marchés principaux du tennis : en sets
    out = []
    for p in prix:
        cote = americaine_vers_decimale(p.get("price"))
        if cote is None:
            _erreur("marché rejeté : cote américaine invalide")
            return []
        d = p.get("designation")
        if typ == "moneyline":
            nb = len(prix)
            if nb not in (2, 3):
                return []
            marche = "RESULTAT_1N2" if nb == 3 else "VAINQUEUR"
            issue = {"home": "DOM", "away": "EXT", "draw": "NUL"}.get(d)
            ligne = None
        elif typ == "spread":
            marche, issue = "HANDICAP", {"home": "DOM", "away": "EXT"}.get(d)
            pts = _nombre(p.get("points"))
            ligne = pts if d == "home" else (-pts if pts is not None else None)   # handicap du domicile
        elif typ == "total":
            marche, issue, ligne = "TOTAL", {"over": "PLUS", "under": "MOINS"}.get(d), _nombre(p.get("points"))
        elif typ == "team_total":
            cote_eq = mk.get("side")
            if cote_eq not in ("home", "away"):
                return []
            marche = "TOTAL_DOM" if cote_eq == "home" else "TOTAL_EXT"
            issue, ligne = {"over": "PLUS", "under": "MOINS"}.get(d), _nombre(p.get("points"))
        else:
            return []
        if issue is None or (typ != "moneyline" and ligne is None):
            return []
        out.append({**base, "ligue": (parent.get("league") or {}).get("name"), "match_id": parent["id"],
                    "domicile": dom, "exterieur": ext, "debut": parent.get("startTime"),
                    "marche": unite + marche, "periode": periode, "ligne": ligne, "issue": issue,
                    "joueur": None, "cote": cote,
                    "cle_marche": f"{mu['id']}|{mk.get('key')}|{mk.get('side', '')}"})
    return out


def _lignes_special(mu, mk, prix, par_id, base) -> list[dict]:
    parent = par_id.get(mu.get("parentId")) or mu.get("parent")
    if not parent:
        return []                      # paris à long terme : ignorés
    sp = mu.get("special") or {}
    dom, ext = _equipes(parent)
    if not isinstance(dom, str) or not isinstance(ext, str) or not dom or not ext or dom == ext:
        return []
    noms = {p["id"]: p["name"] for p in mu.get("participants") or []}
    cat, desc = sp.get("category", ""), sp.get("description", "")
    out = []
    if cat == "Player Props":
        m = re.match(r"^(.*?) Total (.*)$", desc)
        joueur = m.group(1) if m else desc
        stat = mu.get("units") or (m.group(2) if m else "?")
        for p in prix:
            issue = {"Over": "PLUS", "Under": "MOINS"}.get(noms.get(p.get("participantId")))
            if issue is None:
                return []
            out.append({**base, "ligue": (parent.get("league") or {}).get("name"), "match_id": parent["id"],
                        "domicile": dom, "exterieur": ext, "debut": parent.get("startTime"),
                        "marche": f"JOUEUR:{stat}", "periode": "MATCH", "ligne": p.get("points"),
                        "issue": issue, "joueur": joueur, "cote": americaine_vers_decimale(p["price"]),
                        "cle_marche": f"{mu['id']}|{mk.get('key')}"})
        return out
    if cat not in ("Team Props", "Game Props", "Exact Scores", "Double Result"):
        return []
    marche, periode = _norm_special(desc, dom, ext)
    for p in prix:
        nom = noms.get(p.get("participantId"), "?")
        issue = {dom: "DOM", ext: "EXT", "Draw": "NUL"}.get(nom, nom)
        out.append({**base, "ligue": (parent.get("league") or {}).get("name"), "match_id": parent["id"],
                    "domicile": dom, "exterieur": ext, "debut": parent.get("startTime"),
                    "marche": f"SPECIAL:{marche}", "periode": periode, "ligne": p.get("points"),
                    "issue": issue, "joueur": None, "cote": americaine_vers_decimale(p["price"]),
                    "cle_marche": f"{mu['id']}|{mk.get('key')}"})
    return out


def _ajouter_proba_justes(lignes: list[dict]) -> None:
    groupes: dict[str, list[dict]] = {}
    for l in lignes:
        groupes.setdefault(l["cle_marche"], []).append(l)
    for g in groupes.values():
        cotes = [l.get("cote") for l in g]
        valides = all(isinstance(c, (int, float)) and not isinstance(c, bool) and _nombre(c) is not None and c > 1 for c in cotes)
        issues = [l.get("issue") for l in g]
        marche = str(g[0].get("marche") or "")
        attendues = ({"DOM", "NUL", "EXT"} if marche.endswith("RESULTAT_1N2") else
                     {"DOM", "EXT"} if marche.endswith(("VAINQUEUR", "HANDICAP")) else
                     {"PLUS", "MOINS"} if "TOTAL" in marche or marche.startswith("JOUEUR:") else None)
        valides = valides and all(isinstance(i, str) and i for i in issues)
        valides = valides and len(set(issues)) == len(issues) and (attendues is None or set(issues) == attendues)
        # Les spéciaux ne sont pas encore traduits en DOM/NUL/EXT : on exige seulement
        # le nombre d'issues du marché. Un handicap européen à 2 prix n'est pas un 2-issues.
        if marche.startswith("SPECIAL:3-Way Handicap"):
            valides = valides and len(issues) == 3
        elif marche in ("SPECIAL:Draw No Bet", "SPECIAL:Both Teams To Score?"):
            valides = valides and len(issues) == 2
        valides = valides and all(all(l.get(k) == g[0].get(k) for k in
                         ("match_id", "marche", "periode", "ligne", "joueur")) for l in g)
        if not valides:
            _erreur("marché rejeté : cotes ou issues incohérentes")
        p = proba_justes(cotes) if valides else None
        m = marge(cotes) if p else None
        for l, pi in zip(g, p or [None] * len(g)):
            l["proba_juste"] = round(pi, 6) if pi else None
            l["cote_juste"] = round(1 / pi, 4) if pi else None
            l["marge_pinnacle"] = round(m, 4) if m is not None else None
