"""Cotes OlyBet.fr lues sur le WebSocket BetConstruct, au format PulseScore.

Le site_id 18769041 ne renvoie que l'offre olybet.fr. curl_cffi (impersonation
Chrome) est nécessaire : un WebSocket simple reçoit un HTTP 400 depuis les
runners GitHub. Les types de marchés sont filtrés dans la requête pour ne pas
ramener props, corners ni pair/impair.

``SOURCE_OLYBET`` vaut ``direct`` (défaut) ou ``off``. PulseScore n'a pas
d'OlyBet : il n'y a pas de mode shadow. Hockey et basket « match entier » sans
mention explicite de prolongation restent en période ``MATCH?`` tant que le
règlement n'est pas vérifié, et la comparaison les ignore.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from cotes.correspondance import ressemblance
from cotes.pulsescore import traduire

SWARM = "wss://eu-swarm-reverse.betconstruct.com/"
ORIGINE = "https://sports.olybet.fr"
SITE_ID = 18769041
# alias BetConstruct -> sport interne. Biathlon et NASCAR sont proposés et exclus.
SPORTS = {
    "Soccer": "football", "Tennis": "tennis", "Basketball": "basket",
    "IceHockey": "hockey", "Handball": "handball", "Volleyball": "volley",
    "RugbyUnion": "rugby", "RugbyLeague": "rugby_league", "Baseball": "baseball",
    "Badminton": "badminton", "Snooker": "snooker", "TableTennis": "tennis_de_table",
    "Cycling": "cyclisme", "AmericanFootball": "football_americain",
    "Boxing": "boxe", "MMA": "mma", "Golf": "golf",
    "AustralianFootball": "football_australien",
}
TYPES = (
    "P1XP2", "P1P2", "OverUnder", "AsianHandicap", "Handicap", "DoubleChance",
    "BothTeamsToScore", "CorrectScore", "HalfTimeFullTime", "Team1OverUnder",
    "Team2OverUnder", "HalfTimeResult", "DrawNoBet",
)
PAR_LOT = 20
_echeance = None
ECART_RELATIF = 0.15
ECHANTILLON = 5
MODES = ("direct", "off")
_EXCLU = re.compile(
    r"corner|carton|\bcards?\b|booking|pair\s*/\s*impair|impair\s*/\s*pair|"
    r"odd\s*/\s*even|even\s*/\s*odd|buteur|scorer|\bjoueur\b|\bplayer\b",
    re.I)
_ISSUES = {
    "P1": "HOME", "P2": "AWAY", "X": "DRAW", "Home": "HOME", "Away": "AWAY",
    "Tie": "DRAW", "W1": "HOME", "W2": "AWAY", "Over": "OVER", "Under": "UNDER",
    "Yes": "YES", "No": "NO", "1X": "HOME_DRAW", "X1": "HOME_DRAW",
    "12": "HOME_AWAY", "X2": "DRAW_AWAY", "2X": "DRAW_AWAY",
}


def mode_source() -> str:
    """``direct`` si la variable est absente ou inconnue."""
    valeur = os.environ.get("SOURCE_OLYBET", "direct").strip().lower()
    return valeur if valeur in MODES else "direct"


def sports_demandes(sports: set[str] | None) -> list[tuple[str, str]]:
    if sports is None:
        return list(SPORTS.items())
    voulu = set(sports)
    return [(alias, sport) for alias, sport in SPORTS.items() if sport in voulu]


def _heure_unix(valeur):
    try:
        return datetime.fromtimestamp(int(valeur), timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _heure_iso(valeur):
    try:
        t = datetime.fromisoformat(str(valeur).replace("Z", "+00:00"))
        return t.astimezone(timezone.utc) if t.tzinfo else None
    except (TypeError, ValueError):
        return None


def _nombre(valeur) -> float | None:
    if isinstance(valeur, bool) or valeur is None:
        return None
    try:
        return float(valeur)
    except (TypeError, ValueError):
        return None


def _donnees(doc) -> dict:
    data = ((doc or {}).get("data") or {}).get("data")
    return data if isinstance(data, dict) else {}


def jeux_depuis(doc) -> list[dict]:
    """Matchs d'une réponse ``get`` (sport / [région /] compétition / jeu), avec le chemin de leur page."""
    out = []
    for sp in (_donnees(doc).get("sport") or {}).values():
        if not isinstance(sp, dict):
            continue
        regions = [r for r in (sp.get("region") or {}).values() if isinstance(r, dict)] or [{"competition": sp.get("competition")}]
        for region in regions:
            for cid, comp in (region.get("competition") or {}).items():
                if not isinstance(comp, dict):
                    continue
                ligue = comp.get("name")
                for gid, jeu in (comp.get("game") or {}).items():
                    if isinstance(jeu, dict):
                        ident = jeu.get("id", gid)
                        out.append({**jeu, "id": ident, "league": ligue,
                                    "chemin": chemin_match(sp.get("alias"), region.get("alias"), comp.get("id", cid), ident)})
    return out


