"""Génère le site (une page HTML autonome, en onglets) à partir des données de la branche « donnees »."""
from __future__ import annotations

import json
import hashlib
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cotes.simulation import (REFERENCES, SIMULATIONS, STRATEGIE, TRANCHES, bilan,  # noqa: E402
                              bilan_filtres, bilan_tranches, moyennes_ecarts, paris_strategie,
                              mise_kelly, premiers_par_selection, profil_horaire, REGLES, clv_finale, segments, tranche)
from cotes.convergence import (CONVERGENCE, STRATEGIES, selections, paris_convergence,
                               valider_actuelles)  # noqa: E402
from cotes.strategies_prudentes import VARIANTES, selections_prudentes, suivis_prudents  # noqa: E402
from cotes.reglement import GAIN  # noqa: E402
from cotes.stockage import lire_archives, fusionner_paris  # noqa: E402
from cotes.strategie_chatgpt import CHATGPT, paris_chatgpt  # noqa: E402
from cotes.strategie_gemini import GEMINI, paris_gemini  # noqa: E402
from cotes.strategie_jules import JULES, paris_jules  # noqa: E402
from cotes.strategie_jules_v2 import JULES_V2, paris_jules_v2  # noqa: E402
from cotes.strategie_eden import EDEN, paris_eden  # noqa: E402
from cotes.strategie_qwen import QWEN, paris_qwen  # noqa: E402
from cotes.strategie_m3 import M3, paris_m3  # noqa: E402
from cotes.laboratoire import (DEBUT_ETUDE, DEBUT_SUIVI, PERIODES, REGLES as REGLES_LABO,  # noqa: E402
                              attendu_et_variance, courbe, evaluer, heure, resume, selectionner, suivi_futur)
from cotes.mises import METHODES as METHODES_MISE, comparer as comparer_mises  # noqa: E402
from cotes.securite import json_public
from cotes import notifications as notifications_mod  # noqa: E402
from cotes import ordres as ordres_mod  # noqa: E402


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


CHAMPS_PRISE = ("id", "domicile", "exterieur", "sport", "bookmaker", "pari", "cote", "reference", "ecart", "detecte",
                "debut", "statut", "gain", "collecte_recue", "collecte_debut", "prix_revu", "prix_revu_le",
                "alerte_demande_le", "lien", "lien_repli")


def prise_strategie(p: dict) -> dict:
    """Une prise des listes de stratégies (Eden, Gemini, JULES, M3) ; lien du match tant qu'il est en cours."""
    f = {k: p.get(k) for k in CHAMPS_PRISE}
    if p.get("statut") != "en_cours":
        f["lien"] = f["lien_repli"] = None
    return f


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


def paris_en_mise_kelly(paris: list[dict]) -> list[dict]:
    """Copies des paris misés en Kelly ¼ : mise propre, gain réglé proportionnel (le gain suit la mise).

    Les copies servent aux mêmes calculs que les paris d'origine ; rien n'est écrit dans les données."""
    out = []
    for p in paris:
        k = mise_kelly(p) or 1.0
        q = {**p, "mise": k}
        if p.get("gain") is not None and p.get("mise"):
            q["gain"] = round(p["gain"] * k / p["mise"], 2)
        out.append(q)
    return out


