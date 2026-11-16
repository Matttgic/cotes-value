"""Cotes boostées : les promotions des bookmakers français comparées à la cote juste des références.

Lecture (``cotes/direct/boosts_sites.py`` › ``lire_tous``) : Winamax (route ``sport:100000`` du socket), Unibet (page
« cotes boostées »), NetBet (« Super Cotes ») et OlyBet (API swarm), lecteurs repris du dépôt cotes-boostees ; Genybet
et Betsson refusent les IP non françaises. Un boost : un intitulé libre (« Carlos Alcaraz gagne par au moins 6 jeux
d'écart »), la cote boostée, la cote d'avant quand le bookmaker la publie (Winamax, Unibet) et la mise maximale.

Évaluation. L'intitulé est traduit en pari standard quand il en est un (``traduire``) : victoire, match nul, double
chance, handicap (« gagne par au moins N jeux / buts / points d'écart »), mi-temps/fin (« gagne à la mi-temps et à
la fin du match »), total (« plus de 2,5 buts »), total d'une équipe, les deux équipes marquent, but ou total de
points d'un joueur. Le match est celui du même bookmaker (mêmes équipes, début à 90 minutes près), sinon celui d'un
autre bookmaker. Quand plusieurs périodes sont possibles (hockey : temps réglementaire par défaut chez Winamax), on
retient celle dont la cote habituelle du bookmaker vaut la cote d'avant le boost (« vérifié ») ; sans cote d'avant, la
première qui a une cote juste. La cote juste vient de la référence du match (Pinnacle d'abord, même
association que la comparaison), lue au même moment :

    value = cote boostée × probabilité juste − 1

Combinés (« … et … ») et intitulés non reconnus n'ont pas de cote juste. Restent affichés la hausse (cote boostée /
cote d'avant − 1) et la marge sous laquelle le boost serait rentable si la cote d'avant était la cote juste diminuée
de la marge de Winamax (1 − cote d'avant / cote boostée) : un repère, pas une mesure.

Verdict (``verdict``) : « jouer » ou « passer », affiché sur chaque boost. Avec une cote juste : jouer si la value est
positive. Sans cote juste mais avec la cote d'avant : jouer si la marge seuil dépasse la marge habituelle d'un
bookmaker français (``MARGE_HABITUELLE`` par sélection, cumulée sur les sélections d'un combiné) d'au moins
``MARGE_SECURITE`` ; sinon, ou sans cote d'avant, passer (impossible à juger).

Suivi (``suivre``) : un épisode par boost, de sa première lecture à la dernière. « Gain espéré » = mise maximale
(10 € si inconnue) × value, sur les boosts qui ont une cote juste : une espérance, pas un résultat (les boosts ne sont
pas encore réglés).

Boosts couverts (``couverts``) : un boost traduit en pari standard d'un marché que les surebets savent couvrir (1N2,
vainqueur, double chance, les deux équipes marquent, handicaps et totaux à demi-ligne), joué à sa mise maximale, et
chaque autre issue couverte à la meilleure cote française du cycle (mêmes cotes, mêmes garde-fous que
cotes/surebets.py › ``candidates``) pour le même retour. Si 1/cote boostée + Σ 1/cote de couverture < 1, le gain est
le même quel que soit le résultat :

    gain = mise du boost × cote boostée × (1 − Σ 1/cote) (aux arrondis des mises près)

« Vérifié » : le boost et chaque couverture ont une cote juste chez la référence du match et ces probabilités font 1
(``TOLERANCE_PARTITION`` près) ; si toutes en ont une et qu'elles ne font pas 1, la couverture est écartée (pas le même
marché). Suspect, affiché mais jamais suivi ni envoyé : rendement au-delà de ``RENDEMENT_COUVERT_SUSPECT``, ou de
``RENDEMENT_SUSPECT_NON_VERIFIE`` sans vérification. Garanti sur le papier seulement : la couverture peut bouger
avant d'être jouée.
"""
from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from datetime import datetime, timedelta
from itertools import product
from statistics import median

from . import controle as CT
from . import surebets as SB
from .comparaison import libelle_pari
from .correspondance import ressemblance
from .joueurs import stat_canonique
from .marches import cle, inverser
from .surebets import pivots

