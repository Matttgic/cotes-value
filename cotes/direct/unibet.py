"""Cotes Unibet.fr lues sur l'API LVS, au format d'événement PulseScore.

La page d'accueil est lue avec curl_cffi pour obtenir le jeton ``X-LVS-HSToken``.
Les appels ``/lvs-api`` passent ensuite par ``requests``. Un jeton renvoyé dans
la réponse remplace le précédent. Le jeton n'est jamais journalisé.

Seuls les marchés comparés sont demandés (type + période), pas la fiche complète
d'un match : Unibet est la source la plus lourde. Corners, cartons, buteurs et
cotes boostées sont écartés. Les sports sont ceux déjà suivis (liste ANJ),
lus dans l'état de la page, pas des identifiants figés.

``SOURCE_UNIBET`` vaut ``pulsescore``, ``direct``, ``auto`` ou ``shadow``
(défaut). En ``shadow``, PulseScore décide et ce flux sert au rapport.
Basculer exige 95 % des matchs retrouvés et 99 % des cotes communes à ±0,01.
"""
from __future__ import annotations

import json
import os
import random
import re
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import requests

from cotes.correspondance import ressemblance
from cotes.pulsescore import traduire

ACCUEIL = "https://www.unibet.fr/"
BASE = "https://www.unibet.fr/lvs-api"
# code de la page -> sport interne. Formule 1, ski, moto, voile : hors catalogue.
SPORTS = {
    "FOOT": "football", "TENN": "tennis", "BASK": "basket", "ICEH": "hockey",
    "HAND": "handball", "VOLL": "volley", "RUGU": "rugby", "AMFB": "football_americain",
    "BASE": "baseball", "RUGL": "rugby_league", "GOLF": "golf", "CYCL": "cyclisme",
    "BOXI": "boxe", "SNOO": "snooker", "BADM": "badminton", "MMA": "mma",
}
# (type de marché, période). Relevés le 18/10/2026. Absent : la liste par défaut,
# qui porte déjà le marché principal, sans la fiche de 400 marchés.
MARCHES = {
    "football": (
        (1, 100), (1, 102), (1, 103),
        (605, 100), (605, 102), (605, 103),
        (571, 100), (571, 102), (571, 103),
        (350, 100), (350, 102), (350, 103),
        (994001025, 100), (994001025, 102), (994001025, 103),
        (3007, 100), (3007, 102), (3007, 103),
        (3021, 100), (3021, 102), (3021, 103),
        (3001, 100), (3001, 102), (3001, 103),
        (28, 100), (28, 102), (28, 103),
        (27, 100),
    ),
    "tennis": ((68, 113), (68, 114), (68, 115), (1028, 113), (1028, 114), (121066, 113), (840, 113)),
    "basket": (
        (3056, 1195), (3056, 211), (3056, 210), (3056, 213), (3056, 214), (3056, 215), (3056, 216),
        (3057, 1195), (994003008, 209), (994003008, 211), (3060, 209), (3060, 211), (13810, 1195),
    ),
    "hockey": (
        (361, 185), (361, 186), (361, 187), (361, 188),
        (365, 185), (370, 185), (994033019, 185), (10067, 185), (3006, 185), (376, 185),
    ),
    "handball": ((231, 1131),),
    "volley": ((241, 142),),
    "rugby": ((112, 218),),
    "football_americain": ((10089, 120), (11, 119)),
    "baseball": ((19, 205),),
}
PARAMS = {"lineId": "1", "originId": "3", "breakdownEventsIntoDays": "true", "showPromotions": "true"}
COUVERTURE_MIN = 0.95
ACCORD_MIN = 0.99
ECART_COTE = 0.01
MODES = ("pulsescore", "direct", "auto", "shadow")
_PAGES_MAX = 16
_EXCLU = re.compile(
    r"corner|carton|\bcards?\b|booking|pair\s*/\s*impair|impair\s*/\s*pair|"
    r"odd\s*/\s*even|even\s*/\s*odd|buteur|\bscorer\b|\bjoueur\b|boost",
    re.I)
