"""Collecte des marchés de matchs Polymarket (API publique officielle « gamma », sans clé).

Polymarket est un marché de prédiction : chaque issue s'échange entre 0 et 1 $. La probabilité
« juste » retenue est le milieu entre le meilleur prix d'achat et le meilleur prix de vente
(pas de marge à retirer). L'écart achat/vente et la liquidité sont gardés pour écarter les
marchés trop peu échangés.

Un match = un événement principal (vainqueur) + des événements « enfants » (« More Markets »,
« Exact Score », « Total Corners »…) reliés par parentEventId.
"""
from __future__ import annotations

import json
import logging
import re
import time
from math import isfinite
from datetime import datetime, timedelta, timezone

import requests

BASE = "https://gamma-api.polymarket.com"
TAG_MATCHS = 100639            # étiquette « games » : événements de match (pas les paris à long terme)
ERREURS: list[str] = []
logger = logging.getLogger(__name__)
_bloque = False


def _erreur(message: str) -> None:
    if message not in ERREURS and len(ERREURS) < 30:
        ERREURS.append(message)
        logger.warning("Polymarket : %s", message)


def _nombre(x) -> float | None:
    if isinstance(x, bool):
        return None
    try:
        n = float(x)
        return n if isfinite(n) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _heure(s) -> datetime | None:
    try:
        t = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return t.astimezone(timezone.utc) if t.tzinfo is not None else None
    except (TypeError, ValueError):
        return None

# type de marché Polymarket -> (marché commun, période)
TYPES = {
    "moneyline": ("VAINQUEUR", "MATCH"), "child_moneyline": None,
    "spreads": ("HANDICAP", "MATCH"), "totals": ("TOTAL", "MATCH"),
    "first_half_totals": ("TOTAL", "MT1"), "second_half_totals": ("TOTAL", "MT2"),
    "soccer_team_totals": ("TOTAL_EQUIPE", "MATCH"), "soccer_first_half_team_totals": ("TOTAL_EQUIPE", "MT1"),
    "soccer_second_half_team_totals": ("TOTAL_EQUIPE", "MT2"),
    "both_teams_to_score": ("BOTH_TEAMS_TO_SCORE", "MATCH"),
    "both_teams_to_score_first_half": ("BOTH_TEAMS_TO_SCORE", "MT1"),
    "both_teams_to_score_second_half": ("BOTH_TEAMS_TO_SCORE", "MT2"),
    "soccer_halftime_result": ("RESULTAT_1N2", "MT1"), "soccer_second_half_result": ("RESULTAT_1N2", "MT2"),
    "soccer_exact_score": ("CORRECT_SCORE", "MATCH"),
    "total_corners": ("CORNERS_TOTAL", "MATCH"), "soccer_first_half_total_corners": ("CORNERS_TOTAL", "MT1"),
    "soccer_team_total_corners": ("CORNERS_TOTAL_EQUIPE", "MATCH"),
    "table_tennis_match_totals": ("JEUX_TOTAL", "MATCH"), "table_tennis_game_handicap": ("JEUX_HANDICAP", "MATCH"),
    "map_handicap": ("MAPS_HANDICAP", "MATCH"),
}


def _get(path: str, params: dict, essais: int = 3):
    global _bloque
    if _bloque:
        return None
    for i in range(essais):
        try:
            r = requests.get(BASE + path, params=params, timeout=60)
            if r.status_code == 200:
                try:
                    d = r.json()
                except ValueError:
                    _erreur("JSON invalide")
                    return None
                if isinstance(d, list):
                    return d
                _erreur("liste JSON attendue")
                return None
            _erreur(f"HTTP {r.status_code}")
            if r.status_code in (401, 403, 429):
                _bloque = True
                return None
            if r.status_code != 408 and not 500 <= r.status_code <= 599:
                return None
        except requests.RequestException:
            _erreur("réseau indisponible")
        if i + 1 < essais:
            time.sleep(2 * (i + 1))
    return None


def _liste(x):
    if isinstance(x, str):
        try:
            x = json.loads(x)
        except ValueError:
            return []
    return x if isinstance(x, list) else []


def dans_horizon(e: dict, maintenant: datetime | None = None, heures: int = 48) -> bool:
    maintenant = maintenant or datetime.now(timezone.utc)
    date = _heure(e.get("startTime") or e.get("endDate"))
    return bool(date and maintenant < date <= maintenant + timedelta(hours=heures))


