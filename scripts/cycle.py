"""Collecte et comparaison des cotes ; le règlement fonctionne aussi en cycle indépendant.

Lancé toutes les 5 minutes par GitHub Actions (.github/workflows/collecte.yml).

    python scripts/cycle.py                 # cycle complet (4 bookmakers français + Betfair, 36 h)
    python scripts/cycle.py --mode test     # cycle réduit : Winamax + Betclic, foot, 1 page
    python scripts/cycle.py --reglement oui # forcer le règlement des paris à ce cycle

Le règlement des paris (lecture des résultats : environ 6 minutes, 220 requêtes) n'a lieu qu'une fois par
heure (REGLEMENT_MINUTES, 55 par défaut) : les cotes, elles, sont lues à chaque cycle.

Données (branche « donnees ») : paris.json, etat.json, opportunites/AAAA-MM-JJ.jsonl,
resultats_manuels.json (règlements faits à la main ; « supprime » retire un pari). Site : dossier site/.
"""
from __future__ import annotations

import argparse
import gzip
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
from cotes import (comparaison, controle, pinnacle, polymarket, pulsescore, reglement,  # noqa: E402
                   simulation, smarkets, stockage)
from cotes.direct import betclic as betclic_direct  # noqa: E402
from cotes.direct import olybet as olybet_direct  # noqa: E402
from cotes.direct import pmu as pmu_direct  # noqa: E402
from cotes.direct import unibet as unibet_direct  # noqa: E402
from cotes.direct import winamax as winamax_direct  # noqa: E402
from cotes import resultats as resultats_mod  # noqa: E402
from cotes import theodds, resultats_nhl, propline  # noqa: E402
from cotes.delai import Echeance  # noqa: E402
from cotes.marches import harmoniser_pinnacle  # noqa: E402

# NetBet retiré le 6/10/2026 : le flux « netbet » de PulseScore est le site international (netbet.com :
# intitulés anglais, corners, handicaps asiatiques en quart, compétitions hors liste ANJ), pas netbet.fr.
FRANCAIS = ["winamax", "betclic", "unibet-fr", "pmu"]
SPORTS_FR = ["soccer", "basketball", "tennis", "ice-hockey", "handball", "volleyball", "rugby-union",
             "american-football", "baseball"]
SPORTS_BETFAIR = ["soccer", "tennis"]
HORIZON_H = 36
# Budgets durs : une source au-delà est sautée, le cycle de 5 min continue.
BUDGETS = {
    "pinnacle": 45,
    "polymarket": 30,
    "pulsescore": 75,
    "pmu_direct": 75,
    "winamax_direct": 45,
    "unibet_direct": 75,
    "olybet": 40,
    "betclic_direct": 45,
    "smarkets": 60,
}
PRES_H = 6
RYTHME_MIN = 20
# Les lectures lointaines ne tombent pas le même cycle : PMU toutes les 20 min,
# Unibet 27, Betclic 34. Le premier passage (aucun tampon) reste complet.
RYTHME_SOURCE = {"pmu": 20, "unibet": 27, "betclic": 34}
SMARKETS_FRAIS_MIN = 20
_journal_lock = threading.Lock()
# minutes minimum entre deux règlements (le cycle de 5 min ne lit les résultats qu'une fois par heure)
REGLEMENT_MINUTES = float(os.environ.get("REGLEMENT_MINUTES", "55"))
API ={v: k for k, v in pulsescore.SPORTS.items()}          # « football » -> « soccer »


def lire_json(chemin: Path, defaut):
    """Contenu d'un fichier de données, ou `defaut` s'il n'existe pas encore. Un fichier illisible arrête le
    cycle (erreur JSON) : le traiter comme vide écraserait, par exemple, tous les paris à la sauvegarde."""
    try:
        texte = chemin.read_text(encoding="utf-8")
    except FileNotFoundError:
        return defaut
    return json.loads(texte)


