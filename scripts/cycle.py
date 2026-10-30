"""Collecte et comparaison des cotes ; le règlement fonctionne aussi en cycle indépendant.

Lancé toutes les 5 minutes par GitHub Actions (.github/workflows/collecte.yml).

    python scripts/cycle.py                 # cycle complet (bookmakers français lus en direct, 36 h)
    python scripts/cycle.py --mode test     # cycle réduit : Winamax + Betclic, foot, 1 page
    python scripts/cycle.py --reglement oui # forcer le règlement des paris à ce cycle

Le règlement des paris (lecture des résultats : environ 6 minutes, 220 requêtes) n'a lieu qu'une fois par
heure (REGLEMENT_MINUTES, 55 par défaut) : les cotes, elles, sont lues à chaque cycle.

Données (branche « donnees ») : paris.json, etat.json, opportunites/AAAA-MM-JJ.jsonl, cotes/AAAA-MM-JJ.jsonl.gz,
resultats_manuels.json (règlements faits à la main ; « supprime » retire un pari). Site : dossier site/.
Mémoire de travail (cache Actions, MEMOIRE_CHEMIN) : horizon_direct, caches de secours, contrôle (cotes/memoire.py).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cotes import (flashscore, livescore, comparaison, controle, pinnacle, polymarket, reglement,  # noqa: E402
                   simulation, smarkets, stockage)
from cotes.direct import betclic as betclic_direct  # noqa: E402
from cotes.direct import netbet as netbet_direct  # noqa: E402
from cotes.direct import olybet as olybet_direct  # noqa: E402
from cotes.direct import pmu as pmu_direct  # noqa: E402
from cotes.direct import unibet as unibet_direct  # noqa: E402
from cotes.direct import winamax as winamax_direct  # noqa: E402
from cotes.direct import matchbook as matchbook_direct  # noqa: E402
from cotes import resultats as resultats_mod  # noqa: E402
from cotes import theodds, resultats_nhl, propline, pinnacle_secours, thesportsdb  # noqa: E402
from cotes import liens  # noqa: E402
from cotes import reprise  # noqa: E402
from cotes import historique_cotes, memoire  # noqa: E402
from cotes import echecs  # noqa: E402
from cotes.ecriture import ajouter_gzip  # noqa: E402
from cotes.delai import Echeance  # noqa: E402
from cotes.marches import harmoniser_pinnacle  # noqa: E402

HORIZON_H = 36
# Budgets durs : une source au-delà est sautée, le cycle de 5 min continue.
BUDGETS = {
    "pinnacle": 45,
    "polymarket": 30,
    "pmu_direct": 75,
    "winamax_direct": 80,       # 25 filtres depuis le 25/10 (handicaps, totaux par équipe, mi-temps) : ~70 s
    "unibet_direct": 80,        # coupé par le budget dans la moitié des cycles les 23-24/10 (médiane 72 s)
    "olybet": 40,
    "netbet": 40,
    "betclic_direct": 80,
    "smarkets": 60,
    "matchbook": 25,
}
PRES_H = 6
RYTHME_MIN = 20
# Les lectures lointaines ne tombent pas le même cycle : PMU toutes les 20 min,
# Unibet 27, Betclic 34. Le premier passage (aucun tampon) reste complet.
RYTHME_SOURCE = {"pmu": 20, "unibet": 27, "betclic": 34}
SMARKETS_FRAIS_MIN = 15
_journal_lock = threading.Lock()
# minutes minimum entre deux règlements (le cycle de 5 min ne lit les résultats qu'une fois par heure)
REGLEMENT_MINUTES = float(os.environ.get("REGLEMENT_MINUTES", "55"))


def lire_json(chemin: Path, defaut):
    """Contenu d'un fichier de données, ou `defaut` s'il n'existe pas encore. Un fichier illisible arrête le
    cycle (erreur JSON) : le traiter comme vide écraserait, par exemple, tous les paris à la sauvegarde."""
    try:
        texte = chemin.read_text(encoding="utf-8")
    except FileNotFoundError:
        return defaut
    return json.loads(texte)


def ecrire_json(chemin: Path, donnees, compact: bool = False) -> None:
    """Écriture atomique : un cycle interrompu ne laisse jamais un fichier à moitié écrit.
    ``compact`` : sans indentation ni espaces (fichiers lourds réécrits souvent, comme controle.json)."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    tmp = chemin.with_name(chemin.name + ".tmp")
    texte = (json.dumps(donnees, ensure_ascii=False, separators=(",", ":")) if compact
             else json.dumps(donnees, ensure_ascii=False, indent=1))
    tmp.write_text(texte, encoding="utf-8")
    os.replace(tmp, chemin)


def etape(nom: str, journal: dict, fonction, *args, **kwargs):
    """Exécute une étape ; une source en panne n'arrête pas le cycle (l'erreur est notée)."""
    t = time.time()
    try:
        r = fonction(*args, **kwargs)
        journal["etapes"][nom] = {"secondes": round(time.time() - t, 1), "ok": True}
        return r
    except Exception as e:                                       # noqa: BLE001
        journal["etapes"][nom] = {"secondes": round(time.time() - t, 1), "ok": False, "erreur": repr(e)[:300]}
        traceback.print_exc()
        return None


def etape_bornee(nom: str, journal: dict, budget: float, fonction, *args, **kwargs):
    """Durée maximale. Au-delà, la source est notée et le cycle continue."""
    t = time.time()
    boite: dict = {}

    def courir():
        try:
            boite["r"] = fonction(*args, **kwargs)
        except Exception as e:  # noqa: BLE001
            boite["e"] = e
            traceback.print_exc()

    fil = threading.Thread(target=courir, name=f"source-{nom}", daemon=True)
    fil.start()
    fil.join(budget)
    secondes = round(time.time() - t, 1)
    with _journal_lock:
        if fil.is_alive():
            journal["etapes"][nom] = {"secondes": secondes, "ok": False, "erreur": "budget dépassé"}
            return None
        if "e" in boite:
            journal["etapes"][nom] = {"secondes": secondes, "ok": False, "erreur": repr(boite["e"])[:300]}
            return None
        journal["etapes"][nom] = {"secondes": secondes, "ok": True}
    return boite.get("r")


def source_bornee(module, nom: str, journal: dict, budget: float, fonction, *args, **kwargs):
    """Pose l'échéance lue par le connecteur, puis abandonne le fil s'il dépasse."""
    module._echeance = Echeance(budget)
    try:
        return etape_bornee(nom, journal, budget, fonction, *args, **kwargs)
    finally:
        module._echeance = None


