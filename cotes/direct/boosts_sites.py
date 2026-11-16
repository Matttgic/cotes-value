"""Cotes boostées d'Unibet, NetBet et OlyBet, lues sans proxy (lecteurs repris du dépôt cotes-boostees).

Sonde du 16/11/2026 depuis GitHub (IP américaine, empreinte Chrome, scripts/sonde_boosts.py) : la page
https://www.unibet.fr/cotes-boostees (200), https://www.netbet.fr/super-cotes (200) et l'API swarm d'OlyBet répondent ;
Genybet et Betsson refusent (403, IP non française) : non lus (le dépôt cotes-boostees passe par un proxy payant).

Format commun (cotes/boosts.py) : {bookmaker, id, domicile, exterieur, debut, libelle, cote, cote_avant, mise_max,
titre, lu, lien, long_terme}.

- **Unibet** : état « serverApp-state » de la page ; ``BoostedBets.events`` (un événement par match ou par paquet, avec
  seulement le premier boost et le nombre total ``count``) ; la page de l'événement (``EventsDetail``) donne les autres.
  Intitulé « … (1,80 -> 2,10 / Mise max 25€) » : cote d'avant et mise maximale (25 € sans mention).
- **NetBet** : page /super-cotes (plateforme Sportnco), état ``window.__NUXT__`` (``netbet.etat_nuxt``) ; un boost par
  événement (« Lille (vs Arsenal) marque au moins 1 but »), issue « Oui » ; cote d'avant non publiée ; mise max 10 €.
- **OlyBet** : API swarm (site 18769041) : ``get_boosted_selections`` puis ``get`` sur ces matchs ; un boost = un
  « match » spécial « A - B : pari (13.10.2026) » ; cote d'avant non publiée ; gain net plafonné à 25 €.
"""
from __future__ import annotations

import json
import math
import re
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timezone

ENTETES = {"Accept-Language": "fr-FR,fr;q=0.9"}
RE_LONG_TERME = re.compile(r"\b\d{2}/\d{2}\b|saison|playoffs?|play-?in|division|conf[ée]rence|meilleur "
                           r"(?:marqueur|passeur|rebondeur|intercepteur|buteur)|vainqueur (?:de la|du) "
                           r"(?:ligue|championnat|coupe)|titre", re.I)


class PageInattendue(RuntimeError):
    pass


def _cote(v) -> float | None:
    try:
        c = round(float(str(v).replace(",", ".")), 3)
    except (TypeError, ValueError):
        return None
    return c if c > 1 and math.isfinite(c) else None


def _texte(v) -> str | None:
    return re.sub(r"\s+", " ", v).strip() or None if isinstance(v, str) else None


def _utc(valeur) -> str | None:
    try:
        if isinstance(valeur, (int, float)) and not isinstance(valeur, bool):
            t = datetime.fromtimestamp(valeur, timezone.utc)
        else:
            t = datetime.fromisoformat(str(valeur).replace("Z", "+00:00"))
            t = t if t.tzinfo else t.replace(tzinfo=timezone.utc)
        return t.astimezone(timezone.utc).isoformat(timespec="seconds")
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _equipes(match: str | None) -> tuple[str | None, str | None]:
    a, sep, b = (match or "").partition(" - ")
    return (a.strip() or None, b.strip() or None) if sep else (None, None)


def _boost(bookmaker, ident, match, debut, libelle, cote, avant, mise, titre, moment, lien) -> dict:
    dom, ext = _equipes(match)
    return {"bookmaker": bookmaker, "id": ident, "domicile": dom, "exterieur": ext, "debut": debut,
            "libelle": libelle, "cote": cote, "cote_avant": avant, "mise_max": mise, "titre": titre, "lu": moment,
            "lien": lien, "long_terme": bool(RE_LONG_TERME.search(f"{libelle} {titre or ''}"))}


# --------------------------------------------------------------------------- Unibet

UNIBET = "https://www.unibet.fr"
UNIBET_BOOSTS = UNIBET + "/cotes-boostees"
UNIBET_MISE = 25.0
RE_COTES = re.compile(r"(\d+[.,]\d+)\s*(?:->|→|&gt;)\s*(\d+[.,]\d+)")
RE_MISE = re.compile(r"mise\s*max\s*(?:de\s*)?(\d+(?:[.,]\d+)?)\s*€", re.I)
RE_PARENTHESE = re.compile(r"\s*/?\s*\((?:[^()]*?(?:->|→|mise\s*max)[^()]*)\)", re.I)


def etat_unibet(html: str) -> dict:
    m = re.search(r'<script[^>]*id="serverApp-state"[^>]*>(.*?)</script>', html or "", re.S)
    if not m:
        raise PageInattendue("état serverApp-state absent (page de blocage ou site modifié)")
    return json.loads(m.group(1))