def ecrire_json(chemin: Path, donnees) -> None:
    """Écriture atomique : un cycle interrompu ne laisse jamais un fichier à moitié écrit."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    tmp = chemin.with_name(chemin.name + ".tmp")
    tmp.write_text(json.dumps(donnees, ensure_ascii=False, indent=1), encoding="utf-8")
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


def _cache_sm(chemin: Path) -> dict:
    try:
        doc = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return doc if isinstance(doc, dict) else {}


def appliquer_smarkets(donnees: Path, sports: set, heures: float, radar: list,
                       maintenant: datetime, journal: dict):
    """Relit Smarkets au plus toutes les 20 min, seulement si ``SMARKETS_COLLECTE`` est oui.

    Éteint (défaut) : zéro appel. La table des paris déjà pris reste celle de l'historique.
    Un 429 ou un budget garde le cache périmé.
    """
    if not smarkets.collecte_active():
        journal["etapes"]["smarkets"] = {"secondes": 0.0, "ok": True, "desactive": True}
        journal["smarkets_cache"] = {"reutilise": False, "perime": False, "desactive": True}
        return [], {"ok": True, "erreurs": [], "requetes": 0, "desactive": True}
    chemin = donnees / "smarkets_cache.json"
    cache = _cache_sm(chemin)
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
                            sports, heures, maintenant=maintenant, radar=radar, echeance=echeance)
    finally:
        smarkets._echeance = None
    if not isinstance(recu, tuple) or len(recu) != 2:
        lignes, info = [], {"ok": False, "erreurs": ["budget dépassé"], "perime": True, "requetes": 0}
    else:
        lignes, info = recu
    perime = bool(info.get("perime")) or any(
        e in ("budget", "HTTP 429", "budget dépassé") for e in (info.get("erreurs") or []))
    precedentes = cache.get("lignes") if isinstance(cache.get("lignes"), list) else []
    if perime and precedentes:
        lignes = list(precedentes)
    ecrire_json(chemin, {
        "lu": maintenant.isoformat(), "lignes": lignes, "perime": perime, "matchs": info.get("matchs"),
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


def signaler(journal: dict, nom: str, erreurs: list[str]) -> None:
    """Une étape qui a perdu des lectures (HTTP 500, coupure…) est marquée dégradée, pas « ok » muette :
    sinon « aucune source » pour un pari ne dit pas qu'une source était en panne."""
    if erreurs and nom in journal["etapes"]:
        journal["etapes"][nom] |= {"degrade": True, "erreurs": erreurs[:3]}


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