SEUIL_ALERTE = 0.03
MARGE_HABITUELLE = 0.06      # marge d'un bookmaker français sur une sélection (5 à 7 % sur les grands marchés)
MARGE_SECURITE = 0.05        # écart exigé au-delà de la marge habituelle quand la cote juste manque
TOLERANCE_COTE_AVANT = 0.011
ECART_COTE_AVANT_MAX = 0.08       # cote habituelle à plus de 8 % de la cote d'avant : pas le même pari
ASSOCIATION_MIN = 0.75
HEURE_MAX = timedelta(minutes=90)
MISE_DEFAUT = 10.0
GARDER_JOURS = 30
EPISODES_MAX = 1500
PAS_COUVERTURE = 0.1              # mises de couverture arrondies aux 10 centimes
RENDEMENT_COUVERT_SUSPECT = 0.5   # vérifié ou non, au-delà : presque sûrement une erreur de lecture ou de traduction

# Période par défaut chez Winamax quand l'intitulé n'en dit rien (cotes/pulsescore.py › REGLE_PAR_DEFAUT), puis l'autre.
PERIODES = {"hockey": ("TEMPS_REG", "MATCH"), "basket": ("MATCH", "TEMPS_REG"),
            "football_americain": ("MATCH", "TEMPS_REG"), "baseball": ("MATCH", "TEMPS_REG")}
AVEC_NUL = {"football", "handball", "rugby", "hockey"}
UNITES = {"jeu": "JEUX_", "jeux": "JEUX_", "set": "SETS_", "sets": "SETS_"}
_U = r"(?P<u>jeux|jeu|sets?|buts?|points?|paniers?|essais?)"
_N = r"(?P<n>\d+(?:[.,]\d+)?)"
_GAGNE = r"(?:gagne|s'impose|l'emporte|remporte(?: le match| la rencontre)?)"


def normaliser(texte: str | None) -> str:
    """Minuscules, sans accents, apostrophes droites, espaces simples, sans ponctuation finale."""
    s = unicodedata.normalize("NFKD", str(texte or "")).encode("ascii", "ignore").decode().lower()
    s = s.replace("’", "'").replace("`", "'")
    return re.sub(r"\s+", " ", s).strip(" .!?")


def _nombre(texte: str) -> float:
    return float(texte.replace(",", "."))


def _demi(x: float) -> bool:
    return abs(2 * x - round(2 * x)) < 1e-9 and round(2 * x) % 2 == 1


def _camp(sujet: str, domicile: str | None, exterieur: str | None) -> str | None:
    """« DOM » ou « EXT » si le sujet de l'intitulé est une des deux équipes (ou un des deux joueurs)."""
    sujet = re.sub(r"^(?:le |la |les |l')", "", sujet)
    a, b = ressemblance(sujet, domicile), ressemblance(sujet, exterieur)
    if max(a, b) < ASSOCIATION_MIN or a == b:
        return None
    return "DOM" if a > b else "EXT"


def _periodes(sport: str | None) -> tuple[str, ...]:
    return PERIODES.get(sport or "", ("MATCH",))


def _paris(marche: str, ligne, issue: str, sport, joueur=None) -> list[dict]:
    return [{"marche": marche, "periode": p, "ligne": ligne, "issue": issue, "joueur": joueur} for p in _periodes(sport)]


_VS = re.compile(r"\s*\((?:vs\.?|v|contre)\s+[^)]+\)")