def evenements(heures: int = 48) -> list[dict]:
    """Événements de match non clos qui commencent dans les `heures` prochaines heures.

    La date de fin Polymarket vaut l'heure du match pour la plupart des sports, mais début + 7 jours
    au tennis : on interroge large puis on filtre sur l'heure réelle du match (startTime).
    """
    global _bloque
    ERREURS.clear()
    _bloque = False
    maintenant = datetime.now(timezone.utc)
    out: list[dict] = []
    # fenêtre 1 : fin = heure du match ; fenêtre 2 : fin = heure du match + 7 jours
    for decalage in (timedelta(0), timedelta(days=7)):
        if _bloque:
            break
        offset = 0
        while True:
            debut_lecture = datetime.now(timezone.utc).isoformat(timespec="seconds")
            page = _get("/events", {"tag_id": TAG_MATCHS, "active": "true", "closed": "false", "limit": 100,
                                    "offset": offset,
                                    "end_date_min": (maintenant + decalage - timedelta(hours=1)).isoformat(),
                                    "end_date_max": (maintenant + decalage + timedelta(hours=heures)).isoformat()})
            if not page:
                break
            reception = datetime.now(timezone.utc).isoformat(timespec="seconds")
            valides = [e for e in page if isinstance(e, dict) and isinstance(e.get("id"), (str, int))
                       and not isinstance(e.get("id"), bool)]
            if len(valides) != len(page):
                _erreur("événements invalides dans une page")
            out += [{**e, "_collecte_debut": debut_lecture, "_collecte_recue": reception} for e in valides]
            if len(page) < 100:
                break
            if offset >= 1900:
                _erreur("liste d'événements tronquée (plafond de pagination)")
                break
            offset += 100
    out = list({str(e["id"]): e for e in out}.values())
    gardes = {str(e["id"]) for e in out if not e.get("parentEventId") and dans_horizon(e, maintenant, heures)}
    return [e for e in out if str(e.get("parentEventId") or e["id"]) in gardes]


ETIQUETTES = {"soccer": "football", "hockey": "hockey", "basketball": "basket", "tennis": "tennis",
              "table tennis": "tennis_de_table", "esports": "esport", "baseball": "baseball", "nfl": "football_americain",
              "nfl (all)": "football_americain", "cfb (all)": "football_americain", "rugby": "rugby",
              "handball": "handball", "volleyball": "volley", "cricket": "cricket", "mma": "mma", "ufc": "mma",
              "boxing": "boxe", "darts": "flechettes", "snooker": "snooker"}


def _sport(types: set[str], ligue: str, etiquettes: list[str] | None = None) -> str:
    for e in etiquettes or []:
        if e.lower() in ETIQUETTES:
            return ETIQUETTES[e.lower()]
    if any(t.startswith("soccer_") for t in types) or "corners" in " ".join(types):
        return "football"
    if any(t.startswith("table_tennis") for t in types):
        return "tennis_de_table"
    if any(t.startswith(("map_", "round_")) for t in types) or "child_moneyline" in types:
        return "esport"
    if any(t.startswith("tennis") for t in types) or ligue in ("atp", "wta"):
        return "tennis"
    return "autre"


