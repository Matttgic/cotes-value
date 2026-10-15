"""Secours The Odds API : scores terminés, cache partagé et quatre quotas gratuits.

Documentation : https://the-odds-api.com/liveapi/guides/v4/#get-scores
Seuls les marchés dont le score fourni a le bon sens sont autorisés. Les comptes
ne sont jamais traités comme plusieurs sources de résultats indépendantes.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import datetime, timedelta, timezone

import requests

from . import resultats
from .correspondance import avec_marqueurs_ligue, normaliser, ressemblance

BASE = "https://api.the-odds-api.com/v4/sports"
COUT = 2
BUDGET_JOUR = 16                       # par compte : <= 496 crédits sur 31 jours
BUDGET_MOIS = 500
MAX_APPELS = 4                         # requêtes scores, tous comptes confondus, par cycle
FRAICHEUR = timedelta(hours=3)
REESSAI = timedelta(hours=1)
GARDE = timedelta(days=8)
MARCHES = {"VAINQUEUR", "RESULTAT_1N2", "DOUBLE_CHANCE", "DRAW_NO_BET",
           "HANDICAP", "HANDICAP_3", "TOTAL", "TOTAL_DOM", "TOTAL_EXT",
           "CORRECT_SCORE", "BOTH_TEAMS_TO_SCORE"}


def _canon(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", s).split())


# Associations explicites seulement : « Premier League », « Super League » ou
# « Bundesliga » sans sport/pays ne servent pas à deviner une compétition.
# Football : coupes, phases finales et championnats à playoffs avec prolongation
# sont exclus, car /scores ne distingue pas 90 minutes et prolongations.
LIGUES = {
    "football": {
        "soccer_epl": ["Angleterre Premier League", "England Premier League", "EPL"],
        "soccer_efl_champ": ["Angleterre Championship", "England Championship"],
        "soccer_france_ligue_one": ["France Ligue 1", "Ligue 1", "Ligue 1 McDonald’s®"],
        "soccer_france_ligue_two": ["France Ligue 2", "Ligue 2", "Ligue 2 BKT"],
        "soccer_germany_bundesliga": ["Allemagne Bundesliga", "Allemagne Bundesliga 1"],
        "soccer_germany_bundesliga2": ["Allemagne Bundesliga 2"],
        "soccer_germany_liga3": ["Allemagne 3. Liga", "Allemagne Bundesliga 3"],
        "soccer_italy_serie_a": ["Italie Serie A"],
        "soccer_spain_la_liga": ["Espagne LaLiga", "Espagne Primera Division", "LaLiga"],
        "soccer_japan_j_league": ["Japon J-League", "Japon J1 League"],
        "soccer_korea_kleague1": ["Corée du Sud K-League", "Corée du Sud K-League 1"],
        "soccer_norway_eliteserien": ["Norvège Eliteserien", "Eliteserien"],
        "soccer_finland_veikkausliiga": ["Finlande Veikkausliiga", "Veikkausliiga"],
        "soccer_sweden_allsvenskan": ["Allsvenskan", "Suède Allsvenskan"],
        "soccer_sweden_superettan": ["Superettan", "Suède Superettan"],
        "soccer_poland_ekstraklasa": ["Pologne Ekstraklasa", "Ekstraklasa"],
        "soccer_portugal_primeira_liga": ["Portugal Primeira Liga", "Liga Betclic"],
        "soccer_turkey_super_league": ["Turquie Super Lig", "Süper Lig"],
        "soccer_brazil_campeonato": ["Brésil Série A", "Brazil Serie A"],
        "soccer_brazil_serie_b": ["Brésil Série B", "Brazil Serie B"],
    },
    "basket": {
        "basketball_nba": ["NBA"],
        "basketball_nba_preseason": ["NBA Preseason", "NBA Présaison"],
        "basketball_wnba": ["WNBA"],
        "basketball_euroleague": ["Euroligue", "Euroleague"],
        "basketball_nbl": ["NBL", "Australie NBL"],
        "basketball_ncaab": ["NCAAB", "NCAA Basketball"],
        "basketball_wncaab": ["WNCAAB", "NCAA Basketball Women"],
    },
    "football_americain": {
        "americanfootball_nfl": ["NFL"],
        "americanfootball_nfl_preseason": ["NFL Preseason", "NFL Présaison"],
        "americanfootball_ncaaf": ["NCAAF", "NCAA Football"],
    },
    # Pour le hockey : vainqueur du match seulement. Pas de score réglementaire
    # ni de totaux (le détail du but crédité aux tirs au but est absent).
    "hockey": {
        "icehockey_nhl": ["NHL"],
        "icehockey_nhl_preseason": ["NHL Preseason", "NHL Présaison"],
        "icehockey_sweden_hockey_league": ["SHL", "Suède SHL"],
        "icehockey_sweden_allsvenskan": ["HockeyAllsvenskan", "Suède HockeyAllsvenskan"],
    },
    "handball": {
        "handball_germany_bundesliga": ["Allemagne Bundesliga 1 H.", "Allemagne Bundesliga", "Bundesliga"],
    },
}
INDEX = {(sport, _canon(alias)): cle for sport, ligues in LIGUES.items()
         for cle, aliases in ligues.items() for alias in aliases}
FEMININES = {"basketball_wnba", "basketball_wncaab"}


def _heure(s) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return d.astimezone(timezone.utc) if d.tzinfo else None
    except (TypeError, ValueError):
        return None


def competition(p: dict) -> str | None:
    cle = INDEX.get((p.get("sport"), _canon(p.get("ligue"))))
    noms = [avec_marqueurs_ligue(p.get(k), p.get("ligue")) for k in ("domicile", "exterieur")]
    if any(normaliser(n)[2] for n in noms):
        return None
    if any(normaliser(n)[1] for n in noms) and cle not in FEMININES:
        return None
    return cle


def compatible(p: dict) -> bool:
    if p.get("periode") != "MATCH" or p.get("marche") not in MARCHES:
        return False
    return p.get("sport") != "hockey" or p.get("marche") == "VAINQUEUR"


def _capture(g: dict, cle: str, maintenant: datetime) -> dict | None:
    """Copie seulement les champs utiles d'un résultat explicitement terminé."""
    if not isinstance(g, dict) or g.get("completed") is not True or g.get("sport_key") != cle:
        return None
    debut = _heure(g.get("commence_time"))
    dom, ext = g.get("home_team"), g.get("away_team")
    if not isinstance(dom, str) or not isinstance(ext, str) or dom == ext or not g.get("id"):
        return None
    if not debut or not timedelta(0) < maintenant - debut < GARDE:
        return None
    try:
        scores = g.get("scores") or []
        if len(scores) != 2 or {s["name"] for s in scores} != {dom, ext}:
            return None
        if any(not re.fullmatch(r"\d+", str(s["score"])) for s in scores):
            return None
        sc = {s["name"]: int(s["score"]) for s in scores}
    except (TypeError, KeyError, ValueError):
        return None
    return {"id": str(g["id"]), "sport_key": cle, "domicile": dom, "exterieur": ext,
            "debut": debut.isoformat(), "score": [sc[dom], sc[ext]],
            "lu": maintenant.isoformat(timespec="seconds")}


