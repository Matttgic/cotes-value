"""Paris simulés : 10 € misés à la première détection d'une erreur de cote, par référence.

Simulations = tranches d'écart qui ne se chevauchent pas (écart = cote française × probabilité juste − 1),
à la première détection :
    A 2 à 3 %, B 3 à 4 %, C 4 à 5 %, D 5 à 7 %, E 7 % et plus   (cotes jusqu'à 10)
    X « cotes > 10 », écart ≥ 3 %                               (à part : cote juste imprécise, gros aléa)
Un pari n'est pris qu'une fois par référence, bookmaker et sélection (à la cote vue à la première
détection) et appartient à une seule simulation : « A+B » = les paris de 2 à 4 %, chacun compté une fois.
Chaque référence (Pinnacle, Betfair, Polymarket, Smarkets, Consensus) a ses paris.
Kalshi n'est plus collecté ; le nom reste dans la liste pour les paris déjà enregistrés.
"""
from __future__ import annotations

from .decisions import figer_selecteur

import hashlib
from math import isfinite
from datetime import datetime, timedelta, timezone

from . import VERSION
from .correspondance import normaliser
from .marches import cle
from .strategie_chatgpt import CHATGPT, paris_chatgpt
from .strategie_gemini import GEMINI, paris_gemini
from .strategie_jules import JULES, paris_jules
from .strategie_jules_v2 import JULES_V2, paris_jules_v2
from .strategie_eden import EDEN, paris_eden
from .strategie_qwen import QWEN, paris_qwen
from .liens import lien_match

MISE = 10.0
INF = float("inf")
FRAICHEUR_PRISE_MIN = 15
SIMULATIONS = {     # écart dans [ecart, ecart_max[, cote dans [cote_min, cote_max]
    "A": {"ecart": 0.02, "ecart_max": 0.03, "cote_min": 1.0, "cote_max": 10.0, "nom": "2 à 3 %"},
    "B": {"ecart": 0.03, "ecart_max": 0.04, "cote_min": 1.0, "cote_max": 10.0, "nom": "3 à 4 %"},
    "C": {"ecart": 0.04, "ecart_max": 0.05, "cote_min": 1.0, "cote_max": 10.0, "nom": "4 à 5 %"},
    "D": {"ecart": 0.05, "ecart_max": 0.07, "cote_min": 1.0, "cote_max": 10.0, "nom": "5 à 7 %"},
    "E": {"ecart": 0.07, "ecart_max": INF, "cote_min": 1.0, "cote_max": 10.0, "nom": "7 % et plus"},
    "X": {"ecart": 0.03, "ecart_max": INF, "cote_min": 10.0001, "cote_max": INF, "nom": "cotes > 10, ≥ 3 %"},
}


def simulation_de(ecart: float, cote: float) -> str | None:
    """La simulation (une seule) d'une opportunité, ou None."""
    if not _nombre_fini(ecart) or not _cote_valide(cote):
        return None
    for code, s in SIMULATIONS.items():
        if s["ecart"] <= ecart < s["ecart_max"] and s["cote_min"] <= cote <= s["cote_max"]:
            return code
    return None
REFERENCES = ["Pinnacle", "Betfair", "Polymarket", "Smarkets", "Kalshi", "Consensus"]


def _id(*parts) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:16]


