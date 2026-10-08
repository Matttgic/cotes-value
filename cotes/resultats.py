"""Résultats des matchs pour le règlement des paris, validés par des sources fiables.

Les flux de résultats PulseScore des bookmakers français ne disent pas quand un match est fini (Winamax,
Unibet : dernier score vu en direct ; Betclic, NetBet : aucun état ; Unibet : champ score parfois faux).
On règle donc avec des « validateurs », des bookmakers dont le flux marque explicitement les matchs
terminés (sonde du 6/10/2026) : Betfair (Orbit, terminé quand tous ses marchés sont réglés), DraftKings,
Unibet UK, Interwetten, BetMGM (« Finished ») et PMU quand il marque le match terminé.

ESPN (API publique, sans clé) est un validateur de plus et la source des scores par période (mi-temps au
football : fiche du match ouverte seulement quand un pari en a besoin ; quart-temps NFL, tiers-temps NHL…).

Un match est retrouvé chez chaque validateur par les noms d'équipes (dans un sens ou l'autre) et l'heure
de début. Le score n'est retenu que si au moins SOURCES_MIN validateurs ont le match terminé et qu'ils
donnent tous le même score (ou une nette majorité d'entre eux, voir MAJORITE_MIN) ; les corners, seulement si au moins SOURCES_MIN sources les donnent identiques
(Betfair renvoie 0-0 quand il ne les compte pas). Sinon le pari attend, puis passe « à régler à la main ».
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta

import requests

from .correspondance import normaliser, ressemblance

VALIDATEURS = ["orbitxch", "draftkings", "unibet-uk", "interwetten-de", "betmgm", "pmu"]
ECART_HEURE_MIN = 45
RESSEMBLANCE_MIN = 0.75
# tennis : l'heure annoncée n'est qu'une estimation (ordre de passage, pluie) ; jusqu'à 12 h d'écart si les
# deux joueurs sont clairement les mêmes (cas réel : Charaeva – Zheng annoncé 02:00, joué à 11:05)
ECART_TENNIS_H = 12
RESSEMBLANCE_TENNIS_LOIN = 0.9
PAGES_MAX = 15
SOURCES_MIN = 2
# sources en désaccord : le score majoritaire l'emporte s'il est donné par au moins MAJORITE_MIN sources et
# au moins 3 fois plus de sources que les autres scores (une source isolée se trompe : Unibet UK 0-0 au lieu
# de 1-1, Interwetten 29-28 au lieu de 30-28 ou le score du temps réglementaire au hockey)
MAJORITE_MIN = 3
# une seule source suffit si elle est très fiable et que le match a commencé depuis au moins 6 heures
# (tennis : ESPN est souvent la seule à donner les sets)
SOURCES_FIABLES = {"espn", "orbitxch", "draftkings", "apisports"}
# tennis : Betfair et PMU gardent un score en cours de match (sets, voire points) sur des matchs finis
TENNIS_EXCLUES = {"orbitxch", "pmu"}
TENNIS_FIABLES = {"espn"}                         # seule source unique acceptée (Betfair : score figé)
DELAI_SOURCE_UNIQUE_H = 6
ESPN = "https://site.api.espn.com/apis/site/v2/sports"
ESPN_LIGUES = {"football": ["soccer/all"], "hockey": ["hockey/nhl"], "basket": ["basketball/nba", "basketball/wnba"],
               "football_americain": ["football/nfl", "football/college-football"], "baseball": ["baseball/mlb"],
               "tennis": ["tennis/atp", "tennis/wta"]}
# terminés dans le temps réglementaire au football (une prolongation fausserait le score « match ») ;
# prolongation et tirs au but compris ailleurs
ESPN_FINAUX = {"STATUS_FULL_TIME", "STATUS_FINAL"}
ESPN_FEMININES = {"basketball/wnba"}           # ligues féminines dont ESPN ne marque pas les noms
# tennis : abandon en cours de match (règles d'abandon de chaque bookmaker, cotes/reglement.py)
ESPN_ABANDONS = {"STATUS_RETIRED"}
REPORT_MAX_J = 7


def _heure(s) -> datetime | None:
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def termine(r: dict) -> bool:
    st = r.get("settlement") or {}
    info = str((r.get("score") or {}).get("info") or "").strip().lower()
    return bool(st.get("final")) or info in ("final", "finished", "ended", "ft")


def _corners(r: dict) -> tuple[int, int] | None:
    foot = (r.get("statistics") or {}).get("football") or {}
    try:
        return int(foot["home"]["corners"]), int(foot["away"]["corners"])
    except (KeyError, TypeError, ValueError):
        return None


def libelles_periodes(sport: str, libelles: list | None, n: int) -> list[str]:
    """Libellés des périodes ; quand la source n'en donne pas, déduits du rang (au-delà du temps
    réglementaire : prolongation, tirs au but, manches supplémentaires)."""
    if libelles and len(libelles) == n:
        return [str(x).upper() for x in libelles]
    reg = {"football": 2, "hockey": 3, "basket": 4, "football_americain": 4, "baseball": 9, "handball": 2}.get(sport)
    out = []
    for i in range(n):
        if reg is None or i < reg:
            out.append(str(i + 1))
        elif sport == "hockey":
            out.append("OT" if i == reg else "SO")
        elif sport == "baseball":
            out.append("X")
        elif sport == "football":
            out.append("ET" if i < reg + 2 else "PEN")
        else:
            out.append("OT")
    return out


def lire(client, bookmaker: str, sport_api: str, sport: str, depuis: datetime) -> list[dict]:
    """Matchs terminés d'un validateur, du plus récent jusqu'à `depuis` (début des matchs)."""
    out = []
    for page in range(1, PAGES_MAX + 1):
        d = client.get(f"{bookmaker}/results", {"sport": sport_api, "page": page, "limit": 30})
        if not d or not d.get("results"):
            break
        for r in d["results"]:
            sc = r.get("score") or {}
            try:
                score = (int(sc.get("home")), int(sc.get("away")))
            except (TypeError, ValueError):
                continue
            if not termine(r):
                continue
            ps = r.get("periodScores") or {}
            periodes = list(zip(ps.get("home") or [], ps.get("away") or []))
            out.append({"source": bookmaker, "sport": sport, "domicile": r.get("home"), "exterieur": r.get("away"),
                        "debut": _heure(r.get("startTime")), "score": score, "periodes": periodes,
                        "libelles": libelles_periodes(sport, ps.get("labels"), len(periodes)),
                        "corners": _corners(r)})
        dernier = _heure(d["results"][-1].get("startTime"))
        if not d.get("hasNextPage") or (dernier and dernier < depuis):
            break
    return out


ERREURS_ESPN: list[str] = []          # lectures ESPN en échec (pour le journal du cycle)


def _espn_json(chemin: str, params: dict | None = None) -> dict | None:
    try:
        r = requests.get(f"{ESPN}/{chemin}", params=params, timeout=20)
        if r.ok:
            return r.json()
        ERREURS_ESPN.append(f"{chemin} : HTTP {r.status_code}")
    except (requests.RequestException, ValueError) as e:
        ERREURS_ESPN.append(f"{chemin} : {repr(e)[:150]}")
    return None


# API-Sports (clé gratuite API_SPORTS_KEY, 100 requêtes par jour et par sport) : résultats du monde entier
# avec le score par période (basket européen, handball, KHL, championnats féminins…). Une requête = tous les
# matchs d'un jour ; lue seulement pour les paris que les autres sources n'ont pas réglés, et gardée en
# cache (donnees/apisports.json) pour tenir dans le quota.
APISPORTS = {"football": "https://v3.football.api-sports.io/fixtures",
             "basket": "https://v1.basketball.api-sports.io/games",
             "hockey": "https://v1.hockey.api-sports.io/games",
             "handball": "https://v1.handball.api-sports.io/games"}
APISPORTS_FINAUX = {"FT", "AOT", "AET", "AP", "PEN"}
APISPORTS_FRAIS_MIN = 60           # jour courant ou veille : relu au plus toutes les heures
APISPORTS_ANCIEN_H = 6             # jours plus anciens : toutes les 6 heures
ERREURS_APISPORTS: list[str] = []


def _ap_paire(x) -> tuple[int, int] | None:
    """« 2-1 », {"home": 2, "away": 1} -> (2, 1)."""
    try:
        if isinstance(x, str):
            a, b = x.split("-")
            return int(a), int(b)
        if isinstance(x, dict) and x.get("home") is not None and x.get("away") is not None:
            return int(x["home"]), int(x["away"])
    except (TypeError, ValueError):
        pass
    return None


def apisports_match(sport: str, g: dict) -> dict | None:
    """Un match terminé d'API-Sports au format des validateurs (score final, périodes réglementaires puis
    prolongation ; tirs au but non détaillés : le score final, qui compte le but du vainqueur, suffit)."""
    fx = g.get("fixture") or g
    if ((fx.get("status") or {}).get("short")) not in APISPORTS_FINAUX:
        return None
    t = g.get("teams") or {}
    dom, ext = (t.get("home") or {}).get("name"), (t.get("away") or {}).get("name")
    sc = g.get("scores") or {}
    periodes, libelles = [], []
    if sport == "football":
        score = _ap_paire(g.get("goals"))
        mt, ft, prol = (_ap_paire(sc.get(k)) for k in ("halftime", "fulltime", "extratime"))
        if mt and ft:
            periodes, libelles = [mt, (ft[0] - mt[0], ft[1] - mt[1])], ["1", "2"]
            if prol:
                periodes.append(prol)
                libelles.append("ET")
    elif sport == "basket":
        h, a = sc.get("home") or {}, sc.get("away") or {}
        score = _ap_paire({"home": h.get("total"), "away": a.get("total")})
        for k, lib in (("quarter_1", "1"), ("quarter_2", "2"), ("quarter_3", "3"), ("quarter_4", "4"), ("over_time", "OT")):
            q = _ap_paire({"home": h.get(k), "away": a.get(k)})
            if q:
                periodes.append(q)
                libelles.append(lib)
    else:                                          # hockey, handball
        score = _ap_paire(sc)
        per = g.get("periods") or {}
        for k, lib in (("first", "1"), ("second", "2"), ("third", "3"), ("overtime", "OT")):
            q = _ap_paire(per.get(k))
            if q:
                periodes.append(q)
                libelles.append(lib)
    if not score or not dom or not ext:
        return None
    return {"source": "apisports", "sport": sport, "domicile": dom, "exterieur": ext,
            "debut": _heure(fx.get("date")), "score": score, "periodes": periodes, "libelles": libelles,
            "corners": None}


def lire_apisports(cle: str, sport: str, jours: list[str], cache: dict, maintenant: datetime,
                   http=requests) -> tuple[list[dict], dict]:
    """Matchs terminés d'API-Sports pour ces jours (AAAA-MM-JJ, UTC). `cache` (modifié) : « sport|jour » ->
    {"lu": heure, "matchs": [...]}, relu seulement s'il est trop vieux. Renvoie (matchs, quota restant)."""
    out, quota = [], {}
    for jour in sorted(set(jours)):
        k = f"{sport}|{jour}"
        entree = cache.get(k) or {}
        lu = _heure(entree.get("lu"))
        recent = jour >= (maintenant - timedelta(days=1)).strftime("%Y-%m-%d")
        limite = timedelta(minutes=APISPORTS_FRAIS_MIN) if recent else timedelta(hours=APISPORTS_ANCIEN_H)
        if not lu or maintenant - lu > limite:
            try:
                r = http.get(APISPORTS[sport], params={"date": jour, "timezone": "UTC"},
                             headers={"x-apisports-key": cle}, timeout=60)
                d = r.json()
                quota[sport] = r.headers.get("x-ratelimit-requests-remaining")
                if d.get("errors"):
                    ERREURS_APISPORTS.append(f"{sport} {jour} : {str(d['errors'])[:150]}")
                else:
                    matchs = [m for m in (apisports_match(sport, g) for g in d.get("response") or []) if m]
                    entree = {"lu": maintenant.isoformat(timespec="seconds"),
                              "matchs": [{**m, "debut": m["debut"].isoformat() if m["debut"] else None} for m in matchs]}
                    cache[k] = entree
            except (requests.RequestException, ValueError) as e:
                ERREURS_APISPORTS.append(f"{sport} {jour} : {repr(e)[:150]}")
        for m in entree.get("matchs") or []:
            out.append({**m, "debut": _heure(m["debut"]), "score": tuple(m["score"]),
                        "periodes": [tuple(x) for x in m["periodes"]]})
    return out, quota


