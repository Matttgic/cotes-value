"""Cotes Winamax lues sur le socket socket.io, au format d'événement PulseScore.

Relevé le 18/10/2026 : une session curl_cffi qui se fait passer pour Chrome.
La route ``sport:<id>`` porte déjà tous les matchs du sport (environ 340 sur
36 h). Les marchés comparés arrivent ensuite, un filtre à la fois, et non
match par match. Le serveur pousse aussi des mises à jour sans ``requestId`` :
elles sont ignorées, seule la trame qui porte l'identifiant demandé est lue.
``marketId`` est l'identifiant Sportradar. Corners, cartons et pair/impair
ne sont pas traduits : les exclusions de la comparaison restent en place.

Une lecture sans aucun match, ou qui ne cote pas la moitié de ceux qu'elle
vient d'annoncer, est un échec : l'étape du cycle est alors notée en échec.
"""
from __future__ import annotations

import json
import random
import re
import time
from datetime import datetime, timedelta, timezone

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
    # Le vainqueur à deux issues porte le même identifiant qu'au tennis.
    "volley": {186: "MATCH_RESULT"},
    "snooker": {186: "MATCH_RESULT"},
    "badminton": {186: "MATCH_RESULT"},
    "football_americain": {219: "MATCH_RESULT"},
}
# Filtres de la page sport, limités aux marchés déjà comparés. Le football est
# le plus lourd (quelques Mo par filtre) ; un filtre remplace des centaines de
# routes ``match:``.
# Tennis et hockey relevés le 20/10/2026 (sans eux : vainqueur seul) ; un seul filtre par marché, les autres
# (108/120, 247/260…) renvoient les mêmes paris. Tennis : sets (314), jeux (189), écart de sets (188),
# écart de jeux (187), jeux de chaque joueur (190, 191). Hockey : écart (410), total (412), les deux
# équipes marquent (29), vainqueur (406), double chance (10).
FILTRES = {
    "football": (6, 13, 16, 56, 17, 74, 4),
    "basket": (207,),
    "tennis": (107, 108, 116, 121, 122, 123),
    "hockey": (247, 248, 249, 253, 255),
}
# En dessous, la lecture a vu les matchs mais n'a presque pas sorti de cotes.
_SEUIL_LECTURE = 0.5
_MIN_POUR_SEUIL = 8
_REPONSES_MAX = 8
_echeance = None
_HUIT = {"1": "HOME", "2": "AWAY", "x": "DRAW", "X": "DRAW"}
_DOUBLES = {"9": "HOME_DRAW", "10": "HOME_AWAY", "11": "DRAW_AWAY"}
_TOTAUX = {"over": "OVER", "under": "UNDER"}
_BTTS = {"74": "YES", "76": "NO"}
_ABREGE = re.compile(r"^(?:[^\W\d_]{1,3}\.\s*)+(.+?)(?:\s*[-+]\d+(?:[.,]\d+)?)?\s*$")


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
        self.echeance = None
        self._seq = 0

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
            self._ws = self._session.ws_connect(URL, headers={"Origin": ORIGIN}, timeout=30)
        if not str(self._lire() or "").startswith("0"):
            raise OSError("ouverture")
        self._ws.send_str("40")
        if not str(self._lire() or "").startswith("40"):
            raise OSError("namespace")

    def _assurer(self) -> None:
        if self._ws is None:
            self._ouvrir()

    def _reprise(self, essai: int) -> bool:
        """Pause courte puis nouvel essai, tant que le budget le permet."""
        if self.echeance is not None and not self.echeance.ok():
            return False
        delai = min(1.0, 0.3 * (essai + 1))
        reste = getattr(self.echeance, "reste", None) if self.echeance is not None else None
        if reste is not None:
            valeur = reste()
            if valeur is not None and valeur < delai + 1:
                return False
        _pause(delai)
        return True

    def _lire(self) -> str:
        for _ in range(12):
            msg = self._ws.recv_str()
            if msg == "2":
                self._ws.send_str("3")
                continue
            return msg
        return ""

    def _lire_reponse(self, identifiant: str) -> str:
        """Ignore les poussées sans l'identifiant de la demande en cours."""
        for _ in range(_REPONSES_MAX):
            msg = self._lire()
            if not str(msg).startswith("42"):
                continue
            try:
                doc = json.loads(msg[2:])
            except ValueError:
                continue
            payload = doc[1] if isinstance(doc, list) and len(doc) > 1 else None
            if isinstance(payload, dict) and payload.get("requestId") == identifiant:
                return msg
        return ""

    def demander(self, route: str, filtre: int | None = None) -> dict | None:
        if self.echeance is not None and not self.echeance.ok():
            self._noter("budget")
            return None
        if not _ROUTE.fullmatch(route):
            self._noter("route ignorée")
            return None
        self._espacer()
        identifiant = f"w{self._seq}"
        self._seq += 1
        corps = {"route": route, "requestId": identifiant}
        if filtre is not None:
            corps["filterId"] = int(filtre)
        message = "42" + json.dumps(["m", corps], separators=(",", ":"))
        for essai in range(3):
            if self.echeance is not None and not self.echeance.ok():
                self._noter("budget")
                return None
            try:
                self._assurer()
                self._ws.send_str(message)
                self.requetes += 1
                msg = self._lire_reponse(identifiant)
            except Exception:  # noqa: BLE001
                self.fermer()
                if essai < 2 and self._reprise(essai):
                    continue
                self._noter(f"{route} : réseau")
                return None
            if not str(msg).startswith("42"):
                self._noter(f"{route} : réponse absente")
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
        # Tennis : « M. Uchijima +0.5 » pour Moyuka Uchijima. Le nom de famille doit désigner un seul joueur.
        m = _ABREGE.match(bas)
        if m:
            nom = m.group(1)
            dom = bool(domicile) and (domicile.casefold() == nom or domicile.casefold().endswith(" " + nom))
            ext = bool(exterieur) and (exterieur.casefold() == nom or exterieur.casefold().endswith(" " + nom))
            if dom != ext:
                return "HOME" if dom else "AWAY"
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
        if isinstance(offre, dict) and str(offre.get("matchId")) != str(match.get("matchId")):
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