_SCRIPT = re.compile(r'<script[^>]*id="serverApp-state"[^>]*>(.*?)</script>', re.S)
_NOMBRE = re.compile(r"[-+]?\d+(?:[.,]\d+)?")
_CROCHET = re.compile(r"[\[(]\s*([-+]?\d+(?:[.,]\d+)?)\s*[\])]")


def mode_source() -> str:
    """``shadow`` si la variable est absente ou inconnue."""
    valeur = os.environ.get("SOURCE_UNIBET", "shadow").strip().lower()
    return valeur if valeur in MODES else "shadow"


def _pause(secondes: float) -> None:
    if secondes > 0:
        time.sleep(secondes)


def _nombre(valeur) -> float | None:
    if isinstance(valeur, bool) or valeur is None:
        return None
    if isinstance(valeur, (int, float)):
        return float(valeur)
    m = _NOMBRE.search(str(valeur))
    return float(m.group(0).replace(",", ".")) if m else None


def _cote(valeur) -> float | None:
    n = _nombre(valeur)
    if n is None or n <= 1:
        return None
    return n


def _crochet(texte: str) -> float | None:
    m = _CROCHET.search(texte or "")
    return float(m.group(1).replace(",", ".")) if m else None


def _debut(valeur):
    texte = str(valeur or "")
    if not re.fullmatch(r"\d{10}", texte):
        return None
    try:
        return datetime.strptime(texte, "%y%m%d%H%M").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _heure(valeur):
    try:
        t = datetime.fromisoformat(str(valeur).replace("Z", "+00:00"))
        return t.astimezone(timezone.utc) if t.tzinfo else None
    except (TypeError, ValueError):
        return None


def _page_chrome():
    """Page d'accueil seulement : le jeton est dans le HTML, l'API se lit ensuite avec requests."""
    from curl_cffi.requests import Session
    return Session(impersonate="chrome")


def _etat(html: str) -> tuple[str | None, dict[str, int]]:
    """Jeton et nœuds de sports. Le jeton n'est pas recopié ailleurs."""
    m = _SCRIPT.search(html or "")
    if not m:
        return None, {}
    try:
        doc = json.loads(m.group(1))
    except ValueError:
        return None, {}
    hs = doc.get("HsToken") if isinstance(doc, dict) else None
    jeton = hs.get("hsToken") if isinstance(hs, dict) else None
    if not isinstance(jeton, str) or not jeton:
        jeton = None
    sports: dict[str, int] = {}
    ept = doc.get("Ept") if isinstance(doc, dict) else None
    items = ept.get("ept") if isinstance(ept, dict) else None
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict) or item.get("code") not in SPORTS:
                continue
            if isinstance(item.get("id"), int) and not isinstance(item.get("id"), bool):
                sports[item["code"]] = item["id"]
    return jeton, sports