def jours_a_lire(paris: list[dict], regles: set[str], maintenant: datetime) -> dict[str, list[str]]:
    """Sport -> jours (UTC) des paris pas encore réglés par les autres sources, commencés depuis 2 h."""
    out: dict[str, set[str]] = {}
    for p in paris:
        if p["statut"] not in ("en_cours", "a_regler") or p["match_id"] in regles or p["sport"] not in APISPORTS:
            continue
        debut = _heure(p.get("reporte_au") or p.get("debut"))
        if debut and timedelta(hours=2) < maintenant - debut < timedelta(days=7):
            out.setdefault(p["sport"], set()).add(debut.strftime("%Y-%m-%d"))
    return {k: sorted(v) for k, v in out.items()}


def elaguer_cache_apisports(cache: dict, maintenant: datetime) -> dict:
    garde = (maintenant - timedelta(days=8)).strftime("%Y-%m-%d")
    return {k: v for k, v in cache.items() if k.split("|")[-1] >= garde}


def lire_espn(sport: str, depuis: datetime, maintenant: datetime, lire_json=_espn_json) -> list[dict]:
    """Matchs ESPN (calendrier jour par jour, dates américaines : un jour de marge de chaque côté). Terminés,
    abandons au tennis (« abandon »), et pas encore joués (« a_venir » : pour reconnaître un match reporté,
    jamais pour régler)."""
    out, vus = [], set()
    jour = (depuis - timedelta(days=1)).date()
    while jour <= maintenant.date() + timedelta(days=1):
        for ligue in ESPN_LIGUES.get(sport, []):
            d = lire_json(f"{ligue}/scoreboard", {"dates": f"{jour:%Y%m%d}", "limit": 1000}) or {}
            for e in d.get("events") or []:
                # tennis : un tournoi par « event », ses matchs dans groupings[].competitions
                comps = [c for g in e.get("groupings") or [] for c in g.get("competitions") or []] \
                    or e.get("competitions") or []
                for c in comps:
                    cid = c.get("id") or e.get("id")
                    etat = ((c.get("status") or {}).get("type") or {}).get("name")
                    if cid in vus:
                        continue
                    r = _espn_match(sport, c, e, ligue)
                    if r:
                        vus.add(cid)
                        r["abandon"] = sport == "tennis" and etat in ESPN_ABANDONS
                        r["a_venir"] = etat not in ESPN_FINAUX and not r["abandon"]
                        out.append(r)
        jour += timedelta(days=1)
    return out


