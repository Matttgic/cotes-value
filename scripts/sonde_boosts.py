"""Sonde des cotes boostées : où et sous quelle forme chaque bookmaker français les publie. Rien n'est écrit.

Lance chaque lecteur direct (football, tennis, basket) avec un budget et note tout ce qu'il reçoit qui parle de
« boost » ou de « super cote » : documents JSON (HTTP et WebSocket, via ``json.loads``) et réponses brutes (gRPC
Betclic, pages NetBet). Pour chaque trouvaille : le chemin dans le document et un extrait borné. Plus quelques
adresses candidates (groupes Kambi de PMU, sport 100000 de Winamax). À lancer là où tourne la collecte
(workflow « Sonde cotes boostées »).
"""
from __future__ import annotations

import json
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

MOTIF = re.compile(r"boost|super\s*cote|cote\s*plus|enhanc|price\s*boost|odds\s*boost|surcot", re.I)
MOTIF_OCTETS = re.compile(rb"[Bb]oost|BOOST|[Ss]uper [Cc]ote")
SPORTS = {"football", "tennis", "basket"}
EXTRAIT = 1800
PAR_SOURCE = 14

ETAT = {"source": "?"}
DOCS: Counter = Counter()
TROUVES: dict[str, list[str]] = defaultdict(list)
CHEMINS: dict[str, Counter] = defaultdict(Counter)
BRUTS: dict[str, list[str]] = defaultdict(list)


def _court(x, n: int = EXTRAIT) -> str:
    try:
        s = json.dumps(x, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        s = repr(x)
    return s if len(s) <= n else s[:n] + "…"


def parcourir(obj, chemin: str, parent, source: str, profondeur: int = 0) -> None:
    if profondeur > 40:
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            ici = f"{chemin}.{k}"
            if isinstance(k, str) and MOTIF.search(k):
                noter(source, ici, obj)
            parcourir(v, ici, obj, source, profondeur + 1)
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:5000]):
            parcourir(v, f"{chemin}[{i if i < 3 else '*'}]", obj, source, profondeur + 1)
    elif isinstance(obj, str) and MOTIF.search(obj):
        noter(source, chemin, parent)


def noter(source: str, chemin: str, contexte) -> None:
    generique = re.sub(r"\[\d+\]", "[*]", re.sub(r"\.\d{3,}", ".<id>", chemin))
    CHEMINS[source][generique] += 1
    if CHEMINS[source][generique] <= 2 and len(TROUVES[source]) < PAR_SOURCE:
        TROUVES[source].append(f"{chemin}\n      {_court(contexte)}")


_LOADS = json.loads


def loads(s, *args, **kwargs):
    obj = _LOADS(s, *args, **kwargs)
    try:
        DOCS[ETAT["source"]] += 1
        texte = s if isinstance(s, str) else bytes(s).decode("utf-8", "ignore")
        if MOTIF.search(texte):
            parcourir(obj, "$", None, ETAT["source"])
    except Exception:  # noqa: BLE001 - la sonde ne casse jamais la lecture
        pass
    return obj


def octets(source: str, contenu: bytes | None) -> None:
    """Réponses non JSON (gRPC Betclic, HTML NetBet) : chaînes lisibles autour de « boost »."""
    if not contenu or len(BRUTS[source]) >= PAR_SOURCE:
        return
    for m in list(MOTIF_OCTETS.finditer(contenu))[:3]:
        a, b = max(0, m.start() - 260), min(len(contenu), m.end() + 420)
        lisible = re.sub(rb"[^\x20-\x7e\xc0-\xff\x80-\xbf]+", b" | ", contenu[a:b]).decode("utf-8", "ignore")
        BRUTS[source].append(lisible[:900])
        if len(BRUTS[source]) >= PAR_SOURCE:
            return


def installer() -> None:
    json.loads = loads
    import requests
    envoyer = requests.Session.send

    def send(self, req, **kw):
        r = envoyer(self, req, **kw)
        try:
            if not kw.get("stream") and "json" not in (r.headers.get("content-type") or ""):
                octets(ETAT["source"], r.content)
        except Exception:  # noqa: BLE001
            pass
        return r
    requests.Session.send = send
    try:
        from curl_cffi.requests import Session
        demande = Session.request

        def request(self, *a, **kw):
            r = demande(self, *a, **kw)
            try:
                if "json" not in (r.headers.get("content-type") or ""):
                    octets(ETAT["source"], r.content)
            except Exception:  # noqa: BLE001
                pass
            return r
        Session.request = request
    except ImportError:
        print("curl_cffi absent")


