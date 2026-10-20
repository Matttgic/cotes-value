"""Lien direct vers le match chez le bookmaker, construit à partir de ``match_id`` (« bookmaker|id »).

Ordre de préférence :
1. URL qui n'a besoin que de l'identifiant (Winamax) ;
2. chemin relevé par la collecte chez le bookmaker, s'il contient bien cet identifiant (Betclic, PMU,
   Unibet exigent le nom du match dans l'URL : seule la collecte le connaît exactement) ;
3. sinon une recherche limitée au site du bookmaker (OlyBet : son URL exige des identifiants de région et
   de compétition que la collecte ne garde pas).
Non vérifié en ligne : les sites refusent les requêtes automatiques.
"""
from __future__ import annotations

from urllib.parse import quote, quote_plus

# clé = bookmaker en minuscules : (préfixe du match_id, site, URL avec le seul identifiant)
BOOKMAKERS = {
    "winamax": ("winamax", "https://www.winamax.fr", "https://www.winamax.fr/paris-sportifs/match/{id}"),
    "betclic": ("betclic", "https://www.betclic.fr", None),
    "pmu": ("pmu", "https://paris-sportifs.pmu.fr", None),
    "unibet": ("unibet-fr", "https://www.unibet.fr", None),
    "olybet": ("olybet", "https://sports.olybet.fr", None),
}


def _identifiant(match_id, prefixe: str) -> str | None:
    tete, sep, ident = str(match_id or "").partition("|")
    return ident.strip() or None if sep and tete.strip().lower() == prefixe else None


def _propre(url: str) -> str:
    """ASCII seulement (utilisable tel quel dans un en-tête HTTP)."""
    return quote(url, safe=":/?&=%#+-_.~!$'()*,;@")


def lien_match(p: dict) -> str | None:
    """URL absolue du match ; ``None`` pour un bookmaker inconnu sans lien absolu relevé."""
    cle = str(p.get("bookmaker") or "").strip().lower()
    releve = p.get("lien") if isinstance(p.get("lien"), str) else ""
    releve = releve.strip()
    if cle not in BOOKMAKERS:
        return _propre(releve) if releve.startswith("https://") else None
    prefixe, site, modele = BOOKMAKERS[cle]
    ident = _identifiant(p.get("match_id"), prefixe)
    if ident and modele:
        return modele.format(id=quote(ident, safe=""))
    if releve and (not ident or ident in releve):
        if releve.startswith(site + "/"):
            return _propre(releve)
        if not releve.startswith(("http://", "https://")):
            return _propre(site + (releve if releve.startswith("/") else "/" + releve))
    equipes = " ".join(str(p.get(k) or "").strip() for k in ("domicile", "exterieur")).strip()
    domaine = site.split("://", 1)[1]
    return "https://www.google.com/search?q=" + quote_plus(f"site:{domaine} {equipes}".strip())


def completer_liens(paris: list[dict]) -> int:
    """Remplit ``lien`` (URL absolue) sur chaque pari ; renvoie le nombre de liens modifiés."""
    n = 0
    for p in paris:
        if not isinstance(p, dict):
            continue
        lien = lien_match(p)
        if lien and lien != p.get("lien"):
            p["lien"] = lien
            n += 1
    return n