def traduire(libelle: str, domicile: str | None, exterieur: str | None, sport: str | None) -> list[dict]:
    """Paris standard que l'intitulé peut désigner, du plus probable au moins probable ; vide si combiné ou inconnu."""
    t = normaliser(_VS.sub("", str(libelle or "")))          # « Lille (vs Arsenal) marque… » : l'adversaire en trop
    t = re.sub(r"^(?:cote boostee|super cote|boost)\s*:\s*", "", t).replace("les 2 equipes", "les deux equipes")
    m = re.fullmatch(rf"(?P<s>.+?) (?:gagne|mene) a la mi-temps et (?:gagne )?a la fin du match", t)
    if m:
        camp = _camp(m["s"], domicile, exterieur)
        return [{"marche": "HALF_TIME_FULL_TIME", "periode": "MATCH", "ligne": None, "issue": f"{camp}/{camp}",
                 "joueur": None}] if camp else []
    if re.search(r"\bet\b|&|\+|\bpuis\b", t):
        return []                                            # combiné : probabilité jointe inconnue
    m = (re.fullmatch(rf"(?P<s>.+?) {_GAGNE} (?:le match )?(?:par|avec) (?P<q>au moins|plus de) {_N} {_U} d'ecart", t)
         or re.fullmatch(rf"(?P<s>.+?) {_GAGNE} (?:le match )?par {_N} {_U} d'ecart (?P<q>ou plus)", t))
    if m:
        camp, n = _camp(m["s"], domicile, exterieur), _nombre(m["n"])
        ligne = n if _demi(n) else n - 0.5 if m["q"] in ("au moins", "ou plus") else n + 0.5
        if not camp or not _demi(ligne):
            return []
        marche = UNITES.get(m["u"], "") + "HANDICAP"
        return _paris(marche, -ligne if camp == "DOM" else ligne, camp, sport)
    m = re.fullmatch(rf"(?P<s>.+?) {_GAGNE}(?: le match| la rencontre| la partie)?", t) or \
        re.fullmatch(r"victoire (?:de |d'|du |des )(?P<s>.+)", t)
    if m:
        camp = _camp(m["s"], domicile, exterieur)
        if not camp:
            return []
        un_n_deux = _paris("RESULTAT_1N2", None, camp, sport)
        vainqueur = [{"marche": "VAINQUEUR", "periode": "MATCH", "ligne": None, "issue": camp, "joueur": None}]
        return un_n_deux + vainqueur if (sport or "") in AVEC_NUL else vainqueur + un_n_deux
    if re.fullmatch(r"(?:match )?nul|egalite", t):
        return _paris("RESULTAT_1N2", None, "NUL", sport)
    m = re.fullmatch(r"(?P<s>.+?) ou (?:match )?nul", t) or re.fullmatch(r"(?P<s>.+?) ne perd pas", t)
    if m:
        camp = _camp(m["s"], domicile, exterieur)
        return _paris("DOUBLE_CHANCE", None, "HOME_DRAW" if camp == "DOM" else "DRAW_AWAY", sport) if camp else []
    if re.fullmatch(r"les deux equipes marquent(?: dans le match)?", t):
        return _paris("BOTH_TEAMS_TO_SCORE", None, "YES", sport)
    if re.fullmatch(r"les deux equipes ne marquent pas", t):
        return _paris("BOTH_TEAMS_TO_SCORE", None, "NO", sport)
    m = re.fullmatch(rf"(?:il y a )?(?P<sens>plus|moins) de {_N} {_U}(?: dans le match| au total| dans la rencontre)?", t)
    if m:
        n = _nombre(m["n"])
        return _paris(UNITES.get(m["u"], "") + "TOTAL", n, "PLUS" if m["sens"] == "plus" else "MOINS", sport) \
            if _demi(n) else []
    m = re.fullmatch(rf"au moins {_N} {_U} dans le match", t)
    if m and float(_nombre(m["n"])).is_integer():
        return _paris(UNITES.get(m["u"], "") + "TOTAL", _nombre(m["n"]) - 0.5, "PLUS", sport)
    # « Le PSG gagne 1-0 », « Score exact 2-1 » : score exact, dans le sens domicile-extérieur
    m = re.fullmatch(r"(?P<s>.+?) (?:gagne|s'impose|l'emporte) (?P<a>\d{1,2}) ?[-–] ?(?P<b>\d{1,2})", t)
    if m and int(m["a"]) > int(m["b"]):
        camp = _camp(m["s"], domicile, exterieur)
        score = f'{m["a"]}-{m["b"]}' if camp == "DOM" else f'{m["b"]}-{m["a"]}'
        return [{"marche": "CORRECT_SCORE", "periode": "MATCH", "ligne": None, "issue": score, "joueur": None}] \
            if camp else []
    # « X marque … » : une équipe (total de l'équipe) ou un joueur (pari joueur) ; « X buteur »
    m = (re.fullmatch(r"(?P<s>.+?) marque (?:au moins un but|au moins 1 but|un but|a tout moment)", t)
         or re.fullmatch(r"(?P<s>.+?) (?:buteur|marque)(?: dans le match)?", t))
    if m:
        return _marque(m["s"], 0.5, "PLUS", "buts", domicile, exterieur, sport)
    m = re.fullmatch(rf"(?P<s>.+?) marque (?P<sens>plus|moins) de {_N} (?P<stat>buts?|points?|rebonds?|passes(?: decisives)?)", t)
    if m and _demi(_nombre(m["n"])):
        return _marque(m["s"], _nombre(m["n"]), "PLUS" if m["sens"] == "plus" else "MOINS", m["stat"], domicile,
                       exterieur, sport)
    m = re.fullmatch(r"(?P<s>.+?) (?:marque|realise|inscrit) (?:au moins )?(?P<n>\d+) "
                     r"(?P<stat>buts?|points?|rebonds?|passes(?: decisives)?|tirs cadres)(?: ou plus)?", t)
    if m and (" au moins " in f" {t} " or t.endswith("ou plus")):
        return _marque(m["s"], int(m["n"]) - 0.5, "PLUS", m["stat"], domicile, exterieur, sport)
    return []