def chemin_match(sport, region, competition, jeu) -> str | None:
    """Chemin de la page du match sur olybet.fr, ``/sportsbook/pre-match/match/<sport>/<région>/<compétition>/<id>``.

    Vérifié le 25/10/2026 (PSG - Lyon, Philadelphia - Detroit) : sport et région sont les alias BetConstruct
    (« North America » garde son espace), compétition et match leurs identifiants. Une région ou une
    compétition fausse renvoie à la page de la compétition : sans les quatre, pas de chemin."""
    if not isinstance(sport, str) or not isinstance(region, str) or not sport.strip() or not region.strip():
        return None
    if not str(competition).isdigit() or not str(jeu).isdigit():
        return None
    return f"/sportsbook/pre-match/match/{quote(sport.strip(), safe='')}/{quote(region.strip(), safe='')}/{competition}/{jeu}"


def marches_par_jeu(doc) -> dict:
    """id de jeu -> marchés, pour une réponse filtrée par identifiants."""
    out = {}
    for gid, jeu in (_donnees(doc).get("game") or {}).items():
        if not isinstance(jeu, dict):
            continue
        ident = jeu.get("id", gid)
        marches = [m for m in (jeu.get("market") or {}).values() if isinstance(m, dict)]
        out[ident] = marches
        try:
            out[int(ident)] = marches
        except (TypeError, ValueError):
            pass
    return out


def _canonique(type_marche: str, nom: str, sport: str) -> str | None:
    if _EXCLU.search(nom or ""):
        return None
    if type_marche in ("P1XP2", "P1P2", "HalfTimeResult"):
        return "MATCH_RESULT"
    if type_marche == "DrawNoBet":
        return "DRAW_NO_BET"
    if type_marche == "DoubleChance":
        return "DOUBLE_CHANCE"
    if type_marche == "BothTeamsToScore":
        return "BOTH_TEAMS_TO_SCORE"
    if type_marche == "CorrectScore":
        return "CORRECT_SCORE"
    if type_marche == "HalfTimeFullTime":
        return "HALF_TIME_FULL_TIME"
    libelle = (nom or "").lower()
    if type_marche == "Handicap":
        if sport == "tennis" and "jeu" in libelle:
            return "GAME_HANDICAP"
        if sport == "tennis" and "set" in libelle:
            return "SET_HANDICAP"
        if sport == "tennis":
            return None
        return "EUROPEAN_HANDICAP"
    if type_marche == "AsianHandicap":
        return None if sport == "tennis" else "ASIAN_HANDICAP"
    if type_marche == "Team1OverUnder":
        return "HOME_OVER_UNDER"
    if type_marche == "Team2OverUnder":
        return "AWAY_OVER_UNDER"
    if type_marche == "OverUnder":
        if sport == "tennis" and "set" in libelle and "jeu" not in libelle:
            return "TOTAL_SETS"
        return "OVER_UNDER"
    return None


def marche_depuis(offre: dict, sport: str) -> dict | None:
    if not isinstance(offre, dict) or offre.get("is_blocked"):
        return None
    nom = str(offre.get("name") or "")
    canon = _canonique(str(offre.get("type") or ""), nom, sport)
    if not canon:
        return None
    selections = []
    for issue in (offre.get("event") or {}).values():
        if not isinstance(issue, dict) or issue.get("is_blocked"):
            continue
        cote = _nombre(issue.get("price"))
        if cote is None or cote <= 1:
            continue
        brut = str(issue.get("name") or "").strip()
        if canon in ("CORRECT_SCORE", "HALF_TIME_FULL_TIME"):
            outcome = "SCORE"
        else:
            outcome = _ISSUES.get(str(issue.get("type") or ""))
            if outcome is None:
                continue
        ligne = _nombre(issue.get("base")) if issue.get("base") is not None else None
        selections.append({"canonicalOutcome": outcome, "rawName": brut, "odds": cote, "line": ligne})
    if len(selections) < 2:
        return None
    return {
        "marketId": offre.get("id"),
        "canonicalMarket": canon,
        "rawName": nom,
        "period": "FULL_TIME",
        "selections": selections,
    }


