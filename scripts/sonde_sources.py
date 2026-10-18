"""Sonde en lecture seule : les sources répondent-elles depuis un runner GitHub ?

Chaque cible est un GET ou une poignée de messages WebSocket. Le journal contient
le statut, la taille, la latence et un court extrait sans jeton ni secret.
Winamax et Unibet sont d'abord lus avec ``requests`` ; un 403 est retenté avec
curl_cffi (impersonation Chrome).
"""
from __future__ import annotations

import base64
import json
import re
import socket
import ssl
import struct
import time
from urllib.parse import urlparse

import requests

UA = "Mozilla/5.0 (cotes-value sonde)"
PARAMS_KAMBI = "lang=fr_FR&market=FR&client_id=2&channel_id=1"
LISTE_PMU = (
    "https://eu1.offering-api.kambicdn.com/offering/v2018/pmusportsfr/"
    "listView/football/all/all/all/matches.json?" + PARAMS_KAMBI
)
SMARKETS = "https://api.smarkets.com/v3/events/?states=upcoming&limit=5&type=football_match"
POLYMARKET = "https://gamma-api.polymarket.com/events?active=true&closed=false&limit=3"
OLYBET = "wss://eu-swarm-reverse.betconstruct.com/"
WINAMAX_PAGE = "https://www.winamax.fr/paris-sportifs/sports/1"
WINAMAX_SOCK = "sports-eu-west-3.winamax.fr"
UNIBET = "https://www.unibet.fr/"
BETCLIC = (
    "https://offering.begmedia.com/web/offering.access.api/"
    "offering.access.api.MatchService/GetMatchesBySportWithNotifications"
)


def _extrait(texte: str, n: int = 160) -> str:
    """Extrait court, sans jeton ni URL authentifiée."""
    t = re.sub(r"(?i)(token|secret|api[_-]?key|authorization|hstoken)(['\"=: ]+)[^\s,'\"}]{6,}",
               r"\1\2[omis]", texte or "")
    t = re.sub(r"\s+", " ", t).strip()
    return t[:n]


def _mesure(nom: str, client: str, status, taille: int, debut: float, extrait: str,
            ok: bool, detail: str = "") -> dict:
    return {
        "endpoint": nom,
        "client": client,
        "status": status,
        "octets": taille,
        "latence_s": round(time.perf_counter() - debut, 2),
        "ok": ok,
        "extrait": _extrait(extrait),
        "detail": detail[:180],
    }


def _http(url: str, headers: dict | None = None, timeout: int = 25, data: bytes | None = None,
          stream: bool = False):
    h = {"User-Agent": UA, "Accept": "*/*", **(headers or {})}
    debut = time.perf_counter()
    if data is None:
        r = requests.get(url, headers=h, timeout=timeout, stream=stream)
    else:
        r = requests.post(url, headers=h, data=data, timeout=timeout, stream=stream)
    return r, debut


def _cffi(url: str, headers: dict | None = None, timeout: int = 25, data: bytes | None = None,
          limite: int | None = None, impersonate: str = "chrome"):
    from curl_cffi.requests import Session
    h = {"Accept": "*/*", **(headers or {})}
    debut = time.perf_counter()
    with Session(impersonate=impersonate) as s:
        if data is None:
            r = s.get(url, headers=h, timeout=timeout, stream=limite is not None)
        else:
            r = s.post(url, headers=h, data=data, timeout=timeout, stream=limite is not None)
        if limite is None:
            brut = r.content
        else:
            brut = _premiers_octets(r, limite)
            r.close()
    return r, debut, brut


