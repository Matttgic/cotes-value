"""Cotes Smarkets, API publique v3, sans compte.

Les prix sont des probabilités × 10 000 (4 808 = 48,08 %, cote décimale 2,0799).
La quantité est en dix-millièmes d'unité monétaire. Le meilleur achat est la
plus basse offre, la meilleure vente la plus haute demande. La cote juste est
ensuite le milieu achat/vente, comme Betfair : le spread est dans le milieu,
aucune commission n'est retirée en plus.

Les paris simulés contre Smarkets ont leur propre table, comme Betfair :
10 € dès qu'un bookmaker français bat la cote juste. ``SMARKETS_DANS_DECISION``
(défaut : non) ne décide que du consensus partagé. Éteint, Smarkets n'entre
pas dans cette moyenne. L'écart affiché reste dans les deux cas.
"""
from __future__ import annotations

import os
import random
import re
import time
from datetime import datetime, timedelta, timezone

import requests

from cotes.comparaison import reference_echange

BASE = "https://api.smarkets.com/v3"
_OUI = {"1", "oui", "on", "true", "yes"}
# type d'événement Smarkets -> sport interne
EVENEMENTS = {
    "football_match": "football",
    "tennis_match": "tennis",
    "basketball_match": "basket",
    "ice_hockey_match": "hockey",
    "handball_match": "handball",
    "volleyball_match": "volley",
    "rugby_union_match": "rugby",
    "american_football_match": "football_americain",
    "baseball_match": "baseball",
}
# type de marché -> (marché interne, période, la ligne est le paramètre)
MARCHES = {
    "WINNER_3_WAY": ("RESULTAT_1N2", "MATCH", False),
    "WINNER_2_WAY": ("VAINQUEUR", "MATCH", False),
    "HALF_TIME_WINNER_3_WAY": ("RESULTAT_1N2", "MT1", False),
    "SECOND_HALF_WINNER_3_WAY": ("RESULTAT_1N2", "MT2", False),
    "WINNER_DNB": ("DRAW_NO_BET", "MATCH", False),
    "DOUBLE_CHANCE": ("DOUBLE_CHANCE", "MATCH", False),
    "HALF_TIME_DOUBLE_CHANCE": ("DOUBLE_CHANCE", "MT1", False),
    "BTTS": ("BOTH_TEAMS_TO_SCORE", "MATCH", False),
    "BTTS_FIRST_HALF": ("BOTH_TEAMS_TO_SCORE", "MT1", False),
    "BTTS_SECOND_HALF": ("BOTH_TEAMS_TO_SCORE", "MT2", False),
    "OVER_UNDER": ("TOTAL", "MATCH", True),
    "FIRST_HALF_OVER_UNDER": ("TOTAL", "MT1", True),
    "SECOND_HALF_OVER_UNDER": ("TOTAL", "MT2", True),
    "HOME_TEAM_OVER_UNDER": ("TOTAL_DOM", "MATCH", True),
    "AWAY_TEAM_OVER_UNDER": ("TOTAL_EXT", "MATCH", True),
    "FIRST_HALF_HOME_TEAM_OVER_UNDER": ("TOTAL_DOM", "MT1", True),
    "FIRST_HALF_AWAY_TEAM_OVER_UNDER": ("TOTAL_EXT", "MT1", True),
    "ASIAN_HANDICAP": ("HANDICAP", "MATCH", True),
    "FIRST_HALF_ASIAN_HANDICAP": ("HANDICAP", "MT1", True),
    "HANDICAP_3_WAY": ("HANDICAP_3", "MATCH", True),
    "FIRST_HALF_HANDICAP_3_WAY": ("HANDICAP_3", "MT1", True),
    "CORRECT_SCORE": ("CORRECT_SCORE", "MATCH", False),
    "HALF_TIME_CORRECT_SCORE": ("CORRECT_SCORE", "MT1", False),
    "HALF_FULL": ("HALF_TIME_FULL_TIME", "MATCH", False),
}
_ISSUE = {
    "HOME": "DOM", "AWAY": "EXT", "DRAW": "NUL",
    "OVER": "PLUS", "UNDER": "MOINS", "YES": "YES", "NO": "NO",
    "HOME_DRAW": "HOME_DRAW", "HOME_AWAY": "HOME_AWAY", "DRAW_AWAY": "DRAW_AWAY",
}
_HTFT = {"HOME": "DOM", "AWAY": "EXT", "DRAW": "NUL"}
_PROLONGATION = ("hockey", "basket", "football_americain", "baseball")