class Client:
    """GET espacés. Le jeton de la réponse, s'il change, remplace le précédent."""

    def __init__(self, session=None, page=None, pause: tuple[float, float] = (0.2, 0.4)):
        self.session = session or requests.Session()
        self.page = page
        self.pause = pause
        self.jeton: str | None = None
        self.noeuds: dict[str, int] = {}
        self.requetes = 0
        self.erreurs: list[str] = []
        self._premier = True

    def _espacer(self) -> None:
        if self._premier:
            self._premier = False
            return
        bas, haut = self.pause
        _pause(haut if bas == haut else random.uniform(bas, haut))

    def ouvrir(self) -> bool:
        lecteur = self.page or _page_chrome()
        try:
            r = lecteur.get(ACCUEIL, timeout=30, headers={
                "Accept": "text/html", "Accept-Language": "fr-FR"})
        except (requests.RequestException, OSError):
            self._noter("accueil")
            return False
        if getattr(r, "status_code", None) != 200:
            self._noter(f"accueil HTTP {getattr(r, 'status_code', '?')}")
            return False
        jeton, noeuds = _etat(getattr(r, "text", "") or "")
        if not jeton:
            self._noter("jeton absent")
            return False
        self.jeton = jeton
        self.noeuds = noeuds
        return True

    def _renouveler(self, headers) -> None:
        if not headers:
            return
        nouveau = None
        for cle in ("X-Lvs-Hstoken", "X-LVS-HSToken", "x-lvs-hstoken"):
            if cle in headers and headers[cle]:
                nouveau = headers[cle]
                break
        if nouveau is None and hasattr(headers, "get"):
            nouveau = headers.get("X-Lvs-Hstoken") or headers.get("X-LVS-HSToken")
        if isinstance(nouveau, str) and nouveau:
            self.jeton = nouveau

    def get(self, chemin: str, params: dict | None = None) -> dict | None:
        if not self.jeton:
            return None
        url = f"{BASE}/{chemin.lstrip('/')}"
        if params:
            url = f"{url}?{urlencode(params)}"
        dernier = "réseau"
        for essai in range(3):
            self._espacer()
            self.requetes += 1
            try:
                r = self.session.get(url, timeout=30, headers={
                    "Accept": "application/json",
                    "Accept-Language": "fr-FR",
                    "Referer": ACCUEIL,
                    "X-LVS-HSToken": self.jeton,
                })
            except (requests.RequestException, OSError):
                dernier = "réseau"
                _pause(0.5 * (essai + 1))
                continue
            self._renouveler(getattr(r, "headers", None))
            if r.status_code in (429, 500, 502, 503, 504):
                dernier = f"HTTP {r.status_code}"
                _pause(0.5 * (essai + 1))
                continue
            if r.status_code != 200:
                self._noter(f"HTTP {r.status_code}")
                return None
            try:
                doc = r.json()
            except ValueError:
                self._noter("JSON invalide")
                return None
            if not isinstance(doc, dict):
                self._noter("objet JSON attendu")
                return None
            return doc
        self._noter(dernier)
        return None

    def _noter(self, message: str) -> None:
        if message not in self.erreurs and len(self.erreurs) < 30:
            self.erreurs.append(message)


def _cache(issue: dict) -> bool:
    flags = issue.get("flags") or []
    if isinstance(flags, str):
        flags = [flags]
    if not isinstance(flags, list):
        return False
    return any(str(f).lower() in {"hidden", "suspended"} for f in flags)


def _boost(event: dict) -> bool:
    path = event.get("path") if isinstance(event.get("path"), dict) else {}
    texte = " ".join(str(event.get(k) or "") for k in ("pdesc", "desc"))
    texte += " " + " ".join(str(path.get(k) or "") for k in ("League", "Category"))
    return bool(re.search(r"boost|cotes boost", texte, re.I))


def _match(event: dict) -> bool:
    return (isinstance(event, dict) and event.get("eType") == "G"
            and event.get("a") and event.get("b") and not _boost(event))


def _canon(desc: str, style: str) -> str | None:
    if _EXCLU.search(desc):
        return None
    d = desc.casefold()
    if "mi-temps / fin" in d or "mi-temps/fin" in d or style == "HALF_TIME_FULL_TIME":
        return "HALF_TIME_FULL_TIME"
    # « Plus / Moins » porte une barre qui n'est pas une combinaison de marchés.
    if "plus / moins" in d or "plus/moins" in d:
        return "TEAM_TOTAL" if " - " in desc else "OVER_UNDER"
    if re.search(r"\bet\b", d) or ("/" in desc and "double chance" not in d):
        return None
    if "double chance" in d:
        return "DOUBLE_CHANCE"
    if "remboursé si nul" in d or "rembourse si nul" in d:
        return "DRAW_NO_BET"
    if "marqueront" in d and ("2 équipes" in d or "deux équipes" in d or "2 equipes" in d):
        return "BOTH_TEAMS_TO_SCORE"
    if "score exact" in d or str(style).startswith("CORRECT_SCORE"):
        return "CORRECT_SCORE"
    if "handicap" in d:
        return "EUROPEAN_HANDICAP" if style == "WIN_DRAW_WIN_HANDICAP" else "ASIAN_HANDICAP"
    if re.fullmatch(r"(1\s*n\s*2|face à face|vainqueur)(\s.*)?", d):
        return "MATCH_RESULT"
    return None