def lire_http(nom: str, url: str, headers: dict | None = None, data: bytes | None = None,
              limite: int | None = None, repli_reseau: bool = False) -> tuple[dict, bytes | str | None]:
    """requests d'abord. curl_cffi si 403, ou si le réseau coupe et que ``repli_reseau`` est vrai."""
    raison = "403"
    try:
        r, debut = _http(url, headers, data=data, stream=limite is not None)
        try:
            brut = r.content if limite is None else _premiers_octets(r, limite)
            status = r.status_code
        finally:
            if limite is not None:
                r.close()
        if status != 403:
            texte = brut.decode("utf-8", "replace") if isinstance(brut, bytes) else ""
            return _mesure(nom, "requests", status, len(brut), debut, texte, 200 <= status < 300), brut
    except requests.RequestException as e:
        if not repli_reseau:
            return _mesure(nom, "requests", None, 0, time.perf_counter(), "", False, type(e).__name__), None
        raison = type(e).__name__
    try:
        r, debut, brut = _cffi(url, headers, data=data, limite=limite, impersonate="chrome")
        if r.status_code == 403:
            r, debut, brut = _cffi(url, headers, data=data, limite=limite, impersonate="safari")
            raison = f"{raison}, puis safari"
        texte = brut.decode("utf-8", "replace")
        return _mesure(nom, "curl_cffi", r.status_code, len(brut), debut, texte,
                       200 <= r.status_code < 300, f"repli après {raison}"), brut
    except Exception as e:  # noqa: BLE001
        return _mesure(nom, "curl_cffi", None, 0, time.perf_counter(), "", False,
                       f"repli après {raison} : {type(e).__name__}"), None


def _premiers_octets(reponse, limite: int) -> bytes:
    out = bytearray()
    for bloc in reponse.iter_content(8192):
        out += bloc
        if len(out) >= limite:
            break
    return bytes(out[:limite])


def pmu() -> list[dict]:
    ligne, brut = lire_http("PMU listView football", LISTE_PMU)
    lignes = [ligne]
    if not isinstance(brut, (bytes, str)) or not ligne["ok"]:
        lignes.append(_mesure("PMU betoffer/event", "—", None, 0, time.perf_counter(), "", False,
                              "liste indisponible"))
        return lignes
    try:
        doc = json.loads(brut)
    except ValueError:
        lignes.append(_mesure("PMU betoffer/event", "—", None, 0, time.perf_counter(), "", False, "JSON"))
        return lignes
    ident = None
    for ev in doc.get("events") or []:
        ident = ((ev.get("event") or {}).get("id"))
        if ident:
            break
    if not ident:
        lignes.append(_mesure("PMU betoffer/event", "—", None, 0, time.perf_counter(), "", False, "aucun id"))
        return lignes
    url = (f"https://eu1.offering-api.kambicdn.com/offering/v2018/pmusportsfr/"
           f"betoffer/event/{ident}.json?{PARAMS_KAMBI}")
    offre, _ = lire_http("PMU betoffer/event", url)
    offre["detail"] = f"id {ident}"
    lignes.append(offre)
    n = len(doc.get("events") or [])
    ligne["detail"] = f"{n} événements"
    ligne["extrait"] = _extrait(json.dumps({"events": n, "premier": ident}))
    return lignes


def _ws_stdlib(url: str, origin: str, messages: list[str], timeout: float = 20,
               lire_ouverture: bool = False, lectures_finale: int = 1) -> tuple[int, str]:
    """Poignée WebSocket minimale (RFC 6455), sans bibliothèque."""
    u = urlparse(url)
    hote, port = u.hostname, u.port or 443
    chemin = u.path or "/"
    if u.query:
        chemin += "?" + u.query
    cle = base64.b64encode(b"cotes-value-sonde").decode()
    ctx = ssl.create_default_context()
    brut = socket.create_connection((hote, port), timeout=timeout)
    tls = ctx.wrap_socket(brut, server_hostname=hote)
    tls.settimeout(timeout)
    requete = (
        f"GET {chemin} HTTP/1.1\r\nHost: {hote}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {cle}\r\nSec-WebSocket-Version: 13\r\nOrigin: {origin}\r\n"
        f"User-Agent: {UA}\r\n\r\n"
    )
    tls.sendall(requete.encode())
    entete = b""
    while b"\r\n\r\n" not in entete:
        bloc = tls.recv(4096)
        if not bloc:
            break
        entete += bloc
        if len(entete) > 16384:
            break
    statut = 0
    m = re.search(rb"HTTP/1\.[01] (\d+)", entete)
    if m:
        statut = int(m.group(1))
    if statut != 101:
        tls.close()
        return statut, entete[:200].decode("utf-8", "replace")
    reste = entete.split(b"\r\n\r\n", 1)[1]
    recus = []
    if lire_ouverture:
        morceau, reste = _ws_lire(tls, reste)
        recus.append(morceau)
    for i, msg in enumerate(messages):
        _ws_envoyer(tls, msg)
        n = lectures_finale if i == len(messages) - 1 else 1
        for _ in range(max(1, n)):
            morceau, reste = _ws_lire(tls, reste)
            recus.append(morceau)
            if not morceau:
                break
    tls.close()
    return 101, " | ".join(recus)[:500]