def lien_evenement(html: str, event_id) -> str | None:
    m = re.search(rf'href="(/[^"]*/{re.escape(str(event_id))}/[^"]*)"', html or "")
    return UNIBET + m.group(1) if m else None


def _pari_unibet(desc: str) -> str | None:
    t = RE_PARENTHESE.sub("", desc or "")
    t = re.sub(r"^\s*(?:CB|Boost|Cote boostée)\s*[-:]?\s+", "", t, flags=re.I)
    t = re.sub(r"\s*-\s*\d+\s*Mins?\s*$", "", t, flags=re.I)        # « - 80 Mins » (durée du match)
    return _texte(t.strip(" -/"))


def boosts_unibet(e: dict, moment: str, lien: str | None = None) -> list[dict]:
    """Boosts d'un événement de la page (ou de sa page détaillée) : l'issue jouable est la seule non cachée."""
    a, b = (e.get("opponentA") or {}).get("label"), (e.get("opponentB") or {}).get("label")
    match = f"{a} - {b}" if a and b else _texte(e.get("description"))
    out = []
    for g in e.get("groupedMarkets") or []:
        for m in g.get("markets") or []:
            desc = m.get("description") or ""
            issues = [o for o in m.get("outcomes") or [] if not o.get("hidden") and not o.get("suspended")]
            if len(issues) != 1 or m.get("suspended"):
                continue
            cote = _cote(issues[0].get("price"))
            if cote is None:
                continue
            fl, mise = RE_COTES.search(desc), RE_MISE.search(desc)
            b_ = _boost("Unibet", f"unibet|{m.get('id')}|{issues[0].get('id')}", match, _utc(e.get("parsedStart")),
                        _pari_unibet(desc), cote, _cote(fl.group(1)) if fl else None,
                        float(mise.group(1).replace(",", ".")) if mise else UNIBET_MISE, _texte(desc), moment,
                        lien or UNIBET_BOOSTS)
            b_["long_terme"] = b_["long_terme"] or bool(RE_LONG_TERME.search(e.get("description") or ""))
            out.append(b_)
    return out


def lire_unibet(session, moment: str) -> list[dict]:
    """Page des boosts, puis la page de chaque événement qui a plus de boosts que ceux affichés."""
    r = session.get(UNIBET_BOOSTS, headers=ENTETES, timeout=20)
    if r.status_code != 200:
        raise PageInattendue(f"HTTP {r.status_code}")
    html = r.text
    out = []
    for e in (etat_unibet(html).get("BoostedBets") or {}).get("events") or []:
        lien = lien_evenement(html, e.get("id"))
        lus = boosts_unibet(e, moment, lien)
        affiches = sum(len(g.get("markets") or []) for g in e.get("groupedMarkets") or [])
        if int(e.get("count") or 0) > affiches and lien:
            rd = session.get(lien, headers=ENTETES, timeout=20)
            if rd.status_code == 200:
                detail = (etat_unibet(rd.text).get("EventsDetail") or {}).get("events") or []
                if detail:
                    lus = boosts_unibet({**e, **detail[0]}, moment, lien)
        out += lus
    return list({b["id"]: b for b in out}.values())


# --------------------------------------------------------------------------- NetBet (Sportnco)

NETBET = "https://www.netbet.fr"
NETBET_MISE = 10.0
RE_VS = re.compile(r"^(?P<a>.+?)\s*\(\s*(?:vs\.?|contre|v)\s+(?P<b>[^)]+)\)\s*(?P<reste>.*)$", re.I)
RE_PAIRE = re.compile(r"^(?P<a>[^/:()]{2,30}?)\s*/\s*(?P<b>[^/:()]{2,30}?)(?:\s*:\s*|\s+-\s+)\S", re.I)
RE_VS_FIN = re.compile(r"^(?P<a>[A-ZÀ-Ý][\w'.-]+(?: [A-ZÀ-Ý][\w'.-]+){0,2}) .+\(\s*(?:vs\.?|v|contre)\s+(?P<b>[^)]+)\)\s*\??$")
RE_VERBE = re.compile(r"\s+(?:marque|marquent|gagne|gagnent|ne perd|remporte|d[ée]cisif|buteur|et)\b", re.I)


def separer(label: str) -> str | None:
    """« Lille (vs Arsenal) marque au moins 1 but » -> « Lille - Arsenal » ; None si l'affiche n'est pas lisible."""
    m = RE_VS.match(label or "")
    if m:
        a = RE_VERBE.split(m.group("a"))[0].strip(" ?") or m.group("a").strip()
        return f"{a} - {m.group('b').strip()}"
    m = RE_PAIRE.match(label or "") or RE_VS_FIN.match(label or "")
    return f"{m.group('a').strip()} - {m.group('b').strip()}" if m else None