def _marque(sujet, ligne, issue, stat, domicile, exterieur, sport) -> list[dict]:
    camp = _camp(sujet, domicile, exterieur)
    if camp and stat.startswith(("but", "point")):
        return _paris("TOTAL_DOM" if camp == "DOM" else "TOTAL_EXT", ligne, issue, sport)
    if camp:
        return []
    nom = stat_canonique(stat)
    return [{"marche": f"JOUEUR:{nom}", "periode": "MATCH", "ligne": ligne, "issue": issue, "joueur": sujet.title()}] \
        if nom else []


# --------------------------------------------------------------------------- évaluation

def _t(s) -> datetime | None:
    return CT._lue(s)


# Nom du bookmaker du boost -> ``source`` de ses lignes dans la collecte (cotes/pulsescore.py › NOMS).
SOURCES = {"Winamax": "Winamax", "Unibet": "Unibet", "NetBet": "NetBet", "OlyBet": "OlyBet"}


def matchs_francais(francais: list[dict]) -> dict[str, dict]:
    """Matchs français du cycle : bookmaker, équipes, début, sport et cotes par clé de pari."""
    out: dict[str, dict] = {}
    for l in francais:
        if not l.get("match_id"):
            continue
        m = out.setdefault(l["match_id"], {"match_id": l["match_id"], "source": l.get("source"),
                                           "domicile": l.get("domicile"), "exterieur": l.get("exterieur"),
                                           "debut": l.get("debut"), "sport": l.get("sport"), "ligue": l.get("ligue"),
                                           "lignes": {}})
        try:
            m["lignes"][cle(l)] = l
        except (KeyError, TypeError, ValueError):
            continue
    return out


def matchs_winamax(francais: list[dict]) -> dict[str, dict]:
    """Matchs Winamax du cycle (compatibilité)."""
    return {k: m for k, m in matchs_francais(francais).items() if m["source"] == "Winamax"}


def associer(boost: dict, matchs: dict[str, dict]) -> dict | None:
    """Le match du boost : d'abord chez le même bookmaker (mêmes équipes, dans cet ordre), sinon chez un autre (ordre
    indifférent : seule la cote juste de la référence sert alors) ; début à 90 minutes près."""
    debut = _t(boost.get("debut"))
    if debut is None or not boost.get("domicile") or not boost.get("exterieur"):
        return None
    source = SOURCES.get(boost.get("bookmaker"))
    meilleur = None
    for m in matchs.values():
        d = _t(m.get("debut"))
        if d is None or abs(d - debut) > HEURE_MAX:
            continue
        direct = min(ressemblance(boost["domicile"], m.get("domicile")), ressemblance(boost["exterieur"], m.get("exterieur")))
        meme = m.get("source") == source
        score = direct if meme else max(direct, min(ressemblance(boost["domicile"], m.get("exterieur")),
                                                    ressemblance(boost["exterieur"], m.get("domicile"))))
        if score >= ASSOCIATION_MIN and (meilleur is None or (meme, score) > meilleur[0]):
            meilleur = ((meme, score), m)
    return meilleur[1] if meilleur else None


def _cle(p: dict):
    try:
        return cle(p)
    except (KeyError, TypeError, ValueError):
        return None


def choisir(candidats: list[dict], lignes: dict, cote_avant: float | None,
            justes: dict | None = None) -> tuple[dict | None, dict | None]:
    """(pari retenu, sa cote habituelle chez le bookmaker du boost).

    Avec la cote d'avant et les cotes du même bookmaker : celui dont la cote habituelle vaut la cote d'avant, puis celui
    qui en est proche (8 %) ; s'il n'existe qu'à une tout autre cote, ce n'est pas lui. Sinon (cote d'avant inconnue,
    match lu chez un autre bookmaker) : le premier candidat qui a une cote juste chez la référence (``justes``), à
    défaut le premier."""
    if cote_avant and lignes:
        avec = [(c, lignes.get(_cle(c))) for c in candidats]
        for c, l in avec:
            if l and abs(l["cote"] - cote_avant) <= TOLERANCE_COTE_AVANT:
                return c, l
        for c, l in avec:
            if l and abs(l["cote"] / cote_avant - 1) <= ECART_COTE_AVANT_MAX:
                return c, l
        if any(l for _, l in avec):
            return None, None
    for c in candidats:
        if justes and _cle(c) in justes:
            return c, None
    return (candidats[0], None) if candidats else (None, None)


STATS = {"Goals": "buts", "Points": "points", "Rebounds": "rebonds", "Assists": "passes", "ShotsOnGoal": "tirs cadrés"}