def collecter_prematch(cle: str | None, mode: str, maintenant: datetime, journal: dict,
                      attentes: dict | None = None, donnees: Path | None = None):
    """Pinnacle et Polymarket d'abord, puis les books indépendants en parallèle.

    PMU vient de PulseScore, de Kambi, ou des deux selon SOURCE_PMU (défaut shadow :
    PulseScore décide, Kambi n'est qu'un rapport). Une panne de l'un n'arrête pas l'autre.
    """
    limite = maintenant + timedelta(hours=HORIZON_H)

    def sports_des(lignes):
        return {l["sport"] for l in lignes if comparaison._t(l.get("debut"))
                and (maintenant - timedelta(hours=5) if l.get("debut_approximatif") else maintenant)
                    < comparaison._t(l["debut"])
                    <= limite + (timedelta(hours=5) if l.get("debut_approximatif") else timedelta())}

    def pulse(sports, nom, sans_pmu=False, sans_winamax=False, sans_unibet=False, sans_betclic=False):
        if mode == "test":
            livres = [b for b in ("winamax", "betclic")
                      if not (sans_winamax and b == "winamax") and not (sans_betclic and b == "betclic")]
            plan = {b: ["soccer"] for b in livres} | {"orbitxch": ["soccer"]}
            pages, horizon = 1, 12
        else:
            fr = [s for s in SPORTS_FR if pulsescore.SPORTS[s] in sports]
            if not fr:
                return [], {}, {}
            livres = [b for b in FRANCAIS
                      if not (sans_pmu and b == "pmu") and not (sans_winamax and b == "winamax")
                      and not (sans_unibet and b == "unibet-fr") and not (sans_betclic and b == "betclic")]
            plan = {b: fr for b in livres} | {"orbitxch": [s for s in SPORTS_BETFAIR if s in fr]}
            pages, horizon = 40, HORIZON_H
        return etape_bornee(nom, journal, BUDGETS["pulsescore"], pulsescore.collecter, cle, plan,
                            horizon, pages, etat=attentes) or ([], {}, {})

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

    source_pmu = pmu_direct.mode_source()
    journal["pmu_source"] = source_pmu
    rythme_path = donnees / "rythme_sources.json" if donnees else None
    rythme = lire_json(rythme_path, {}) if rythme_path else {}
    if not isinstance(rythme, dict):
        rythme = {}
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
        pin, poly = fpin.result() or [], fpoly.result() or []
        if pinnacle._cle_resolue:
            journal["pinnacle_configuration"] = {"mode": pinnacle.origine_cle}
        ages = [l.get("age_cache_s") for l in pin
                if isinstance(l, dict) and isinstance(l.get("age_cache_s"), int)
                and not isinstance(l.get("age_cache_s"), bool)]
        journal["pinnacle_fraicheur"] = {
            "seuil_min": pinnacle.age_max_secondes() // 60,
            "age_max_s": max(ages) if ages else None,
            "lignes_perimees": sum(1 for l in pin if isinstance(l, dict) and l.get("cote_perimee")),
            "rechauffeur": pinnacle.etat_rechauffeur,
            "rechauffeur_detail": pinnacle.resume_rechauffeur(),
            "choix_prix": dict(pinnacle.choix_prix),
        }
        signaler(journal, "pinnacle", list(pinnacle.ERREURS))
        signaler(journal, "polymarket", list(polymarket.ERREURS))
        sports = sports_des(pin + poly)
        futurs = {}

        def lancer(nom, module, budget, fonction, *args, **kwargs):
            futurs[nom] = pool.submit(source_bornee, module, nom, journal, budget,
                                      fonction, *args, **kwargs)

        if source_pmu != "pulsescore":
            heures_pmu, plein_pmu = heures_ombre("pmu", source_pmu, mode, maintenant, rythme)
            if plein_pmu:
                rythme["pmu"] = maintenant.isoformat()
            lancer("pmu_direct", pmu_direct, BUDGETS["pmu_direct"], pmu_direct.collecter,
                   sports, heures_pmu)
        source_wina = winamax_direct.mode_source()
        journal["winamax_source"] = source_wina
        if source_wina != "pulsescore":
            lancer("winamax_direct", winamax_direct, BUDGETS["winamax_direct"],
                   winamax_direct.collecter, sports, 12 if mode == "test" else HORIZON_H,
                   maintenant=maintenant)
        source_uni = unibet_direct.mode_source()
        journal["unibet_source"] = source_uni
        if source_uni != "pulsescore":
            heures_uni, plein_uni = heures_ombre("unibet", source_uni, mode, maintenant, rythme)
            if plein_uni:
                rythme["unibet"] = maintenant.isoformat()
            lancer("unibet_direct", unibet_direct, BUDGETS["unibet_direct"],
                   unibet_direct.collecter, sports, heures_uni, maintenant=maintenant,
                   concurrence=3, radar=_radar_depuis(pin) or None)
        source_bet = betclic_direct.mode_source()
        journal["betclic_source"] = source_bet
        if source_bet != "pulsescore":
            heures_bet, plein_bet = heures_ombre("betclic", source_bet, mode, maintenant, rythme)
            if plein_bet:
                rythme["betclic"] = maintenant.isoformat()
            lancer("betclic_direct", betclic_direct, BUDGETS["betclic_direct"],
                   betclic_direct.collecter, sports, heures_bet, maintenant=maintenant)
        source_oly = olybet_direct.mode_source()
        journal["olybet_source"] = source_oly
        if source_oly == "direct":
            sports_oly = sports & {"football"} if mode == "test" else sports
            lancer("olybet", olybet_direct, BUDGETS["olybet"], olybet_direct.collecter,
                   sports_oly, 12 if mode == "test" else HORIZON_H)

        recus: dict = {}

        def recevoir(nom):
            if nom in recus:
                return recus[nom]
            if nom not in futurs:
                recus[nom] = ([], {"ok": False, "erreurs": [], "requetes": 0})
                return recus[nom]
            recu = futurs[nom].result()
            if recu is None:
                recus[nom] = ([], {"ok": False, "erreurs": ["lecture interrompue"], "requetes": 0})
            else:
                recus[nom] = recu
            return recus[nom]

        # En auto le plan PulseScore dépend du résultat. Shadow et direct sont connus tout de suite.
        if source_pmu == "auto":
            direct_lignes, direct_meta = recevoir("pmu_direct")
            direct_utilisable = bool(direct_meta.get("ok") and (direct_lignes or not direct_meta.get("erreurs")))
        else:
            direct_lignes, direct_meta, direct_utilisable = [], {"ok": False, "erreurs": [], "requetes": 0}, False
        sans_pmu = source_pmu == "direct" or (source_pmu == "auto" and direct_utilisable)
        if source_wina == "auto":
            wina_lignes, wina_meta = recevoir("winamax_direct")
            wina_utilisable = bool(wina_meta.get("ok") and wina_lignes)
        else:
            wina_lignes, wina_meta, wina_utilisable = [], {"ok": False, "erreurs": [], "requetes": 0}, False
        sans_wina = source_wina == "direct" or (source_wina == "auto" and wina_utilisable)
        if source_uni == "auto":
            uni_lignes, uni_meta = recevoir("unibet_direct")
            uni_utilisable = bool(uni_meta.get("ok") and (uni_lignes or not uni_meta.get("erreurs")))
        else:
            uni_lignes, uni_meta, uni_utilisable = [], {"ok": False, "erreurs": [], "requetes": 0}, False
        sans_uni = source_uni == "direct" or (source_uni == "auto" and uni_utilisable)
        if source_bet == "auto":
            bet_lignes, bet_meta = recevoir("betclic_direct")
            bet_utilisable = bool(bet_meta.get("ok") and (bet_lignes or not bet_meta.get("erreurs")))
        else:
            bet_lignes, bet_meta, bet_utilisable = [], {"ok": False, "erreurs": [], "requetes": 0}, False
        sans_bet = source_bet == "direct" or (source_bet == "auto" and bet_utilisable)
        fpulse = pool.submit(pulse, sports, "pulsescore", sans_pmu, sans_wina, sans_uni, sans_bet) if cle else None
        if source_pmu != "auto":
            direct_lignes, direct_meta = recevoir("pmu_direct")
            direct_utilisable = bool(direct_meta.get("ok") and (direct_lignes or not direct_meta.get("erreurs")))
            sans_pmu = source_pmu == "direct" or (source_pmu == "auto" and direct_utilisable)
        if source_wina != "auto":
            wina_lignes, wina_meta = recevoir("winamax_direct")
            if wina_meta.get("ok") is False and "winamax_direct" in journal["etapes"]:
                journal["etapes"]["winamax_direct"]["ok"] = False
            wina_utilisable = bool(wina_meta.get("ok") and wina_lignes)
            sans_wina = source_wina == "direct" or (source_wina == "auto" and wina_utilisable)
        elif wina_meta.get("ok") is False and "winamax_direct" in journal["etapes"]:
            journal["etapes"]["winamax_direct"]["ok"] = False
        if source_uni != "auto":
            uni_lignes, uni_meta = recevoir("unibet_direct")
            uni_utilisable = bool(uni_meta.get("ok") and (uni_lignes or not uni_meta.get("erreurs")))
            sans_uni = source_uni == "direct" or (source_uni == "auto" and uni_utilisable)
        if source_bet != "auto":
            bet_lignes, bet_meta = recevoir("betclic_direct")
            bet_utilisable = bool(bet_meta.get("ok") and (bet_lignes or not bet_meta.get("erreurs")))
            sans_bet = source_bet == "direct" or (source_bet == "auto" and bet_utilisable)
        if source_pmu != "pulsescore":
            signaler(journal, "pmu_direct", list(direct_meta.get("erreurs") or []))
        if source_wina != "pulsescore":
            signaler(journal, "winamax_direct", list(wina_meta.get("erreurs") or []))
            if wina_meta.get("ok") is False and "winamax_direct" in journal["etapes"]:
                journal["etapes"]["winamax_direct"]["ok"] = False
        if source_uni != "pulsescore":
            signaler(journal, "unibet_direct", list(uni_meta.get("erreurs") or []))
        if source_bet != "pulsescore":
            signaler(journal, "betclic_direct", list(bet_meta.get("erreurs") or []))
        if fpulse is not None:
            lignes, requetes, erreurs = fpulse.result() or ([], {}, {})
            if erreurs and "pulsescore" in journal["etapes"]:
                journal["etapes"]["pulsescore"] |= {"degrade": True,
                    "erreurs": {b: e[:5] for b, e in erreurs.items()}}
        else:
            lignes, requetes, erreurs = [], {}, {}
            journal["etapes"]["pulsescore"] = {"ok": False, "erreur": "PULSESCORE_KEY absente"}
        if source_oly == "direct":
            oly_lignes, oly_meta = recevoir("olybet")
        else:
            oly_lignes, oly_meta = [], {"ok": False, "erreurs": [], "requetes": 0}
        pmu_ko = (not cle or journal["etapes"].get("pulsescore", {}).get("ok") is False
                  or pulsescore.indisponible(erreurs.get("pmu", []) if cle else ["PULSESCORE_KEY absente"]))
        if source_pmu == "shadow":
            try:
                journal["pmu_direct_rapport"] = pmu_direct.rapport(lignes, direct_lignes)
            except Exception as e:  # noqa: BLE001
                journal["pmu_direct_rapport"] = {"ok": False, "erreur": type(e).__name__}
            if pmu_ko and direct_utilisable:
                lignes = [l for l in lignes if l.get("bookmaker") != "pmu"] + list(direct_lignes)
                journal["pmu_repli"] = "Kambi remplace PulseScore (401/403/402/quota ou lecture impossible)"
                journal["pmu_source_effective"] = "direct"
                if "pulsescore" in journal["etapes"]:
                    journal["etapes"]["pulsescore"]["pmu_repli"] = journal["pmu_repli"]
            elif pmu_ko:
                journal["pmu_repli"] = "PulseScore indisponible, Kambi sans cote utilisable"
                journal["pmu_source_effective"] = "shadow"
        elif sans_pmu:
            lignes = [l for l in lignes if l.get("bookmaker") != "pmu"] + list(direct_lignes)
        wina_ko = (not cle or journal["etapes"].get("pulsescore", {}).get("ok") is False
                   or pulsescore.indisponible(erreurs.get("winamax", []) if cle else ["PULSESCORE_KEY absente"]))
        if source_wina == "shadow":
            try:
                journal["winamax_direct_rapport"] = winamax_direct.rapport(lignes, wina_lignes)
            except Exception as e:  # noqa: BLE001
                journal["winamax_direct_rapport"] = {"ok": False, "erreur": type(e).__name__}
            if wina_ko and wina_utilisable:
                lignes = [l for l in lignes if l.get("bookmaker") != "winamax"] + list(wina_lignes)
                journal["winamax_repli"] = "Socket Winamax remplace PulseScore (401/403/402/quota ou lecture impossible)"
                journal["winamax_source_effective"] = "direct"
                if "pulsescore" in journal["etapes"]:
                    journal["etapes"]["pulsescore"]["winamax_repli"] = journal["winamax_repli"]
            elif wina_ko:
                journal["winamax_repli"] = "PulseScore indisponible, socket Winamax sans cote utilisable"
                journal["winamax_source_effective"] = "shadow"
        elif sans_wina:
            lignes = [l for l in lignes if l.get("bookmaker") != "winamax"] + list(wina_lignes)
        uni_ko = (not cle or journal["etapes"].get("pulsescore", {}).get("ok") is False
                  or pulsescore.indisponible(erreurs.get("unibet-fr", []) if cle else ["PULSESCORE_KEY absente"]))
        if source_uni == "shadow":
            try:
                journal["unibet_direct_rapport"] = unibet_direct.rapport(lignes, uni_lignes)
            except Exception as e:  # noqa: BLE001
                journal["unibet_direct_rapport"] = {"ok": False, "erreur": type(e).__name__}
            if uni_ko and uni_utilisable:
                lignes = [l for l in lignes if l.get("bookmaker") != "unibet-fr"] + list(uni_lignes)
                journal["unibet_repli"] = "L'API Unibet remplace PulseScore (401/403/402/quota ou lecture impossible)"
                journal["unibet_source_effective"] = "direct"
                if "pulsescore" in journal["etapes"]:
                    journal["etapes"]["pulsescore"]["unibet_repli"] = journal["unibet_repli"]
            elif uni_ko:
                journal["unibet_repli"] = "PulseScore indisponible, API Unibet sans cote utilisable"
                journal["unibet_source_effective"] = "shadow"
        elif sans_uni:
            lignes = [l for l in lignes if l.get("bookmaker") != "unibet-fr"] + list(uni_lignes)
        bet_ko = (not cle or journal["etapes"].get("pulsescore", {}).get("ok") is False
                  or pulsescore.indisponible(erreurs.get("betclic", []) if cle else ["PULSESCORE_KEY absente"]))
        if source_bet == "shadow":
            try:
                journal["betclic_direct_rapport"] = betclic_direct.rapport(lignes, bet_lignes)
            except Exception as e:  # noqa: BLE001
                journal["betclic_direct_rapport"] = {"ok": False, "erreur": type(e).__name__}
            if bet_ko and bet_utilisable:
                lignes = [l for l in lignes if l.get("bookmaker") != "betclic"] + list(bet_lignes)
                journal["betclic_repli"] = "L'API Betclic remplace PulseScore (401/403/402/quota ou lecture impossible)"
                journal["betclic_source_effective"] = "direct"
                if "pulsescore" in journal["etapes"]:
                    journal["etapes"]["pulsescore"]["betclic_repli"] = journal["betclic_repli"]
            elif bet_ko:
                journal["betclic_repli"] = "PulseScore indisponible, API Betclic sans cote utilisable"
                journal["betclic_source_effective"] = "shadow"
        elif sans_bet:
            lignes = [l for l in lignes if l.get("bookmaker") != "betclic"] + list(bet_lignes)
    if source_oly == "direct":
        signaler(journal, "olybet", list(oly_meta.get("erreurs") or []))
        lignes = list(lignes) + list(oly_lignes)
        try:
            refs = list(pin) + [l for l in lignes if l.get("bookmaker") == "pmu"]
            journal["olybet_controle"] = olybet_direct.controle_prix(oly_lignes, refs)
        except Exception as e:  # noqa: BLE001
            journal["olybet_controle"] = {"ok": False, "erreur": type(e).__name__}
    mesures_delta(pin, lignes)
    if rythme_path is not None:
        ecrire_json(rythme_path, {k: rythme[k] for k in ("pmu", "unibet", "betclic") if k in rythme})
    return pin, poly, lignes, requetes


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


