"""Sonde PulseScore : mesure ce que l'API renvoie pour les bookmakers français.

Budget : environ 15 requêtes (offre gratuite : 500 par mois, 1 par seconde et par bookmaker).
Sorties dans sonde/ : resume.json (synthèse lisible) et brut/*.json.gz (réponses brutes).

Usage : PULSESCORE_KEY=... python scripts/sonde_pulsescore.py
"""
from __future__ import annotations

import collections
import gzip
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE = "https://api.pulsescore.net/api"
OUT = Path("sonde")
# plan de sonde : bookmaker -> sports (variable SONDE_PLAN en JSON pour le changer sans modifier le code)
PLAN = json.loads(os.environ.get("SONDE_PLAN") or "null") or {
    "winamax": ["soccer", "basketball", "tennis", "ice-hockey", "handball"],
    "betclic": ["soccer", "basketball", "tennis", "ice-hockey", "handball"],
    "unibet-fr": ["soccer"], "pmu": ["soccer"], "netbet": ["soccer"]}
# fiche complète d'un match (bookmaker, sport) et résultats à tester
DETAIL = os.environ.get("SONDE_DETAIL", "winamax/soccer")
RESULTATS = os.environ.get("SONDE_RESULTATS", "winamax")


def get(session: requests.Session, path: str, params: dict | None = None):
    url = f"{BASE}/{path}"
    t0 = time.time()
    try:
        r = session.get(url, params=params, timeout=60)
    except requests.RequestException as e:
        return None, {"url": url, "error": str(e)}
    meta = {"url": r.url.replace(session.headers.get("X-Secret", "§"), "***"),
            "status": r.status_code, "secondes": round(time.time() - t0, 2),
            "octets": len(r.content),
            "rate_headers": {k: v for k, v in r.headers.items() if k.lower().startswith(("x-ratelimit", "retry-after"))}}
    try:
        return r.json(), meta
    except ValueError:
        meta["texte"] = r.text[:300]
        return None, meta


def save_raw(name: str, data) -> None:
    (OUT / "brut").mkdir(parents=True, exist_ok=True)
    with gzip.open(OUT / "brut" / f"{name}.json.gz", "wt", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def summarize_events(events: list[dict]) -> dict:
    n_markets = [len(e.get("markets") or []) for e in events]
    combos = collections.Counter()
    raw_names = collections.defaultdict(set)
    fields_event, fields_market, fields_sel = set(), set(), set()
    for e in events:
        fields_event |= set(e)
        for m in e.get("markets") or []:
            fields_market |= set(m)
            key = f"{m.get('canonicalMarket')}|{m.get('period')}"
            combos[key] += 1
            if len(raw_names[key]) < 4:
                raw_names[key].add(m.get("rawName"))
            for s in m.get("selections") or []:
                fields_sel |= set(s)
    starts = [e.get("startTime") for e in events]
    return {
        "matchs_sur_la_page": len(events),
        "marches_par_match": {"min": min(n_markets, default=0), "moyenne": round(sum(n_markets) / max(len(n_markets), 1), 1),
                              "max": max(n_markets, default=0)},
        "debut_premier_et_dernier": [starts[0], starts[-1]] if starts else None,
        "trie_par_heure": starts == sorted(s or "" for s in starts),
        "ligues_exemples": sorted({e.get("league") for e in events})[:10],
        "champs_match": sorted(fields_event), "champs_marche": sorted(fields_market), "champs_selection": sorted(fields_sel),
        "marches_canoniques": {k: {"n": v, "libelles": sorted(x for x in raw_names[k] if x)} for k, v in combos.most_common()},
    }


def main() -> int:
    key = os.environ.get("PULSESCORE_KEY", "").strip()
    if not key:
        print("PULSESCORE_KEY manquante", file=sys.stderr)
        return 1
    s = requests.Session()
    s.headers.update({"X-Secret": key, "Accept-Encoding": "gzip", "Accept": "application/json"})
    OUT.mkdir(exist_ok=True)
    report = {"date_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "requetes": [], "bookmakers": {}}

    for bm, sports in PLAN.items():
        info = {}
        for sport in sports:
            data, meta = get(s, f"{bm}/{sport}/events", {"page": 1, "limit": 30})
            report["requetes"].append(meta)
            time.sleep(1.2)
            if not isinstance(data, dict) or "events" not in data:
                info[sport] = {"erreur": meta, "reponse": data if not isinstance(data, list) else "liste"}
                continue
            save_raw(f"{bm}_{sport}_p1", data)
            info[sport] = {"total_matchs": data.get("total"), "pages_de_30": data.get("totalPages"),
                           **summarize_events(data["events"])}
        report["bookmakers"][bm] = info

    # un match complet pour comparer avec la version « liste » (le match le plus fourni de la page)
    bm_d, sp_d = DETAIL.split("/")
    try:
        evs = json.loads(gzip.open(OUT / "brut" / f"{bm_d}_{sp_d}_p1.json.gz", "rt").read())["events"]
        ev = max(evs, key=lambda e: len(e.get("markets") or []))
        time.sleep(1.2)
        data, meta = get(s, f"{bm_d}/{sp_d}/events/{ev['eventId']}")
        report["requetes"].append(meta)
        if isinstance(data, dict) and data.get("data"):
            save_raw(f"{bm_d}_{sp_d}_un_match", data)
            report["un_match"] = {"bookmaker": bm_d, "eventId": ev["eventId"], "marches_liste": len(ev.get("markets") or []),
                                  "marches_detail": len(data["data"].get("markets") or [])}
    except (FileNotFoundError, KeyError, IndexError, ValueError) as e:
        report["un_match"] = {"erreur": str(e)}

    # résultats (règlement des paris) : un ou plusieurs bookmakers séparés par des virgules
    report["resultats"] = {}
    for bm in [b.strip() for b in RESULTATS.split(",") if b.strip()]:
        for sp in ("soccer", "ice-hockey"):
            time.sleep(1.2)
            data, meta = get(s, f"{bm}/results", {"sport": sp, "page": 1, "limit": 30})
            report["requetes"].append(meta)
            if data is None:
                continue
            save_raw(f"{bm.replace('/', '-')}_results_{sp}", data)
            items = (data.get("results") or []) if isinstance(data, dict) else []
            report["resultats"][f"{bm}/{sp}"] = {
                "total": data.get("total") if isinstance(data, dict) else None,
                "final": sum(bool((x.get("settlement") or {}).get("final")) for x in items),
                "etats": sorted({str((x.get("settlement") or {}).get("state")) for x in items}),
                "exemple": items[0] if items else None}

    (OUT / "resume.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({bm: {sp: {k: v for k, v in d.items() if k in ("total_matchs", "pages_de_30", "marches_par_match", "erreur")}
                           for sp, d in info.items()} for bm, info in report["bookmakers"].items()}, ensure_ascii=False, indent=1))
    print("requêtes utilisées :", len(report["requetes"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
