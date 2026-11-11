"""Cotes DraftKings, en référence seulement : matchs NBA, NHL, NFL, MLB et props joueurs NBA et NHL.

Matthieu ne peut pas parier chez DraftKings. Les lignes servent à comparer la probabilité juste (marge retirée,
même méthode que Pinnacle) à celle de Pinnacle. Aucun sélecteur, aucun pari.

API publique du site (``sportscontent``), sans clé ni compte. Relevé du 10/11/2026 depuis GitHub Actions (sortie aux
États-Unis, ``scripts/sonde_sources_us.py``) : HTTP 200 en 0,1 à 0,3 s pour chaque appel, avec ``curl_cffi`` en
Chrome. Une réponse = trois listes à plat : ``events`` (nom « Extérieur @ Domicile », ``participants`` avec
``venueRole``), ``markets`` (``eventId``, ``marketType.name``) et ``selections`` (``marketId``, ``trueOdds`` en cote
décimale, ``points``, ``outcomeType`` Home / Away / Over / Under, joueur dans ``participants``).

- ``/leagues/<ligue>`` : les matchs et leurs trois marchés principaux (Moneyline, Spread ou Puck Line, Total),
  prolongation comprise ;
- ``/leagues/<ligue>/categories/<c>/subcategories/<s>`` : un marché plus/moins par joueur (``PROPS``).

Le MLB était hors saison au relevé (un seul pari de long terme) : ses matchs seront lus avec les mêmes noms de
marché, sauf le handicap (« Run Line », jamais observé, donc pas encore traduit).

``SOURCE_DRAFTKINGS`` vaut ``direct`` ou ``off`` (défaut : ``off``, pour que les tests du cycle n'appellent pas le
site). La collecte GitHub le passe à ``direct``. Onze appels par cycle au plus. Un 403, un corps vide, un JSON
illisible ou un délai devient un avertissement court, sans en-tête, sans cookie et sans adresse.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from cotes.direct.fanduel import obtenir
from cotes.joueurs import cle_joueur
from cotes.marge import marge, proba_justes
from cotes.temps import instant_utc

_echeance = None
MODES = ("direct", "off")
HOTE = "https://sportsbook-nash.draftkings.com/api/sportscontent/dkusnj/v1"
# sport interne -> (ligue affichée, identifiant de ligue DraftKings)
LIGUES = {"basket": ("NBA", 42648), "hockey": ("NHL", 42133),
          "football_americain": ("NFL", 88808), "baseball": ("MLB", 84240)}
# type de marché DraftKings -> marché interne (noms relevés le 10/11/2026)
MARCHES_MATCH = {"Moneyline": "VAINQUEUR", "Spread": "HANDICAP", "Puck Line": "HANDICAP", "Total": "TOTAL"}
# sport -> (catégorie, sous-catégorie, statistique commune de cotes/joueurs.py) ; identifiants relevés le 10/11/2026
PROPS = {
    "basket": ((1215, 12488, "Points"), (1216, 12492, "Rebounds"), (1217, 12495, "Assists"),
               (1218, 12497, "ThreePoints")),
    "hockey": ((1189, 12040, "ShotsOnGoal"), (1675, 16213, "Points"), (1676, 16215, "Assists")),
}
DELAI_S = 20


def mode(environ=None) -> str:
    """``off`` si la variable est absente ou inconnue. ``direct`` interroge DraftKings."""
    env = os.environ if environ is None else environ
    valeur = str(env.get("SOURCE_DRAFTKINGS", "off")).strip().lower()
    return valeur if valeur in MODES else "off"


def surnom(nom: str) -> str:
    """« MIL Bucks » -> « Bucks », « NY Knicks » -> « Knicks » : DraftKings abrège la ville, pas le surnom.

    Le surnom seul se rapproche mieux du nom complet des autres sources (« Milwaukee Bucks ») que l'abréviation,
    et il est unique dans une ligue."""
    mots = str(nom or "").split()
    if len(mots) >= 2 and mots[0].isalpha() and mots[0].isupper() and len(mots[0]) <= 4:
        return " ".join(mots[1:])
    return " ".join(mots)


def session_defaut():
    """Chrome simulé (curl_cffi, comme la sonde) ; à défaut la session simple de FanDuel."""
    try:
        from curl_cffi.requests import Session
        return Session(impersonate="chrome")
    except Exception:  # noqa: BLE001 - bibliothèque absente : on essaie sans
        from cotes.direct.fanduel import session_defaut as simple
        return simple()


def _cote(selection: dict) -> float | None:
    c = selection.get("trueOdds")
    if isinstance(c, bool) or not isinstance(c, (int, float)) or not c > 1:
        return None
    return float(c)


def _nombre(x) -> float | None:
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    return float(x)


def evenements(doc, maintenant: datetime, heures: float) -> dict[str, dict]:
    """Matchs à deux équipes pas encore commencés, dans l'horizon : id -> {domicile, exterieur, debut}."""
    out: dict[str, dict] = {}
    for e in (doc.get("events") if isinstance(doc, dict) else None) or []:
        if not isinstance(e, dict) or e.get("eventParticipantType") != "TwoTeam" or e.get("status") != "NOT_STARTED":
            continue
        debut = instant_utc(e.get("startEventDate"))
        if debut is None or not 0 < (debut - maintenant).total_seconds() <= heures * 3600:
            continue
        roles = {p.get("venueRole"): str(p.get("name") or "").strip()
                 for p in e.get("participants") or [] if isinstance(p, dict)}
        if not roles.get("Home") or not roles.get("Away") or e.get("id") is None:
            continue
        out[str(e["id"])] = {"domicile": surnom(roles["Home"]), "exterieur": surnom(roles["Away"]),
                             "domicile_source": roles["Home"], "exterieur_source": roles["Away"], "debut": debut}
    return out


