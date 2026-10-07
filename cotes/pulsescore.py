"""Collecte PulseScore (bookmakers français + Betfair via Orbit Exchange) et traduction des marchés.

Listes paginées par 30 matchs, triées par heure de début : on lit les pages jusqu'à dépasser
l'horizon voulu. Limite de l'offre : 1 requête par seconde et par bookmaker en PRO (1 par minute
en STARTER), réglable par la variable PULSESCORE_PAUSE (secondes entre deux pages).

La traduction vers le vocabulaire commun (voir cotes/pinnacle.py) s'appuie sur le marché
normalisé de PulseScore (canonicalMarket) mais vérifie le libellé d'origine (rawName) : période
écrite dans le libellé, ligne de handicap notée différemment selon les sites, règles du hockey
(temps réglementaire ou prolongation incluse), marchés mal classés (breaks au tennis…).
"""
from __future__ import annotations

import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import requests

BASE = "https://api.pulsescore.net/api"
FRANCAIS = ["winamax", "betclic", "unibet-fr", "pmu"]   # NetBet retiré : flux netbet.com, pas netbet.fr
NOMS = {"winamax": "Winamax", "betclic": "Betclic", "unibet-fr": "Unibet", "pmu": "PMU", "netbet": "NetBet",
        "orbitxch": "Betfair"}
SPORTS = {"soccer": "football", "basketball": "basket", "tennis": "tennis", "ice-hockey": "hockey",
          "handball": "handball", "volleyball": "volley", "rugby-union": "rugby", "american-football":
          "football_americain", "baseball": "baseball", "mma": "mma", "table-tennis": "tennis_de_table"}


# --------------------------------------------------------------------------- collecte

class Client:
    def __init__(self, cle: str, pause: float | None = None):
        self.s = requests.Session()
        self.s.headers.update({"X-Secret": cle, "Accept-Encoding": "gzip", "Accept": "application/json"})
        self.pause = float(os.environ.get("PULSESCORE_PAUSE", "1.1")) if pause is None else pause
        self.requetes = 0
        self.erreurs: list[str] = []

    def get(self, chemin: str, params: dict | None = None):
        """Réponse JSON, ou None (page absente, erreur). Les erreurs réseau et 429 sont réessayées ;
        chaque échec est noté dans `erreurs` pour être visible dans le journal du cycle."""
        derniere = "429 répétés"
        for essai in range(4):
            try:
                r = self.s.get(f"{BASE}/{chemin}", params=params, timeout=90)
            except requests.RequestException as e:
                self.requetes += 1                 # tentative émise (sa facturation n'est pas connue)
                derniere = repr(e)[:150]
                time.sleep(2 * (essai + 1) + self.pause)
                continue
            self.requetes += 1
            if r.status_code == 429:
                time.sleep(float(r.headers.get("Retry-After") or 2 * (essai + 1)) + self.pause)
                continue
            time.sleep(self.pause)
            if r.status_code != 200:
                if r.status_code != 404:
                    self.erreurs.append(f"{chemin} : HTTP {r.status_code}")
                return None
            try:
                return r.json()
            except ValueError:
                self.erreurs.append(f"{chemin} : JSON invalide")
                return None
        self.erreurs.append(f"{chemin} : {derniere}")
        return None

    def matchs(self, bookmaker: str, sport: str, heures: float, pages_max: int = 40) -> list[dict]:
        """Matchs d'avant-match commençant dans les `heures` prochaines heures."""
        limite = datetime.now(timezone.utc) + timedelta(hours=heures)
        out = []
        for page in range(1, pages_max + 1):
            d = self.get(f"{bookmaker}/{sport}/events", {"page": page, "limit": 30})
            if not d or not d.get("events"):
                break
            maintenant = datetime.now(timezone.utc)
            for e in d["events"]:
                debut = _heure(e.get("startTime"))
                if not e.get("live") and not e.get("suspended") and debut and debut > maintenant:
                    out.append(e)
            dernier = _heure(d["events"][-1].get("startTime"))
            if not d.get("hasNextPage") or (dernier and dernier > limite):
                break
        return [e for e in out if (_heure(e["startTime"]) or limite) <= limite]