def _espn_match(sport: str, c: dict, e: dict, ligue: str) -> dict | None:
    comp = c.get("competitors") or []
    if len(comp) != 2:
        return None
    eq = {x.get("homeAway"): x for x in comp}
    dom, ext = (eq["home"], eq["away"]) if {"home", "away"} <= set(eq) else (comp[0], comp[1])
    nom = lambda x: ((x.get("team") or {}).get("displayName") or (x.get("athlete") or {}).get("displayName"))  # noqa: E731
    lignes = [[l.get("value") for l in x.get("linescores") or []] for x in (dom, ext)]
    periodes = [(int(a), int(b)) for a, b in zip(*lignes) if a is not None and b is not None]
    try:
        if sport == "tennis":                      # score = sets gagnés
            score = (sum(a > b for a, b in periodes), sum(b > a for a, b in periodes))
        else:
            score = (int(dom["score"]), int(ext["score"]))
    except (KeyError, TypeError, ValueError):
        return None
    if not nom(dom) or not nom(ext):
        return None
    if ligue in ESPN_FEMININES:                    # ESPN n'écrit pas « Women », les bookmakers si (« (W) »)
        nom = (lambda f: lambda x: f(x) and f"{f(x)} Women")(nom)
    return {"source": "espn", "sport": sport, "domicile": nom(dom), "exterieur": nom(ext),
            "debut": _heure(c.get("date") or e.get("date")), "score": score, "periodes": periodes,
            "libelles": libelles_periodes(sport, None, len(periodes)), "corners": None,
            "espn": f"{ligue.split('/')[0]}/all/summary" if sport == "football" else None,
            "espn_id": c.get("id") or e.get("id")}


