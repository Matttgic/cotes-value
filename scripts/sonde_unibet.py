"""Sonde Unibet : pourquoi l'accueil répond-il 403 depuis la collecte ?

Aucune écriture, aucun jeton affiché : pour chaque variante (empreinte de navigateur, page lue), le code HTTP,
la taille, le serveur et les en-têtes anti-robot, la présence du jeton LVS, puis un essai de l'API avec ce jeton.
À lancer là où tourne la collecte (workflow « Sonde Unibet »).
"""
from __future__ import annotations

import re
import sys

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


if __name__ == "__main__":
    sys.exit(main())