def placer(opportunites: list[dict], paris: list[dict], maintenant: datetime | None = None) -> list[dict]:
    """Ajoute les nouveaux paris (modifie `paris`) et renvoie ceux qui viennent d'être pris. Un pari par
    référence, bookmaker et sélection, à la première détection, rangé dans la tranche de son écart. Un même
    pari vu chez plusieurs bookmakers = paris distincts (on sait ainsi lequel se trompe le plus souvent)."""
    deja = {p["id"] for p in paris}
    nouveaux = []
    lot = maintenant or datetime.now(timezone.utc)
    admissibles = [o for o in opportunites if _nombre_fini(o.get("ecart"))
                  and _cote_valide(o.get("cote")) and _cote_valide(o.get("cote_juste"))]
    for o in sorted(admissibles, key=lambda o: -o["ecart"]):
        if o.get("suspect") or o.get("pariable") is False:
            continue
        decision = maintenant or datetime.now(timezone.utc)
        debut = _heure(o.get("debut"))
        if not debut or not debut.tzinfo or debut <= decision + timedelta(seconds=30):
            continue
        if not _lectures_fraiches(o, decision, debut):
            continue
        code = simulation_de(o["ecart"], o["cote"])
        if code is None:
            continue
        pid = _id(o["reference"], o["match_id"], *cle(o))
        if pid in deja:
            continue
        deja.add(pid)
        p = {"id": pid, "simulation": code, "reference": o["reference"], "detecte": o["detecte"],
             "decide_le": decision.isoformat(timespec="microseconds"), "lot_decision": lot.isoformat(),
             "collecte_debut": o.get("collecte_debut"), "collecte_recue": o.get("collecte_recue"),
             "bookmaker": o["bookmaker"], "sport": o["sport"], "ligue": o.get("ligue"),
             "match_id": o["match_id"], "domicile": o["domicile"], "exterieur": o["exterieur"],
             "debut": o["debut"], "marche": o["marche"], "periode": o["periode"], "ligne": o.get("ligne"),
             "issue": o["issue"], "pari": o["pari"], "libelle_bookmaker": o.get("libelle_bookmaker"),
             "cote": o["cote"], "cote_juste": o["cote_juste"], "cote_reference": o.get("cote_reference"),
             "lu_reference": o.get("lu_reference"), "ecart": o["ecart"], "mise": MISE,
             "ecart_polymarket": o.get("ecart_polymarket"),
             "ecart_smarkets": o.get("ecart_smarkets"),
             # filtres à tester, descriptifs : mesurés à la prise, absents des anciens paris
             "trj_bookmaker": o.get("trj_bookmaker"), "limite_pinnacle": o.get("limite_pinnacle"),
             "marge_pinnacle": o.get("marge_pinnacle"), "mouvement_pinnacle": o.get("mouvement_pinnacle"),
             "mouvement_s": o.get("mouvement_s"),
             "statut": "en_cours", "gain": None, "cote_juste_cloture": o["cote_juste"], "clv": None,
             "match_reference": o.get("match_reference"), "lien": lien_match(o),
             # trace de la prise : de quoi revérifier le pari après coup
             "preuve_prise": {"match_id_reference": o.get("match_id_reference"),
                              "equipes_inversees": o.get("reference_inversee"),
                              "ressemblance_noms": o.get("score_association"),
                              "composantes": o.get("composantes"), "controle": o.get("controle"),
                              "preuves_composantes": o.get("preuves_composantes"),
                              "lectures_references": o.get("lectures_references"),
                              "version": VERSION}}
        if o.get("reference_reprise"):
            p["preuve_prise"]["reference_reprise"] = True
        paris.append(p)
        nouveaux.append(p)
    return nouveaux


def suivre_prix(paris: list[dict], lignes: list[dict]) -> None:
    """Dernier prix relu du même contrat ; la cote de prise et les bilans restent intacts.

    Une disparition n'est pas une baisse : aucune valeur n'est inventée si la
    ligne n'est plus dans le flux. Le navigateur affiche l'âge de la dernière lecture.
    """
    index = {}
    for l in lignes:
        t = _heure(l.get("collecte_recue") or l.get("collecte"))
        prix = l.get("cote")
        if not t or not t.tzinfo or isinstance(prix,bool) or not isinstance(prix, (int, float)) or not isfinite(prix) or prix <= 1:
            continue
        k = (l.get("match_id"), cle(l))
        if k not in index or t > index[k][0]:
            index[k] = (t, prix)
    for p in paris:
        if p.get("statut") != "en_cours":
            continue
        vu = index.get((p.get("match_id"), cle(p)))
        if not vu:
            continue
        t, prix = vu
        avant = _heure(p.get("prix_revu_le"))
        if avant and avant.tzinfo and t < avant:
            continue
        p["prix_revu"] = prix
        p["prix_revu_le"] = t.isoformat(timespec="seconds")


FRAICHEUR_CLOTURE_MIN = 15
TOLERANCE_HORLOGE_S = 60
# CLV « de clôture » : dernière observation à moins de CLOTURE_MAX_MIN minutes du coup d'envoi. Une
# observation plus ancienne (marché retiré tôt, référence absente ensuite) reste affichée sur le pari mais
# n'entre pas dans la CLV moyenne du bilan.
CLOTURE_MAX_MIN = 30