def _ws_cadre(tls, opcode: int, data: bytes) -> None:
    masque = b"\x11\x22\x33\x44"
    cadre = bytearray([0x80 | opcode])
    n = len(data)
    if n < 126:
        cadre.append(0x80 | n)
    else:
        cadre.append(0x80 | 126)
        cadre += struct.pack(">H", n)
    cadre += masque + bytes(b ^ masque[i % 4] for i, b in enumerate(data))
    tls.sendall(cadre)


def _ws_envoyer(tls, texte: str) -> None:
    _ws_cadre(tls, 0x1, texte.encode())


def _ws_lire(tls, reste: bytes = b"") -> tuple[str, bytes]:
    def prendre(n: int) -> bytes:
        nonlocal reste
        while len(reste) < n:
            bloc = tls.recv(max(4096, n - len(reste)))
            if not bloc:
                break
            reste += bloc
        out, reste = reste[:n], reste[n:]
        return out

    for _ in range(6):
        tete = prendre(2)
        if len(tete) < 2:
            return "", reste
        n = tete[1] & 0x7F
        if n == 126:
            n = struct.unpack(">H", prendre(2))[0]
        elif n == 127:
            n = struct.unpack(">Q", prendre(8))[0]
        n = min(n, 8000)
        if tete[1] & 0x80:
            masque = prendre(4)
            data = bytes(b ^ masque[i % 4] for i, b in enumerate(prendre(n)))
        else:
            data = prendre(n)
        opcode = tete[0] & 0x0F
        if opcode == 9:
            _ws_cadre(tls, 0xA, data)
            continue
        if opcode == 1:
            return data.decode("utf-8", "replace"), reste
        if opcode == 8:
            return "", reste
    return "", reste


def olybet() -> dict:
    session = json.dumps({"command": "request_session", "params": {
        "site_id": 18769041, "language": "fra", "source": 42}, "rid": "1"})
    football = json.dumps({"command": "get", "params": {
        "source": "betting", "what": {"game": ["id", "team1_name", "team2_name"]},
        "where": {"sport": {"alias": "Soccer"}, "game": {"type": {"@in": [0, 2]}}},
        "subscribe": False}, "rid": "2"})
    debut = time.perf_counter()
    try:
        statut, texte = _ws_stdlib(OLYBET, "https://sports.olybet.fr", [session, football])
        compact = texte.replace(" ", "")
        ok = statut == 101 and ('"code":0' in compact)
        if ok:
            return _mesure("OlyBet swarm football", "websocket", statut, len(texte), debut, texte, True)
        premier = _mesure("OlyBet swarm football", "websocket", statut, len(texte), debut, texte, False)
    except Exception as e:  # noqa: BLE001
        premier = _mesure("OlyBet swarm football", "websocket", None, 0, debut, "", False, type(e).__name__)
    if premier["ok"]:
        return premier
    debut = time.perf_counter()
    try:
        from curl_cffi.requests import Session
        with Session(impersonate="chrome") as s:
            ws = s.ws_connect(OLYBET, headers={"Origin": "https://sports.olybet.fr"}, timeout=20)
            ws.send_str(session)
            a = ws.recv_str()
            ws.send_str(football)
            b = ws.recv_str()
            ws.close()
        texte = a[:120] + " " + b[:120]
        return _mesure("OlyBet swarm football", "curl_cffi", 101, len(a) + len(b), debut, texte,
                       '"code":0' in a.replace(" ", "") or '"code": 0' in a,
                       f"repli après websocket {premier['status']} {premier['detail']}".strip())
    except Exception as e:  # noqa: BLE001
        return _mesure("OlyBet swarm football", "curl_cffi", premier["status"], 0, debut, "", False,
                       f"{premier['detail'] or 'echec simple'} ; repli {type(e).__name__}")


