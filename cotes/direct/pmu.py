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

La liste ``all/all/all`` est plafonnée (le 18/10/2026 elle s'arrêtait vers 22 h
alors que l'horizon est 36 h). Un match isolé au-delà de l'horizon peut aussi
faire croire que la liste est complète et cacher des ligues. Sans réserve,
chaque compétition du ``group.json`` est relue quand la liste n'atteint pas
l'horizon. Avec une réserve (le cycle), les matchs à moins de 6 h sont relus
à chaque passage, et les feuilles de compétition tournent pour tous les sports :
le catalogue est mis en cache, quelques feuilles par cycle, deux lectures à la fois.
Un HTTP 429 arrête cette lecture. L'union couvre les 36 h.
"""
from __future__ import annotations

import os
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import requests

from cotes.correspondance import ressemblance
from cotes.direct.horizon import fusionner, tranche
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
# « Match » chez Kambi couvre aussi le premier but, le race-to et la manche :
# ces intitulés ne sont pas le résultat du match.
_PAS_RESULTAT = re.compile(
    r"first goal|premier but|first team to score|premi[eè]re [eé]quipe|"
    r"first to|premier [aà]|race to|"
    r"touchdown|"
    r"\bframes?\b|\bmanches?\b|"
    r"next goal|prochain but|winning margin|marge de victoire|"
    r"premier essai|first try|"
    r"à la fin du\s+\d+\s*e?\s*set|result at end of set",
    re.I)
_ORDINAUX = {"1": "1re", "2": "2e", "3": "3e", "4": "4e"}
_UNITES_PERIODE = {
    "periode": "période", "période": "période", "period": "période",
    "quart-temps": "quart-temps", "quarter": "quart-temps",
    "set": "set", "mi-temps": "mi-temps", "half": "mi-temps",
}
_PERIODE_APRES = re.compile(
    r"(?i)\b(p[eé]riode|period|quart-temps|quarter|set|mi-temps|half)\s*([1-4])\b")
_PERIODE_MOTS = (
    (re.compile(r"(?i)\bpremi[eè]re\s+p[eé]riode\b"), "1re période"),
    (re.compile(r"(?i)\bdeuxi[eè]me\s+p[eé]riode\b"), "2e période"),
    (re.compile(r"(?i)\btroisi[eè]me\s+p[eé]riode\b"), "3e période"),
)
_A_PERIODE = re.compile(
    r"(?i)\b(?:1re|2e|3e|4e)\s+(?:période|quart-temps|set|mi-temps)\b|"
    r"\b[1-4]\s*(?:er|ère|re|e|st|nd|rd|th)?\s*(?:mi-temps|half|période|periode|period|"
    r"quart-temps|quarter|set)\b|"
    r"\b(?:half time|halftime|mi-temps)\b")
_QUEUE_PERIODE = re.compile(
    r"(?i)\s*[-–]\s*(?:"
    r"1st half|2nd half|first half|second half|half time|"
    r"1(?:re|ère|ere)? mi-temps|2e mi-temps|mi-temps|"
    r"regular time|temps r[ée]glementaire|"
    r"including overtime(?: and penalty shootout)?|"
    r"prolongations?(?:\s+incluses)?(?:\s+et\s+\S+)*|"
    r"(?:premi[eè]re|deuxi[eè]me|troisi[eè]me)\s+p[eé]riode|"
    r"(?:p[eé]riode|period|quart-temps|quarter|set)\s*[1-4]|"
    r"[1-4](?:er|re|e|ère)?\s+(?:p[eé]riode|quart-temps|set|mi-temps)"
    r")\s*$")
MODES = ("pulsescore", "direct", "auto", "shadow")
_PRES_H = 6
_LOIN_EVENTS = 40
_LOIN_COMP = 8
_COMP_FRAIS_MIN = 45
_PAUSE_PARALLELE = (0.4, 0.6)
_MARGE_S = 3.0


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


_echeance = None


class Client:
    """GET espacés. Un 429 attend puis réessaie ; le corps n'est jamais journalisé."""

    def __init__(self, session=None, pause: tuple[float, float] = (1.0, 1.5), echeance=None):
        self.session = session or requests.Session()
        self.pause = pause
        self.echeance = echeance
        self.requetes = 0
        self.erreurs: list[str] = []
        self._premier = True
        self.stop_429 = False
        self._bloque = False
        self._verrou = threading.Lock()

    def _espacer(self) -> None:
        if self._premier:
            self._premier = False
            return
        bas, haut = self.pause
        _pause(haut if bas == haut else random.uniform(bas, haut))

    def _temps(self) -> bool:
        if self.echeance is None:
            return True
        reste = self.echeance.reste()
        if self.echeance.ok() and (reste is None or reste >= _MARGE_S):
            return True
        self._noter("budget")
        return False

    def get(self, chemin: str, session=None) -> dict | None:
        if self._bloque or not self._temps():
            return None
        url = f"{BASE}/{chemin}?{urlencode(PARAMS)}"
        dernier = "réseau"
        if self.echeance is None:
            delai = 30
        else:
            reste = self.echeance.reste() or 1
            delai = min(4.0, max(1.0, reste - 1))
        http = session or self.session
        for essai in range(4):
            if self._bloque or not self._temps():
                return None
            with self._verrou:
                if self._bloque:
                    return None
                self._espacer()
                self.requetes += 1
            try:
                r = http.get(url, timeout=delai, headers={"Accept": "application/json"})
            except requests.RequestException:
                dernier = "réseau"
                if essai < 3 and self._temps():
                    _pause(2 * (essai + 1))
                continue
            if r.status_code == 429 and self.stop_429:
                self._bloque = True
                self._noter("HTTP 429")
                return None
            if r.status_code in (429, 500, 502, 503, 504):
                dernier = f"HTTP {r.status_code}"
                if not self._temps():
                    return None
                attente = _nombre(r.headers.get("Retry-After")) if r.status_code == 429 else None
                pause = attente if attente is not None and 0 < attente <= 30 else 2 * (essai + 1)
                if self.echeance is not None and pause > (self.echeance.reste() or 0):
                    self._noter("budget")
                    return None
                _pause(pause)
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
        with self._verrou:
            if message not in self.erreurs and len(self.erreurs) < 30:
                self.erreurs.append(message)


def sports_demandes(sports: set[str] | None) -> list[tuple[str, str]]:
    """(termKey, sport interne), dans un ordre stable. ``None`` : tout le catalogue."""
    out = []
    for terme, interne in SPORTS.items():
        if sports is None or interne in sports:
            out.append((terme, interne))
    return out


def _chemin_liste(chemin: str) -> str:
    """Quatre segments avant ``matches.json`` : le sport, puis la compétition, complétés par ``all``."""
    parts = [p for p in str(chemin).split("/") if p]
    while len(parts) < 4:
        parts.append("all")
    return "listView/" + "/".join(parts) + "/matches.json"


def _feuilles(doc, terme: str) -> list[str]:
    """Compétitions feuilles de ``group.json`` pour un sport (``football/france/ligue_1``)."""
    if not isinstance(doc, dict):
        return []
    racine = doc.get("group") if isinstance(doc.get("group"), dict) else doc
    feuilles: list[str] = []

    def walk(noeud, chemin: str) -> None:
        if isinstance(noeud, list):
            for enfant in noeud:
                walk(enfant, chemin)
            return
        if not isinstance(noeud, dict):
            return
        cle = noeud.get("termKey")
        suivant = f"{chemin}/{cle}" if cle else chemin
        enfants = [g for g in (noeud.get("groups") or []) if isinstance(g, dict)]
        brut = suivant.strip("/")
        if (noeud.get("sport") and cle and noeud.get("eventCount") and not enfants
                and brut.startswith(terme + "/")):
            feuilles.append(brut)
        for enfant in enfants:
            walk(enfant, suivant)

    walk(racine, "")
    return feuilles


def _liste_courte(events: list[dict], maintenant: datetime, heures: float) -> bool:
    """Vrai si aucun match à venir n'atteint l'horizon : la liste globale est incomplète."""
    horizon = maintenant + timedelta(hours=heures)
    debuts = [_heure(e.get("start")) for e in events
              if isinstance(e, dict) and e.get("state") == "NOT_STARTED"]
    debuts = [d for d in debuts if d]
    return not debuts or max(debuts) < horizon


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


def _normaliser_periode(libelle: str) -> str:
    """« Période 2 » et « Première période » deviennent « 2e période » / « 1re période ».

    ``pulsescore.periode`` ne lit le numéro que lorsqu'il précède l'unité.
    """
    texte = libelle or ""
    for motif, remplacement in _PERIODE_MOTS:
        texte = motif.sub(remplacement, texte)

    def _ordre(m: re.Match) -> str:
        unite = _UNITES_PERIODE[m.group(1).lower()]
        return f"{_ORDINAUX[m.group(2)]} {unite}"

    return _PERIODE_APRES.sub(_ordre, texte)


def _avec_periode(francais: str, anglais: str) -> str:
    """Libellé français, complété par la période anglaise si elle n'y est pas."""
    base = _normaliser_periode(francais)
    if _A_PERIODE.search(base):
        return base
    autre = _normaliser_periode(anglais)
    if autre and _A_PERIODE.search(autre) and autre.casefold() not in base.casefold():
        return f"{base} - {autre}".strip(" -")
    return base


def _btts(anglais: str, francais: str) -> bool:
    """Les deux équipes marquent, pas « au moins 2 buts » ni un combiné."""
    if re.search(r"at least|au moins|\band\b", anglais) or re.search(r"au moins|\bet\b", francais):
        return False
    return "both teams to score" in anglais or "les deux équipes marquent" in francais


def _canonique(offre: dict, domicile: str, exterieur: str) -> tuple[str, str] | None:
    crit = offre.get("criterion") or {}
    anglais = str(crit.get("englishLabel") or "")
    francais = str(crit.get("label") or anglais)
    type_offre = str((offre.get("betOfferType") or {}).get("englishName") or "")
    bas = anglais.lower()
    fr = francais.lower()
    if _btts(bas, fr):
        return "BOTH_TEAMS_TO_SCORE", _avec_periode(francais, anglais)
    if type_offre == "Double Chance" or bas == "double chance":
        return "DOUBLE_CHANCE", _avec_periode(francais, anglais)
    if "draw no bet" in bas or "remboursé" in fr:
        return "DRAW_NO_BET", _avec_periode(francais, anglais)
    if type_offre in ("HT/FT", "Half Time/Full Time") or "half time/full time" in bas:
        return "HALF_TIME_FULL_TIME", francais
    if type_offre == "Correct Score" or bas == "correct score":
        return "CORRECT_SCORE", _avec_periode(francais, anglais)
    if type_offre == "3-Way Handicap":
        return "EUROPEAN_HANDICAP", _avec_periode(francais, anglais)
    if type_offre == "Handicap" or bas == "handicap":
        return "ASIAN_HANDICAP", _avec_periode(francais, anglais)
    if type_offre == "Over/Under" or bas.startswith("total"):
        equipe = _equipe_du_total(anglais, francais)
        if equipe:
            if equipe.casefold() == domicile.casefold():
                return "HOME_OVER_UNDER", _avec_periode(francais, anglais)
            if equipe.casefold() == exterieur.casefold():
                return "AWAY_OVER_UNDER", _avec_periode(francais, anglais)
            return None
        if "set" in bas and "game" not in bas:
            return "TOTAL_SETS", _avec_periode(francais, anglais)
        return "OVER_UNDER", _avec_periode(francais, anglais)
    if type_offre == "Match":
        if _PAS_RESULTAT.search(f"{anglais} {francais}"):
            return None
        return "MATCH_RESULT", _avec_periode(francais, anglais)
    return None


def _equipe_du_total(anglais: str, francais: str) -> str | None:
    for texte, separateur in ((anglais, " by "), (francais, " par ")):
        bas = texte.lower()
        idx = bas.find(separateur)
        if idx < 0:
            continue
        nom = _QUEUE_PERIODE.sub("", texte[idx + len(separateur):].strip()).strip(" -")
        return nom or None
    return None


def _priorite_libelle(ligne: dict) -> int:
    """Quand deux intitulés tombent sur la même clé, garder le temps réglementaire."""
    texte = (ligne.get("libelle") or "").lower()
    if "temps rég" in texte or "temps règ" in texte or "regular time" in texte:
        return 2
    if "prolong" in texte or "overtime" in texte or "tirs au but" in texte:
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


def _events_doc(doc) -> list[dict]:
    if not isinstance(doc, dict):
        return []
    out = []
    for wrap in doc.get("events") or []:
        ev = wrap.get("event") if isinstance(wrap, dict) else None
        if isinstance(ev, dict):
            out.append(ev)
    return out


def _lire_parallele(client: Client, chemins: list[str], concurrence: int) -> list:
    """Quelques GET à la fois. L'écart entre deux départs reste celui du client."""
    if not chemins:
        return []
    if concurrence <= 1 or len(chemins) == 1:
        return [client.get(chemin) for chemin in chemins]

    def un(chemin):
        if client._bloque or not client._temps():
            return None
        return client.get(chemin, session=requests.Session())

    with ThreadPoolExecutor(max_workers=min(concurrence, len(chemins))) as pool:
        return list(pool.map(un, chemins))


def _collecter_reserve(sports, heures, session, pause, maintenant, echeance, reserve, concurrence):
    """Proche à chaque cycle, lointain par tranches. La réserve renvoie l'union sur 36 h."""
    if echeance is None:
        echeance = _echeance
    largeur = max(1, int(concurrence or 1))
    client = Client(session, _PAUSE_PARALLELE if largeur > 1 else pause, echeance=echeance)
    client.stop_429 = True
    demandes = sports_demandes(sports)
    vide = {"ok": True, "erreurs": [], "requetes": 0, "matchs": 0, "reserve": reserve}
    if not demandes:
        return [], vide
    if echeance is not None and not echeance.ok():
        client._noter("budget")
        return [], {"ok": False, "erreurs": list(client.erreurs), "requetes": 0, "matchs": 0,
                    "reserve": reserve}
    moment = maintenant.isoformat(timespec="seconds")
    proche_limite = maintenant + timedelta(hours=min(_PRES_H, heures))
    comps = reserve.get("competitions") if isinstance(reserve.get("competitions"), dict) else {}
    comp_lu = _heure(reserve.get("comp_lu"))
    frais = comp_lu is not None and maintenant - comp_lu < timedelta(minutes=_COMP_FRAIS_MIN)
    events: list[tuple[str, dict]] = []
    courts = []
    demandes_lues = []
    for terme, sport in demandes:
        if client._bloque or not client._temps():
            break
        doc = client.get(f"listView/{terme}/all/all/all/matches.json")
        lus = _events_doc(doc)
        events.extend((sport, ev) for ev in lus)
        demandes_lues.append((terme, sport))
        if _liste_courte(lus, maintenant, heures):
            courts.append((terme, sport))
    feuilles = dict(comps)
    comp_lu_nouveau = reserve.get("comp_lu")
    # Un seul match très lointain dans la liste globale masque les ligues
    # absentes du plafond : on complète tous les sports, les listes courtes d'abord.
    manque = any(terme not in feuilles for terme, _sport in demandes_lues)
    if demandes_lues and (not frais or manque) and not client._bloque and client._temps():
        arbre = client.get("group.json") or {}
        for terme, _sport in demandes_lues:
            feuilles[terme] = _feuilles(arbre, terme)
        comp_lu_nouveau = moment
    ordre = courts + [couple for couple in demandes_lues if couple not in courts]
    file_comp = [(terme, sport, chemin)
                 for terme, sport in ordre
                 for chemin in (feuilles.get(terme) or [])]
    choisis_comp, curseur_comp = tranche(file_comp, int(reserve.get("curseur_comp") or 0), _LOIN_COMP)
    connus = {ev.get("id") for _sport, ev in events}
    comp_ids = set()
    docs_comp = _lire_parallele(client, [_chemin_liste(chemin) for _t, _s, chemin in choisis_comp], largeur)
    for (_terme, sport, _chemin), doc in zip(choisis_comp, docs_comp):
        for ev in _events_doc(doc):
            if ev.get("id") in connus:
                continue
            connus.add(ev.get("id"))
            comp_ids.add(ev.get("id"))
            events.append((sport, ev))
    proches, lointains, queue_comp = [], [], []
    for sport, ev in events:
        if not _a_venir(ev, maintenant, heures):
            continue
        debut = _heure(ev.get("start"))
        if debut and debut <= proche_limite:
            proches.append((sport, ev))
        elif ev.get("id") in comp_ids:
            queue_comp.append((sport, ev))
        else:
            lointains.append((sport, ev))
    proches.sort(key=lambda couple: str(couple[1].get("start") or ""))
    lointains.sort(key=lambda couple: str(couple[1].get("start") or ""))
    tranche_loin, curseur_loin = tranche(lointains, int(reserve.get("curseur_loin") or 0), _LOIN_EVENTS)
    choisis = proches + queue_comp + tranche_loin
    lots = []
    for i in range(0, len(choisis), PAR_LOT):
        lot = choisis[i:i + PAR_LOT]
        ids = ",".join(str(ev["id"]) for _sport, ev in lot if ev.get("id"))
        if ids:
            lots.append((lot, f"betoffer/event/{ids}.json"))
    if largeur > 1 and len(lots) > 1 and not client._bloque:
        with ThreadPoolExecutor(max_workers=min(largeur, len(lots))) as pool:
            offres_lots = list(pool.map(
                lambda item: (item[0], None if client._bloque or not client._temps()
                              else client.get(item[1], session=requests.Session())),
                lots))
    else:
        offres_lots = []
        for lot, chemin in lots:
            if client._bloque or not client._temps():
                break
            offres_lots.append((lot, client.get(chemin)))
    lignes: list[dict] = []
    lus = 0
    for lot, doc in offres_lots:
        offres = (doc or {}).get("betOffers") if isinstance(doc, dict) else []
        if not isinstance(offres, list):
            offres = []
        for sport, event in lot:
            lus += 1
            ev = evenement_depuis(event, [o for o in offres if isinstance(o, dict)
                                          and o.get("eventId") == event.get("id")])
            if ev:
                lignes += _retenir(traduire(ev, "pmu", sport, moment))
    fusion = fusionner(reserve.get("lignes") or [], lignes, maintenant, heures)
    reserve_out = {
        "competitions": feuilles,
        "comp_lu": comp_lu_nouveau,
        "curseur_comp": curseur_comp,
        "curseur_loin": curseur_loin,
        "lignes": fusion,
    }
    return fusion, {
        "ok": bool(fusion) or not client.erreurs,
        "erreurs": list(client.erreurs),
        "requetes": client.requetes,
        "matchs": len({l.get("match_id") for l in fusion}),
        "lus": lus,
        "reserve": reserve_out,
    }


def collecter(sports: set[str] | None = None, heures: float = 36, session=None,
              pause: tuple[float, float] = (1.0, 1.5),
              maintenant: datetime | None = None, echeance=None,
              reserve=None, concurrence: int = 1) -> tuple[list[dict], dict]:
    """Lignes déjà passées par ``pulsescore.traduire`` (bookmaker ``pmu``)."""
    maintenant = maintenant or datetime.now(timezone.utc)
    if reserve is not None:
        return _collecter_reserve(sports, heures, session, pause, maintenant, echeance,
                                  reserve if isinstance(reserve, dict) else {}, concurrence)
    if echeance is None:
        echeance = _echeance
    client = Client(session, pause, echeance=echeance)
    moment = maintenant.isoformat(timespec="seconds")
    lignes: list[dict] = []
    matchs = 0
    lectures = 0
    demandes = sports_demandes(sports)
    if not demandes:
        return [], {"ok": True, "erreurs": [], "requetes": 0, "matchs": 0}
    arbre = None
    for terme, sport in demandes:
        doc = client.get(f"listView/{terme}/all/all/all/matches.json")
        if not doc:
            continue
        lectures += 1
        events = [e.get("event") for e in doc.get("events") or [] if isinstance(e, dict)]
        if _liste_courte(events, maintenant, heures):
            if arbre is None:
                arbre = client.get("group.json") or {}
            connus = {e.get("id") for e in events if isinstance(e, dict)}
            for chemin in _feuilles(arbre, terme):
                if not client._temps():
                    break
                extra = client.get(_chemin_liste(chemin))
                if not extra:
                    continue
                for wrap in extra.get("events") or []:
                    ev = wrap.get("event") if isinstance(wrap, dict) else None
                    if isinstance(ev, dict) and ev.get("id") not in connus:
                        connus.add(ev.get("id"))
                        events.append(ev)
        choisis = [e for e in events if isinstance(e, dict) and _a_venir(e, maintenant, heures)]
        choisis.sort(key=lambda e: str(e.get("start") or ""))
        matchs += len(choisis)
        for i in range(0, len(choisis), PAR_LOT):
            if not client._temps():
                break
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
                    lignes += _retenir(traduire(ev, "pmu", sport, moment))
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
    associes = {mid for mid, _did in couples}
    manques = []
    for mid, ligne in matchs_ps.items():
        if mid in associes or len(manques) >= 20:
            continue
        manques.append({
            "sport": ligne.get("sport"),
            "domicile": ligne.get("domicile"),
            "exterieur": ligne.get("exterieur"),
            "ligue": ligne.get("ligue"),
            "debut": ligne.get("debut"),
        })
    return {
        "matchs_pulsescore": len(matchs_ps),
        "matchs_direct": len(matchs_di),
        "matchs_communs": len(couples),
        "manques": manques,
        "couverture": None if couverture is None else round(couverture, 4),
        "selections_communes": communs,
        "selections_egales": egaux,
        "accord_cotes": None if accord is None else round(accord, 4),
        "seuil_couverture": COUVERTURE_MIN,
        "seuil_accord": ACCORD_MIN,
        "pret_a_basculer": pret,
    }
