"""Props joueurs NBA et NHL chez FanDuel, en référence seulement.

Matthieu ne peut pas parier chez FanDuel. Les lignes servent à comparer la
probabilité juste (marge retirée, même méthode que Pinnacle) à celle de
Pinnacle. Aucun sélecteur, aucun pari.

``SOURCE_FANDUEL`` vaut ``direct`` ou ``off`` (défaut : ``off``, pour que les
tests du cycle n'appellent pas le site). La collecte GitHub, depuis les
États-Unis, le passe à ``direct``.

Transport et lecture sont séparés : ``obtenir`` ne connaît pas les marchés,
``props_de`` ne fait aucun appel. L'horloge et la session sont injectables.
Un 403, un corps vide, un JSON illisible ou un délai devient un avertissement
court, sans en-tête, sans cookie et sans adresse.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from urllib.parse import urlencode

from cotes.joueurs import cle_joueur, stat_canonique
from cotes.marge import marge, proba_justes
from cotes.temps import instant_utc

_echeance = None
MODES = ("direct", "off")
AK = "FhMFpcPWXMeyZxOx"
HOTE = "https://sbapi.oh.sportsbook.fanduel.com/api"
PAGES = {"basket": "nba", "hockey": "nhl"}
LIGUES = {"basket": "NBA", "hockey": "NHL"}
ONGLETS = ("player-points", "popular")
ONGLETS_STATS = {
    "basket": ("player-rebounds", "player-assists", "player-threes"),
    "hockey": ("player-shots", "player-points", "player-goals"),
}
MATCHS_MAX = 12
DELAI_S = 20
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
_JEUX = {
    "spread", "moneyline", "money line", "total", "total points", "game total",
    "match total", "alternate spread", "alternate total", "point spread",
}
_PERIODE = re.compile(
    r"\b(1st|2nd|3rd|4th|first|second|third|fourth|qtr|quarter|half|period|periods)\b",
    re.I)
_STATS = {
    "threes": "ThreePoints", "3 pointers": "ThreePoints", "three pointers": "ThreePoints",
    "made threes": "ThreePoints", "shots": "ShotsOnGoal", "shots on goal": "ShotsOnGoal",
    "sog": "ShotsOnGoal",
}


def mode(environ=None) -> str:
    """``off`` si la variable est absente ou inconnue. ``direct`` interroge FanDuel."""
    env = os.environ if environ is None else environ
    valeur = str(env.get("SOURCE_FANDUEL", "off")).strip().lower()
    return valeur if valeur in MODES else "off"


def _heure(valeur):
    return instant_utc(valeur)


def _americaine(prix) -> float | None:
    try:
        p = float(prix)
    except (TypeError, ValueError):
        return None
    if p == 0:
        return None
    cote = 1 + p / 100.0 if p > 0 else 1 + 100.0 / abs(p)
    return cote if cote > 1 else None


def _nom(e: dict) -> str:
    return str(e.get("name") or e.get("eventName") or "").strip()


def _en_jeu(e: dict) -> bool:
    if e.get("inPlay") is True or e.get("inplay") is True:
        return True
    return str(e.get("status") or e.get("eventStatus") or "").upper() in {
        "LIVE", "IN_PLAY", "INPLAY", "STARTED"}


def _est_match(nom: str) -> bool:
    bas = nom.lower()
    if any(m in bas for m in ("winner", "outright", "champion", "mvp", "award", "futures")):
        return False
    if "(" in nom:
        return False
    return " @ " in nom or " v " in bas or " vs " in bas


def _equipes(nom: str) -> tuple[str, str] | None:
    """« Extérieur @ Domicile » (usage américain) ou « Domicile v Extérieur »."""
    if " @ " in nom:
        ext, dom = nom.split(" @ ", 1)
        return dom.strip(), ext.strip()
    bas = nom.lower()
    sep = " vs " if " vs " in bas else " v " if " v " in bas else ""
    if not sep:
        return None
    i = bas.index(sep.strip())
    return nom[:i].strip(), nom[i + len(sep.strip()):].strip()


def evenements_liste(doc, maintenant: datetime) -> list[dict]:
    """Matchs NBA ou NHL dont le coup d'envoi est encore devant nous."""
    if not isinstance(doc, dict):
        return []
    par: dict[str, dict] = {}

    def marcher(o):
        if isinstance(o, dict):
            eid = o.get("eventId")
            if eid is not None and (o.get("name") or o.get("eventName") or o.get("openDate")):
                cur = par.setdefault(str(eid), {})
                for k, v in o.items():
                    if v in (None, "", [], {}):
                        continue
                    if k not in cur or cur.get(k) in (None, "", [], {}):
                        cur[k] = v
                nouveau = _nom(o)
                if nouveau and ("@" in nouveau or " v " in nouveau.lower()):
                    ancien = _nom(cur)
                    if not ancien or ("(" in ancien and "(" not in nouveau):
                        cur["name"] = nouveau
            for v in o.values():
                marcher(v)
        elif isinstance(o, list):
            for v in o:
                marcher(v)

    marcher(doc)
    futurs = []
    for e in par.values():
        nom = _nom(e)
        if not _est_match(nom) or _en_jeu(e):
            continue
        debut = _heure(e.get("openDate") or e.get("startTime"))
        if debut is None or debut <= maintenant:
            continue
        equipes = _equipes(nom)
        if not equipes or equipes[0] == equipes[1]:
            continue
        e = dict(e)
        e["debut"] = debut
        e["domicile"], e["exterieur"] = equipes
        futurs.append(e)
    futurs.sort(key=lambda e: e["debut"])
    return futurs[:MATCHS_MAX]


