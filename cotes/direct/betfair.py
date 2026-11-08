"""Cotes Betfair Exchange, API du site lues sans compte (clé publique ``_ak`` du site, pas de session).

Trois appels, relevés le 08/11/2026 depuis une IP finlandaise (l'Allemagne, la France et les États-Unis reçoivent
« Restricted » : à lancer seulement depuis le serveur, s'il est en Finlande) :

1. ``POST scan-inbf.betfair.com/www/sports/navigation/facet/v1/search`` : matchs à venir (Match Odds), du premier
   qui commence au suivant. Pas encore vérifié (POST impossible depuis l'outil de relevé) : la sonde
   ``scripts/sonde_betfair.py`` le teste sur le serveur ;
2. ``GET ero.betfair.com/…/readonly/v1/byevent`` (``MARKET_DESCRIPTION``) : catalogue des marchés de ces matchs,
   sans prix (le filtre par type de marché est ignoré : tout revient, on trie ici). Gardé ``CATALOGUE_S`` ;
3. ``GET ero.betfair.com/…/readonly/v1/bymarket`` : meilleurs back et lay et leur montant, jusqu'à 100 marchés par
   appel (vérifié). ``isMarketDataDelayed`` vaut ``true`` sans compte : les prix peuvent avoir quelques secondes de
   retard, aucune heure de mise à jour n'est fournie (pas de ``maj_source``).

Le milieu back/lay est la cote juste (``reference_echange``), comme Matchbook et Smarkets : source « Betfair ».

``SOURCE_BETFAIR`` : ``direct``, ``shadow`` (lu, rien n'est comparé) ou ``off``. Sans valeur : ``direct`` sur le
serveur (``SERVEUR_DIRECT=oui``), ``off`` ailleurs (GitHub Actions sort par les États-Unis, refusés). Un 403 ou un 429
coupe la lecture ; un 401 ou 400 fait relire la clé dans la page de l'Exchange, une fois.
"""
from __future__ import annotations

import os
import random
import re
import time
from datetime import datetime, timedelta, timezone

from cotes.temps import instant_utc

NOM_SOURCE = "Betfair"
AK_CONNUE = "nzIFcwyWhrlwYMrh"
PAGE = "https://www.betfair.com/exchange/plus/"
RECHERCHE = "https://scan-inbf.betfair.com/www/sports/navigation/facet/v1/search"
LECTURE = "https://ero.betfair.com/www/sports/exchange/readonly/v1"
TYPES_PRIX = "MARKET_STATE,MARKET_DESCRIPTION,EVENT,RUNNER_DESCRIPTION,RUNNER_STATE,RUNNER_EXCHANGE_PRICES_BEST"
SPORTS = {1: "football", 2: "tennis"}
MODES = ("off", "shadow", "direct")
CATALOGUE_S = 600
MATCHS_MAX = 200                 # par sport, du premier qui commence au suivant
EVENEMENTS_PAR_APPEL = 10        # catalogue : ~50 marchés par match de football
MARCHES_PAR_APPEL = 100          # prix : vérifié à 100
APPELS_PRIX_MAX = 30             # par cycle ; les matchs les plus proches d'abord
ENTETES = {"Accept": "application/json, text/plain, */*", "Origin": "https://www.betfair.com", "Referer": PAGE}
_MOTIFS_AK = (re.compile(r"""["']?appKey["']?\s*[:=]\s*["']([A-Za-z0-9]{16})["']"""),
              re.compile(r"""[?&]_ak=([A-Za-z0-9]{16})"""))
_echeance = None
_catalogue: dict = {"lu": 0.0, "cle": None, "marches": []}

