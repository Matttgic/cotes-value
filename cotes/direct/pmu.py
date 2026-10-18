"""Cotes PMU lues sur l'API publique Kambi, au format d'événement PulseScore.

Le catalogue a été relevé le 18/10/2026 sur ``group.json`` (offre pmusportsfr).
Seuls les sports autorisés par l'ANJ et réellement proposés par PMU sont demandés.
Formule 1, voile et sports d'hiver sont écartés. Corners, cartons et pair/impair
ne sont pas traduits : les exclusions déjà appliquées par la comparaison restent
en place pour tout ce qui passerait quand même.

``SOURCE_PMU`` vaut ``pulsescore``, ``direct``, ``auto`` ou ``shadow`` (défaut).
En ``shadow``, PulseScore reste la source des décisions ; le flux direct sert au
rapport de couverture. Basculer exige au moins 95 % des matchs PulseScore
retrouvés et 99 % des cotes communes à ±0,01.
"""
from __future__ import annotations

import os
import random
import re
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import requests

from cotes.correspondance import ressemblance
from cotes.pulsescore import traduire

BASE = "https://eu1.offering-api.kambicdn.com/offering/v2018/pmusportsfr"
PARAMS = {"lang": "fr_FR", "market": "FR", "client_id": "2", "channel_id": "1"}
# termKey Kambi -> sport interne (le même vocabulaire que pulsescore.traduire)
SPORTS = {
    "football": "football", "tennis": "tennis", "basketball": "basket",
    "ice_hockey": "hockey", "handball": "handball", "volleyball": "volley",
    "rugby_union": "rugby", "american_football": "football_americain",
    "baseball": "baseball", "ufc_mma": "mma", "boxing": "boxe",
    "snooker": "snooker", "rugby_league": "rugby_league", "golf": "golf",
    "cycling": "cyclisme", "badminton": "badminton",
    "australian_rules": "football_australien",
}
PAR_LOT = 20
COUVERTURE_MIN = 0.95
ACCORD_MIN = 0.99
ECART_COTE = 0.01
_HORLOGE = re.compile(r"\d{1,2}:\d{2}")
_EXCLU = re.compile(
    r"corner|carton|\bcards?\b|booking|pair\s*/\s*impair|impair\s*/\s*pair|"
    r"odd\s*/\s*even|even\s*/\s*odd",
    re.I)
_ISSUES = {
    "OT_ONE": "HOME", "OT_CROSS": "DRAW", "OT_TWO": "AWAY",
    "OT_OVER": "OVER", "OT_UNDER": "UNDER", "OT_YES": "YES", "OT_NO": "NO",
    "OT_ONE_OR_CROSS": "HOME_DRAW", "OT_ONE_OR_TWO": "HOME_AWAY",
    "OT_CROSS_OR_TWO": "DRAW_AWAY",
}
MODES = ("pulsescore", "direct", "auto", "shadow")


def mode_source() -> str:
    """``shadow`` si la variable est absente ou inconnue."""
    valeur = os.environ.get("SOURCE_PMU", "shadow").strip().lower()
    return valeur if valeur in MODES else "shadow"


def _heure(valeur):
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


def _cote(valeur) -> float | None:
    n = _nombre(valeur)
    if n is None:
        return None
    if n >= 100:
        n = n / 1000
    return n if n > 1 else None


def _ligne(valeur) -> float | None:
    n = _nombre(valeur)
    if n is None:
        return None
    if abs(n) >= 50:
        n = n / 1000
    return n


def _pause(secondes: float) -> None:
    if secondes > 0:
        time.sleep(secondes)