def dans_decision() -> bool:
    """Faux tant que la variable n'est pas explicitement oui."""
    return os.environ.get("SMARKETS_DANS_DECISION", "").strip().lower() in _OUI


def ajouter_table(references: dict, lignes: list[dict]) -> dict:
    """Table de paris propre, toujours, comme Betfair.

    Les lignes ne sont jamais versées dans les cotes françaises. Le drapeau
    ne retire pas cette table : il ne concerne que le consensus.
    """
    references["Smarkets"] = lignes
    return references


def hors_consensus() -> frozenset[str]:
    """Smarkets reste hors de la moyenne partagée tant que le drapeau est éteint."""
    return frozenset() if dans_decision() else frozenset({"Smarkets"})


def ajouter_decision(references: dict, lignes: list[dict]) -> dict:
    """Compatibilité : la table est toujours alimentée."""
    return ajouter_table(references, lignes)


def _heure(valeur):
    try:
        t = datetime.fromisoformat(str(valeur).replace("Z", "+00:00"))
        return t.astimezone(timezone.utc) if t.tzinfo else None
    except (TypeError, ValueError):
        return None


def _nombre(valeur) -> float | None:
    if isinstance(valeur, bool) or valeur is None:
        return None
    try:
        return float(valeur)
    except (TypeError, ValueError):
        return None


def periode_match(sport: str, nom: str, periode: str) -> str:
    """Hockey et basket : sans mention explicite, la prolongation reste ambiguë."""
    if periode != "MATCH" or sport not in _PROLONGATION:
        return periode
    bas = (nom or "").lower()
    if "overtime" in bas or "extra time" in bas or "prolong" in bas:
        return "MATCH"
    if "regular" in bas or "regulation" in bas:
        return "TEMPS_REG"
    return "MATCH?"


def _decimal(prix) -> float | None:
    n = _nombre(prix)
    if n is None or not 0 < n < 10000:
        return None
    return 10000 / n


def _liquidite(quantite) -> float:
    n = _nombre(quantite) or 0
    return round(n / 10000, 2)


class Client:
    """GET espacés. Un 403 (blocage du runner, pas une auth) est retenté une fois puis coupe le sport.

    Sans session injectée, curl_cffi se fait passer pour Chrome : l'API publique
    répond 200 hors de GitHub et 403 en 0,1 s depuis les runners, dès la première
    requête. Le corps n'est jamais journalisé.
    """

    def __init__(self, session=None, pause: tuple[float, float] = (0.2, 0.4)):
        self.session = session if session is not None else _session_chrome()
        self.pause = pause
        self.requetes = 0
        self.erreurs: list[str] = []
        self._bloque = False
        self._premier = True

    def _espacer(self) -> None:
        if self._premier:
            self._premier = False
            return
        bas, haut = self.pause
        if haut > 0:
            time.sleep(haut if bas == haut else random.uniform(bas, haut))

    def get(self, chemin: str):
        if self._bloque:
            return None
        url = chemin if chemin.startswith("http") else f"{BASE}/{chemin.lstrip('/')}"
        dernier = "réseau"
        for essai in range(3):
            self._espacer()
            self.requetes += 1
            try:
                r = self.session.get(url, timeout=30, headers={"Accept": "application/json"})
            except (requests.RequestException, OSError):
                dernier = "réseau"
                time.sleep(0.5 * (essai + 1))
                continue
            if r.status_code == 403:
                # Pas une demande d'identifiants : la même URL répond 200 ailleurs.
                if essai == 0:
                    time.sleep(1.5)
                    continue
                self._bloque = True
                self._noter("HTTP 403")
                return None
            if r.status_code in (429, 500, 502, 503, 504):
                dernier = f"HTTP {r.status_code}"
                time.sleep(0.5 * (essai + 1))
                continue
            if r.status_code != 200:
                self._noter(f"HTTP {r.status_code}")
                return None
            try:
                doc = r.json()
            except ValueError:
                self._noter("JSON invalide")
                return None
            if not isinstance(doc, (dict, list)):
                self._noter("JSON inattendu")
                return None
            return doc
        self._noter(dernier)
        return None

    def _noter(self, message: str) -> None:
        if message not in self.erreurs and len(self.erreurs) < 30:
            self.erreurs.append(message)