def collecter(heures: int = 48) -> list[dict]:
    evs = evenements(heures)
    par_id = {str(e["id"]): e for e in evs}
    # regrouper chaque enfant sous son événement principal
    groupes: dict[str, list[dict]] = {}
    for e in evs:
        racine = str(e.get("parentEventId") or e["id"])
        groupes.setdefault(racine, []).append(e)
    maintenant = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lignes: list[dict] = []
    for racine, membres in groupes.items():
        principal = par_id.get(racine) or membres[0]
        teams = principal.get("teams")
        equipes = {t.get("ordering"): t.get("name") for t in teams
                   if isinstance(t, dict) and isinstance(t.get("ordering"), str)} if isinstance(teams, list) else {}
        dom, ext = equipes.get("home"), equipes.get("away")
        if not (isinstance(dom, str) and isinstance(ext, str) and dom and ext):
            titre = principal.get("title")
            m = re.match(r"^(?:.*?: )?(.+?) vs\.? (.+?)(?: \(BO\d\))?(?: - .*)?$", titre if isinstance(titre, str) else "")
            if not m:
                continue
            dom, ext = m.group(1), m.group(2)
        marches = []
        for e in membres:
            liste = e.get("markets")
            if not isinstance(liste, list):
                _erreur("liste de marchés absente ou invalide")
                continue
            for mk in liste:
                if not isinstance(mk, dict) or not isinstance(mk.get("sportsMarketType"), str):
                    _erreur("schéma de marché invalide")
                    continue
                marches.append({**mk, "_collecte_debut": e.get("_collecte_debut"),
                                "_collecte_recue": e.get("_collecte_recue")})
        types = {mk.get("sportsMarketType") or "" for mk in marches}
        sport = _sport(types, principal.get("seriesSlug") or "",
                       [t["label"] for t in _liste(principal.get("tags"))
                        if isinstance(t, dict) and isinstance(t.get("label"), str)])
        debut = (marches[0].get("gameStartTime") if marches else None) or principal.get("startTime") or principal.get("endDate")
        date = _heure(debut)
        if date is None:
            _erreur("événement sans date valide avec fuseau")
            continue
        debut = date.isoformat()
        base = {"source": "polymarket", "sport": sport, "ligue": principal.get("seriesSlug"),
                "match_id": racine, "domicile": dom, "exterieur": ext, "debut": debut, "collecte": maintenant,
                "joueur": None, "lien": f"https://polymarket.com/event/{principal.get('slug')}"}
        lignes += _lignes(marches, base, dom, ext, sport)
    _normaliser_1n2(lignes)
    return lignes


def _issue_equipe(nom: str | None, dom: str, ext: str) -> str | None:
    if not isinstance(nom, str):
        return None
    n = nom.lower()
    if n == dom.lower():
        return "DOM"
    if n == ext.lower():
        return "EXT"
    return None