def evenements(etat: dict) -> list[dict]:
    """Tous les événements (avec paris) des composants de la page, sans doublon."""
    vus, out = set(), []

    def parcourir(o):
        if isinstance(o, dict):
            if "label" in o and "start" in o and ("bets" in o or "choices" in o):
                if o.get("id") not in vus:
                    vus.add(o.get("id"))
                    out.append(o)
                return
            for v in o.values():
                parcourir(v)
        elif isinstance(o, list):
            for v in o:
                parcourir(v)

    parcourir(((etat.get("state") or {}).get("UFWSClient") or {}).get("components") or {})
    return out


def competitions(etat: dict) -> list[dict]:
    """Compétitions Super Cotes annoncées par la page (adresse, nombre d'événements)."""
    comp = ((etat.get("state") or {}).get("UFWSClient") or {}).get("components") or {}
    liens = ((((comp.get("sport_page_all") or {}).get("data") or {}).get("topCompetitions") or {}).get("links")) or []
    return [x for x in liens if isinstance(x, dict) and str(x.get("url") or "").startswith("/super-cotes")]


def boosts_netbet(etat: dict, moment: str, maintenant: datetime) -> list[dict]:
    out = []
    for e in evenements(etat):
        debut = _utc(e.get("start"))
        if e.get("live") or e.get("becomeLive") or (debut and datetime.fromisoformat(debut) <= maintenant):
            continue
        label = _texte(e.get("label")) or ""
        url = str(e.get("url") or "")
        lien = NETBET + url if url.startswith("/") else NETBET + "/super-cotes"
        for b in e.get("bets") or ([e["choices"]] if e.get("choices") else []):
            for c in (b or {}).get("choices") or []:
                issue = str((c.get("actor") or {}).get("label") or "").strip()
                cote = _cote(c.get("odd"))
                if not cote or cote <= 1.01 or c.get("isEmptyChoice") or issue.lower() == "non" or c.get("status"):
                    continue
                libelle = label if issue.lower() in ("oui", "yes", "") else f"{label} — {issue}"
                out.append(_boost("NetBet", f"netbet|{e.get('id')}|{c.get('id')}", separer(label), debut, libelle,
                                  cote, None, NETBET_MISE, label, moment, lien))
    return out


def lire_netbet(session, moment: str, maintenant: datetime) -> list[dict]:
    from cotes.direct.netbet import etat_nuxt

    def page(url):
        r = session.get(url, headers=ENTETES, timeout=20)
        if r.status_code != 200:
            raise PageInattendue(f"HTTP {r.status_code} sur {url}")
        etat = etat_nuxt(r.text)
        if not isinstance(etat, dict):
            raise PageInattendue("état Nuxt illisible")
        return etat

    etat = page(NETBET + "/super-cotes")
    out = boosts_netbet(etat, moment, maintenant)
    annonces = competitions(etat)
    if sum(int(c.get("events") or 0) for c in annonces) > len(evenements(etat)):
        for c in annonces[:8]:
            out += boosts_netbet(page(NETBET + c["url"]), moment, maintenant)
    return list({b["id"]: b for b in out}.values())


# --------------------------------------------------------------------------- OlyBet (swarm)

SWARM = "wss://eu-swarm-reverse.betconstruct.com/"
OLYBET_ORIGINE = "https://sports.olybet.fr"
OLYBET_SITE = 18769041
OLYBET_GAIN_MAX = 25.0
RE_DATE_FIN = re.compile(r"\s*\(\d{1,2}[./]\d{1,2}[./]\d{2,4}\)\s*$")


def selections_olybet(reponse: dict) -> dict[int, set[int]]:
    """Réponse de get_boosted_selections -> {match: {issues boostées}}."""
    out: dict[int, set[int]] = {}
    for match, liste in (((reponse or {}).get("data") or {}).get("details") or {}).items():
        for s in liste if isinstance(liste, list) else [liste]:
            if isinstance(s, dict) and s.get("Id") is not None:
                out.setdefault(int(s.get("MatchId") or match), set()).add(int(s["Id"]))
    return out


