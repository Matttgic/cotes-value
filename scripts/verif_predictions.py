"""Vérification : nos lectures directes Polymarket et Kalshi = les prix fournis par PulseScore ?

1. Lit quelques pages PulseScore (Polymarket et Kalshi), environ 6 requêtes.
2. Relit aussitôt les mêmes marchés via les API officielles (identifiants identiques :
   conditionId Polymarket, ticker Kalshi), comme le font nos collecteurs.
3. Compare le meilleur achat, la meilleure vente et le prix milieu de chaque marché ouvert.

Sortie : verif/rapport.json. Usage : PULSESCORE_KEY=... python scripts/verif_predictions.py
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

PS = "https://api.pulsescore.net/api"
GAMMA = "https://gamma-api.polymarket.com"
KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
PAGES = {"polymarket": [("soccer", 1), ("soccer", 2), ("tennis", 1)],
         "kalshi": [("soccer", 1), ("tennis", 1), ("basketball", 1)]}
OUT = Path("verif")


def _liste(x):
    return json.loads(x) if isinstance(x, str) else (x or [])


def pulsescore(session: requests.Session) -> dict[str, list[dict]]:
    out = {"polymarket": [], "kalshi": []}
    for source, pages in PAGES.items():
        for sport, page in pages:
            r = session.get(f"{PS}/{source}/{sport}/events", params={"page": page, "limit": 30}, timeout=60)
            time.sleep(1.2)
            if r.status_code != 200:
                print(source, sport, page, r.status_code, r.text[:200])
                continue
            for e in r.json().get("events", []):
                for m in e.get("markets") or []:
                    out[source].append({"evenement": f'{e.get("home") or ""} - {e.get("away") or ""}'.strip(" -")
                                        or e.get("league"), "sport": sport, "marche": m.get("rawName"),
                                        "id": m.get("marketId"), "selections": m.get("selections") or []})
    return out


def polymarket_direct(ids: list[str]) -> dict[str, dict]:
    res = {}
    for i in range(0, len(ids), 40):
        lot = ids[i:i + 40]
        r = requests.get(f"{GAMMA}/markets", params=[("condition_ids", c) for c in lot] + [("limit", 100)], timeout=60)
        if r.status_code == 200:
            for m in r.json():
                res[m.get("conditionId")] = m
    return res


def kalshi_direct(tickers: list[str]) -> dict[str, dict]:
    res = {}
    for i in range(0, len(tickers), 100):
        r = requests.get(f"{KALSHI}/markets", params={"tickers": ",".join(tickers[i:i + 100])}, timeout=60)
        if r.status_code == 200:
            for m in r.json().get("markets") or []:
                res[m.get("ticker")] = m
    return res


def comparer(a_ps: tuple[float, float], a_dir: tuple[float, float], base: dict) -> dict:
    (b1, v1), (b2, v2) = a_ps, a_dir
    return {**base, "achat_pulsescore": b1, "vente_pulsescore": v1, "achat_direct": b2, "vente_direct": v2,
            "identique": abs(b1 - b2) < 1e-9 and abs(v1 - v2) < 1e-9,
            "ecart_milieu_pts": round(100 * abs((b1 + v1) / 2 - (b2 + v2) / 2), 3)}


def main() -> int:
    key = os.environ.get("PULSESCORE_KEY", "").strip()
    if not key:
        print("PULSESCORE_KEY manquante", file=sys.stderr)
        return 1
    OUT.mkdir(exist_ok=True)
    s = requests.Session()
    s.headers.update({"X-Secret": key, "Accept-Encoding": "gzip"})
    t0 = datetime.now(timezone.utc)
    ps = pulsescore(s)
    t1 = datetime.now(timezone.utc)
    pm = polymarket_direct([m["id"] for m in ps["polymarket"] if str(m["id"]).startswith("0x")])
    ks = kalshi_direct([m["id"] for m in ps["kalshi"] if m["id"]])
    t2 = datetime.now(timezone.utc)

    lignes = []
    for m in ps["polymarket"]:
        d = pm.get(m["id"])
        if not d or not d.get("acceptingOrders") or d.get("closed") or d.get("bestBid") is None:
            continue
        jetons = _liste(d.get("clobTokenIds"))
        sel = next((x for x in m["selections"] if jetons and str(x.get("selectionId")) == str(jetons[0])), None)
        if not sel or sel.get("bestBid") is None:
            continue
        lignes.append(comparer((float(sel["bestBid"]), float(sel["bestAsk"])),
                               (float(d["bestBid"]), float(d["bestAsk"])),
                               {"source": "polymarket", "evenement": m["evenement"], "marche": d.get("question")}))
    for m in ps["kalshi"]:
        d = ks.get(m["id"])
        if not d or d.get("status") not in ("active", "open"):
            continue
        sel = next((x for x in m["selections"] if str(x.get("selectionId", "")).endswith(":yes")), None)
        try:
            direct = (float(d["yes_bid_dollars"]), float(d["yes_ask_dollars"]))
        except (KeyError, TypeError, ValueError):
            continue
        if not sel or sel.get("bestBid") is None:
            continue
        lignes.append(comparer((float(sel["bestBid"]), float(sel["bestAsk"])), direct,
                               {"source": "kalshi", "evenement": m["evenement"], "marche": d.get("title")}))

    resume = {}
    for src in ("polymarket", "kalshi"):
        L = [l for l in lignes if l["source"] == src]
        e = [l["ecart_milieu_pts"] for l in L]
        resume[src] = {"marches_compares": len(L), "identiques": sum(l["identique"] for l in L),
                       "ecart_milieu_moins_1pt": sum(x < 1 for x in e),
                       "ecart_milieu_median_pts": round(statistics.median(e), 3) if e else None,
                       "ecart_milieu_moyen_pts": round(statistics.mean(e), 3) if e else None}
    rapport = {"lecture_pulsescore": [t0.isoformat(timespec="seconds"), t1.isoformat(timespec="seconds")],
               "lecture_directe_fin": t2.isoformat(timespec="seconds"), "resume": resume,
               "plus_gros_ecarts": sorted(lignes, key=lambda l: -l["ecart_milieu_pts"])[:25],
               "exemples": [l for l in lignes if l["source"] == "polymarket"][:15]
               + [l for l in lignes if l["source"] == "kalshi"][:15]}
    (OUT / "rapport.json").write_text(json.dumps(rapport, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: rapport[k] for k in ("lecture_pulsescore", "lecture_directe_fin", "resume")},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
