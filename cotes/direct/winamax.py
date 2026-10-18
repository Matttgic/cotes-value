"""Cotes Winamax lues sur le socket socket.io, au format d'événement PulseScore.

Relevé le 18/10/2026 : une session curl_cffi qui se fait passer pour Chrome,
route ``sport:<id>`` pour les matchs, puis ``match:<id>`` pour les marchés.
``marketId`` est l'identifiant Sportradar. Corners, cartons et pair/impair
ne sont pas traduits : les exclusions de la comparaison restent en place.

``SOURCE_WINAMAX`` vaut ``pulsescore``, ``direct``, ``auto`` ou ``shadow``
(défaut). En ``shadow``, PulseScore décide et le socket sert au rapport.
Basculer exige 95 % des matchs retrouvés et 99 % des cotes communes à ±0,01.
"""
from __future__ import annotations

import json
import os
import random
import re
import time
from datetime import datetime, timedelta, timezone

from cotes.correspondance import ressemblance
from cotes.pulsescore import traduire

URL = "wss://sports-eu-west-3.winamax.fr/uof-sports-server/socket.io/?EIO=4&transport=websocket"
ORIGIN = "https://www.winamax.fr"
# Identifiants de la page sports, limités aux sports déjà suivis (ANJ).
SPORTS = {
    1: "football", 2: "basket", 3: "baseball", 4: "hockey", 5: "tennis",
    6: "handball", 9: "golf", 10: "boxe", 12: "rugby", 13: "football_australien",
    16: "football_americain", 17: "cyclisme", 19: "snooker", 23: "volley",
    31: "badminton", 117: "mma", 9992: "rugby_league",
}
COUVERTURE_MIN = 0.95
ACCORD_MIN = 0.99
ECART_COTE = 0.01
MODES = ("pulsescore", "direct", "auto", "shadow")
_ROUTE = re.compile(r"^(?:sport|match):\d+$")
_EXCLU = re.compile(
    r"corner|carton|\bcards?\b|booking|pair\s*/\s*impair|impair\s*/\s*pair|"
    r"odd\s*/\s*even|even\s*/\s*odd|buteur|\bscorer\b|\bjoueur\b",
    re.I)
# Identifiants Sportradar vus le 18/10/2026, plus les marchés 1X2 / total / handicap
# communs. Les combinés (résultat et les deux équipes marquent, etc.) sont ignorés.
_COMMUNS = {
    1: "MATCH_RESULT", 10: "DOUBLE_CHANCE", 11: "DRAW_NO_BET",
    14: "EUROPEAN_HANDICAP", 16: "ASIAN_HANDICAP", 18: "OVER_UNDER",
    19: "HOME_OVER_UNDER", 20: "AWAY_OVER_UNDER", 29: "BOTH_TEAMS_TO_SCORE",
    47: "HALF_TIME_FULL_TIME", 60: "MATCH_RESULT", 63: "DOUBLE_CHANCE",
    64: "DRAW_NO_BET", 66: "ASIAN_HANDICAP", 68: "OVER_UNDER",
    69: "HOME_OVER_UNDER", 70: "AWAY_OVER_UNDER", 75: "BOTH_TEAMS_TO_SCORE",
    81: "CORRECT_SCORE", 199: "CORRECT_SCORE", 7016: "ASIAN_HANDICAP",
}
_PAR_SPORT = {
    "tennis": {
        186: "MATCH_RESULT", 187: "GAME_HANDICAP", 188: "SET_HANDICAP",
        189: "OVER_UNDER", 190: "HOME_OVER_UNDER", 191: "AWAY_OVER_UNDER",
        202: "SET_WINNER", 204: "OVER_UNDER", 314: "TOTAL_SETS",
    },
    "basket": {
        219: "MATCH_RESULT", 223: "ASIAN_HANDICAP", 225: "OVER_UNDER",
        227: "HOME_OVER_UNDER", 228: "AWAY_OVER_UNDER",
    },
    "hockey": {
        406: "MATCH_RESULT", 410: "ASIAN_HANDICAP", 412: "OVER_UNDER",
        443: "MATCH_RESULT", 446: "OVER_UNDER", 452: "BOTH_TEAMS_TO_SCORE",
        459: "DRAW_NO_BET", 460: "ASIAN_HANDICAP",
    },
}
_HUIT = {"1": "HOME", "2": "AWAY", "x": "DRAW", "X": "DRAW"}
_DOUBLES = {"9": "HOME_DRAW", "10": "HOME_AWAY", "11": "DRAW_AWAY"}
_TOTAUX = {"over": "OVER", "under": "UNDER"}
_BTTS = {"74": "YES", "76": "NO"}