def catalogue_paris(paris: list[dict], retenus: dict[str, set[int]], regles: dict[str, set[int]] | None = None) -> dict:
    """Toutes les prises, en colonnes compactes ; le navigateur ne rend que 50 cartes.

    Une ligne = une prise enregistrée (référence comprise), prix/date exacts.
    La CLV exportée est uniquement celle de clôture validée, comme dans le bilan.
    """
    champs = list(CHAMPS_FICHE) + ["simulation", "tranche", "strategies", "convergence", "mise", "mise_kelly", "unique_bilan", "regles"]
    regles = regles or {}
    uniques = premiers_par_selection(paris)
    convergents = paris_convergence(paris, retenus)
    rows = []
    for p in sorted(paris, key=lambda p: p.get("detecte") or "", reverse=True):
        f = fiche(p)
        f.update(simulation=p.get("simulation"), clv=clv_finale(p), tranche=tranche(p["cote"]) if p.get("cote") else None,
                 strategies=[cle for cle in retenus if id(p) in retenus[cle]], convergence=id(p) in convergents,
                 mise=p.get("mise"), mise_kelly=mise_kelly(p) or 1.0, unique_bilan=id(p) in uniques,
                 regles=[cle for cle in regles if id(p) in regles[cle]])      # règles Pinnacle/Polymarket (« Mes stratégies »)
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
    from scripts.comparer_strategies import claude_rejouee

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
        enregistrer(regle.id, historique, selectionner(futur, regle, DEBUT_SUIVI))

    # Une sélection calculée une fois, pas une fois par fiche. Les paris observés
    # hors période gardent leur place dans les plafonds journaliers des rejeux.
    historiques = {
        "Claude (rejeu)": {id(p) for p in claude_rejouee(observes)},
        "ChatGPT v1 (rejeu)": paris_chatgpt(observes, depuis=DEBUT_ETUDE),
        "Gemini Argon v1 (rejeu)": paris_gemini(observes, depuis=DEBUT_ETUDE),
        "JULES EDGE v1 (rejeu)": paris_jules(observes, depuis=DEBUT_ETUDE),
        "JULES EDGE v2 (rejeu)": paris_jules_v2(observes, depuis=DEBUT_ETUDE),
        "Eden (rejeu)": paris_eden(observes, depuis=DEBUT_ETUDE),
        "M3 (rejeu)": paris_m3(observes, depuis=DEBUT_ETUDE),
    }
    officiels = {
        "Claude (rejeu)": paris_strategie(paris),
        "ChatGPT v1 (rejeu)": paris_chatgpt(paris),
        "Gemini Argon v1 (rejeu)": paris_gemini(paris),
        "JULES EDGE v1 (rejeu)": paris_jules(paris),
        "JULES EDGE v2 (rejeu)": paris_jules_v2(paris),
        "Eden (rejeu)": paris_eden(paris),
        "M3 (rejeu)": paris_m3(paris),
    }
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


def construire(donnees: Path, sortie: Path) -> Path:
    """Site complet. Les sélections de la vue à mises fixes servent aussi à la vue Kelly (cotes/memo.py)."""
    from cotes.memo import memoriser_selections
    with memoriser_selections():
        return _construire(donnees, sortie)