# type Betfair -> (marché interne, période, ligne fixe) ; les lignes des marchés asiatiques sont lues par issue
FOOTBALL = {
    "MATCH_ODDS": ("RESULTAT_1N2", "MATCH", None),
    "HALF_TIME": ("RESULTAT_1N2", "MT1", None),
    "DRAW_NO_BET": ("DRAW_NO_BET", "MATCH", None),
    # pas DOUBLE_CHANCE : reference_echange la recalcule depuis le 1N2 et jette celle du marché
    "BOTH_TEAMS_TO_SCORE": ("BOTH_TEAMS_TO_SCORE", "MATCH", None),
    "CORRECT_SCORE": ("CORRECT_SCORE", "MATCH", None),
    "HALF_TIME_FULL_TIME": ("HALF_TIME_FULL_TIME", "MATCH", None),
    "ASIAN_HANDICAP": ("HANDICAP", "MATCH", None),
    "ALT_TOTAL_GOALS": ("TOTAL", "MATCH", None),
}
_TOTAUX = (  # OVER_UNDER_25 -> 2.5 ; FIRST_HALF_GOALS_15 -> 1.5 en 1re mi-temps ; TEAM_A_OVER_UNDER_05 -> domicile
    (re.compile(r"^OVER_UNDER_(\d)5$"), "TOTAL", "MATCH"),
    (re.compile(r"^FIRST_HALF_GOALS_(\d)5$"), "TOTAL", "MT1"),
    (re.compile(r"^TEAM_A_OVER_UNDER_(\d)5$"), "TOTAL_DOM", "MATCH"),
    (re.compile(r"^TEAM_B_OVER_UNDER_(\d)5$"), "TOTAL_EXT", "MATCH"),
)
TENNIS = {"MATCH_ODDS": ("VAINQUEUR", "MATCH", None)}


def mode(environ=None) -> str:
    env = os.environ if environ is None else environ
    defaut = "direct" if env.get("SERVEUR_DIRECT", "").strip().lower() == "oui" else "off"
    valeur = env.get("SOURCE_BETFAIR", defaut).strip().lower()
    return valeur if valeur in MODES else defaut


def regle(type_marche: str, sport: str):
    """(marché interne, période, ligne) d'un type Betfair, ou None s'il n'est pas lu."""
    if sport == "tennis":
        return TENNIS.get(type_marche)
    if type_marche in FOOTBALL:
        return FOOTBALL[type_marche]
    for motif, interne, periode in _TOTAUX:
        m = motif.match(type_marche or "")
        if m:
            return interne, periode, int(m.group(1)) + 0.5
    return None


def cles_ak(texte: str) -> list[str]:
    vues: list[str] = []
    for motif in _MOTIFS_AK:
        for cle in motif.findall(texte or ""):
            if cle not in vues:
                vues.append(cle)
    return vues


def _nombre(v):
    if v is None or isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _session():
    try:
        from curl_cffi.requests import Session
        return Session(impersonate="chrome")
    except ImportError:
        import requests
        return requests.Session()


class Client:
    """Appels espacés, sans compte. 403/429 : lecture coupée. 401/400 : clé relue une fois. Corps jamais journalisé."""

    def __init__(self, session=None, pause=(0.2, 0.5), echeance=None, ak=None):
        self.session = session or _session()
        self.pause, self.echeance = pause, echeance
        self.ak = ak or os.environ.get("BETFAIR_AK", "").strip() or AK_CONNUE
        self.requetes, self.erreurs, self.bloque, self._premier, self._cle_relue = 0, [], False, True, False

    def _noter(self, m):
        if m not in self.erreurs:
            self.erreurs.append(m)

    def _relire_cle(self) -> bool:
        if self._cle_relue:
            return False
        self._cle_relue = True
        try:
            r = self.session.request("GET", PAGE, timeout=20, headers={"Accept": "text/html"})
        except Exception:  # noqa: BLE001 - réseau : la clé actuelle reste
            return False
        trouvees = [c for c in cles_ak(r.text) if c != self.ak] if r.status_code == 200 else []
        if trouvees:
            self.ak = trouvees[0]
            return True
        return False

    def appel(self, methode: str, url: str, params: dict | None = None, json_corps=None):
        if self.bloque:
            return None
        dernier = "réseau"
        for essai in range(3):
            if self.echeance is not None and not self.echeance.ok():
                self.bloque = True
                self._noter("budget")
                return None
            if not self._premier:
                time.sleep(random.uniform(*self.pause))
            self._premier = False
            self.requetes += 1
            try:
                r = self.session.request(methode, url, params={"_ak": self.ak, "alt": "json", **(params or {})},
                                         json=json_corps, timeout=30, headers=ENTETES)
            except Exception:  # noqa: BLE001 - curl_cffi et requests n'ont pas les mêmes exceptions
                dernier = "réseau"
                time.sleep(0.5 * (essai + 1))
                continue
            if r.status_code in (403, 429):
                self.bloque = True                       # 403 : pays refusé ou Cloudflare ; 429 : quota
                self._noter(f"HTTP {r.status_code}")
                return None
            if r.status_code in (400, 401) and self._relire_cle():
                continue
            if r.status_code in (500, 502, 503, 504):
                dernier = f"HTTP {r.status_code}"
                time.sleep(0.5 * (essai + 1))
                continue
            if r.status_code != 200:
                self._noter(f"HTTP {r.status_code}")
                return None
            try:
                doc = r.json()
            except ValueError:
                self._noter("JSON invalide")
                return None
            return doc if isinstance(doc, dict) else None
        self._noter(dernier)
        return None