def mode_source() -> str:
    """``shadow`` si la variable est absente ou inconnue."""
    valeur = os.environ.get("SOURCE_WINAMAX", "shadow").strip().lower()
    return valeur if valeur in MODES else "shadow"


def _pause(secondes: float) -> None:
    if secondes > 0:
        time.sleep(secondes)


def _nombre(valeur) -> float | None:
    if isinstance(valeur, bool) or valeur is None:
        return None
    try:
        return float(valeur)
    except (TypeError, ValueError):
        return None


def _heure_unix(valeur):
    n = _nombre(valeur)
    if n is None:
        return None
    try:
        return datetime.fromtimestamp(n, timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


class Socket:
    """Une connexion, des routes espacées. Le corps des messages n'est pas journalisé."""

    def __init__(self, pause: tuple[float, float] = (0.35, 0.6), connecter=None):
        self.pause = pause
        self.requetes = 0
        self.erreurs: list[str] = []
        self._connecter = connecter
        self._ws = None
        self._session = None
        self._premier = True

    def fermer(self) -> None:
        try:
            if self._ws is not None:
                self._ws.close()
        except Exception:  # noqa: BLE001
            pass
        self._ws = None
        self._session = None

    def _noter(self, message: str) -> None:
        if message not in self.erreurs and len(self.erreurs) < 30:
            self.erreurs.append(message)

    def _espacer(self) -> None:
        if self._premier:
            self._premier = False
            return
        bas, haut = self.pause
        _pause(haut if bas == haut else random.uniform(bas, haut))

    def _ouvrir(self) -> None:
        if self._connecter is not None:
            self._ws = self._connecter()
        else:
            from curl_cffi.requests import Session
            self._session = Session(impersonate="chrome")
            self._ws = self._session.ws_connect(URL, headers={"Origin": ORIGIN}, timeout=20)
        if not str(self._lire() or "").startswith("0"):
            raise OSError("ouverture")
        self._ws.send_str("40")
        if not str(self._lire() or "").startswith("40"):
            raise OSError("namespace")

    def _assurer(self) -> None:
        if self._ws is None:
            self._ouvrir()

    def _lire(self) -> str:
        for _ in range(12):
            msg = self._ws.recv_str()
            if msg == "2":
                self._ws.send_str("3")
                continue
            return msg
        return ""

    def demander(self, route: str) -> dict | None:
        if not _ROUTE.fullmatch(route):
            self._noter("route ignorée")
            return None
        self._espacer()
        for essai in range(2):
            try:
                self._assurer()
                self._ws.send_str('42["m",{"route":"%s"}]' % route)
                self.requetes += 1
                msg = self._lire()
            except Exception:  # noqa: BLE001
                self.fermer()
                if essai == 0:
                    continue
                self._noter(f"{route} : réseau")
                return None
            if not str(msg).startswith("42"):
                self._noter(f"{route} : réponse inattendue")
                return None
            try:
                doc = json.loads(msg[2:])
            except ValueError:
                self._noter(f"{route} : JSON invalide")
                return None
            payload = doc[1] if isinstance(doc, list) and len(doc) > 1 else None
            if not isinstance(payload, dict):
                self._noter(f"{route} : objet attendu")
                return None
            return payload
        return None


def sports_demandes(sports: set[str] | None) -> list[tuple[int, str]]:
    """(identifiant Winamax, sport interne), dans un ordre stable."""
    out = []
    for ident, interne in SPORTS.items():
        if sports is None or interne in sports:
            out.append((ident, interne))
    return out


def _spec(valeur) -> dict[str, str]:
    if not isinstance(valeur, str):
        return {}
    out = {}
    for part in valeur.split("|"):
        if "=" not in part:
            continue
        cle, val = part.split("=", 1)
        out[cle] = val
    return out


def _ligne_spec(valeur) -> float | None:
    n = _nombre(valeur)
    return n if n is not None else None


def _canon(sport: str, market_id) -> str | None:
    try:
        ident = int(market_id)
    except (TypeError, ValueError):
        return None
    return _PAR_SPORT.get(sport, {}).get(ident) or _COMMUNS.get(ident)


def _issue(code, libelle: str, domicile: str, exterieur: str, canon: str) -> str | None:
    c = str(code or "")
    if canon in ("OVER_UNDER", "HOME_OVER_UNDER", "AWAY_OVER_UNDER", "TOTAL_SETS"):
        return _TOTAUX.get(c.lower())
    if canon == "BOTH_TEAMS_TO_SCORE":
        return _BTTS.get(c)
    if canon == "DOUBLE_CHANCE":
        return _DOUBLES.get(c)
    if c == "1714":
        return "HOME"
    if c == "1715":
        return "AWAY"
    direct = _HUIT.get(c)
    if direct:
        if canon == "DRAW_NO_BET" or canon in ("ASIAN_HANDICAP", "GAME_HANDICAP", "SET_HANDICAP"):
            return None if direct == "DRAW" else direct
        if direct == "DRAW" and canon not in ("MATCH_RESULT", "HALF_TIME_RESULT", "EUROPEAN_HANDICAP"):
            return None
        if canon in ("MATCH_RESULT", "HALF_TIME_RESULT", "SET_WINNER", "EUROPEAN_HANDICAP"):
            return direct
    if canon in ("ASIAN_HANDICAP", "GAME_HANDICAP", "SET_HANDICAP", "MATCH_RESULT",
                 "SET_WINNER", "DRAW_NO_BET"):
        bas = (libelle or "").casefold()
        if domicile and bas.startswith(domicile.casefold()):
            return "HOME"
        if exterieur and bas.startswith(exterieur.casefold()):
            return "AWAY"
    return None


def _nom_score(code, libelle: str) -> str | None:
    texte = libelle or ""
    if re.match(r"^\s*\d+\s*[-:]\s*\d+\s*$", texte):
        return re.sub(r"\s*:\s*", " - ", texte.strip())
    m = re.match(r"^\s*(\d+)\s*:\s*(\d+)\s*$", str(code or ""))
    return f"{m.group(1)} - {m.group(2)}" if m else None


def marche_depuis(offre: dict, outcomes: dict, odds: dict, domicile: str, exterieur: str,
                  sport: str) -> dict | None:
    if not isinstance(offre, dict) or offre.get("available") is False:
        return None
    titre = str(offre.get("betTitle") or "")
    if _EXCLU.search(titre):
        return None
    canon = _canon(sport, offre.get("marketId"))
    if not canon:
        return None
    spec = _spec(offre.get("specialBetValue"))
    ligne = None
    if canon in ("OVER_UNDER", "HOME_OVER_UNDER", "AWAY_OVER_UNDER", "TOTAL_SETS"):
        ligne = _ligne_spec(spec.get("total"))
        if ligne is None:
            return None
    elif canon in ("ASIAN_HANDICAP", "GAME_HANDICAP", "SET_HANDICAP", "EUROPEAN_HANDICAP"):
        ligne = _ligne_spec(spec.get("hcp"))
        if ligne is None:
            return None
    selections = []
    for oid in offre.get("outcomes") or []:
        issue = outcomes.get(str(oid))
        if not isinstance(issue, dict) or issue.get("available") is False:
            continue
        cote = _nombre(odds.get(str(oid)))
        if cote is None or cote <= 1:
            continue
        libelle = str(issue.get("label") or "")
        if canon == "CORRECT_SCORE":
            libelle = _nom_score(issue.get("code"), libelle) or ""
            if not libelle:
                continue
            selections.append({"canonicalOutcome": "SCORE", "rawName": libelle, "odds": cote})
            continue
        if canon == "HALF_TIME_FULL_TIME":
            if "/" not in libelle:
                continue
            selections.append({"canonicalOutcome": "SCORE", "rawName": libelle, "odds": cote})
            continue
        code = _issue(issue.get("code"), libelle, domicile, exterieur, canon)
        if not code:
            continue
        sel = {"canonicalOutcome": code, "rawName": libelle, "odds": cote}
        if ligne is not None:
            sel["line"] = ligne
        selections.append(sel)
    if len(selections) < 2:
        return None
    return {
        "marketId": offre.get("betId"),
        "canonicalMarket": canon,
        "rawName": titre,
        "period": "FULL_TIME",
        "selections": selections,
    }


def evenement_depuis(match: dict, detail: dict, sport: str) -> dict | None:
    if not isinstance(match, dict) or not isinstance(detail, dict):
        return None
    domicile, exterieur = match.get("competitor1Name"), match.get("competitor2Name")
    if not domicile or not exterieur or not match.get("matchId"):
        return None
    outcomes = {str(k): v for k, v in (detail.get("outcomes") or {}).items() if isinstance(v, dict)}
    odds = {str(k): v for k, v in (detail.get("odds") or {}).items()}
    marches = []
    for offre in (detail.get("bets") or {}).values():
        if isinstance(offre, dict) and offre.get("matchId") not in (None, match.get("matchId")):
            continue
        marche = marche_depuis(offre, outcomes, odds, str(domicile), str(exterieur), sport)
        if marche:
            marches.append(marche)
    debut = _heure_unix(match.get("matchStart"))
    return {
        "eventId": match.get("matchId"),
        "home": domicile,
        "away": exterieur,
        "league": None,
        "startTime": debut.isoformat() if debut else None,
        "markets": marches,
    }


def _a_venir(match: dict, maintenant: datetime, heures: float) -> bool:
    if match.get("status") != "PREMATCH":
        return False
    debut = _heure_unix(match.get("matchStart"))
    return bool(debut and maintenant < debut <= maintenant + timedelta(hours=heures))


def _priorite_libelle(ligne: dict) -> int:
    texte = (ligne.get("libelle") or "").lower()
    if "temps rég" in texte or "temps règ" in texte or "regular time" in texte:
        return 2
    if "prolong" in texte or "overtime" in texte:
        return 0
    return 1


def _retenir(lignes: list[dict]) -> list[dict]:
    gardes: dict[tuple, dict] = {}
    ordre: list[tuple] = []
    for ligne in lignes:
        cle = (ligne.get("match_id"), ligne.get("marche"), ligne.get("periode"),
               ligne.get("ligne"), ligne.get("issue"))
        if cle not in gardes:
            ordre.append(cle)
            gardes[cle] = ligne
            continue
        if _priorite_libelle(ligne) > _priorite_libelle(gardes[cle]):
            gardes[cle] = ligne
    return [gardes[cle] for cle in ordre]


def collecter(sports: set[str] | None = None, heures: float = 36, transport=None,
              pause: tuple[float, float] = (0.35, 0.6),
              maintenant: datetime | None = None) -> tuple[list[dict], dict]:
    """Lignes déjà passées par ``pulsescore.traduire`` (bookmaker ``winamax``)."""
    maintenant = maintenant or datetime.now(timezone.utc)
    propre = transport is None
    client = transport or Socket(pause=pause)
    moment = maintenant.isoformat(timespec="seconds")
    lignes: list[dict] = []
    matchs = 0
    lectures = 0
    try:
        demandes = sports_demandes(sports)
        if not demandes:
            return [], {"ok": True, "erreurs": [], "requetes": 0, "matchs": 0}
        for ident, sport in demandes:
            doc = client.demander(f"sport:{ident}")
            if not doc:
                continue
            lectures += 1
            bruts = [m for m in (doc.get("matches") or {}).values()
                     if isinstance(m, dict) and _a_venir(m, maintenant, heures)]
            matchs += len(bruts)
            for match in bruts:
                detail = client.demander(f"match:{match.get('matchId')}")
                if not detail:
                    continue
                ev = evenement_depuis(match, detail, sport)
                if ev:
                    lignes += _retenir(traduire(ev, "winamax", sport, moment))
        return lignes, {"ok": lectures > 0 or not client.erreurs, "erreurs": list(client.erreurs),
                        "requetes": client.requetes, "matchs": matchs}
    finally:
        if propre and hasattr(client, "fermer"):
            client.fermer()


def _cle_selection(ligne: dict):
    valeur = ligne.get("ligne")
    if isinstance(valeur, bool):
        valeur = None
    elif isinstance(valeur, (int, float)):
        valeur = round(float(valeur), 2)
    return (ligne.get("marche"), ligne.get("periode"), valeur, ligne.get("issue"))


def _heure(valeur):
    try:
        t = datetime.fromisoformat(str(valeur).replace("Z", "+00:00"))
        return t.astimezone(timezone.utc) if t.tzinfo else None
    except (TypeError, ValueError):
        return None


def rapport(pulse: list[dict], direct: list[dict]) -> dict:
    """Couverture des matchs PulseScore et part des cotes communes à ±0,01."""
    ps = [l for l in pulse if isinstance(l, dict) and l.get("bookmaker") == "winamax"]
    di = [l for l in direct if isinstance(l, dict) and l.get("bookmaker") == "winamax"]
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