def _issue(desc: str, home: str, away: str, canon: str) -> str | None:
    texte = (desc or "").strip()
    bas = texte.casefold()
    if canon == "DOUBLE_CHANCE":
        parts = [p.strip() for p in texte.split("/")]
        if len(parts) != 2:
            return None

        def cote_nom(nom: str) -> str | None:
            n = nom.casefold()
            if n in {"n", "nul", "x"}:
                return "N"
            if n == home.casefold():
                return "H"
            if n == away.casefold():
                return "A"
            return None

        return {("H", "N"): "HOME_DRAW", ("N", "A"): "DRAW_AWAY", ("H", "A"): "HOME_AWAY"}.get(
            (cote_nom(parts[0]), cote_nom(parts[1])))
    if canon in ("OVER_UNDER", "TEAM_TOTAL"):
        if bas.startswith("plus"):
            return "OVER"
        if bas.startswith("moins"):
            return "UNDER"
        return None
    if canon == "BOTH_TEAMS_TO_SCORE":
        if bas in {"oui", "yes"}:
            return "YES"
        if bas in {"non", "no"}:
            return "NO"
        return None
    if canon == "CORRECT_SCORE":
        return "SCORE"
    if canon == "HALF_TIME_FULL_TIME":
        return "SCORE"
    if bas in {"n", "nul", "x", "match nul"} or re.match(r"^n\b", bas):
        return "DRAW"
    if bas == home.casefold() or bas.startswith(home.casefold() + " "):
        return "HOME"
    if bas == away.casefold() or bas.startswith(away.casefold() + " "):
        return "AWAY"
    return None


def marche_depuis(cle: str, offre: dict, home: str, away: str) -> dict | None:
    if not isinstance(offre, dict):
        return None
    desc = str(offre.get("desc") or "")
    style = str(offre.get("style") or "")
    canon = _canon(desc, style)
    if not canon:
        return None
    if canon == "TEAM_TOTAL":
        droite = desc.split(" - ", 1)[-1]
        if home.casefold() in droite.casefold():
            canon = "HOME_OVER_UNDER"
        elif away.casefold() in droite.casefold():
            canon = "AWAY_OVER_UNDER"
        else:
            return None
    periode = str(offre.get("period") or "")
    libelle = desc if not periode or periode.casefold() in desc.casefold() else f"{desc} - {periode}"
    ligne_marche = _crochet(desc)
    if ligne_marche is None and canon in ("OVER_UNDER", "HOME_OVER_UNDER", "AWAY_OVER_UNDER"):
        ligne_marche = _nombre(desc)
    selections = []
    for issue in offre.get("outcomes") or []:
        if not isinstance(issue, dict) or _cache(issue):
            continue
        cote = _cote(issue.get("price"))
        if cote is None:
            continue
        nom = str(issue.get("desc") or "")
        code = _issue(nom, home, away, "TEAM_TOTAL" if canon in ("HOME_OVER_UNDER", "AWAY_OVER_UNDER") else canon)
        if canon == "HALF_TIME_FULL_TIME":
            nom = nom.replace(" - ", "/")
        if not code:
            continue
        sel = {"canonicalOutcome": code, "rawName": nom, "odds": cote}
        ligne = _crochet(nom)
        if ligne is None and canon in ("OVER_UNDER", "HOME_OVER_UNDER", "AWAY_OVER_UNDER"):
            ligne = ligne_marche if ligne_marche is not None else _nombre(nom)
        if canon in ("ASIAN_HANDICAP", "EUROPEAN_HANDICAP", "OVER_UNDER", "HOME_OVER_UNDER", "AWAY_OVER_UNDER"):
            if ligne is None:
                continue
            sel["line"] = ligne
        selections.append(sel)
    if len(selections) < 2:
        return None
    return {
        "marketId": cle,
        "canonicalMarket": canon,
        "rawName": libelle,
        "period": "FULL_TIME",
        "selections": selections,
    }