def _par_marche(doc) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for s in (doc.get("selections") if isinstance(doc, dict) else None) or []:
        if isinstance(s, dict) and s.get("marketId") is not None:
            out.setdefault(str(s["marketId"]), []).append(s)
    return out


def _paire(selections: list[dict], roles: tuple[str, str]) -> tuple[dict, dict] | None:
    """Les deux sélections d'un marché à deux issues (une par rôle), ou None s'il n'est pas complet et simple."""
    par_role: dict[str, dict] = {}
    for s in selections:
        role = s.get("outcomeType")
        if role in roles:
            if role in par_role:
                return None                       # plusieurs lignes dans le même marché : pas un marché simple
            par_role[role] = s
    if set(par_role) != set(roles) or len(selections) != 2:
        return None
    return par_role[roles[0]], par_role[roles[1]]


def lignes_match(doc, matchs: dict[str, dict]) -> tuple[list[dict], int]:
    """Vainqueur, handicap et total de chaque match, marge retirée. Second nombre : marchés laissés de côté."""
    lignes, ignores = [], 0
    selections = _par_marche(doc)
    for m in (doc.get("markets") if isinstance(doc, dict) else None) or []:
        if not isinstance(m, dict) or str(m.get("eventId")) not in matchs:
            continue
        marche = MARCHES_MATCH.get(str((m.get("marketType") or {}).get("name")))
        if not marche:
            ignores += 1
            continue
        paire = _paire(selections.get(str(m.get("id")), []), ("Over", "Under") if marche == "TOTAL" else ("Home", "Away"))
        cotes = [_cote(s) for s in paire] if paire else []
        if not paire or None in cotes:
            ignores += 1
            continue
        ligne = None
        if marche == "TOTAL":
            a, b = _nombre(paire[0].get("points")), _nombre(paire[1].get("points"))
            if a is None or a != b:
                ignores += 1
                continue
            ligne, issues = a, ("PLUS", "MOINS")
        else:
            issues = ("DOM", "EXT")
            if marche == "HANDICAP":
                a, b = _nombre(paire[0].get("points")), _nombre(paire[1].get("points"))
                if a is None or b is None or abs(a + b) > 1e-9:
                    ignores += 1
                    continue
                ligne = a                           # handicap du domicile, pour les deux issues (cotes/reglement.py)
        justes = proba_justes(cotes, complet=True)
        if not justes:
            ignores += 1
            continue
        for issue, cote, pi in zip(issues, cotes, justes):
            lignes.append({"eventId": str(m["eventId"]), "marche": marche, "ligne": ligne, "issue": issue,
                           "cote": round(cote, 4), "proba_juste": round(pi, 6), "cote_juste": round(1 / pi, 4),
                           "marge_draftkings": round(marge(cotes), 4)})
    return lignes, ignores


