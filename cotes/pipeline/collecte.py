"""Collecte du cycle (déplacée de scripts/cycle.py, E3.5) : Pinnacle, Polymarket et les bookmakers français en
parallèle, bourses (Smarkets, Matchbook, Betfair), références des props, réserves, sports du cycle précédent et dérive
des sources. Chaque source a un budget dur (cotes/sources/registre.py) : au-delà, elle est sautée et le cycle continue.
"""
from __future__ import annotations

import json
import os
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

from cotes import (comparaison, derive, echecs, historiques, inconnus, memoire, pinnacle, pinnacle_secours,
                   polymarket, reprise, smarkets)
from cotes.delai import Echeance
from cotes.depot.json_io import ecrire_json, lire_json
from cotes.direct import betfair as betfair_direct
from cotes.direct import draftkings as draftkings_direct
from cotes.direct import fanduel as fanduel_direct
from cotes.direct import matchbook as matchbook_direct
from cotes.direct import netbet as netbet_direct
from cotes.direct import olybet as olybet_direct
from cotes.direct import unibet as unibet_direct
from cotes.fraicheur import resume_lignes
from cotes.marches import harmoniser_pinnacle
from cotes.pipeline.contexte import Contexte
from cotes.pipeline.outils import signaler
from cotes.sources import registre as registre_sources
from cotes.temps import instant_utc

HORIZON_H = 36
# Budgets durs : une source au-delà est sautée, le cycle de 5 min continue (cotes/sources/registre.py).
BUDGETS = registre_sources.budgets()
SMARKETS_FRAIS_MIN = 15
_journal_lock = threading.Lock()



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
    return instant_utc(valeur)


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
    return _appliquer_bourse(matchbook_direct, "matchbook", sports, heures, maintenant, journal)


def appliquer_betfair(sports: set, heures: float, maintenant: datetime, journal: dict):
    """Betfair Exchange (``SOURCE_BETFAIR`` ; ``off`` par défaut hors serveur, l'IP de GitHub est refusée).
    Mêmes règles que Matchbook : ``shadow`` ne renvoie rien, un refus ou un budget ne coupent que ce lecteur."""
    return _appliquer_bourse(betfair_direct, "betfair", sports, heures, maintenant, journal)


def _appliquer_bourse(module, cle: str, sports: set, heures: float, maintenant: datetime, journal: dict):
    actif = module.mode()
    if actif == "off":
        journal["etapes"][cle] = {"secondes": 0.0, "ok": True, "desactive": True}
        journal[cle] = {"mode": "off", "ok": True, "requetes": 0, "erreurs": [],
                        "matchs": 0, "lignes": 0, "desactive": True}
        return []
    recu = source_bornee(module, cle, journal, BUDGETS[cle], module.collecter, sports, heures, maintenant=maintenant)
    if not isinstance(recu, tuple) or len(recu) != 2:
        info = {"mode": actif, "ok": False, "requetes": 0, "erreurs": ["lecture interrompue"],
                "matchs": 0, "lignes": 0}
        journal[cle] = info
        signaler(journal, cle, info["erreurs"])
        if cle in journal["etapes"]:
            journal["etapes"][cle]["ok"] = False
        return []
    lignes, info = recu
    if not isinstance(lignes, list):
        lignes = []
    resume = {"mode": info.get("mode", actif), "ok": bool(info.get("ok")),
              "requetes": info.get("requetes") or 0, "erreurs": list(info.get("erreurs") or [])[:10],
              "matchs": info.get("matchs") or 0, "lignes": len(lignes)}
    journal[cle] = resume
    # Résumé pour la page Santé : n'altère pas les lignes, ni cote_perimee, ni les sélecteurs.
    journal[f"{cle}_fraicheur"] = resume_lignes(lignes)
    signaler(journal, cle, resume["erreurs"])
    if not resume["ok"] and cle in journal["etapes"]:
        journal["etapes"][cle]["ok"] = False
    if actif != "direct":
        if cle in journal["etapes"]:
            journal["etapes"][cle]["shadow"] = True
        return []
    return lignes


