"""Sonde Unibet : pourquoi l'accueil répond-il 403 depuis la collecte ?

Aucune écriture, aucun jeton affiché : pour chaque variante (empreinte de navigateur, page lue), le code HTTP,
la taille, le serveur et les en-têtes anti-robot, la présence du jeton LVS, puis un essai de l'API avec ce jeton.
À lancer là où tourne la collecte (workflow « Sonde Unibet »).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ACCUEIL = "https://www.unibet.fr/"
PAGES = ["https://www.unibet.fr/", "https://www.unibet.fr/sport", "https://www.unibet.fr/sport/football"]
EMPREINTES = ["chrome", "chrome131", "chrome124", "safari", "safari_ios", "firefox", "edge"]
ENTETES = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
           "Accept-Language": "fr-FR,fr;q=0.9"}
INDICES = ("server", "cf-ray", "cf-mitigated", "x-akamai", "akamai-grn", "x-iinfo", "x-cdn", "via",
           "x-datadome", "set-cookie")


def resume(r) -> str:
    h = {k.lower(): v for k, v in (r.headers or {}).items()}
    vus = {k: (h[k][:60] if k != "set-cookie" else "/".join(c.split("=")[0] for c in h[k].split(", ")[:6]))
           for k in INDICES if k in h}
    texte = r.text or ""
    titre = re.search(r"<title>(.*?)</title>", texte, re.DOTALL | re.IGNORECASE)
    jeton = bool(re.search(r"HSToken|hsToken|lvs", texte))
    return (f"{r.status_code} · {len(texte)} car. · titre={titre.group(1).strip()[:60] if titre else '-'} · "
            f"lvs={'oui' if jeton else 'non'} · {vus}")


def main() -> int:
    import requests
    from curl_cffi.requests import Session

    try:
        ip = requests.get("https://api.ipify.org", timeout=10).text
        pays = requests.get(f"https://ipinfo.io/{ip}/country", timeout=10).text.strip()
        print(f"Sortie : pays {pays}")
    except Exception as ex:  # noqa: BLE001
        print(f"Sortie : inconnue ({type(ex).__name__})")
    for imp in EMPREINTES:
        try:
            s = Session(impersonate=imp)
        except Exception as ex:  # noqa: BLE001
            print(f"{imp:11} indisponible ({type(ex).__name__})")
            continue
        for url in PAGES:
            try:
                print(f"{imp:11} {url[22:] or '/':16} {resume(s.get(url, headers=ENTETES, timeout=20))}")
            except Exception as ex:  # noqa: BLE001
                print(f"{imp:11} {url[22:] or '/':16} erreur {type(ex).__name__}: {str(ex)[:100]}")
    try:
        r = requests.get(ACCUEIL, headers={**ENTETES, "User-Agent": "Mozilla/5.0"}, timeout=20)
        print(f"requests    /                {resume(r)}")
    except Exception as ex:  # noqa: BLE001
        print(f"requests    erreur {type(ex).__name__}")
    try:
        r = requests.get("https://www.unibet.fr/lvs-api/next/50/p?lineId=1&originId=3", timeout=20,
                         headers={"Accept": "application/json", "Referer": ACCUEIL, "User-Agent": "Mozilla/5.0"})
        print(f"API sans jeton : {r.status_code} · {len(r.text)} car.")
    except Exception as ex:  # noqa: BLE001
        print(f"API sans jeton : erreur {type(ex).__name__}")
    return 0


def _objets(x, chemin=""):
    """Tous les dictionnaires imbriqués, avec leur chemin."""
    if isinstance(x, dict):
        yield chemin, x
        for k, v in x.items():
            yield from _objets(v, f"{chemin}/{k}")
    elif isinstance(x, list):
        for i, v in enumerate(x[:400]):
            yield from _objets(v, f"{chemin}[{i}]")


def marches(sports=("VOLL", "AMFB", "HAND", "RUGU", "BADM")) -> int:
    """Identifiants des marchés d'un match par sport : clés des marchés de la liste lvs-api, puis marchés de la
    page du match (état serverApp). Aucune cote ni jeton affichés : description, style et champs d'identifiants."""
    import json
    from cotes.direct import unibet as U
    c = U.Client()
    if not c.ouvrir():
        print("ouverture impossible :", c.erreurs)
        return 1
    print("nœuds :", {k: v for k, v in c.noeuds.items() if k in sports})
    page = U._page_chrome()
    for code in sports:
        noeud = c.noeuds.get(code)
        if not noeud:
            print(f"== {code} : pas de nœud")
            continue
        doc = c.get(f"next/50/p{noeud}", dict(U.PARAMS)) or {}
        items = doc.get("items") if isinstance(doc.get("items"), dict) else {}
        evs = [(k, v) for k, v in items.items() if k.startswith("e") and isinstance(v, dict) and U._match(v)]
        mks = [v for k, v in items.items() if k.startswith("m") and isinstance(v, dict)]
        print(f"== {code} : {len(evs)} matchs ; clés d'un marché de la liste : {sorted(mks[0]) if mks else '-'}")
        if mks:
            print("   exemple :", {k: v for k, v in mks[0].items() if k not in ("outcomes",)})
        for cle, ev in evs[:1]:
            chemin = U.chemin_match(cle[1:], ev)
            if not chemin:
                continue
            try:
                r = page.get("https://www.unibet.fr" + chemin, timeout=20,
                             headers={"Accept": "text/html", "Accept-Language": "fr-FR"})
            except Exception as ex:  # noqa: BLE001
                print(f"   {chemin} : erreur {type(ex).__name__}")
                continue
            m = U._SCRIPT.search(r.text or "")
            print(f"   {ev.get('desc')} : HTTP {r.status_code}, état {'oui' if m else 'non'}")
            if not m:
                continue
            try:
                etat = json.loads(m.group(1))
            except ValueError:
                continue
            print("     état :", {k: len(json.dumps(v)) for k, v in etat.items()} if isinstance(etat, dict) else type(etat))
            paires = {}
            for ch, o in _objets(etat):
                t, per = o.get("marketTypeId"), o.get("periodId")
                if isinstance(t, int) and isinstance(per, int) and not re.search(
                        r"mi-temps|quart|set|p[ée]riode|manche", str(o.get("period")), re.I):
                    paires[(t, per)] = paires.get((t, per), 0) + 1
            print(f"     {len(paires)} marchés « match » sur la page ; vérification par l'API :")
            for (t, per), n in sorted(paires.items(), key=lambda x: -x[1])[:14]:
                d = c.get(f"next/50/p{noeud}", {**U.PARAMS, "marketTypeId": str(t), "periodId": str(per)}) or {}
                it = d.get("items") if isinstance(d.get("items"), dict) else {}
                ms = [v for k, v in it.items() if k.startswith("m") and isinstance(v, dict)]
                noms = sorted({str(v.get("desc"))[:45] for v in ms})[:3]
                print(f"     ({t}, {per}) {n} sur la page · API : {len(ms)} marchés · {noms} · {ms[0].get('style') if ms else ''}")
            break
    # Collecte réelle de ces sports avec les filtres du collecteur : marchés et lignes de total par match
    import collections
    lignes, meta = U.collecter({"volley", "football_americain", "handball"}, 36)
    print("collecte :", {k: v for k, v in meta.items() if k in ("ok", "requetes", "matchs")}, meta.get("erreurs", [])[:5])
    for k, n in sorted(collections.Counter((l["sport"], l["marche"], l["periode"]) for l in lignes).items()):
        print("  ", k, n)
    par = collections.defaultdict(set)
    for l in lignes:
        if l["marche"] == "TOTAL" and l["periode"] == "MATCH":
            par[(l["sport"], l["match_id"])].add(l["ligne"])
    for sp in ("volley", "football_americain", "handball"):
        v = [len(x) for (s_, _), x in par.items() if s_ == sp]
        print(f"   {sp} : {len(v)} matchs avec total, {sum(v) / max(1, len(v)):.1f} lignes par match")
    return 0


if __name__ == "__main__":
    sys.exit(marches() if "--marches" in sys.argv else main())
