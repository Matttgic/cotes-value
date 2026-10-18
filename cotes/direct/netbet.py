"""Cotes NetBet.fr lues dans l'état Nuxt, au format d'événement PulseScore.

Les pages sont rendues côté serveur. ``window.__NUXT__`` est une fonction qui
reconstruit l'état : on l'évalue comme des données (objets, listes, chaînes),
pas en exécutant de script. ``curl_cffi`` est nécessaire, ``requests`` reçoit
souvent un HTTP 403. Le corps des pages et les jetons ne sont pas journalisés.

``SOURCE_NETBET`` vaut ``direct`` (défaut) ou ``off``. PulseScore n'a pas
netbet.fr (son identifiant « netbet » est netbet.com). Les lignes s'ajoutent
comme celles d'OlyBet. Un contrôle les compare à Pinnacle et au PMU.
"""
from __future__ import annotations

import os
import random
import re
import time
from datetime import datetime, timedelta, timezone

from cotes.correspondance import ressemblance
from cotes.pulsescore import traduire

ACCUEIL = "https://www.netbet.fr"
# chemin -> sport interne. Ski, biathlon, moto, voile, sport auto : hors liste.
PAGES = {
    "football": "/football",
    "tennis": "/tennis",
    "basket": "/basketball",
    "hockey": "/hockey-glace",
    "handball": "/handball",
    "volley": "/volleyball",
    "rugby": "/rugby",
    "football_americain": "/foot-us",
    "baseball": "/baseball",
    "boxe": "/boxe",
    "mma": "/mma",
    "golf": "/golf",
    "snooker": "/snooker",
    "tennis_de_table": "/tennis-de-table",
}
MODES = ("direct", "off")
ECART_RELATIF = 0.15
ECHANTILLON = 5
_MARGE_S = 3.0
_EXCLU = re.compile(
    r"corner|carton|\bcards?\b|booking|pair\s*/\s*impair|impair\s*/\s*pair|"
    r"buteur|\bscorer\b|\bjoueur\b|boost|garantie",
    re.I)
_HANDICAP = re.compile(r"^\(([+-]?\d+(?:[.,]\d+)?)\)\s*(.+)$")
_NOMBRE = re.compile(r"[-+]?\d+(?:[.,]\d+)?")
_echeance = None


def mode_source() -> str:
    """``direct`` si la variable est absente ou inconnue. ``off`` n'appelle pas le site."""
    valeur = os.environ.get("SOURCE_NETBET", "direct").strip().lower()
    return valeur if valeur in MODES else "direct"


def _pause(secondes: float) -> None:
    if secondes > 0:
        time.sleep(secondes)


def _page_chrome():
    from curl_cffi.requests import Session
    return Session(impersonate="chrome")