def retrouver(p: dict, matchs: list[dict], cle: str) -> dict | None:
    """Deux noms forts, même compétition, heure à +/- 30 min et candidat unique."""
    debut = _heure(p.get("reporte_au") or p.get("debut"))
    if not debut:
        return None
    dom, ext = resultats._noms(p)
    if cle in FEMININES:
        dom = [n if normaliser(n)[1] else f"{n} Women" for n in dom]
        ext = [n if normaliser(n)[1] else f"{n} Women" for n in ext]

    def proche(noms, nom):
        if cle in FEMININES and not normaliser(nom)[1]:
            nom = f"{nom} Women"
        return max((ressemblance(n, nom) for n in noms if normaliser(n)[1:] == normaliser(nom)[1:]), default=0)

    candidats = []
    for m in matchs:
        h = _heure(m.get("debut"))
        if m.get("sport_key") != cle or not h or abs(h - debut) > timedelta(minutes=30):
            continue
        direct = min(proche(dom, m["domicile"]), proche(ext, m["exterieur"]))
        inverse = min(proche(dom, m["exterieur"]), proche(ext, m["domicile"]))
        if max(direct, inverse) < 0.9 or direct == inverse:
            continue
        score = tuple(m["score"] if direct > inverse else m["score"][::-1])
        if resultats.plausible(p["sport"], score) and (p["sport"] != "hockey" or score[0] != score[1]):
            candidats.append({**m, "score": score})
    return candidats[0] if len(candidats) == 1 else None


