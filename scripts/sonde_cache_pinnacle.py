"""Sonde temporaire : âge Cloudflare de chaque orthographe d'URL des prix Pinnacle, toutes les 30 s pendant 14 min,
puis une lecture complète du basket par orthographe pour comparer les `version` par match. Rien n'est écrit."""
import json
import statistics
import time

import requests

from cotes import pinnacle

ORTHOS = ["", "?primaryOnly=false", "?primaryOnly=true", "?withSpecials=false", "?withSpecials=true",
          "?primaryOnly=true&withSpecials=false", "?primaryOnly=false&withSpecials=true",
          "?withSpecials=true&primaryOnly=false", "?primaryOnly=false&withSpecials=false",
          "?withSpecials=false&primaryOnly=true", "?primaryOnly=true&withSpecials=true"]
SPORTS = {"foot": 29, "basket": 4, "tennis": 33}
s = requests.Session()
h = pinnacle.headers()
base = pinnacle.base_api()
mesures = []
fin = time.time() + 14 * 60
while time.time() < fin:
    t = time.time()
    for nom, sid in SPORTS.items():
        for q in ORTHOS:
            try:
                r = s.head(f"{base}/sports/{sid}/markets/straight{q}", headers=h, timeout=15, allow_redirects=False)
                mesures.append({"t": round(t), "sport": nom, "q": q, "code": r.status_code,
                                "cache": r.headers.get("cf-cache-status"), "age": r.headers.get("age")})
            except requests.RequestException as e:
                mesures.append({"t": round(t), "sport": nom, "q": q, "code": type(e).__name__})
    time.sleep(max(0, 30 - (time.time() - t)))

print("MESURES", json.dumps(mesures, separators=(",", ":")))

versions = {}
for q in ORTHOS:
    try:
        r = s.get(f"{base}/sports/4/markets/straight{q}", headers=h, timeout=60)
        if r.status_code != 200:
            print("GET", repr(q), r.status_code)
            continue
        v = {}
        for mk in r.json():
            k = f'{mk.get("matchupId")}|{mk.get("key")}'
            v[k] = mk.get("version")
        versions[q] = v
        print("GET", repr(q), 200, "age", r.headers.get("age"), "marches", len(v))
    except Exception as e:  # noqa: BLE001
        print("GET", repr(q), type(e).__name__)
if versions:
    cles = set().union(*versions.values())
    gagne = {q: 0 for q in versions}
    for k in cles:
        vs = {q: d[k] for q, d in versions.items() if k in d and isinstance(d[k], (int, float))}
        if vs:
            m = max(vs.values())
            for q, x in vs.items():
                gagne[q] += x == m
    print("VERSION_MAX", json.dumps({"marches": len(cles), "a_jour_par_ortho": gagne}))