def libelle(pari: dict, match: dict) -> str:
    """Le pari standard en clair (« Carlos Alcaraz -5,5 jeux », « Jack Eichel : plus de 0,5 buts »)."""
    if str(pari["marche"]).startswith("JOUEUR:"):
        stat = STATS.get(pari["marche"][7:], pari["marche"][7:].lower())
        sens = "plus" if pari["issue"] == "PLUS" else "moins"
        return f'{pari.get("joueur")} : {sens} de {str(pari["ligne"]).replace(".", ",")} {stat}'
    return libelle_pari({**pari, "domicile": match.get("domicile"), "exterieur": match.get("exterieur"),
                         "sport": match.get("sport")})


def selections(r: dict) -> int:
    """Nombre de sélections du boost : 1 s'il est traduit en pari standard, sinon les « , » et « et » de l'intitulé."""
    if r.get("pari"):
        return 1
    return len([x for x in re.split(r",(?!\d)| et ", normaliser(r.get("libelle"))) if x.strip()]) or 1


def verdict(r: dict) -> tuple[str, float | None]:
    """(« jouer » ou « passer », marge habituelle attendue sur ce boost quand la cote juste manque)."""
    if r.get("value") is not None:
        return ("jouer" if r["value"] > 0 else "passer"), None
    if r.get("marge_seuil") is None:
        return "passer", None
    attendue = round(1 - (1 - MARGE_HABITUELLE) ** selections(r), 4)
    return ("jouer" if r["marge_seuil"] >= attendue + MARGE_SECURITE else "passer"), attendue


def evaluer(boosts: list[dict], francais: list[dict], index: dict, maintenant: datetime) -> list[dict]:
    """Chaque boost avec son match, son pari standard, sa cote juste et sa value quand elles sont connues."""
    matchs, piv = matchs_francais(francais), pivots(index)
    out = []
    for b in boosts:
        r = dict(b)
        avant, cote = b.get("cote_avant"), b.get("cote")
        r["hausse"] = round(cote / avant - 1, 4) if avant else None
        r["marge_seuil"] = round(1 - avant / cote, 4) if avant else None
        r["value"] = r["cote_juste"] = r["proba_juste"] = r["reference"] = None
        r["verifie"] = False
        debut = _t(b.get("debut"))
        if debut is not None and debut <= maintenant:
            continue                                         # match commencé : boost terminé
        if b.get("long_terme"):
            r["statut"] = "pari à long terme"
            out.append(r)
            continue
        m = associer(b, matchs)
        if m is None:
            r["statut"] = "match introuvable"
            out.append(r)
            continue
        r.update(match_id=m["match_id"], sport=m["sport"], ligue=m["ligue"])
        candidats = traduire(b.get("libelle"), m["domicile"], m["exterieur"], m["sport"])
        if not candidats:
            r["statut"] = "combiné ou intitulé non traduit"
            out.append(r)
            continue
        p = piv.get(m["match_id"])
        justes = (index.get(p[0]) or {}).get(m["match_id"], {}) if p else {}
        meme = m.get("source") == SOURCES.get(b.get("bookmaker"))
        pari, habituelle = choisir(candidats, m["lignes"] if meme else {}, avant, justes)
        if pari is None:
            r["statut"] = "pari standard introuvable"
            out.append(r)
            continue
        r.update({k: pari[k] for k in ("marche", "periode", "ligne", "issue", "joueur")})
        r["pari"] = libelle(pari, m)
        r["cote_habituelle"] = habituelle["cote"] if habituelle else None
        r["verifie"] = habituelle is not None
        juste = justes.get(_cle(pari)) if justes else None
        if juste and not juste.get("prix_prudent") and 0 < (juste.get("proba_juste") or 0) < 1 \
                and CT.contemporaines({"collecte": b.get("lu")}, juste):
            q = juste["proba_juste"]
            r.update(reference=p[0], proba_juste=round(q, 5), cote_juste=round(1 / q, 3), value=round(cote * q - 1, 4))
            r["statut"] = "évalué"
        else:
            r["statut"] = "sans cote juste"
        out.append(r)
    for r in out:
        r["verdict"], r["marge_attendue"] = verdict(r)
    out.sort(key=lambda x: (x.get("value") is None, -(x.get("value") or 0), -(x.get("hausse") or 0)))
    return out


# --------------------------------------------------------------------------- boosts couverts