class Client:
    def __init__(self, cles: list[str], cache: dict, maintenant: datetime, http=requests):
        self.cache, self.maintenant, self.http = cache, maintenant, http
        self.erreurs: list[str] = []
        self.appels = 0
        self.comptes = []
        uniques = list(dict.fromkeys(c.strip() for c in cles if c and c.strip()))
        anciens = cache.get("comptes", {})
        cache["comptes"] = {}
        for i, cle in enumerate(uniques):
            empreinte = hashlib.sha256(cle.encode()).hexdigest()[:16]
            etat = anciens.get(empreinte, {})
            if etat.get("mois") != maintenant.strftime("%Y-%m"):
                etat = {"mois": maintenant.strftime("%Y-%m"), "credits_mois": 0}
            if etat.get("jour") != maintenant.strftime("%Y-%m-%d"):
                etat.update(jour=maintenant.strftime("%Y-%m-%d"), credits_jour=0)
            etat["numero"] = i + 1
            cache["comptes"][empreinte] = etat
            self.comptes.append((cle, etat))

    @staticmethod
    def _quota(r, etat):
        for entete, champ in (("x-requests-remaining", "restant"), ("x-requests-used", "utilise_api")):
            try:
                etat[champ] = max(0, int(r.headers[entete]))
            except (KeyError, TypeError, ValueError):
                pass

    def _get(self, chemin, cle, etat, params=None):
        try:
            r = self.http.get(f"{BASE}{chemin}", params={"apiKey": cle, **(params or {})}, timeout=20)
            self._quota(r, etat)
            if r.status_code != 200:
                self.erreurs.append(f"compte {etat['numero']} : HTTP {r.status_code}")
                if r.status_code in (401, 403):
                    etat["valide"] = False
                return None
            d = r.json()
            if isinstance(d, list):
                return d
            self.erreurs.append(f"compte {etat['numero']} : réponse inattendue")
        except (requests.RequestException, ValueError):
            # Une exception requests contient souvent l'URL, donc la clé. Jamais
            # de repr(exception), de corps d'erreur ou d'URL dans les journaux.
            self.erreurs.append(f"compte {etat['numero']} : lecture indisponible")
        return None

    def verifier(self):
        """/sports est gratuit : vérifier chaque nouvelle clé sans lire de cotes."""
        for cle, etat in self.comptes:
            lu = _heure(etat.get("verifie"))
            if lu and (etat.get("valide") or self.maintenant - lu < REESSAI):
                continue
            etat["verifie"] = self.maintenant.isoformat(timespec="seconds")
            sports = self._get("/", cle, etat, {"all": "true"})
            etat["valide"] = sports is not None and all(isinstance(s, dict) and isinstance(s.get("key"), str)
                                                      for s in sports)
            if etat["valide"]:
                etat["sports"] = [s["key"] for s in sports if not s.get("has_outrights")]

    def scores(self, competition):
        for cle, etat in sorted(self.comptes, key=lambda c: c[1].get("credits_mois", 0)):
            if self.appels >= MAX_APPELS:
                break
            if not etat.get("valide") or competition not in etat.get("sports", []):
                continue
            if etat.get("restant", BUDGET_MOIS) < COUT or etat.get("credits_mois", 0) + COUT > BUDGET_MOIS \
                    or etat.get("credits_jour", 0) + COUT > BUDGET_JOUR:
                continue
            # Réserver même en cas de panne : un timeout peut avoir consommé les
            # crédits côté API. Les compteurs et quotas sont persistés.
            etat["credits_mois"] = etat.get("credits_mois", 0) + COUT
            etat["credits_jour"] = etat.get("credits_jour", 0) + COUT
            if "restant" in etat:
                etat["restant"] = max(0, etat["restant"] - COUT)
            self.appels += 1
            d = self._get(f"/{competition}/scores/", cle, etat, {"daysFrom": 3, "dateFormat": "iso"})
            if d is not None:
                return d
        return None