def _stat(texte: str) -> str | None:
    bas = re.sub(r"[^a-z0-9]+", " ", (texte or "").lower()).strip()
    if bas in _STATS:
        return _STATS[bas]
    if _PERIODE.search(texte or ""):
        return None
    return stat_canonique(texte)


def _cote_de(runner: dict) -> str | None:
    n = str(runner.get("runnerName") or "").strip().lower()
    if n == "over" or n.startswith("over "):
        return "PLUS"
    if n == "under" or n.startswith("under "):
        return "MOINS"
    t = str((runner.get("result") or {}).get("type") or "").upper()
    if t in ("OVER", "UNDER"):
        return "PLUS" if t == "OVER" else "MOINS"
    return None


def _cote(runner: dict) -> float | None:
    w = runner.get("winRunnerOdds") or {}
    dec = (w.get("decimalDisplayOdds") or {}).get("decimalOdds")
    if dec is None:
        dec = ((w.get("trueOdds") or {}).get("decimalOdds") or {}).get("decimalOdds")
    if isinstance(dec, (int, float)) and not isinstance(dec, bool) and dec > 1:
        return float(dec)
    return _americaine((w.get("americanDisplayOdds") or {}).get("americanOdds"))


def _ligne(runner: dict, marche: dict):
    if runner.get("handicap") is not None:
        try:
            return float(runner["handicap"])
        except (TypeError, ValueError):
            return None
    if marche.get("handicap") is not None:
        try:
            return float(marche["handicap"])
        except (TypeError, ValueError):
            return None
    return None


def _marches(doc) -> list[dict]:
    bruts = (doc.get("attachments") or {}).get("markets") if isinstance(doc, dict) else None
    if isinstance(bruts, dict):
        return [m for m in bruts.values() if isinstance(m, dict)]
    if isinstance(bruts, list):
        return [m for m in bruts if isinstance(m, dict)]
    return []