UNIBET_BOOSTS: list[str] = []
UNIBET_CLIENTS: list = []


def unibet_boosts(items: dict) -> None:
    """Événements « Cotes Boostées » d'une page Unibet, avec leurs marchés et issues."""
    from cotes.direct import unibet
    for k, ev in items.items():
        if not (isinstance(k, str) and k.startswith("e") and isinstance(ev, dict) and unibet._boost(ev)):
            continue
        if len(UNIBET_BOOSTS) >= 6:
            return
        marches = {mk: m for mk, m in items.items() if isinstance(m, dict) and str(mk).startswith("m")
                   and m.get("parent") == k}
        issues = [o for o in items.values() if isinstance(o, dict) and o.get("parent") in marches]
        UNIBET_BOOSTS.append(f"{_court(ev, 900)}\n      marchés {_court(marches, 1200)}\n      issues {_court(issues, 1200)}")


def installer_specifiques() -> None:
    from cotes.direct import betclic, unibet
    poster = betclic.Client.poster

    def poster_sonde(self, methode, charge):
        trame = poster(self, methode, charge)
        ETAT.setdefault("methodes", Counter())[methode] += 1
        if trame:
            octets("betclic:trames", trame)
        return trame
    betclic.Client.poster = poster_sonde
    lire = unibet.Client.get

    def get_sonde(self, chemin, params=None, session=None, espacer=None):
        if self not in UNIBET_CLIENTS:
            UNIBET_CLIENTS.append(self)
        doc = lire(self, chemin, params, session=session, espacer=espacer)
        if isinstance(doc, dict) and isinstance(doc.get("items"), dict):
            unibet_boosts(doc["items"])
        return doc
    unibet.Client.get = get_sonde


def unibet_rubrique() -> None:
    """La rubrique « Cotes Boostées » (chemin 58245556 vu le 16/11) lue directement."""
    if not UNIBET_CLIENTS:
        print("[unibet rubrique] pas de client")
        return
    client = UNIBET_CLIENTS[0]
    from cotes.delai import Echeance
    client.echeance = Echeance(30)
    for noeud in ("p58245556", "p58410983"):
        doc = client.get(f"next/50/{noeud}", {"lineId": "1", "originId": "3", "breakdownEventsIntoDays": "true",
                                             "showPromotions": "true"})
        items = doc.get("items") if isinstance(doc, dict) and isinstance(doc.get("items"), dict) else {}
        print(f"[unibet rubrique {noeud}] {len(items)} éléments : "
              + ", ".join(f"{k}:{(v or {}).get('desc') or (v or {}).get('a')}" for k, v in list(items.items())[:12]))
        evs = [k for k in items if str(k).startswith("e")]
        for k in evs[:3]:
            ev = items[k]
            marches = {mk: m for mk, m in items.items() if str(mk).startswith("m") and isinstance(m, dict)
                       and m.get("parent") == k}
            issues = [o for o in items.values() if isinstance(o, dict) and o.get("parent") in marches]
            print(f"  ÉVÉNEMENT {_court(ev, 900)}\n  MARCHÉS {_court(marches, 1500)}\n  ISSUES {_court(issues, 1500)}")


def winamax_liste() -> None:
    from cotes.delai import Echeance
    from cotes.direct import winamax
    client = winamax.Socket()
    client.echeance = Echeance(40)
    ETAT["source"] = "winamax:liste"
    doc = client.demander("sport:100000")
    client.fermer()
    if not isinstance(doc, dict):
        print(f"[winamax liste] rien {client.erreurs}")
        return
    odds = doc.get("odds") or {}
    outs = doc.get("outcomes") or {}
    for bet in list((doc.get("bets") or {}).values())[:40]:
        m = (doc.get("matches") or {}).get(str(bet.get("matchId"))) or {}
        libelles = [f'{(outs.get(str(o)) or {}).get("label")} @ {odds.get(str(o))}' for o in bet.get("outcomes") or []]
        print(f'  WINAMAX {m.get("title")} | début {m.get("matchStart")} | cat {m.get("categoryId")} tour '
              f'{m.get("tournamentId")} | {bet.get("betTitle")} | avant {bet.get("previousOdd")} | {libelles} '
              f'| marketId {bet.get("marketId")} betType {bet.get("betType")}')


