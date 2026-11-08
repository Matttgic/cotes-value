"""Sonde Betfair Exchange : les API du site, lues sans compte, répondent-elles depuis cette machine ?

À lancer sur le serveur (IP hors de France et hors des États-Unis : Betfair refuse les deux) :

    cd /opt/cotes-value && sudo -u cotes .venv/bin/python scripts/sonde_betfair.py

Quatre étapes, chacune affiche son code HTTP et son temps de réponse :
1. pays de l'IP vu par le CDN de Betfair (``/cdn-cgi/trace``) ;
2. clé publique ``_ak`` du site, cherchée dans la page de l'Exchange ; sinon ``BETFAIR_AK``, sinon la valeur connue ;
3. recherche des marchés « Match Odds » à venir (``scan-inbf.betfair.com``, navigation facet) ;
4. cotes et montants disponibles de ces marchés (``ero.betfair.com``, readonly ``bymarket``).

Options : ``--sport 1`` (football, défaut) ou ``2`` (tennis) ; ``--sauver DOSSIER`` garde les réponses brutes
(pour écrire le futur lecteur et ses tests). Code de sortie 0 si les étapes 3 et 4 réussissent.
Aucun compte, aucun identifiant ; rien n'est écrit dans les données.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

AK_CONNUE = "nzIFcwyWhrlwYMrh"
PAGE = "https://www.betfair.com/exchange/plus/"
TRACE = "https://www.betfair.com/cdn-cgi/trace"
RECHERCHE = "https://scan-inbf.betfair.com/www/sports/navigation/facet/v1/search"
COTES = "https://ero.betfair.com/www/sports/exchange/readonly/v1/bymarket"
ENTETES = {"Accept": "application/json, text/plain, */*", "Origin": "https://www.betfair.com", "Referer": PAGE}
TYPES = "MARKET_STATE,MARKET_DESCRIPTION,EVENT,RUNNER_DESCRIPTION,RUNNER_STATE,RUNNER_EXCHANGE_PRICES_BEST"
_MOTIFS_AK = (re.compile(r"""["']?appKey["']?\s*[:=]\s*["']([A-Za-z0-9]{16})["']"""),
              re.compile(r"""[?&]_ak=([A-Za-z0-9]{16})"""))
_ID_MARCHE = re.compile(r"\b1\.\d{8,10}\b")


def session():
    """Empreinte TLS de Chrome si curl_cffi est installé (cas du serveur), sinon requests."""
    try:
        from curl_cffi.requests import Session
        return Session(impersonate="chrome"), "curl_cffi (Chrome)"
    except ImportError:
        import requests
        return requests.Session(), "requests (sans empreinte Chrome)"


def appel(s, methode: str, url: str, **kw):
    """(code, texte, durée en ms) ; code 0 si la connexion échoue."""
    debut = time.monotonic()
    try:
        r = s.request(methode, url, timeout=20, **kw)
        return r.status_code, r.text, round(1000 * (time.monotonic() - debut))
    except Exception as e:  # noqa: BLE001 — la sonde rapporte toute erreur réseau, elle ne s'arrête pas
        return 0, f"{type(e).__name__}: {e}", round(1000 * (time.monotonic() - debut))


def pays(trace: str) -> str | None:
    m = re.search(r"^loc=([A-Z]{2})$", trace, re.MULTILINE)
    return m.group(1) if m else None


def cles_ak(texte: str) -> list[str]:
    """Clés ``_ak`` trouvées dans une page ou un script, sans doublon, dans l'ordre."""
    vues: list[str] = []
    for motif in _MOTIFS_AK:
        for cle in motif.findall(texte):
            if cle not in vues:
                vues.append(cle)
    return vues


def corps_recherche(sport: int, nombre: int) -> dict:
    """Requête de navigation du site : marchés Match Odds à venir, du premier qui commence au suivant."""
    return {
        "filter": {"marketBettingTypes": ["ODDS"], "productTypes": ["EXCHANGE"], "marketTypeCodes": ["MATCH_ODDS"],
                   "selectBy": "FIRST_TO_START", "contentGroup": {"language": "en", "regionCode": "UK"},
                   "turnInPlayEnabled": True, "maxResults": 0, "eventTypeIds": [sport]},
        "facets": [{"type": "EVENT", "skipValues": 0, "maxValues": nombre,
                    "next": {"type": "MARKET", "skipValues": 0, "maxValues": 1}}],
        "currencyCode": "EUR", "locale": "en_GB",
    }


def marches_trouves(reponse: dict | list | None, texte: str) -> list[dict]:
    """Marchés de la réponse de recherche : ``attachments.markets`` (et l'événement lié), sinon tout identifiant
    ``1.xxxxxxxxx`` du texte. Chaque marché : ``id``, ``nom``, ``evenement``, ``debut`` (None si inconnus)."""
    att = reponse.get("attachments") if isinstance(reponse, dict) else None
    marches = att.get("markets") if isinstance(att, dict) else None
    evenements = (att.get("events") or {}) if isinstance(att, dict) else {}
    out = []
    if isinstance(marches, dict) and marches:
        for cle, m in marches.items():
            m = m if isinstance(m, dict) else {}
            ev = evenements.get(str(m.get("eventId"))) or {}
            out.append({"id": str(m.get("marketId") or cle), "nom": m.get("marketName"),
                        "evenement": ev.get("name"), "debut": m.get("marketTime") or ev.get("openDate")})
        return out
    return [{"id": i, "nom": None, "evenement": None, "debut": None} for i in dict.fromkeys(_ID_MARCHE.findall(texte))]