def _integrer(sac: dict, items: dict, sport: str) -> list[str]:
    vus = []
    for cle, val in items.items():
        if not isinstance(cle, str) or not isinstance(val, dict):
            continue
        if cle.startswith("e"):
            if not _match(val):
                continue
            sac["events"].setdefault(cle, {
                "home": val.get("a"), "away": val.get("b"), "league": val.get("pdesc"),
                "start": val.get("start"), "sport": sport, "markets": {},
            })
            vus.append(cle)
        elif cle.startswith("m"):
            sac["markets"][cle] = val
        elif cle.startswith("o"):
            sac["outcomes"].setdefault(val.get("parent"), []).append(val)
    return vus


def _attacher(sac: dict) -> None:
    for mid, offre in sac["markets"].items():
        event = sac["events"].get(offre.get("parent"))
        if not event:
            continue
        event["markets"][mid] = {**offre, "outcomes": sac["outcomes"].get(mid, [])}


def _lire_filtre(client: Client, noeud: int, sport: str, sac: dict,
                 type_id, periode) -> None:
    params = dict(PARAMS)
    if type_id is not None:
        params["marketTypeId"] = str(type_id)
    if periode is not None:
        params["periodId"] = str(periode)
    connus: set[str] = set()
    for page in range(_PAGES_MAX):
        params["pageIndex"] = str(page)
        doc = client.get(f"next/50/p{noeud}", params)
        if not doc:
            return
        items = doc.get("items") if isinstance(doc.get("items"), dict) else {}
        vus = _integrer(sac, items, sport)
        if not vus or all(v in connus for v in vus):
            return
        connus.update(vus)
        total = doc.get("numberOfEvents")
        if isinstance(total, int) and not isinstance(total, bool) and (page + 1) * 50 >= total:
            return


def collecter(sports: set[str] | None = None, heures: float = 36, session=None, page=None,
              pause: tuple[float, float] = (0.2, 0.4),
              maintenant: datetime | None = None) -> tuple[list[dict], dict]:
    """Lignes déjà passées par ``pulsescore.traduire`` (bookmaker ``unibet-fr``)."""
    maintenant = maintenant or datetime.now(timezone.utc)
    if sports is not None and not (set(SPORTS.values()) & set(sports)):
        return [], {"ok": True, "erreurs": [], "requetes": 0, "matchs": 0}
    client = Client(session, page, pause)
    if not client.ouvrir():
        return [], {"ok": False, "erreurs": list(client.erreurs), "requetes": client.requetes, "matchs": 0}
    sac = {"events": {}, "markets": {}, "outcomes": {}}
    for code, interne in SPORTS.items():
        if sports is not None and interne not in sports:
            continue
        noeud = client.noeuds.get(code)
        if noeud is None:
            continue
        for type_id, periode in MARCHES.get(interne, ((None, None),)):
            _lire_filtre(client, noeud, interne, sac, type_id, periode)
    _attacher(sac)
    moment = maintenant.isoformat(timespec="seconds")
    lignes: list[dict] = []
    matchs = 0
    horizon = maintenant + timedelta(hours=heures)
    for cle, event in sac["events"].items():
        debut = _debut(event.get("start"))
        if not debut or not (maintenant < debut <= horizon):
            continue
        marches = []
        home, away = str(event["home"]), str(event["away"])
        for mid, offre in event["markets"].items():
            marche = marche_depuis(mid, offre, home, away)
            if marche:
                marches.append(marche)
        if not marches:
            continue
        matchs += 1
        ev = {
            "eventId": cle[1:],
            "home": home,
            "away": away,
            "league": event.get("league"),
            "startTime": debut.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "markets": marches,
        }
        lignes += traduire(ev, "unibet-fr", event["sport"], moment)
    return lignes, {"ok": not client.erreurs or bool(lignes), "erreurs": list(client.erreurs),
                    "requetes": client.requetes, "matchs": matchs}