def winamax() -> list[dict]:
    page, brut = lire_http("Winamax page sports/1", WINAMAX_PAGE,
                           {"Accept": "text/html", "Accept-Language": "fr-FR"})
    lignes = [page]
    html = brut.decode("utf-8", "replace") if isinstance(brut, bytes) else ""
    a_etat = "PRELOADED_STATE" in html
    ident = None
    m = re.search(r'"matches"\s*:\s*\[\s*(\d+)', html)
    if m:
        ident = m.group(1)
    if ident is None:
        m = re.search(r"PRELOADED_STATE\s*=\s*(\{.*)", html)
        if m:
            try:
                doc, _ = json.JSONDecoder().raw_decode(m.group(1))
                matchs = doc.get("matches") if isinstance(doc, dict) else None
                if isinstance(matchs, dict) and matchs:
                    ident = next(iter(matchs))
                elif isinstance(matchs, list) and matchs:
                    ident = matchs[0]
            except ValueError:
                ident = None
    if ident is None:
        m = re.search(r'"matchId"\s*:\s*"?(\d+)', html)
        ident = m.group(1) if m else None
    page["detail"] = ("PRELOADED_STATE présent" if a_etat else "PRELOADED_STATE absent") + (
        f", match {ident}" if ident else ", aucun match")
    if not ident:
        lignes.append(_mesure("Winamax socket.io match", page["client"], None, 0, time.perf_counter(),
                              "", False, "aucun matchId"))
        return lignes
    message = '42["m",{"route":"match:%s"}]' % ident
    debut = time.perf_counter()
    try:
        statut, texte = _ws_stdlib(
            f"wss://{WINAMAX_SOCK}/uof-sports-server/socket.io/?EIO=4&transport=websocket",
            "https://www.winamax.fr", ["40", message], lire_ouverture=True, lectures_finale=3)
        ok = statut == 101 and ("42" in texte or "match" in texte.lower())
        ligne = _mesure("Winamax socket.io match", "websocket", statut, len(texte), debut,
                        texte, ok, f"match {ident}")
        if ok:
            lignes.append(ligne)
            return lignes
    except Exception as e:  # noqa: BLE001
        ligne = _mesure("Winamax socket.io match", "websocket", None, 0, debut, "", False, type(e).__name__)
    debut = time.perf_counter()
    try:
        from curl_cffi.requests import Session
        with Session(impersonate="chrome") as s:
            ws = s.ws_connect(
                f"wss://{WINAMAX_SOCK}/uof-sports-server/socket.io/?EIO=4&transport=websocket",
                headers={"Origin": "https://www.winamax.fr"}, timeout=20)
            ouvert = ws.recv_str()
            ws.send_str("40")
            ack = ws.recv_str()
            ws.send_str(message)
            corps = ws.recv_str()
            ws.close()
        texte = " ".join((ouvert, ack, corps))
        lignes.append(_mesure(
            "Winamax socket.io match", "curl_cffi", 101, len(texte), debut, texte,
            "42" in texte or "match" in texte.lower(),
            f"repli match {ident} après {ligne.get('status')} {ligne.get('detail')}".strip()))
    except Exception as e:  # noqa: BLE001
        lignes.append(_mesure("Winamax socket.io match", "curl_cffi", ligne.get("status"), 0, debut, "",
                              False, f"{ligne.get('detail')} ; repli {type(e).__name__}"))
    return lignes