def props_de(doc, matchs: dict[str, dict], stat: str) -> tuple[list[dict], int]:
    """Paires plus/moins d'un joueur d'une sous-catégorie, marge retirée. Second nombre : marchés laissés de côté."""
    props, ignores = [], 0
    selections = _par_marche(doc)
    for m in (doc.get("markets") if isinstance(doc, dict) else None) or []:
        if not isinstance(m, dict) or str(m.get("eventId")) not in matchs:
            continue
        paire = _paire(selections.get(str(m.get("id")), []), ("Over", "Under"))
        if not paire:
            ignores += 1
            continue
        joueurs = {str((p or {}).get("name") or "").strip() for s in paire for p in (s.get("participants") or [])[:1]
                   if isinstance(p, dict) and p.get("type") == "Player"}
        cotes = [_cote(s) for s in paire]
        a, b = _nombre(paire[0].get("points")), _nombre(paire[1].get("points"))
        if len(joueurs) != 1 or None in cotes or a is None or a != b or not cle_joueur(next(iter(joueurs))):
            ignores += 1
            continue
        justes = proba_justes(cotes, complet=True)
        if not justes:
            ignores += 1
            continue
        for issue, cote, pi in zip(("PLUS", "MOINS"), cotes, justes):
            props.append({"eventId": str(m["eventId"]), "marche": f"JOUEUR:{stat}", "joueur": next(iter(joueurs)),
                          "ligne": a, "issue": issue, "cote": round(cote, 4), "proba_juste": round(pi, 6),
                          "cote_juste": round(1 / pi, 4), "marge_draftkings": round(marge(cotes), 4)})
    return props, ignores


def _timeout(plafond: float) -> float:
    echeance = _echeance
    if echeance is None or not hasattr(echeance, "timeout"):
        return plafond
    return echeance.timeout(plafond)


def _temps_restant() -> bool:
    return _echeance is None or _echeance.ok()


def collecter(sports: set[str] | None = None, heures: float = 36, session=None,
              maintenant: datetime | None = None, environ=None) -> tuple[list[dict], dict]:
    """Lignes de match et lignes ``JOUEUR:`` à venir. Une panne de transport ne lève pas."""
    try:
        return _collecter(sports, heures, session, maintenant, environ)
    except Exception as e:  # noqa: BLE001 - le cycle continue, les autres sources aussi
        return [], {"ok": False, "erreurs": [type(e).__name__], "avertissements": [type(e).__name__],
                    "requetes": 0, "matchs": 0, "lignes": 0, "props": 0, "ignores": 0}


def _collecter(sports, heures, session, maintenant, environ) -> tuple[list[dict], dict]:
    vide = {"ok": True, "erreurs": [], "avertissements": [], "requetes": 0, "matchs": 0, "lignes": 0, "props": 0,
            "ignores": 0}
    if mode(environ) == "off":
        return [], {**vide, "mode": "off"}
    maintenant = maintenant or datetime.now(timezone.utc)
    if maintenant.tzinfo is None:
        maintenant = maintenant.replace(tzinfo=timezone.utc)
    voulu = set(sports) if sports is not None else set(LIGUES)
    session = session or session_defaut()
    avertissements: list[str] = []
    requetes = ignores = n_matchs = n_props = 0
    lignes: list[dict] = []
    moment = maintenant.isoformat(timespec="seconds")

    def lire(chemin: str, nom: str):
        nonlocal requetes
        if not _temps_restant():
            avertissements.append("budget")
            return None
        requetes += 1
        _code, doc, err = obtenir(session, f"{HOTE}{chemin}", _timeout(DELAI_S))
        if err:
            avertissements.append(f"{nom} {err}")
        return doc if isinstance(doc, dict) else None

    for sport, (ligue, identifiant) in LIGUES.items():
        if sport not in voulu or "budget" in avertissements:
            continue
        doc = lire(f"/leagues/{identifiant}", ligue)
        if doc is None:
            continue
        matchs = evenements(doc, maintenant, heures)
        n_matchs += len(matchs)

        def complete(l: dict) -> dict:
            m = matchs[l["eventId"]]
            return {"source": "draftkings", "bookmaker": "draftkings", "sport": sport, "ligue": ligue,
                    "match_id": f"draftkings|{l['eventId']}", "domicile": m["domicile"], "exterieur": m["exterieur"],
                    "debut": m["debut"].isoformat(timespec="seconds"), "periode": "MATCH", "collecte": moment,
                    **{k: v for k, v in l.items() if k != "eventId"}}

        du_match, laisses = lignes_match(doc, matchs)
        ignores += laisses
        lignes.extend(complete(l) for l in du_match)
        for categorie, sous_categorie, stat in PROPS.get(sport, ()) if matchs else ():
            page = lire(f"/leagues/{identifiant}/categories/{categorie}/subcategories/{sous_categorie}", f"{ligue} {stat}")
            if page is None:
                continue
            props, laisses = props_de(page, matchs, stat)
            ignores += laisses
            n_props += len(props)
            lignes.extend(complete(p) for p in props)
    erreurs = [a for a in avertissements if a != "budget"]
    return lignes, {"ok": not erreurs, "erreurs": erreurs[:8], "avertissements": avertissements[:8],
                    "requetes": requetes, "matchs": n_matchs, "lignes": len(lignes) - n_props, "props": n_props,
                    "ignores": ignores}
