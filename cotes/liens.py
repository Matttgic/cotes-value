"""Lien direct vers le match chez le bookmaker, construit à partir de ``match_id`` (« bookmaker|id »).

Formats vérifiés le 25/10/2026 sur de vrais matchs, depuis la France (titre de la page = les deux équipes) :

- Winamax ``/paris-sportifs/match/<id>``, PMU ``/sport/event/<id>`` (redirige vers la page du match),
  NetBet ``/evenement/<id>`` : l'identifiant suffit ;
- Betclic ``/<sport>-s…/<compétition>-c…/<équipes>-m<id>`` : le site ne lit que ``-m<id>``, le reste est du décor ;
- Unibet ``/paris-<sport>/<pays>/<compétition>/<id>/<équipes>`` et OlyBet
  ``/sportsbook/pre-match/match/<sport>/<région>/<compétition>/<id>`` : sport, pays (région) et
  compétition doivent être exacts (sinon page introuvable, ou page de la compétition chez OlyBet). Seule la
  collecte les connaît : elle les met dans ``lien`` (champ ``slug`` de l'événement).

Sans ces données (vieux pari, collecte incomplète), le lien de **repli** ouvre la page du sport chez le
bookmaker ; ``lien_repli`` le signale. Aucune recherche Google.
"""
from __future__ import annotations

import re
import unicodedata
from urllib.parse import quote

# clé = bookmaker en minuscules : (préfixe du match_id, site, URL avec le seul identifiant)
BOOKMAKERS = {
    "winamax": ("winamax", "https://www.winamax.fr", "https://www.winamax.fr/paris-sportifs/match/{id}"),
    "betclic": ("betclic", "https://www.betclic.fr", None),
    "pmu": ("pmu", "https://www.pmu.fr", "https://www.pmu.fr/sport/event/{id}"),
    "unibet": ("unibet-fr", "https://www.unibet.fr", None),
    "olybet": ("olybet", "https://www.olybet.fr", None),
    "netbet": ("netbet", "https://www.netbet.fr", "https://www.netbet.fr/evenement/{id}"),
}
# sport interne -> rubrique du site, pour Betclic (décor du chemin) et pour les liens de repli.
# Unibet et OlyBet : rubriques relevées sur les sites le 25/10/2026.
# Betclic : « <rubrique>-s<code du sport> », la forme vers laquelle le site redirige (football-sfootball,
# hockey-sur-glace-sice_hockey), pour ouvrir la page sans détour.
BETCLIC_SPORTS = {
    "football": "football-sfootball", "tennis": "tennis-stennis", "basket": "basket-ball-sbasketball",
    "hockey": "hockey-sur-glace-sice_hockey", "handball": "handball-shandball", "volley": "volley-ball-svolleyball",
    "rugby": "rugby-a-xv-srugby_union", "football_americain": "football-americain-samerican_football",
    "baseball": "baseball-sbaseball",
}
UNIBET_SPORTS = {
    "football": "football", "tennis": "tennis", "basket": "basketball", "hockey": "hockey-sur-glace",
    "handball": "handball", "volley": "volley-ball", "rugby": "rugby", "rugby_league": "rugby-a-xiii",
    "baseball": "baseball", "boxe": "boxe", "snooker": "snooker", "golf": "golf", "cyclisme": "cyclisme",
}
OLYBET_SPORTS = {
    "football": "Soccer", "tennis": "Tennis", "basket": "Basketball", "hockey": "IceHockey", "handball": "Handball",
    "volley": "Volleyball", "rugby": "RugbyUnion", "rugby_league": "RugbyLeague", "baseball": "Baseball",
    "badminton": "Badminton", "snooker": "Snooker", "tennis_de_table": "TableTennis", "cyclisme": "Cycling",
    "football_americain": "AmericanFootball", "boxe": "Boxing", "mma": "MMA", "golf": "Golf",
    "football_australien": "AustralianFootball",
}