def effectuer_reglement(paris, donnees: Path, maintenant: datetime, cle: str,
                        journal: dict, requetes: dict, mode_reglement: str) -> bool:
    # Le règlement ne lit pas Smarkets : les cotes de l'échange ne servent pas à solder un pari.
    # 4. règlement (offre PulseScore PRO : requêtes illimitées). Sans clé PulseScore, ESPN
    #    et les résultats saisis à la main règlent quand même ce qu'ils peuvent.
    #    Environ une fois par heure, depuis le cron ou la collecte : voir REGLEMENT_MINUTES.
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
        attentes = lire_json(donnees / "pulsescore_attentes.json", {})
        client = pulsescore.Client(cle, etat=attentes) if cle else None
        for sport, depuis in resultats_mod.a_lire(paris, maintenant).items():
            # résultats validés par des bookmakers dont le flux marque les matchs terminés (cotes/resultats.py)
            for bm in (resultats_mod.VALIDATEURS if client and sport in API else []):
                n = len(client.erreurs)
                enregistrements += etape(f"resultats_{bm}_{sport}", journal, resultats_mod.lire,
                                         client, bm, API[sport], sport, depuis) or []
                signaler(journal, f"resultats_{bm}_{sport}", client.erreurs[n:])
            n = len(resultats_mod.ERREURS_ESPN)
            enregistrements += etape(f"resultats_espn_{sport}", journal, resultats_mod.lire_espn,
                                     sport, depuis, datetime.now(timezone.utc)) or []
            signaler(journal, f"resultats_espn_{sport}", resultats_mod.ERREURS_ESPN[n:])
        if client:
            ecrire_json(donnees / "pulsescore_attentes.json", attentes)
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
        if client:
            requetes["resultats"] = client.requetes
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
        journal["resultats"]["temoins_en_attente"] = sum(p.get("reference") == "Pinnacle brut" for p in attente)
        journal["resultats"]["paris_regles"] = sum(id(p) in ouverts_avant and p.get("statut") in reglement.GAIN for p in paris)
        # Même regroupement que le compteur « À régler » du site : une sélection
        # commune aux références n'est comptée qu'une fois, témoin après les vraies références.
        selections = {}
        for p in attente:
            k = tuple(p.get(c) for c in ("match_id", "marche", "periode", "ligne", "issue", "joueur"))
            selections[k] = selections.get(k, True) and p.get("reference") == "Pinnacle brut"
        journal["resultats"]["selections_en_attente"] = len(selections)
        journal["resultats"]["selections_temoins_en_attente"] = sum(selections.values())
        journal["resultats"]["ignores"] = list(resultats_mod.RESULTATS_IGNORES)
        journal["resultats"]["ignores_limite"] = resultats_mod.IGNORES_MAX
        journal["resultats"]["paris_avec_alertes"] = sum(bool(p.get("alertes")) for p in paris
                                                         if p.get("statut") in ("en_cours", "a_regler"))
    else:
        journal["resultats"] = {"saute": True, "dernier_reglement": dernier_reglement}

    return regler


