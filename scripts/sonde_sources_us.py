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


def _selection(x: dict) -> dict:
    j = (x.get("participants") or [{}])[0]
    return {k: v for k, v in {"m": x.get("marketId"), "l": x.get("label"), "c": x.get("trueOdds"), "pts": x.get("points"),
                              "o": x.get("outcomeType"), "j": j.get("name"), "jt": j.get("type"), "r": j.get("venueRole"),
                              "ms": x.get("milestoneValue"), "main": x.get("main")}.items() if v is not None}


def _marche(m: dict) -> dict:
    t = m.get("marketType") or {}
    return {"id": m.get("id"), "e": m.get("eventId"), "n": m.get("name"), "t": t.get("name"), "tid": t.get("id"),
            "sub": m.get("subcategoryId"), "main": m.get("main")}


def extrait_dk(doc, evenements=1, marches_max=40, selections_max=60, listes=False):
    """Un événement d'une réponse DraftKings, ses marchés et leurs sélections, en lignes compactes."""
    if not isinstance(doc, dict):
        return
    evs, marches, sels = doc.get("events") or [], doc.get("markets") or [], doc.get("selections") or []
    print(f"   {len(evs)} événements · {len(marches)} marchés · {len(sels)} sélections")
    types = {}
    for m in marches:
        cle = f"{(m.get('marketType') or {}).get('name')}|{m.get('subcategoryId')}"
        types[cle] = types.get(cle, 0) + 1
    print("   types|sous-catégorie :", json.dumps(types, ensure_ascii=False)[:1500])
    if listes:
        print("   catégories :", "; ".join(f"{c.get('id')}={c.get('name')}" for c in doc.get("categories") or [])[:1800])
        print("   sous-catégories :", "; ".join(f"{c.get('id')}/{c.get('categoryId')}={c.get('name')}"
                                                for c in doc.get("subcategories") or [])[:5000])
    deux = [e for e in evs if e.get("eventParticipantType") == "TwoTeam"][:evenements]
    for e in deux:
        print("   EV", json.dumps({"id": e.get("id"), "name": e.get("name"), "start": e.get("startEventDate"),
                                   "status": e.get("status"), "type": e.get("eventParticipantType"),
                                   "p": [{"n": q.get("name"), "r": q.get("venueRole"),
                                          "court": (q.get("metadata") or {}).get("shortName")}
                                         for q in e.get("participants") or []]}, ensure_ascii=False))
        ms = [m for m in marches if m.get("eventId") == e.get("id")][:marches_max]
        ids = {m.get("id") for m in ms}
        for m in ms:
            print("   MA", json.dumps(_marche(m), ensure_ascii=False))
        for x in [x for x in sels if x.get("marketId") in ids][:selections_max]:
            print("   SE", json.dumps(_selection(x), ensure_ascii=False))


def scores(s):
    """Sources de scores pour le règlement (handball, volley, basket féminin) : répondent-elles d'ici ?"""
    jour = time.strftime("%d/%m/%Y", time.gmtime(time.time() - 86400))
    iso = time.strftime("%Y-%m-%d", time.gmtime(time.time() - 86400))
    for nom, url in (
            ("365scores handball", "https://webws.365scores.com/web/games/allscores/?appTypeId=5&langId=1&timezoneName=UTC"
             f"&userCountryId=1&sports=8&startDate={jour}&endDate={jour}&showOdds=false&onlyMajorGames=false"),
            ("365scores sports", "https://webws.365scores.com/web/sports/?appTypeId=5&langId=1&timezoneName=UTC&userCountryId=1"),
            ("Sofascore handball", f"https://api.sofascore.com/api/v1/sport/handball/scheduled-events/{iso}"),
            ("Sofascore volley", f"https://www.sofascore.com/api/v1/sport/volleyball/scheduled-events/{iso}")):
        doc = lire(s, url, False, nom)
        if not isinstance(doc, dict):
            continue
        if doc.get("sports"):
            print("   sports :", "; ".join(f"{x.get('id')}={x.get('name')}" for x in doc["sports"])[:900])
        jeux = doc.get("games") or doc.get("events") or []
        print(f"   {len(jeux)} matchs ; clés :", sorted(jeux[0])[:40] if jeux else [])
        for g in jeux[:3]:
            print("   JEU", json.dumps(g, ensure_ascii=False)[:1400])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--detail", action="store_true")
    args = ap.parse_args()
    s = session()
    lire(s, BETFAIR, True, "Betfair bymarket")
    for nom, ligue in LIGUES_DK.items():
        doc = lire(s, f"{DK}/api/sportscontent/dkusnj/v1/leagues/{ligue}", False, f"DK {nom} ligue")
        extrait_dk(doc, listes=nom in ("NBA", "NHL"))
    # Props : points NBA (catégorie 1215 relevée le 10/11/2026), puis les sous-catégories « O/U » si elles existent
    doc = lire(s, f"{DK}/api/sportscontent/dkusnj/v1/leagues/42648/categories/1215", False, "DK NBA catégorie 1215")
    extrait_dk(doc, marches_max=6, selections_max=30)
    for ligue, nom in ((42648, "NBA"), (42133, "NHL")):
        base = lire(s, f"{DK}/api/sportscontent/dkusnj/v1/leagues/{ligue}", False, f"DK {nom} (sous-catégories)")
        if not isinstance(base, dict):
            continue
        cats = {c.get("id"): c.get("name") for c in base.get("categories") or []}
        vus = 0
        for sc in base.get("subcategories") or []:
            n = str(sc.get("name") or "")
            if "O/U" in n or n in ("Points", "Shots on Goal", "Rebounds", "Assists", "Threes", "Goals"):
                d = lire(s, f"{DK}/api/sportscontent/dkusnj/v1/leagues/{ligue}/categories/{sc.get('categoryId')}"
                            f"/subcategories/{sc.get('id')}", False,
                         f"DK {nom} {cats.get(sc.get('categoryId'))} › {n} ({sc.get('categoryId')}/{sc.get('id')})")
                extrait_dk(d, marches_max=3, selections_max=8)
                vus += 1
                if vus >= 8:
                    break
    if args.detail:
        scores(s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