class _JS:
    """Lecteur de littéraux JavaScript produits par Nuxt (pas un interpréteur)."""

    def __init__(self, texte: str):
        self.s = texte
        self.n = len(texte)
        self.i = 0

    def _blanc(self) -> None:
        s, n = self.s, self.n
        i = self.i
        while i < n and s[i] in " \t\r\n":
            i += 1
        self.i = i

    def _mot(self, mot: str) -> bool:
        self._blanc()
        fin = self.i + len(mot)
        if self.s.startswith(mot, self.i) and not (fin < self.n and (self.s[fin].isalnum() or self.s[fin] in "_$")):
            self.i = fin
            return True
        return False

    def ident(self) -> str:
        self._blanc()
        j = self.i
        if j >= self.n or not (self.s[j].isalpha() or self.s[j] in "_$"):
            raise ValueError("identifiant")
        j += 1
        while j < self.n and (self.s[j].isalnum() or self.s[j] in "_$"):
            j += 1
        nom = self.s[self.i:j]
        self.i = j
        return nom

    def chaine(self) -> str:
        quote = self.s[self.i]
        i = self.i + 1
        s, n = self.s, self.n
        out = []
        while i < n:
            c = s[i]
            if c == "\\":
                e = s[i + 1]
                i += 2
                if e == "u":
                    out.append(chr(int(s[i:i + 4], 16)))
                    i += 4
                elif e == "n":
                    out.append("\n")
                elif e == "r":
                    out.append("\r")
                elif e == "t":
                    out.append("\t")
                else:
                    out.append(e)
                continue
            if c == quote:
                self.i = i + 1
                return "".join(out)
            out.append(c)
            i += 1
        raise ValueError("chaîne")

    def nombre(self):
        self._blanc()
        j = self.i
        if j < self.n and self.s[j] == "-":
            j += 1
        debut = j
        while j < self.n and self.s[j].isdigit():
            j += 1
        if j < self.n and self.s[j] == ".":
            j += 1
            while j < self.n and self.s[j].isdigit():
                j += 1
        if j == debut or (j == debut + 1 and self.s[debut] == "."):
            raise ValueError("nombre")
        texte = self.s[self.i:j]
        self.i = j
        return float(texte) if "." in texte else int(texte)

    def valeur(self, env: dict | None):
        self._blanc()
        if self.i >= self.n:
            raise ValueError("fin")
        c = self.s[self.i]
        if c == '"':
            return self.chaine()
        if c == "{":
            return self.objet(env)
        if c == "[":
            return self.tableau(env)
        if c == "-" or c == "." or c.isdigit():
            return self.nombre()
        if self._mot("null") or self._mot("undefined"):
            return None
        if self._mot("true"):
            return True
        if self._mot("false"):
            return False
        if self._mot("void"):
            self.nombre()
            return None
        nom = self.ident()
        self._blanc()
        if self.i < self.n and self.s[self.i] == "(":
            return self.appel(nom, env)
        if env is None or nom not in env:
            if env is None:
                return None
            raise ValueError("symbole")
        return env[nom]

    def appel(self, nom: str, env):
        """``Array(0)`` est le seul appel que Nuxt laisse dans les arguments."""
        self.i += 1
        args = []
        while True:
            self._blanc()
            if self.i < self.n and self.s[self.i] == ")":
                self.i += 1
                break
            args.append(self.valeur(env))
            self._blanc()
            if self.i < self.n and self.s[self.i] == ",":
                self.i += 1
                continue
            if self.i < self.n and self.s[self.i] == ")":
                self.i += 1
                break
            raise ValueError("appel")
        if nom == "Array":
            if len(args) == 1 and isinstance(args[0], int):
                return []
            return list(args)
        if env is None:
            return None
        raise ValueError("symbole")

    def objet(self, env):
        self.i += 1
        out = {}
        while True:
            self._blanc()
            if self.i < self.n and self.s[self.i] == "}":
                self.i += 1
                return out
            if self.s[self.i] == '"':
                cle = self.chaine()
            else:
                cle = self.ident()
            self._blanc()
            if self.i >= self.n or self.s[self.i] != ":":
                raise ValueError("objet")
            self.i += 1
            out[cle] = self.valeur(env)
            self._blanc()
            if self.i < self.n and self.s[self.i] == ",":
                self.i += 1
                continue
            if self.i < self.n and self.s[self.i] == "}":
                self.i += 1
                return out
            raise ValueError("objet")

    def tableau(self, env):
        self.i += 1
        out = []
        while True:
            self._blanc()
            if self.i < self.n and self.s[self.i] == "]":
                self.i += 1
                return out
            out.append(self.valeur(env))
            self._blanc()
            if self.i < self.n and self.s[self.i] == ",":
                self.i += 1
                continue
            if self.i < self.n and self.s[self.i] == "]":
                self.i += 1
                return out
            raise ValueError("tableau")

    def _jusqua_return(self) -> None:
        """Avance jusqu'après le mot ``return``, en ignorant les chaînes."""
        s, n = self.s, self.n
        i = self.i
        while i < n:
            c = s[i]
            if c in "\"'":
                i += 1
                while i < n:
                    if s[i] == "\\":
                        i += 2
                        continue
                    if s[i] == c:
                        i += 1
                        break
                    i += 1
                continue
            if s.startswith("return", i) and (i == 0 or not (s[i - 1].isalnum() or s[i - 1] in "_$")):
                fin = i + 6
                if fin >= n or not (s[fin].isalnum() or s[fin] in "_$"):
                    self.i = fin
                    return
            i += 1
        raise ValueError("return")