def lancer(nom: str, module, budget: float, **kwargs) -> None:
    from cotes.delai import Echeance
    ETAT["source"] = nom
    t = time.monotonic()
    module._echeance = Echeance(budget)
    try:
        lignes, meta = module.collecter(sports=set(SPORTS), heures=36, echeance=Echeance(budget), **kwargs)
        print(f"[{nom}] {len(lignes)} lignes, {round(time.monotonic() - t)} s, erreurs={(meta or {}).get('erreurs')}")
    except Exception as e:  # noqa: BLE001
        print(f"[{nom}] échec : {type(e).__name__} {str(e)[:200]}")
    finally:
        module._echeance = None


def candidats() -> None:
    """Adresses qui pourraient porter les boosts hors des pages déjà lues."""
    import requests
    from cotes.direct import pmu, winamax
    ETAT["source"] = "pmu:group.json"
    try:
        r = requests.get(f"{pmu.BASE}/group.json", params=pmu.PARAMS, timeout=20, headers={"Accept": "application/json"})
        doc = r.json() if r.status_code == 200 else {}
        print(f"[pmu group.json] HTTP {r.status_code}")

        def groupes(g, chemin=""):
            nom = f"{chemin}/{g.get('termKey') or g.get('name')}"
            if MOTIF.search(str(g.get("name"))) or re.search(r"promo|sp[ée]cial|cote", str(g.get("name")), re.I):
                print(f"  groupe {g.get('id')} {nom} : {g.get('name')!r} sport={g.get('sport')} n={g.get('eventCount')}")
            for x in g.get("groups") or []:
                groupes(x, nom)
        groupes(doc.get("group") or {})
    except Exception as e:  # noqa: BLE001
        print(f"[pmu group.json] échec : {type(e).__name__}")
    from cotes.delai import Echeance
    client = winamax.Socket()
    client.echeance = Echeance(60)
    for ident in (100000, 100001, 800000):
        ETAT["source"] = f"winamax:sport:{ident}"
        try:
            doc = client.demander(f"sport:{ident}")
            if not isinstance(doc, dict):
                print(f"[winamax sport:{ident}] rien ({client.erreurs[-1:] if client.erreurs else ''})")
                continue
            tailles = {k: (len(v) if isinstance(v, (dict, list)) else type(v).__name__) for k, v in doc.items()}
            print(f"[winamax sport:{ident}] clés {tailles}")
            sports = doc.get("sports") if isinstance(doc.get("sports"), dict) else {}
            print("  sports : " + ", ".join(f"{k}={(v or {}).get('sportName')}" for k, v in list(sports.items())[:60]))
            for cle in ("matches", "bets", "outcomes", "tournaments", "categories"):
                bloc = doc.get(cle)
                if isinstance(bloc, dict) and bloc:
                    k, v = next(iter(bloc.items()))
                    print(f"  exemple {cle}[{k}] : {_court(v, 900)}")
            if isinstance(doc.get("odds"), dict):
                print(f"  odds : {_court(dict(list(doc['odds'].items())[:6]), 400)}")
        except Exception as e:  # noqa: BLE001
            print(f"[winamax sport:{ident}] échec : {type(e).__name__}")
    client.fermer()


def main() -> int:
    installer()
    installer_specifiques()
    from cotes.direct import betclic, unibet
    print(f"Sonde des cotes boostées, {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    winamax_liste()
    lancer("unibet", unibet, 90)
    for b in UNIBET_BOOSTS:
        print(f"  UNIBET BOOST {b}")
    unibet_rubrique()
    lancer("betclic", betclic, 90)
    print(f"[betclic] méthodes : {dict(ETAT.get('methodes') or {})}")
    for source in sorted(set(DOCS) | set(CHEMINS) | set(BRUTS)):
        print(f"\n=== {source} : {DOCS[source]} documents JSON, {sum(CHEMINS[source].values())} mentions")
        for chemin, n in CHEMINS[source].most_common(12):
            print(f"  {n:>5} × {chemin}")
        for t in TROUVES[source]:
            print(f"  · {t}")
        for b in BRUTS[source]:
            print(f"  ~ {b}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