def collecter(cle: str, plan: dict[str, list[str]], heures: float = 36,
              pages_max: int = 40) -> tuple[list[dict], dict[str, int], dict[str, list[str]]]:
    """plan : bookmaker -> sports (noms PulseScore). Les bookmakers sont lus en parallèle (la limite de
    débit est par bookmaker). Renvoie (lignes, requêtes par bookmaker, erreurs par bookmaker) : une panne
    sur un bookmaker ou un sport n'efface pas ce qui a été lu ailleurs."""
    def un_bookmaker(bm: str):
        c = Client(cle)
        lignes = []
        for sp in plan[bm]:
            try:
                moment = datetime.now(timezone.utc).isoformat(timespec="seconds")
                for e in c.matchs(bm, sp, heures, pages_max):
                    lignes += traduire(e, bm, SPORTS.get(sp, sp), moment)
            except Exception as e:                                   # noqa: BLE001
                c.erreurs.append(f"{sp} : {repr(e)[:150]}")
        return bm, lignes, c.requetes, c.erreurs

    with ThreadPoolExecutor(max_workers=max(1, len(plan))) as pool:
        res = list(pool.map(un_bookmaker, list(plan)))
    return ([l for _, r, _, _ in res for l in r], {bm: n for bm, _, n, _ in res},
            {bm: err for bm, _, _, err in res if err})


# --------------------------------------------------------------------------- traduction

def _heure(s):
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None


def _nombre(s) -> float | None:
    m = re.search(r"[-+]?\d+(?:[.,]\d+)?", s or "")
    return float(m.group(0).replace(",", ".")) if m else None


def _crochet(s) -> float | None:
    """« Aruba [-4,5] » -> -4.5 ; « Home (-2.5) » -> -2.5."""
    m = re.search(r"[\[(]\s*([-+]?\d+(?:[.,]\d+)?)\s*[\])]", s or "")
    return float(m.group(1).replace(",", ".")) if m else None


ORDINAUX = {"1": 1, "2": 2, "3": 3, "4": 4}


# Statistiques que PulseScore range parfois dans les totaux ou handicaps ordinaires (« Plus / Moins Tirs
# cadrés - Italie » classé en total de buts de l'équipe) : jamais comparées.
STATISTIQUES = re.compile(
    r"\btirs?\b(?! au but)|cadr|\bshots?\b|carton|\bcards?\b|booking|faute|\bfouls?\b|hors-jeu|offside|"
    r"touches|throw|\bpasses?\b|tacle|tackle|arr[eê]ts|\bsaves?\b|possession|\baces?\b|double faute|"
    r"rebond|rebound|passes? d[ée]cisive|assist|interception|steal|\bcontres?\b|\bblocks?\b|strikeout|"
    r"\bhits?\b|home runs?|penalt|buteur|scorer|marqueur|\bjoueur|player|s[ée]ries?\b(?! [ab]\b)|\bbreaks?\b|"
    r"\bwalks?\b|\bbases?\b|touchdowns?|field goals?|yards|sacks?|turnover|panier|\b3 points|three|3-pt")
MANCHES = re.compile(r"(?:first|premi[eè]res?)\s+(\d+)\s+(?:innings|manches)|(\d+)\s+(?:premi[eè]res?|first)\s+"
                     r"(?:innings|manches)|(?:innings|manches)\s+1\s*[-àa]\s*(\d+)")


def libelle_exclu(sport: str, marche_canonique: str | None, libelle: str) -> bool:
    l = (libelle or "").lower()
    if "CORNERS" in (marche_canonique or ""):
        return False
    return bool(STATISTIQUES.search(l)) or ("corner" in l)