def _session_chrome():
    """Session navigateur. L'API ne demande pas de compte ; seul le fingerprint change."""
    from curl_cffi.requests import Session
    return Session(impersonate="chrome")


def _lots(valeurs: list, taille: int):
    for i in range(0, len(valeurs), taille):
        yield valeurs[i:i + taille]


def _type_marche(marche: dict) -> str:
    return str((marche.get("market_type") or {}).get("name") or "")


def _ligne(marche: dict) -> float | None:
    return _nombre((marche.get("market_type") or {}).get("param"))


def _issue(marche_interne: str, contrat: dict) -> str | None:
    ctype = contrat.get("contract_type") if isinstance(contrat.get("contract_type"), dict) else {}
    nom = str(ctype.get("name") or "")
    if marche_interne == "CORRECT_SCORE":
        brut = str(ctype.get("param") or "").replace(" ", "")
        return brut if re.fullmatch(r"\d+-\d+", brut) else None
    if marche_interne == "HALF_TIME_FULL_TIME":
        parts = nom.split("_")
        if len(parts) == 2 and all(p in _HTFT for p in parts):
            return f"{_HTFT[parts[0]]}/{_HTFT[parts[1]]}"
        return None
    return _ISSUE.get(nom)


def _carnet(quote: dict) -> tuple[dict, dict] | None:
    offres = [q for q in (quote.get("offers") or []) if _decimal(q.get("price"))]
    demandes = [q for q in (quote.get("bids") or []) if _decimal(q.get("price"))]
    if not offres or not demandes:
        return None
    offre = min(offres, key=lambda q: q["price"])
    demande = max(demandes, key=lambda q: q["price"])
    achat, vente = _decimal(offre["price"]), _decimal(demande["price"])
    if achat is None or vente is None or not 1 < achat <= vente:
        return None
    return ({"price": round(achat, 4), "liquidity": _liquidite(offre.get("quantity"))},
            {"price": round(vente, 4), "liquidity": _liquidite(demande.get("quantity"))})


def _equipes(event: dict, contrats: list[dict]) -> tuple[str | None, str | None]:
    home = away = None
    for c in contrats:
        nom = str((c.get("contract_type") or {}).get("name") or "")
        if nom == "HOME" and c.get("name"):
            home = str(c["name"])
        elif nom == "AWAY" and c.get("name"):
            away = str(c["name"])
    if home and away:
        return home, away
    titre = str(event.get("name") or "")
    bas = titre.lower()
    if " vs " in bas or " vs. " in bas:
        sep = " vs. " if " vs. " in bas else " vs "
        a, b = titre.split(sep, 1)
        return a.strip() or None, b.strip() or None
    if " at " in bas:
        a, b = titre.split(" at ", 1)
        return b.strip() or None, a.strip() or None
    return None, None


def _evenements(client: Client, type_event: str, heures: float, maintenant: datetime) -> list[dict]:
    chemin = f"events/?states=upcoming&limit=100&type={type_event}&sort=start_datetime,id"
    out = []
    for _ in range(6):
        doc = client.get(chemin)
        if not isinstance(doc, dict):
            break
        for ev in doc.get("events") or []:
            if not isinstance(ev, dict) or ev.get("hidden") or ev.get("state") not in (None, "upcoming"):
                continue
            debut = _heure(ev.get("start_datetime"))
            if debut and maintenant < debut <= maintenant + timedelta(hours=heures):
                out.append(ev)
        nxt = (doc.get("pagination") or {}).get("next_page")
        if not nxt:
            break
        chemin = "events/" + nxt if str(nxt).startswith("?") else str(nxt).lstrip("/")
    return out