def _a_venir(jeu: dict, maintenant: datetime, heures: float) -> bool:
    if jeu.get("is_started") or jeu.get("is_blocked") or jeu.get("is_live"):
        return False
    if not jeu.get("team1_name") or not jeu.get("team2_name"):
        return False
    debut = _heure_unix(jeu.get("start_ts"))
    return bool(debut and maintenant < debut <= maintenant + timedelta(hours=heures))


class Swarm:
    """Une session, des messages ``rid``. Le corps d'erreur n'est pas conservé."""

    def __init__(self, timeout: int = 40):
        from curl_cffi.requests import Session
        self._s = Session(impersonate="chrome")
        self.ws = self._s.ws_connect(SWARM, headers={"Origin": ORIGINE}, timeout=timeout)
        self._rid = 0
        self.requetes = 0
        self.erreurs: list[str] = []
        self.echeance = None

    def appel(self, commande: str, params: dict):
        if self.echeance is not None and not self.echeance.ok():
            if "budget" not in self.erreurs:
                self.erreurs.append("budget")
            return None
        self._rid += 1
        rid = str(self._rid)
        self.requetes += 1
        self.ws.send_str(json.dumps({"command": commande, "params": params, "rid": rid}))
        for _ in range(40):
            if self.echeance is not None and not self.echeance.ok():
                if "budget" not in self.erreurs:
                    self.erreurs.append("budget")
                return None
            message = json.loads(self.ws.recv_str())
            if str(message.get("rid")) != rid:
                continue
            if message.get("code") not in (0, None):
                self.erreurs.append(f"code {message.get('code')}")
                return None
            return message
        self.erreurs.append("sans réponse")
        return None

    def fermer(self) -> None:
        try:
            self.ws.close()
        finally:
            self._s.close()


def _lots(ids: list, taille: int):
    for i in range(0, len(ids), taille):
        yield ids[i:i + taille]


def collecter(sports: set[str] | None = None, heures: float = 36, client=None,
              maintenant: datetime | None = None, echeance=None) -> tuple[list[dict], dict]:
    """Lignes déjà passées par ``pulsescore.traduire`` (bookmaker ``olybet``)."""
    maintenant = maintenant or datetime.now(timezone.utc)
    if echeance is None:
        echeance = _echeance
    moment = maintenant.isoformat(timespec="seconds")
    demandes = sports_demandes(sports)
    if not demandes:
        return [], {"ok": True, "erreurs": [], "requetes": 0, "matchs": 0}
    propre = client is None
    delai = 40 if echeance is None else max(5, int(min(20, echeance.reste() or 5)))
    swarm = client or Swarm(timeout=delai)
    if hasattr(swarm, "echeance"):
        swarm.echeance = echeance
    try:
        if not swarm.appel("request_session", {"site_id": SITE_ID, "language": "fra", "source": 42}):
            return [], {"ok": False, "erreurs": list(getattr(swarm, "erreurs", [])) or ["session"],
                        "requetes": getattr(swarm, "requetes", 0), "matchs": 0}
        lignes: list[dict] = []
        matchs = 0
        for alias, sport in demandes:
            if echeance is not None and not echeance.ok():
                if "budget" not in swarm.erreurs:
                    swarm.erreurs.append("budget")
                break
            liste = swarm.appel("get", {
                "source": "betting",
                "what": {"sport": ["alias"], "region": ["alias"], "competition": ["id", "name"],
                         "game": ["id", "team1_name", "team2_name", "start_ts",
                                  "is_started", "is_blocked", "is_live"]},
                "where": {"sport": {"alias": alias}, "game": {"type": {"@in": [0, 2]}}},
                "subscribe": False,
            })
            choisis = [j for j in jeux_depuis(liste) if _a_venir(j, maintenant, heures)]
            matchs += len(choisis)
            for lot in _lots(choisis, PAR_LOT):
                if echeance is not None and not echeance.ok():
                    if "budget" not in swarm.erreurs:
                        swarm.erreurs.append("budget")
                    break
                detail = swarm.appel("get", {
                    "source": "betting",
                    "what": {"game": ["id"], "market": ["id", "type", "name", "base"],
                             "event": ["type", "name", "price", "base"]},
                    "where": {"game": {"id": {"@in": [j["id"] for j in lot]}},
                              "market": {"type": {"@in": list(TYPES)}}},
                    "subscribe": False,
                })
                par_id = marches_par_jeu(detail)
                for jeu in lot:
                    debut = _heure_unix(jeu.get("start_ts"))
                    domicile = str(jeu.get("team1_name") or "").strip()
                    exterieur = str(jeu.get("team2_name") or "").strip()
                    ligue = str(jeu.get("league") or "").strip()
                    marches = []
                    for offre in par_id.get(jeu.get("id"), []):
                        marche = marche_depuis(offre, sport)
                        if marche:
                            marches.append(marche)
                    if not marches or debut is None or not domicile or not exterieur:
                        continue
                    evenement = {
                        "eventId": jeu.get("id"),
                        "home": domicile,
                        "away": exterieur,
                        "league": ligue or None,
                        "startTime": debut.isoformat().replace("+00:00", "Z"),
                        "markets": marches,
                        "slug": jeu.get("chemin"),
                    }
                    lignes += traduire(evenement, "olybet", sport, moment)
        erreurs = list(getattr(swarm, "erreurs", []))
        return lignes, {"ok": not erreurs or bool(lignes), "erreurs": erreurs,
                        "requetes": getattr(swarm, "requetes", 0), "matchs": matchs}
    except Exception as e:  # noqa: BLE001
        return [], {"ok": False, "erreurs": [type(e).__name__],
                    "requetes": getattr(swarm, "requetes", 0), "matchs": 0}
    finally:
        if propre:
            swarm.fermer()