def props_de(doc) -> tuple[list[dict], int]:
    """Paires plus/moins d'un joueur, et le nombre de marchés laissés de côté.

    Le second nombre est un compte : aucun nom n'est renvoyé pour un marché ignoré.
    """
    props, ignores = [], 0
    for m in _marches(doc):
        titre = str(m.get("marketName") or "").strip()
        if titre.lower() in _JEUX or " - " not in titre:
            continue
        joueur, stat_txt = [p.strip() for p in titre.split(" - ", 1)]
        joueur = re.sub(r"\s*\([^)]*\)\s*$", "", joueur).strip()
        stat = _stat(stat_txt)
        if not joueur or not stat or not cle_joueur(joueur):
            ignores += 1
            continue
        par_issue: dict[str, tuple[float, float]] = {}
        for r in m.get("runners") or []:
            if not isinstance(r, dict):
                continue
            issue = _cote_de(r)
            cote = _cote(r)
            ligne = _ligne(r, m)
            if issue and cote and ligne is not None and issue not in par_issue:
                par_issue[issue] = (ligne, cote)
        if set(par_issue) != {"PLUS", "MOINS"}:
            ignores += 1
            continue
        if round(par_issue["PLUS"][0], 2) != round(par_issue["MOINS"][0], 2):
            ignores += 1
            continue
        justes = proba_justes([par_issue["PLUS"][1], par_issue["MOINS"][1]], complet=True)
        if not justes:
            ignores += 1
            continue
        marge_paire = marge([par_issue["PLUS"][1], par_issue["MOINS"][1]])
        for issue, pi in zip(("PLUS", "MOINS"), justes):
            ligne, cote = par_issue[issue]
            props.append({
                "marketId": str(m.get("marketId") or titre),
                "joueur": joueur, "stat": stat, "ligne": ligne, "issue": issue,
                "cote": round(cote, 4), "proba_juste": round(pi, 6),
                "cote_juste": round(1 / pi, 4), "marge": round(marge_paire, 4),
            })
    return props, ignores


class _Reponse:
    def __init__(self, status: int, texte: str):
        self.status_code = status
        self.text = texte


def session_defaut():
    """Session sans bocal à cookies. Les en-têtes ne sont pas journalisés."""
    import urllib.error
    import urllib.request

    class Session:
        def get(self, url, timeout=DELAI_S):
            req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=timeout) as rep:
                    return _Reponse(getattr(rep, "status", 200), rep.read().decode("utf-8", "replace"))
            except urllib.error.HTTPError as e:
                return _Reponse(e.code, "")

    return Session()


def obtenir(session, url: str, timeout: float) -> tuple[int | None, dict | None, str | None]:
    """(code, document, avertissement). L'avertissement ne contient ni adresse ni en-tête."""
    try:
        rep = session.get(url, timeout=timeout)
    except Exception as e:
        nom = type(e).__name__
        raison = type(getattr(e, "reason", None)).__name__
        return None, None, "delai" if "Timeout" in nom or "Timeout" in raison else "reseau"
    code = getattr(rep, "status_code", None)
    if code is None:
        code = getattr(rep, "status", None)
    if code == 403:
        return 403, None, "HTTP 403"
    if code != 200:
        return code, None, f"HTTP {code}" if code else "reseau"
    if hasattr(rep, "json") and not getattr(rep, "text", None):
        try:
            doc = rep.json()
        except Exception:
            return 200, None, "JSON illisible"
        return (200, doc, None) if isinstance(doc, dict) else (200, None, "JSON illisible")
    texte = getattr(rep, "text", "") or ""
    if not str(texte).strip():
        return 200, None, "corps vide"
    try:
        doc = json.loads(texte)
    except (json.JSONDecodeError, TypeError):
        return 200, None, "JSON illisible"
    if not isinstance(doc, dict):
        return 200, None, "JSON illisible"
    return 200, doc, None


def _url_liste(page: str) -> str:
    return f"{HOTE}/content-managed-page?{urlencode({'page': 'CUSTOM', 'customPageId': page, '_ak': AK, 'timezone': 'America/New_York'})}"


def _url_match(event_id: str, onglet: str) -> str:
    return f"{HOTE}/event-page?{urlencode({'_ak': AK, 'eventId': event_id, 'tab': onglet})}"


def _timeout(plafond: float) -> float:
    echeance = _echeance
    if echeance is None or not hasattr(echeance, "timeout"):
        return plafond
    return echeance.timeout(plafond)