def noter_lecture(journal: dict, nom: str, meta: dict) -> None:
    """Erreurs d'un lecteur direct dans son étape. Lecture en échec (socket Winamax incomplet, accueil Unibet
    refusé…) : l'étape passe en échec, même si la mémoire des cycles précédents fournit encore des cotes. Sans
    cela, le refus 403 d'Unibet du 21/10 (115 cycles sans aucune cote) restait « ok » et n'alertait pas."""
    signaler(journal, nom, list(meta.get("erreurs") or []))
    if meta.get("ok") is False and nom in journal["etapes"]:
        journal["etapes"][nom]["ok"] = False
    if meta.get("relances") and nom in journal["etapes"]:        # demandes ratées puis relues avec succès
        journal["etapes"][nom]["relances"] = list(meta["relances"])[:10]


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
MEMOIRES = registre_sources.memoires()
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

    # Mémoire de travail (gzip, cache Actions) : absente ou illisible = démarrage à froid, lecture complète.
    horizon = memoire.lire(donnees, "horizon_direct", {}) if donnees else {}
    if not isinstance(horizon, dict):
        horizon = {}
    cotes_avant = historiques.index_cotes(horizon) if donnees else {}

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
        source_fd = fanduel_direct.mode()
        journal["fanduel_source"] = source_fd
        fd_lignes, fd_meta = [], {"ok": True, "erreurs": [], "requetes": 0, "props": 0, "mode": "off"}
        if source_fd == "direct":
            # Référence props seulement : ne rejoint pas les cotes françaises ni les paris.
            lancer("fanduel", fanduel_direct, BUDGETS["fanduel"], fanduel_direct.collecter,
                   {"basket", "hockey"}, heures_directes, maintenant=maintenant)

        source_dk = draftkings_direct.mode()
        journal["draftkings_source"] = source_dk
        dk_lignes, dk_meta = [], {"ok": True, "erreurs": [], "requetes": 0, "props": 0, "mode": "off"}
        if source_dk == "direct":
            # Référence seulement (matchs NBA, NHL, NFL, MLB et props NBA, NHL) : ni cotes françaises ni paris.
            lancer("draftkings", draftkings_direct, BUDGETS["draftkings"], draftkings_direct.collecter,
                   None, heures_directes, maintenant=maintenant)

        def lancer_francais(sports_fr):
            """Bookmakers français du registre (cotes/sources/registre.py) : seul Unibet dépend du radar Pinnacle."""
            for s in registre_sources.ordre_de_lancement():
                if s.mode() != "direct":
                    continue
                sports_s = sports_fr & s.sports_test if mode == "test" and s.sports_test is not None else sports_fr
                options = {}
                if s.avec_maintenant:
                    options["maintenant"] = maintenant
                if s.memoire:
                    options["reserve"] = _reserve(s.memoire)
                if s.concurrence:
                    options["concurrence"] = s.concurrence
                lancer(s.nom, s.module, BUDGETS[s.nom], s.module.collecter, sports_s, heures_directes, **options)

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
            "rechauffeur_cause": pinnacle.cause_rechauffeur,
            "rechauffeur_duree_s": pinnacle.duree_rechauffeur_s,
            "rechauffeur_detail": pinnacle.resume_rechauffeur(),
            "choix_prix": dict(pinnacle.choix_prix),
        }
        signaler(journal, "pinnacle", list(pinnacle.ERREURS))
        signaler(journal, "polymarket", list(polymarket.ERREURS))
        journal["polymarket_flux"] = dict(polymarket.FLUX)     # prix du websocket repris (serveur en direct)
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
        rotation_ub = (metas.get("unibet_direct") or {}).get("rotation")
        if isinstance(rotation_ub, dict):     # Unibet : filtres secondaires lancés ce cycle sur le tour complet
            journal["unibet_rotation"] = rotation_ub
        onglets_bc = (metas.get("betclic_direct") or {}).get("onglets_vus")
        if isinstance(onglets_bc, dict):      # onglets proposés par sport : repérer un onglet renommé
            journal["betclic_onglets"] = onglets_bc
        if source_oly == "direct":
            oly_lignes, oly_meta = recevoir("olybet")
        else:
            oly_lignes, oly_meta = [], {"ok": False, "erreurs": [], "requetes": 0}
        if source_net == "direct":
            net_lignes, net_meta = recevoir("netbet")
        else:
            net_lignes, net_meta = [], {"ok": False, "erreurs": [], "requetes": 0}
        if source_fd == "direct":
            recu = recevoir("fanduel")
            if isinstance(recu, tuple) and len(recu) == 2:
                fd_lignes, fd_meta = recu
            else:
                fd_lignes, fd_meta = [], {"ok": False, "erreurs": ["lecture interrompue"], "requetes": 0}
        if source_dk == "direct":
            recu = recevoir("draftkings")
            if isinstance(recu, tuple) and len(recu) == 2:
                dk_lignes, dk_meta = recu
            else:
                dk_lignes, dk_meta = [], {"ok": False, "erreurs": ["lecture interrompue"], "requetes": 0}
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
    if source_fd == "direct":
        noter_lecture(journal, "fanduel", fd_meta if isinstance(fd_meta, dict) else {})
        journal["fanduel"] = {
            "mode": "direct", "ok": bool((fd_meta or {}).get("ok")),
            "requetes": (fd_meta or {}).get("requetes") or 0,
            "matchs": (fd_meta or {}).get("matchs") or 0,
            "props": (fd_meta or {}).get("props") or 0,
            "ignores": (fd_meta or {}).get("ignores") or 0,
            "avertissements": list((fd_meta or {}).get("avertissements") or [])[:5],
        }
    else:
        journal["fanduel"] = {"mode": "off", "ok": True, "requetes": 0, "props": 0}
    try:
        from cotes.props import comparer_fanduel
        journal["props_fanduel"] = comparer_fanduel(fd_lignes, pin)
    except Exception as e:  # noqa: BLE001 - la comparaison FanDuel ne coupe pas le cycle
        journal["props_fanduel"] = {"ok": False, "erreur": type(e).__name__, "reference_seule": True,
                                    "rapproches": 0, "non_rapproches": 0}
    # DraftKings : même rôle que FanDuel pour les props, plus les lignes de match NBA, NHL, NFL et MLB.
    if source_dk == "direct":
        noter_lecture(journal, "draftkings", dk_meta if isinstance(dk_meta, dict) else {})
        journal["draftkings"] = {"mode": "direct", "ok": bool((dk_meta or {}).get("ok")),
                                 **{k: (dk_meta or {}).get(k) or 0 for k in ("requetes", "matchs", "lignes", "props", "ignores")},
                                 "avertissements": list((dk_meta or {}).get("avertissements") or [])[:5]}
    else:
        journal["draftkings"] = {"mode": "off", "ok": True, "requetes": 0, "lignes": 0, "props": 0}
    try:
        from cotes.props import comparer_matchs, comparer_reference
        journal["props_draftkings"] = comparer_reference(dk_lignes, pin, "draftkings")
        journal["matchs_draftkings"] = comparer_matchs(dk_lignes, pin, "draftkings")
    except Exception as e:  # noqa: BLE001 - la comparaison DraftKings ne coupe pas le cycle
        journal["props_draftkings"] = {"ok": False, "erreur": type(e).__name__, "reference_seule": True,
                                       "rapproches": 0, "non_rapproches": 0}
        journal["matchs_draftkings"] = {"ok": False, "erreur": type(e).__name__, "reference_seule": True}
    mesures_delta(pin, lignes)
    for nom, meta in (("pmu", metas["pmu_direct"]), ("unibet", metas["unibet_direct"]),
                      ("betclic", metas["betclic_direct"]), ("netbet", net_meta)):
        bloc = meta.get("reserve") if isinstance(meta, dict) else None
        if isinstance(bloc, dict):
            horizon[nom] = bloc
    from cotes.joueurs import est_joueur
    horizon["props"] = {"lignes": [l for l in list(pin) + list(lignes) + list(fd_lignes)
                                    if est_joueur(l.get("marche"))]}
    # Winamax et OlyBet n'ont pas de mémoire de lecture : leurs marchés hors props ne sont gardés que pour
    # l'historique (seuls les changements sont écrits au cycle suivant). Lecture vide (panne) : dernier état gardé.
    for nom, source in (("winamax", "Winamax"), ("olybet", "OlyBet")):
        a_garder = [l for l in lignes if l.get("source") == source and not est_joueur(l.get("marche"))]
        if a_garder:
            horizon[nom] = {"lignes": a_garder}
    gardes = ("pmu", "unibet", "betclic", "netbet", "props", "winamax", "olybet")
    if donnees and any(k in horizon for k in gardes):
        horizon = {k: horizon[k] for k in gardes if k in horizon}
        memoire.ecrire(donnees, "horizon_direct", horizon)
        try:            # historique en ajout seul : jamais bloquant pour la collecte
            journal["historique_cotes"] = {"lignes": historiques.ajouter_cotes(donnees, cotes_avant, horizon,
                                                                               maintenant)}
        except Exception as e:  # noqa: BLE001
            journal["historique_cotes"] = {"erreur": echecs.noter(journal, "historique_cotes", e, maintenant)}
    return pin, poly, lignes