def periodes_espn(r: dict, lire_json=_espn_json) -> list[tuple[int, int]]:
    """Mi-temps d'un match de football ESPN (fiche du match)."""
    if not r.get("espn"):
        return []
    d = lire_json(r["espn"], {"event": r["espn_id"]}) or {}
    c = ((d.get("header") or {}).get("competitions") or [{}])[0]
    eq = {x.get("homeAway"): x for x in c.get("competitors") or []}
    try:
        lignes = [[int(l.get("displayValue")) for l in eq[k].get("linescores") or []] for k in ("home", "away")]
    except (KeyError, TypeError, ValueError):
        return []
    return list(zip(*lignes))


def completer_periodes(p: dict, resultat: dict, enregistrements: list[dict], lire_json=_espn_json) -> dict:
    """Ajoute les mi-temps ESPN à un résultat validé qui n'en a pas, quand un pari en a besoin et que leur
    somme redonne bien le score validé."""
    if resultat.get("periodes") or p["sport"] != "football":
        return resultat
    for r in retrouver(p, [e for e in enregistrements if e["source"] == "espn"]):
        inverse = r["domicile"] != next((e["domicile"] for e in enregistrements if e.get("espn_id") == r["espn_id"]), None)
        periodes = periodes_espn(r, lire_json)
        if inverse:
            periodes = [(b, a) for a, b in periodes]
        cand = {**r, "score": resultat["score"], "periodes": periodes}
        if len(periodes) == 2 and _periodes_coherentes(p["sport"], cand):
            return {**resultat, "periodes": periodes, "libelles": libelles_periodes("football", None, 2)}
    return resultat