def periode(sport: str, canonique: str | None, libelle: str) -> str | None:
    """Période commune, d'après le libellé d'abord (plus fiable), sinon la période canonique."""
    l = (libelle or "").lower()
    n = None
    if sport == "baseball":
        m = MANCHES.search(l)
        if m:                             # « First 5 Innings » -> 5_MANCHES ; 3 ou 7 manches : non comparé
            return "5_MANCHES" if next(g for g in m.groups() if g) == "5" else None
        if re.search(r"\b(inning|manche)\b", l):
            return None                   # une manche précise (« 1st Inning ») : non comparé
    m = re.search(r"\b([1-4])\s*(?:er|ère|re|e|ème|eme|de|nd|st|rd|th)?\s*(mi-temps|half|tiers-temps|période|periode|"
                  r"quart-temps|quarter|set|period)", l)
    if m:
        n, unite = ORDINAUX[m.group(1)], m.group(2)
    elif re.search(r"(première|first)\s+(mi-temps|half)", l):
        n, unite = 1, "mi-temps"
    elif re.search(r"(seconde|second|deuxième)\s+(mi-temps|half)", l):
        n, unite = 2, "mi-temps"
    elif re.match(r"^mi-temps\b", l) or "half time" in l or "halftime" in l:
        n, unite = 1, "mi-temps"
    if n:
        if unite in ("mi-temps", "half"):
            return f"MT{n}"
        if unite in ("tiers-temps", "période", "periode", "period"):
            return f"P{n}" if sport == "hockey" else None
        if unite in ("quart-temps", "quarter"):
            return f"QT{n}"
        if unite == "set":
            return f"SET{n}"
    c = canonique or "FULL_TIME"
    if c == "FULL_TIME":
        return "MATCH"
    if sport != "tennis":
        return None        # période annoncée par PulseScore mais absente du libellé : ambigu, ignoré
    table = {"hockey": {"FIRST_HALF": "P1", "SECOND_HALF": "P2", "THIRD_PERIOD": "P3"},
             "tennis": {"FIRST_SET": "SET1", "SECOND_SET": "SET2", "FIRST_HALF": "SET1"}}.get(sport, {})
    if c in table:
        return table[c]
    return {"FIRST_HALF": "MT1", "SECOND_HALF": "MT2", "FIRST_QUARTER": "QT1", "SECOND_QUARTER": "QT2",
            "THIRD_QUARTER": "QT3", "FOURTH_QUARTER": "QT4", "FIRST_SET": "SET1", "SECOND_SET": "SET2"}.get(c)