def collecter(ctx: Contexte) -> None:
    """Remplit les lignes du cycle (``ctx.pinnacle``, ``ctx.francais``, bourses…), ``ctx.references`` et
    ``ctx.hors_consensus`` ; écrit marches_inconnus.json et la mémoire de travail."""
    donnees, maintenant, journal, mode = ctx.donnees, ctx.maintenant, ctx.journal, ctx.mode
    # Matchbook ne dépend d'aucune autre source (sports fixes) : lu dès le départ, en parallèle de la collecte,
    # au lieu d'attendre Pinnacle, les bookmakers français puis Smarkets. Son résultat n'est lu qu'au même endroit.
    sports_mb = {"football"} if mode == "test" else {"football", "tennis"}
    pool_mb = ThreadPoolExecutor(max_workers=2, thread_name_prefix="bourses")
    futur_mb = pool_mb.submit(appliquer_matchbook, sports_mb, 12 if mode == "test" else HORIZON_H,
                              maintenant, journal)
    # Betfair, même logique (sports fixes, aucune dépendance) ; éteint hors serveur
    futur_bf = pool_mb.submit(appliquer_betfair, sports_mb, 12 if mode == "test" else HORIZON_H,
                              maintenant, journal)
    pool_mb.shutdown(wait=False)
    inconnus.vider()
    pin, poly, francais = collecter_prematch(mode, maintenant, journal, donnees, ctx.reprise)
    # Marchés français qu'aucun traducteur ne reconnaît (couverture, libellés changés) : page Santé
    releve = inconnus.vider()
    journal["marches_inconnus"] = {b: sum(v.values()) for b, v in releve.items()}
    ecrire_json(donnees / "marches_inconnus.json",
                inconnus.fusionner(lire_json(donnees / "marches_inconnus.json", {}), releve, maintenant))
    references = {"Pinnacle": pin, "Polymarket": poly}
    # Smarkets reste hors de `francais` : bookmaker « smarkets » n'est pas un book français.
    sports_sm = {"football"} if mode == "test" else {l["sport"] for l in francais if l.get("sport")}
    sm_lignes, sm_info = appliquer_smarkets(
        donnees, sports_sm, 12 if mode == "test" else HORIZON_H,
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
    try:
        bf_lignes = futur_bf.result()
    except Exception as e:  # noqa: BLE001 - appliquer_betfair ne lève pas ; garde-fou
        journal["betfair"] = {"mode": betfair_direct.mode(), "ok": False, "requetes": 0,
                              "erreurs": [type(e).__name__], "matchs": 0, "lignes": 0}
        bf_lignes = []
    if bf_lignes:
        # Référence sharp attendue par les stratégies (Pinnacle, Betfair, Polymarket) et le Consensus, comme
        # avant la fin du flux Orbit. Hors du contrôle de conformité des intitulés, comme les autres bourses.
        references["Betfair"] = bf_lignes
    # Dérive des sources (cotes/derive.py) : volume anormal, marchés disparus ou non reconnus, cotes figées.
    # Une anomalie marque l'étape dégradée (page Santé, journal d'incidents) et alerte ; aucun pari n'est bloqué.
    if mode == "complet":
        par_source = {"pinnacle": pin, "polymarket": poly, "smarkets": sm_lignes, "matchbook": mb_lignes}
        for l in francais:
            par_source.setdefault(l.get("bookmaker"), []).append(l)
        journal["derive"] = derive.mettre_a_jour(
            donnees, derive.mesures_du_cycle(journal["etapes"], par_source, releve), maintenant)
        for nom, textes in journal["derive"].pop("etapes", {}).items():
            if nom in journal["etapes"]:
                journal["etapes"][nom] |= {"degrade": True, "erreurs": (
                    textes + list(journal["etapes"][nom].get("erreurs") or []))[:10]}
    # Matchbook a sa table de paris (mêmes seuils que Pinnacle). Il reste hors
    # de la moyenne : le Consensus et le désaccord des tables déjà en place
    # ne changent pas, donc les stratégies figées non plus.
    hors = smarkets.hors_consensus() | matchbook_direct.hors_consensus()
    ctx.pinnacle, ctx.polymarket, ctx.francais = pin, poly, francais
    ctx.smarkets, ctx.matchbook, ctx.betfair = sm_lignes, mb_lignes, bf_lignes
    ctx.references, ctx.hors_consensus = references, hors