def complements(marche: str, ligne, issue: str) -> list[list[tuple[str, object, str]]]:
    """Façons de couvrir tous les autres résultats d'un pari standard : listes de (marché, ligne, issue), même période.
    Vide si le marché ne se couvre pas sans remboursement possible (score exact, mi-temps/fin, joueur, ligne entière)."""
    if marche in SB.TROIS_ISSUES:
        issues = SB.TROIS_ISSUES[marche]
        if issue not in issues:
            return []
        out = [[(marche, ligne, i) for i in issues if i != issue]]
        if marche == "RESULTAT_1N2":                       # ou la double chance qui couvre les deux autres
            out.append([("DOUBLE_CHANCE", None, {"DOM": "DRAW_AWAY", "EXT": "HOME_DRAW", "NUL": "HOME_AWAY"}[issue])])
        return out
    if marche in SB.DEUX_ISSUES or (marche in SB.DEMI_LIGNE and SB.demi_ligne(ligne)):
        issues = SB.DEUX_ISSUES.get(marche) or SB.DEMI_LIGNE[marche]
        return [[(marche, ligne, i) for i in issues if i != issue]] if issue in issues else []
    if marche == "DOUBLE_CHANCE":
        reste = dict(SB.CROISES).get(issue)
        return [[("RESULTAT_1N2", None, reste)]] if reste else []
    return []


def mises_couverture(cote_boost: float, mise_boost: float, cotes: list[float], pas: float = PAS_COUVERTURE) -> dict:
    """Boost misé ``mise_boost`` ; chaque couverture reçoit mise × cote boostée / sa cote, arrondie à ``pas`` près
    (plancher ou plafond, au mieux pour le pire résultat). Rend {"mises" (boost d'abord), "mise_totale", "gain_min",
    "gain_max"} en euros."""
    retour = mise_boost * cote_boost
    meilleur = None
    for choix in product(*[(math.floor(retour / c / pas + 1e-9) * pas, math.ceil(retour / c / pas - 1e-9) * pas)
                           for c in cotes]):
        mises = [round(mise_boost, 2), *(round(m, 2) for m in choix)]
        if min(mises) <= 0:
            continue
        total = sum(mises)
        retours = [m * c for m, c in zip(mises, [cote_boost, *cotes])]
        cle_tri = (round(min(retours) - total, 6), -total)
        if meilleur is None or cle_tri > meilleur[0]:
            meilleur = (cle_tri, mises, total, retours)
    if meilleur is None:                                   # couvertures sous le pas : sans arrondi
        mises = [round(mise_boost, 2), *(round(retour / c, 2) for c in cotes)]
        total, retours = sum(mises), [m * c for m, c in zip(mises, [cote_boost, *cotes])]
    else:
        _, mises, total, retours = meilleur
    return {"mises": mises, "mise_totale": round(total, 2), "gain_min": round(min(retours) - total, 2),
            "gain_max": round(max(retours) - total, 2)}


def suspicion_couvert(jambes: list[dict], r: float) -> str | None:
    """Pourquoi un boost couvert n'est pas crédible (None : il l'est)."""
    if r > RENDEMENT_COUVERT_SUSPECT:
        return "rendement trop grand"
    if r > SB.RENDEMENT_SUSPECT_NON_VERIFIE and not SB.verifie(jambes):
        return "trop beau sans cote juste pour vérifier"
    return None


def _jambe_boost(b: dict, issue: str) -> dict:
    return {"bookmaker": b.get("bookmaker"), "issue": issue, "pari": b.get("pari"), "libelle_bookmaker": b.get("libelle"),
            "cote": float(b["cote"]), "lu": b.get("lu"), "proba_juste": b.get("proba_juste"),
            "cote_juste": b.get("cote_juste"), "ecart": b.get("value"), "lien": b.get("lien"), "lien_repli": False,
            "boost": True}


def _couvert(b: dict, jambes: list[dict], reference: str, maintenant: datetime) -> dict:
    jambes = [dict(j) for j in jambes]
    cotes = [j["cote"] for j in jambes]
    mise_max = b.get("mise_max")
    connue = isinstance(mise_max, (int, float)) and not isinstance(mise_max, bool) and mise_max > 0
    rep = mises_couverture(cotes[0], float(mise_max) if connue else MISE_DEFAUT, cotes[1:])
    for j, m in zip(jambes, rep["mises"]):
        j["mise"] = m
    r = SB.rendement(cotes)
    cle_c = "|".join([str(b.get("id")), *(f'{j["bookmaker"]}:{j["issue"]}' for j in jambes[1:])])
    return {"id": hashlib.sha1(cle_c.encode()).hexdigest()[:16], "cle": cle_c, "boost_id": b.get("id"),
            "detecte": maintenant.isoformat(timespec="seconds"), "bookmaker": b.get("bookmaker"),
            "libelle": b.get("libelle"), "pari": b.get("pari"), "domicile": b.get("domicile"),
            "exterieur": b.get("exterieur"), "match": f'{b.get("domicile")} – {b.get("exterieur")}',
            "debut": b.get("debut"), "sport": b.get("sport"), "ligue": b.get("ligue"), "reference": reference,
            "cote": b.get("cote"), "cote_avant": b.get("cote_avant"), "mise_max": mise_max if connue else None,
            "value": b.get("value"), "jambes": jambes, "bookmakers": sorted({j["bookmaker"] for j in jambes}),
            "verifie": SB.verifie(jambes), "somme_inverses": round(sum(1 / c for c in cotes), 5),
            "rendement": round(r, 5), "mise_boost": rep["mises"][0], "mise_totale": rep["mise_totale"],
            "gain": rep["gain_min"], "gain_max": rep["gain_max"], "suspect": suspicion_couvert(jambes, r)}


