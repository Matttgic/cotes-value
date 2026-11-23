"""Génère le site (une page HTML autonome, en onglets) à partir des données de la branche « donnees ».

Déplacé de scripts/site_web.py (E5.4), qui renvoie ce module : `from scripts.site_web import construire` et
`import site_web` donnent les mêmes fonctions."""
from __future__ import annotations

import argparse
import json
import hashlib
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]

from cotes.simulation import (REFERENCES, SIMULATIONS, STRATEGIE, TRANCHES, bilan,  # noqa: E402
                              bilan_filtres, bilan_plafond, bilan_tranches, moyennes_ecarts, paris_strategie,
                              premiers_par_selection, profil_horaire, REGLES, clv_finale, segments, tranche)
from cotes.convergence import (CONVERGENCE, STRATEGIES, selections, paris_convergence,
                               valider_actuelles)  # noqa: E402
from cotes.strategies_prudentes import VARIANTES, selections_prudentes  # noqa: E402
from cotes.strategies import registre as registre_strategies  # noqa: E402
from cotes.strategie_recommandee import FUSIONS_AUTO, RECOMMANDEE_FUSION, charger_fusions, paris_fusion  # noqa: E402
from cotes.reglement import GAIN, taux_manuel  # noqa: E402
from cotes.sources_resultats import ou_chercher  # noqa: E402
from cotes.stockage import lire_archives, fusionner_paris  # noqa: E402
from cotes.simulation import COTE_MAX_PRISE, SOURCES_MAX, cle_selection_unique, motif_hors_regle, sources_par_selection  # noqa: E402
from cotes.alertes import bankroll as bankroll_auto  # noqa: E402
from cotes.strategie_chatgpt import CHATGPT, paris_chatgpt  # noqa: E402
from cotes.strategie_gemini import GEMINI, paris_gemini  # noqa: E402
from cotes.strategie_jules import JULES, paris_jules  # noqa: E402
from cotes.strategie_jules_v2 import JULES_V2, paris_jules_v2  # noqa: E402
from cotes.strategie_eden import EDEN, paris_eden  # noqa: E402
from cotes.strategie_qwen import QWEN, paris_qwen  # noqa: E402
from cotes.strategie_m3 import M3, paris_m3  # noqa: E402
from cotes.laboratoire import (DEBUT_ETUDE, DEBUT_SUIVI, PERIODES, REGLES as REGLES_LABO,  # noqa: E402
                              attendu_et_variance, courbe, evaluer, heure, resume, selectionner, suivi_futur)
from cotes.pauses import RETIREES  # noqa: E402
from cotes.mises import (METHODES as METHODES_MISE, MODE_DEFAUT, MODES_BILAN, MODES_INTEGRES,  # noqa: E402
                         comparer as comparer_mises, mise_du_mode)
from cotes.securite import json_public
from cotes.protection import calculer, mettre_a_jour_pannes, proteger_strategies  # noqa: E402
from cotes.analyste import SEUILS as SEUILS_AVIS, alleger_avis, annoter_avis, reference_avis  # noqa: E402
from cotes import notifications as notifications_mod  # noqa: E402
from cotes import ordres as ordres_mod  # noqa: E402
from cotes import inconnus as inconnus_mod  # noqa: E402
from cotes import surebets as surebets_mod  # noqa: E402
from cotes import boosts as boosts_mod  # noqa: E402
from cotes.alertes import promos as promos_mod  # noqa: E402


# Les variantes sont des comparateurs supplémentaires, jamais des votes de base.
BADGES_COMPARATEURS = [(cle, nom) for cle, _, _, nom, _ in STRATEGIES] + [
    (v["cle"], v["nom"]) for v in VARIANTES]


def _lire(chemin: Path, defaut):
    """Fichier absent : `defaut`. Fichier illisible : erreur (une page aux bilans vides passerait pour un
    état valable)."""
    try:
        texte = chemin.read_text(encoding="utf-8")
    except FileNotFoundError:
        return defaut
    return json.loads(texte)