def _etat_unibet(html: str) -> tuple[str | None, str | None]:
    m = re.search(r'<script[^>]*id="serverApp-state"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        return None, None
    try:
        doc = json.loads(m.group(1))
    except ValueError:
        return None, None
    jeton = (doc.get("HsToken") or {}).get("hsToken") if isinstance(doc.get("HsToken"), dict) else None
    noeud = None
    for item in (doc.get("Ept") or {}).get("ept") or []:
        if isinstance(item, dict) and item.get("code") == "FOOT" and isinstance(item.get("id"), int):
            noeud = f"p{item['id']}"
            break
    return jeton if isinstance(jeton, str) and jeton else None, noeud


def unibet() -> list[dict]:
    page, brut = lire_http("Unibet accueil", UNIBET, {"Accept": "text/html", "Accept-Language": "fr-FR"})
    html = brut.decode("utf-8", "replace") if isinstance(brut, bytes) else ""
    jeton, noeud = _etat_unibet(html)
    if jeton and not noeud:
        sport, brut_sport = lire_http("Unibet football", "https://www.unibet.fr/sport/football",
                                      {"Accept": "text/html", "Accept-Language": "fr-FR"})
        html_sport = brut_sport.decode("utf-8", "replace") if isinstance(brut_sport, bytes) else ""
        jeton2, noeud = _etat_unibet(html_sport)
        jeton = jeton2 or jeton
        page["detail"] = (f"jeton oui, nœud {noeud or 'absent'} "
                          f"(page sport {sport['status']}, {page['detail']})")
    else:
        page["detail"] = f"jeton {'oui' if jeton else 'non'}, nœud {noeud or 'absent'} ({page['detail']})"
    page["extrait"] = _extrait("page unibet, jeton omis")
    lignes = [page]
    if not jeton or not noeud:
        lignes.append(_mesure("Unibet lvs-api football", page["client"], None, 0, time.perf_counter(),
                              "", False, page["detail"]))
        return lignes
    url = f"https://www.unibet.fr/lvs-api/next/50/{noeud}"
    api, corps = lire_http("Unibet lvs-api football", url, {
        "X-LVS-HSToken": jeton, "Accept": "application/json", "Referer": UNIBET})
    texte = corps.decode("utf-8", "replace") if isinstance(corps, bytes) else ""
    api["extrait"] = _extrait(re.sub(r"[A-Za-z0-9+/_=-]{24,}", "[omis]", texte))
    api["detail"] = f"nœud {noeud}"
    lignes.append(api)
    return lignes


def _varint(n: int) -> bytes:
    out = bytearray()
    while n > 0x7F:
        out.append((n & 0x7F) | 0x80)
        n >>= 7
    out.append(n & 0x7F)
    return bytes(out)


def betclic() -> dict:
    corps = _varint((1 << 3) | 2) + _varint(8) + b"football"
    corps += _varint((2 << 3) | 2) + _varint(2) + b"fr"
    corps += _varint((4 << 3) | 0) + _varint(0)
    corps += _varint((5 << 3) | 0) + _varint(20)
    cadre = b"\x00" + struct.pack(">I", len(corps)) + corps
    entetes = {
        "Content-Type": "application/grpc-web+proto",
        "x-grpc-web": "1",
        "x-bg-ref-platform": "DESKTOP",
        "x-bg-regulation": "FR",
        "x-bg-ref-brand": "BETCLIC",
        "x-bg-ref-regulator-zone": "FR",
        "Accept": "application/grpc-web+proto",
        "Origin": "https://www.betclic.fr",
        "Referer": "https://www.betclic.fr/",
    }
    ligne, brut = lire_http("Betclic GetMatchesBySport", BETCLIC, entetes, data=cadre,
                            limite=8192, repli_reseau=True)
    if isinstance(brut, bytes) and brut:
        ligne["extrait"] = _extrait(repr(brut[:60]))
        ligne["ok"] = ligne["status"] == 200 and len(brut) > 5
        ligne["detail"] = f"première trame {len(brut)} o"
    return ligne


def controles() -> list[dict]:
    sm, brut = lire_http("Smarkets events", SMARKETS, {"Accept": "application/json"})
    if isinstance(brut, bytes) and sm["ok"]:
        try:
            n = len(json.loads(brut).get("events") or [])
            sm["detail"] = f"{n} événements"
        except ValueError:
            sm["detail"] = "JSON illisible"
    poly, brut = lire_http("Polymarket gamma events", POLYMARKET, {"Accept": "application/json"})
    if isinstance(brut, bytes) and poly["ok"]:
        try:
            doc = json.loads(brut)
            n = len(doc) if isinstance(doc, list) else 0
            poly["detail"] = f"{n} événements"
        except ValueError:
            poly["detail"] = "JSON illisible"
    return [sm, poly]


def main() -> int:
    lignes = []
    for bloc in (pmu, olybet, winamax, unibet, betclic, controles):
        try:
            r = bloc()
        except Exception as e:  # noqa: BLE001
            r = _mesure(bloc.__name__, "—", None, 0, time.perf_counter(), "", False, type(e).__name__)
        lignes.extend(r if isinstance(r, list) else [r])
    print("SONDE_TABLE_BEGIN")
    print(f"{'endpoint':<32} {'ok':<5} {'client':<12} {'status':<8} {'octets':>8} {'s':>6} detail")
    for l in lignes:
        print(f"{l['endpoint']:<32} {str(l['ok']):<5} {l['client']:<12} {str(l['status']):<8} "
              f"{l['octets']:>8} {l['latence_s']:>6} {l['detail']}")
    print("SONDE_TABLE_END")
    print(json.dumps(lignes, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