def couverts(evalues: list[dict], francais: list[dict], index: dict, maintenant: datetime,
             controle: tuple[dict, dict] | None = None) -> list[dict]:
    """Boosts du cycle (``evaluer``) qui, couverts aux meilleures cotes françaises des autres issues, gagnent quoi
    qu'il arrive ; du plus rentable au moins rentable, un par boost."""
    a_couvrir = []
    for b in evalues:
        c = b.get("cote")
        if not b.get("marche") or not b.get("match_id") or isinstance(c, bool) or not isinstance(c, (int, float)) \
                or not c > 1:
            continue
        a_couvrir.append(b)
    if not a_couvrir:
        return []
    familles = SB.candidates(francais, index, maintenant, controle)[0]
    piv = pivots(index)
    out = []
    for b in a_couvrir:
        p = piv.get(b["match_id"])
        if p is None:
            continue
        nom, mid_ref, inverse = p
        pari = {"marche": b["marche"], "periode": b.get("periode"), "ligne": b.get("ligne"), "issue": b.get("issue"),
                "domicile": b.get("domicile"), "exterieur": b.get("exterieur")}
        pc = inverser(pari) if inverse else pari              # dans le sens de la référence, comme les familles
        ligne = None if pc["ligne"] is None else round(float(pc["ligne"]), 2)
        boost = _jambe_boost(b, pc["issue"])
        meilleur = None
        for option in complements(pc["marche"], ligne, pc["issue"]):
            listes = [SB._meilleures((familles.get((nom, mid_ref, m, pc["periode"], l)) or {}).get(i) or [])
                      for m, l, i in option]
            if not all(listes):
                continue
            for combo in product(*listes):
                jambes = [boost, *combo]
                ok = SB.verifie(jambes)
                if ok and abs(sum(j["proba_juste"] for j in jambes) - 1) > SB.TOLERANCE_PARTITION:
                    continue                                   # pas le même marché : on n'y croit pas
                cle_tri = (round(SB.rendement([j["cote"] for j in jambes]), 6), ok)
                if meilleur is None or cle_tri > meilleur[0]:
                    meilleur = (cle_tri, jambes)
        if meilleur and meilleur[0][0] > 0:
            out.append(_couvert(b, meilleur[1], nom, maintenant))
    out.sort(key=lambda x: -x["rendement"])
    return out


# --------------------------------------------------------------------------- suivi

CHAMPS = ("bookmaker", "libelle", "domicile", "exterieur", "debut", "sport", "cote", "cote_avant", "mise_max",
          "pari", "marche", "periode", "ligne", "issue", "joueur", "match_id", "lien")


def suivre(etat: dict | None, actuels: list[dict], maintenant: datetime) -> dict:
    """Un épisode par boost : première et dernière lecture, cote et value à la première lecture et à la dernière."""
    episodes = {e["id"]: e for e in ((etat or {}).get("episodes") or []) if isinstance(e, dict) and e.get("id")}
    t = maintenant.isoformat(timespec="seconds")
    for b in actuels:
        e = episodes.get(b["id"])
        if e is None:
            e = episodes[b["id"]] = {"id": b["id"], "premier": t, "cycles": 0, **{k: b.get(k) for k in CHAMPS},
                                     "value_initiale": b.get("value"), "cote_juste_initiale": b.get("cote_juste")}
        e["dernier"], e["cycles"] = t, e["cycles"] + 1
        e["cote_derniere"], e["value_derniere"], e["statut"] = b.get("cote"), b.get("value"), b.get("statut")
        if e.get("value_initiale") is None and b.get("value") is not None:     # cote juste arrivée plus tard
            e["value_initiale"], e["cote_juste_initiale"] = b["value"], b.get("cote_juste")
        for k in ("pari", "marche", "periode", "ligne", "issue", "joueur", "match_id", "sport"):
            if e.get(k) is None and b.get(k) is not None:
                e[k] = b[k]
    limite = maintenant - timedelta(days=GARDER_JOURS)
    garde = sorted((e for e in episodes.values() if (_t(e.get("dernier")) or maintenant) >= limite),
                   key=lambda e: e.get("premier") or "")
    return {"episodes": garde[-EPISODES_MAX:]}