# ---------------------------------------------------------------- règles des bookmakers (prolongations)
# Sports où une prolongation peut changer le résultat d'un marché « match entier ». Pour chacun, la règle
# par défaut de chaque bookmaker quand le libellé ne précise rien, d'après les règlements officiels lus le
# 05/10/2026 (détail et citations : docs/reglements.md) :
#   "MATCH" = prolongation (et tirs au but) inclus, "TEMPS_REG" = temps réglementaire, None = inconnu.
# Les marchés à la règle inconnue ne sont pas comparés (période « MATCH? »).
SPORTS_PROLONGATION = {"hockey", "basket", "football_americain", "baseball"}
REGLE_PAR_DEFAUT = {
    # Winamax : hockey « par défaut sur la base du temps règlementaire » ; basket « temps total du match »
    ("winamax", "hockey"): "TEMPS_REG", ("winamax", "basket"): "MATCH",
    # Betclic (vérifié dans l'appli) : sans mention entre parenthèses, la prolongation compte
    ("betclic", "hockey"): "MATCH", ("betclic", "basket"): "MATCH",
    # Unibet (vérifié dans l'appli) : « temps réglementaire » est écrit dans l'intitulé quand il s'applique ;
    # sans mention, la prolongation compte (face à face et handicaps : règlement 2.3.1.40)
    ("unibet-fr", "hockey"): "MATCH", ("unibet-fr", "basket"): "MATCH",
    # NetBet : « le résultat qui fait foi est celui ... après le temps réglementaire » sauf mention ; au
    # basket, « prolongations incluses » est écrit dans l'intitulé quand elles comptent (vérifié dans l'appli)
    ("netbet", "hockey"): "TEMPS_REG", ("netbet", "basket"): "TEMPS_REG",
    # PMU : basket « temps réglementaire ... ainsi que des prolongations le cas échéant » (règlement) ;
    # hockey : « Prol. et t.a.b. inc. » écrit quand la prolongation compte, sinon temps réglementaire (appli)
    ("pmu", "hockey"): "TEMPS_REG", ("pmu", "basket"): "MATCH",
}
# Football américain et baseball : prolongation (manches supplémentaires) incluse chez tous les bookmakers
# (vérifié dans les applis ; NetBet : « résultat final prolongations incluses ») ; le 1N2 reste sur le temps
# réglementaire (marché avec nul, voir MARCHES_AVEC_NUL)
REGLE_PAR_SPORT = {"football_americain": "MATCH", "baseball": "MATCH"}
# Exceptions vérifiées par marché, quand l'intitulé ne dit rien (un intitulé explicite l'emporte toujours) :
# - Winamax, hockey : « Nombre de buts » du match prolongations incluses (vérifié sur winamax.fr) ;
#   vainqueur à 2 issues = prolongation et tirs au but inclus (règlement) ;
# - Winamax et Unibet, hockey : total par équipe sur le temps réglementaire seulement (vérifié dans l'appli).
# Le contrôle de conformité ne remet pas en cause ces périodes vérifiées (cotes/controle.py).
PERIODE_VERIFIEE = {
    ("winamax", "hockey"): {"TOTAL": "MATCH", "TOTAL_DOM": "TEMPS_REG", "TOTAL_EXT": "TEMPS_REG", "VAINQUEUR": "MATCH"},
    ("unibet-fr", "hockey"): {"TOTAL_DOM": "TEMPS_REG", "TOTAL_EXT": "TEMPS_REG"},
}
# Périodes constatées sur les cotes par le contrôle de conformité (que le contrôle continue de vérifier) :
# - Unibet, hockey, total du match « Plus / Moins x But(s) » : suit la version temps réglementaire de
#   Pinnacle 10 fois plus étroitement que la version prolongation incluse (0,0065 contre 0,070 sur 3 476
#   cotes, nuit du 5 au 6/10/2026), comme le prévoit le règlement Unibet par défaut.
PERIODE_CONSTATEE = {("unibet-fr", "hockey"): {"TOTAL": "TEMPS_REG"}}
# marchés où le nul existe : forcément sur le temps réglementaire
MARCHES_AVEC_NUL = {"RESULTAT_1N2", "DOUBLE_CHANCE", "DRAW_NO_BET", "HANDICAP_3", "HALF_TIME_FULL_TIME"}


def _temps_reglementaire(libelle: str) -> bool:
    l = (libelle or "").lower()
    return any(x in l for x in ("t. rég", "tps rég", "temps réglementaire", "temps règlementaire", "regular time",
                                "regulation", "60 min", "90 min", "(rt)", "hors prolong"))


def _prolongation_incluse(libelle: str) -> bool:
    l = (libelle or "").lower()
    if re.search(r"prol[^,;]*?inclu", l) and "non inclu" not in l:
        return True                       # « prolongations incluses », « Prolongation(s) incluse(s) »…
    return any(x in l for x in ("prolongations incluses", "prolongation incluse", "prol. incl", "incl. ot",
                                "including overtime", "incl. overtime", "tirs au but inclus", "t.a.b. inc", "(ot)"))


def _handicap_hockey_sans_effet(sport: str, marche: str, ligne) -> bool:
    """Au hockey, la prolongation (mort subite) ou les tirs au but donnent toujours 1 but d'écart à partir
    d'une égalité : un handicap à ±1,5, ±2,5… se règle pareil avec ou sans prolongation."""
    return (sport == "hockey" and marche == "HANDICAP" and ligne is not None and abs(ligne) >= 1.5
            and abs(ligne * 2) % 2 == 1)