def _cle_selection(ligne: dict):
    valeur = ligne.get("ligne")
    if isinstance(valeur, bool):
        valeur = None
    elif isinstance(valeur, (int, float)):
        valeur = round(float(valeur), 2)
    return (ligne.get("marche"), ligne.get("periode"), valeur, ligne.get("issue"))


def rapport(pulse: list[dict], direct: list[dict]) -> dict:
    """Couverture des matchs PulseScore et part des cotes communes à ±0,01."""
    ps = [l for l in pulse if isinstance(l, dict) and l.get("bookmaker") == "unibet-fr"]
    di = [l for l in direct if isinstance(l, dict) and l.get("bookmaker") == "unibet-fr"]
    matchs_ps, matchs_di = {}, {}
    for ligne in ps:
        matchs_ps.setdefault(ligne.get("match_id"), ligne)
    for ligne in di:
        matchs_di.setdefault(ligne.get("match_id"), ligne)
    couples = []
    pris = set()
    for mid, a in matchs_ps.items():
        meilleur = None
        for did, b in matchs_di.items():
            if did in pris or a.get("sport") != b.get("sport"):
                continue
            ta, tb = _heure(a.get("debut")), _heure(b.get("debut"))
            if not ta or not tb or abs((ta - tb).total_seconds()) > 90 * 60:
                continue
            score = min(ressemblance(a.get("domicile"), b.get("domicile")),
                        ressemblance(a.get("exterieur"), b.get("exterieur")))
            if meilleur is None or score > meilleur[0]:
                meilleur = (score, did)
        if meilleur and meilleur[0] >= 0.85:
            pris.add(meilleur[1])
            couples.append((mid, meilleur[1]))
    couverture = len(couples) / len(matchs_ps) if matchs_ps else None
    index = {}
    for ligne in di:
        index.setdefault(ligne.get("match_id"), {})[_cle_selection(ligne)] = ligne
    communs = egaux = 0
    for mid_ps, mid_di in couples:
        offres = index.get(mid_di, {})
        for ligne in ps:
            if ligne.get("match_id") != mid_ps:
                continue
            autre = offres.get(_cle_selection(ligne))
            if not autre:
                continue
            communs += 1
            ca, cb = _nombre(ligne.get("cote")), _nombre(autre.get("cote"))
            if ca is not None and cb is not None and abs(ca - cb) <= ECART_COTE + 1e-9:
                egaux += 1
    accord = egaux / communs if communs else None
    pret = bool(couverture is not None and accord is not None
                and couverture + 1e-9 >= COUVERTURE_MIN and accord + 1e-9 >= ACCORD_MIN)
    return {
        "matchs_pulsescore": len(matchs_ps),
        "matchs_direct": len(matchs_di),
        "matchs_communs": len(couples),
        "couverture": None if couverture is None else round(couverture, 4),
        "selections_communes": communs,
        "selections_egales": egaux,
        "accord_cotes": None if accord is None else round(accord, 4),
        "seuil_couverture": COUVERTURE_MIN,
        "seuil_accord": ACCORD_MIN,
        "pret_a_basculer": pret,
    }