def corps_recherche(sport_id: int, nombre: int = MATCHS_MAX) -> dict:
    """Même requête que la page de l'Exchange : matchs avec un marché Match Odds, du premier qui commence au suivant."""
    return {
        "filter": {"marketBettingTypes": ["ODDS"], "productTypes": ["EXCHANGE"], "marketTypeCodes": ["MATCH_ODDS"],
                   "selectBy": "FIRST_TO_START", "contentGroup": {"language": "en", "regionCode": "UK"},
                   "turnInPlayEnabled": True, "maxResults": 0, "eventTypeIds": [sport_id]},
        "facets": [{"type": "EVENT", "skipValues": 0, "maxValues": nombre,
                    "next": {"type": "MARKET", "skipValues": 0, "maxValues": 1}}],
        "currencyCode": "EUR", "locale": "en_GB",
    }


_ID_EVENEMENT = re.compile(r"""['"]eventId['"]\s*:\s*['"]?(\d{6,10})""")


def evenements_trouves(doc) -> list[str]:
    """Identifiants des matchs d'une réponse de recherche, dans l'ordre : ``attachments.events``, sinon tout
    ``eventId`` du document (la forme exacte de la réponse n'a pas encore été vue)."""
    att = doc.get("attachments") if isinstance(doc, dict) else None
    evs = att.get("events") if isinstance(att, dict) else None
    if isinstance(evs, dict) and evs:
        return [str(v.get("eventId") or k) if isinstance(v, dict) else str(k) for k, v in evs.items()]
    return list(dict.fromkeys(_ID_EVENEMENT.findall(str(doc)))) if doc else []


def marches_du_catalogue(doc, sport: str, maintenant: datetime, heures: float) -> list[dict]:
    """Réponse ``byevent`` -> marchés lus (id, début), matchs pas encore commencés dans l'horizon."""
    horizon = maintenant + timedelta(hours=heures)
    out = []
    for et in (doc or {}).get("eventTypes") or []:
        for noeud in et.get("eventNodes") or []:
            for m in noeud.get("marketNodes") or []:
                d = m.get("description") or {}
                debut = instant_utc(d.get("marketTime"))
                if regle(d.get("marketType"), sport) and debut and maintenant < debut <= horizon:
                    out.append({"id": str(m.get("marketId")), "debut": debut, "sport": sport})
    return out


def _equipes(nom: str):
    a, sep, b = str(nom or "").partition(" v ")
    return (a.strip() or None, b.strip() or None) if sep else (None, None)


def _meme(a, b) -> bool:
    return (a or "").strip().lower() == (b or "").strip().lower()


def _cote(nom: str, dom: str, ext: str):
    n = (nom or "").strip()
    if n.lower() in ("draw", "the draw"):
        return "NUL"
    return "DOM" if _meme(n, dom) else "EXT" if _meme(n, ext) else None