def _meme_match(a: dict, b: dict) -> bool:
    if a.get("sport") != b.get("sport"):
        return False
    ta, tb = _heure_iso(a.get("debut")), _heure_iso(b.get("debut"))
    if not ta or not tb or abs((ta - tb).total_seconds()) > 90 * 60:
        return False
    return min(ressemblance(a.get("domicile"), b.get("domicile")),
               ressemblance(a.get("exterieur"), b.get("exterieur"))) >= 0.85


def _nom_reference(ligne: dict) -> str | None:
    if ligne.get("bookmaker") == "pmu" or ligne.get("source") == "PMU":
        return "PMU"
    if ligne.get("source") == "pinnacle":
        return "Pinnacle"
    return None


def controle_prix(olybet: list[dict], references: list[dict], plafond: int = ECHANTILLON) -> dict:
    """Quelques 1N2 football comparés à PMU et Pinnacle. Un écart relatif > 15 % est signalé.

    Les cotes restent dans la comparaison : le contrôle ne retire rien, il signale.
    """
    cibles = []
    vus = set()
    for ligne in olybet:
        if not (ligne.get("sport") == "football" and ligne.get("marche") == "RESULTAT_1N2"
                and ligne.get("issue") == "DOM" and ligne.get("periode") == "MATCH"):
            continue
        if ligne.get("match_id") in vus:
            continue
        vus.add(ligne.get("match_id"))
        cibles.append(ligne)
        if len(cibles) >= plafond:
            break
    refs = [l for l in references if _nom_reference(l) and l.get("sport") == "football"
            and l.get("marche") == "RESULTAT_1N2" and l.get("issue") == "DOM"
            and l.get("periode") == "MATCH"]
    comparaisons = []
    for ligne in cibles:
        vues = set()
        for ref in refs:
            nom = _nom_reference(ref)
            if nom in vues or not _meme_match(ligne, ref):
                continue
            vues.add(nom)
            co, cr = _nombre(ligne.get("cote")), _nombre(ref.get("cote"))
            if not co or not cr:
                continue
            ecart = abs(co / cr - 1)
            comparaisons.append({
                "match": f"{ligne.get('domicile')} – {ligne.get('exterieur')}",
                "source": nom,
                "cote_olybet": round(co, 3),
                "cote_reference": round(cr, 3),
                "ecart_relatif": round(ecart, 4),
                "aberrant": ecart > ECART_RELATIF + 1e-9,
            })
    return {
        "ok": True,
        "seuil_relatif": ECART_RELATIF,
        "examines": len(comparaisons),
        "comparaisons": comparaisons,
        "aberrants": [c for c in comparaisons if c["aberrant"]],
    }