def collecter(sports: set[str] | None = None, heures: float = 36, session=None,
              maintenant: datetime | None = None) -> tuple[list[dict], dict]:
    """Lignes au format référence (probabilité juste déjà calculée)."""
    maintenant = maintenant or datetime.now(timezone.utc)
    client = Client(session)
    moment = maintenant.isoformat(timespec="seconds")
    demandes = [(t, s) for t, s in EVENEMENTS.items() if sports is None or s in sports]
    if not demandes:
        return [], {"ok": True, "erreurs": [], "requetes": 0, "matchs": 0}
    bruts: list[dict] = []
    matchs = 0
    for type_event, sport in demandes:
        events = _evenements(client, type_event, heures, maintenant)
        matchs += len(events)
        for lot in _lots(events, 10):
            ids = ",".join(str(e["id"]) for e in lot if e.get("id"))
            doc = client.get(f"events/{ids}/markets/")
            marches = [m for m in ((doc or {}).get("markets") or [])
                       if isinstance(m, dict) and m.get("state") in (None, "open")
                       and not m.get("hidden") and _type_marche(m) in MARCHES]
            if not marches:
                continue
            ids_m = [str(m["id"]) for m in marches if m.get("id")]
            contrats: dict[str, list] = {}
            carnets: dict[str, dict] = {}
            for groupe in _lots(ids_m, 20):
                cle = ",".join(groupe)
                doc_c = client.get(f"markets/{cle}/contracts/")
                for c in ((doc_c or {}).get("contracts") or []) if isinstance(doc_c, dict) else []:
                    if isinstance(c, dict):
                        contrats.setdefault(str(c.get("market_id")), []).append(c)
                doc_q = client.get(f"markets/{cle}/quotes/")
                if isinstance(doc_q, dict) and "error_type" not in doc_q:
                    carnets.update(doc_q)
            par_event = {str(e["id"]): e for e in lot}
            vainqueurs: dict[str, list] = {}
            for m in marches:
                if _type_marche(m) in ("WINNER_3_WAY", "WINNER_2_WAY"):
                    vainqueurs.setdefault(str(m.get("event_id")), []).extend(
                        contrats.get(str(m.get("id")), []))
            for m in marches:
                event = par_event.get(str(m.get("event_id")))
                if not event:
                    continue
                interne, periode, a_ligne = MARCHES[_type_marche(m)]
                home, away = _equipes(event, vainqueurs.get(str(event.get("id")), []))
                if not home or not away:
                    continue
                debut = _heure(event.get("start_datetime"))
                if not debut:
                    continue
                ligne = _ligne(m) if a_ligne else None
                if a_ligne and ligne is None:
                    continue
                per = periode_match(sport, str(m.get("name") or ""), periode)
                base = {
                    "source": "Smarkets", "bookmaker": "smarkets", "sport": sport,
                    "ligue": None, "match_id": f"smarkets|{event.get('id')}",
                    "domicile": home, "exterieur": away, "debut": debut.isoformat(),
                    "collecte": moment, "joueur": None, "cle_marche": f"smarkets|{m.get('id')}",
                    "marche": interne, "periode": per, "ligne": ligne, "libelle": m.get("name"),
                }
                for contrat in contrats.get(str(m.get("id")), []):
                    if contrat.get("state_or_outcome") not in (None, "open"):
                        continue
                    issue = _issue(interne, contrat)
                    if not issue:
                        continue
                    carnet = _carnet(carnets.get(str(contrat.get("id"))) or {})
                    if not carnet:
                        # Une issue ouverte sans achat ou sans vente retire tout le marché,
                        # comme une ligne Betfair incomplète.
                        bruts.append({**base, "issue": issue, "achat": [], "vente": []})
                        continue
                    achat, vente = carnet
                    bruts.append({**base, "issue": issue, "achat": [achat], "vente": [vente]})
    justes = reference_echange(bruts, "Smarkets")
    return justes, {"ok": not client.erreurs or bool(justes), "erreurs": list(client.erreurs),
                    "requetes": client.requetes, "matchs": matchs}