class Client:
    """GET espacés. Un 429 attend puis réessaie ; le corps n'est jamais journalisé."""

    def __init__(self, session=None, pause: tuple[float, float] = (1.0, 1.5)):
        self.session = session or requests.Session()
        self.pause = pause
        self.requetes = 0
        self.erreurs: list[str] = []
        self._premier = True

    def _espacer(self) -> None:
        if self._premier:
            self._premier = False
            return
        bas, haut = self.pause
        _pause(haut if bas == haut else random.uniform(bas, haut))

    def get(self, chemin: str) -> dict | None:
        url = f"{BASE}/{chemin}?{urlencode(PARAMS)}"
        dernier = "réseau"
        for essai in range(4):
            self._espacer()
            self.requetes += 1
            try:
                r = self.session.get(url, timeout=30, headers={"Accept": "application/json"})
            except requests.RequestException:
                dernier = "réseau"
                if essai < 3:
                    _pause(2 * (essai + 1))
                continue
            if r.status_code in (429, 500, 502, 503, 504):
                dernier = f"HTTP {r.status_code}"
                attente = _nombre(r.headers.get("Retry-After")) if r.status_code == 429 else None
                _pause(attente if attente is not None and 0 < attente <= 30 else 2 * (essai + 1))
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


def sports_demandes(sports: set[str] | None) -> list[tuple[str, str]]:
    """(termKey, sport interne), dans un ordre stable. ``None`` : tout le catalogue."""
    out = []
    for terme, interne in SPORTS.items():
        if sports is None or interne in sports:
            out.append((terme, interne))
    return out


def _exclu(offre: dict) -> bool:
    crit = offre.get("criterion") if isinstance(offre.get("criterion"), dict) else {}
    libelle = f"{crit.get('label') or ''} {crit.get('englishLabel') or ''}"
    occurrence = str(crit.get("occurrenceType") or "").upper()
    if occurrence in {"CORNERS", "CORNER", "CARDS", "CARD", "BOOKINGS", "BOOKING"}:
        return True
    if _EXCLU.search(libelle) or _HORLOGE.search(libelle):
        return True
    type_offre = (offre.get("betOfferType") or {}).get("englishName") or ""
    return type_offre.startswith("Player") or "scorer" in libelle.lower() or "buteur" in libelle.lower()


def _canonique(offre: dict, domicile: str, exterieur: str) -> tuple[str, str] | None:
    crit = offre.get("criterion") or {}
    anglais = str(crit.get("englishLabel") or "")
    francais = str(crit.get("label") or anglais)
    type_offre = str((offre.get("betOfferType") or {}).get("englishName") or "")
    bas = anglais.lower()
    if "both teams to score" in bas or "les deux équipes marquent" in francais.lower():
        return "BOTH_TEAMS_TO_SCORE", francais
    if type_offre == "Double Chance" or bas == "double chance":
        return "DOUBLE_CHANCE", francais
    if "draw no bet" in bas or "remboursé" in francais.lower():
        return "DRAW_NO_BET", francais
    if type_offre in ("HT/FT", "Half Time/Full Time") or "half time/full time" in bas:
        return "HALF_TIME_FULL_TIME", francais
    if type_offre == "Correct Score" or bas == "correct score":
        return "CORRECT_SCORE", francais
    if type_offre == "3-Way Handicap":
        return "EUROPEAN_HANDICAP", francais
    if type_offre == "Handicap" or bas == "handicap":
        return "ASIAN_HANDICAP", francais
    if type_offre == "Over/Under" or bas.startswith("total"):
        equipe = _equipe_du_total(anglais, francais)
        if equipe:
            if equipe.casefold() == domicile.casefold():
                return "HOME_OVER_UNDER", francais
            if equipe.casefold() == exterieur.casefold():
                return "AWAY_OVER_UNDER", francais
            return None
        if "set" in bas and "game" not in bas:
            return "TOTAL_SETS", francais
        return "OVER_UNDER", francais
    if type_offre == "Match":
        return "MATCH_RESULT", francais
    return None


def _equipe_du_total(anglais: str, francais: str) -> str | None:
    for texte, separateur in ((anglais, " by "), (francais, " par ")):
        if separateur in texte.lower():
            return texte.split(separateur, 1)[1].strip() or None
    return None


def _score(libelle: str) -> str | None:
    m = re.match(r"^\s*(\d+)\s*[-:]\s*(\d+)\s*$", libelle or "")
    return f"{m.group(1)}-{m.group(2)}" if m else None