def evaluer(script: str):
    """``window.__NUXT__=(function(...){return ...})(...)`` -> état."""
    texte = script.strip()
    prefixe = "window.__NUXT__="
    if texte.startswith(prefixe):
        texte = texte[len(prefixe):]
    if not texte.startswith("(function("):
        raise ValueError("fonction")
    p = _JS(texte)
    p.i = len("(function(")
    params = []
    while True:
        p._blanc()
        if p.i < p.n and p.s[p.i] == ")":
            p.i += 1
            break
        params.append(p.ident())
        p._blanc()
        if p.i < p.n and p.s[p.i] == ",":
            p.i += 1
    p._blanc()
    if p.i >= p.n or p.s[p.i] != "{":
        raise ValueError("corps")
    p.i += 1
    p._jusqua_return()
    p._blanc()
    debut = p.i
    p.valeur(None)
    p._blanc()
    # (function(){return ...})(args) ou (function(){return ...}(args))
    if p.s.startswith("})(", p.i):
        p.i += 3
    elif p.s.startswith("}(", p.i):
        p.i += 2
    else:
        raise ValueError("appel")
    args = []
    while True:
        p._blanc()
        if p.i < p.n and p.s[p.i] == ")":
            break
        args.append(p.valeur({}))
        p._blanc()
        if p.i < p.n and p.s[p.i] == ",":
            p.i += 1
    env = {nom: args[i] if i < len(args) else None for i, nom in enumerate(params)}
    return _JS(texte[debut:]).valeur(env)


def etat_nuxt(html: str):
    """État de la page, ou None si le marqueur est absent ou illisible."""
    if not html or "window.__NUXT__=" not in html:
        return None
    debut = html.find("window.__NUXT__=")
    fin = html.find("</script>", debut)
    if fin < 0:
        return None
    try:
        return evaluer(html[debut:fin])
    except (ValueError, IndexError, OverflowError):
        return None


def _composants(etat) -> dict:
    try:
        comps = etat["state"]["UFWSClient"]["components"]
    except (TypeError, KeyError, IndexError):
        return {}
    return comps if isinstance(comps, dict) else {}


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


