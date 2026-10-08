"""Sonde API-Sports : la clé (secret API_SPORTS_KEY) donne-t-elle les résultats récents des sports que
les autres sources ne couvrent pas (basket européen, handball, KHL, football féminin) ? N'affiche jamais
la clé ; seulement l'offre, le quota restant et ce qui est trouvé."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone

import requests

API = {"football": "https://v3.football.api-sports.io/fixtures",
       "basket": "https://v1.basketball.api-sports.io/games",
       "hockey": "https://v1.hockey.api-sports.io/games",
       "handball": "https://v1.handball.api-sports.io/games"}
CHERCHES = ["Metz", "Bourges", "Dynamo", "Sochi", "Manresa", "Cluj", "Toronto", "Rwanda", "Trepca", "Botevgrad",
            "Kolossos", "Bakken", "Absheron", "Nice", "Saint-Amand", "Charnay", "Tronche", "AEK"]


def noms(g: dict) -> tuple[str, str, str, str]:
    t = g.get("teams") or {}
    h, a = (t.get("home") or {}).get("name", ""), (t.get("away") or {}).get("name", "")
    ligue = (g.get("league") or {}).get("name", "")
    etat = ((g.get("status") or (g.get("fixture") or {}).get("status") or {}).get("short")) or ""
    return h, a, ligue, etat


def main() -> int:
    cle = os.environ.get("API_SPORTS_KEY", "").strip()
    if not cle:
        print("API_SPORTS_KEY absente")
        return 1
    s = requests.Session()
    s.headers["x-apisports-key"] = cle
    st = s.get("https://v3.football.api-sports.io/status", timeout=30).json()
    compte = (st.get("response") or {})
    print("Offre :", json.dumps({"abonnement": compte.get("subscription"), "requetes": compte.get("requests")},
                                ensure_ascii=False))
    hier = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    for sport, url in API.items():
        r = s.get(url, params={"date": hier, "timezone": "UTC"}, timeout=60)
        d = r.json()
        jeux = d.get("response") or []
        print(f"\n== {sport} {hier} : HTTP {r.status_code}, {len(jeux)} matchs, erreurs {d.get('errors')}, "
              f"quota restant {r.headers.get('x-ratelimit-requests-remaining')}")
        if jeux:
            print("   exemple :", json.dumps(jeux[0], ensure_ascii=False)[:900])
        for g in jeux:
            h, a, ligue, etat = noms(g)
            if any(c.lower() in (h + " " + a).lower() for c in CHERCHES):
                sc = g.get("scores") or g.get("goals") or {}
                print(f"   trouvé : {h} – {a} | {ligue} | {etat} | {json.dumps(sc, ensure_ascii=False)[:300]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