def _instant(valeur):
    try:
        t = datetime.fromisoformat(str(valeur).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if getattr(t, "tzinfo", None) is None:
        return None
    return t.astimezone(timezone.utc)


def heures_ombre(nom: str, mode: str, mode_collecte: str, maintenant: datetime,
                 rythme: dict) -> tuple[float, bool]:
    """En shadow, les matchs à plus de 6 h ne sont relus qu'au rythme de la source."""
    plein = 12.0 if mode_collecte == "test" else float(HORIZON_H)
    if mode != "shadow" or mode_collecte == "test":
        return plein, False
    dernier = _instant(rythme.get(nom)) if isinstance(rythme, dict) else None
    delai = RYTHME_SOURCE.get(nom, RYTHME_MIN)
    if dernier is None or maintenant - dernier >= timedelta(minutes=delai):
        return plein, True
    return float(PRES_H), False


def _cache_sm(donnees: Path) -> dict:
    """Cache Smarkets (mémoire hors « donnees », cotes/memoire.py) ; {} s'il est absent ou illisible."""
    doc = memoire.lire(donnees, "smarkets_cache", {})
    return doc if isinstance(doc, dict) else {}


def appliquer_smarkets(donnees: Path, sports: set, heures: float, radar: list,
                       maintenant: datetime, journal: dict):
    """Relit Smarkets au plus toutes les 15 min, seulement si ``SMARKETS_COLLECTE`` est oui.

    Éteint (``SMARKETS_COLLECTE`` autre que oui ; le workflow l'allume par défaut) : zéro appel.
    La table des paris déjà pris reste celle de l'historique.
    Un 429 ou un budget garde le cache périmé.
    """
    if not smarkets.collecte_active():
        journal["etapes"]["smarkets"] = {"secondes": 0.0, "ok": True, "desactive": True}
        journal["smarkets_cache"] = {"reutilise": False, "perime": False, "desactive": True}
        return [], {"ok": True, "erreurs": [], "requetes": 0, "desactive": True}
    cache = _cache_sm(donnees)
    if _instant(cache.get("lu")) and maintenant - _instant(cache.get("lu")) < timedelta(minutes=SMARKETS_FRAIS_MIN):
        perime = bool(cache.get("perime"))
        lu = _instant(cache.get("lu"))
        etape_j = {"secondes": 0.0, "ok": True, "cache": True}
        if perime:
            etape_j["degrade"] = True
            etape_j["erreurs"] = ["périmé"]
        journal["etapes"]["smarkets"] = etape_j
        journal["smarkets_cache"] = {
            "reutilise": True, "perime": perime,
            "age_min": round((maintenant - lu).total_seconds() / 60, 1) if lu else None,
        }
        return list(cache.get("lignes") or []), {
            "ok": True, "erreurs": ["périmé"] if perime else [], "requetes": 0}

    echeance = Echeance(BUDGETS["smarkets"])
    smarkets._echeance = echeance
    try:
        recu = etape_bornee("smarkets", journal, BUDGETS["smarkets"], smarkets.collecter,
                            sports, heures, maintenant=maintenant, radar=radar, echeance=echeance,
                            reserve={"lignes": cache.get("lignes") or [], "evenements": cache.get("evenements")})
    finally:
        smarkets._echeance = None
    if not isinstance(recu, tuple) or len(recu) != 2:
        lignes, info = [], {"ok": False, "erreurs": ["budget dépassé"], "perime": True, "requetes": 0}
    else:
        lignes, info = recu
    # Lecture incrémentale ("lus") : un budget ou un quota qui coupe la fin du catalogue n'est pas un cache périmé.
    perime = bool(info.get("perime")) if "lus" in info else (bool(info.get("perime")) or any(
        e in ("budget", "HTTP 429", "budget dépassé") for e in (info.get("erreurs") or [])))
    precedentes = cache.get("lignes") if isinstance(cache.get("lignes"), list) else []
    if perime and precedentes:
        lignes = list(precedentes)
    memoire.ecrire(donnees, "smarkets_cache", {
        "lu": maintenant.isoformat(), "lignes": lignes, "perime": perime, "matchs": info.get("matchs"),
        "lus": info.get("lus"), "evenements": info.get("evenements") or cache.get("evenements"),
    })
    if perime and "smarkets" in journal["etapes"]:
        et = journal["etapes"]["smarkets"]
        et["perime"] = True
        deja = [e for e in (et.get("erreurs") or []) if e != "périmé"]
        deja.append("périmé")
        et["erreurs"] = deja[:3]
        if et.get("ok"):
            et["degrade"] = True
    journal["smarkets_cache"] = {"reutilise": bool(perime and precedentes), "perime": perime}
    return lignes, info


def appliquer_matchbook(sports: set, heures: float, maintenant: datetime, journal: dict):
    """Lit Matchbook si ``SOURCE_MATCHBOOK`` n'est pas ``off``.

    ``shadow`` enregistre l'état et ne renvoie aucune ligne : pas de pari.
    ``direct`` (défaut) renvoie les cotes justes. Un 401, 403, 429, un budget
    ou une exception coupent ce lecteur seulement. Le résumé va dans le journal,
    donc dans ``etat.json`` ; aucun corps de réponse n'y est copié.
    """
    actif = matchbook_direct.mode()
    if actif == "off":
        journal["etapes"]["matchbook"] = {"secondes": 0.0, "ok": True, "desactive": True}
        journal["matchbook"] = {"mode": "off", "ok": True, "requetes": 0, "erreurs": [],
                                "matchs": 0, "lignes": 0, "desactive": True}
        return []
    recu = source_bornee(matchbook_direct, "matchbook", journal, BUDGETS["matchbook"],
                         matchbook_direct.collecter, sports, heures, maintenant=maintenant)
    if not isinstance(recu, tuple) or len(recu) != 2:
        info = {"mode": actif, "ok": False, "requetes": 0, "erreurs": ["lecture interrompue"],
                "matchs": 0, "lignes": 0}
        journal["matchbook"] = info
        signaler(journal, "matchbook", info["erreurs"])
        if "matchbook" in journal["etapes"]:
            journal["etapes"]["matchbook"]["ok"] = False
        return []
    lignes, info = recu
    if not isinstance(lignes, list):
        lignes = []
    resume = {"mode": info.get("mode", actif), "ok": bool(info.get("ok")),
              "requetes": info.get("requetes") or 0, "erreurs": list(info.get("erreurs") or [])[:10],
              "matchs": info.get("matchs") or 0, "lignes": len(lignes)}
    journal["matchbook"] = resume
    signaler(journal, "matchbook", resume["erreurs"])
    if not resume["ok"] and "matchbook" in journal["etapes"]:
        journal["etapes"]["matchbook"]["ok"] = False
    if actif != "direct":
        if "matchbook" in journal["etapes"]:
            journal["etapes"]["matchbook"]["shadow"] = True
        return []
    return lignes


def signaler(journal: dict, nom: str, erreurs: list[str]) -> None:
    """Une étape qui a perdu des lectures (HTTP 500, coupure…) est marquée dégradée, pas « ok » muette :
    sinon « aucune source » pour un pari ne dit pas qu'une source était en panne."""
    if erreurs and nom in journal["etapes"]:
        journal["etapes"][nom] |= {"degrade": True, "erreurs": erreurs[:10]}


def noter_lecture(journal: dict, nom: str, meta: dict) -> None:
    """Erreurs d'un lecteur direct dans son étape. Lecture en échec (socket Winamax incomplet, accueil Unibet
    refusé…) : l'étape passe en échec, même si la mémoire des cycles précédents fournit encore des cotes. Sans
    cela, le refus 403 d'Unibet du 21/10 (115 cycles sans aucune cote) restait « ok » et n'alertait pas."""
    signaler(journal, nom, list(meta.get("erreurs") or []))
    if meta.get("ok") is False and nom in journal["etapes"]:
        journal["etapes"][nom]["ok"] = False


def _radar_depuis(lignes) -> list[dict]:
    """Matchs déjà vus (Pinnacle) : sport, équipes, heure. Sert à ne pas tout relire."""
    vus = set()
    out = []
    for ligne in lignes or []:
        if not isinstance(ligne, dict):
            continue
        cle = (ligne.get("sport"), ligne.get("domicile"), ligne.get("exterieur"), ligne.get("debut"))
        if not all(cle) or cle in vus:
            continue
        vus.add(cle)
        out.append({"sport": cle[0], "domicile": cle[1], "exterieur": cle[2], "debut": cle[3]})
    return out


# source du cycle -> clé de sa mémoire dans horizon_direct (cotes/memoire.py, hors branche « donnees »)
MEMOIRES = {"pmu_direct": "pmu", "unibet_direct": "unibet", "betclic_direct": "betclic", "netbet": "netbet"}
AGE_REPLI_MIN = 30


def repli_reserve(bloc: dict, maintenant: datetime) -> tuple[list[dict], dict]:
    """Source coupée par son budget : ses cotes du passage précédent, au lieu de rien.

    Constaté du 23 au 25/10/2026 : 22 cycles Unibet « lecture interrompue » donnaient zéro cote (les cycles à moins
    de 130 000 cotes françaises). Les lignes gardent leur heure de lecture d'origine, donc leur âge reste honnête :
    la fenêtre de 15 minutes de la comparaison et de la prise écarte les trop vieilles. Les matchs commencés
    et les lignes de plus de ``AGE_REPLI_MIN`` minutes sont retirés. La mémoire de la source est conservée telle quelle."""
    limite = maintenant - timedelta(minutes=AGE_REPLI_MIN)
    lignes = []
    for ligne in (bloc.get("lignes") or []) if isinstance(bloc, dict) else []:
        if not isinstance(ligne, dict):
            continue
        debut, lu = _instant(ligne.get("debut")), _instant(ligne.get("collecte"))
        if debut is not None and debut > maintenant and lu is not None and lu >= limite:
            lignes.append(ligne)
    meta = {"ok": False, "erreurs": ["lecture interrompue"], "requetes": 0, "repli": len(lignes)}
    if isinstance(bloc, dict) and bloc:
        meta["reserve"] = bloc
    return lignes, meta


# Un sport reste lu chez les bookmakers français 2 h après sa dernière présence chez les références : un 403
# passager de Pinnacle sur un sport ne le retire pas du cycle suivant.
SPORTS_PRECEDENTS_GARDE_H = 2


def _chemin_sports(reprise_chemin: Path | None) -> Path | None:
    return Path(reprise_chemin).with_name("sports_cycle.json") if reprise_chemin else None


def _sports_vus(reprise_chemin: Path | None) -> dict[str, datetime]:
    chemin = _chemin_sports(reprise_chemin)
    if chemin is None:
        return {}
    try:
        vus = json.loads(chemin.read_text(encoding="utf-8")).get("vus")
    except (OSError, ValueError, AttributeError):
        return {}
    if not isinstance(vus, dict):
        return {}
    return {k: t for k, v in vus.items() if isinstance(k, str) and k and (t := _instant(v)) is not None}


def sports_precedents(reprise_chemin: Path | None, maintenant: datetime) -> set[str] | None:
    """Sports des références (Pinnacle, Polymarket) vus dans les 2 dernières heures, gardés à côté de la reprise
    (cache Actions). ``None`` (absent, illisible ou rien de récent) : les bookmakers français attendent les
    références, comme avant. Ne lève jamais."""
    garde = timedelta(hours=SPORTS_PRECEDENTS_GARDE_H)
    sports = {k for k, t in _sports_vus(reprise_chemin).items() if timedelta(0) <= maintenant - t <= garde}
    return sports or None


def memoriser_sports(reprise_chemin: Path | None, sports: set[str], maintenant: datetime) -> None:
    """Note les sports de ce cycle (heure de dernière présence) pour le suivant. Ne lève jamais."""
    chemin = _chemin_sports(reprise_chemin)
    if chemin is None:
        return
    garde = timedelta(hours=SPORTS_PRECEDENTS_GARDE_H)
    vus = {k: t for k, t in _sports_vus(reprise_chemin).items() if timedelta(0) <= maintenant - t <= garde}
    vus.update({x: maintenant for x in sports if isinstance(x, str) and x})
    try:
        ecrire_json(chemin, {"maj": maintenant.isoformat(timespec="seconds"),
                             "vus": {k: vus[k].isoformat(timespec="seconds") for k in sorted(vus)}})
    except OSError:
        pass


def collecter_prematch(mode: str, maintenant: datetime, journal: dict, donnees: Path | None = None,
                       reprise_chemin: Path | None = None):
    """Pinnacle, Polymarket et les bookmakers français en parallèle.

    Chaque bookmaker est lu directement sur son site (PulseScore n'existe plus) ; la panne
    d'un lecteur n'arrête pas les autres.

    Les bookmakers français (sauf Unibet) partent tout de suite avec les sports vus chez les références dans
    les 2 dernières heures (``sports_cycle.json`` à côté de la reprise), sans attendre Pinnacle (jusqu'à 45 s).
    Sans ce fichier (premier cycle, cache évincé, lecture locale) : ils attendent les références, comme avant.
    Compromis : un sport qui apparaît chez les références n'est lu chez ces bookmakers qu'au cycle suivant
    (5 minutes plus tard), il est noté dans ``journal["sports_francais"]``. Unibet garde le radar Pinnacle du
    cycle, il part donc toujours après Pinnacle avec les sports du cycle.
    """
    limite = maintenant + timedelta(hours=HORIZON_H)

    def sports_des(lignes):
        return {l["sport"] for l in lignes if comparaison._t(l.get("debut"))
                and (maintenant - timedelta(hours=5) if l.get("debut_approximatif") else maintenant)
                    < comparaison._t(l["debut"])
                    <= limite + (timedelta(hours=5) if l.get("debut_approximatif") else timedelta())}

    def mesures_delta(pin, lignes):
        """Diagnostic, pas une nouvelle règle de sélection ; temps réels des lignes lues."""
        refs = [comparaison._t(l.get("collecte")) for l in pin]
        books = [comparaison._t(l.get("collecte")) for l in lignes]
        refs, books = [t for t in refs if t], [t for t in books if t]
        journal["fraicheur_prematch"] = {
            "pinnacle_premiere_lecture": min(refs).isoformat() if refs else None,
            "pinnacle_derniere_lecture": max(refs).isoformat() if refs else None,
            "books_premiere_lecture": min(books).isoformat() if books else None,
            "books_derniere_lecture": max(books).isoformat() if books else None,
            "ecart_enveloppe_secondes": round(max(abs((b-r).total_seconds()) for b in (min(books), max(books))
                                               for r in (min(refs), max(refs))), 1) if refs and books else None,
        }

    rythme_path = donnees / "rythme_sources.json" if donnees else None
    rythme = lire_json(rythme_path, {}) if rythme_path else {}
    if not isinstance(rythme, dict):
        rythme = {}
    # Mémoire de travail (gzip, cache Actions) : absente ou illisible = démarrage à froid, lecture complète.
    horizon = memoire.lire(donnees, "horizon_direct", {}) if donnees else {}
    if not isinstance(horizon, dict):
        horizon = {}
    cotes_avant = historique_cotes.index(horizon) if donnees else {}

    def _reserve(nom: str) -> dict:
        bloc = horizon.get(nom)
        return bloc if isinstance(bloc, dict) else {}

    heures_directes = 12 if mode == "test" else HORIZON_H
    with ThreadPoolExecutor(max_workers=8) as pool:
        journal["pinnacle_configuration"] = {"mode": "environnement" if os.environ.get("PINNACLE_API_KEY", "").strip()
                                                else "guest_historique"}

        def _lire_pinnacle():
            pinnacle._echeance = Echeance(BUDGETS["pinnacle"])
            try:
                return harmoniser_pinnacle(pinnacle.collecter())
            finally:
                pinnacle._echeance = None

        fpin = pool.submit(etape_bornee, "pinnacle", journal, BUDGETS["pinnacle"], _lire_pinnacle)
        fpoly = pool.submit(etape_bornee, "polymarket", journal, BUDGETS["polymarket"],
                            polymarket.collecter, HORIZON_H)
        futurs = {}

        def lancer(nom, module, budget, fonction, *args, **kwargs):
            futurs[nom] = pool.submit(source_bornee, module, nom, journal, budget,
                                      fonction, *args, **kwargs)

        source_oly = olybet_direct.mode_source()
        journal["olybet_source"] = source_oly
        source_net = netbet_direct.mode_source()
        journal["netbet_source"] = source_net

        def lancer_francais(sports_fr):
            """PMU, Winamax, Betclic, OlyBet et NetBet : seul Unibet dépend du radar Pinnacle du cycle."""
            lancer("pmu_direct", pmu_direct, BUDGETS["pmu_direct"], pmu_direct.collecter,
                   sports_fr, heures_directes, reserve=_reserve("pmu"), concurrence=2)
            lancer("winamax_direct", winamax_direct, BUDGETS["winamax_direct"],
                   winamax_direct.collecter, sports_fr, heures_directes, maintenant=maintenant)
            lancer("betclic_direct", betclic_direct, BUDGETS["betclic_direct"],
                   betclic_direct.collecter, sports_fr, heures_directes, maintenant=maintenant,
                   reserve=_reserve("betclic"))
            if source_oly == "direct":
                sports_oly = sports_fr & {"football"} if mode == "test" else sports_fr
                lancer("olybet", olybet_direct, BUDGETS["olybet"], olybet_direct.collecter,
                       sports_oly, 12 if mode == "test" else HORIZON_H)
            if source_net == "direct":
                sports_net = sports_fr & {"football"} if mode == "test" else sports_fr
                # Lecture tournante : la mémoire du passage précédent dit quelles pages relire (cotes/direct/netbet.py).
                lancer("netbet", netbet_direct, BUDGETS["netbet"], netbet_direct.collecter,
                       sports_net, 12 if mode == "test" else HORIZON_H, reserve=_reserve("netbet"))

        precedents = sports_precedents(reprise_chemin, maintenant)
        if precedents:
            lancer_francais(precedents)
        pin, poly = fpin.result() or [], fpoly.result() or []
        # Fraîcheur de la lecture directe seule (avant le secours) : c'est elle que la page Santé affiche.
        ages = [l.get("age_cache_s") for l in pin
                if isinstance(l, dict) and isinstance(l.get("age_cache_s"), int)
                and not isinstance(l.get("age_cache_s"), bool)]
        perimees = sum(1 for l in pin if isinstance(l, dict) and l.get("cote_perimee"))
        lues = len(pin)
        # Secours : sports en erreur HTTP, ou en retard (aucune cote directe fraîche), et seulement avec une clé.
        if pinnacle_secours.disponible():
            a_secourir = pinnacle_secours.sports_a_secourir(list(pinnacle.ERREURS), pin)
            en_retard = pinnacle_secours.sports_en_retard(pin) & a_secourir
            if a_secourir:
                pin = pin + pinnacle_secours.collecter(a_secourir, maintenant, donnees)
                journal["pinnacle_secours"] = {**pinnacle_secours.RESUME, "erreurs": list(pinnacle_secours.ERREURS),
                                               "retard": sorted(pinnacle.SPORTS[s] for s in en_retard)}
        if pinnacle._cle_resolue:
            journal["pinnacle_configuration"] = {"mode": pinnacle.origine_cle}
        journal["pinnacle_fraicheur"] = {
            "seuil_min": pinnacle.age_max_secondes() // 60,
            "seuil_loin_min": pinnacle.age_max_loin_secondes() // 60,
            "proche_h": pinnacle.PROCHE_H,
            "age_max_s": max(ages) if ages else None,
            "age_min_s": min(ages) if ages else None,
            "lignes": lues,
            "lignes_perimees": perimees,
            "rechauffeur": pinnacle.etat_rechauffeur,
            "rechauffeur_detail": pinnacle.resume_rechauffeur(),
            "choix_prix": dict(pinnacle.choix_prix),
        }
        signaler(journal, "pinnacle", list(pinnacle.ERREURS))
        signaler(journal, "polymarket", list(polymarket.ERREURS))
        # Après le secours : un sport resté sans référence reprend son dernier passage (cotes/reprise.py).
        # La panne reste notée dans l'étape ; les bookmakers français lisent encore ce sport.
        repris, journal["reprise"] = reprise.appliquer(reprise_chemin, {"Pinnacle": pin, "Polymarket": poly},
                                                       maintenant)
        pin, poly = pin + repris.get("Pinnacle", []), poly + repris.get("Polymarket", [])
        for nom, etape_nom in (("Pinnacle", "pinnacle"), ("Polymarket", "polymarket")):
            if repris.get(nom) and etape_nom in journal["etapes"]:
                journal["etapes"][etape_nom]["reprise"] = len(repris[nom])
        sports = sports_des(pin + poly)
        if precedents:
            journal["sports_francais"] = {"source": "cycle précédent", "sports": sorted(precedents),
                                          "nouveaux_au_cycle_suivant": sorted(sports - precedents),
                                          "plus_chez_les_references": sorted(precedents - sports)}
        else:
            journal["sports_francais"] = {"source": "références du cycle", "sports": sorted(sports)}
            lancer_francais(sports)
        memoriser_sports(reprise_chemin, sports, maintenant)
        lancer("unibet_direct", unibet_direct, BUDGETS["unibet_direct"],
               unibet_direct.collecter, sports, heures_directes, maintenant=maintenant,
               concurrence=3, radar=_radar_depuis(pin) or None, reserve=_reserve("unibet"))

        recus: dict = {}

        def recevoir(nom):
            if nom in recus:
                return recus[nom]
            if nom not in futurs:
                recus[nom] = ([], {"ok": False, "erreurs": [], "requetes": 0})
                return recus[nom]
            recu = futurs[nom].result()
            if recu is None:
                recus[nom] = repli_reserve(_reserve(MEMOIRES.get(nom, "")), maintenant)
            else:
                recus[nom] = recu
            return recus[nom]

        lignes = []
        metas = {}
        for nom in ("pmu_direct", "winamax_direct", "unibet_direct", "betclic_direct"):
            lues, meta = recevoir(nom)
            noter_lecture(journal, nom, meta)
            lignes += list(lues)
            metas[nom] = meta
        proches = (metas.get("betclic_direct") or {}).get("proches")
        if isinstance(proches, dict):         # matchs proches de Betclic : relances, lectures ratées ou vides
            journal["betclic_proches"] = proches
        if source_oly == "direct":
            oly_lignes, oly_meta = recevoir("olybet")
        else:
            oly_lignes, oly_meta = [], {"ok": False, "erreurs": [], "requetes": 0}
        if source_net == "direct":
            net_lignes, net_meta = recevoir("netbet")
        else:
            net_lignes, net_meta = [], {"ok": False, "erreurs": [], "requetes": 0}
    if source_oly == "direct":
        signaler(journal, "olybet", list(oly_meta.get("erreurs") or []))
        lignes = list(lignes) + list(oly_lignes)
        try:
            refs = list(pin) + [l for l in lignes if l.get("bookmaker") == "pmu"]
            journal["olybet_controle"] = olybet_direct.controle_prix(oly_lignes, refs)
        except Exception as e:  # noqa: BLE001
            journal["olybet_controle"] = {"ok": False, "erreur": type(e).__name__}
    if source_net == "direct":
        signaler(journal, "netbet", list(net_meta.get("erreurs") or []))
        lignes = list(lignes) + list(net_lignes)
        try:
            refs = list(pin) + [l for l in lignes if l.get("bookmaker") == "pmu"]
            journal["netbet_controle"] = netbet_direct.controle_prix(net_lignes, refs)
        except Exception as e:  # noqa: BLE001
            journal["netbet_controle"] = {"ok": False, "erreur": type(e).__name__}
    mesures_delta(pin, lignes)
    if rythme_path is not None:
        ecrire_json(rythme_path, {k: rythme[k] for k in ("pmu", "unibet", "betclic") if k in rythme})
    for nom, meta in (("pmu", metas["pmu_direct"]), ("unibet", metas["unibet_direct"]),
                      ("betclic", metas["betclic_direct"]), ("netbet", net_meta)):
        bloc = meta.get("reserve") if isinstance(meta, dict) else None
        if isinstance(bloc, dict):
            horizon[nom] = bloc
    gardes = ("pmu", "unibet", "betclic", "netbet")
    if donnees and any(k in horizon for k in gardes):
        horizon = {k: horizon[k] for k in gardes if k in horizon}
        memoire.ecrire(donnees, "horizon_direct", horizon)
        try:            # historique en ajout seul : jamais bloquant pour la collecte
            journal["historique_cotes"] = {"lignes": historique_cotes.ajouter(donnees, cotes_avant, horizon,
                                                                               maintenant)}
        except Exception as e:  # noqa: BLE001
            journal["historique_cotes"] = {"erreur": echecs.noter(journal, "historique_cotes", e, maintenant)}
    return pin, poly, lignes


# controle.json (3 Mo) n'est publié dans « donnees » qu'une fois par heure ; la version de chaque cycle vit
# dans la mémoire (controle.json.gz). Mémoire perdue : on repart de la dernière publication (moins d'une heure).
CONTROLE_PUBLICATION_MIN = float(os.environ.get("CONTROLE_PUBLICATION_MIN", "55"))


def _derniere_mesure(doc) -> datetime | None:
    groupes = doc.get("groupes") if isinstance(doc, dict) else None
    moments = [_instant(g.get("maj")) for g in groupes.values() if isinstance(g, dict)] if isinstance(groupes, dict) else []
    moments = [m for m in moments if m is not None]
    return max(moments) if moments else None


def lire_controle(donnees: Path) -> dict:
    """État cumulé du contrôle : la mémoire du cycle précédent, ou la publication horaire si elle est plus
    récente (mémoire absente ou restaurée d'un vieux cache). Publication illisible : erreur, comme avant."""
    publie = lire_json(donnees / "controle.json", {})
    publie = publie if isinstance(publie, dict) else {}
    doc = memoire.lire(donnees, "controle", None, ancien_aussi=False)
    if not isinstance(doc, dict) or (_derniere_mesure(publie) or datetime.min.replace(tzinfo=timezone.utc)) > (
            _derniere_mesure(doc) or datetime.min.replace(tzinfo=timezone.utc)):
        doc = publie
    doc.pop("publie", None)
    return doc


def enregistrer_controle(donnees: Path, etat_controle: dict, maintenant: datetime) -> bool:
    """Mémoire à chaque cycle ; copie compacte dans « donnees » si la dernière date d'au moins 55 min."""
    memoire.ecrire(donnees, "controle", etat_controle, retirer_ancien=False)
    publie = donnees / "controle.json"
    try:
        derniere = _instant(json.loads(publie.read_text(encoding="utf-8")).get("publie"))
    except (OSError, ValueError, AttributeError):
        derniere = None
    if derniere is not None and timedelta(0) <= maintenant - derniere < timedelta(minutes=CONTROLE_PUBLICATION_MIN):
        return False
    ecrire_json(publie, {**etat_controle, "publie": maintenant.isoformat(timespec="seconds")}, compact=True)
    return True


def reglement_echu(etat: dict, maintenant: datetime, mode: str) -> bool:
    """Le cron et la collecte partagent le même délai et le même verrou de données.

    Une date absente ou invalide ne doit pas arrêter le règlement indéfiniment.
    Une petite dérive d'horloge reste tolérée ; une date très future est invalide.
    """
    if mode != "auto":
        return mode == "oui"
    try:
        dernier = datetime.fromisoformat(str(etat.get("dernier_reglement")).replace("Z", "+00:00"))
        if dernier.tzinfo is None or dernier > maintenant + timedelta(minutes=5):
            return True
        return maintenant - dernier >= timedelta(minutes=REGLEMENT_MINUTES)
    except (TypeError, ValueError, OverflowError):
        return True


def conserver_journal_reglement(etat: dict, journal: dict, effectue: bool) -> None:
    """Un cycle sans règlement conserve le dernier diagnostic réel affiché sur le site."""
    if effectue:
        etat["dernier_reglement"] = journal["debut"]
        etat["dernier_cycle_reglement"] = dict(journal)


TEMOIN_ABANDONNE = "Pinnacle brut"


def charger_paris(donnees: Path, journal: dict) -> list[dict]:
    """paris.json sans le témoin « Pinnacle brut », abandonné : il ne servait qu'à mesurer ce que change le retrait
    de la marge (ROI −12,6 % contre −12,8 % avec la marge retirée) et pesait 80 % du fichier. Retiré à la lecture,
    donc sous le verrou de la branche « donnees » ; l'historique reste dans les commits."""
    paris, retires = stockage.retirer_reference(lire_json(donnees / "paris.json", []), TEMOIN_ABANDONNE)
    if retires:
        journal["temoin_pinnacle_brut_retires"] = retires
    return paris


def effectuer_reglement(paris, donnees: Path, maintenant: datetime, journal: dict, mode_reglement: str) -> bool:
    # Le règlement ne lit pas Smarkets : les cotes de l'échange ne servent pas à solder un pari.
    # 4. règlement : ESPN, LiveScore, Flashscore, NHL, API-Sports et les secours, plus les résultats
    #    saisis à la main. Environ une fois par heure, depuis le cron ou la collecte : voir REGLEMENT_MINUTES.
    etat_avant = lire_json(donnees / "etat.json", {})
    dernier_reglement = etat_avant.get("dernier_reglement")
    regler = reglement_echu(etat_avant, maintenant, mode_reglement)
    journal["reglement"] = regler
    if regler:
        resultats_mod.reinitialiser_ignores()
        ouverts_avant = {id(p) for p in paris if p.get("statut") in ("en_cours", "a_regler")}
        manuels = lire_json(donnees / "resultats_manuels.json", {})
        # Les corrections vérifiées sont disponibles sans nouvelle requête réseau.
        reglement.appliquer(paris, {}, manuels, maintenant)
        enregistrements = []
        for sport, depuis in resultats_mod.a_lire(paris, maintenant).items():
            n = len(resultats_mod.ERREURS_ESPN)
            enregistrements += etape(f"resultats_espn_{sport}", journal, resultats_mod.lire_espn,
                                     sport, depuis, datetime.now(timezone.utc)) or []
            signaler(journal, f"resultats_espn_{sport}", resultats_mod.ERREURS_ESPN[n:])
        # LiveScore : gratuit, sans clé (football, hockey, basket, tennis)
        for sport, depuis in livescore.a_lire(paris, maintenant).items():
            n = len(livescore.ERREURS)
            enregistrements += etape(f"resultats_livescore_{sport}", journal, livescore.lire, sport,
                                     livescore.jours_a_lire(depuis, maintenant)) or []
            signaler(journal, f"resultats_livescore_{sport}", livescore.ERREURS[n:])
        nhl = etape("resultats_nhl_officiel", journal, resultats_nhl.collecter, paris, maintenant)
        if nhl:
            enregistrements += nhl[0]
            signaler(journal, "resultats_nhl_officiel", nhl[1])
        resultats = {}
        for p in paris:
            if p["statut"] in ("en_cours", "a_regler") and p["match_id"] not in resultats:
                r = resultats_mod.consensus(p, enregistrements, maintenant)
                if r:
                    resultats[p["match_id"]] = r
        # Flashscore : secours gratuit pour ce qu'aucune source n'a validé, et seule source du volley, du handball
        # et du rugby sans PulseScore (une source seule ne règle qu'après 24 h : cotes/resultats.py)
        restants = [p for p in paris if p["statut"] in ("en_cours", "a_regler") and p["match_id"] not in resultats]
        for sport, jours in flashscore.jours_a_lire(restants, maintenant).items():
            n = len(flashscore.ERREURS)
            enregistrements += etape(f"resultats_flashscore_{sport}", journal, flashscore.lire, sport, jours,
                                     maintenant) or []
            signaler(journal, f"resultats_flashscore_{sport}", flashscore.ERREURS[n:])
        for p in restants:
            if p["match_id"] not in resultats:
                r = resultats_mod.consensus(p, enregistrements, maintenant)
                if r:
                    resultats[p["match_id"]] = r
        # API-Sports, pour les paris que les autres sources n'ont pas réglés (quota gratuit : 100 requêtes par
        # jour et par sport ; réponses gardées en cache dans donnees/apisports.json)
        cle_ap = os.environ.get("API_SPORTS_KEY", "").strip()
        if cle_ap:
            cache_ap = resultats_mod.elaguer_cache_apisports(lire_json(donnees / "apisports.json", {}), maintenant)
            quota_ap = {}
            # matchs déjà validés ailleurs mais sans le détail des périodes dont un pari a besoin (mi-temps…)
            besoin = {p["match_id"] for p in paris if p["statut"] in ("en_cours", "a_regler")
                      and (p["periode"] != "MATCH" or p["marche"] == "HALF_TIME_FULL_TIME")}
            complets = {m for m, r in resultats.items() if r.get("periodes") or m not in besoin}
            for sport, jours in resultats_mod.jours_a_lire(paris, complets, maintenant).items():
                n = len(resultats_mod.ERREURS_APISPORTS)
                lu = etape(f"resultats_apisports_{sport}", journal, resultats_mod.lire_apisports,
                           cle_ap, sport, jours, cache_ap, datetime.now(timezone.utc))
                signaler(journal, f"resultats_apisports_{sport}", resultats_mod.ERREURS_APISPORTS[n:])
                if lu:
                    enregistrements += lu[0]
                    quota_ap |= lu[1]
            ecrire_json(donnees / "apisports.json", cache_ap)
            for p in paris:
                if p["statut"] in ("en_cours", "a_regler") and p["match_id"] not in complets:
                    r = resultats_mod.consensus(p, enregistrements, maintenant)
                    if r:
                        resultats[p["match_id"]] = r
            journal["apisports_quota_restant"] = quota_ap
        # TheSportsDB : secours gratuit (clé publique), match par match, pour ce qu'aucune source n'a validé.
        # Seul le score final : une source seule ne règle qu'après 24 h, jamais au hockey (cotes/resultats.py).
        restants_tsdb = [p for p in paris if p["statut"] in ("en_cours", "a_regler") and p["match_id"] not in resultats]
        if restants_tsdb:
            cache_ts = lire_json(donnees / "thesportsdb.json", {})
            n = len(thesportsdb.ERREURS)
            enregistrements += etape("resultats_thesportsdb", journal, thesportsdb.collecter,
                                     restants_tsdb, cache_ts, datetime.now(timezone.utc)) or []
            ecrire_json(donnees / "thesportsdb.json", cache_ts)
            signaler(journal, "resultats_thesportsdb", thesportsdb.ERREURS[n:])
            journal["thesportsdb"] = dict(thesportsdb.RESUME)
            for p in restants_tsdb:
                if p["match_id"] not in resultats:
                    r = resultats_mod.consensus(p, enregistrements, maintenant)
                    if r:
                        resultats[p["match_id"]] = r
        # mi-temps ESPN pour les paris qui en ont besoin (mi-temps/fin, 1re ou 2e mi-temps)
        for p in paris:
            r = resultats.get(p["match_id"])
            if r and p["statut"] in ("en_cours", "a_regler") and (
                    p["periode"] in reglement.SOUS_PERIODES or p["marche"] == "HALF_TIME_FULL_TIME"):
                resultats[p["match_id"]] = resultats_mod.completer_periodes(p, r, enregistrements)
        # Secours The Odds API uniquement pour les résultats encore manquants.
        # Les quatre comptes partagent le cache, jamais quatre voix au consensus.
        cles_odds = [os.environ.get(f"THE_ODDS_API_KEY_{i}", "").strip() for i in range(1, 5)]
        journal["theodds"] = {"cles_configurees": sum(bool(c) for c in set(cles_odds))}
        if any(cles_odds):
            cache_odds = lire_json(donnees / "theodds.json", {})
            secours = etape("resultats_theodds", journal, theodds.collecter,
                           paris, resultats, enregistrements, cles_odds, cache_odds, datetime.now(timezone.utc))
            ecrire_json(donnees / "theodds.json", cache_odds)
            if secours:
                resultats.update(secours[0])
                journal["theodds"] = secours[1]
                signaler(journal, "resultats_theodds", secours[1]["erreurs"])
        # Scores gratuits Prop-Line : secours indépendant des clés The Odds API,
        # sans compter ses données ESPN comme une voix supplémentaire au consensus.
        cle_prop = os.environ.get("PROPLINE_API_KEY", "").strip()
        journal["propline"] = {"configure": bool(cle_prop)}
        if cle_prop:
            cache_prop = lire_json(donnees / "propline.json", {})
            secours = etape("resultats_propline", journal, propline.collecter,
                           paris, resultats, enregistrements, cle_prop, cache_prop, datetime.now(timezone.utc))
            ecrire_json(donnees / "propline.json", cache_prop)
            if secours:
                resultats.update(secours[0])
                journal["propline"] = secours[1]
                signaler(journal, "resultats_propline", secours[1]["erreurs"])
        journal["resultats"] = {"enregistrements": len(enregistrements), "matchs_valides": len(resultats)}
        # matchs reportés (vus « à venir » chez ESPN à une date plus tardive) : ils restent en cours
        reportes = {p["match_id"]: d for p in paris
                    if p["statut"] in ("en_cours", "a_regler") and p["match_id"] not in resultats
                    and (d := resultats_mod.reporte(p, enregistrements))}
        journal["resultats"]["reportes"] = len(reportes)
        reglement.appliquer(paris, resultats, manuels, maintenant, reportes)
        # pourquoi les paris « à régler » ne se règlent pas (pour le diagnostic)
        vus = set()
        journal["resultats"]["non_regles"] = [
            resultats_mod.diagnostic(p, enregistrements, maintenant) for p in paris
            if p["statut"] == "a_regler" and p["match_id"] not in vus and not vus.add(p["match_id"])]
        attente = [p for p in paris if p["statut"] == "a_regler"]
        journal["resultats"]["paris_en_attente"] = len(attente)
        journal["resultats"]["paris_regles"] = sum(id(p) in ouverts_avant and p.get("statut") in reglement.GAIN for p in paris)
        # Même regroupement que le compteur « À régler » du site : une sélection
        # commune aux références n'est comptée qu'une fois.
        selections = {tuple(p.get(c) for c in ("match_id", "marche", "periode", "ligne", "issue", "joueur"))
                      for p in attente}
        journal["resultats"]["selections_en_attente"] = len(selections)
        journal["resultats"]["ignores"] = list(resultats_mod.RESULTATS_IGNORES)
        journal["resultats"]["ignores_limite"] = resultats_mod.IGNORES_MAX
        journal["resultats"]["paris_avec_alertes"] = sum(bool(p.get("alertes")) for p in paris
                                                         if p.get("statut") in ("en_cours", "a_regler"))
        # Quelles sources ont réglé les paris de ce cycle
        sources_reglees: dict = {}
        for p in paris:
            if id(p) in ouverts_avant and p.get("statut") in reglement.GAIN:
                for src in (p.get("preuve_reglement") or {}).get("sources") or ["saisie manuelle"]:
                    sources_reglees[src] = sources_reglees.get(src, 0) + 1
        journal["resultats"]["sources_reglement"] = sources_reglees
        # Rien ne règle ces matchs : la liste est prête à être complétée à la main
        ecrire_json(donnees / "resultats_a_saisir.json",
                    {"genere": maintenant.isoformat(timespec="seconds"),
                     "aide": "Copier `modele` dans resultats_manuels.json sous chaque clé de `match_ids`, y remplir le score.",
                     "matchs": resultats_mod.a_saisir(paris, enregistrements, maintenant)})
    else:
        journal["resultats"] = {"saute": True, "dernier_reglement": dernier_reglement}

    return regler


def redecider(registre: list, maintenant: datetime, journal: dict, redecider_ouverts) -> None:
    """Redécision des paris ouverts. Jamais bloquante ; un échec est annoncé et noté (cotes/echecs.py)."""
    try:
        journal["redecision"] = {"ajoutees": redecider_ouverts(registre, maintenant)}
    except Exception as e:      # une correction ratée ne doit jamais arrêter la collecte
        journal["redecision"] = {"erreur": echecs.noter(journal, "redecision", e, maintenant)}


def suivre_qwen(donnees: Path, registre: list, opportunites: list, maintenant: datetime, journal: dict) -> None:
    """Qwen : validation après deux cycles consécutifs. Jamais bloquante ; un échec est annoncé et noté."""
    try:
        from cotes import strategie_qwen
        chemin_qwen = donnees / "persistance_qwen.json"
        etat_qwen, vues_qwen = strategie_qwen.suivre(lire_json(chemin_qwen, {}), opportunites, maintenant, journal["debut"])
        journal["qwen"] = strategie_qwen.valider(registre, vues_qwen, maintenant)
        ecrire_json(chemin_qwen, etat_qwen)
    except Exception as e:  # noqa: BLE001
        journal["qwen"] = {"erreur": echecs.noter(journal, "qwen", e, maintenant)}


def main() -> int:
    a = argparse.ArgumentParser()
    a.add_argument("--mode", choices=["complet", "test"], default=os.environ.get("MODE_COLLECTE", "complet"))
    a.add_argument("--donnees", default="donnees")
    a.add_argument("--site", default="site")
    a.add_argument("--sans-site", action="store_true",
                   help="Sauvegarder la collecte avant le chemin rapide d'alertes ; site construit ensuite")
    a.add_argument("--reglement", choices=["auto", "oui", "non"], default=os.environ.get("REGLEMENT", "auto"),
                   help="auto = si le dernier règlement date d'au moins REGLEMENT_MINUTES")
    a.add_argument("--reprise", default=os.environ.get("REPRISE_CHEMIN", ""),
                   help="Dernier bon état des références (gzip, hors branche « donnees ») ; vide = aucune reprise")
    a.add_argument("--seulement-reglement", action="store_true",
                   help="Régler les paris sans interroger les cotes ni créer de nouveaux paris")
    args = a.parse_args()
    donnees = Path(args.donnees)
    maintenant = datetime.now(timezone.utc)
    journal = {"debut": maintenant.isoformat(timespec="seconds"), "mode": args.mode, "etapes": {}}

    if args.seulement_reglement:
        # Cycle indépendant : aucune collecte ni placement de paris.
        paris = charger_paris(donnees, journal)
        manuels = lire_json(donnees / "resultats_manuels.json", {})
        paris = [p for p in paris if manuels.get(p["id"]) != "supprime"]
        journal["mode"] = "reglement"
        regler = effectuer_reglement(paris, donnees, maintenant, journal, args.reglement)
        paris = stockage.archiver(donnees, paris, maintenant)
        liens.completer_liens(paris)
        ecrire_json(donnees / "paris.json", paris)
        etat = lire_json(donnees / "etat.json", {})
        journal["fin"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        conserver_journal_reglement(etat, journal, regler)
        echecs.fusionner(etat, journal.get("echecs", []), maintenant)
        ecrire_json(donnees / "etat.json", etat)
        from site_web import construire
        construire(donnees, Path(args.site))
        print(json.dumps({"mode": "reglement", "resultats": journal.get("resultats"), "theodds": journal.get("theodds"),
                          "etapes": journal.get("etapes", {})}, ensure_ascii=False))
        return 0

    # Matchbook ne dépend d'aucune autre source (sports fixes) : lu dès le départ, en parallèle de la collecte,
    # au lieu d'attendre Pinnacle, les bookmakers français puis Smarkets. Son résultat n'est lu qu'au même endroit.
    sports_mb = {"football"} if args.mode == "test" else {"football", "tennis"}
    pool_mb = ThreadPoolExecutor(max_workers=1, thread_name_prefix="matchbook")
    futur_mb = pool_mb.submit(appliquer_matchbook, sports_mb, 12 if args.mode == "test" else HORIZON_H,
                              maintenant, journal)
    pool_mb.shutdown(wait=False)
    pin, poly, francais = collecter_prematch(args.mode, maintenant, journal, donnees,
                                             Path(args.reprise) if args.reprise else None)
    references = {"Pinnacle": pin, "Polymarket": poly}
    # Smarkets reste hors de `francais` : bookmaker « smarkets » n'est pas un book français.
    sports_sm = {"football"} if args.mode == "test" else {l["sport"] for l in francais if l.get("sport")}
    sm_lignes, sm_info = appliquer_smarkets(
        donnees, sports_sm, 12 if args.mode == "test" else HORIZON_H,
        smarkets.radar_depuis(francais), maintenant, journal)
    erreurs_sm = list(sm_info.get("erreurs") or [])
    if journal.get("smarkets_cache", {}).get("perime") and "périmé" not in erreurs_sm:
        erreurs_sm.append("périmé")
    signaler(journal, "smarkets", erreurs_sm)
    journal["smarkets_dans_decision"] = smarkets.dans_decision()
    # Table propre. Le drapeau ne retire que le consensus partagé.
    smarkets.ajouter_table(references, sm_lignes)
    try:
        mb_lignes = futur_mb.result()
    except Exception as e:  # noqa: BLE001 - appliquer_matchbook ne lève pas ; garde-fou
        journal["matchbook"] = {"mode": matchbook_direct.mode(), "ok": False, "requetes": 0,
                                "erreurs": [type(e).__name__], "matchs": 0, "lignes": 0}
        mb_lignes = []
    if mb_lignes:
        references["Matchbook"] = mb_lignes
    # Matchbook a sa table de paris (mêmes seuils que Pinnacle). Il reste hors
    # de la moyenne : le Consensus et le désaccord des tables déjà en place
    # ne changent pas, donc les stratégies figées non plus.
    hors = smarkets.hors_consensus() | matchbook_direct.hors_consensus()

    # 3. contrôle de conformité des marchés (cumulé d'un cycle à l'autre), comparaison et paris simulés :
    #    seules les cotes dont l'intitulé est contrôlé conforme peuvent donner un pari.
    #    Le contrôle reste celui des références déjà en place : Smarkets a sa table,
    #    pas une nouvelle mesure de conformité.
    index = etape("association", journal, comparaison.indexer, francais, references) or {}
    index_controle = {n: v for n, v in index.items() if n not in ("Smarkets", "Matchbook")}
    mesures = controle.mesurer(francais, index_controle)
    etat_controle = controle.mettre_a_jour(lire_controle(donnees), mesures, journal["debut"])
    suspects = controle.matchs_suspects(mesures)
    etat_controle["matchs_suspects"] = [
        {"match_id": l["match_id"], "bookmaker": l["source"], "match": f'{l["domicile"]} – {l["exterieur"]}',
         "rapport_median": suspects[l["match_id"]]}
        for l in {l["match_id"]: l for l, *_ in mesures if l["match_id"] in suspects}.values()]
    journal["controle"] = controle.resume(etat_controle) | {"mesures": len(mesures),
                                                            "matchs_suspects": len(suspects)}
    opportunites = etape("comparaison", journal, comparaison.comparer, francais, references,
                         index=index, controle=(etat_controle, suspects),
                         hors_consensus=hors) or []
    for o in opportunites:           # marqueur de cycle : sert à la persistance (Qwen) et au diagnostic
        o["cycle_id"] = journal["debut"]
    # Mouvement de la cote juste de Pinnacle (dropping odds) : descriptif, inscrit dans le pari. Jamais bloquant.
    from cotes import mouvement
    journal["mouvement"] = mouvement.annoter(
        opportunites, index,
        Path(args.reprise).with_name("ancres_mouvement.json.gz") if args.reprise else None, maintenant)
    # Écarts d'affichage, y compris quand Smarkets ne décide pas. Avant le placement :
    # le pari enregistre les trois champs.
    # L'index de l'association contient déjà Polymarket et Smarkets (mêmes lignes) : pas de seconde association.
    references_ecarts = {"Polymarket": poly, "Smarkets": sm_lignes}
    comparaison.annoter_ecarts(opportunites, francais, references_ecarts,
                               index={n: index[n] for n in references_ecarts
                                      if n in index and references.get(n) is references_ecarts[n]})
    paris = charger_paris(donnees, journal)
    # paris annulés à la main (pris sur un match mal associé) : « supprime » dans resultats_manuels.json
    manuels = lire_json(donnees / "resultats_manuels.json", {})
    paris = [p for p in paris if manuels.get(p["id"]) != "supprime"]
    nouveaux = simulation.placer(opportunites, paris)
    from cotes.decisions import figer_nouveaux, redecider_ouverts
    registre = stockage.fusionner_paris(paris, stockage.lire_archives(donnees))
    figer_nouveaux(registre, nouveaux)
    redecider(registre, maintenant, journal, redecider_ouverts)
    suivre_qwen(donnees, registre, opportunites, maintenant, journal)
    simulation.suivre_prix(paris, francais)
    justes = etape("cotes_cloture", journal, comparaison.cotes_justes_depuis, index,
                   hors_consensus=hors) or {}
    simulation.suivre_cloture(paris, justes)      # heure réelle : un match peut commencer pendant le cycle

    # La collecte reprend le règlement si le workflow horaire a été retardé.
    regler = effectuer_reglement(paris, donnees, maintenant, journal, args.reglement)

    # 5. sauvegarde
    paris = stockage.archiver(donnees, paris, maintenant)      # réglés depuis plus de 30 jours -> archives
    liens.completer_liens(paris)                              # lien direct vers le match chez le bookmaker
    ecrire_json(donnees / "paris.json", paris)
    journal["controle_publie"] = enregistrer_controle(donnees, etat_controle, maintenant)
    ecrire_json(donnees / "opportunites_actuelles.json", sorted(opportunites, key=lambda o: -o["ecart"]))
    if opportunites:
        jour = donnees / "opportunites" / f"{maintenant:%Y-%m-%d}.jsonl.gz"
        jour.parent.mkdir(parents=True, exist_ok=True)
        # Ajout atomique (copie + nouveau membre gzip + os.replace) : un job tué ne tronque jamais le fichier.
        ajouter_gzip(jour, "".join(json.dumps(o, ensure_ascii=False) + "\n" for o in opportunites))
    etat = lire_json(donnees / "etat.json", {})
    journal.update({
        "fin": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cotes": {"francaises": len(francais), "pinnacle": len(pin), "polymarket": len(poly),
                  "smarkets": len(sm_lignes), "matchbook": len(mb_lignes)},
        "matchs_francais": len({l["match_id"] for l in francais}),
        "opportunites": sum(not o.get("suspect") for o in opportunites),
        "opportunites_suspectes": sum(bool(o.get("suspect")) for o in opportunites),
        "nouveaux_paris": len(nouveaux)})
    etat.pop("requetes_par_mois", None)     # compteur de l'ancien abonnement PulseScore
    etat.update({"dernier_cycle": journal})
    echecs.fusionner(etat, journal.get("echecs", []), maintenant)
    conserver_journal_reglement(etat, journal, regler)
    historique = etat.get("historique", [])[-200:] + [{k: journal[k] for k in ("debut", "mode", "opportunites",
                                                                                "nouveaux_paris")}]
    etat["historique"] = historique
    ecrire_json(donnees / "etat.json", etat)
    from cotes import surveillance                                      # noqa: E402
    journal["surveillance"] = surveillance.surveiller(donnees, journal.get("etapes", {}))

    # 6. site
    if not args.sans_site:
        from site_web import construire                                 # noqa: E402
        construire(donnees, Path(args.site))
    print(json.dumps({k: journal[k] for k in ("mode", "cotes", "matchs_francais", "opportunites", "nouveaux_paris",
                                               "controle", "etapes")}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