def _noter_budget(client) -> None:
    erreurs = getattr(client, "erreurs", None)
    if isinstance(erreurs, list) and "budget" not in erreurs:
        erreurs.append("budget")
    noter = getattr(client, "_noter", None)
    if noter and (not isinstance(erreurs, list) or "budget" not in erreurs):
        noter("budget")


def _fusionner(sac: dict, doc: dict | None) -> None:
    if not isinstance(doc, dict):
        return
    for cle in ("bets", "outcomes", "odds"):
        val = doc.get(cle)
        if isinstance(val, dict):
            sac[cle].update(val)


def _detail_du(match_id, sac: dict) -> dict:
    mid = str(match_id)
    bets = {cle: offre for cle, offre in sac["bets"].items()
            if isinstance(offre, dict) and str(offre.get("matchId")) == mid}
    besoin = {str(oid) for offre in bets.values() for oid in (offre.get("outcomes") or [])}
    return {
        "bets": bets,
        "outcomes": {k: v for k, v in sac["outcomes"].items() if str(k) in besoin},
        "odds": {k: v for k, v in sac["odds"].items() if str(k) in besoin},
    }


def collecter(sports: set[str] | None = None, heures: float = 36, transport=None,
              pause: tuple[float, float] = (0.35, 0.6),
              maintenant: datetime | None = None, echeance=None) -> tuple[list[dict], dict]:
    """Lignes déjà passées par ``pulsescore.traduire`` (bookmaker ``winamax``)."""
    maintenant = maintenant or datetime.now(timezone.utc)
    if echeance is None:
        echeance = _echeance
    propre = transport is None
    client = transport or Socket(pause=pause)
    if hasattr(client, "echeance"):
        client.echeance = echeance
    moment = maintenant.isoformat(timespec="seconds")
    lignes: list[dict] = []
    matchs = 0
    try:
        demandes = sports_demandes(sports)
        if not demandes:
            return [], {"ok": True, "erreurs": [], "requetes": 0, "matchs": 0}
        for ident, sport in demandes:
            if echeance is not None and not echeance.ok():
                _noter_budget(client)
                break
            doc = client.demander(f"sport:{ident}")
            if not isinstance(doc, dict):
                continue
            sac = {"bets": {}, "outcomes": {}, "odds": {}}
            _fusionner(sac, doc)
            for filtre in FILTRES.get(sport, ()):
                if echeance is not None and not echeance.ok():
                    _noter_budget(client)
                    break
                _fusionner(sac, client.demander(f"sport:{ident}", filtre))
            bruts = [m for m in (doc.get("matches") or {}).values()
                     if isinstance(m, dict) and _a_venir(m, maintenant, heures)]
            bruts.sort(key=lambda m: m.get("matchStart") or 0)
            matchs += len(bruts)
            for match in bruts:
                ev = evenement_depuis(match, _detail_du(match.get("matchId"), sac), sport)
                if ev:
                    lignes += _retenir(traduire(ev, "winamax", sport, moment))
        couverts = len({l.get("match_id") for l in lignes})
        if not lignes:
            client._noter("lecture vide")
            ok = False
        elif matchs >= _MIN_POUR_SEUIL and couverts < _SEUIL_LECTURE * matchs:
            client._noter("lecture incomplète")
            ok = False
        else:
            ok = True
        return lignes, {"ok": ok, "erreurs": list(client.erreurs),
                        "requetes": client.requetes, "matchs": matchs}
    finally:
        if propre and hasattr(client, "fermer"):
            client.fermer()


def _heure(valeur):
    try:
        t = datetime.fromisoformat(str(valeur).replace("Z", "+00:00"))
        return t.astimezone(timezone.utc) if t.tzinfo else None
    except (TypeError, ValueError):
        return None