def _issue(interne: str, nom: str, dom: str, ext: str):
    n = (nom or "").strip()
    bas = n.lower()
    if interne in ("RESULTAT_1N2", "VAINQUEUR", "DRAW_NO_BET", "HANDICAP"):
        issue = _cote(n, dom, ext)
        return issue if issue != "NUL" or interne == "RESULTAT_1N2" else None
    if interne == "BOTH_TEAMS_TO_SCORE":
        return {"yes": "YES", "no": "NO"}.get(bas)
    if interne == "CORRECT_SCORE":
        m = re.fullmatch(r"(\d+)\s*-\s*(\d+)", n)        # « Any Other Home Win » n'est pas lu
        return f"{m.group(1)}-{m.group(2)}" if m else None
    if interne == "HALF_TIME_FULL_TIME":
        a, _, b = n.partition("/")
        x, y = _cote(a, dom, ext), _cote(b, dom, ext)
        return f"{x}/{y}" if x and y else None
    if interne.startswith("TOTAL"):
        return "PLUS" if bas.startswith("over") else "MOINS" if bas.startswith("under") else None
    return None


def _carnet(runner: dict):
    ex = runner.get("exchange") or {}
    backs, lays = ex.get("availableToBack") or [], ex.get("availableToLay") or []
    if not backs or not lays or not isinstance(backs[0], dict) or not isinstance(lays[0], dict):
        return None
    b, v = _nombre(backs[0].get("price")), _nombre(lays[0].get("price"))
    if b is None or v is None or not 1 < b <= v:
        return None
    return ({"price": round(b, 4), "liquidity": round(_nombre(backs[0].get("size")) or 0, 2)},
            {"price": round(v, 4), "liquidity": round(_nombre(lays[0].get("size")) or 0, 2)})


def lignes_brutes(doc, sport: str, maintenant: datetime, heures: float = 36, ligues: dict | None = None) -> list[dict]:
    """Réponse ``bymarket`` -> lignes achat/vente au format du dépôt (avant cote juste). Marchés ouverts, pas en
    direct ; issues actives. Les marchés asiatiques donnent une ligne par handicap (celui du domicile)."""
    moment = maintenant.isoformat(timespec="seconds")
    horizon = maintenant + timedelta(hours=heures)
    out = []
    for et in (doc or {}).get("eventTypes") or []:
        for noeud in et.get("eventNodes") or []:
            ev = noeud.get("event") or {}
            dom, ext = _equipes(ev.get("eventName"))
            if not dom or not ext:
                continue
            for m in noeud.get("marketNodes") or []:
                etat, d = m.get("state") or {}, m.get("description") or {}
                r = regle(d.get("marketType"), sport)
                debut = instant_utc(d.get("marketTime") or ev.get("openDate"))
                if not r or etat.get("status") != "OPEN" or etat.get("inplay") or not debut \
                        or not (maintenant < debut <= horizon):
                    continue
                interne, periode, ligne_fixe = r
                base = {"source": NOM_SOURCE, "bookmaker": "betfair", "sport": sport,
                        "ligue": (ligues or {}).get(str(noeud.get("eventId"))),
                        "match_id": f"betfair|{noeud.get('eventId')}", "domicile": dom, "exterieur": ext,
                        "debut": debut.isoformat(), "collecte": moment, "joueur": None,
                        "cle_marche": f"betfair|{m.get('marketId')}", "marche": interne, "periode": periode,
                        "libelle": d.get("marketName")}
                asiatique = d.get("bettingType") == "ASIAN_HANDICAP_DOUBLE_LINE"
                for runner in m.get("runners") or []:
                    if (runner.get("state") or {}).get("status", "ACTIVE") != "ACTIVE":
                        continue
                    issue = _issue(interne, (runner.get("description") or {}).get("runnerName"), dom, ext)
                    if not issue:
                        continue
                    ligne = ligne_fixe
                    if asiatique:
                        h = _nombre(runner.get("handicap"))
                        if h is None:
                            continue
                        if interne == "HANDICAP":
                            ligne = h if issue == "DOM" else -h
                        elif h % 1 == 0.5:     # 2.5, 3.5… : déjà lus dans OVER_UNDER_xx, pas de doublon
                            continue
                        else:
                            ligne = h
                    carnet = _carnet(runner)
                    out.append({**base, "ligne": ligne, "issue": issue,
                                "achat": [carnet[0]] if carnet else [], "vente": [carnet[1]] if carnet else []})
    return out


