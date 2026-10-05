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
import re
import time
from datetime import datetime, timedelta, timezone

import requests

BASE = "https://gamma-api.polymarket.com"
TAG_MATCHS = 100639            # étiquette « games » : événements de match (pas les paris à long terme)

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
    for i in range(essais):
        try:
            r = requests.get(BASE + path, params=params, timeout=60)
            if r.status_code == 200:
                return r.json()
        except (requests.RequestException, ValueError):
            pass
        time.sleep(2 * (i + 1))
    return None


def _liste(x):
    if isinstance(x, str):
        try:
            return json.loads(x)
        except ValueError:
            return []
    return x or []


def evenements(heures: int = 48) -> list[dict]:
    """Événements de match non clos qui commencent dans les `heures` prochaines heures.

    La date de fin Polymarket vaut l'heure du match pour la plupart des sports, mais début + 7 jours
    au tennis : on interroge large puis on filtre sur l'heure réelle du match (startTime).
    """
    maintenant = datetime.now(timezone.utc)
    out: list[dict] = []
    # fenêtre 1 : fin = heure du match ; fenêtre 2 : fin = heure du match + 7 jours
    for decalage in (timedelta(0), timedelta(days=7)):
        offset = 0
        while True:
            page = _get("/events", {"tag_id": TAG_MATCHS, "active": "true", "closed": "false", "limit": 100,
                                    "offset": offset,
                                    "end_date_min": (maintenant + decalage - timedelta(hours=1)).isoformat(),
                                    "end_date_max": (maintenant + decalage + timedelta(hours=heures)).isoformat()})
            if not page:
                break
            out += page
            if len(page) < 100 or offset >= 1900:
                break
            offset += 100
    out = list({str(e["id"]): e for e in out}.values())
    limite = maintenant + timedelta(hours=heures)

    def dans_horizon(e: dict) -> bool:
        d = e.get("startTime") or e.get("endDate")
        try:
            return datetime.fromisoformat(d.replace("Z", "+00:00")) <= limite
        except (AttributeError, ValueError):
            return False

    gardes = {str(e["id"]) for e in out if not e.get("parentEventId") and dans_horizon(e)}
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
        equipes = {t.get("ordering"): t.get("name") for t in principal.get("teams") or []}
        dom, ext = equipes.get("home"), equipes.get("away")
        if not (dom and ext):
            m = re.match(r"^(?:.*?: )?(.+?) vs\.? (.+?)(?: \(BO\d\))?(?: - .*)?$", principal.get("title", ""))
            if not m:
                continue
            dom, ext = m.group(1), m.group(2)
        marches = [mk for e in membres for mk in e.get("markets") or []]
        types = {mk.get("sportsMarketType") or "" for mk in marches}
        sport = _sport(types, principal.get("seriesSlug") or "",
                       [t.get("label", "") for t in principal.get("tags") or []])
        debut = (marches[0].get("gameStartTime") if marches else None) or principal.get("startTime") or principal.get("endDate")
        if debut and " " in debut:
            debut = debut.replace(" ", "T").replace("+00", "+00:00")
        base = {"source": "polymarket", "sport": sport, "ligue": principal.get("seriesSlug"),
                "match_id": racine, "domicile": dom, "exterieur": ext, "debut": debut, "collecte": maintenant,
                "joueur": None, "lien": f"https://polymarket.com/event/{principal.get('slug')}"}
        lignes += _lignes(marches, base, dom, ext, sport)
    _normaliser_1n2(lignes)
    return lignes


def _issue_equipe(nom: str | None, dom: str, ext: str) -> str | None:
    if nom is None:
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
        t = mk.get("sportsMarketType")
        cible = TYPES.get(t)
        if not cible or not mk.get("acceptingOrders") or mk.get("closed"):
            continue
        bid, ask = mk.get("bestBid"), mk.get("bestAsk")
        if bid is None or ask is None or not (0 < float(bid) <= float(ask) < 1):
            continue
        bid, ask = float(bid), float(ask)
        issues = _liste(mk.get("outcomes"))
        if len(issues) != 2:
            continue
        marche, periode = cible
        ligne = mk.get("line")
        commun = {**base, "periode": periode, "ecart_achat_vente": round(ask - bid, 4),
                  "liquidite": round(float(mk.get("liquidityNum") or 0), 2), "cle_marche": f"pm|{mk.get('id')}"}
        mid0 = (bid + ask) / 2
        paires = [(issues[0], mid0, bid, ask), (issues[1], 1 - mid0, 1 - ask, 1 - bid)]
        if issues == ["Yes", "No"]:
            groupe = mk.get("groupItemTitle") or ""
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
                s = re.search(r"(\d+)\s*-\s*(\d+)", mk.get("question", ""))
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
            if marche in ("TOTAL_EQUIPE", "CORNERS_TOTAL_EQUIPE"):
                q = (mk.get("question") or "").split(":")[-1]
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
        if i0 is None:
            continue
        if marche.endswith("HANDICAP") and ligne is not None:
            ligne = float(ligne) if i0 == "DOM" else -float(ligne)      # notre ligne = handicap du domicile
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
        if len(g) == 3:
            s = sum(l["proba_juste"] for l in g)
            for l in g:
                l["proba_juste_brute"] = l["proba_juste"]
                l["proba_juste"] = round(l["proba_juste"] / s, 5)
                l["cote_juste"] = round(1 / l["proba_juste"], 4)