def _instant(texte):
    try:
        t = datetime.fromisoformat(str(texte).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _a_venir(x: dict, maintenant: datetime) -> bool:
    debut = _instant(x.get("debut"))
    return debut is None or debut > maintenant


def surebets_publies(doc: dict, maintenant: datetime) -> dict:
    """Page Boosts › Surebets : ceux du dernier relevé (matchs pas commencés), bilans sur 7 et 30 jours, 30 derniers
    épisodes (cotes/surebets.py)."""
    doc = doc if isinstance(doc, dict) else {}
    episodes = [x for x in doc.get("episodes") or [] if isinstance(x, dict) and x.get("premier")]
    return {"maj": doc.get("maj"), "actuels": [x for x in doc.get("actuels") or []
                                               if isinstance(x, dict) and _a_venir(x, maintenant)][:30],
            "bilan": {str(j): surebets_mod.bilan(episodes, maintenant, j) for j in (7, 30)},
            "episodes": sorted(episodes, key=lambda x: x["premier"], reverse=True)[:30],
            "seuil_alerte": surebets_mod.SEUIL_ALERTE}


def boosts_publies(doc: dict, maintenant: datetime, resultats: dict | None = None) -> dict:
    """Page Boosts › Cotes boostées et boosts couverts : ceux du dernier relevé (matchs pas commencés) et bilans
    (cotes/boosts.py). Bilan › Boosts : boosts « jouer » à régler à la main et ceux déjà réglés
    (``donnees/boosts_resultats.json``)."""
    doc = doc if isinstance(doc, dict) else {}
    resultats = {k: v for k, v in (resultats or {}).items() if isinstance(v, dict)}
    regles = sorted(resultats.values(), key=lambda r: r.get("debut") or "", reverse=True)
    episodes = [x for x in doc.get("episodes") or [] if isinstance(x, dict) and x.get("premier")]
    couverts = [x for x in doc.get("episodes_couverts") or [] if isinstance(x, dict) and x.get("premier")]
    return {"maj": doc.get("maj"), "actuels": [x for x in doc.get("actuels") or []
                                               if isinstance(x, dict) and _a_venir(x, maintenant)][:60],
            "bilan": {str(j): boosts_mod.bilan(episodes, maintenant, j) for j in (7, 30)},
            "couverts": [x for x in doc.get("couverts") or []
                         if isinstance(x, dict) and x.get("jambes") and _a_venir(x, maintenant)][:20],
            "bilan_couverts": {str(j): boosts_mod.bilan_couverts(couverts, maintenant, j) for j in (7, 30)},
            "episodes_couverts": sorted(couverts, key=lambda x: x["premier"], reverse=True)[:20],
            "seuil_alerte": boosts_mod.SEUIL_ALERTE,
            "a_regler": boosts_mod.boosts_a_regler(episodes, resultats, maintenant),
            "regles": regles[:100], "bilan_regles": boosts_mod.bilan_regles(resultats)}


def rapidite_alertes(historique: list[dict], cycles_alertes: list[dict]) -> dict:
    """Délais réels : envoi après la lecture du prix, et écarts entre deux relevés (cause des alertes ratées)."""
    debuts = sorted(t for t in (_instant(h.get("debut")) for h in historique) if t)
    ecarts = sorted((b - a).total_seconds() / 60 for a, b in zip(debuts, debuts[1:]))
    delais, dernieres = [], []
    for c in cycles_alertes:
        envoi = _instant(c.get("envoi_demande_le"))
        for a in c.get("alertes", []):
            lu = _instant(a.get("collecte_le") or a.get("detecte"))
            if envoi and lu:
                delais.append((envoi - lu).total_seconds())
            dernieres.append({**{k: a.get(k) for k in ("match", "pari", "bookmaker", "cote")},
                              "envoi": c.get("envoi_demande_le")})
    mediane = lambda v: sorted(v)[len(v) // 2] if v else None
    return {"releves": len(debuts), "ecart_median_min": mediane(ecarts),
            "ecarts_plus_8_min": sum(e > 8 for e in ecarts), "plus_long_trou_min": max(ecarts, default=None),
            "envoi_median_s": mediane(delais), "dernieres": dernieres[-5:][::-1]}


EN_COURS_AFFICHES = 400        # paris en cours les plus récents
REGLES_AFFICHES = 600          # paris réglés les plus récemment (+ tous ceux à régler à la main)
CHAMPS_FILTRES = {"sims": "simulation", "reference": "reference", "statut": "statut", "bookmaker": "bookmaker",
                  "sport": "sport"}


def cle_fiche(p: dict) -> tuple:
    """Un même pari pris par plusieurs simulations = une seule fiche (même clé que la page)."""
    return (p.get("reference"), p.get("match_id"), p.get("marche"), p.get("periode"), p.get("ligne"), p.get("issue"), p.get("joueur"))


CHAMPS_FICHE = ("reference", "match_id", "marche", "periode", "ligne", "issue", "domicile", "exterieur", "debut",
                "pari", "bookmaker", "cote", "cote_juste", "ecart", "statut", "gain", "clv", "detecte", "sport",
                "ligue", "regle_le", "reporte_au", "id", "joueur", "collecte_recue", "collecte_debut", "prix_revu", "prix_revu_le", "alerte_demande_le", "decide_le", "registre_version",
                "ecart_polymarket", "ecart_smarkets", "lien", "lien_repli")


def fiche(p: dict) -> dict:
    """Champs publiés d'un pari ; le lien du match seulement tant qu'il est en cours (rien à jouer après)."""
    f = {c: p.get(c) for c in CHAMPS_FICHE}
    if p.get("statut") != "en_cours":
        f["lien"] = f["lien_repli"] = None
    return f


PARIS_TZ = ZoneInfo("Europe/Paris")
PERIODES_TRACE = {"MT1": "1re mi-temps", "MT2": "2e mi-temps", "TEMPS_REG": "temps réglementaire",
                  "P1": "1re période", "P2": "2e période", "P3": "3e période", "SET1": "1er set", "SET2": "2e set",
                  "5_MANCHES": "5 manches", "JEUX": "jeux"}


def _h(s, jour: bool = False) -> str:
    try:
        t = datetime.fromisoformat(str(s).replace("Z", "+00:00")).astimezone(PARIS_TZ)
    except (TypeError, ValueError):
        return "?"
    return t.strftime("%d/%m à %H:%M" if jour else "%H:%M")


def _c(x) -> str:
    return f"{x:.2f}".replace(".", ",") if isinstance(x, (int, float)) else "—"


def _score(x) -> str:
    return f"{x[0]}-{x[1]}" if isinstance(x, (list, tuple)) and len(x) == 2 else str(x)


# Délai médian avant que le bookmaker baisse une cote « value » (docs/duree-values.md, mesuré du 30/10 au 10/11/2026).
DUREE_VALUE_MIN = {"Betclic": 14, "PMU": 65, "NetBet": 19, "Unibet": 14}
PRIX_FRAIS_S = 400          # au-delà, la CLV des paris Pinnacle est négative (docs/strategie-claude-signal.md)


def trace(p: dict) -> list[str]:
    """Le parcours d'un pari en quelques phrases : où et quand il a été repéré, contre quelle cote juste,
    la cote juste avant le match, le résultat et d'où il vient. Les paris d'avant le 7/10/2026 n'ont qu'une
    partie de ces informations."""
    out = [f"Repéré le {_h(p.get('detecte'), True)} chez {p.get('bookmaker')}"
           + (f" (« {p['libelle_bookmaker']} »)" if p.get("libelle_bookmaker") else "") + f" à {_c(p.get('cote'))}."]
    if p.get("registre_version"):
        out.append(f"Décision figée le {_h(p.get('decide_le'), True)} · registre v{p['registre_version']}.")
    messages = {"date_debut_absente_ou_invalide": "Date de début absente, invalide ou sans fuseau : règlement à vérifier.",
                "statut_reglement_inconnu": "Statut manuel inconnu : aucun gain calculé pour cette valeur."}
    out.extend(messages[a] for a in p.get("alertes", []) if a in messages)
    prise = p.get("preuve_prise") or {}
    ref = f"Cote juste {p.get('reference')} : {_c(p.get('cote_juste'))}"
    if prise.get("composantes"):
        ref += " (moyenne de " + " · ".join(f"{n} {_c(c)}" for n, c in prise["composantes"].items()) + ")"
    if p.get("match_reference"):
        ref += f", match « {p['match_reference']} »"
    if p.get("lu_reference"):
        ref += f", lue à {_h(p['lu_reference'])}"
    out.append(ref + ".")
    age = p.get("age_prix_pinnacle_s")
    if isinstance(age, (int, float)) and not isinstance(age, bool) and age >= 0:
        duree = f"{round(age)} s" if age < 120 else f"{round(age / 60)} min"
        out.append(f"Prix Pinnacle vieux de {duree} à la détection"
                   + (" : frais." if age <= PRIX_FRAIS_S else " : ancien, l'écart peut être un retard de la référence."))
    if p.get("statut") == "en_cours" and p.get("bookmaker") in DUREE_VALUE_MIN:
        out.append(f"Chez {p['bookmaker']}, une cote value baisse d'habitude après environ "
                   f"{DUREE_VALUE_MIN[p['bookmaker']]} min (médiane mesurée) : vérifier la cote avant de jouer plus tard.")
    ctl = prise.get("controle") or {}
    if ctl.get("statut") == "conforme":
        out.append(f"Intitulé contrôlé conforme ({ctl.get('n')} comparaisons).")
    if p.get("cloture_lue") and p.get("cote_juste_cloture"):
        try:
            avant = (datetime.fromisoformat(p["debut"].replace("Z", "+00:00"))
                     - datetime.fromisoformat(p["cloture_lue"].replace("Z", "+00:00"))).total_seconds() / 60
            quand = f"{round(avant)} min avant le début" if avant >= 0 else "après le début"
        except (AttributeError, ValueError):
            quand = _h(p["cloture_lue"], True)
        out.append(f"Cote juste avant le match : {_c(p['cote_juste_cloture'])} (relevée {quand}).")
    r = p.get("preuve_reglement") or {}
    if r.get("origine") == "automatique":
        txt = f"Résultat {_score(r.get('score'))}"
        per = PERIODES_TRACE.get(p.get("periode"))
        if per and (r.get("scores") or {}).get(p.get("periode")):
            txt += f", {per} {_score(r['scores'][p['periode']])}"
        out.append(txt + " · sources : " + ", ".join(r.get("sources") or []) + ".")
        if isinstance(r.get("frere"), dict):      # même match validé chez un autre bookmaker (resultats.par_freres)
            out.append(f"Score repris du même match chez {r['frere'].get('bookmaker')} (« {r['frere'].get('match')} »).")
    elif r.get("origine"):
        out.append("Réglé à la main" + (f" : {r['source']}" if r.get("source") else "") + ".")
    return out


def selection_paris(paris: list[dict], en_cours: int = EN_COURS_AFFICHES,
                    regles: int = REGLES_AFFICHES) -> tuple[list[dict], int, dict]:
    """Page légère : un même pari pris par plusieurs simulations = une fiche (celle de la première
    détection, avec la liste des simulations). Garde les `en_cours` fiches en cours les plus récentes, les
    `regles` fiches réglées le plus récemment et toutes celles à régler à la main. Renvoie (fiches de la
    plus récente à la plus ancienne, nombre total de fiches, valeurs des filtres calculées sur TOUS les
    paris)."""
    groupes: dict[tuple, list[dict]] = {}
    strategie = paris_strategie(paris)
    chatgpt = paris_chatgpt(paris)
    gemini = paris_gemini(paris)
    jules = paris_jules(paris)
    jules_v2 = paris_jules_v2(paris)
    eden = paris_eden(paris)
    for p in paris:
        groupes.setdefault(cle_fiche(p), []).append(p)
    fiches = []
    for lignes in groupes.values():
        lignes.sort(key=lambda r: r.get("detecte") or "")
        f = fiche(lignes[0])
        f["trace"] = trace(lignes[0])
        f["sims"] = sorted({r.get("simulation") for r in lignes})
        f["a_regler"] = any(r.get("statut") == "a_regler" for r in lignes)
        if f["a_regler"]:
            sites = ou_chercher(lignes[0].get("sport"), lignes[0].get("ligue"))
            if sites:
                f["trace"].append("Score à chercher sur : " + ", ".join(f"{x['nom']} ({x['url']})" for x in sites) + ".")
        f["strategie"] = any(id(r) in strategie for r in lignes)
        f["chatgpt"] = any(id(r) in chatgpt for r in lignes)
        f["gemini"] = any(id(r) in gemini for r in lignes)
        f["jules"] = any(id(r) in jules for r in lignes)
        f["jules_v2"] = any(id(r) in jules_v2 for r in lignes)
        f["eden"] = any(id(r) in eden for r in lignes)
        f["tranche"] = tranche(f["cote"]) if f.get("cote") else None
        fiches.append(f)
    recents = lambda champ: lambda f: f.get(champ) or ""      # noqa: E731
    ouverts = sorted((f for f in fiches if f["statut"] == "en_cours"), key=recents("detecte"), reverse=True)
    finis = sorted((f for f in fiches if f["statut"] not in ("en_cours", "a_regler")), key=recents("regle_le"),
                   reverse=True)
    gardees = ouverts[:en_cours] + finis[:regles] + [f for f in fiches if f["a_regler"]]
    # Les filtres ChatGPT et Gemini donnent accès à l'ensemble de leurs paris, même si les
    # simulations très volumineuses ont repoussé une fiche hors des plus récentes.
    deja = {id(f) for f in gardees}
    gardees += [f for f in fiches if (f["chatgpt"] or f["gemini"] or f["jules"] or f["jules_v2"] or f["eden"]) and id(f) not in deja]
    gardees.sort(key=recents("detecte"), reverse=True)
    valeurs = {f: sorted({str(p.get(c)) for p in paris if p.get(c) is not None}) for f, c in CHAMPS_FILTRES.items()}
    return gardees, len(fiches), valeurs


def courbes(paris: list[dict]) -> dict[str, list]:
    """Pour le graphique du gain cumulé : par vue du bilan (Uniques, chaque référence, Toutes), les paris
    réglés dans l'ordre du règlement, chacun en [minute du règlement, gain, simulation, gain attendu, variance] (la
    page fait le cumul selon les simulations choisies). Gain attendu = mise × (cote / cote juste − 1) : ce que
    le pari rapporte en moyenne si la cote juste est exacte ; la variance donne la marge du hasard autour."""
    uniques, strategie = premiers_par_selection(paris), paris_strategie(paris)
    chatgpt = paris_chatgpt(paris)
    gemini = paris_gemini(paris)
    jules = paris_jules(paris)
    jules_v2 = paris_jules_v2(paris)
    eden = paris_eden(paris)
    qwen = paris_qwen(paris)
    out: dict[str, list] = {}
    regles = [p for p in paris if p.get("statut") not in ("en_cours", "a_regler") and p.get("regle_le")]
    regles.sort(key=lambda p: (p["regle_le"], p.get("debut") or ""))
    for p in regles:
        try:
            t = int(datetime.fromisoformat(p["regle_le"].replace("Z", "+00:00")).timestamp() // 60)
        except ValueError:
            continue
        attendu = (round(p["mise"] * (p["cote"] / p["cote_juste"] - 1), 2)
                   if p.get("cote_juste") else None)
        variance = attendu_et_variance(p, p["mise"])[1]
        point = [t, round(p.get("gain") or 0, 2), p.get("simulation"), attendu,
                 round(variance) if variance >= 10 else round(variance, 2)]
        vues = ([p["reference"], "Toutes"]
                + (["Uniques"] if id(p) in uniques else [])
                + ([STRATEGIE["nom"]] if id(p) in strategie else [])
                + ([CHATGPT["nom"]] if id(p) in chatgpt else [])
                + ([GEMINI["nom"]] if id(p) in gemini else [])
                + ([JULES["nom"]] if id(p) in jules else [])
                + ([JULES_V2["nom"]] if id(p) in jules_v2 else [])
                + ([EDEN["nom"]] if id(p) in eden else [])
                + ([QWEN["nom"]] if id(p) in qwen else []))
        for v in vues:
            out.setdefault(v, []).append(point)
    return out


def paris_des_segments(paris: list[dict]) -> list[list]:
    """Les paris uniques réglés (ceux que comptent les segments), en lignes compactes pour l'onglet Segments :
    [match, pari, bookmaker, cote, cote juste, statut, gain, CLV, début, tranche, sport], du plus récent au plus
    ancien."""
    uniques = premiers_par_selection(paris)
    regles = [p for p in paris if id(p) in uniques and p.get("statut") in REGLES and p.get("cote_juste")]
    regles.sort(key=lambda p: (p.get("debut") or "", p.get("regle_le") or ""), reverse=True)
    return [[f'{p.get("domicile")} – {p.get("exterieur")}', p.get("pari"), p.get("bookmaker"), p["cote"],
             p["cote_juste"], p["statut"], p.get("gain"), clv_finale(p), p.get("debut"), tranche(p["cote"]),
             p.get("sport"), p.get("reference")] for p in regles]


def paris_a_venir_des_segments(paris: list[dict], maintenant: datetime | None = None) -> list[list]:
    """Les paris uniques pas encore commencés, aux mêmes positions que paris_des_segments pour le filtrage (bookmaker 2,
    tranche 9, sport 10) : [match, pari, bookmaker, cote, cote juste, écart, référence, CLV du moment, début,
    tranche, sport], du plus proche au plus lointain."""
    maintenant = (maintenant or datetime.now(ZoneInfo("UTC"))).isoformat()
    uniques = premiers_par_selection(paris)

    def debut(p):
        try:
            return datetime.fromisoformat(p["debut"].replace("Z", "+00:00")).isoformat()
        except (KeyError, AttributeError, ValueError):
            return ""
    venir = [p for p in paris if id(p) in uniques and p.get("statut") == "en_cours" and p.get("cote_juste")
             and debut(p) > maintenant]
    venir.sort(key=debut)
    return [[f'{p.get("domicile")} – {p.get("exterieur")}', p.get("pari"), p.get("bookmaker"), p["cote"],
             p["cote_juste"], p.get("ecart"), p.get("reference"), p.get("clv"), p.get("debut"), tranche(p["cote"]),
             p.get("sport"), p.get("reference")] for p in venir]


def enrichir_comparateurs(paris: list[dict], laboratoire: dict, maintenant: str) -> None:
    """Les nouveaux comparateurs fonctionnent aussi avec l'ancien JSON figé."""
    releve = laboratoire.get("releve") or maintenant
    observes = [p for p in paris if heure(p.get("detecte")) and heure(p["detecte"]) <= heure(releve)]
    historiques = selections(observes, depuis=DEBUT_ETUDE)
    historiques["convergence"] = paris_convergence(observes, historiques, depuis=DEBUT_ETUDE)
    historiques.update(selections_prudentes(observes, depuis=DEBUT_ETUDE, bases=historiques))
    comparateurs = laboratoire.setdefault("comparateurs", {})
    for cle, nom in BADGES_COMPARATEURS + [("convergence", CONVERGENCE["nom"])]:
        if nom in comparateurs and nom != "M3 (rejeu)":
            continue
        rows = [p for p in observes if id(p) in historiques[cle]]
        commun = [p for p in rows if heure(p.get("debut"))
                  and heure(DEBUT_ETUDE) <= heure(p["debut"]) < heure(PERIODES[-1][2])]
        # Pas d'intervalle prétendant ces paris corrélés indépendants.
        stats = {}
        for periode, debut, fin in PERIODES:
            partie = [p for p in rows if heure(debut) <= heure(p["debut"]) < heure(fin)]
            stats[periode] = resume(partie, fin if periode != "test" else releve, incertitude=False)
        comparateurs[nom] = {**stats, "ensemble": resume(commun, releve, incertitude=False)}


def paris_en_mise(paris: list[dict], mode: str) -> list[dict]:
    """Copies des paris misés dans un mode du sélecteur (cotes/mises.py, MODES_BILAN) : mise propre, gain réglé
    proportionnel (le gain suit la mise).

    Les copies servent aux mêmes calculs que les paris d'origine ; rien n'est écrit dans les données."""
    out = []
    for p in paris:
        k = mise_du_mode(mode, p)
        q = {**p, "mise": k}
        if p.get("gain") is not None and p.get("mise"):
            q["gain"] = round(p["gain"] * k / p["mise"], 2)
        out.append(q)
    return out


def paris_en_mise_kelly(paris: list[dict]) -> list[dict]:
    """Copies des paris misés en Kelly ⅛ corrigé (la mise des alertes), le mode par défaut du site."""
    return paris_en_mise(paris, "kelly")


def catalogue_paris(paris: list[dict], retenus: dict[str, set[int]], regles: dict[str, set[int]] | None = None) -> dict:
    """Toutes les prises, en colonnes compactes ; le navigateur ne rend que 50 cartes.

    Une ligne = une prise enregistrée (référence comprise), prix/date exacts.
    La CLV exportée est uniquement celle de clôture validée, comme dans le bilan.
    """
    champs = list(CHAMPS_FICHE) + ["simulation", "tranche", "strategies", "convergence", "mise", "mise_kelly", "unique_bilan", "regles",
                                    "sources"]
    regles = regles or {}
    uniques = premiers_par_selection(paris)
    sources = sources_par_selection(paris)
    convergents = paris_convergence(paris, retenus)
    rows = []
    for p in sorted(paris, key=lambda p: p.get("detecte") or "", reverse=True):
        f = fiche(p)
        f.update(simulation=p.get("simulation"), clv=clv_finale(p), tranche=tranche(p["cote"]) if p.get("cote") else None,
                 strategies=[cle for cle in retenus if id(p) in retenus[cle]], convergence=id(p) in convergents,
                 mise=p.get("mise"), mise_kelly=mise_du_mode("kelly", p), unique_bilan=id(p) in uniques,
                 regles=[cle for cle in regles if id(p) in regles[cle]],      # règles Pinnacle/Polymarket (« Mes stratégies »)
                 sources=len(sources.get(cle_selection_unique(p)) or ()) or 1)   # références qui ont repéré la cote
        rows.append([f[k] for k in champs])
    return {"champs": champs, "lignes": rows}


def navigation_strategies(paris: list[dict], laboratoire: dict, maintenant: str) -> dict:
    """Relie les lignes du laboratoire aux paris exacts, sans perdre les anciens paris.

    Les IDs historiques des règles viennent du relevé *figé* ; les sélections
    prospectives sont recalculées sur les prises, jamais sur les résultats.
    Les comparateurs historiques sont des rejeux et restent distingués de leurs
    sélections officielles. Le dictionnaire envoyé au mobile ne contient que les
    paris appartenant à au moins une stratégie, sans limitation aux 600 fiches.
    """
    from cotes.laboratoire import claude_rejouee

    index = {p["id"]: p for p in paris if p.get("id")}
    def ids(lignes):
        return list(dict.fromkeys(p["id"] for p in lignes if p.get("id") in index))

    dates = [(nom, heure(debut), heure(fin)) for nom, debut, fin in PERIODES]
    debut_historique, fin_historique = dates[0][1], dates[-1][2]
    releve = heure(laboratoire.get("releve")) or heure(maintenant)
    observes = [p for p in paris if heure(p.get("detecte")) and heure(p.get("debut"))
                and heure(p["detecte"]) <= releve]
    passe = [p for p in observes if debut_historique <= heure(p["debut"]) < fin_historique]
    passe_ids = {id(p) for p in passe}
    futur = [p for p in paris if heure(p.get("detecte"))
             and heure(DEBUT_SUIVI) <= heure(p["detecte"]) < heure(maintenant)]
    selection = {}
    toutes = set()

    def enregistrer(nom: str, historique: list[dict], futur_lignes: list[dict]):
        repartition = {"ensemble": ids(historique), "futur": ids(futur_lignes)}
        for periode, debut, fin in dates:
            repartition[periode] = ids(p for p in historique
                                      if heure(p.get("debut")) and debut <= heure(p["debut"]) < fin)
        selection[nom] = repartition
        toutes.update(id_pari for li in repartition.values() for id_pari in li)

    for resultat, regle in zip(laboratoire.get("resultats", []), REGLES_LABO):
        assert resultat["regle"]["id"] == regle.id
        historique = [index[x] for x in resultat.get("ids_selections", []) if x in index
                      and id(index[x]) in passe_ids]
        enregistrer(regle.id, historique, calculer(regle.id, lambda: selectionner(futur, regle, DEBUT_SUIVI), list))

    # Une sélection calculée une fois, pas une fois par fiche. Les paris observés
    # hors période gardent leur place dans les plafonds journaliers des rejeux.
    historiques = {
        "Claude (rejeu)": calculer("Claude (rejeu)", lambda: {id(p) for p in claude_rejouee(observes)}),
        "ChatGPT v1 (rejeu)": paris_chatgpt(observes, depuis=DEBUT_ETUDE),
        "Gemini Argon v1 (rejeu)": paris_gemini(observes, depuis=DEBUT_ETUDE),
        "JULES EDGE v1 (rejeu)": paris_jules(observes, depuis=DEBUT_ETUDE),
        "JULES EDGE v2 (rejeu)": paris_jules_v2(observes, depuis=DEBUT_ETUDE),
        "Eden (rejeu)": paris_eden(observes, depuis=DEBUT_ETUDE),
        "M3 (rejeu)": paris_m3(observes, depuis=DEBUT_ETUDE),
    }
    # sélections officielles des 7 bases, dans l'ordre du registre (cotes/strategies/registre.py)
    officiels = {s.ligne: s.selectionner(paris) for s in registre_strategies.par_famille("base")}
    cles = {nom: cle for cle, _, _, nom, _ in STRATEGIES}
    historiques[CONVERGENCE["nom"]] = paris_convergence(
        observes, {cles[nom]: ids for nom, ids in historiques.items()}, depuis=DEBUT_ETUDE)
    officiels[CONVERGENCE["nom"]] = paris_convergence(
        paris, {cles[nom]: ids for nom, ids in officiels.items()})
    bases_historiques = {cles[nom]: historiques[nom] for nom in cles}
    bases_officielles = {cles[nom]: officiels[nom] for nom in cles}
    historiques_prudents = selections_prudentes(observes, depuis=DEBUT_ETUDE, bases=bases_historiques)
    officiels_prudents = selections_prudentes(paris, bases=bases_officielles)
    for v in VARIANTES:
        historiques[v["nom"]] = historiques_prudents[v["cle"]]
        officiels[v["nom"]] = officiels_prudents[v["cle"]]
    for nom, historique_ids in historiques.items():
        if nom in laboratoire.get("comparateurs", {}):
            enregistrer(nom, [p for p in passe if id(p) in historique_ids],
                        [p for p in futur if id(p) in officiels[nom]])

    # Courbes de toutes les stratégies (règles et comparateurs), même coupure et même mise que leurs bilans, avec la
    # ligne attendue (témoin) et sa marge du hasard : laboratoire["courbes"], propre à chaque mise (fixe ou Kelly).
    courbes_strategies = {}
    for nom, repartition in selection.items():
        courbes_strategies[nom] = {}
        for periode, pids in repartition.items():
            cutoff = maintenant if periode == "futur" else (
                next((fin for n, _, fin in PERIODES if n == periode and n != "test"), None) or releve.isoformat())
            courbes_strategies[nom][periode] = courbe([index[pid] for pid in pids], cutoff)
    return {
        "selections": selection,
        "courbes": courbes_strategies,
        "paris": {pid: {**fiche(index[pid]), "simulation": index[pid].get("simulation"),
                        "sims": [index[pid].get("simulation")],
                        "tranche": tranche(index[pid]["cote"]) if index[pid].get("cote") else None,
                        "clv": clv_finale(index[pid]),
                        **{cle: id(index[pid]) in officiels[nom] for cle, nom in BADGES_COMPARATEURS},
                        "strategies": [cle for cle, nom in BADGES_COMPARATEURS if id(index[pid]) in officiels[nom]],
                        "convergence": id(index[pid]) in officiels[CONVERGENCE["nom"]],
                        "strategies_historiques": [cle for cle, nom in BADGES_COMPARATEURS if id(index[pid]) in historiques[nom]],
                        "convergence_historique": id(index[pid]) in historiques[CONVERGENCE["nom"]],
                        "trace": []}
                 for pid in sorted(toutes) if pid in index},  # ordre stable : un set de str varie d'un processus à l'autre
    }


def enrichir_evenements(paris: list[dict], laboratoire: dict, maintenant: str):
    from cotes.evenements import identites
    from cotes.laboratoire import clv
    from statistics import mean
    from collections import defaultdict
    nav = laboratoire["navigation"]
    index = {p["id"]: p for p in paris}
    dates = {nom: fin for nom, _, fin in PERIODES if nom != "test"}
    dates.update(ensemble=laboratoire.get("releve") or maintenant,
                 test=laboratoire.get("releve") or maintenant, futur=maintenant)
    liens = {periode: identites([p for p in paris if heure(p.get("detecte"))
                                and heure(p["detecte"]) < heure(cutoff)])
             for periode, cutoff in dates.items()}
    for nom, periodes in nav["selections"].items():
        for periode, pids in periodes.items():
            if periode not in dates:
                continue
            if periode == "futur":
                stats = (laboratoire.get("comparateurs_futur", {}).get(nom) or
                         next((r for r in laboratoire.get("futur", []) if r["id"] == nom), None))
            else:
                source = (laboratoire.get("comparateurs", {}).get(nom) or
                          next((r for r in laboratoire.get("resultats", []) if r["regle"]["id"] == nom), {}))
                stats = source.get(periode)
            if stats is None:
                continue
            rows = [index[pid] for pid in pids if pid in index]
            cutoff = heure(dates[periode])
            regles = [p for p in rows if p.get("statut") in GAIN and heure(p.get("regle_le"))
                      and heure(p.get("detecte")) <= heure(p["regle_le"]) < cutoff]
            cle = lambda p: liens[periode].get(id(p), ("ligne", p["id"]))
            cs = defaultdict(list)
            for p in regles:
                c = clv(p)
                if c is not None:
                    cs[cle(p)].append(c)
            stats.update(evenements=len({cle(p) for p in rows}),
                         evenements_regles=len({cle(p) for p in regles}),
                         clv_evenement=round(100*mean(mean(v) for v in cs.values()), 2) if cs else None,
                         clv_evenements_n=len(cs))


def recommandations_du_laboratoire(laboratoire: dict, paris: list[dict], donnees: Path,
                                   instant: datetime | None = None) -> dict:
    """Liste stable des recommandées (cotes/recommandations.py, état ``recommandees.json``), sur la vue à mises fixes,
    avec le résultat de chaque stratégie depuis son entrée dans la liste (et jusqu'à sa sortie pour les anciennes).
    Retire du laboratoire les blocs de travail (« _ensembles », « _fusion_rejeu ») qui ne sont pas publiés tels quels."""
    from cotes import recommandations as reco
    ensembles = laboratoire.pop("_ensembles", {}) or {}
    rejeu = laboratoire.pop("_fusion_rejeu", None)
    lignes = [{"id": s["id"], "stats": s, "ensemble": ensembles.get(s["id"], set())}
              for s in laboratoire.get("futur") or []]
    lignes += [{"id": nom, "stats": s, "ensemble": ensembles.get(nom, set())}
               for nom, s in (laboratoire.get("comparateurs_futur") or {}).items()]
    lignes += [{"id": "base:" + nom, "stats": s, "ensemble": ensembles.get("base:" + nom, set()), "base": True}
               for nom, s in (laboratoire.get("bases_futur") or {}).items()]
    maintenant = _maintenant(instant)
    mesure = reco.mesurer_preuves(lignes, paris)       # ROI et CLV Pinnacle par match, corrigées : les critères
    etat = reco.mettre_a_jour(donnees, lignes, maintenant, reviser_permis=mesure)
    par_id = {l["id"]: l for l in lignes}
    pauses_etat = evaluer_pauses(donnees, lignes, paris, maintenant, etat)

    def depuis_entree(x):
        """Résultat des paris détectés entre l'entrée (jour, Paris) et la sortie (exclue) de la liste."""
        ids = par_id.get(x["id"], {}).get("ensemble") or set()
        debut = datetime.fromisoformat(x["depuis"]).replace(tzinfo=reco.PARIS)
        fin = datetime.fromisoformat(x["jusqua"]).replace(tzinfo=reco.PARIS) if x.get("jusqua") else maintenant
        rows = [p for p in paris if p.get("id") in ids and heure(p.get("detecte")) and debut <= heure(p["detecte"]) < fin]
        s = resume(rows, maintenant.isoformat(), incertitude=False)
        return {k: s.get(k) for k in ("paris", "regles", "attente", "gain", "roi", "clv", "evenements_regles")}

    return {"actuelles": [{**x, "depuis_entree": depuis_entree(x)} for x in etat["actuelles"]],
            "anciennes": [{**x, "pendant": depuis_entree(x)} for x in etat["anciennes"]][::-1],
            "derniere_revision": etat["derniere_revision"], "prochaine_revision": etat["prochaine_revision"],
            "criteres": {"version": reco.CRITERES, "min_matchs": reco.MIN_MATCHS, "min_clv": reco.MIN_CLV,
                         "part_pinnacle_min": reco.PART_PINNACLE_MIN, "alpha": reco.ALPHA,
                         "recouvrement_max": reco.RECOUVREMENT_MAX, "maximum": reco.MAXIMUM,
                         "revision_jours": reco.REVISION_JOURS, "ecart_remplacement": reco.ECART_REMPLACEMENT},
            "fusion_rejeu": rejeu, "doublons": reco.doublons(lignes), "pauses": pauses_etat}


def evaluer_pauses(donnees: Path, lignes: list[dict], paris: list[dict], maintenant: datetime, etat_reco: dict) -> dict:
    """Pauses automatiques (cotes/pauses.py) : nouvelles pauses écrites dans ``pauses.json``, actives à la prochaine
    construction. Exemptées : bases, stratégies de base, convergence et membres des fusions actives."""
    from cotes import pauses
    from cotes.laboratoire import clv, regles_avant
    cle_de = {r.id: "labo:" + r.id for r in REGLES_LABO}
    cle_de.update({v["nom"]: v["cle"] for v in VARIANTES})
    base = {nom for _, _, _, nom, _ in STRATEGIES} | {CONVERGENCE["nom"]}
    membres = {m for f in [RECOMMANDEE_FUSION, *FUSIONS_AUTO] if f.get("actif", True) for m in f.get("membres") or ()}
    membres |= {m for f in etat_reco.get("fusions") or [] for m in f.get("membres") or ()}
    exemptes = base | membres | {l["id"] for l in lignes if l.get("base")}
    par_id = {p["id"]: p for p in paris if p.get("id")}

    def clvs_de(ident):
        rows = [par_id[i] for i in next((l["ensemble"] for l in lignes if l["id"] == ident), ()) if i in par_id]
        return [c for c in (clv(p) for p in regles_avant(rows, maintenant)) if c is not None]
    return pauses.mettre_a_jour(donnees, lignes, cle_de, clvs_de, exemptes, maintenant)


def suivi_protocole(paris: list[dict], donnees: Path, echecs: dict | None = None,
                    instant: datetime | None = None) -> dict:
    """Protocole de validation (cotes/protocole.py, docs/protocole.md) : état de chaque stratégie, à mises fixes.
    Les empreintes des règles sont recalculées sur le jeu témoin, dans un mémo à part (mêmes identifiants que les
    vrais paris, contenu différent). Une stratégie en erreur à cette construction (``echecs``, cotes/protection.py)
    garde son état précédent ; en erreur sur le témoin seulement, son empreinte n'est pas vérifiée cette fois."""
    from cotes import protocole
    from cotes.memo import memoriser_selections
    echecs = echecs if echecs is not None else {}
    en_erreur = set(echecs)
    with memoriser_selections():
        actuelles = protocole.empreintes_actuelles()
    for nom in set(echecs) - en_erreur if actuelles else ():
        actuelles.pop(nom, None)
        actuelles.pop("labo:" + nom, None)
    return protocole.suivre(paris, protocole.selections_officielles(paris), donnees, _maintenant(instant),
                            actuelles, indisponibles=en_erreur | {"labo:" + nom for nom in en_erreur})


def _maintenant(instant: datetime | None) -> datetime:
    """Heure donnée (empreinte, tests) ou heure réelle, relue à chaque appel comme avant E5.3."""
    return instant or datetime.now(timezone.utc)


def construire(donnees: Path, sortie: Path, maintenant: datetime | None = None) -> Path:
    """Site complet. Les sélections de la vue à mises fixes servent aussi à la vue Kelly (cotes/memo.py).
    Chaque stratégie est isolée (cotes/protection.py) : une erreur la vide sans arrêter le site."""
    from cotes.memo import memoriser_selections
    with memoriser_selections(), proteger_strategies(maintenant) as echecs_strategies:
        return _construire(donnees, sortie, echecs_strategies, maintenant)


def retirer_places_libres(labo: dict) -> None:
    """Les places de fusion automatique pas encore créées (Fusion 2, 3…) ne sont ni affichées ni publiées."""
    libres = {f["nom"] for f in FUSIONS_AUTO if not f["actif"]}
    for bloc in (labo.get("comparateurs"), labo.get("comparateurs_futur"), labo.get("courbes"),
                 (labo.get("mises") or {}).get("selections"), (labo.get("navigation") or {}).get("selections")):
        if isinstance(bloc, dict):
            for nom in libres:
                bloc.pop(nom, None)


def resume_hors_plafond(paris: list[dict]) -> dict:
    """Paris à cote > plafond : nombre, réglés, gain en mises fixes (hors des bilans, gardés en archive)."""
    regles = [p for p in paris if p.get("statut") not in ("en_cours", "a_regler")]
    motifs: dict[str, int] = {}
    for p in paris:
        m = motif_hors_regle(p) or "autre"
        motifs[m] = motifs.get(m, 0) + 1
    return {"plafond": COTE_MAX_PRISE, "paris": len(paris), "regles": len(regles),
            "gain": round(sum(p.get("gain") or 0 for p in regles), 2),
            "mises": round(sum(p.get("mise") or 0 for p in regles), 2),
            "motifs": dict(sorted(motifs.items(), key=lambda x: -x[1]))}


def archive_hors_plafond(paris: list[dict]) -> list[dict]:
    """Archive lisible : une ligne par pari, du plus récent au plus ancien."""
    cles = ("id", "simulation", "reference", "bookmaker", "sport", "ligue", "domicile", "exterieur", "debut", "pari",
            "cote", "cote_juste", "ecart", "mise", "statut", "gain")
    return [{k: p.get(k) for k in cles} for p in sorted(paris, key=lambda p: str(p.get("debut")), reverse=True)]


def _construire(donnees: Path, sortie: Path, echecs_strategies: dict | None = None,
                maintenant: datetime | None = None) -> Path:
    """Lecture des données, calcul des blocs, rendu des pages, écriture du site (E5.2 : quatre étapes)."""
    entrees = charger_entrees(donnees)
    blocs = calculer_blocs(entrees, donnees, echecs_strategies, maintenant)
    pages = rendre_pages(blocs, maintenant)
    return ecrire_site(sortie, pages)


def charger_entrees(donnees: Path) -> dict:
    """Paris (hors plafond à part), journal des alertes, état, opportunités actuelles et contrôle des intitulés."""
    charger_fusions(donnees)          # fusions automatiques déjà créées (recommandees.json)
    from cotes import pauses
    pauses.charger(donnees)           # stratégies en pause (pauses.json) : plus de nouveaux paris
    paris = fusionner_paris(_lire(donnees / "paris.json", []), lire_archives(donnees))
    # Paris hors règle de prise (plafond de cote du 11/11/2026, règle du 19/11/2026 : simulation.motif_hors_regle) :
    # retirés de tous les bilans du site, jamais supprimés des données ; listés dans site/hors_plafond.json (archive).
    hors_plafond = [p for p in paris if motif_hors_regle(p)]
    paris = [p for p in paris if not motif_hors_regle(p)]
    journal_alertes = _lire(donnees / "notifications_diagnostic.json", {"cycles": []})
    demandes = {a["id"]: c.get("envoi_demande_le") for c in journal_alertes.get("cycles", [])
                for a in c.get("alertes", []) if a.get("id")}
    for p in paris:
        demande = demandes.get(notifications_mod.empreinte_prix(p))
        if demande:
            p["alerte_demande_le"] = demande
    etat = _lire(donnees / "etat.json", {})
    actuelles = [o for o in _lire(donnees / "opportunites_actuelles.json", [])
                 if not o.get("suspect")]
    # version du dernier cycle (mémoire, cotes/memoire.py) si elle existe ; sinon la publication horaire
    from cotes import memoire
    ctl = memoire.lire(donnees, "controle", None, ancien_aussi=False)
    if not isinstance(ctl, dict):
        ctl = _lire(donnees / "controle.json", {})
    # seulement les groupes mesurés dans les 6 dernières heures (les anciens restent dans controle.json)
    dernier = (etat.get("dernier_cycle") or {}).get("debut") or ""
    try:
        recent = (datetime.fromisoformat(dernier) - timedelta(hours=6)).isoformat()
    except ValueError:
        recent = ""
    groupes = [{k: g.get(k) for k in ("bookmaker", "sport", "marche", "periode", "type", "n", "mediane",
                                      "part_haute", "statut", "exemples", "dispersion", "dispersion_autre_periode")} for g in ctl.get("groupes", {}).values()
               if (g.get("maj") or "") >= recent]
    controle = {"groupes": sorted(groupes, key=lambda g: (-(g["n"] or 0))), "matchs": ctl.get("matchs_suspects", [])}
    # page légère sur mobile : liste limitée aux fiches récentes ; le bilan est calculé sur tous les paris
    return {"paris": paris, "hors_plafond": hors_plafond, "journal_alertes": journal_alertes, "etat": etat,
            "actuelles": actuelles, "controle": controle,
            "surebets": _lire(donnees / "surebets.json", {}), "boosts": _lire(donnees / "boosts.json", {}),
            "boosts_resultats": _lire(donnees / "boosts_resultats.json", {}),
            "euria": _lire(donnees / "euria.json", {})}


def calculer_blocs(entrees: dict, donnees: Path, echecs_strategies: dict | None = None,
                   instant: datetime | None = None) -> dict:
    """Bilans, laboratoire (mises fixes, Kelly et autres modes), recommandées, notes, protocole, décision : le
    dictionnaire publié dans la page. Écrit aussi les états du site dans « donnees » (notes, recommandées, protocole,
    pannes des stratégies)."""
    paris, hors_plafond, journal_alertes = entrees["paris"], entrees["hors_plafond"], entrees["journal_alertes"]
    etat, actuelles, controle = entrees["etat"], entrees["actuelles"], entrees["controle"]
    liste, _, valeurs = selection_paris(paris)
    def _laboratoire(paris, complet=True):
        """Laboratoire des stratégies pour un jeu de paris (mises fixes ou autre mode de mise). ``complet`` faux :
        sans la comparaison des méthodes de mise, qui ne lit ni la mise ni le gain (identique dans tous les modes)."""
        laboratoire = _lire(RACINE / "docs/comparaison-strategies.json", {})
        if laboratoire:
            # L'étude figée contient encore les règles Betfair (BET-*) : seules les règles actuelles sont gardées.
            ids_regles = {r.id for r in REGLES_LABO}
            laboratoire["resultats"] = [r for r in laboratoire.get("resultats", []) if r["regle"]["id"] in ids_regles]
            maintenant = _maintenant(instant).isoformat()
            releve_str = laboratoire.get("releve") or maintenant
            releve_dt = heure(releve_str) or heure(maintenant)
            rapport_v2 = _lire(RACINE / "docs/strategie-jules-v2.json", {})
            v2_historique = rapport_v2.get("comparateurs", {}).get("JULES EDGE v2 reconstruite")
            if v2_historique and heure(rapport_v2.get("releve")) == releve_dt:
                laboratoire.setdefault("comparateurs", {})["JULES EDGE v2 (rejeu)"] = {
                    k: v2_historique[k] for k in ("construction", "validation", "test", "ensemble")}
            else:
                observes_v2 = [p for p in paris if heure(p.get("detecte")) and heure(p["detecte"]) <= releve_dt]
                ids_v2 = paris_jules_v2(observes_v2, depuis=DEBUT_ETUDE)
                lignes_v2 = [p for p in observes_v2 if id(p) in ids_v2]
                commun_v2 = [p for p in lignes_v2 if heure(DEBUT_ETUDE) <= heure(p["debut"]) < heure(PERIODES[-1][2])]
                laboratoire.setdefault("comparateurs", {})["JULES EDGE v2 (rejeu)"] = {
                    **evaluer(lignes_v2, releve_str), "ensemble": resume(commun_v2, releve_str, incertitude=False)}
            enrichir_comparateurs(paris, laboratoire, maintenant)
            laboratoire["navigation"] = navigation_strategies(paris, laboratoire, maintenant)
            # Hors de la navigation (identique dans les deux mises, publiée une fois) : les courbes suivent la mise.
            laboratoire["courbes"] = laboratoire["navigation"].pop("courbes")
            laboratoire["resultats"] = [{k: v for k, v in r.items() if k != "ids_selections"}
                                        for r in laboratoire.get("resultats", [])]
            laboratoire.update(debut_suivi=DEBUT_SUIVI, futur=suivi_futur(paris, DEBUT_SUIVI, maintenant))
            # Règle absente de l'étude figée (donc de la navigation) : sa courbe prospective quand même.
            manquantes = [r for r in REGLES_LABO if "futur" not in laboratoire["courbes"].get(r.id, {})]
            if manquantes:
                suivies = [p for p in paris if heure(p.get("detecte"))
                           and heure(DEBUT_SUIVI) <= heure(p["detecte"]) < heure(maintenant)]
                for r in manquantes:
                    laboratoire["courbes"].setdefault(r.id, {})["futur"] = courbe(
                        calculer(r.id, lambda: selectionner(suivies, r, DEBUT_SUIVI), list), maintenant)
            officiels = {s.ligne: s.selectionner(paris) for s in registre_strategies.par_famille("base")}
            officiels[CONVERGENCE["nom"]] = paris_convergence(paris)
            prudentes = selections_prudentes(paris, bases={cle: officiels[nom] for cle, _, _, nom, _ in STRATEGIES})
            officiels.update({v["nom"]: prudentes[v["cle"]] for v in VARIANTES})
            # Les variantes lancées après le 14/10 comptent leurs jours depuis leur propre lancement.
            lancements = {v["nom"]: max(v["debut"], DEBUT_SUIVI, key=heure) for v in VARIANTES}
            laboratoire["comparateurs_futur"] = {
                nom: resume([p for p in paris if id(p) in ids and heure(p.get("detecte"))
                             and heure(DEBUT_SUIVI) <= heure(p["detecte"]) < heure(maintenant)],
                            maintenant, incertitude=False, depuis=lancements.get(nom, DEBUT_SUIVI))
                for nom, ids in officiels.items()}
            # Méthodes de mise comparées sur les mêmes paris réglés du suivi (rien n'est appliqué).
            uniques_suivi = premiers_par_selection(paris)
            # Bases du Bilan (chaque référence, et les paris uniques), toutes tranches, sur le même suivi que les
            # stratégies : la note /100 les classe avec elles.
            debut_suivi, fin_suivi = heure(DEBUT_SUIVI), heure(maintenant)
            suivi = [p for p in paris if heure(p.get("detecte")) and debut_suivi <= heure(p["detecte"]) < fin_suivi]
            bases = {ref: [p for p in suivi if p.get("reference") == ref] for ref in REFERENCES}
            bases["Uniques"] = [p for p in suivi if id(p) in uniques_suivi]
            laboratoire["bases_futur"] = {nom: resume(rows, maintenant, incertitude=False, depuis=DEBUT_SUIVI)
                                          for nom, rows in bases.items() if rows}
            laboratoire["courbes"].update({"base:" + nom: {"futur": courbe(rows, maintenant)}
                                           for nom, rows in bases.items() if rows})
            # Paris de chaque ligne du classement (identifiants stables) : recouvrements des recommandées.
            suivies = [p for p in paris if heure(p.get("detecte"))
                       and heure(DEBUT_SUIVI) <= heure(p["detecte"]) < heure(maintenant)]
            ensembles = {r.id: {p["id"] for p in selectionner(suivies, r, DEBUT_SUIVI)} for r in REGLES_LABO}
            ensembles.update({nom: {p["id"] for p in paris if id(p) in ids and heure(p.get("detecte"))
                                    and heure(DEBUT_SUIVI) <= heure(p["detecte"]) < heure(maintenant)}
                              for nom, ids in officiels.items()})
            ensembles.update({"base:" + nom: {p["id"] for p in rows} for nom, rows in bases.items()})
            laboratoire["_ensembles"] = ensembles
            # Rejeu de la fusion depuis le 14/10 : indicatif et optimiste (membres choisis après coup).
            ids_rejeu = paris_fusion(paris, depuis=DEBUT_SUIVI)
            rejeu = [p for p in suivies if id(p) in ids_rejeu]
            laboratoire["_fusion_rejeu"] = {"stats": resume(rejeu, maintenant, incertitude=False, depuis=DEBUT_SUIVI),
                                            "courbe": courbe(rejeu, maintenant)}
            depart = heure(DEBUT_SUIVI)
            if complet:
                laboratoire["mises"] = {"methodes": {k: {"nom": m[0], "regle": m[1]} for k, m in METHODES_MISE.items()},
                                        "selections": {"Paris uniques": comparer_mises(
                                            [p for p in paris if id(p) in uniques_suivi and heure(p.get("detecte"))
                                             and depart <= heure(p["detecte"])])}}
            for nom, ids in officiels.items() if complet else ():
                debut_nom = heure(lancements.get(nom, DEBUT_SUIVI))
                laboratoire["mises"]["selections"][nom] = comparer_mises(
                    [p for p in paris if id(p) in ids and heure(p.get("detecte")) and debut_nom <= heure(p["detecte"])])
            enrichir_evenements(paris, laboratoire, maintenant)
            # Les 30 dernières prises de chaque règle ne sont pas publiées : « Les paris » de la règle les montre toutes.
            for r in laboratoire["futur"]:
                r.pop("ids_recents", None)
            # Avis d'analyste (cotes/analyste.py). La correction de Benjamini-Hochberg se calcule
            # sur toutes les lignes d'au moins 100 paris réglés, pour cette mise.
            par_id = {p["id"]: p for p in paris}
            cibles = [(bloc, ensembles.get(bloc.get("id"), ())) for bloc in laboratoire.get("futur") or []]
            cibles += [(stats, ensembles.get(nom, ()))
                       for nom, stats in (laboratoire.get("comparateurs_futur") or {}).items()
                       if isinstance(stats, dict)]
            cibles += [(stats, ensembles.get("base:" + nom, ()))
                       for nom, stats in (laboratoire.get("bases_futur") or {}).items()
                       if isinstance(stats, dict)]
            avis = annoter_avis([[par_id[i] for i in ids if i in par_id] for _, ids in cibles], maintenant)
            for (cible, _), a in zip(cibles, avis):
                cible["avis"] = alleger_avis(a)       # textes communs publiés une seule fois, ci-dessous
            laboratoire["analyste"] = {"seuils": SEUILS_AVIS, **reference_avis()}
        return laboratoire

    laboratoire = _laboratoire(paris)
    retirer_places_libres(laboratoire)
    recommandees = recommandations_du_laboratoire(laboratoire, paris, donnees, instant)
    fusion_rejeu = recommandees.pop("fusion_rejeu", None)
    doublons = recommandees.pop("doublons", [])
    pauses_publiees = recommandees.pop("pauses", {})
    # Classement vivant : notes du jour gardées dans « donnees », progression depuis la veille et sur 7 jours.
    from cotes import notation
    instant_notes = _maintenant(instant)
    notes_reperes = notation.reperes(notation.historiser(
        donnees, notation.notes_du_laboratoire(laboratoire), instant_notes), instant_notes)
    retenus = selections(paris)
    retenus.update(selections_prudentes(paris, bases=retenus))
    actuelles = valider_actuelles(actuelles, paris, retenus)
    # Une seule copie des contrats dans le catalogue. La navigation ne garde
    # ici que ses étiquettes historiques ; le client partage les mêmes fiches.
    def _alleger_navigation(labo):
        if labo.get("navigation"):
            labo["navigation"]["paris"] = {pid: {k: p.get(k) for k in
                ("strategies_historiques", "convergence_historique", "tranche", "cote", "strategies", "jules_v2", "eden")}
                for pid, p in labo["navigation"]["paris"].items()}
    _alleger_navigation(laboratoire)
    # Même historique rejoué en mise Kelly : le navigateur échange ces blocs quand on choisit « Kelly ».
    paris_k = paris_en_mise_kelly(paris)
    laboratoire_k = _laboratoire(paris_k, complet=False)
    retirer_places_libres(laboratoire_k)
    fusion_rejeu_k = laboratoire_k.pop("_fusion_rejeu", None)
    laboratoire_k.pop("_ensembles", None)
    _alleger_navigation(laboratoire_k)
    # Sous-blocs identiques dans les deux mises (navigation, méthodes de mise, étude figée… environ 0,7 Mo) :
    # publiés une seule fois. Le navigateur reprend ceux de la vue fixe (appliquerMise).
    laboratoire_k = {k: v for k, v in laboratoire_k.items() if laboratoire.get(k) != v}
    # Paris des segments : seule la colonne du gain (6) dépend de la mise. Le gain Kelly est ajouté en colonne 12 des
    # lignes fixes au lieu de republier toute la liste (environ 0,6 Mo) ; la page le remet en colonne 6 (appliquerMise).
    segments_fixe, segments_k = paris_des_segments(paris), paris_des_segments(paris_k)
    segments_fusionnes = len(segments_fixe) == len(segments_k) and all(
        f[:6] == k[:6] and f[7:] == k[7:] for f, k in zip(segments_fixe, segments_k))
    if segments_fusionnes:
        segments_fixe = [f + [k[6]] for f, k in zip(segments_fixe, segments_k)]
    # Autres modes de mise du sélecteur (Kelly ⅛, Kelly ½…) : un fichier par mode (site/mises/<mode>.json), chargé
    # par la page seulement quand on le choisit. Un mode en erreur est retiré du menu, le site continue.
    from cotes import protection
    durees_strategies = protection.durees()         # avant les modes supplémentaires, qui recalculent les mêmes
    protocole_publie = calculer("protocole", lambda: suivi_protocole(paris, donnees, echecs_strategies, instant), dict)
    # Page Décision (cotes/decision.py, web/decision.js) : ROI et CLV Pinnacle par bookmaker et par référence.
    from cotes import decision
    decision_publiee = calculer("décision", lambda: decision.construire(paris, _maintenant(instant)), dict)
    blocs_mises: dict[str, dict] = {}
    for mode in MODES_BILAN:
        if mode in MODES_INTEGRES:
            continue
        try:
            paris_m = paris_en_mise(paris, mode)
            labo_m = _laboratoire(paris_m, complet=False)
            retirer_places_libres(labo_m)
            rejeu_m = labo_m.pop("_fusion_rejeu", None)
            labo_m.pop("_ensembles", None)
            _alleger_navigation(labo_m)
            segments_m = paris_des_segments(paris_m)
            alignes = len(segments_m) == len(segments_fixe) and all(
                f[:6] == m[:6] and f[7:12] == m[7:12] for f, m in zip(segments_fixe, segments_m))
            blocs_mises[mode] = {
                "bilan": bilan(paris_m), "courbes": courbes(paris_m), "segments": segments(paris_m),
                "bilan_tranches": {k: {c: x for c, x in b.items() if c != "evenements_detail"}
                                   for k, b in bilan_tranches(paris_m).items()},
                "filtres": bilan_filtres(paris_m),
                "laboratoire": {k: v for k, v in labo_m.items() if laboratoire.get(k) != v},
                # seule la colonne du gain (6) des paris des segments dépend de la mise
                **({"gains_segments": [m[6] for m in segments_m]} if alignes else {"paris_segments": segments_m}),
                "fusion_rejeu": rejeu_m,
                "mises_paris": {p["id"]: p["mise"] for p in paris_m if p.get("id")}}
        except Exception as e:  # noqa: BLE001 - un mode de mise en erreur ne doit pas arrêter le site
            from cotes import echecs
            echecs.annoter(f"mode de mise {mode}", echecs.message_court(e))
    from cotes.props_papier import bilan as bilan_props
    from cotes.props_papier import lire as lire_props
    props_publies = bilan_props(lire_props(donnees))
    libres = {f["cle"] for f in FUSIONS_AUTO if not f["actif"]}
    data = {"diagnostic_alertes": journal_alertes.get("cycles", [])[-5:], "notes_reperes": notes_reperes,
            "modes_mise": [{"cle": mode, "nom": nom, "regle": regle, "integre": mode in MODES_INTEGRES}
                           for mode, (nom, regle, _) in MODES_BILAN.items()
                           if mode in MODES_INTEGRES or mode in blocs_mises],
            "mode_mise_defaut": MODE_DEFAUT,
            "doublons": doublons, "pauses": pauses_publiees,
            "protocole": protocole_publie, "decision": decision_publiee,
            "rapidite": rapidite_alertes(etat.get("historique", []), journal_alertes.get("cycles", [])),
            "notifications": {"api": notifications_mod.API, "strategies": {k: v for k, v in notifications_mod.NOMS.items()
                                                                           if k not in libres and k not in RETIREES},
                              "details": {**notifications_mod.DETAILS, **promos_mod.DETAILS},
                              "speciales": promos_mod.SPECIALES,
                              "comparateurs": {**{cle: nom for cle, _, _, nom, _ in STRATEGIES},
                                               **{v["cle"]: v["nom"] for v in VARIANTES},
                                               "convergence": CONVERGENCE["nom"]}},
            "catalogue": catalogue_paris(paris, retenus, notifications_mod.selections_labo(paris)),
            "strategies_badges": {**{cle: nom for cle, _, nom, _, _ in STRATEGIES},
                                   **{v["cle"]: v["court"] for v in VARIANTES}},
            "variantes": {v["nom"]: v for v in VARIANTES if v.get("actif", True)},
            "recommandees": {**recommandees,
                             "fusions": [{k: f.get(k) for k in ("n", "nom", "court", "debut", "date", "membres", "regles")}
                                         for f in FUSIONS_AUTO if f["actif"]],
                             "fusion": {**{k: RECOMMANDEE_FUSION[k] for k in
                                                            ("cle", "nom", "court", "debut", "membres", "regles")},
                                                         "rejeu": fusion_rejeu,
                                                         "rejeu_kelly": fusion_rejeu_k}},
            "convergence": CONVERGENCE, "paris": [p if p["a_regler"] else {"id":p["id"], "trace":p["trace"]} for p in liste], "valeurs_filtres": valeurs, "etat": etat, "incidents": _lire(donnees / "sante_incidents.json", {}), "bilan": bilan(paris),
            "kelly": {"bilan": bilan(paris_k), "courbes": courbes(paris_k), "segments": segments(paris_k),
                      "bilan_tranches": {k: {c: x for c, x in b.items() if c != "evenements_detail"}
                                         for k, b in bilan_tranches(paris_k).items()},
                      **({} if segments_fusionnes else {"paris_segments": segments_k}), "filtres": bilan_filtres(paris_k),
                      "laboratoire": laboratoire_k},
            "ecarts_references": moyennes_ecarts(paris),
            "bilan_tranches": {k: {c: x for c, x in b.items() if c != "evenements_detail"} for k, b in bilan_tranches(paris).items()}, "courbes": courbes(paris), "profil_horaire": profil_horaire(paris), "filtres": bilan_filtres(paris), "plafond_match": bilan_plafond(paris), "segments": segments(paris),
            "paris_segments": segments_fixe, "paris_a_venir_segments": paris_a_venir_des_segments(paris, instant),
            "bookmakers": sorted({p["bookmaker"] for p in paris if p.get("bookmaker")}), "tranches": [t[2] for t in TRANCHES], "controle": controle,
            "strategie": {"debut": STRATEGIE["debut"], "references": list(STRATEGIE["references"]),
                          "cote_max": STRATEGIE["cote_max"], "avance_max_h": STRATEGIE["avance_max_h"]},
            "chatgpt": CHATGPT,
            "gemini": GEMINI,
            "jules": JULES,
            "jules_v2": JULES_V2,
            "eden": EDEN,
            "m3": M3,
            "laboratoire": laboratoire,
            "simulations": {k: v["nom"].replace(" %", "\u00a0%").replace("≥ ", "≥\u00a0") for k, v in SIMULATIONS.items()}, "references": REFERENCES,
            "props": props_publies,
            # même match réglé avec deux scores chez deux bookmakers (resultats.incoherences_freres), page Santé
            "hors_plafond": resume_hors_plafond(hors_plafond),
            "bankroll_auto": bankroll_auto.resume(_lire(donnees / bankroll_auto.FICHIER, {}) or {}),
            "taux_manuel": taux_manuel(paris, _maintenant(instant)),
            "marches_inconnus": inconnus_mod.resume(_lire(donnees / "marches_inconnus.json", {}) or {}, _maintenant(instant)),
            "incoherences_reglement": [x for x in (_lire(donnees / "resultats_a_saisir.json", {}) or {}).get("incoherences") or []
                                       if isinstance(x, dict)][:20]}
    # Tous les contenus sont vérifiés avant de remplacer le site existant.
    # Page Santé : temps de calcul de chaque stratégie et pannes qui durent (alerte Pushover, cotes/protection.py).
    data["durees_strategies"] = durees_strategies
    data["surebets"] = surebets_publies(entrees.get("surebets"), _maintenant(instant))
    data["sources_max"] = SOURCES_MAX
    data["boosts"] = boosts_publies(entrees.get("boosts"), _maintenant(instant), entrees.get("boosts_resultats"))
    data["pannes_strategies"] = mettre_a_jour_pannes(donnees, echecs_strategies or {}, _maintenant(instant))
    if echecs_strategies:     # page Santé › « Erreurs non bloquantes » (copie en mémoire, etat.json inchangé)
        from cotes import echecs
        echecs.fusionner(etat, list(echecs_strategies.values()), _maintenant(instant))
    # Page Euria (autre dépôt, même origine) : fichier à part, hors de index.html (cotes/euria.py).
    from cotes import euria as euria_mod
    euria = euria_mod.publie(entrees.get("euria"), data["surebets"], data["boosts"], _maintenant(instant))
    euria_stats = euria_mod.stats((entrees.get("euria") or {}).get("episodes_milieux") or []
                                  if isinstance(entrees.get("euria"), dict) else [])
    return {"data": data, "actuelles": actuelles, "paris": paris, "retenus": retenus, "hors_plafond": hors_plafond,
            "blocs_mises": blocs_mises, "euria": euria, "euria_stats": euria_stats}


def rendre_pages(blocs: dict, instant: datetime | None = None) -> dict:
    """Contenu de chaque fichier du site, tout calculé avant d'écrire (le site existant n'est remplacé qu'après)."""
    data, actuelles, paris, retenus = blocs["data"], blocs["actuelles"], blocs["paris"], blocs["retenus"]
    hors_plafond, blocs_mises = blocs["hors_plafond"], blocs["blocs_mises"]
    # Blocs lourds hors de la page (donnees.json, chargé juste après l'accueil) : la page ne garde que ce que l'accueil lit.
    leger = {k: v for k, v in data.items() if k not in BLOCS_DIFFERES}
    # Noms des règles du laboratoire (« Pinnacle 12 ») pour les recommandées de l'accueil, avant donnees.json.
    leger["regles_labo"] = [[r["regle"]["id"], r["regle"]["reference"]]
                            for r in (data.get("laboratoire") or {}).get("resultats") or []
                            if isinstance(r, dict) and isinstance(r.get("regle"), dict) and "id" in r["regle"]]
    donnees_json = json_public(leger)
    differes_json = json_public({k: data[k] for k in BLOCS_DIFFERES if k in data})
    flux_alertes = notifications_mod.flux(actuelles, paris, retenus, instant)
    alertes_json = json_public(flux_alertes)
    ordres_json = json_public(ordres_mod.construire(flux_alertes, actuelles, instant))
    web = RACINE / "web"
    html = MODELE
    html = html.replace("__INTERFACE_CSS__", (web / "interface.css").read_text(encoding="utf-8"))
    html = html.replace("__LIENS_JS__", (web / "liens.js").read_text(encoding="utf-8"))
    html = html.replace("__VISUELS_JS__", (web / "visuels.js").read_text(encoding="utf-8"))
    html = html.replace("__INTERFACE_JS__", (web / "interface.js").read_text(encoding="utf-8"))
    html = html.replace("__EFFETS_JS__", (web / "effets.js").read_text(encoding="utf-8"))
    html = html.replace("__BOURSE_JS__", (web / "bourse.js").read_text(encoding="utf-8"))
    html = html.replace("__HORAIRES_JS__", (web / "horaires.js").read_text(encoding="utf-8"))
    html = html.replace("__ANALYSES_JS__", (web / "analyses.js").read_text(encoding="utf-8"))
    html = html.replace("__ACCUEIL_JS__", (web / "accueil.js").read_text(encoding="utf-8"))
    html = html.replace("__DECISION_JS__", (web / "decision.js").read_text(encoding="utf-8"))
    html = html.replace("__SUIVI_JS__", (web / "suivi.js").read_text(encoding="utf-8"))
    html = html.replace("__NOTIFICATIONS_JS__", (web / "notifications.js").read_text(encoding="utf-8"))
    html = html.replace("__JOURNAL_JS__", (web / "journal.js").read_text(encoding="utf-8"))
    html = html.replace("__PUSHOVER_JS__", (web / "pushover.js").read_text(encoding="utf-8"))
    html = html.replace("__VOYANT_JS__", (web / "voyant.js").read_text(encoding="utf-8"))
    html = html.replace("__ACTUALISATION_JS__", (web / "actualisation.js").read_text(encoding="utf-8"))
    html = html.replace("__BOOSTS_JS__", (web / "boosts.js").read_text(encoding="utf-8"))
    # Empreinte du contenu complet : une mise à jour du code déclenche aussi le renouvellement.
    version = hashlib.sha256((html.replace("__DONNEES__", donnees_json, 1) + differes_json).encode("utf-8")).hexdigest()
    html = html.replace("__VERSION_SITE__", version)
    # Les données externes ne passent jamais dans les remplacements du gabarit.
    html = html.replace("__DONNEES__", donnees_json, 1)
    # Vitrine publique, gardée à part (vitrine.html, liée nulle part) ; ses deux grands chiffres sont ceux du bilan Kelly ¼.
    vitrine = (web / "vitrine.html").read_text(encoding="utf-8")
    for ref in ("Uniques", "Toutes"):
        gain = sum(b["gains"] for k, b in data["kelly"]["bilan"].items() if k.endswith("|" + ref))
        vitrine = vitrine.replace(f"__GAIN_{ref.upper()}_KELLY__", montant_vitrine(gain))
    return {"index.html": html, "vitrine.html": vitrine, "donnees.json": differes_json,
            "hors_plafond.json": json.dumps(archive_hors_plafond(hors_plafond), ensure_ascii=False),
            "version.json": json.dumps({"version": version}),
            "mises": {mode: json_public(bloc) for mode, bloc in blocs_mises.items()},
            "sw.js": (web / "sw.js").read_text(encoding="utf-8"),
            "notifications.json": alertes_json, "ordres.json": ordres_json, ".nojekyll": "",
            "euria.json": json.dumps(blocs.get("euria") or {}, ensure_ascii=False, separators=(",", ":")),
            "euria-stats.json": json.dumps(blocs.get("euria_stats") or {}, ensure_ascii=False, separators=(",", ":"))}


DERNIER_SITE: Path | None = None        # dossier du dernier site écrit (tests : tests/outils_site.py)


def ecrire_site(sortie: Path, pages: dict) -> Path:
    """Écrit les pages rendues dans le dossier du site ; les modes de mise retirés du menu sont effacés."""
    global DERNIER_SITE
    sortie.mkdir(parents=True, exist_ok=True)
    DERNIER_SITE = sortie
    web = RACINE / "web"
    (sortie / "index.html").write_text(pages["index.html"], encoding="utf-8")
    (sortie / "vitrine.html").write_text(pages["vitrine.html"], encoding="utf-8")
    (sortie / "polices").mkdir(exist_ok=True)
    for police in (web / "polices").glob("*.woff2"):
        (sortie / "polices" / police.name).write_bytes(police.read_bytes())
    (sortie / "hors_plafond.json").write_text(pages["hors_plafond.json"], encoding="utf-8")
    (sortie / "version.json").write_text(pages["version.json"], encoding="utf-8")
    (sortie / "mises").mkdir(exist_ok=True)
    for ancien in (sortie / "mises").glob("*.json"):          # un mode retiré du menu ne reste pas publié
        ancien.unlink()
    for mode, texte in pages["mises"].items():
        (sortie / "mises" / f"{mode}.json").write_text(texte, encoding="utf-8")
    if "donnees.json" in pages:                               # blocs différés (BLOCS_DIFFERES), lus par la page
        (sortie / "donnees.json").write_text(pages["donnees.json"], encoding="utf-8")
    for nom in ("sw.js", "notifications.json", "ordres.json", ".nojekyll"):
        (sortie / nom).write_text(pages[nom], encoding="utf-8")
    if "euria.json" in pages:                                 # lu par la page Euria (cotes/euria.py)
        (sortie / "euria.json").write_text(pages["euria.json"], encoding="utf-8")
    if "euria-stats.json" in pages:                           # onglet Stats de la page Euria (cotes/euria.py)
        (sortie / "euria-stats.json").write_text(pages["euria-stats.json"], encoding="utf-8")
    return sortie / "index.html"


def montant_vitrine(gain: float) -> str:
    """Grand chiffre de la vitrine : euros entiers, signe à part (+ en signal), milliers espacés par la DA."""
    n = round(gain)
    signe = '<span class="s">+</span>' if n > 0 else '<span class="n">−</span>' if n < 0 else ""
    tranches = f"{abs(n):,}".split(",")
    return signe + tranches[0] + "".join(f'<span class="milliers">{t}</span>' for t in tranches[1:]) + "<sup>€</sup>"


# Blocs de données publiés à part dans donnees.json et chargés après l'accueil (web/modele.html › chargerDifferes).
# L'accueil n'en lit aucun : la page passe de 5,3 Mo (956 Ko gzip) à 1,7 Mo (360 Ko gzip) sur les données du 20/11/2026.
BLOCS_DIFFERES = ("laboratoire", "kelly", "paris", "paris_segments", "courbes", "bilan", "segments", "bilan_tranches")
# Premier script de la page, fixe, dans le <head> : le mode jour/nuit mémorisé, avant tout le reste. Les contrôles de
# publication (site.yml, tests) exigent exactement deux scripts : celui-ci, à l'identique, puis le script principal.
THEME_SCRIPT = 'try{const t=localStorage.getItem("cv-theme-v1");if(t==="jour"||t==="nuit")document.documentElement.dataset.theme=t==="jour"?"light":"dark";}catch{}'
# Gabarit de la page (HTML, CSS et JavaScript, environ 1 800 lignes) : web/modele.html, rempli par construire().
MODELE = (RACINE / "web" / "modele.html").read_text(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """`python -m cotes site` : construit le site depuis les données enregistrées, sans collecter (site.yml)."""
    a = argparse.ArgumentParser(prog="site", description="Construit le site depuis les données enregistrées.")
    a.add_argument("--donnees", type=Path, default=Path("donnees"))
    a.add_argument("--sortie", type=Path, default=Path("site"))
    a.add_argument("--maintenant", type=datetime.fromisoformat, default=None,
                   help="heure de la construction (ISO, avec fuseau) ; défaut : l'heure réelle")
    args = a.parse_args(argv)
    print(construire(args.donnees, args.sortie, args.maintenant))
    return 0