def _ligues(doc) -> dict:
    """eventId -> compétition, si la réponse de recherche les joint."""
    att = doc.get("attachments") if isinstance(doc, dict) else None
    if not isinstance(att, dict):
        return {}
    comp = att.get("competitions") or {}
    out = {}
    for k, ev in (att.get("events") or {}).items():
        if isinstance(ev, dict):
            c = comp.get(str(ev.get("competitionId"))) if isinstance(comp, dict) else None
            if isinstance(c, dict) and c.get("name"):
                out[str(ev.get("eventId") or k)] = c["name"]
    return out


def _lire_catalogue(client: Client, sports: set[str] | None, maintenant: datetime, heures: float):
    marches, ligues = [], {}
    for sid, sport in SPORTS.items():
        if sports is not None and sport not in sports:
            continue
        doc = client.appel("POST", RECHERCHE, json_corps=corps_recherche(sid))
        if doc is None:
            if client.bloque:
                break
            continue
        ligues.update(_ligues(doc))
        ids = evenements_trouves(doc)
        for i in range(0, len(ids), EVENEMENTS_PAR_APPEL):
            cat = client.appel("GET", f"{LECTURE}/byevent", {"currencyCode": "EUR", "locale": "en_GB",
                                                            "types": "MARKET_DESCRIPTION",
                                                            "eventIds": ",".join(ids[i:i + EVENEMENTS_PAR_APPEL])})
            if cat is None:
                break
            marches += marches_du_catalogue(cat, sport, maintenant, heures)
    marches.sort(key=lambda m: m["debut"])
    return marches, ligues


def collecter(sports: set[str] | None = None, heures: float = 36, session=None, maintenant: datetime | None = None,
              echeance=None, environ=None, pause=(0.2, 0.5), catalogue: dict | None = None):
    """Catalogue relu toutes les ``CATALOGUE_S`` secondes, puis les prix, par paquets de 100 marchés."""
    from cotes.comparaison import reference_echange
    maintenant = maintenant or datetime.now(timezone.utc)
    actif = mode(environ)
    if actif == "off":
        return [], {"ok": True, "requetes": 0, "erreurs": [], "matchs": 0, "marches": 0, "mode": "off"}
    cache = _catalogue if catalogue is None else catalogue
    client = Client(session, pause=pause, echeance=echeance if echeance is not None else _echeance)
    cle = (tuple(sorted(sports)) if sports is not None else None, heures)
    if cache.get("cle") != cle or time.monotonic() - cache.get("lu", 0.0) >= CATALOGUE_S or not cache.get("marches"):
        marches, ligues = _lire_catalogue(client, sports, maintenant, heures)
        if marches:
            cache.update(lu=time.monotonic(), cle=cle, marches=marches, ligues=ligues)
    marches = [m for m in cache.get("marches") or [] if m["debut"] > maintenant]
    bruts = []
    for sport in dict.fromkeys(m["sport"] for m in marches):
        ids = [m["id"] for m in marches if m["sport"] == sport]
        for i in range(0, min(len(ids), APPELS_PRIX_MAX * MARCHES_PAR_APPEL), MARCHES_PAR_APPEL):
            doc = client.appel("GET", f"{LECTURE}/bymarket", {"currencyCode": "EUR", "locale": "en_GB",
                                                              "rollupLimit": 1, "rollupModel": "STAKE",
                                                              "types": TYPES_PRIX,
                                                              "marketIds": ",".join(ids[i:i + MARCHES_PAR_APPEL])})
            if doc is None:
                break
            bruts += lignes_brutes(doc, sport, maintenant, heures, cache.get("ligues"))
        if client.bloque:
            break
    justes = reference_echange(bruts, NOM_SOURCE)
    return justes, {"ok": not client.erreurs or bool(justes), "requetes": client.requetes,
                    "erreurs": list(client.erreurs), "matchs": len({l["match_id"] for l in bruts}),
                    "marches": len(marches), "mode": actif}