def periode_match(bookmaker: str, sport: str, marche: str, libelle: str, ligne=None) -> str:
    """Période d'un marché « match entier » selon les règles du bookmaker."""
    if sport not in SPORTS_PROLONGATION:
        return "MATCH"                    # football, handball, rugby… : MATCH = temps réglementaire partout
    if _handicap_hockey_sans_effet(sport, marche, ligne):
        return "MATCH"
    if _temps_reglementaire(libelle) or marche in MARCHES_AVEC_NUL:
        return "TEMPS_REG"
    if _prolongation_incluse(libelle):
        return "MATCH"
    for table in (PERIODE_VERIFIEE, PERIODE_CONSTATEE):
        if marche in table.get((bookmaker, sport), {}):
            return table[(bookmaker, sport)][marche]
    return REGLE_PAR_DEFAUT.get((bookmaker, sport)) or REGLE_PAR_SPORT.get(sport) or "MATCH?"


def _equipe(nom: str, dom: str, ext: str) -> str | None:
    n = (nom or "").strip().lower()
    if not n:
        return None
    if n in ("match nul", "nul", "n", "draw", "x", "tie"):
        return "NUL"
    if n == (dom or "").lower() or n in ("1", "home"):
        return "DOM"
    if n == (ext or "").lower() or n in ("2", "away"):
        return "EXT"
    return None


def traduire(e: dict, bookmaker: str, sport: str, moment: str) -> list[dict]:
    dom, ext = e.get("home"), e.get("away")
    base = {"source": NOMS.get(bookmaker, bookmaker), "bookmaker": bookmaker, "sport": sport,
            "ligue": e.get("league"), "match_id": f"{bookmaker}|{e.get('eventId')}", "domicile": dom,
            "exterieur": ext, "debut": e.get("startTime"), "collecte": moment, "joueur": None,
            "lien": e.get("slug")}
    out = []
    for m in e.get("markets") or []:
        # l'état « actif » du marché n'est pas fiable chez tous les bookmakers (NetBet) : on se fie aux cotes
        sels = [s for s in m.get("selections") or [] if s.get("isActive", True) and not s.get("suspended")
                and (s.get("odds") or 0) > 1]
        if not sels:
            continue
        canon, libelle = m.get("canonicalMarket"), m.get("rawName") or ""
        if libelle_exclu(sport, canon, libelle):
            continue
        per = "MATCH" if canon == "HALF_TIME_FULL_TIME" else periode(sport, m.get("period"), libelle)
        if per is None:
            continue
        for marche, ligne, issue, s in _marche(canon, libelle, sels, sport, dom, ext):
            p = per
            if per == "MATCH":
                p = periode_match(bookmaker, sport, marche, libelle, ligne)
            elif sport in ("basket", "football_americain") and per in ("MT2", "QT4"):
                p = per + "?"             # prolongation comptée dans la 2e mi-temps ? différent selon les sites
            out.append({**base, "marche": marche, "periode": p, "ligne": ligne, "issue": issue,
                        "cote": float(s["odds"]), "libelle": libelle, "cle_marche": f"{bookmaker}|{m.get('marketId')}",
                        "achat": s.get("back"), "vente": s.get("lay")})
    return out