def _oriente(r: dict, inverse: bool) -> dict:
    if not inverse:
        return r
    sw = lambda t: (t[1], t[0]) if t else t       # noqa: E731
    return {**r, "domicile": r["exterieur"], "exterieur": r["domicile"], "score": sw(r["score"]),
            "periodes": [sw(p) for p in r["periodes"]], "corners": sw(r["corners"])}


def _avec_marqueurs(nom: str, modele: str) -> str:
    """Reporte sur `nom` les marqueurs U21 / Women du nom `modele` (Pinnacle ne les écrit pas dans le nom)."""
    _, fem, jeunes = normaliser(modele)
    _, fem_n, jeunes_n = normaliser(nom)
    for j in sorted(jeunes - jeunes_n):
        nom = f"{nom} {j.upper()}"
    return f"{nom} Women" if fem and not fem_n else nom


def _noms(p: dict) -> tuple[list[str], list[str]]:
    """Noms possibles de chaque équipe du pari : ceux du bookmaker et ceux de la référence (Pinnacle, en
    anglais : « England », « Czechia », là où le bookmaker écrit « Angleterre », « Rép.Tchèque »)."""
    dom, ext = [p["domicile"]], [p["exterieur"]]
    ref = str(p.get("match_reference") or "")
    if ref.count(" - ") == 1:
        a, b = (_avec_marqueurs(x.strip(), m) for x, m in zip(ref.split(" - "), (p["domicile"], p["exterieur"])))
        # la référence peut être dans l'autre sens que le bookmaker
        direct = (ressemblance(p["domicile"], a), ressemblance(p["exterieur"], b))
        inverse = (ressemblance(p["domicile"], b), ressemblance(p["exterieur"], a))
        if (min(inverse), sum(inverse)) > (min(direct), sum(direct)):
            a, b = (_avec_marqueurs(x.strip(), m) for x, m in zip(ref.split(" - ")[::-1], (p["domicile"], p["exterieur"])))
        dom.append(a)
        ext.append(b)
    return dom, ext