def bilan(episodes: list[dict], maintenant: datetime, jours: int = 7) -> dict:
    """Boosts vus sur ``jours`` jours : combien ont une cote juste, leur value, le gain espéré à la mise maximale."""
    es = [e for e in episodes if (maintenant - (_t(e.get("premier")) or maintenant)) <= timedelta(days=jours)]
    evalues = [e for e in es if e.get("value_initiale") is not None]
    hausses = [e["cote"] / e["cote_avant"] - 1 for e in es if e.get("cote_avant")]
    return {"jours": jours, "n": len(es), "evalues": len(evalues),
            "positifs": sum(e["value_initiale"] > 0 for e in evalues),
            "value_mediane": round(median(e["value_initiale"] for e in evalues), 4) if evalues else None,
            "gain_espere": round(sum((e.get("mise_max") or MISE_DEFAUT) * e["value_initiale"] for e in evalues), 2),
            "gain_espere_positifs": round(sum((e.get("mise_max") or MISE_DEFAUT) * e["value_initiale"]
                                              for e in evalues if e["value_initiale"] > 0), 2),
            "hausse_mediane": round(median(hausses), 4) if hausses else None}


def suivre_couverts(etat: dict | None, actuels: list[dict], maintenant: datetime) -> list[dict]:
    """Un épisode par boost couvert (même boost, mêmes couvertures) : première et dernière lecture, rendement et gain
    à la première lecture. Les suspects ne sont pas suivis."""
    episodes = {e["cle"]: e for e in ((etat or {}).get("episodes_couverts") or [])
                if isinstance(e, dict) and e.get("cle")}
    t = maintenant.isoformat(timespec="seconds")
    for c in actuels:
        if c.get("suspect"):
            continue
        e = episodes.get(c["cle"])
        if e is None:
            e = episodes[c["cle"]] = {
                "cle": c["cle"], "id": c["id"], "premier": t, "cycles": 0,
                **{k: c.get(k) for k in ("bookmaker", "libelle", "match", "debut", "sport", "pari", "bookmakers")},
                "rendement_initial": c["rendement"], "gain_initial": c["gain"], "mise_initiale": c["mise_totale"],
                "verifie": bool(c.get("verifie")), "rendement_max": c["rendement"],
                "jambes": [{k: j.get(k) for k in ("bookmaker", "issue", "pari", "cote", "cote_juste", "mise", "boost")}
                           for j in c["jambes"]]}
        e["dernier"], e["cycles"] = t, e["cycles"] + 1
        e["rendement_dernier"] = c["rendement"]
        e["rendement_max"] = max(e.get("rendement_max") or 0, c["rendement"])
    limite = maintenant - timedelta(days=GARDER_JOURS)
    garde = sorted((e for e in episodes.values() if (_t(e.get("dernier")) or maintenant) >= limite),
                   key=lambda e: e.get("premier") or "")
    return garde[-EPISODES_MAX:]


def bilan_couverts(episodes: list[dict], maintenant: datetime, jours: int = 7) -> dict:
    """Boosts couverts vus sur ``jours`` jours : nombre, vérifiés, gain garanti s'ils avaient tous été pris à la
    première lecture (boost à sa mise maximale), mise engagée, rendement médian."""
    es = [e for e in episodes if (maintenant - (_t(e.get("premier")) or maintenant)) <= timedelta(days=jours)]
    if not es:
        return {"jours": jours, "n": 0}
    return {"jours": jours, "n": len(es), "verifies": sum(bool(e.get("verifie")) for e in es),
            "gain": round(sum(e.get("gain_initial") or 0 for e in es), 2),
            "mise": round(sum(e.get("mise_initiale") or 0 for e in es), 2),
            "rendement_median": round(median(e["rendement_initial"] for e in es), 4)}


def publier(actuels: list[dict], etat: dict, maintenant: datetime, journal: dict | None = None,
            couverts_du_cycle: list[dict] | None = None) -> dict:
    """Document ``donnees/boosts.json`` : boosts du cycle, épisodes suivis, boosts couverts du cycle et leurs
    épisodes, journal du cycle."""
    return {"maj": maintenant.isoformat(timespec="seconds"), "actuels": actuels, "journal": journal or {},
            "episodes": etat.get("episodes", []), "couverts": couverts_du_cycle or [],
            "episodes_couverts": etat.get("episodes_couverts", [])}
