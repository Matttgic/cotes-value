"""Sonde de lecture : DraftKings et Betfair répondent-ils depuis cette machine ?

Aucune clé, aucun compte, aucune écriture : quelques GET sur les API publiques des sites, puis un résumé court de
chaque réponse (code HTTP, taille, forme du JSON). À lancer depuis l'endroit où tourne la collecte (GitHub Actions :
workflow « Sonde des sources US », ou le serveur) : la réponse dépend du pays de sortie.

    python scripts/sonde_sources_us.py            # résumé
    python scripts/sonde_sources_us.py --detail   # plus un extrait du premier match et de ses marchés
"""
from __future__ import annotations

import argparse
import json
import sys
import time

DK = "https://sportsbook-nash.draftkings.com"
LIGUES_DK = {"NBA": 42648, "NHL": 42133, "NFL": 88808, "MLB": 84240}
BETFAIR = ("https://ero.betfair.com/www/sports/exchange/readonly/v1/bymarket?_ak=nzIFcwyWhrlwYMrh&alt=json"
           "&currencyCode=EUR&locale=en_GB&marketIds=1.1&types=MARKET_STATE")


def session():
    from curl_cffi.requests import Session
    return Session(impersonate="chrome")


def forme(o, profondeur=0, largeur=12):
    """Forme d'un JSON : clés, tailles des listes, sans les valeurs (sauf quelques scalaires courts)."""
    if isinstance(o, dict):
        if profondeur >= 3:
            return f"{{{len(o)} clés}}"
        return {k: forme(v, profondeur + 1) for k, v in list(o.items())[:largeur]}
    if isinstance(o, list):
        return [f"{len(o)} éléments", forme(o[0], profondeur + 1)] if o else []
    if isinstance(o, str):
        return o[:40]
    return o


def lire(s, url, detail=False, nom=""):
    debut = time.monotonic()
    try:
        r = s.get(url, timeout=20, headers={"Accept": "application/json, text/plain, */*"})
    except Exception as e:  # noqa: BLE001 - une sonde note l'erreur et continue
        print(f"[{nom}] ERREUR {type(e).__name__}: {str(e)[:120]}")
        return None
    duree = time.monotonic() - debut
    corps = r.content or b""
    print(f"[{nom}] HTTP {r.status_code} · {len(corps)} octets · {duree:.1f} s · {r.headers.get('content-type', '')[:40]}")
    try:
        doc = json.loads(corps)
    except ValueError:
        print("   corps non JSON :", corps[:160].decode("utf-8", "replace").replace("\n", " "))
        return None
    if detail:
        print("   forme :", json.dumps(forme(doc), ensure_ascii=False)[:1800])
    return doc


def extrait_dk(doc, n=2):
    """Premiers événements, marchés et sélections d'une réponse DraftKings (forme « sportscontent »)."""
    if not isinstance(doc, dict):
        return
    for cle in ("events", "markets", "selections"):
        lignes = doc.get(cle) or []
        print(f"   {cle} : {len(lignes)}")
        for x in lignes[:n]:
            print("     ", json.dumps(x, ensure_ascii=False)[:700])
    types = {}
    for m in doc.get("markets") or []:
        t = (m.get("marketType") or {}).get("name") if isinstance(m.get("marketType"), dict) else m.get("marketType")
        types[str(t)] = types.get(str(t), 0) + 1
    if types:
        print("   types de marché :", json.dumps(dict(sorted(types.items(), key=lambda kv: -kv[1])[:40]), ensure_ascii=False))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--detail", action="store_true")
    args = ap.parse_args()
    s = session()
    lire(s, BETFAIR, args.detail, "Betfair bymarket")
    nav = lire(s, f"{DK}/api/sportscontent/navigation/dkusnj/v1/nav/leagues?format=json", args.detail, "DK navigation")
    for nom, ligue in LIGUES_DK.items():
        doc = lire(s, f"{DK}/api/sportscontent/dkusnj/v1/leagues/{ligue}", args.detail, f"DK {nom} ligue")
        if args.detail:
            extrait_dk(doc)
    for nom, chemin in (("DK NBA catégories", f"{DK}/api/sportscontent/dkusnj/v1/leagues/42648/categories"),
                        ("DK NBA points joueurs", f"{DK}/api/sportscontent/dkusnj/v1/leagues/42648/categories/1215"),
                        ("DK NHL catégories", f"{DK}/api/sportscontent/dkusnj/v1/leagues/42133/categories")):
        doc = lire(s, chemin, args.detail, nom)
        if args.detail:
            extrait_dk(doc)
    del nav
    return 0


if __name__ == "__main__":
    sys.exit(main())