def _heure(valeur):
    try:
        t = datetime.fromisoformat(str(valeur).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if t.tzinfo is None:
        return None
    return t.astimezone(timezone.utc)


def _equipes(event: dict) -> tuple[str, str] | None:
    acteurs = [a for a in (event.get("actors") or []) if isinstance(a, dict)]
    home = next((a.get("label") for a in acteurs if a.get("type") == "home"), None)
    away = next((a.get("label") for a in acteurs if a.get("type") == "away"), None)
    if not home or not away:
        if len(acteurs) < 2:
            return None
        home, away = acteurs[0].get("label"), acteurs[1].get("label")
    if not home or not away:
        return None
    return str(home), str(away)


def _issue_nom(nom: str, home: str, away: str) -> str | None:
    bas = (nom or "").strip().casefold()
    if bas in {"n", "nul", "x", "match nul"}:
        return "DRAW"
    if bas == home.casefold():
        return "HOME"
    if bas == away.casefold():
        return "AWAY"
    return None


def _double(nom: str, home: str, away: str) -> str | None:
    parts = [p.strip() for p in re.split(r"\s+ou\s+", nom or "", flags=re.I)]
    if len(parts) != 2:
        return None

    def cote(part: str) -> str | None:
        if part.casefold() in {"n", "nul", "x"}:
            return "N"
        if part.casefold() == home.casefold():
            return "H"
        if part.casefold() == away.casefold():
            return "A"
        return None

    return {("H", "N"): "HOME_DRAW", ("N", "A"): "DRAW_AWAY", ("H", "A"): "HOME_AWAY"}.get(
        (cote(parts[0]), cote(parts[1])))


def marche_depuis(offre: dict, home: str, away: str) -> dict | None:
    if not isinstance(offre, dict):
        return None
    paris = offre.get("bets") or []
    if not paris or not isinstance(paris[0], dict):
        return None
    libelle = str(paris[0].get("label") or "")
    if not libelle or _EXCLU.search(libelle):
        return None
    style = str(offre.get("selection_order_type") or "")
    if style == "1x2":
        canon = "MATCH_RESULT"
    elif style == "over_under":
        canon = "OVER_UNDER"
    elif style == "yes_no" and "marquent" in libelle.casefold():
        canon = "BOTH_TEAMS_TO_SCORE"
    elif style == "double_chance":
        canon = "DOUBLE_CHANCE"
    elif style == "handicap_2ways":
        canon = "ASIAN_HANDICAP"
    else:
        return None
    selections = []
    for sel in paris[0].get("selections") or []:
        if not isinstance(sel, dict):
            continue
        cote = _cote(sel.get("odds") if sel.get("odds") is not None else sel.get("odd"))
        if cote is None:
            continue
        nom = str(sel.get("label") or "")
        if canon == "OVER_UNDER":
            bas = nom.casefold()
            code = "OVER" if bas.startswith("plus") else "UNDER" if bas.startswith("moins") else None
            ligne = _nombre(nom) or _nombre(libelle)
            if code is None or ligne is None:
                continue
            selections.append({"canonicalOutcome": code, "rawName": nom, "odds": cote, "line": ligne})
        elif canon == "BOTH_TEAMS_TO_SCORE":
            code = {"oui": "YES", "yes": "YES", "non": "NO", "no": "NO"}.get(nom.casefold())
            if code:
                selections.append({"canonicalOutcome": code, "rawName": nom, "odds": cote})
        elif canon == "DOUBLE_CHANCE":
            code = _double(nom, home, away)
            if code:
                selections.append({"canonicalOutcome": code, "rawName": nom, "odds": cote})
        elif canon == "ASIAN_HANDICAP":
            m = _HANDICAP.match(nom.strip())
            if not m:
                continue
            ligne = float(m.group(1).replace(",", "."))
            code = _issue_nom(m.group(2), home, away)
            if code not in {"HOME", "AWAY"}:
                continue
            selections.append({"canonicalOutcome": code, "rawName": nom, "odds": cote, "line": ligne})
        else:
            code = _issue_nom(nom, home, away)
            if code:
                selections.append({"canonicalOutcome": code, "rawName": nom, "odds": cote})
    if len(selections) < 2:
        return None
    return {
        "marketId": str(offre.get("order") or style),
        "canonicalMarket": canon,
        "rawName": libelle,
        "period": "FULL_TIME",
        "selections": selections,
    }


def evenements_de(etat, sport: str) -> list[dict]:
    comps = _composants(etat)
    trouves = []
    blocs = []
    une = comps.get("sport_page_featured") or {}
    data = une.get("data") if isinstance(une, dict) else {}
    if isinstance(data, dict):
        for cle in ("last_minutes", "top_bets"):
            bloc = data.get(cle) or {}
            if isinstance(bloc, dict) and isinstance(bloc.get("events"), list):
                blocs.append(bloc["events"])
    liste = comps.get("prematch_event_list") or {}
    data = liste.get("data") if isinstance(liste, dict) else {}
    if isinstance(data, dict) and isinstance(data.get("events"), list):
        blocs.append(data["events"])
    vus = set()
    for events in blocs:
        for event in events:
            if not isinstance(event, dict) or event.get("state") == "live" or event.get("type") == "live":
                continue
            if event.get("id") in vus:
                continue
            equipes = _equipes(event)
            if not equipes:
                continue
            vus.add(event.get("id"))
            marches = []
            for offre in event.get("markets") or []:
                marche = marche_depuis(offre, *equipes)
                if marche:
                    marches.append(marche)
            if not marches:
                continue
            trouves.append({
                "eventId": event.get("id"),
                "home": equipes[0],
                "away": equipes[1],
                "league": event.get("competitionLabel"),
                "start": event.get("start"),
                "sport": sport,
                "markets": marches,
            })
    return trouves


def _liens(etat) -> list[str]:
    comps = _composants(etat)
    page = comps.get("sport_page_all") or {}
    data = page.get("data") if isinstance(page, dict) else {}
    if not isinstance(data, dict):
        return []
    liens = []
    top = (data.get("topCompetitions") or {}).get("links") or []
    cats = (data.get("azCategories") or {}).get("categories") or []
    for item in list(top):
        if isinstance(item, dict):
            liens.append(item)
    for cat in cats if isinstance(cats, list) else []:
        if isinstance(cat, dict):
            liens.extend(x for x in (cat.get("links") or []) if isinstance(x, dict))
    urls = []
    vus = set()
    for item in sorted(liens, key=lambda x: -(x.get("events") or 0)):
        url = item.get("url")
        if not isinstance(url, str) or not url.startswith("/") or url in vus:
            continue
        if not item.get("events"):
            continue
        vus.add(url)
        urls.append(url)
    return urls


class Client:
    def __init__(self, session=None, pause: tuple[float, float] = (0.25, 0.45), echeance=None):
        self.session = session
        self.pause = pause
        self.echeance = echeance
        self.requetes = 0
        self.erreurs: list[str] = []
        self._premier = True

    def _noter(self, message: str) -> None:
        if message not in self.erreurs and len(self.erreurs) < 20:
            self.erreurs.append(message)

    def _delai(self) -> float | None:
        if self.echeance is None:
            return 20.0
        reste = self.echeance.reste()
        if reste is None:
            return 20.0
        if reste < _MARGE_S or not self.echeance.ok():
            self._noter("budget")
            return None
        return min(12.0, max(1.0, reste - 1))

    def lire(self, chemin: str) -> str | None:
        delai = self._delai()
        if delai is None:
            return None
        if self._premier:
            self._premier = False
        else:
            bas, haut = self.pause
            _pause(haut if bas == haut else random.uniform(bas, haut))
            if self._delai() is None:
                return None
        self.requetes += 1
        url = chemin if chemin.startswith("http") else ACCUEIL + chemin
        try:
            if self.session is None:
                self.session = _page_chrome()
            r = self.session.get(url, timeout=delai, headers={
                "Accept": "text/html", "Accept-Language": "fr-FR", "Referer": ACCUEIL + "/"})
        except Exception:
            # Le message d'erreur de curl peut reprendre l'URL ou un jeton : on ne le garde pas.
            self._noter("réseau")
            return None
        code = getattr(r, "status_code", None)
        if code == 429:
            self._noter("HTTP 429")
            return None
        if code != 200:
            self._noter(f"HTTP {code}")
            return None
        return getattr(r, "text", "") or ""


def collecter(sports: set[str] | None = None, heures: float = 36, session=None,
              pause: tuple[float, float] = (0.25, 0.45),
              maintenant: datetime | None = None, echeance=None) -> tuple[list[dict], dict]:
    """Lignes déjà passées par ``pulsescore.traduire`` (bookmaker ``netbet``)."""
    maintenant = maintenant or datetime.now(timezone.utc)
    if echeance is None:
        echeance = _echeance
    voulu = [s for s in PAGES if sports is None or s in sports]
    if not voulu:
        return [], {"ok": True, "erreurs": [], "requetes": 0, "matchs": 0}
    client = Client(session, pause, echeance)
    if echeance is not None and not echeance.ok():
        client._noter("budget")
        return [], {"ok": False, "erreurs": list(client.erreurs), "requetes": 0, "matchs": 0}
    files: list[tuple[str, list[str]]] = []
    bruts: list[dict] = []
    for sport in voulu:
        if echeance is not None and not echeance.ok():
            client._noter("budget")
            break
        html = client.lire(PAGES[sport])
        if html is None:
            if "HTTP 429" in client.erreurs:
                break
            continue
        etat = etat_nuxt(html)
        if etat is None:
            client._noter("état illisible")
            continue
        bruts.extend(evenements_de(etat, sport))
        files.append((sport, _liens(etat)))
    while any(urls for _, urls in files):
        if echeance is not None and not echeance.ok():
            client._noter("budget")
            break
        progres = False
        for sport, urls in files:
            if not urls:
                continue
            if echeance is not None and not echeance.ok():
                client._noter("budget")
                break
            chemin = urls.pop(0)
            progres = True
            html = client.lire(chemin)
            if html is None:
                if "HTTP 429" in client.erreurs:
                    break
                continue
            etat = etat_nuxt(html)
            if etat is None:
                client._noter("état illisible")
                continue
            bruts.extend(evenements_de(etat, sport))
        if not progres or "HTTP 429" in client.erreurs:
            break
    horizon = maintenant + timedelta(hours=heures)
    moment = maintenant.isoformat(timespec="seconds")
    lignes: list[dict] = []
    matchs = 0
    vus = set()
    for event in bruts:
        if event["eventId"] in vus:
            continue
        debut = _heure(event.get("start"))
        if not debut or not (maintenant < debut <= horizon):
            continue
        vus.add(event["eventId"])
        matchs += 1
        ev = {
            "eventId": event["eventId"],
            "home": event["home"],
            "away": event["away"],
            "league": event.get("league"),
            "startTime": debut.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "markets": event["markets"],
        }
        lignes += traduire(ev, "netbet", event["sport"], moment)
    return lignes, {
        "ok": not client.erreurs or bool(lignes),
        "erreurs": list(client.erreurs),
        "requetes": client.requetes,
        "matchs": matchs,
    }


def controle_prix(netbet: list[dict], references: list[dict], plafond: int = ECHANTILLON) -> dict:
    """Quelques 1N2 football comparés à PMU et Pinnacle. Un écart relatif > 15 % est signalé."""
    cibles = []
    vus = set()
    for ligne in netbet:
        if not (ligne.get("sport") == "football" and ligne.get("marche") == "RESULTAT_1N2"
                and ligne.get("issue") == "DOM" and ligne.get("periode") == "MATCH"):
            continue
        if ligne.get("match_id") in vus:
            continue
        vus.add(ligne.get("match_id"))
        cibles.append(ligne)
        if len(cibles) >= plafond:
            break

    def nom_ref(ligne: dict) -> str | None:
        if ligne.get("bookmaker") == "pmu" or ligne.get("source") == "PMU":
            return "PMU"
        if ligne.get("source") == "pinnacle":
            return "Pinnacle"
        return None

    refs = [l for l in references if nom_ref(l) and l.get("sport") == "football"
            and l.get("marche") == "RESULTAT_1N2" and l.get("issue") == "DOM"
            and l.get("periode") == "MATCH"]
    comparaisons = []
    for ligne in cibles:
        vues = set()
        for ref in refs:
            nom = nom_ref(ref)
            if nom in vues:
                continue
            ta, tb = _heure(ligne.get("debut")), _heure(ref.get("debut"))
            if not ta or not tb or abs((ta - tb).total_seconds()) > 90 * 60:
                continue
            if min(ressemblance(ligne.get("domicile"), ref.get("domicile")),
                   ressemblance(ligne.get("exterieur"), ref.get("exterieur"))) < 0.85:
                continue
            vues.add(nom)
            co, cr = _nombre(ligne.get("cote")), _nombre(ref.get("cote"))
            if not co or not cr:
                continue
            ecart = abs(co / cr - 1)
            comparaisons.append({
                "match": f"{ligne.get('domicile')} – {ligne.get('exterieur')}",
                "source": nom,
                "cote_netbet": round(co, 3),
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