def _temps_restant() -> bool:
    return _echeance is None or _echeance.ok()


def collecter(sports: set[str] | None = None, heures: float = 36, session=None,
              maintenant: datetime | None = None, environ=None) -> tuple[list[dict], dict]:
    """Lignes ``JOUEUR:`` à venir. Une panne de transport ne lève pas."""
    try:
        return _collecter(sports, heures, session, maintenant, environ)
    except Exception as e:  # noqa: BLE001 - le cycle continue, les autres sources aussi
        return [], {"ok": False, "erreurs": [type(e).__name__], "avertissements": [type(e).__name__],
                    "requetes": 0, "matchs": 0, "props": 0, "ignores": 0}


def _collecter(sports, heures, session, maintenant, environ) -> tuple[list[dict], dict]:
    if mode(environ) == "off":
        return [], {"ok": True, "erreurs": [], "avertissements": [], "requetes": 0,
                    "matchs": 0, "props": 0, "ignores": 0, "mode": "off"}
    maintenant = maintenant or datetime.now(timezone.utc)
    if maintenant.tzinfo is None:
        maintenant = maintenant.replace(tzinfo=timezone.utc)
    voulu = set(sports) if sports is not None else set(PAGES)
    session = session or session_defaut()
    avertissements: list[str] = []
    requetes = 0
    ignores = 0
    lignes: list[dict] = []
    vus: set[tuple] = set()
    matchs = 0
    moment = maintenant.isoformat(timespec="seconds")

    def lire(url: str):
        nonlocal requetes
        if not _temps_restant():
            avertissements.append("budget")
            return None, "budget"
        requetes += 1
        _code, doc, err = obtenir(session, url, _timeout(DELAI_S))
        return doc, err

    for sport, page in PAGES.items():
        if sport not in voulu:
            continue
        doc, err = lire(_url_liste(page))
        if err or not isinstance(doc, dict):
            if err and err != "budget":
                avertissements.append(f"{page} {err}")
            if err == "budget":
                break
            continue
        for event in evenements_liste(doc, maintenant):
            fin = event["debut"]
            if (fin - maintenant).total_seconds() > heures * 3600:
                continue
            matchs += 1
            eid = str(event.get("eventId"))
            base = {
                "source": "fanduel", "bookmaker": "fanduel", "sport": sport,
                "ligue": LIGUES[sport], "match_id": f"fanduel|{eid}",
                "domicile": event["domicile"], "exterieur": event["exterieur"],
                "debut": event["debut"].isoformat(timespec="seconds"), "periode": "MATCH",
                "collecte": moment,
            }
            for i, onglet in enumerate((*ONGLETS, *ONGLETS_STATS.get(sport, ()))):
                page_match, err = lire(_url_match(eid, onglet))
                obligatoire = i < len(ONGLETS)
                if err == "budget":
                    break
                if err or not isinstance(page_match, dict):
                    if obligatoire and err:
                        avertissements.append(f"{onglet} {err}")
                    continue
                props, laisses = props_de(page_match)
                ignores += laisses
                if not props and not obligatoire:
                    continue
                for p in props:
                    cle = (eid, cle_joueur(p["joueur"]), p["stat"], round(p["ligne"], 2), p["issue"])
                    if cle in vus:
                        continue
                    vus.add(cle)
                    lignes.append({**base, "marche": f"JOUEUR:{p['stat']}", "ligne": p["ligne"],
                                   "issue": p["issue"], "joueur": p["joueur"], "cote": p["cote"],
                                   "proba_juste": p["proba_juste"], "cote_juste": p["cote_juste"],
                                   "marge_fanduel": p["marge"]})
            if not _temps_restant():
                break
    return lignes, {
        "ok": not any(a != "budget" for a in avertissements),
        "erreurs": [a for a in avertissements if a != "budget"][:8],
        "avertissements": avertissements[:8],
        "requetes": requetes, "matchs": matchs, "props": len(lignes), "ignores": ignores,
    }