def _heure(s) -> datetime | None:
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _nombre_fini(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and isfinite(x)


def _cote_valide(cote) -> bool:
    return _nombre_fini(cote) and cote > 1


def _lectures_fraiches(o: dict, decision: datetime, debut: datetime) -> bool:
    """Deux lectures datées, contemporaines et encore fraîches lors de la décision.

    L'heure de réception FR, si fournie, ne remplace pas une détection absente ou
    périmée. Les anciennes prises ne passent jamais par cette validation.
    """
    from .controle import contemporaines
    fr, ref = _heure(o.get("detecte")), _heure(o.get("lu_reference"))
    dates = [fr, ref]
    lectures = o.get("lectures_references")
    if o.get("reference") == "Consensus" and (not isinstance(lectures, dict) or len(lectures) < 2):
        return False
    if lectures is not None:
        if not isinstance(lectures, dict) or not lectures:
            return False
        dates.extend(_heure(t) for t in lectures.values())
    if "collecte_recue" in o and o["collecte_recue"] is not None:
        dates.append(_heure(o["collecte_recue"]))
    if any(t is None or t.tzinfo is None or t.utcoffset() is None for t in dates):
        return False
    if any(not contemporaines({"collecte": o["detecte"]}, {"collecte": t.isoformat()}) for t in dates[1:]):
        return False
    return all(t < debut and -TOLERANCE_HORLOGE_S <= (decision - t).total_seconds() <= FRAICHEUR_PRISE_MIN * 60
               for t in dates)


# Mise « Kelly fractionné » : alternative simulée aux 10 € fixes, calculée sur les mêmes paris (rien n'est pris
# en plus). Mise = bankroll fictive × fraction × écart / (cote − 1), plafonnée. Bankroll constante, sans cumul.
KELLY_BANKROLL = 1000.0
KELLY_FRACTION = 0.25
KELLY_PLAFOND = 0.02          # 2 % de la bankroll par pari au plus


def mise_kelly(p: dict) -> float:
    """Mise Kelly fractionné d'un pari (0 si cote ou écart inexploitables)."""
    cote, ecart = p.get("cote"), p.get("ecart")
    if not (_nombre_fini(cote) and _nombre_fini(ecart)) or cote <= 1 or ecart <= 0:
        return 0.0
    plein = ecart / (cote - 1)
    return round(min(KELLY_BANKROLL * KELLY_FRACTION * plein, KELLY_BANKROLL * KELLY_PLAFOND), 2)


def clv_finale(p: dict) -> float | None:
    """CLV du pari si elle est mesurée près du coup d'envoi et que le match est joué (pari réglé), sinon None.
    Pour les paris d'avant le 7/10/2026, `cloture_lue` est l'heure du cycle (à quelques minutes près celle
    de la cote, toutes les références étant relues à chaque cycle)."""
    if p.get("clv") is None or p.get("statut") in ("en_cours", "a_regler"):
        return None
    t, debut = _heure(p.get("cloture_lue")), _heure(p.get("debut"))
    if not t or not debut or t.tzinfo is None or debut.tzinfo is None:
        return None
    return p["clv"] if 0 < (debut - t).total_seconds() <= CLOTURE_MAX_MIN * 60 else None


def suivre_cloture(paris: list[dict], justes: dict[tuple, dict[str, tuple]], maintenant: datetime | None = None):
    """Intègre une lecture pré-match prouvée, même traitée après le coup d’envoi.

    Avant le départ, la lecture doit dater de moins de FRAICHEUR_CLOTURE_MIN minutes.
    Après le départ, sa date source doit toujours prouver t < début ; le filtre
    de clôture à 30 min reste appliqué par clv_finale(). `cloture_lue` est l'heure de lecture de la
    référence (et non celle du traitement)."""
    maintenant = maintenant or datetime.now(timezone.utc)
    for p in paris:
        if p["statut"] != "en_cours":
            continue
        try:
            debut = datetime.fromisoformat(p["debut"].replace("Z", "+00:00"))
        except (AttributeError, ValueError):
            continue
        if not debut.tzinfo:
            continue
        proba, lue = justes.get((p["match_id"], cle(p)), {}).get(p["reference"]) or (None, None)
        t = _heure(lue)
        if not proba or not t or t.tzinfo is None or t >= debut:
            continue
        age = (maintenant - t).total_seconds()
        if age < -TOLERANCE_HORLOGE_S or (maintenant < debut and age > FRAICHEUR_CLOTURE_MIN * 60):      # périmée, ou dans le futur
            continue
        avant = _heure(p.get("cloture_lue"))
        if avant and avant.tzinfo and t <= avant:        # uniquement une nouvelle observation
            continue
        p["cote_juste_cloture"] = round(1 / proba, 4)
        p["clv"] = round(p["cote"] * proba - 1, 4)
        p["cloture_lue"] = t.isoformat(timespec="seconds")


# tranches de cote (bornes basses exclues, hautes incluses)
TRANCHES = [(1.0, 1.5, "1,01 – 1,50"), (1.5, 2.0, "1,51 – 2,00"), (2.0, 3.0, "2,01 – 3,00"),
            (3.0, 5.0, "3,01 – 5,00"), (5.0, 10.0, "5,01 – 10"), (10.0, float("inf"), "plus de 10")]


def tranche(cote: float) -> str:
    """Une donnée corrompue reste repérable, sans bloquer la construction du bilan."""
    if _cote_valide(cote):
        for bas, haut, nom in TRANCHES:
            if bas < cote <= haut:
                return nom
    return "cote invalide"


# Stratégie du 11/10/2026 : critères tirés des paris du 5 au 11/10 (meilleure CLV), puis FIGÉS. Elle n'est
# jugée que sur les paris repérés après sa création, pour ne pas mesurer la chance qui a servi à la trouver.
STRATEGIE = {"nom": "Stratégie", "debut": "2026-10-11T10:30:00+00:00",
             "references": ("Pinnacle", "Betfair", "Polymarket"),     # pas Kalshi (CLV −6 %)
             "simulations": ("A", "B", "C", "D", "E"),                 # écart ≥ 2 %, pas les cotes > 10
             "cote_max": 2.5,                                          # cote < 2,5
             "avance_max_h": 12}                                       # repéré moins de 12 h avant le match


def dans_strategie(p: dict, depuis: str | None = None) -> bool:
    """Pari qui suit la stratégie : référence, écart, cote < 2,5, repéré moins de 12 h avant le match, et
    hommes seniors (pas de compétition féminine ni de jeunes)."""
    if p.get("reference") not in STRATEGIE["references"] or p.get("simulation") not in STRATEGIE["simulations"]:
        return False
    if not (p.get("cote") or 99) < STRATEGIE["cote_max"]:
        return False
    detecte, debut = _heure(p.get("detecte")), _heure(p.get("debut"))
    if not detecte or not debut or not detecte.tzinfo or not debut.tzinfo or detecte < _heure(depuis or STRATEGIE["debut"]):
        return False
    if not timedelta(0) < debut - detecte < timedelta(hours=STRATEGIE["avance_max_h"]):
        return False
    noms = [normaliser(str(p.get(c) or "")) for c in ("domicile", "exterieur", "ligue")]
    return not any(n[1] for n in noms) and not any(n[2] for n in noms[:2])


@figer_selecteur("strategie")
def paris_strategie(paris: list[dict], depuis: str | None = None) -> set[int]:
    """Les paris de la stratégie (id() de leur dict) : une mise par cote française, à sa première détection
    qui suit la stratégie."""
    premiers: dict[tuple, dict] = {}
    for p in paris:
        if not dans_strategie(p, depuis=depuis):
            continue
        k = tuple(p.get(c) for c in ("match_id", "marche", "periode", "ligne", "issue", "joueur"))
        if k not in premiers or (p.get("detecte") or "") < (premiers[k].get("detecte") or ""):
            premiers[k] = p
    return {id(p) for p in premiers.values()}


def premiers_par_selection(paris: list[dict]) -> set[int]:
    """Les « paris uniques » (repérés par id() de leur dict) : pour chaque cote française (bookmaker, match, marché, issue), le
    pari de sa première détection, quelle que soit la référence qui l'a repérée. C'est ce
    qu'on aurait réellement joué : une seule mise par cote, même si plusieurs références l'ont signalée."""
    ordre = {r: i for i, r in enumerate(REFERENCES)}
    premiers: dict[tuple, dict] = {}
    for p in paris:
        k = tuple(p.get(c) for c in ("match_id", "marche", "periode", "ligne", "issue", "joueur")) \
            if p.get("match_id") else (id(p),)
        rang = (p.get("detecte") or "", ordre.get(p.get("reference"), 99))
        if k not in premiers or rang < premiers[k][0]:
            premiers[k] = (rang, p)
    return {id(p) for _, p in premiers.values()}


def _cumuler(paris: list[dict], groupe) -> dict:
    """Résumé par (groupe, référence), (groupe, « Toutes »), (groupe, « Uniques ») et (groupe, « Stratégie ») :
    nombre, mises, gains, ROI, CLV moyenne. « Toutes » = les vraies références, un pari par référence ; « Uniques » = un pari par
    cote française."""
    from .evenements import identites
    liens = identites(paris)
    numeros = {cle:i for i,cle in enumerate(dict.fromkeys(liens.values()))}
    out: dict[str, dict] = {}
    uniques, strategie = premiers_par_selection(paris), paris_strategie(paris)
    chatgpt = paris_chatgpt(paris)
    gemini = paris_gemini(paris)
    jules = paris_jules(paris)
    jules_v2 = paris_jules_v2(paris)
    eden = paris_eden(paris)
    qwen = paris_qwen(paris)
    for p in paris:
        clefs = [f'{groupe(p)}|{p["reference"]}', f'{groupe(p)}|Toutes']
        if id(p) in uniques:
            clefs.append(f'{groupe(p)}|Uniques')
        if id(p) in strategie:
            clefs.append(f'{groupe(p)}|{STRATEGIE["nom"]}')
        if id(p) in chatgpt:
            clefs.append(f'{groupe(p)}|{CHATGPT["nom"]}')
        if id(p) in gemini:
            clefs.append(f'{groupe(p)}|{GEMINI["nom"]}')
        if id(p) in jules:
            clefs.append(f'{groupe(p)}|{JULES["nom"]}')
        if id(p) in jules_v2:
            clefs.append(f'{groupe(p)}|{JULES_V2["nom"]}')
        if id(p) in eden:
            clefs.append(f'{groupe(p)}|{EDEN["nom"]}')
        if id(p) in qwen:
            clefs.append(f'{groupe(p)}|{QWEN["nom"]}')
        for clef in clefs:
            b = out.setdefault(clef, {"paris": 0, "regles": 0, "en_cours": 0, "mises": 0.0, "gains": 0.0,
                                      "clv_somme": 0.0, "clv_n": 0, "clv_positifs": 0, "gagnes": 0,
                                      # paris réglés avec / sans CLV mesurée : gain réel, et gain espéré d'après
                                      # la CLV (mise × CLV) pour ceux qui en ont une
                                      "gains_avec_clv": 0.0, "espere_clv": 0.0, "gains_sans_clv": 0.0,
                                      "regles_sans_clv": 0, "mises_kelly": 0.0, "gains_kelly": 0.0,
                                      "evenements_detail": {}})
            b["paris"] += 1
            ev = b["evenements_detail"].setdefault(str(numeros[liens[id(p)]]), [0,0,0.0,0])
            ev[0] += 1
            ev[1] += p["statut"] not in ("en_cours", "a_regler")
            if p["statut"] in ("en_cours", "a_regler"):
                b["en_cours"] += 1
            else:
                b["regles"] += 1
                b["mises"] += p["mise"]
                b["gains"] += p["gain"] or 0
                b["gagnes"] += p["statut"] in ("gagne", "demi_gagne")
                k = mise_kelly(p)
                b["mises_kelly"] += k
                b["gains_kelly"] += (p["gain"] or 0) * k / p["mise"] if p.get("mise") else 0
            clv = clv_finale(p)
            if clv is not None:
                ev[2] += clv
                ev[3] += 1
                b["clv_somme"] += clv
                b["clv_n"] += 1
                b["clv_positifs"] += clv > 0      # a battu la cote de clôture
                b["gains_avec_clv"] += p["gain"] or 0
                b["espere_clv"] += p["mise"] * clv
            elif p["statut"] not in ("en_cours", "a_regler"):
                b["regles_sans_clv"] += 1
                b["gains_sans_clv"] += p["gain"] or 0
    for b in out.values():
        es = list(b["evenements_detail"].values())
        b["evenements"] = len(es)
        b["evenements_regles"] = sum(v[1]>0 for v in es)
        cs = [v[2]/v[3] for v in es if v[3]]
        b["clv_evenement"] = sum(cs)/len(cs) if cs else None
        b["clv_evenements_n"] = len(cs)
        b["roi"] = round(b["gains"] / b["mises"], 4) if b["mises"] else None
        b["clv_moyenne"] = round(b["clv_somme"] / b["clv_n"], 4) if b["clv_n"] else None
        b["roi_kelly"] = round(b["gains_kelly"] / b["mises_kelly"], 4) if b["mises_kelly"] else None
        for k in ("gains", "gains_avec_clv", "espere_clv", "gains_sans_clv", "mises_kelly", "gains_kelly"):
            b[k] = round(b[k], 2)
    return out


def bilan(paris: list[dict]) -> dict:
    """Par simulation (« A|Pinnacle », « A|Toutes »…)."""
    return _cumuler(paris, lambda p: p["simulation"])


def moyennes_ecarts(paris: list[dict]) -> dict:
    """Écart moyen à la prise, paris uniques réglés, contre chaque référence affichée.

    Un ancien pari n'a le champ que s'il a été pris contre cette référence :
    son ``ecart`` est alors l'écart contre elle.
    """
    uniques = premiers_par_selection(paris)
    specs = (("Polymarket", "ecart_polymarket"), ("Smarkets", "ecart_smarkets"))
    out = {}
    for nom, champ in specs:
        valeurs = []
        for p in paris:
            if id(p) not in uniques or p.get("statut") not in REGLES:
                continue
            valeur = p.get(champ)
            if valeur is None and p.get("reference") == nom:
                valeur = p.get("ecart")
            if _nombre_fini(valeur):
                valeurs.append(valeur)
        out[nom] = {"moyenne": round(sum(valeurs) / len(valeurs), 4) if valeurs else None,
                    "n": len(valeurs)}
    return out


def bilan_bookmakers(paris: list[dict]) -> dict:
    """Par bookmaker et simulation (« PMU·A|Uniques »…) : la page additionne les simulations choisies."""
    return _cumuler(paris, lambda p: f'{p.get("bookmaker")}·{p.get("simulation")}')


def profil_horaire(paris: list[dict]) -> dict:
    """Détections par heure de Paris (0 à 23), par bookmaker : « PMU » -> 24 compteurs.

    Paris uniques seulement (une cote française comptée une fois, quelle que soit la référence qui l'a
    repérée) à leur première détection : on voit quand les erreurs de cote apparaissent chez chaque
    bookmaker. « Tous » regroupe les bookmakers. Aucune lecture réseau, descriptif seulement."""
    from zoneinfo import ZoneInfo
    paris_tz = ZoneInfo("Europe/Paris")
    uniques = premiers_par_selection(paris)
    out: dict[str, list[int]] = {"Tous": [0] * 24}
    for p in paris:
        if id(p) not in uniques:
            continue
        t = _heure(p.get("detecte"))
        if t is None or t.tzinfo is None:
            continue
        h = t.astimezone(paris_tz).hour
        out["Tous"][h] += 1
        out.setdefault(p.get("bookmaker") or "?", [0] * 24)[h] += 1
    return out


# Filtres à tester : TRJ du bookmaker, limite de mise Pinnacle (liquidité du marché sharp), mouvement de Pinnacle.
# Chaque filtre = (champ du pari, tranches (libellé, minimum inclus, maximum exclus)). Descriptif : aucun n'est appliqué.
MARCHES_2_ISSUES = {"VAINQUEUR", "DRAW_NO_BET", "TOTAL", "TOTAL_DOM", "TOTAL_EXT", "HANDICAP", "BOTH_TEAMS_TO_SCORE"}


def marge_pinnacle_estimee(p: dict) -> float | None:
    """Marge de Pinnacle retrouvée sur un ancien pari (qui ne l'a pas enregistrée), marchés à 2 issues seulement.

    Le pari garde la cote Pinnacle brute et la cote juste de la sélection ; la méthode « power » (p = (1/cote)^k) donne
    k, donc la cote de l'autre issue et la marge. Pas de 1N2 : trois issues, une seule connue. Une marge élevée
    reflète un marché peu liquide, c'est notre indicateur de liquidité pour le passé."""
    if p.get("reference") != "Pinnacle" or p.get("marche") not in MARCHES_2_ISSUES:
        return None
    brute, juste = p.get("cote_reference"), p.get("cote_juste")
    if not (_nombre_fini(brute) and _nombre_fini(juste)) or brute <= 1 or juste <= 1:
        return None
    from math import log
    po, pj = 1 / brute, 1 / juste
    if not 0 < pj < 1 or po >= 1 or log(po) == 0:
        return None
    k = log(pj) / log(po)
    if not 0.2 <= k <= 5:
        return None
    return round(po + (1 - pj) ** (1 / k) - 1, 4)


def _valeur_filtre(champ: str, p: dict) -> float | None:
    v = p.get(champ)
    if _nombre_fini(v):
        return v
    return marge_pinnacle_estimee(p) if champ == "marge_pinnacle" else None


FILTRES = {
    "trj": ("trj_bookmaker", (("< 92 %", 0, .92), ("92 – 94 %", .92, .94), ("94 – 96 %", .94, .96), ("96 % et plus", .96, 9))),
    "limite": ("limite_pinnacle", (("< 300 €", 0, 300), ("300 – 999 €", 300, 1000),
                                   ("1 000 – 2 999 €", 1000, 3000), ("3 000 € et plus", 3000, 1e12))),
    "marge": ("marge_pinnacle", (("< 4 %", -1, .04), ("4 – 6 %", .04, .06), ("6 – 8 %", .06, .08),
                                       ("8 – 10 %", .08, .10), ("10 % et plus", .10, 9))),
    "mouvement": ("mouvement_pinnacle", (("Cote Pinnacle en baisse ≥ 2 %", .02, 9), ("En baisse de 0,5 à 2 %", .005, .02),
                                         ("Stable (± 0,5 %)", -.005, .005), ("Cote Pinnacle en hausse", -9, -.005))),
}


def bilan_filtres(paris: list[dict]) -> dict:
    """Par filtre et tranche : paris uniques réglés, gain, ROI, CLV, part battant la clôture, et mise Kelly.

    Seuls les paris pris après l'ajout de la mesure la portent (``n_mesures`` donne leur nombre, réglés ou non).
    Un tableau à zéro ligne veut dire « pas encore assez de paris », pas « sans effet »."""
    uniques = premiers_par_selection(paris)
    out: dict[str, dict] = {}
    for nom, (champ, tranches) in FILTRES.items():
        lignes = [{"tranche": t, "n": 0, "regles": 0, "gagnes": 0, "mises": 0.0, "gains": 0.0, "clv_n": 0,
                   "clv_somme": 0.0, "clv_positifs": 0} for t, _, _ in tranches]
        mesures = estimee = 0
        for p in paris:
            v = _valeur_filtre(champ, p)
            if id(p) not in uniques or v is None:
                continue
            mesures += 1
            estimee += not _nombre_fini(p.get(champ))
            for l, (_, bas, haut) in zip(lignes, tranches):
                if bas <= v < haut:
                    l["n"] += 1
                    if p.get("statut") in REGLES:
                        l["regles"] += 1
                        l["gagnes"] += p["statut"] in ("gagne", "demi_gagne")
                        l["mises"] += p["mise"]
                        l["gains"] += p["gain"] or 0
                        clv = clv_finale(p)
                        if clv is not None:
                            l["clv_n"] += 1
                            l["clv_somme"] += clv
                            l["clv_positifs"] += clv > 0
                    break
        for l in lignes:
            l["roi"] = round(l["gains"] / l["mises"], 4) if l["mises"] else None
            l["clv_moyenne"] = round(l["clv_somme"] / l["clv_n"], 4) if l["clv_n"] else None
            l["gains"], l["mises"] = round(l["gains"], 2), round(l["mises"], 2)
            del l["clv_somme"]
        out[nom] = {"n_mesures": mesures, "n_estimees": estimee, "tranches": lignes}
    return out


def bilan_tranches(paris: list[dict]) -> dict:
    """Par tranche de cote (« 1,51 – 2,00|Pinnacle »…) ; chaque pari n'appartient qu'à une simulation."""
    return _cumuler(paris, lambda p: tranche(p["cote"]))


SEGMENT_MIN = 10       # paris réglés minimum pour afficher un segment
SIGMA_FIABLE_MIN = 30  # condition nécessaire, jamais une preuve de rentabilité
REGLES = ("gagne", "perdu", "demi_gagne", "demi_perdu", "rembourse")


def segments(paris: list[dict]) -> list[dict]:
    """Bilan par segment (tranche, bookmaker, sport, référence et leurs croisements) sur les paris uniques réglés :
    réussite réelle contre réussite attendue (somme des probabilités justes à la prise), écart en écarts-types,
    ROI et CLV. Le sigma reste descriptif : corrélations, règlements non binaires et essais multiples
    empêchent de l'interpréter automatiquement comme une preuve de rentabilité."""
    # Référence de la première détection : une seule mise, même si plusieurs
    # références ont signalé la même sélection.
    uniques = premiers_par_selection(paris)
    regles = [p for p in paris if id(p) in uniques and p.get("statut") in REGLES and p.get("cote_juste")]
    from .evenements import identites
    liens = identites(regles)
    from itertools import combinations

    dimensions = ("tranche", "bookmaker", "sport", "reference")
    dims = [d for n in range(1, len(dimensions)+1) for d in combinations(dimensions, n)]
    valeur = {"tranche": lambda p: tranche(p["cote"]), "bookmaker": lambda p: p.get("bookmaker"),
              "sport": lambda p: p.get("sport"), "reference": lambda p: p.get("reference")}
    groupes: dict[tuple, list[dict]] = {}
    for p in regles:
        for d in dims:
            groupes.setdefault(tuple((k, valeur[k](p)) for k in d), []).append(p)
    out, vus = [], set()
    # du plus général au plus précis : un croisement qui contient exactement les mêmes paris qu'un segment plus
    # général (« plus de 10 · Winamax » = « plus de 10 · Winamax · football ») n'est pas répété
    for cle_seg, rows in sorted(groupes.items(), key=lambda kv: len(kv[0])):
        contenu = frozenset(id(p) for p in rows)
        if len(rows) < SEGMENT_MIN or contenu in vus:
            continue
        vus.add(contenu)
        probas = [1 / p["cote_juste"] for p in rows]
        gagnes = sum(p["statut"] in ("gagne", "demi_gagne") for p in rows)
        attendus = sum(probas)
        sd = sum(q * (1 - q) for q in probas) ** 0.5 or 1
        mises = sum(p["mise"] for p in rows)
        gains = sum(p.get("gain") or 0 for p in rows)
        clvs = [c for c in (clv_finale(p) for p in rows) if c is not None]
        evenements = len({liens[id(p)] for p in rows})
        limites = []
        if len(rows) < SIGMA_FIABLE_MIN:
            limites.append("effectif_faible")
        if evenements < len(rows):
            limites.append("tickets_meme_evenement")
        if any(p["statut"] not in ("gagne", "perdu") for p in rows):
            limites.append("reglements_non_binaires")
        if min(attendus, sum(1-q for q in probas)) < 5:
            limites.append("attendus_extremes")
        out.append({**dict(cle_seg), "n": len(rows), "gagnes": gagnes, "attendus": round(attendus, 1),
                    "evenements": evenements, "sigma_fiable": not limites, "sigma_limites": limites,
                    "ecart_sigma": round((gagnes - attendus) / sd, 2), "gains": round(gains, 2),
                    "roi": round(gains / mises, 4) if mises else None,
                    "clv_moyenne": round(sum(clvs) / len(clvs), 4) if clvs else None, "clv_n": len(clvs)})
    return out