def retrouver(p: dict, enregistrements: list[dict]) -> list[dict]:
    """Le match du pari chez chaque validateur (le meilleur par source), orienté comme le pari. Un match
    reporté est cherché à sa nouvelle date (`reporte_au`)."""
    debut = _heure(p.get("reporte_au") or p.get("debut"))
    if not debut:
        return []
    dom, ext = _noms(p)
    def proche(noms: list[str], x: str) -> float:
        # espoirs / féminines : le marqueur doit être le même des deux côtés (sinon équipe A ou masculine)
        return max((ressemblance(n, x) for n in noms if normaliser(n)[1:] == normaliser(x)[1:]), default=0.0)

    meilleurs: dict[str, tuple[float, float, dict]] = {}
    for r in enregistrements:
        if r.get("a_venir"):
            continue
        ecart = abs((r["debut"] - debut).total_seconds()) if r["sport"] == p["sport"] and r["debut"] else None
        tennis_large = p["sport"] == "tennis" and ecart is not None and ecart <= ECART_TENNIS_H * 3600
        if ecart is None or (ecart > ECART_HEURE_MIN * 60 and not tennis_large):
            continue
        direct = min(proche(dom, r["domicile"]), proche(ext, r["exterieur"]))
        inverse = min(proche(dom, r["exterieur"]), proche(ext, r["domicile"]))
        score = max(direct, inverse)
        if score < (RESSEMBLANCE_TENNIS_LOIN if ecart > ECART_HEURE_MIN * 60 else RESSEMBLANCE_MIN):
            continue
        # à ressemblance égale, l'heure la plus proche (même affiche deux fois dans la fenêtre)
        if r["source"] not in meilleurs or (score, -ecart) > meilleurs[r["source"]][:2]:
            meilleurs[r["source"]] = (score, -ecart, _oriente(r, inverse > direct))
    return [r for _, _, r in meilleurs.values()]


def _periodes_coherentes(sport: str, r: dict) -> bool:
    if not r["periodes"]:
        return False
    if sport == "tennis":                          # jeux par set : le score en sets doit s'en déduire
        return (sum(a > b for a, b in r["periodes"]), sum(b > a for a, b in r["periodes"])) == r["score"]
    d, e = sum(x[0] for x in r["periodes"]), sum(x[1] for x in r["periodes"])
    if (d, e) == r["score"]:
        return True
    # hockey : le vainqueur des tirs au but est crédité d'un but dans le score final ; seulement si le temps
    # réglementaire est à égalité et que personne n'a marqué en prolongation
    if sport != "hockey" or abs(d - r["score"][0]) + abs(e - r["score"][1]) != 1 or len(r["periodes"]) < 3:
        return False
    reg = r["periodes"][:3]
    return sum(x[0] for x in reg) == sum(x[1] for x in reg) and all(a == b == 0 for a, b in r["periodes"][3:])


def _retenus(p: dict, enregistrements: list[dict]) -> list[dict]:
    """Les sources du match retenues pour le valider (au tennis : score final plausible, en sets)."""
    trouves = retrouver(p, enregistrements)
    if p["sport"] == "tennis":
        trouves = [r for r in trouves if r["source"] not in TENNIS_EXCLUES
                   and (r.get("abandon") or (max(r["score"]) in (2, 3) and min(r["score"]) < max(r["score"])))]
    return trouves


def reporte(p: dict, enregistrements: list[dict]) -> datetime | None:
    """Nouvelle date du match d'un pari s'il a été reporté (même affiche pas encore jouée, programmée plus
    tard dans les REPORT_MAX_J jours) : le pari reste en cours au lieu de passer « à régler »."""
    debut = _heure(p.get("debut"))
    if not debut:
        return None
    dom, ext = _noms(p)
    proche = lambda noms, x: max(ressemblance(n, x) for n in noms)  # noqa: E731
    for r in enregistrements:
        if not r.get("a_venir") or r["sport"] != p["sport"] or not r["debut"]:
            continue
        if not timedelta(hours=1) < r["debut"] - debut <= timedelta(days=REPORT_MAX_J):
            continue
        if max(min(proche(dom, r["domicile"]), proche(ext, r["exterieur"])),
               min(proche(dom, r["exterieur"]), proche(ext, r["domicile"]))) >= RESSEMBLANCE_TENNIS_LOIN:
            return r["debut"]
    return None