def _marche(canon, libelle, sels, sport, dom, ext):
    """Générateur de (marché, ligne, issue, sélection) pour un marché PulseScore."""
    issues = {s.get("canonicalOutcome"): s for s in sels}
    l = libelle.lower()
    if canon in ("MATCH_RESULT", "HALF_TIME_RESULT", "SET_WINNER"):
        nul = "DRAW" in issues
        for k, s in issues.items():
            i = {"HOME": "DOM", "AWAY": "EXT", "DRAW": "NUL"}.get(k)
            if i:
                yield ("RESULTAT_1N2" if nul else "VAINQUEUR"), None, i, s
    elif canon == "DRAW_NO_BET":
        for k, s in issues.items():
            if k in ("HOME", "AWAY"):
                yield "DRAW_NO_BET", None, {"HOME": "DOM", "AWAY": "EXT"}[k], s
    elif canon == "DOUBLE_CHANCE":
        for k, s in issues.items():
            if k in ("HOME_DRAW", "HOME_AWAY", "DRAW_AWAY"):
                yield "DOUBLE_CHANCE", None, k, s
    elif canon in ("ASIAN_HANDICAP", "GAME_HANDICAP", "SET_HANDICAP"):
        if sport == "tennis" and canon == "ASIAN_HANDICAP":
            return                       # au tennis : sets ou jeux ? ambigu -> ignoré
        h, a = issues.get("HOME"), issues.get("AWAY")
        if not (h and a):
            return
        lh, la = h.get("line"), a.get("line")
        if lh is None:
            lh, la = _crochet(h.get("rawName")), _crochet(a.get("rawName"))
        if lh is None:
            return
        ligne = lh if (la is None or abs(lh + la) < 1e-9 and lh != 0) else lh
        if la is not None and abs(lh - la) < 1e-9:
            ligne = lh                   # même ligne sur les deux issues = ligne du domicile
        unite = {"GAME_HANDICAP": "JEUX_", "SET_HANDICAP": "SETS_"}.get(canon, "")
        yield unite + "HANDICAP", float(ligne), "DOM", h
        yield unite + "HANDICAP", float(ligne), "EXT", a
    elif canon == "EUROPEAN_HANDICAP":
        h = issues.get("HOME")
        ligne = h.get("line") if h else None
        if ligne is None and h:
            ligne = _crochet(h.get("rawName"))
        if ligne is None or "DRAW" not in issues:
            return
        for k, s in issues.items():
            i = {"HOME": "DOM", "AWAY": "EXT", "DRAW": "NUL"}.get(k)
            if i:
                yield "HANDICAP_3", float(ligne), i, s
    elif canon in ("OVER_UNDER", "HALF_TIME_OVER_UNDER", "HOME_OVER_UNDER", "AWAY_OVER_UNDER", "TOTAL_GAMES",
                   "TOTAL_SETS", "CORNERS_OVER_UNDER", "HOME_CORNERS_OVER_UNDER", "AWAY_CORNERS_OVER_UNDER"):
        if sport == "tennis" and canon in ("OVER_UNDER", "HOME_OVER_UNDER", "AWAY_OVER_UNDER") and "jeu" not in l \
                and "game" not in l:
            return                       # breaks, aces… mal classés en « total »
        prefixe = "CORNERS_" if "CORNERS" in canon else ("JEUX_" if (sport == "tennis" and canon != "TOTAL_SETS")
                                                          else ("SETS_" if canon == "TOTAL_SETS" else ""))
        marche = prefixe + ("TOTAL_DOM" if canon.startswith("HOME_") else
                            "TOTAL_EXT" if canon.startswith("AWAY_") else "TOTAL")
        for k, s in issues.items():
            if k not in ("OVER", "UNDER"):
                continue
            ligne = s.get("line")
            if ligne is None:
                ligne = _crochet(s.get("rawName")) or _nombre(s.get("rawName")) or _nombre(libelle)
            if ligne is None:
                continue
            yield marche, float(ligne), {"OVER": "PLUS", "UNDER": "MOINS"}[k], s
    elif canon == "BOTH_TEAMS_TO_SCORE":
        for k, s in issues.items():
            if k in ("YES", "NO"):
                yield "BOTH_TEAMS_TO_SCORE", None, k, s
    elif canon == "CORRECT_SCORE" and sport != "tennis":
        for s in sels:
            m = re.match(r"^\s*(\d+)\s*[-:]\s*(\d+)\s*$", s.get("rawName") or "")
            if m:
                yield "CORRECT_SCORE", None, f"{m.group(1)}-{m.group(2)}", s
    elif canon == "HALF_TIME_FULL_TIME":
        for s in sels:
            parts = re.split(r"\s*/\s*", s.get("rawName") or "")
            if len(parts) == 2:
                a, b = _equipe(parts[0], dom, ext), _equipe(parts[1], dom, ext)
                if a and b:
                    yield "HALF_TIME_FULL_TIME", None, f"{a}/{b}", s