def collecter(paris: list[dict], deja: dict, enregistrements: list[dict], cles: list[str],
              cache: dict, maintenant: datetime, http=requests) -> tuple[dict, dict]:
    """Résultats compatibles manquants et bilan sans secrets. Modifie le cache."""
    client = Client(cles, cache, maintenant, http)
    client.verifier()
    ligues = cache.setdefault("ligues", {})
    for cle in list(ligues):
        entree = ligues[cle]
        entree["matchs"] = [m for m in entree.get("matchs", []) if _heure(m.get("debut"))
                            and maintenant - _heure(m["debut"]) < GARDE]
        lu = _heure(entree.get("essai"))
        if not entree["matchs"] and (not lu or maintenant - lu > GARDE):
            del ligues[cle]
    besoin = {}
    couverture = {"marche_non_couvert": 0, "competition_non_couverte": 0,
                  "deja_valide": 0, "trop_recent": 0, "hors_fenetre": 0, "eligibles": 0}
    for p in paris:
        debut = _heure(p.get("reporte_au") or p.get("debut"))
        if p.get("statut") not in ("en_cours", "a_regler") or not debut or debut > maintenant:
            continue
        if p["match_id"] in deja:
            couverture["deja_valide"] += 1
            continue
        if not compatible(p):
            couverture["marche_non_couvert"] += 1
            continue
        if maintenant - debut < timedelta(hours=6):
            couverture["trop_recent"] += 1
            continue
        if maintenant - debut >= GARDE:
            couverture["hors_fenetre"] += 1
            continue
        cle = competition(p)
        if cle:
            couverture["eligibles"] += 1
            besoin.setdefault(cle, []).append(p)
        else:
            couverture["competition_non_couverte"] += 1
    # La ligue la moins récemment interrogée passe d'abord, pour éviter qu'un
    # grand championnat monopolise le budget. Le cache sert aussi après 3 jours.
    for cle, ps in sorted(besoin.items(), key=lambda x: (ligues.get(x[0], {}).get("essai", ""), x[0])):
        entree = ligues.setdefault(cle, {"matchs": []})
        nouveaux = [p for p in ps if not retrouver(p, entree["matchs"], cle)]
        essai = _heure(entree.get("essai"))
        attente = FRAICHEUR if entree.get("ok") else REESSAI
        if not nouveaux or not any(maintenant - _heure(p.get("reporte_au") or p["debut"]) < timedelta(days=3)
                                  for p in nouveaux) or (essai and maintenant - essai < attente):
            continue
        avant = client.appels
        d = client.scores(cle)
        if client.appels == avant:
            continue
        entree.update(essai=maintenant.isoformat(timespec="seconds"), ok=d is not None)
        if d is not None:
            matchs = {m["id"]: m for m in entree["matchs"]}
            for g in d:
                m = _capture(g, cle, maintenant)
                if m:
                    matchs[m["id"]] = m
                elif isinstance(g, dict) and g.get("sport_key") == cle and g.get("id"):
                    matchs.pop(str(g["id"]), None)
            entree["matchs"] = list(matchs.values())
    valides, conflits = {}, 0
    for cle, ps in besoin.items():
        for p in ps:
            m = retrouver(p, ligues[cle]["matchs"], cle)
            if not m:
                continue
            autres = resultats.retrouver(p, enregistrements)
            if any(tuple(r["score"]) != m["score"] for r in autres):
                conflits += 1
                continue
            r = valides.setdefault(p["match_id"], {
                "sport": p["sport"], "score": m["score"], "final": True,
                "periodes": [], "libelles": [], "corners": None,
                "sources": ["theodds"], "id_paris_autorises": [],
                "preuve_source": {"source": "The Odds API", "event_id": m["id"], "sport_key": cle,
                                  "debut": m["debut"], "lu": m["lu"], "completed": True},
            })
            if r["score"] == m["score"]:
                r["id_paris_autorises"].append(p["id"])
    bilan = {"cles_configurees": len(client.comptes), "cles_valides": sum(bool(e.get("valide")) for _, e in client.comptes),
             "requetes_scores": client.appels, "competitions_manquantes": len(besoin),
             "matchs_valides": len(valides), "paris_compatibles": sum(len(r["id_paris_autorises"]) for r in valides.values()),
             "conflits": conflits, "erreurs": client.erreurs, "couverture": couverture,
             "comptes": [{k: e[k] for k in ("numero", "valide", "credits_jour", "credits_mois", "restant", "utilise_api")
                          if k in e} for _, e in client.comptes]}
    return valides, bilan