def _majoritaires(trouves: list[dict]) -> list[dict]:
    """Les sources qui donnent le score retenu : toutes d'accord, une nette majorité (MAJORITE_MIN), ou au
    moins deux sources dont une fiable (ESPN, API-Sports…) contre une seule source isolée."""
    compte = Counter(r["score"] for r in trouves)
    if not compte:
        return []
    score, n = compte.most_common(1)[0]
    autres = len(trouves) - n
    avec_fiable = any(r["source"] in SOURCES_FIABLES for r in trouves if r["score"] == score)
    if autres and (n < MAJORITE_MIN or n < 3 * autres) and not (n >= 2 and autres == 1 and avec_fiable):
        return []
    return [r for r in trouves if r["score"] == score]


def _sans_zeros_finaux(periodes: list) -> tuple:
    """Périodes sans les 0-0 de fin (manche non jouée au baseball, prolongation blanche) : certaines sources
    les listent, d'autres non, sans que ce soit un désaccord."""
    out = list(periodes)
    while out and tuple(out[-1]) == (0, 0):
        out.pop()
    return tuple(tuple(x) for x in out)


def consensus(p: dict, enregistrements: list[dict], maintenant: datetime | None = None) -> dict | None:
    """Résultat validé du match d'un pari, ou None (pas encore terminé chez un validateur, ou désaccord)."""
    trouves = _majoritaires(_retenus(p, enregistrements))
    if not trouves:
        return None
    if len(trouves) < SOURCES_MIN:
        debut = _heure(p.get("reporte_au") or p.get("debut"))
        fiables = TENNIS_FIABLES if p["sport"] == "tennis" else SOURCES_FIABLES
        seule_fiable = trouves[0]["source"] in fiables and maintenant and debut and \
            maintenant - debut >= timedelta(hours=DELAI_SOURCE_UNIQUE_H)
        if not seule_fiable:
            return None
    score = trouves[0]["score"]
    avec_periodes = sorted((r for r in trouves if _periodes_coherentes(p["sport"], r)),
                           key=lambda r: -len(r["periodes"]))
    if len({_sans_zeros_finaux(r["periodes"]) for r in avec_periodes}) > 1:
        avec_periodes = []                           # sources en désaccord sur les périodes : on s'en passe
    corners = [r["corners"] for r in trouves if r["corners"] is not None and r["corners"] != (0, 0)]
    base = avec_periodes[0] if avec_periodes else None
    return {"sport": p["sport"], "score": score, "final": True,
            "periodes": base["periodes"] if base else [], "libelles": base["libelles"] if base else [],
            "corners": corners[0] if len(corners) >= SOURCES_MIN and len(set(corners)) == 1 else None,
            "sources": sorted(r["source"] for r in trouves)}


def a_lire(paris: list[dict], maintenant: datetime, apres_debut_h: float = 2) -> dict[str, datetime]:
    """Sports à lire chez les validateurs -> début du plus ancien match encore à régler."""
    out: dict[str, datetime] = {}
    for p in paris:
        if p["statut"] not in ("en_cours", "a_regler"):
            continue
        debut = _heure(p.get("debut"))
        if debut and maintenant - debut > timedelta(hours=apres_debut_h) and maintenant - debut < timedelta(days=7):
            out[p["sport"]] = min(out.get(p["sport"], debut), debut - timedelta(hours=1))
    return out


def diagnostic(p: dict, enregistrements: list[dict]) -> dict:
    """Pourquoi le match d'un pari n'est pas (encore) réglé : sources trouvées et leurs scores."""
    trouves, retenus = retrouver(p, enregistrements), _retenus(p, enregistrements)
    return {"match": f'{p["domicile"]} – {p["exterieur"]}', "sport": p["sport"], "debut": p.get("debut"),
            "sources": {r["source"]: {"score": r["score"], "periodes": r["periodes"]} for r in trouves},
            "retenues": sorted(r["source"] for r in retenus),
            "raison": "aucune source" if not retenus else
            ("sources en désaccord" if not _majoritaires(retenus) else "pas assez de sources ou de périodes")}