def _meilleur(echelle) -> tuple[float | None, float | None]:
    if isinstance(echelle, list) and echelle and isinstance(echelle[0], dict):
        return echelle[0].get("price"), echelle[0].get("size")
    return None, None


def cotes_lues(reponse) -> list[dict]:
    """Une ligne par issue : marché, événement, état, issue, meilleur back et lay avec leur montant (EUR)."""
    lignes = []
    types = reponse.get("eventTypes") if isinstance(reponse, dict) else None
    for et in types or []:
        for noeud in et.get("eventNodes") or []:
            evenement = (noeud.get("event") or {}).get("eventName")
            for m in noeud.get("marketNodes") or []:
                etat = m.get("state") or {}
                for r in m.get("runners") or []:
                    ech = r.get("exchange") or {}
                    back, back_eur = _meilleur(ech.get("availableToBack"))
                    lay, lay_eur = _meilleur(ech.get("availableToLay"))
                    lignes.append({"marche": m.get("marketId"), "evenement": evenement,
                                   "etat": etat.get("status"), "en_direct": etat.get("inplay"),
                                   "issue": (r.get("description") or {}).get("runnerName") or r.get("selectionId"),
                                   "back": back, "back_eur": back_eur, "lay": lay, "lay_eur": lay_eur})
    return lignes


def _json(texte: str):
    try:
        return json.loads(texte)
    except ValueError:
        return None


def _resume(code: int, texte: str) -> str:
    """Début de réponse lisible quand ce n'est pas du JSON (page Cloudflare, erreur…)."""
    titre = re.search(r"<title>(.*?)</title>", texte, re.DOTALL | re.IGNORECASE)
    return (titre.group(1).strip() if titre else texte.strip().replace("\n", " "))[:160] if code != 200 else ""


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--sport", type=int, default=1, help="1 football (défaut), 2 tennis")
    p.add_argument("--nombre", type=int, default=10, help="marchés à lire (25 au plus par appel)")
    p.add_argument("--sauver", type=Path, help="dossier où garder les réponses brutes")
    a = p.parse_args(argv)
    nombre = max(1, min(a.nombre, 25))
    if a.sauver:
        a.sauver.mkdir(parents=True, exist_ok=True)

    def garder(nom: str, texte: str) -> None:
        if a.sauver:
            (a.sauver / nom).write_text(texte, encoding="utf-8")

    s, client = session()
    print(f"Client HTTP : {client}")

    code, texte, ms = appel(s, "GET", TRACE)
    print(f"1. Pays vu par Betfair : {pays(texte) or 'inconnu'} (HTTP {code}, {ms} ms)")

    code, texte, ms = appel(s, "GET", PAGE, headers={"Accept": "text/html"})
    trouvees = cles_ak(texte) if code == 200 else []
    garder("page_exchange.html", texte)
    ak = (trouvees[0] if trouvees else "") or os.environ.get("BETFAIR_AK", "").strip() or AK_CONNUE
    origine = "page" if trouvees else ("BETFAIR_AK" if os.environ.get("BETFAIR_AK", "").strip() else "valeur connue")
    print(f"2. Page Exchange : HTTP {code}, {ms} ms {_resume(code, texte)}".rstrip())
    print(f"   clé _ak : {ak[:4]}… ({origine}{', identique à la connue' if ak == AK_CONNUE and trouvees else ''}"
          f"{f', {len(trouvees)} trouvée(s)' if trouvees else ''})")

    code, texte, ms = appel(s, "POST", RECHERCHE, params={"_ak": ak, "alt": "json"},
                            json=corps_recherche(a.sport, nombre), headers=ENTETES)
    garder("recherche.json", texte)
    marches = marches_trouves(_json(texte), texte) if code == 200 else []
    print(f"3. Recherche des marchés : HTTP {code}, {ms} ms, {len(marches)} marché(s) {_resume(code, texte)}".rstrip())
    for m in marches[:5]:
        print(f"   {m['id']}  {m['evenement'] or '?'} · {m['nom'] or '?'} · {m['debut'] or '?'}")
    recherche_ok = code == 200 and bool(marches)

    if not marches:
        print("4. Cotes : non testées (aucun marché trouvé)")
        print("Bilan : recherche KO, cotes non testées")
        return 1
    params = {"_ak": ak, "alt": "json", "currencyCode": "EUR", "locale": "en_GB", "rollupLimit": 5,
              "rollupModel": "STAKE", "types": TYPES, "marketIds": ",".join(m["id"] for m in marches[:nombre])}
    code, texte, ms = appel(s, "GET", COTES, params=params, headers=ENTETES)
    garder("cotes.json", texte)
    lignes = cotes_lues(_json(texte)) if code == 200 else []
    avec_prix = [l for l in lignes if l["back"] is not None or l["lay"] is not None]
    print(f"4. Cotes : HTTP {code}, {ms} ms, {len(lignes)} issue(s), {len(avec_prix)} avec un prix "
          f"{_resume(code, texte)}".rstrip())
    for l in lignes[:9]:
        print(f"   {l['marche']}  {l['evenement'] or '?'} · {l['issue']} · {l['etat']}"
              f"{' (en direct)' if l['en_direct'] else ''} · back {l['back']} ({l['back_eur']} €)"
              f" · lay {l['lay']} ({l['lay_eur']} €)")
    cotes_ok = code == 200 and bool(avec_prix)
    print(f"Bilan : recherche {'OK' if recherche_ok else 'KO'}, cotes {'OK' if cotes_ok else 'KO'}")
    if a.sauver:
        print(f"Réponses brutes gardées dans {a.sauver}")
    return 0 if recherche_ok and cotes_ok else 1


if __name__ == "__main__":
    sys.exit(main())