def slug(texte) -> str:
    """Minuscules sans accents, tout le reste en tirets (« Ligue 1 McDonald's » -> « ligue-1-mcdonald-s »)."""
    base = unicodedata.normalize("NFKD", str(texte or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", base).strip("-")


def _identifiant(match_id, prefixe: str) -> str | None:
    tete, sep, ident = str(match_id or "").partition("|")
    return ident.strip() or None if sep and tete.strip().lower() == prefixe else None


def _propre(url: str) -> str:
    """ASCII seulement (utilisable tel quel dans un en-tête HTTP)."""
    return quote(url, safe=":/?&=%#+-_.~!$'()*,;@")


def _releve(p: dict, site: str, ident: str | None) -> str | None:
    """Chemin relevé par la collecte, sur ce site et pour ce match (l'identifiant doit y figurer)."""
    releve = p.get("lien").strip() if isinstance(p.get("lien"), str) else ""
    # l'identifiant doit être un segment du chemin : « /<id>/ », « /<id> » en fin, ou « -m<id> » (Betclic)
    if not releve or not ident or not re.search(rf"(?:/|-m){re.escape(ident)}(?:/|$|[?#])", releve):
        return None
    if releve.startswith(site + "/"):
        return _propre(releve)
    if releve.startswith("/"):
        return _propre(site + releve)
    return None


def _betclic(p: dict, ident: str) -> str:
    """Le site ne lit que ``-m<id>`` (vérifié avec un chemin faux) : sport, compétition et équipes en décor."""
    sport = BETCLIC_SPORTS.get(str(p.get("sport") or ""), "sport-s1")
    ligue = slug(p.get("ligue")) or "competition"
    equipes = slug(f"{p.get('domicile') or ''} {p.get('exterieur') or ''}") or "match"
    return f"https://www.betclic.fr/{sport}/{ligue}-c1/{equipes}-m{quote(ident, safe='')}"


def _repli(cle: str, site: str, sport: str) -> str:
    """Page du sport chez le bookmaker (ou son accueil des paris sportifs)."""
    if cle == "unibet":
        return f"{site}/paris-{UNIBET_SPORTS[sport]}" if sport in UNIBET_SPORTS else f"{site}/paris-tous-sports"
    if cle == "olybet":
        base = f"{site}/sportsbook/pre-match/match"
        return f"{base}/{OLYBET_SPORTS[sport]}" if sport in OLYBET_SPORTS else base
    return site


def lien_info(p: dict) -> tuple[str | None, bool]:
    """(URL absolue, ``True`` si c'est un lien de repli vers la page du sport) ; ``(None, False)`` sans rien de sûr."""
    cle = str(p.get("bookmaker") or "").strip().lower()
    if cle not in BOOKMAKERS:
        releve = p.get("lien").strip() if isinstance(p.get("lien"), str) else ""
        return (_propre(releve), False) if releve.startswith("https://") else (None, False)
    prefixe, site, modele = BOOKMAKERS[cle]
    ident = _identifiant(p.get("match_id"), prefixe)
    if ident and modele:
        return modele.format(id=quote(ident, safe="")), False
    releve = _releve(p, site, ident)
    if releve:
        return releve, False
    if ident and cle == "betclic":
        return _betclic(p, ident), False
    return _repli(cle, site, str(p.get("sport") or "")), True


def lien_match(p: dict) -> str | None:
    """URL absolue du match ; ``None`` pour un bookmaker inconnu sans lien absolu relevé."""
    return lien_info(p)[0]


def completer_liens(paris: list[dict]) -> int:
    """Remplit ``lien`` (URL absolue) et ``lien_repli`` sur chaque pari ; renvoie le nombre de paris modifiés."""
    n = 0
    for p in paris:
        if not isinstance(p, dict):
            continue
        lien, repli = lien_info(p)
        if not lien:
            continue
        avant = (p.get("lien"), p.get("lien_repli", False))
        p["lien"] = lien
        if repli:
            p["lien_repli"] = True
        else:
            p.pop("lien_repli", None)
        n += (p["lien"], p.get("lien_repli", False)) != avant
    return n