def marche_depuis(offre: dict, domicile: str, exterieur: str) -> dict | None:
    if not isinstance(offre, dict) or _exclu(offre):
        return None
    classe = _canonique(offre, domicile, exterieur)
    if not classe:
        return None
    canon, libelle = classe
    selections = []
    for issue in offre.get("outcomes") or []:
        if not isinstance(issue, dict) or issue.get("status") not in (None, "OPEN"):
            continue
        cote = _cote(issue.get("odds"))
        if cote is None:
            continue
        outcome = _ISSUES.get(str(issue.get("type") or ""))
        brut = str(issue.get("label") or issue.get("englishLabel") or "")
        if canon == "CORRECT_SCORE":
            brut = _score(brut) or ""
            outcome = outcome or "SCORE"
            if not brut:
                continue
        if canon == "HALF_TIME_FULL_TIME":
            outcome = outcome or "SCORE"
        if outcome is None:
            continue
        ligne = _ligne(issue.get("line")) if issue.get("line") is not None else None
        selections.append({"canonicalOutcome": outcome, "rawName": brut, "odds": cote, "line": ligne})
    if len(selections) < 2:
        return None
    duree = (offre.get("criterion") or {}).get("lifetime")
    return {
        "marketId": offre.get("id"),
        "canonicalMarket": canon,
        "rawName": libelle,
        "period": duree if isinstance(duree, str) else "FULL_TIME",
        "selections": selections,
    }


def evenement_depuis(event: dict, offres: list[dict]) -> dict | None:
    if not isinstance(event, dict):
        return None
    domicile, exterieur = event.get("homeName"), event.get("awayName")
    if not domicile or not exterieur or not event.get("id"):
        return None
    marches = []
    for offre in offres:
        if isinstance(offre, dict) and offre.get("eventId") not in (None, event.get("id")):
            continue
        marche = marche_depuis(offre, str(domicile), str(exterieur))
        if marche:
            marches.append(marche)
    return {
        "eventId": event.get("id"),
        "home": domicile,
        "away": exterieur,
        "league": event.get("group"),
        "startTime": event.get("start"),
        "markets": marches,
    }


def _a_venir(event: dict, maintenant: datetime, heures: float) -> bool:
    if event.get("state") != "NOT_STARTED":
        return False
    debut = _heure(event.get("start"))
    return bool(debut and maintenant < debut <= maintenant + timedelta(hours=heures))


def collecter(sports: set[str] | None = None, heures: float = 36, session=None,
              pause: tuple[float, float] = (1.0, 1.5),
              maintenant: datetime | None = None) -> tuple[list[dict], dict]:
    """Lignes déjà passées par ``pulsescore.traduire`` (bookmaker ``pmu``)."""
    maintenant = maintenant or datetime.now(timezone.utc)
    client = Client(session, pause)
    moment = maintenant.isoformat(timespec="seconds")
    lignes: list[dict] = []
    matchs = 0
    lectures = 0
    demandes = sports_demandes(sports)
    if not demandes:
        return [], {"ok": True, "erreurs": [], "requetes": 0, "matchs": 0}
    for terme, sport in demandes:
        doc = client.get(f"listView/{terme}/all/all/all/matches.json")
        if not doc:
            continue
        lectures += 1
        events = [e.get("event") for e in doc.get("events") or [] if isinstance(e, dict)]
        choisis = [e for e in events if isinstance(e, dict) and _a_venir(e, maintenant, heures)]
        matchs += len(choisis)
        for i in range(0, len(choisis), PAR_LOT):
            lot = choisis[i:i + PAR_LOT]
            ids = ",".join(str(e["id"]) for e in lot)
            offres_doc = client.get(f"betoffer/event/{ids}.json")
            offres = (offres_doc or {}).get("betOffers") if offres_doc else []
            if not isinstance(offres, list):
                offres = []
            for event in lot:
                ev = evenement_depuis(event, [o for o in offres if isinstance(o, dict)
                                              and o.get("eventId") == event.get("id")])
                if ev:
                    lignes += traduire(ev, "pmu", sport, moment)
    return lignes, {"ok": lectures > 0 or not client.erreurs, "erreurs": list(client.erreurs),
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
    ps = [l for l in pulse if isinstance(l, dict) and l.get("bookmaker") == "pmu"]
    di = [l for l in direct if isinstance(l, dict) and l.get("bookmaker") == "pmu"]
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
