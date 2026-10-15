"""Audit ponctuel en lecture seule, au plus 11 GET, aucun pari ni notification.

PULSESCORE_KEY / PROPLINE_API_KEY restent dans les en-têtes. Pas de réponse
brute ni d'exception réseau dans la sortie. Les absences ne prouvent pas une
absence de couverture : une seule page de 30 matchs et un instant sont sondés.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cotes import pinnacle, pulsescore  # noqa: E402


def summarize(events: list[dict]) -> dict:
    """Décrit les preuves disponibles ; n'infère jamais une pause du seul score."""
    fields = ("live", "suspended", "status", "score", "matchClock", "periodScores",
              "updatedAt", "lastUpdated", "last_update", "period", "clock")
    return {
        "events": len(events),
        "sports": dict(Counter(str(e.get("sport", "unknown")) for e in events)),
        "fields_present": {k: sum(e.get(k) is not None for e in events) for k in fields},
        "with_markets": sum(bool(e.get("markets")) for e in events),
        "market_fields": sorted({k for e in events for m in e.get("markets") or [] for k in m}),
        "selection_fields": sorted({k for e in events for m in e.get("markets") or []
                                    for s in m.get("selections") or [] for k in s}),
        "state_examples": [{k: e[k] for k in fields if k in e} for e in events[:5]],
        "pause_detection": "not_implemented_requires_verified_provider_mapping",
    }


def probe(http=requests) -> dict:
    now = datetime.now(timezone.utc)
    out = {"observed_at": now.isoformat(), "requests": 0, "paper_only": True,
           "pulsescore": {}, "pinnacle": {}, "scores": {}}

    def get(url, headers=None, params=None):
        out["requests"] += 1
        try:
            r = http.get(url, headers=headers or {}, params=params or {}, timeout=15)
            if r.status_code != 200:
                return None, {"http": r.status_code}
            return r.json(), {"http": 200}
        except (requests.RequestException, ValueError):
            return None, {"error": "request_failed"}

    key = os.environ.get("PULSESCORE_KEY", "").strip()
    if key:
        for book in ("winamax", "betclic", "unibet-fr", "pmu", "orbitxch"):
            d, meta = get(f"{pulsescore.BASE}/{book}/live-events",
                          {"X-Secret": key, "Accept-Encoding": "gzip"}, {"limit": 30, "page": 1})
            events = d.get("events") if isinstance(d, dict) else None
            out["pulsescore"][book] = {**meta, "schema_ok": isinstance(events, list)}
            if isinstance(events, list) and all(isinstance(e, dict) for e in events):
                out["pulsescore"][book].update(summarize(events), total=d.get("total"),
                                              has_next_page=d.get("hasNextPage"))
            time.sleep(1.1)
    else:
        out["pulsescore"] = {"skipped": "key_not_available_in_this_environment"}

    # UNIQUEMENT les chemins déjà utilisés par le collecteur pré-match.
    # Aucun endpoint live Pinnacle non documenté n'est inventé.
    for sid, sport in ((29, "football"), (19, "hockey")):
        matchups, m_meta = get(f"{pinnacle.BASE}/sports/{sid}/matchups?withSpecials=true", pinnacle.HEADERS)
        markets, p_meta = get(f"{pinnacle.BASE}/sports/{sid}/markets/straight?primaryOnly=false&withSpecials=true",
                              pinnacle.HEADERS)
        live = [m for m in matchups or [] if isinstance(m, dict) and m.get("isLive") is True] \
            if isinstance(matchups, list) else []
        mids = {m.get("id") for m in live}
        prices = [m for m in markets or [] if isinstance(m, dict) and m.get("matchupId") in mids] \
            if isinstance(markets, list) else []
        out["pinnacle"][sport] = {"matchups": m_meta, "markets": p_meta,
                                  "live_matchups": len(live), "linked_markets": len(prices),
                                  "live_types": dict(Counter(str(m.get("type")) for m in live)),
                                  "live_fields": sorted({k for m in live for k in m}),
                                  "price_fields": sorted({k for m in prices for k in m}),
                                  "state_examples": [
                                      {k: m[k] for k in ("isLive", "state", "status", "periods", "version") if k in m}
                                      for m in live if m.get("type") == "matchup"][:3]}

    d, meta = get(f"https://api-web.nhle.com/v1/score/{now:%Y-%m-%d}")
    games = d.get("games") if isinstance(d, dict) else None
    out["scores"]["nhl"] = {**meta, "schema_ok": isinstance(games, list)}
    if isinstance(games, list):
        out["scores"]["nhl"].update(
            states=dict(Counter(str(g.get("gameState")) for g in games)),
            state_examples=[{k: g[k] for k in ("gameState", "clock", "periodDescriptor") if k in g}
                            for g in games[:5]])
    key = os.environ.get("PROPLINE_API_KEY", "").strip()
    if key:
        d, meta = get("https://api.prop-line.com/v1/sports/hockey_nhl/scores",
                      {"X-API-Key": key}, {"days_from": 1})
        out["scores"]["propline_nhl"] = {**meta, "schema_ok": isinstance(d, list)}
        if isinstance(d, list) and all(isinstance(e, dict) for e in d):
            out["scores"]["propline_nhl"].update(summarize(d))
    else:
        out["scores"]["propline_nhl"] = {"skipped": "key_not_available_in_this_environment"}
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sortie", type=Path, required=True)
    args = parser.parse_args()
    report = probe()
    args.sortie.parent.mkdir(parents=True, exist_ok=True)
    args.sortie.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"requests": report["requests"], "paper_only": True}, ensure_ascii=False))


if __name__ == "__main__":
    main()