def main() -> int:
    a = argparse.ArgumentParser()
    a.add_argument("--mode", choices=["complet", "test"], default=os.environ.get("MODE_COLLECTE", "complet"))
    a.add_argument("--donnees", default="donnees")
    a.add_argument("--site", default="site")
    a.add_argument("--sans-site", action="store_true",
                   help="Sauvegarder la collecte avant le chemin rapide d'alertes ; site construit ensuite")
    a.add_argument("--reglement", choices=["auto", "oui", "non"], default=os.environ.get("REGLEMENT", "auto"),
                   help="auto = si le dernier règlement date d'au moins REGLEMENT_MINUTES")
    a.add_argument("--seulement-reglement", action="store_true",
                   help="Régler les paris sans interroger les cotes ni créer de nouveaux paris")
    args = a.parse_args()
    cle = os.environ.get("PULSESCORE_KEY", "").strip()
    donnees = Path(args.donnees)
    maintenant = datetime.now(timezone.utc)
    journal = {"debut": maintenant.isoformat(timespec="seconds"), "mode": args.mode, "etapes": {}}

    if args.seulement_reglement:
        # Cycle indépendant : aucune collecte ni placement de paris.
        paris = lire_json(donnees / "paris.json", [])
        manuels = lire_json(donnees / "resultats_manuels.json", {})
        paris = [p for p in paris if manuels.get(p["id"]) != "supprime"]
        requetes = {}
        journal["mode"] = "reglement"
        regler = effectuer_reglement(paris, donnees, maintenant, cle, journal, requetes, args.reglement)
        paris = stockage.archiver(donnees, paris, maintenant)
        ecrire_json(donnees / "paris.json", paris)
        etat = lire_json(donnees / "etat.json", {})
        compteur = etat.get("requetes_par_mois", {})
        mois = f"{maintenant:%Y-%m}"
        compteur[mois] = compteur.get(mois, 0) + sum(requetes.values())
        etat["requetes_par_mois"] = compteur
        journal["fin"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        conserver_journal_reglement(etat, journal, regler)
        ecrire_json(donnees / "etat.json", etat)
        from site_web import construire
        construire(donnees, Path(args.site))
        print(json.dumps({"mode": "reglement", "resultats": journal.get("resultats"), "theodds": journal.get("theodds"),
                          "etapes": journal.get("etapes", {})}, ensure_ascii=False))
        return 0

    # Rafale live isolée AVANT les sources lentes. Les mesures +15/+30 s se font
    # pendant les lectures pré-match, sans changer leur sélection ni les bilans.
    terminer_live = None
    journal["live_papier"] = {"mode": "papier", "actif": False,
        "raison": "désactivé par défaut : fraîcheur source et clôtures complètes requises"}
    if cle and os.environ.get("LIVE_PAPIER") == "oui" and args.mode == "complet":
        try:
            from cotes.live_papier import lancer
            terminer_live = lancer(donnees, cle)
        except Exception:  # un échec live ne bloque jamais le scanner pré-match
            journal["live_papier"] = {"erreur": "initialisation_indisponible", "mode": "papier"}

    # Références en parallèle, puis les bookmakers. PMU direct ne remplace PulseScore
    # qu'en mode direct, ou en auto quand Kambi a répondu.
    attentes = lire_json(donnees / "pulsescore_attentes.json", {})
    pin, poly, lignes_ps, requetes = collecter_prematch(
        cle, args.mode, maintenant, journal, attentes, donnees)
    ecrire_json(donnees / "pulsescore_attentes.json", attentes)
    if "pmu_direct_rapport" in journal:
        ecrire_json(donnees / "pmu_comparaison.json", journal["pmu_direct_rapport"])
    if "winamax_direct_rapport" in journal:
        ecrire_json(donnees / "winamax_comparaison.json", journal["winamax_direct_rapport"])
    if "unibet_direct_rapport" in journal:
        ecrire_json(donnees / "unibet_comparaison.json", journal["unibet_direct_rapport"])
    if "betclic_direct_rapport" in journal:
        ecrire_json(donnees / "betclic_comparaison.json", journal["betclic_direct_rapport"])

    francais = [l for l in lignes_ps if l["bookmaker"] != "orbitxch"]
    betfair = comparaison.reference_betfair([l for l in lignes_ps if l["bookmaker"] == "orbitxch"])
    references = {"Pinnacle": pin, "Betfair": betfair, "Polymarket": poly}
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
    # Table propre, comme Betfair. Le drapeau ne retire que le consensus partagé.
    smarkets.ajouter_table(references, sm_lignes)
    hors = smarkets.hors_consensus()

    # 3. contrôle de conformité des marchés (cumulé d'un cycle à l'autre), comparaison et paris simulés :
    #    seules les cotes dont l'intitulé est contrôlé conforme peuvent donner un pari.
    #    Le contrôle reste celui des références déjà en place : Smarkets a sa table,
    #    pas une nouvelle mesure de conformité.
    index = etape("association", journal, comparaison.indexer, francais, references) or {}
    index_controle = {n: v for n, v in index.items() if n != "Smarkets"}
    mesures = controle.mesurer(francais, index_controle)
    etat_controle = controle.mettre_a_jour(lire_json(donnees / "controle.json", {}), mesures,
                                           journal["debut"])
    suspects = controle.matchs_suspects(mesures)
    etat_controle["matchs_suspects"] = [
        {"match_id": l["match_id"], "bookmaker": l["source"], "match": f'{l["domicile"]} – {l["exterieur"]}',
         "rapport_median": suspects[l["match_id"]]}
        for l in {l["match_id"]: l for l, *_ in mesures if l["match_id"] in suspects}.values()]
    journal["controle"] = controle.resume(etat_controle) | {"mesures": len(mesures),
                                                            "matchs_suspects": len(suspects)}
    opportunites = etape("comparaison", journal, comparaison.comparer, francais, references,
                         index=index, controle=(etat_controle, suspects),
                         temoin_brut=os.environ.get("TEMOIN_PINNACLE_BRUT") == "oui",
                         hors_consensus=hors) or []
    # Écarts d'affichage, y compris quand Smarkets ne décide pas. Avant le placement :
    # le pari enregistre les trois champs.
    comparaison.annoter_ecarts(opportunites, francais,
                               {"Betfair": betfair, "Polymarket": poly, "Smarkets": sm_lignes})
    paris = lire_json(donnees / "paris.json", [])
    # paris annulés à la main (pris sur un match mal associé) : « supprime » dans resultats_manuels.json
    manuels = lire_json(donnees / "resultats_manuels.json", {})
    paris = [p for p in paris if manuels.get(p["id"]) != "supprime"]
    journal["temoin_pinnacle_brut"] = os.environ.get("TEMOIN_PINNACLE_BRUT") == "oui"
    nouveaux = simulation.placer(opportunites, paris)
    from cotes.decisions import figer_nouveaux
    figer_nouveaux(stockage.fusionner_paris(paris, stockage.lire_archives(donnees)), nouveaux)
    simulation.suivre_prix(paris, francais)
    justes = etape("cotes_cloture", journal, comparaison.cotes_justes_depuis, index,
                   hors_consensus=hors) or {}
    simulation.suivre_cloture(paris, justes)      # heure réelle : un match peut commencer pendant le cycle

    # La collecte reprend le règlement si le workflow horaire a été retardé.
    regler = effectuer_reglement(paris, donnees, maintenant, cle, journal, requetes, args.reglement)

    # 5. sauvegarde
    if terminer_live:
        try:
            journal["live_papier"] = terminer_live()
            for bm, n in journal["live_papier"].get("requetes_pulsescore", {}).items():
                requetes[bm] = requetes.get(bm, 0) + n
        except Exception:
            journal["live_papier"] = {"erreur": "suivi_indisponible", "mode": "papier"}
    paris = stockage.archiver(donnees, paris, maintenant)      # réglés depuis plus de 30 jours -> archives
    ecrire_json(donnees / "paris.json", paris)
    ecrire_json(donnees / "controle.json", etat_controle)
    ecrire_json(donnees / "opportunites_actuelles.json", sorted(opportunites, key=lambda o: -o["ecart"]))
    if opportunites:
        jour = donnees / "opportunites" / f"{maintenant:%Y-%m-%d}.jsonl.gz"
        jour.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(jour, "at", encoding="utf-8") as f:
            for o in opportunites:
                f.write(json.dumps(o, ensure_ascii=False) + "\n")
    etat = lire_json(donnees / "etat.json", {})
    mois = f"{maintenant:%Y-%m}"
    compteur = etat.get("requetes_par_mois", {})
    compteur[mois] = compteur.get(mois, 0) + sum(requetes.values())
    journal.update({
        "fin": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "requetes_pulsescore": requetes, "cotes": {"francaises": len(francais), "pinnacle": len(pin),
                                                    "betfair": len(betfair), "polymarket": len(poly),
                                                    "smarkets": len(sm_lignes)},
        "matchs_francais": len({l["match_id"] for l in francais}),
        "opportunites": sum(not o.get("suspect") for o in opportunites),
        "opportunites_suspectes": sum(bool(o.get("suspect")) for o in opportunites),
        "nouveaux_paris": len(nouveaux)})
    etat.update({"dernier_cycle": journal, "requetes_par_mois": compteur})
    conserver_journal_reglement(etat, journal, regler)
    historique = etat.get("historique", [])[-200:] + [{k: journal[k] for k in ("debut", "mode", "opportunites",
                                                                                "nouveaux_paris", "requetes_pulsescore")}]
    etat["historique"] = historique
    ecrire_json(donnees / "etat.json", etat)

    # 6. site
    if not args.sans_site:
        from site_web import construire                                 # noqa: E402
        construire(donnees, Path(args.site))
    print(json.dumps({k: journal[k] for k in ("mode", "cotes", "matchs_francais", "opportunites", "nouveaux_paris",
                                               "requetes_pulsescore", "controle", "etapes")}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