def _construire(donnees: Path, sortie: Path) -> Path:
    paris = fusionner_paris(_lire(donnees / "paris.json", []), lire_archives(donnees))
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
    liste, fiches_total, valeurs = selection_paris(paris)
    def _laboratoire(paris):
        """Laboratoire des stratégies pour un jeu de paris (mises fixes ou mises Kelly)."""
        laboratoire = _lire(Path(__file__).resolve().parent.parent / "docs/comparaison-strategies.json", {})
        if laboratoire:
            # L'étude figée contient encore les règles Betfair (BET-*) : seules les règles actuelles sont gardées.
            ids_regles = {r.id for r in REGLES_LABO}
            laboratoire["resultats"] = [r for r in laboratoire.get("resultats", []) if r["regle"]["id"] in ids_regles]
            maintenant = datetime.now(timezone.utc).isoformat()
            releve_str = laboratoire.get("releve") or maintenant
            m3_ids = paris_m3(paris)
            releve_dt = heure(releve_str) or heure(maintenant)
            rapport_v2 = _lire(Path(__file__).resolve().parent.parent / "docs/strategie-jules-v2.json", {})
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
                        selectionner(suivies, r, DEBUT_SUIVI), maintenant)
            gemini_ids = paris_gemini(paris)
            jules_ids = paris_jules(paris)
            jules_v2_ids = paris_jules_v2(paris)
            eden_ids = paris_eden(paris)
            officiels = {
                "Claude (rejeu)": paris_strategie(paris),
                "ChatGPT v1 (rejeu)": paris_chatgpt(paris),
                "Gemini Argon v1 (rejeu)": gemini_ids,
                "JULES EDGE v1 (rejeu)": jules_ids,
                "JULES EDGE v2 (rejeu)": jules_v2_ids,
                "Eden (rejeu)": eden_ids,
                "M3 (rejeu)": m3_ids,
            }
            laboratoire["m3_paris"] = [prise_strategie(p) for p in sorted((p for p in paris if id(p) in m3_ids),
                                key=lambda p: p.get("detecte") or "", reverse=True)[:60]]
            laboratoire["gemini_paris"] = [prise_strategie(p) for p in sorted((p for p in paris if id(p) in gemini_ids),
                                key=lambda p: p.get("detecte") or "", reverse=True)[:60]]
            laboratoire["jules_paris"] = [prise_strategie(p) for p in sorted((p for p in paris if id(p) in jules_ids),
                                key=lambda p: p.get("detecte") or "", reverse=True)[:60]]
            laboratoire["jules_v2_paris"] = [prise_strategie(p) for p in sorted((p for p in paris if id(p) in jules_v2_ids),
                                key=lambda p: p.get("detecte") or "", reverse=True)[:60]]
            laboratoire["eden_paris"] = [prise_strategie(p) for p in sorted((p for p in paris if id(p) in eden_ids),
                                key=lambda p: p.get("detecte") or "", reverse=True)[:60]]
            officiels[CONVERGENCE["nom"]] = paris_convergence(paris)
            prudentes = selections_prudentes(paris, bases={cle: officiels[nom] for cle, _, _, nom, _ in STRATEGIES})
            officiels.update({v["nom"]: prudentes[v["cle"]] for v in VARIANTES})
            laboratoire["suivis_prudents"] = suivis_prudents(paris, maintenant)
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
            depart = heure(DEBUT_SUIVI)
            laboratoire["mises"] = {"methodes": {k: {"nom": m[0], "regle": m[1]} for k, m in METHODES_MISE.items()},
                                    "selections": {"Paris uniques": comparer_mises(
                                        [p for p in paris if id(p) in uniques_suivi and heure(p.get("detecte"))
                                         and depart <= heure(p["detecte"])])}}
            for nom, ids in officiels.items():
                debut_nom = heure(lancements.get(nom, DEBUT_SUIVI))
                laboratoire["mises"]["selections"][nom] = comparer_mises(
                    [p for p in paris if id(p) in ids and heure(p.get("detecte")) and debut_nom <= heure(p["detecte"])])
            enrichir_evenements(paris, laboratoire, maintenant)
            ids_labo = {i for r in laboratoire["futur"] for i in r["ids_recents"]}
            laboratoire["paris_recents"] = [{k: p.get(k) for k in (
                "id", "domicile", "exterieur", "bookmaker", "pari", "cote", "ecart",
                "detecte", "debut", "statut", "gain")} for p in paris if p["id"] in ids_labo]
        return laboratoire

    laboratoire = _laboratoire(paris)
    # Classement vivant : notes du jour gardées dans « donnees », progression depuis la veille et sur 7 jours.
    from cotes import historique_notes
    instant_notes = datetime.now(timezone.utc)
    notes_reperes = historique_notes.reperes(historique_notes.mettre_a_jour(
        donnees, historique_notes.notes_du_laboratoire(laboratoire), instant_notes), instant_notes)
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
    laboratoire_k = _laboratoire(paris_k)
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
    data = {"diagnostic_alertes": journal_alertes.get("cycles", [])[-5:], "notes_reperes": notes_reperes,
            "rapidite": rapidite_alertes(etat.get("historique", []), journal_alertes.get("cycles", [])),
            "notifications": {"api": notifications_mod.API, "strategies": notifications_mod.NOMS,
                              "details": notifications_mod.DETAILS,
                              "comparateurs": {**{cle: nom for cle, _, _, nom, _ in STRATEGIES},
                                               **{v["cle"]: v["nom"] for v in VARIANTES},
                                               "convergence": CONVERGENCE["nom"]}},
            "catalogue": catalogue_paris(paris, retenus, notifications_mod.selections_labo(paris)),
            "strategies_badges": {**{cle: nom for cle, _, nom, _, _ in STRATEGIES},
                                   **{v["cle"]: v["court"] for v in VARIANTES}},
            "variantes": {v["nom"]: v for v in VARIANTES},
            "convergence": CONVERGENCE, "paris": [p if p["a_regler"] else {"id":p["id"], "trace":p["trace"]} for p in liste], "fiches_total": fiches_total, "valeurs_filtres": valeurs, "etat": etat, "incidents": _lire(donnees / "sante_incidents.json", {}), "bilan": bilan(paris),
            "kelly": {"bilan": bilan(paris_k), "courbes": courbes(paris_k), "segments": segments(paris_k),
                      "bilan_tranches": {k: {c: x for c, x in b.items() if c != "evenements_detail"}
                                         for k, b in bilan_tranches(paris_k).items()},
                      **({} if segments_fusionnes else {"paris_segments": segments_k}), "filtres": bilan_filtres(paris_k),
                      "laboratoire": laboratoire_k},
            "ecarts_references": moyennes_ecarts(paris),
            "bilan_tranches": {k: {c: x for c, x in b.items() if c != "evenements_detail"} for k, b in bilan_tranches(paris).items()}, "courbes": courbes(paris), "profil_horaire": profil_horaire(paris), "filtres": bilan_filtres(paris), "segments": segments(paris),
            "paris_segments": segments_fixe, "paris_a_venir_segments": paris_a_venir_des_segments(paris),
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
            "simulations": {k: v["nom"].replace(" %", "\u00a0%").replace("≥ ", "≥\u00a0") for k, v in SIMULATIONS.items()}, "references": REFERENCES}
    # Tous les contenus sont vérifiés avant de remplacer le site existant.
    donnees_json = json_public(data)
    flux_alertes = notifications_mod.flux(actuelles, paris, retenus)
    alertes_json = json_public(flux_alertes)
    ordres_json = json_public(ordres_mod.construire(flux_alertes, actuelles))
    sortie.mkdir(parents=True, exist_ok=True)
    web = Path(__file__).resolve().parent.parent / "web"
    html = MODELE
    html = html.replace("__INTERFACE_CSS__", (web / "interface.css").read_text(encoding="utf-8"))
    html = html.replace("__LIENS_JS__", (web / "liens.js").read_text(encoding="utf-8"))
    html = html.replace("__VISUELS_JS__", (web / "visuels.js").read_text(encoding="utf-8"))
    html = html.replace("__INTERFACE_JS__", (web / "interface.js").read_text(encoding="utf-8"))
    html = html.replace("__HORAIRES_JS__", (web / "horaires.js").read_text(encoding="utf-8"))
    html = html.replace("__ANALYSES_JS__", (web / "analyses.js").read_text(encoding="utf-8"))
    html = html.replace("__ACCUEIL_JS__", (web / "accueil.js").read_text(encoding="utf-8"))
    html = html.replace("__SUIVI_JS__", (web / "suivi.js").read_text(encoding="utf-8"))
    html = html.replace("__NOTIFICATIONS_JS__", (web / "notifications.js").read_text(encoding="utf-8"))
    html = html.replace("__PUSHOVER_JS__", (web / "pushover.js").read_text(encoding="utf-8"))
    html = html.replace("__VOYANT_JS__", (web / "voyant.js").read_text(encoding="utf-8"))
    html = html.replace("__ACTUALISATION_JS__", (web / "actualisation.js").read_text(encoding="utf-8"))
    # Empreinte du contenu complet : une mise à jour du code déclenche aussi le renouvellement.
    version = hashlib.sha256(html.replace("__DONNEES__", donnees_json, 1).encode("utf-8")).hexdigest()
    html = html.replace("__VERSION_SITE__", version)
    # Les données externes ne passent jamais dans les remplacements du gabarit.
    html = html.replace("__DONNEES__", donnees_json, 1)
    # Vitrine publique, gardée à part (vitrine.html, liée nulle part) ; ses deux grands chiffres sont ceux du bilan Kelly ¼.
    vitrine = (web / "vitrine.html").read_text(encoding="utf-8")
    for ref in ("Uniques", "Toutes"):
        gain = sum(b["gains"] for k, b in data["kelly"]["bilan"].items() if k.endswith("|" + ref))
        vitrine = vitrine.replace(f"__GAIN_{ref.upper()}_KELLY__", montant_vitrine(gain))
    (sortie / "index.html").write_text(html, encoding="utf-8")
    (sortie / "vitrine.html").write_text(vitrine, encoding="utf-8")
    (sortie / "polices").mkdir(exist_ok=True)
    for police in (web / "polices").glob("*.woff2"):
        (sortie / "polices" / police.name).write_bytes(police.read_bytes())
    (sortie / "version.json").write_text(json.dumps({"version": version}), encoding="utf-8")
    (sortie / "verification-responsive.html").write_text((web / "verification-responsive.html").read_text(encoding="utf-8"), encoding="utf-8")
    (sortie / "sw.js").write_text((web / "sw.js").read_text(encoding="utf-8"), encoding="utf-8")
    (sortie / "notifications.json").write_text(alertes_json, encoding="utf-8")
    (sortie / "ordres.json").write_text(ordres_json, encoding="utf-8")
    (sortie / ".nojekyll").write_text("", encoding="utf-8")
    return sortie / "index.html"


def montant_vitrine(gain: float) -> str:
    """Grand chiffre de la vitrine : euros entiers, signe à part (+ en signal), milliers espacés par la DA."""
    n = round(gain)
    signe = '<span class="s">+</span>' if n > 0 else '<span class="n">−</span>' if n < 0 else ""
    tranches = f"{abs(n):,}".split(",")
    return signe + tranches[0] + "".join(f'<span class="milliers">{t}</span>' for t in tranches[1:]) + "<sup>€</sup>"


# Gabarit de la page (HTML, CSS et JavaScript, environ 1 800 lignes) : web/modele.html, rempli par construire().
MODELE = (Path(__file__).resolve().parent.parent / "web" / "modele.html").read_text(encoding="utf-8")