def _lignes(marches, base, dom, ext, sport) -> list[dict]:
    out = []
    for mk in marches:
        if not isinstance(mk, dict):
            _erreur("marché non objet")
            continue
        t = mk.get("sportsMarketType")
        if not isinstance(t, str):
            continue
        cible = TYPES.get(t)
        if not cible or mk.get("acceptingOrders") is not True or mk.get("closed") is not False:
            continue
        if mk.get("bestBid") is None or mk.get("bestAsk") is None:
            continue          # carnet vide ou d'un seul côté : aucun prix à lire, ce n'est pas une erreur de données
        bid, ask = _nombre(mk.get("bestBid")), _nombre(mk.get("bestAsk"))
        if bid is None or ask is None or not (0 < bid <= ask < 1):
            _erreur("prix bid/ask invalides")
            continue
        issues = _liste(mk.get("outcomes"))
        if len(issues) != 2 or any(not isinstance(x, str) or not x for x in issues) or issues[0] == issues[1]:
            _erreur("issues de marché invalides")
            continue
        marche, periode = cible
        ligne = mk.get("line")
        liquidite = _nombre(mk.get("liquidityNum"))
        if liquidite is None or liquidite < 0:
            liquidite = 0.0
            _erreur("liquidité absente ou invalide : zéro retenu")
        commun = {**base, "periode": periode, "ecart_achat_vente": round(ask - bid, 4),
                  "liquidite": round(liquidite, 2), "cle_marche": f"pm|{mk.get('id')}"}
        if mk.get("_collecte_recue"):
            commun.update(collecte=mk["_collecte_recue"], collecte_recue=mk["_collecte_recue"],
                          collecte_debut=mk.get("_collecte_debut"))
        debut, lecture = _heure(commun.get("debut")), _heure(commun.get("collecte"))
        if debut is not None and lecture is not None and lecture >= debut:
            _erreur("prix lu après le coup d'envoi : rejet pré-match")
            continue
        mid0 = (bid + ask) / 2
        if not 0 < round(mid0, 5) < 1 or not 0 < round(1-mid0, 5) < 1:
            continue
        paires = [(issues[0], mid0, bid, ask), (issues[1], 1 - mid0, 1 - ask, 1 - bid)]
        if issues == ["Yes", "No"]:
            groupe = mk.get("groupItemTitle") or ""
            if not isinstance(groupe, str):
                continue
            if t == "moneyline" or t in ("soccer_halftime_result", "soccer_second_half_result"):
                # un marché oui/non par issue du 1N2 : on ne garde que « oui »
                issue = "NUL" if groupe.lower().startswith("draw") else _issue_equipe(groupe, dom, ext)
                if issue is None:
                    continue
                m1 = "RESULTAT_1N2" if (t != "moneyline" or sport == "football") else "VAINQUEUR"
                out.append({**commun, "marche": m1, "ligne": None, "issue": issue, "proba_juste": round(mid0, 5),
                            "achat": bid, "vente": ask})
                continue
            if t == "soccer_exact_score":
                question = mk.get("question")
                s = re.search(r"(\d+)\s*-\s*(\d+)", question if isinstance(question, str) else "")
                if not s:
                    continue
                out.append({**commun, "marche": marche, "ligne": None, "issue": f"{s.group(1)}-{s.group(2)}",
                            "proba_juste": round(mid0, 5), "achat": bid, "vente": ask})
                continue
            for nom, p, b, a in paires:   # les deux équipes marquent : OUI / NON
                out.append({**commun, "marche": marche, "ligne": None, "issue": "YES" if nom == "Yes" else "NO",
                            "proba_juste": round(p, 5), "achat": round(b, 4), "vente": round(a, 4)})
            continue
        if issues == ["Over", "Under"]:
            ligne = _nombre(ligne)
            if ligne is None:
                _erreur("ligne de total invalide")
                continue
            if marche in ("TOTAL_EQUIPE", "CORNERS_TOTAL_EQUIPE"):
                question = mk.get("question")
                if not isinstance(question, str):
                    continue
                q = question.split(":")[-1]
                cote = "DOM" if dom.lower() in q.lower() else ("EXT" if ext.lower() in q.lower() else None)
                if cote is None:
                    continue
                marche = marche.replace("EQUIPE", cote)
            for nom, p, b, a in paires:
                out.append({**commun, "marche": marche, "ligne": ligne, "issue": "PLUS" if nom == "Over" else "MOINS",
                            "proba_juste": round(p, 5), "achat": round(b, 4), "vente": round(a, 4)})
            continue
        # deux équipes / joueurs : vainqueur ou handicap (la ligne porte sur la 1re issue)
        i0 = _issue_equipe(issues[0], dom, ext)
        i1 = _issue_equipe(issues[1], dom, ext)
        if i0 is None or i1 is None or i0 == i1:
            continue
        if marche.endswith("HANDICAP"):
            ligne = _nombre(ligne)
            if ligne is None:
                _erreur("ligne de handicap invalide")
                continue
            ligne = ligne if i0 == "DOM" else -ligne      # notre ligne = handicap du domicile
        for nom, p, b, a in paires:
            out.append({**commun, "marche": marche, "ligne": ligne if marche.endswith("HANDICAP") else None,
                        "issue": _issue_equipe(nom, dom, ext), "proba_juste": round(p, 5),
                        "achat": round(b, 4), "vente": round(a, 4)})
    for l in out:
        l["cote_juste"] = round(1 / l["proba_juste"], 4) if l["proba_juste"] > 0 else None
    return out


def _normaliser_1n2(lignes: list[dict]) -> None:
    """Les trois marchés oui/non d'un 1N2 ne somment pas exactement à 1 : on les renormalise."""
    groupes: dict[tuple, list[dict]] = {}
    for l in lignes:
        if l["marche"] == "RESULTAT_1N2":
            groupes.setdefault((l["match_id"], l["periode"]), []).append(l)
    for g in groupes.values():
        dates = [_heure(l.get("collecte")) for l in g]
        avant_match = all(t is None or _heure(l.get("debut")) is None or t < _heure(l["debut"])
                          for l, t in zip(g, dates))
        if (len(g) == 3 and {l["issue"] for l in g} == {"DOM", "NUL", "EXT"}
                and avant_match
                and all(_nombre(l.get("proba_juste")) is not None and 0 < l["proba_juste"] < 1 for l in g)):
            s = sum(l["proba_juste"] for l in g)
            for l in g:
                l["proba_juste_brute"] = l["proba_juste"]
                l["proba_juste"] = round(l["proba_juste"] / s, 5)
                l["cote_juste"] = round(1 / l["proba_juste"], 4)
            if all(t is not None for t in dates):
                # Les trois prix composent la référence : son plus ancien prix borne sa fraîcheur.
                for l in g:
                    l["collecte"] = min(dates).isoformat(timespec="seconds")
        else:
            _erreur("1N2 incomplet ou issues dupliquées : référence rejetée")
            for l in g:
                l["proba_juste"] = l["cote_juste"] = None