def boosts_olybet(reponse_jeux: dict, choisis: dict[int, set[int]], moment: str, maintenant: datetime) -> list[dict]:
    """Un boost par issue boostée d'un match pas encore commencé ; mise max = 25 € de gain net."""
    sports = (((reponse_jeux or {}).get("data") or {}).get("data") or {}).get("sport") or {}
    out = []
    for sp in sports.values():
        for comp in (sp.get("competition") or {}).values():
            for g in (comp.get("game") or {}).values():
                ids = choisis.get(int(g.get("id") or 0), set())
                if g.get("is_started") or g.get("is_live") or int(g.get("start_ts") or 0) <= maintenant.timestamp():
                    continue
                for m in (g.get("market") or {}).values():
                    for e in (m.get("event") or {}).values():
                        cote = _cote(e.get("price"))
                        if int(e.get("id") or 0) not in ids or cote is None or g.get("is_blocked") \
                                or m.get("is_blocked") or e.get("is_blocked"):
                            continue
                        t = RE_DATE_FIN.sub("", _texte(m.get("name") or g.get("team1_name") or "") or "")
                        sep = re.match(r"^(.+?\S)\s*:\s+(.+)$", t)          # « A - B : pari » ou « A - B: pari »
                        match, pari = (sep.group(1).strip(), sep.group(2).strip()) if sep else (None, t)
                        if str(e.get("name") or "").strip().lower() not in ("oui", "yes", ""):
                            pari = f"{pari} — {e['name']}"
                        out.append(_boost("OlyBet", f"olybet|{g.get('id')}|{e.get('id')}", match,
                                          _utc(g.get("start_ts")), pari, cote, None,
                                          math.floor(OLYBET_GAIN_MAX / (cote - 1) * 100 + 1e-9) / 100, t, moment,
                                          "https://www.olybet.fr"))
    return out


def lire_olybet(moment: str, maintenant: datetime, delai: float = 15) -> list[dict]:
    from curl_cffi.requests import Session
    s = Session(impersonate="chrome")
    ws = s.ws_connect(SWARM, headers={"Origin": OLYBET_ORIGINE}, timeout=delai)
    try:
        def appel(rid: int, commande: str, params: dict) -> dict:
            ws.send_str(json.dumps({"command": commande, "params": params, "rid": str(rid)}))
            for _ in range(50):
                m = json.loads(ws.recv_str())
                if m.get("rid") == str(rid):
                    if m.get("code") not in (0, None):
                        raise PageInattendue(f"swarm {commande} : code {m.get('code')}")
                    return m
            raise PageInattendue(f"swarm {commande} : pas de réponse")
        appel(1, "request_session", {"site_id": OLYBET_SITE, "language": "fra", "source": 42})
        choisis = selections_olybet(appel(2, "get_boosted_selections", {}))
        if not choisis:
            return []
        jeux = appel(3, "get", {"source": "betting", "subscribe": False,
                                "what": {"sport": ["id", "name"], "competition": ["id", "name"], "game": [],
                                         "market": [], "event": []},
                                "where": {"game": {"id": {"@in": sorted(choisis)}}}})
        return boosts_olybet(jeux, choisis, moment, maintenant)
    finally:
        try:
            ws.close()
        finally:
            s.close()


# --------------------------------------------------------------------------- tous les sites

def lire_tous(maintenant: datetime | None = None, budget: float = 25.0,
              lecteurs: dict | None = None) -> tuple[list[dict], dict[str, str]]:
    """(boosts de Winamax, Unibet, NetBet et OlyBet, erreurs par bookmaker), lus en parallèle dans ``budget``
    secondes ; un site en panne n'empêche pas les autres. ``lecteurs`` remplace les lectures réseau (tests)."""
    maintenant = maintenant or datetime.now(timezone.utc)
    moment = maintenant.isoformat(timespec="seconds")
    if lecteurs is None:
        from curl_cffi.requests import Session

        from cotes.delai import Echeance
        from cotes.direct import winamax

        def _winamax():
            lus, erreurs = winamax.lire_boosts(echeance=Echeance(budget - 2), maintenant=maintenant)
            if not lus and erreurs:
                raise PageInattendue(erreurs[0])
            return lus
        lecteurs = {"Winamax": _winamax,
                    "Unibet": lambda: lire_unibet(Session(impersonate="chrome"), moment),
                    "NetBet": lambda: lire_netbet(Session(impersonate="chrome"), moment, maintenant),
                    "OlyBet": lambda: lire_olybet(moment, maintenant)}
    boosts, erreurs = [], {}
    pool = ThreadPoolExecutor(max_workers=len(lecteurs))
    futurs = {pool.submit(f): nom for nom, f in lecteurs.items()}
    finis, restants = wait(futurs, timeout=budget)
    for f in finis:
        try:
            boosts += f.result() or []
        except Exception as e:  # noqa: BLE001 - un site en panne n'arrête pas les autres
            erreurs[futurs[f]] = f"{type(e).__name__} : {str(e)[:120]}"
    for f in restants:
        erreurs[futurs[f]] = "budget dépassé"
    pool.shutdown(wait=False, cancel_futures=True)
    return boosts, erreurs
