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
                              bilan_tranches, moyennes_ecarts, paris_strategie,
                              premiers_par_selection, REGLES, clv_finale, segments, tranche)
from cotes.convergence import (CONVERGENCE, STRATEGIES, selections, paris_convergence,
                               valider_actuelles)  # noqa: E402
from cotes.strategies_prudentes import VARIANTES, selections_prudentes, suivis_prudents  # noqa: E402
from cotes.reglement import gain as gain_reglement, GAIN  # noqa: E402
from cotes.stockage import lire_archives, fusionner_paris  # noqa: E402
from cotes.strategie_chatgpt import CHATGPT, paris_chatgpt  # noqa: E402
from cotes.strategie_gemini import GEMINI, paris_gemini  # noqa: E402
from cotes.strategie_jules import JULES, paris_jules  # noqa: E402
from cotes.strategie_jules_v2 import JULES_V2, paris_jules_v2  # noqa: E402
from cotes.strategie_eden import EDEN, paris_eden  # noqa: E402
from cotes.strategie_m3 import M3, paris_m3  # noqa: E402
from cotes.laboratoire import (DEBUT_ETUDE, DEBUT_SUIVI, PERIODES, REGLES as REGLES_LABO,
                              evaluer, heure, resume, selectionner, suivi_futur)  # noqa: E402
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
                "ecart_polymarket", "ecart_smarkets")


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
        f = {c: lignes[0].get(c) for c in CHAMPS_FICHE}
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
    réglés dans l'ordre du règlement, chacun en [minute du règlement, gain, simulation, gain attendu] (la
    page fait le cumul selon les simulations choisies). Gain attendu = mise × (cote / cote juste − 1) : ce que
    le pari rapporte en moyenne si la cote juste est exacte."""
    uniques, strategie = premiers_par_selection(paris), paris_strategie(paris)
    chatgpt = paris_chatgpt(paris)
    gemini = paris_gemini(paris)
    jules = paris_jules(paris)
    jules_v2 = paris_jules_v2(paris)
    eden = paris_eden(paris)
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
        point = [t, round(p.get("gain") or 0, 2), p.get("simulation"), attendu]
        vues = ([p["reference"], "Toutes"]
                + (["Uniques"] if id(p) in uniques else [])
                + ([STRATEGIE["nom"]] if id(p) in strategie else [])
                + ([CHATGPT["nom"]] if id(p) in chatgpt else [])
                + ([GEMINI["nom"]] if id(p) in gemini else [])
                + ([JULES["nom"]] if id(p) in jules else [])
                + ([JULES_V2["nom"]] if id(p) in jules_v2 else [])
                + ([EDEN["nom"]] if id(p) in eden else []))
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


def courbe_comparateur(rows: list[dict], cutoff: str) -> list[list]:
    """Même mise de 10 € et même coupure de règlement que resume()."""
    connus = [p for p in rows if p.get("statut") in GAIN and heure(p.get("detecte"))
              and heure(p.get("regle_le")) and heure(p["detecte"]) <= heure(p["regle_le"]) < heure(cutoff)]
    total = 0.0
    points = []
    for p in sorted(connus, key=lambda p: (heure(p["regle_le"]), p["id"])):
        total += gain_reglement(p["statut"], 10, p["cote"])
        points.append([int(heure(p["regle_le"]).timestamp()), round(total, 2)])
    return points


def catalogue_paris(paris: list[dict], retenus: dict[str, set[int]]) -> dict:
    """Toutes les prises, en colonnes compactes ; le navigateur ne rend que 50 cartes.

    Une ligne = une prise enregistrée (référence comprise), prix/date exacts.
    La CLV exportée est uniquement celle de clôture validée, comme dans le bilan.
    """
    champs = list(CHAMPS_FICHE) + ["simulation", "tranche", "strategies", "convergence", "mise", "unique_bilan"]
    uniques = premiers_par_selection(paris)
    convergents = paris_convergence(paris, retenus)
    rows = []
    for p in sorted(paris, key=lambda p: p.get("detecte") or "", reverse=True):
        f = {k: p.get(k) for k in CHAMPS_FICHE}
        f.update(simulation=p.get("simulation"), clv=clv_finale(p), tranche=tranche(p["cote"]) if p.get("cote") else None,
                 strategies=[cle for cle in retenus if id(p) in retenus[cle]], convergence=id(p) in convergents,
                 mise=p.get("mise"), unique_bilan=id(p) in uniques)
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

    champs = CHAMPS_FICHE + ("simulation",)
    courbes_comparateurs = {}
    for nom in laboratoire.get("comparateurs", {}):
        repartition = selection.get(nom, {})
        courbes_comparateurs[nom] = {}
        for periode, pids in repartition.items():
            cutoff = maintenant if periode == "futur" else (
                next((fin for n, _, fin in PERIODES if n == periode and n != "test"), None) or releve.isoformat())
            courbes_comparateurs[nom][periode] = courbe_comparateur([index[pid] for pid in pids], cutoff)
    return {
        "selections": selection,
        "courbes": courbes_comparateurs,
        "paris": {pid: {**{k: index[pid].get(k) for k in champs},
                        "sims": [index[pid].get("simulation")],
                        "tranche": tranche(index[pid]["cote"]) if index[pid].get("cote") else None,
                        "clv": clv_finale(index[pid]),
                        **{cle: id(index[pid]) in officiels[nom] for cle, nom in BADGES_COMPARATEURS},
                        "strategies": [cle for cle, nom in BADGES_COMPARATEURS if id(index[pid]) in officiels[nom]],
                        "convergence": id(index[pid]) in officiels[CONVERGENCE["nom"]],
                        "strategies_historiques": [cle for cle, nom in BADGES_COMPARATEURS if id(index[pid]) in historiques[nom]],
                        "convergence_historique": id(index[pid]) in historiques[CONVERGENCE["nom"]],
                        "trace": []}
                 for pid in toutes if pid in index},
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
        laboratoire["resultats"] = [{k: v for k, v in r.items() if k != "ids_selections"}
                                    for r in laboratoire.get("resultats", [])]
        laboratoire.update(debut_suivi=DEBUT_SUIVI, futur=suivi_futur(paris, DEBUT_SUIVI, maintenant))
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
        laboratoire["m3_paris"] = [{k: p.get(k) for k in
            ("id", "domicile", "exterieur", "sport", "bookmaker", "pari", "cote",
             "reference", "ecart", "detecte", "debut", "statut", "gain", "collecte_recue", "collecte_debut", "prix_revu", "prix_revu_le", "alerte_demande_le")}
            for p in sorted((p for p in paris if id(p) in m3_ids),
                            key=lambda p: p.get("detecte") or "", reverse=True)[:60]]
        laboratoire["gemini_paris"] = [{k: p.get(k) for k in
            ("id", "domicile", "exterieur", "sport", "bookmaker", "pari", "cote",
             "reference", "ecart", "detecte", "debut", "statut", "gain", "collecte_recue", "collecte_debut", "prix_revu", "prix_revu_le", "alerte_demande_le")}
            for p in sorted((p for p in paris if id(p) in gemini_ids),
                            key=lambda p: p.get("detecte") or "", reverse=True)[:60]]
        laboratoire["jules_paris"] = [{k: p.get(k) for k in
            ("id", "domicile", "exterieur", "sport", "bookmaker", "pari", "cote",
             "reference", "ecart", "detecte", "debut", "statut", "gain", "collecte_recue", "collecte_debut", "prix_revu", "prix_revu_le", "alerte_demande_le")}
            for p in sorted((p for p in paris if id(p) in jules_ids),
                            key=lambda p: p.get("detecte") or "", reverse=True)[:60]]
        laboratoire["jules_v2_paris"] = [{k: p.get(k) for k in
            ("id", "domicile", "exterieur", "sport", "bookmaker", "pari", "cote",
             "reference", "ecart", "detecte", "debut", "statut", "gain", "collecte_recue", "collecte_debut", "prix_revu", "prix_revu_le", "alerte_demande_le")}
            for p in sorted((p for p in paris if id(p) in jules_v2_ids),
                            key=lambda p: p.get("detecte") or "", reverse=True)[:60]]
        laboratoire["eden_paris"] = [{k: p.get(k) for k in
            ("id", "domicile", "exterieur", "sport", "bookmaker", "pari", "cote",
             "reference", "ecart", "detecte", "debut", "statut", "gain", "collecte_recue", "collecte_debut", "prix_revu", "prix_revu_le", "alerte_demande_le")}
            for p in sorted((p for p in paris if id(p) in eden_ids),
                            key=lambda p: p.get("detecte") or "", reverse=True)[:60]]
        officiels[CONVERGENCE["nom"]] = paris_convergence(paris)
        prudentes = selections_prudentes(paris, bases={cle: officiels[nom] for cle, _, _, nom, _ in STRATEGIES})
        officiels.update({v["nom"]: prudentes[v["cle"]] for v in VARIANTES})
        laboratoire["suivis_prudents"] = suivis_prudents(paris, maintenant)
        laboratoire["comparateurs_futur"] = {
            nom: resume([p for p in paris if id(p) in ids and heure(p.get("detecte"))
                         and heure(DEBUT_SUIVI) <= heure(p["detecte"]) < heure(maintenant)],
                        maintenant, incertitude=False) for nom, ids in officiels.items()}
        enrichir_evenements(paris, laboratoire, maintenant)
        ids_labo = {i for r in laboratoire["futur"] for i in r["ids_recents"]}
        laboratoire["paris_recents"] = [{k: p.get(k) for k in (
            "id", "domicile", "exterieur", "bookmaker", "pari", "cote", "ecart",
            "detecte", "debut", "statut", "gain")} for p in paris if p["id"] in ids_labo]
    retenus = selections(paris)
    retenus.update(selections_prudentes(paris, bases=retenus))
    actuelles = valider_actuelles(actuelles, paris, retenus)
    # Une seule copie des contrats dans le catalogue. La navigation ne garde
    # ici que ses étiquettes historiques ; le client partage les mêmes fiches.
    if laboratoire.get("navigation"):
        laboratoire["navigation"]["paris"] = {pid: {k: p.get(k) for k in
            ("strategies_historiques", "convergence_historique", "tranche", "cote", "strategies", "jules_v2", "eden")}
            for pid, p in laboratoire["navigation"]["paris"].items()}
    data = {"diagnostic_alertes": journal_alertes.get("cycles", [])[-5:],
            "rapidite": rapidite_alertes(etat.get("historique", []), journal_alertes.get("cycles", [])),
            "notifications": {"api": notifications_mod.API, "strategies": notifications_mod.NOMS},
            "catalogue": catalogue_paris(paris, retenus),
            "strategies_badges": {**{cle: nom for cle, _, nom, _, _ in STRATEGIES},
                                   **{v["cle"]: v["court"] for v in VARIANTES}},
            "variantes": {v["nom"]: v for v in VARIANTES},
            "convergence": CONVERGENCE, "paris": [p if p["a_regler"] else {"id":p["id"], "trace":p["trace"]} for p in liste], "fiches_total": fiches_total, "valeurs_filtres": valeurs, "etat": etat, "bilan": bilan(paris),
            "ecarts_references": moyennes_ecarts(paris),
            "bilan_tranches": {k: {c: x for c, x in b.items() if c != "evenements_detail"} for k, b in bilan_tranches(paris).items()}, "courbes": courbes(paris), "segments": segments(paris),
            "paris_segments": paris_des_segments(paris), "paris_a_venir_segments": paris_a_venir_des_segments(paris),
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
    html = html.replace("__VISUELS_JS__", (web / "visuels.js").read_text(encoding="utf-8"))
    html = html.replace("__INTERFACE_JS__", (web / "interface.js").read_text(encoding="utf-8"))
    html = html.replace("__HORAIRES_JS__", (web / "horaires.js").read_text(encoding="utf-8"))
    html = html.replace("__ANALYSES_JS__", (web / "analyses.js").read_text(encoding="utf-8"))
    html = html.replace("__NOTIFICATIONS_JS__", (web / "notifications.js").read_text(encoding="utf-8"))
    html = html.replace("__ACTUALISATION_JS__", (web / "actualisation.js").read_text(encoding="utf-8"))
    # Empreinte du contenu complet : une mise à jour du code déclenche aussi le renouvellement.
    version = hashlib.sha256(html.replace("__DONNEES__", donnees_json, 1).encode("utf-8")).hexdigest()
    html = html.replace("__VERSION_SITE__", version)
    # Les données externes ne passent jamais dans les remplacements du gabarit.
    html = html.replace("__DONNEES__", donnees_json, 1)
    (sortie / "index.html").write_text(html, encoding="utf-8")
    (sortie / "version.json").write_text(json.dumps({"version": version}), encoding="utf-8")
    (sortie / "verification-responsive.html").write_text((web / "verification-responsive.html").read_text(encoding="utf-8"), encoding="utf-8")
    (sortie / "sw.js").write_text((web / "sw.js").read_text(encoding="utf-8"), encoding="utf-8")
    (sortie / "notifications.json").write_text(alertes_json, encoding="utf-8")
    (sortie / "ordres.json").write_text(ordres_json, encoding="utf-8")
    (sortie / ".nojekyll").write_text("", encoding="utf-8")
    return sortie / "index.html"


MODELE = r"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Cotes Value</title>
<style>__INTERFACE_CSS__</style>
</head>
<body>
<a class="evitement" href="#contenu">Aller au contenu</a>
<header class="haut">
  <div class="titre"><div class="marque"><span class="monogramme" aria-hidden="true">cv.</span><div><h1>Cotes Value</h1><label class="signature palette-label">Couleurs <select id="palette-site" aria-label="Couleurs du site"><option value="bleu">Bleu</option><option value="violet">Violet</option><option value="graphite">Graphite</option></select></label><label class="signature palette-label">Mode <select id="theme-site" aria-label="Mode jour ou nuit"><option value="auto">Auto</option><option value="nuit">Nuit</option><option value="jour">Jour</option></select></label></div></div>
    <div class="mise-a-jour"><span class="maj" id="maj"></span><span id="fraicheur" class="fraicheur"></span></div></div>
  <nav id="onglets" aria-label="Navigation principale">
    <button data-o="paris"><svg class="icone" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="4" y="3" width="16" height="18" rx="3"/><path d="M8 8h8M8 12h8M8 16h4"/></svg><span>Paris<span class="nb" id="nb-paris"></span></span></button>
    <button data-o="bilan"><svg class="icone" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 17 9 11l4 3 8-11M16 3h5v5M3 21h18"/></svg><span>Bilan</span></button>
    <button data-o="notifications"><svg class="icone" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/></svg><span>Notifs</span></button>
    <button data-o="controle"><svg class="icone" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 12h4l3-8 4 16 3-8h4"/></svg><span>Santé</span></button>
  </nav>
</header>
<main id="contenu" tabindex="-1">
  <div class="message-reseau" id="hors-ligne" role="status" hidden>Connexion indisponible. Le dernier relevé reste consultable.</div>
  <noscript><p class="vide">Active JavaScript dans Chrome pour afficher les paris et les stratégies.</p></noscript>
  <section class="onglet" id="o-bilan">
    <div class="page-tete"><div><h2>Bilan</h2></div></div>
    <div class="bilan-onglets" role="tablist" aria-label="Vue du bilan">
      <button type="button" role="tab" id="bt-uniques" data-bilan="uniques" aria-controls="bilan-uniques">Paris uniques</button>
      <button type="button" role="tab" id="bt-strategies" data-bilan="strategies" aria-controls="o-strategies">Stratégies</button>
    </div>
    <div id="bilan-uniques" role="tabpanel" aria-labelledby="bt-uniques">
      <div class="puces bu-periodes" id="bu-periodes" aria-label="Période"></div>
      <div class="bu-kpis" id="bu-kpis"></div>
      <p class="aide" id="bu-note"></p>
      <h3 class="bu-titre">Par écart de value</h3><div class="bu-table" id="bu-ecart"></div>
      <p class="aide">★ meilleur ROI parmi les lignes de 50 paris ou plus.</p>
      <h3 class="bu-titre">Par tranche de cote</h3><div class="bu-table" id="bu-cote"></div>
      <h3 class="bu-titre">Par sport</h3><div class="bu-table" id="bu-sport"></div>
      <p class="bilan-liens"><button type="button" class="btn secondaire" data-aller="analyses">Analyses et graphiques ›</button>
        <button type="button" class="btn secondaire" data-aller="segments">Segments ›</button></p>
      <details class="mode-emploi bilan-avance"><summary>Bilan détaillé : références, CLV et courbe</summary>
      <div class="puces" id="puces-ref"></div>
      <details class="mode-emploi"><summary>Comprendre cette sélection</summary><p class="aide" id="bilan-quoi"></p></details>
      <button id="voir-chatgpt" hidden>Voir les paris ChatGPT</button>
      <button id="voir-gemini" hidden>Voir les paris Gemini Argon</button>
      <button id="voir-jules" hidden>Voir les paris JULES EDGE</button>
      <button id="voir-jules-v2" hidden>Voir les paris JULES EDGE v2</button>
      <button id="voir-eden" hidden>Voir les paris Eden</button>
      <details id="bilan-evolution" class="mode-emploi"><summary>Évolution du bilan</summary><div class="courbe" id="courbe"><div class="courbe-tete"><span>Gain cumulé <span id="courbe-quoi"></span></span>
      </div><div class="legende" id="legende"></div>
      <svg id="courbe-svg" role="img" aria-label="Gain cumulé réel et attendu au fil des paris réglés"></svg>
      <div class="bulle" id="bulle"></div></div></details>
      <div class="tableau"><table id="liste-bilan"></table></div>
      <p class="aide" id="bilan-ecarts">Paris uniques réglés · écart vs Polymarket — · écart vs Smarkets —</p>
      <div class="tableau" style="margin-top:10px"><table id="bilan-clv"></table></div>
      <h2 class="sous-titre">Par tranche de cote</h2>
      <div class="tableau"><table id="bilan-tranches"></table></div>
      <details class="aide" style="margin-top:12px"><summary>Comment lire ces tableaux</summary>
      <p>10 € par pari. <b>Gain</b> et <b>ROI</b> : sur les paris réglés. Sous le nombre de paris : les gagnés et le
      <b>% de réussite</b> (gagnés / réglés ; à comparer avec la cote : à 2,00 il faut plus de 50 % pour gagner de l'argent). <b>A à E, X</b> : tranches d'écart entre la
      cote française et la cote juste, au moment où l'erreur est repérée (X : cotes au-dessus de 10).</p>
      <p><b>Selon la CLV</b> : pour les paris dont la CLV est mesurée, le gain réel comparé au gain <b>espéré</b>
      (10 € × CLV) ; un réel sous l'espéré peut n'être que de la malchance, surtout avec des grosses cotes. <b>Sans
      CLV</b> : la cote de référence a disparu avant le match ; si ces paris perdent toujours, il faut les éviter.</p>
      <p><b>CLV</b> : la cote prise comparée à la cote juste relevée juste avant le match (moins de 30 min). Positive =
      on a pris un meilleur prix que le marché final ; c’est un indice favorable, sans garantie de rentabilité. Sous la
      CLV : paris mesurés / paris réglés.</p>
      <p><b>Par match</b> : moyenne des CLV valides dans chaque événement relié, puis moyenne entre ces événements. Chaque match pèse autant. Couverture : matchs mesurés / matchs avec tickets réglés. Les identités non reliées peuvent rester séparées.</p>
      <p><b>Paris uniques</b> : chaque cote française comptée une fois, même si plusieurs références l'ont signalée.
      <b>Pinnacle, Polymarket…</b> : les paris repérés par cette référence, pour comparer les références entre elles.
      <b>Toutes réf.</b> : la somme des références (une même cote peut y compter plusieurs fois).
      <b>Stratégie</b> : les paris qui suivent les critères choisis le 11/10 (voir le texte au-dessus du graphique),
      comptés seulement depuis cette date. <b>ChatGPT</b> : stratégie indépendante, règles figées le 14/10,
      une seule mise par match et cinq nouvelles mises maximum par jour (heure de Paris).
      <b>Gemini Argon</b> : stratégie multi-références à plafond de cote adaptatif (2,15 Pinnacle / 2,60 Betfair & Polymarket),
      une mise par bookmaker et par match, huit par jour maximum.
      <b>JULES EDGE</b> : Pinnacle, cotes 1,30–2,50, edge 3–12 %, six paris par jour maximum.
      Suivi depuis sa première publication du 14/10 à 23 h 04 (Paris). Le passé est un rejeu séparé.
      <b>Eden</b> : Pinnacle et Polymarket, cotes 1,30–2,00, edge 2–12 %, 30 min à 24 h,
      une mise par bookmaker et par match, sans plafond journalier. Suivi depuis le 19/10 à 20 h (Paris).
      Le passé est un rejeu descriptif ; le test historique est positif, aucune rentabilité future n'est annoncée.</p></details>
      </details>
    </div>
    <div id="o-strategies" role="tabpanel" aria-labelledby="bt-strategies" hidden>
      <div class="raccourci-analyses"><a href="#analyses">Analyses et graphiques <span aria-hidden="true">↗</span></a></div>
      <div class="page-tete tete-strategies"><div><h2>Stratégies</h2><p class="sous-texte">Suivi simulé · 10 € par prise.</p></div><span class="periode-badge" id="strategies-contexte">Suivi prospectif</span></div>
      <div class="puces" id="strategies-periodes" aria-label="Période des stratégies"></div>
      <div class="filtres filtres-strategies">
        <div class="champ"><label for="strategies-ref">Afficher</label>
        <select id="strategies-ref"><option value="" selected>Toutes</option><option>Pinnacle</option><option>Polymarket</option><option value="comparateurs">Comparateurs</option></select></div>
        <div class="champ"><label for="strategies-tri">Classer par</label>
        <select id="strategies-tri"><option value="gain">Gain net</option><option value="roi">ROI</option><option value="regles">Paris réglés</option><option value="gagnes">Paris gagnés</option><option value="reussite">Réussite</option><option value="nom">Nom</option></select></div>
      </div>
      <p class="aide" id="strategies-total"></p>
      <div class="vue-strategies-toggle" role="group" aria-label="Présentation des stratégies">
        <button data-vue-strategies="liste" aria-pressed="true"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h16"/></svg>Comparaison</button>
        <button data-vue-strategies="graphiques" aria-pressed="false"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m3 17 6-6 4 3 8-10M3 21h18"/></svg>Graphiques</button>
      </div>
      <div id="strategies-vue-liste">
      <div class="ligne-colonnes" aria-hidden="true"><span>Stratégie</span><span>Réglés</span><span>ROI</span><span>Net</span></div>
      <div id="strategies-mobile" class="strategies-mobile" aria-label="Comparaison des stratégies"></div>
      <div class="tableau comparaison-bureau" aria-label="Comparaison des stratégies"><table class="strategies-table" id="strategies-table"></table></div>
      <details class="mode-emploi"><summary>Comment lire les chiffres</summary><p class="aide" style="margin-top:8px">10 € fictifs par pari. Réussite = gagnés / réglés (demi-gagnés inclus).
        ROI sur mises réglées. Gains et pertes : résultats nets des paris gagnants et perdants ; net = gains − pertes.
        Les mises des stratégies se recoupent : ne pas additionner les lignes. Claude peut prendre plusieurs paris par match.</p></details>
      </div>
      <div id="strategies-vue-graphiques" hidden>
      <h2 class="sous-titre">Évolution des gains des comparateurs</h2>
      <p class="aide">Gain cumulé en euros, par date de règlement. Touche une légende pour masquer ou afficher une courbe.
      Jules v1/v2 représentent une seule famille. Convergence ≥ 2 inclut M3, et Eden à partir du 19/10 ; elle reste exploratoire. Convergence ≥ 3 hors M3 ne compte ni M3 ni Eden. Un accord ne prouve pas la rentabilité.</p>
      <div class="carte"><div class="puces" id="strategies-legende"></div>
        <div id="strategies-courbes-vide" class="aide"></div>
        <svg id="strategies-courbes" viewBox="0 0 760 300" role="img" aria-label="Courbes comparées des gains cumulés en euros" style="width:100%;height:auto"></svg>
      </div>
      <h2 class="sous-titre">Gain net par stratégie</h2>
      <p class="aide">Même période, mêmes filtres et même ordre que le tableau.</p>
      <div class="carte" id="strategies-graph" role="img" aria-label="Comparaison des gains nets des stratégies"></div>
      </div>
      <details class="mode-emploi"><summary>Période, règles et limites de comparaison</summary><p class="aide" id="strategies-quoi"></p></details>
      <details class="carte">
        <summary><b>Variantes à exposition encadrée · suivis séparés</b></summary>
        <p class="aide"><b>Claude 1/match · max 10/j</b> : critères Claude, première prise par événement, dix prises maximum par jour.</p>
        <p class="aide"><b>Convergence ≥3 hors M3</b> : accord d'au moins trois familles parmi Claude, ChatGPT, Gemini et Jules, puis un seul pari par match. Jules v1/v2 donnent un seul vote.</p>
        <p class="aide"><b>M3 Max 3/match</b> : à partir du 17/10 à 03 h (Paris), un vainqueur, un handicap et un total maximum par événement relié, sans rejeu historique.</p>
        <p class="aide">Mises fictives uniformes de 10 €. Le rejeu est exploratoire et ne valide pas leur rentabilité.
        Déplie leur ligne, puis touche « Les paris » pour voir les prises de la période choisie.
        <a href="https://github.com/Matttgic/cotes-value/blob/ccr-148b8ccc-phitmr/docs/variantes-prudentes.md" target="_blank" rel="noopener">Règles figées</a>.</p>
        <div id="prudentes-picks"></div>
        <details><summary>Reconstitution exploratoire depuis le 14/10 à 14 h</summary>
          <p class="aide">Ces règles ont été figées le 15/10. Cette reconstitution n'est pas un suivi prospectif et ne modifie aucun bilan officiel.</p>
          <div id="prudentes-reconstitution"></div>
        </details>
      </details>
      <details class="carte" id="eden-picks">
        <summary><b>Eden</b> — voir les paris depuis le lancement</summary>
        <p class="aide">Pinnacle et Polymarket · cotes 1,30–2,00 · edge 2–12 % · 30 min à 24 h · une mise par bookmaker et par match · 10 € fictifs.
        Suivi depuis le 19/10 à 20 h (Paris). Le rejeu est positif sur la validation et le test ; cela ne promet pas un gain futur.
        <a href="https://github.com/Matttgic/cotes-value/blob/ccr-148b8ccc-phitmr/docs/strategie-eden.md" target="_blank" rel="noopener">Règles et limites</a>.</p>
        <div id="eden-picks-list"></div>
      </details>
      <details class="carte" id="gemini-picks">
        <summary><b>Gemini Argon v1</b> — voir les paris depuis le lancement <small>(règle v2 depuis le 18/10/2026 : un pari par bookmaker et par match)</small></summary>
        <p class="aide">Pinnacle (1,30–2,15), Betfair & Polymarket (1,30–2,60) · edge 2,5–12 % · 30 min à 24 h · 1 pari/match · max 8/jour · mise fictive 10 €.</p>
        <div id="gemini-picks-list"></div>
      </details>
      <details class="carte" id="jules-picks">
        <summary><b>JULES EDGE v1</b> — voir les paris depuis le lancement</summary>
        <p class="aide">Pinnacle · cotes 1,30–2,50 · edge 3–12 % · 15 min à 12 h · 1 pari/match · max 6/jour · 10 € fictifs.
        Suivi depuis le 14/10 à 23 h 04 (Paris). Rejeu historique séparé, rentabilité future non démontrée.
        <a href="https://github.com/Matttgic/cotes-value/blob/ccr-148b8ccc-phitmr/docs/strategie-jules.md" target="_blank" rel="noopener">Règles et audit reproductible</a>.</p>
        <div id="jules-picks-list"></div>
      </details>
      <details class="carte" id="jules-v2-picks">
        <summary><b>JULES EDGE v2 reconstruite</b> — voir les paris depuis le lancement</summary>
        <p class="aide">Pinnacle, Betfair et Polymarket · cotes 1,30–2,80 · edge 2,5–12 % · 15 min à 18 h · max 8/jour · 10 € fictifs.
        Une mise par événement identifiable, sources reliées sans consulter les résultats. Suivi à partir du 15/10 à 00 h 30 (Paris).
        <a href="https://github.com/Matttgic/cotes-value/blob/ccr-148b8ccc-phitmr/docs/strategie-jules-v2.md" target="_blank" rel="noopener">Audit et limites</a>.</p>
        <div id="jules-v2-picks-list"></div>
      </details>
      <details class="carte" id="m3-picks">
        <summary><b>M3 · MultiSport Value</b> — voir les paris depuis le lancement</summary>
        <p class="aide">Basket, baseball, handball · cotes 1,30–3,00 · edge 2–12 % · mise fictive 10 €.
        Optimisée sur le passé : aucune rentabilité future démontrée. Les sélections d'un même match peuvent être corrélées.</p>
        <div id="m3-picks-list"></div>
      </details>
      <div class="carte" id="laboratoire"></div>
    </div>
  </section>
  <section class="onglet" id="o-segments">
    <div class="page-tete"><div><p class="surtitre">Explorer les résultats</p><h2>Les segments</h2><p class="sous-texte">Sport, bookmaker, référence : touche un groupe pour voir ses paris.</p></div></div>
    <div class="puces" id="puces-seg"></div>
    <p class="aide" id="seg-quoi"></p>
    <div id="liste-segments"></div>
    <details class="aide"><summary>Comment lire</summary>
    <p>Un segment = les paris uniques réglés d'une tranche de cote, d'un bookmaker, d'un sport, d'une référence, ou d'un croisement
    (au moins 10 paris). La référence est celle de la première détection du pari unique. <b>Attendu</b> : la réussite prévue par la cote juste ; à 1,30, gagner 77 % est normal.
    <b>Écart</b> : réussite réelle moins attendue, en écarts-types sous hypothèse de paris binaires indépendants.
    L'indicateur devient fragile avec peu de matchs, des tickets corrélés, des remboursements ou des probabilités extrêmes.</p>
    <p><b>À confirmer</b> : au moins 30 paris sur des événements distincts, sans demi-règlement ni remboursement,
    écart d'au moins 2 et CLV positive. Ce repère descriptif ne prouve aucune rentabilité.
    <b>Piste</b> : ROI et CLV positifs. <b>CLV à vérifier</b> : ROI positif sans CLV positive mesurée.
    Les segments sont exploratoires : les nombreux essais et les dépendances restantes ne sont pas corrigés.</p>
    <p>Toucher un segment affiche ses paris : d'abord ceux à venir (pas encore commencés, du plus proche au plus lointain), puis ceux déjà réglés. Le toucher à nouveau les replie. Un pari à venir n'entre dans les chiffres du segment qu'une fois réglé.</p></details>
  </section>
  <section class="onglet" id="o-paris">
    <div class="page-tete"><div><h2>Paris</h2></div></div>
    <button type="button" class="paris-sante" id="paris-sante"></button>
    <div class="paris-puces" id="paris-puces" role="group" aria-label="Statut des paris"></div>
    <div id="paris-strategie-banner" class="carte" hidden></div>
    <div class="filtres recherche"><input type="search" id="f-q" placeholder="Rechercher équipe, ligue, pari…" aria-label="Rechercher équipe, ligue ou pari">
      <button class="btn" id="export-csv">Exporter CSV</button></div>
    <p class="aide" id="paris-compte" aria-live="polite"></p>
    <div class="outils-horaires" aria-label="Horaires des paris">
      <label>Début du match<select id="paris-horaire"><option value="">Tous les horaires</option><option value="imminent">Imminent · moins de 2 h</option><option value="aujourdhui">Aujourd’hui</option><option value="demain">Demain</option></select></label>
      <label>Ordre<select id="paris-tri"><option value="">Ordre du journal</option><option value="heure">Heure de match ↑</option><option value="recent">Heure de match ↓</option></select></label>
    </div>
    <div class="filtres grille-filtres">
      <label>Stratégie / simulation<select id="f-sim"></select></label>
      <label>Référence<select id="f-ref"></select></label>
      <label>Statut<select id="f-statut"></select></label>
      <label>Cote<select id="f-cote"></select></label>
      <label>Bookmaker<select id="f-book"></select></label>
      <label>Sport<select id="f-sport"></select></label>
    </div>
    <div class="outils-paris"><button class="btn secondaire" id="reinitialiser-filtres">Réinitialiser les filtres</button>
    <details class="mode-emploi"><summary>Comptage et export CSV</summary><p class="aide">Une prise par référence, au prix enregistré. L’export inclut tous les paris filtrés. Écarts et CLV en ratios dans le CSV.</p></details></div>
    <p class="paris-resume" id="paris-resume" aria-live="polite"></p>
    <div class="paris-colonnes" aria-hidden="true"><span>Sport · match · pari</span><span>Book · envoi<br>Cote (réf.)</span><span>Écart<br>Net</span></div>
    <div id="liste-paris"></div>
    <div style="text-align:center"><button class="btn" id="plus" style="display:none">Afficher plus</button></div>
  </section>
  <section class="onglet" id="o-analyses" aria-label="Analyses">
    <div class="page-tete"><div><p class="surtitre">Données et tendances</p><h2>Analyses</h2><p class="sous-texte">Résultats, volume et qualité des cotes.</p></div><span class="periode-badge" id="analyse-periode-badge">Suivi prospectif</span></div>
    <div class="analyse-filtres">
      <label for="analyse-selection">Sélection<select id="analyse-selection"><option value="uniques">Paris uniques</option></select></label>
      <label for="analyse-periode">Période<select id="analyse-periode"><option value="futur">Suivi prospectif</option><option value="ensemble">Historique 7–13 oct.</option><option value="tout">Tout l’historique</option></select></label>
    </div>
    <details class="mode-emploi analyse-affiner" id="analyse-affiner"><summary id="analyse-affiner-titre">Sport et bookmaker</summary><div class="analyse-filtres">
      <label for="analyse-sport">Sport<select id="analyse-sport"><option value="">Tous les sports</option></select></label>
      <label for="analyse-book">Bookmaker<select id="analyse-book"><option value="">Tous les bookmakers</option></select></label>
    </div></details>
    <p class="aide" id="analyse-contexte" aria-live="polite"></p>
    <div id="analyse-kpis" class="analyse-kpis"></div>
    <div id="analyse-vide" class="vide" hidden>Aucun pari pour cette sélection. Change la période, le sport ou le bookmaker.</div>
    <div id="analyse-graphiques" class="analyse-grille"></div>
    <details class="mode-emploi"><summary>Comptage, dates et limites</summary><p>Les paris uniques reprennent exactement la déduplication du Bilan, avant les filtres. Les stratégies utilisent leurs sélections enregistrées, sans votes supplémentaires. Leurs prises peuvent se recouper.</p>
      <p>Gain et ROI portent sur les mises réglées. Les paris en attente restent hors du ROI ; les demi-gains et demi-pertes restent distingués dans la répartition. La CLV utilise seulement les clôtures validées et affiche sa couverture. La réussite compte les gagnés et demi-gagnés parmi tous les réglés, comme dans Stratégies.</p>
      <p>L’historique 7–13 octobre utilise le relevé figé du laboratoire. Le suivi prospectif respecte le démarrage propre à chaque stratégie. « Tout l’historique » utilise les règlements actuels, y compris les règlements tardifs. Ces graphiques ne prédisent pas les gains futurs.</p>
    </details>
  </section>
  <section class="onglet" id="o-notifications">
    <div class="page-tete"><div><h2>Notifications</h2></div></div>
    <div class="carte notif-appareil">
      <p id="notif-etat" role="status" aria-live="polite">Vérification de cet appareil…</p>
      <div class="notif-boutons"><button class="btn" id="notif-activer">Activer les notifications</button>
        <button class="btn secondaire" id="notif-test" disabled>Envoyer un test</button>
        <button class="btn secondaire" id="notif-arreter" hidden>Désactiver</button></div>
    </div>
    <h3 class="bu-titre">Rapidité des alertes</h3>
    <div class="bu-table notif-rapidite" id="notif-rapidite"></div>
    <p class="aide">Chiffres réels des derniers relevés. Pendant un trou entre deux relevés, aucune opportunité n’est vue : c’est la cause des alertes ratées, pas l’envoi.</p>
    <h3 class="bu-titre">Me prévenir pour</h3>
    <fieldset class="carte" id="notif-strategies"><legend>Stratégies à suivre</legend></fieldset>
    <p><button class="btn" id="notif-sauver" disabled>Enregistrer mes choix</button></p>
    <p class="aide" id="notif-message" role="status" aria-live="polite"></p>
    <h3 class="bu-titre">Dernières alertes</h3>
    <div class="bu-table" id="notif-dernieres"></div>
    <p class="aide">Une seule alerte si plusieurs stratégies retiennent le même pari au même prix. Les prix de plus de 5 minutes sont écartés ; vérifie la cote, elle peut changer avant ton clic.</p>
    <details class="mode-emploi"><summary>Délais et derniers envois</summary><div id="notif-diagnostic"></div><p class="aide">Une réponse du service Push ne confirme pas la réception sur le téléphone. Chrome, le réseau et l’économie de batterie peuvent retarder l’affichage. L’heure de réception API ne certifie pas l’heure de mise à jour interne du fournisseur.</p></details>
    <details class="aide"><summary>Si tu ne reçois rien</summary>
      <p>Utilise Chrome sur Android et autorise les notifications du site et de Chrome dans les paramètres du téléphone.
      L’économie de batterie, une coupure réseau ou un arrêt forcé de Chrome peuvent retarder les alertes.
      Un plafond quotidien atteint ou aucune nouvelle sélection peuvent aussi expliquer l’absence d’alerte.</p>
      <p>Les préférences concernent cet appareil. Elles sont conservées avec un identifiant aléatoire et son abonnement de notification ;
      aucun compte ni adresse e-mail n’est demandé. Désactiver supprime l’abonnement du serveur.</p>
    </details>
  </section>
  <section class="onglet" id="o-regler">
    <div class="page-tete"><div><p class="surtitre">Règlement automatique</p><h2>Les résultats en attente</h2></div></div>
    <p class="aide">Les résultats sont recherchés automatiquement environ une fois par heure. La collecte prend le relais si la tâche planifiée tarde. Une source unique peut demander
    24 h de validation : « À régler » ne signifie pas qu’une saisie manuelle est déjà nécessaire.</p>
    <div id="reglement-etat" class="aide"></div>
    <p><button class="btn" id="copier">Copier la liste</button></p>
    <div id="liste-regler"></div>
  </section>
  <section class="onglet" id="o-controle">
    <div class="page-tete"><div><h2>Santé</h2></div></div>
    <div class="carte sante-global" id="sante-global" role="status"></div>
    <h3 class="bu-titre">Automatismes</h3><div class="bu-table" id="sante-auto"></div>
    <h3 class="bu-titre">Sources de cotes</h3><div class="bu-table" id="sante-cotes"></div>
    <h3 class="bu-titre">Sources de résultats</h3><div class="bu-table" id="sante-resultats"></div>
    <p class="aide" id="sante-attente"></p>
    <p><button type="button" class="btn secondaire" data-aller="regler" id="sante-saisie">Matchs à saisir à la main ›</button></p>
    <details class="mode-emploi sante-controle"><summary>Contrôle des intitulés des bookmakers</summary>
    <p class="aide">Chaque type d'intitulé de chaque bookmaker est comparé à la référence à chaque passage. Bien
    traduit, un marché est en général un peu sous la cote juste (marge) : rapport médian cote / cote juste entre
    0,70 et 1,02, et moins de 10 % des cotes au-dessus de 1,12. Seuls les intitulés <b>conformes</b> donnent des paris.</p>
    <div class="infos" id="ctl-resume" style="margin:0 0 12px"></div>
    <div class="puces" id="ctl-puces"></div>
    <div id="ctl-liste"></div>
    <h2 class="sous-titre">Dernier passage</h2>
    <div class="infos" id="infos" style="margin-top:0"></div>
    </details>
  </section>
</main>
<script>
// Mode jour/nuit appliqué dès le début du script unique de la page (les contrôles de publication exigent un seul script).
try{const t=localStorage.getItem("cv-theme-v1");if(t==="jour"||t==="nuit")document.documentElement.dataset.theme=t==="jour"?"light":"dark";}catch{}
const D = __DONNEES__;
const e = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const cote = x => x==null ? "—" : Number(x).toFixed(2).replace(".", ",");
const pct = x => x==null ? "—" : (x>0?"+":"") + (100*x).toFixed(1).replace(".", ",") + " %";
const eur = x => (x>0?"+":"") + Number(x).toFixed(2).replace(".", ",") + " €";
// bilan : montants compacts (euros entiers, séparateur de milliers ; pourcentages sans décimale au-delà de 100 %)
const eurC = x => x==null ? "—" : (x>0?"+":"") + Math.round(x).toLocaleString("fr-FR") + " €";
const pctC = x => x==null ? "—" : (x>0?"+":"") + (Math.abs(x) >= 1 ? Math.round(100*x).toLocaleString("fr-FR")
  : (100*x).toFixed(1).replace(".", ",")) + " %";
const quand = s => s ? new Date(s).toLocaleString("fr-FR",{timeZone:"Europe/Paris",weekday:"short",day:"numeric",month:"numeric",hour:"2-digit",minute:"2-digit"}) : "—";
const hm = s => s ? new Date(s).toLocaleTimeString("fr-FR",{timeZone:"Europe/Paris",hour:"2-digit",minute:"2-digit"}) : "";
const signe = x => x==null ? "" : x>0 ? "pos" : x<0 ? "neg" : "";
const STATUTS = {en_cours:"En cours",gagne:"Gagné",perdu:"Perdu",rembourse:"Remboursé",demi_gagne:"½ gagné",
  demi_perdu:"½ perdu",a_regler:"À régler"};
const lire = k => { try { return localStorage.getItem(k); } catch { return null; } };
const ecrire = (k,v) => { try { localStorage.setItem(k,v); } catch {} };

__VISUELS_JS__
__HORAIRES_JS__
__INTERFACE_JS__

// --- en-tête et onglets
const dc = (D.etat||{}).dernier_cycle || {};
document.getElementById("maj").textContent = dc.debut ? "mis à jour " + quand(dc.debut) + (dc.mode==="test" ? " · test" : "") : "pas encore de données";
// Le bilan a deux vues : les paris uniques et les stratégies (ancienne page Stratégies).
let vueBilan = "uniques";
function montrerVueBilan(v) {
  vueBilan = v;
  document.querySelectorAll("[data-bilan]").forEach(b => b.setAttribute("aria-selected", String(b.dataset.bilan===v)));
  document.getElementById("bilan-uniques").hidden = v !== "uniques";
  document.getElementById("o-strategies").hidden = v !== "strategies";
  if (v === "strategies") requestAnimationFrame(() => rendreStrategies());
  else requestAnimationFrame(() => rendreCourbe());
}
// Quatre onglets : « À jouer » rejoint Paris, la saisie à la main rejoint Santé, Analyses et Segments restent sous Bilan.
const GROUPES = {jouer:"paris", regler:"controle", strategies:"bilan", segments:"bilan", analyses:"bilan"};
function ouvrir(o) {
  // « #strategies » ouvre la vue Stratégies du bilan ; « #bilan », les paris uniques.
  if (o === "strategies" || o === "bilan") vueBilan = o === "strategies" ? "strategies" : "uniques";
  const page = o === "strategies" ? "bilan" : o === "jouer" ? "paris" : o, groupe = GROUPES[page] || page;
  const nom = page === "bilan" && vueBilan === "strategies" ? "strategies" : page;
  document.querySelectorAll("nav button[data-o]").forEach(b => {
    b.classList.toggle("actif", b.dataset.o===groupe);
    if (b.dataset.o===groupe) b.setAttribute("aria-current","page"); else b.removeAttribute("aria-current");
  });
  document.querySelectorAll(".onglet").forEach(s => s.classList.toggle("actif", s.id==="o-"+page));
  ecrire("onglet", nom); history.replaceState(null, "", "#"+nom);
  if (page === "bilan") montrerVueBilan(vueBilan);
  if (page === "analyses") requestAnimationFrame(() => rendreAnalyses());
}
document.querySelectorAll("[data-bilan]").forEach(b => b.onclick = () => {
  montrerVueBilan(b.dataset.bilan); history.replaceState(null, "", "#"+(b.dataset.bilan === "strategies" ? "strategies" : "bilan"));
  ecrire("onglet", b.dataset.bilan === "strategies" ? "strategies" : "bilan");
});
document.querySelectorAll("[data-aller]").forEach(b => b.onclick = () => {ouvrir(b.dataset.aller);window.scrollTo(0,0);});
document.querySelectorAll("nav button[data-o]").forEach(b => b.onclick = () => {ouvrir(b.dataset.o);window.scrollTo(0,0);});

// --- Outils partagés par Paris et Bilan
const minutes = s => s ? Math.max(0, Math.round((Date.now() - new Date(s)) / 60000)) : null;
const badgeStrategies = p => (p.strategies || []).map(cle =>
  `<span class="badge">${e(D.strategies_badges?.[cle] || cle)}</span>`).join("") +
  (p.convergence ? '<span class="badge en_cours">Convergence ≥ 2</span>' : "");
const ecartsReferences = p => ["Polymarket", "Smarkets"].map(nom =>
  `<span>écart vs ${nom} ${pct(p["ecart_" + nom.toLowerCase()])}</span>`).join(" ");

// --- Bilan
let refBilan = "Uniques";
const NOMS_REF = {Uniques: "Paris uniques", Toutes: "Toutes réf.", "JULES EDGE":"JULES EDGE v1"};
const ST = D.strategie || {};
const CG = D.chatgpt || {};
const GM = D.gemini || {};
const JL = D.jules || {};
const JV2 = D.jules_v2 || {};
const ED = D.eden || {};
const QUOI = {Uniques: "Ce que tu aurais gagné en jouant chaque cote signalée une seule fois (10 € par pari).",
  Toutes: "Somme des références : une même cote repérée par plusieurs références compte plusieurs fois.",
  "Stratégie": `Stratégie testée depuis le ${ST.debut ? new Date(ST.debut).toLocaleString("fr-FR", {day: "numeric",
    month: "numeric", hour: "2-digit", minute: "2-digit"}) : "11/10"} : référence ${(ST.references || []).join(", ")},
    écart ≥ 2 %, cote < ${String(ST.cote_max).replace(".", ",")}, repéré moins de ${ST.avance_max_h} h avant le match,
    hommes seniors. Critères figés : seule la CLV des prochains paris dira si elle marche (environ 300 paris).`,
  "ChatGPT": `ChatGPT v${CG.version} — simulation depuis le ${new Date(CG.debut).toLocaleString("fr-FR", {
    timeZone: "Europe/Paris", day: "numeric", month: "numeric", hour: "2-digit", minute: "2-digit"})} (Paris).
    Pinnacle sans marge ; cote ${cote(CG.cote_min)} à ${cote(CG.cote_max)} ; edge ${Math.round(CG.edge_min*100)} à ${Math.round(CG.edge_max*100)} %.
    Première détection entre ${CG.avance_min_minutes} min et ${CG.avance_max_h} h avant le match ; référence lue depuis ${CG.fraicheur_max_minutes} min maximum et correspondance contrôlée.
    Match entier : 1N2, vainqueur, totaux et handicaps entiers ou demi-points ; tennis/volley : vainqueur seulement.
    ${CG.mise} € fictifs par pari, un seul pari par match tous bookmakers confondus, ${CG.paris_max_jour} par jour maximum.
    Critères figés, résultats passés exclus. Pas de combiné ni de hausse de mise après une perte. Rentabilité non démontrée.`,
  "Gemini Argon": `Gemini Argon v${GM.version || 1} — simulation depuis le ${GM.debut ? new Date(GM.debut).toLocaleString("fr-FR", {
    timeZone: "Europe/Paris", day: "numeric", month: "numeric", hour: "2-digit", minute: "2-digit"}) : "14/10"} (Paris).
    Multi-références (Pinnacle 1,30–2,15 ; Betfair & Polymarket 1,30–2,60) ; edge 2,5 à 12 %.
    Détection entre ${GM.avance_min_minutes || 30} min et ${GM.avance_max_h || 24} h avant le match ; fraîcheur ≤ ${GM.fraicheur_max_minutes || 10} min.
    10 € fictifs par pari, une mise par bookmaker et par match, ${GM.paris_max_jour || 8} par jour maximum.`,
  "JULES EDGE": `JULES EDGE v${JL.version || 1} — suivi depuis le ${new Date(JL.debut).toLocaleString("fr-FR", {
    timeZone: "Europe/Paris", day: "numeric", month: "numeric", hour: "2-digit", minute: "2-digit"})} (Paris).
    Pinnacle sans marge ; cotes 1,30–2,50 ; edge 3–12 % ; 15 min à 12 h avant le match ; référence fraîche de 5 min maximum.
    Un seul pari par match et ${JL.paris_max_jour || 6} par jour maximum, à 10 € fictifs.
    Le passé reste un rejeu descriptif dans Stratégies → Historique. Rentabilité future non démontrée.`,
  "JULES EDGE v2": `JULES EDGE v2 reconstruite — suivi à partir du ${new Date(JV2.debut).toLocaleString("fr-FR", {
    timeZone:"Europe/Paris", day:"numeric", month:"numeric", hour:"2-digit", minute:"2-digit"})} (Paris).
    Pinnacle, Betfair et Polymarket ; cotes 1,30–2,80 ; edge 2,5–12 % ; 15 min à 18 h avant le match ; référence de 5 min maximum.
    Une mise par événement identifiable, huit par jour maximum, à 10 € fictifs. Historique séparé ; rentabilité future non démontrée.`,
  "Eden": `Eden v${ED.version || 1} — suivi à partir du ${ED.debut ? new Date(ED.debut).toLocaleString("fr-FR", {
    timeZone: "Europe/Paris", day: "numeric", month: "numeric", hour: "2-digit", minute: "2-digit"}) : "19/10 20:00"} (Paris).
    Pinnacle et Polymarket ; cotes 1,30–2,00 ; edge 2–12 % ; détection de 30 min à 24 h ; référence de 15 min maximum.
    Une mise fictive de 10 € par bookmaker français et par match, sans plafond journalier.
    Le rejeu d'avant le lancement est descriptif. Rentabilité future non démontrée.`};
// ligne « Total » : cumul des simulations choisies (A, A+B, A+B+C…), par défaut toutes
const SIMS = Object.keys(D.simulations);
const CUMULS = [...SIMS.filter(s => s !== "X").map((s, i, l) => l.slice(0, i + 1)), SIMS];
let cumul = CUMULS.length - 1;
const nomCumul = l => l.length === SIMS.length ? "Toutes" : l.join("+");
function additionner(sims, source = D.bilan, prefixe = "") {
  const t = {paris: 0, regles: 0, en_cours: 0, mises: 0, gains: 0, clv_somme: 0, clv_n: 0, gagnes: 0,
    gains_avec_clv: 0, espere_clv: 0, gains_sans_clv: 0, regles_sans_clv: 0};
  let vu = false;
  const evenements=new Map();
  for (const s of sims) {
    const b = (source || {})[prefixe + s + "|" + refBilan];
    if (!b) continue;
    vu = true;
    for (const k of Object.keys(t)) t[k] += b[k] || 0;
    for(const [id,mesures] of Object.entries(b.evenements_detail || {})) {
      const v=evenements.get(id) || [0,0,0,0];
      evenements.set(id,v.map((x,i)=>x+mesures[i]));
    }
  }
  if (!vu) return null;
  t.evenements=evenements.size;
  t.evenements_regles=[...evenements.values()].filter(v=>v[1]>0).length;
  const cs=[...evenements.values()].filter(v=>v[3]>0).map(v=>v[2]/v[3]);
  t.clv_evenement=cs.length?cs.reduce((a,b)=>a+b,0)/cs.length:null;
  t.clv_evenements_n=cs.length;
  t.roi = t.mises ? t.gains / t.mises : null;
  t.clv_moyenne = t.clv_n ? t.clv_somme / t.clv_n : null;
  return t;
}
function rendreBilan() {
  const refs = ["Uniques", "Stratégie", "ChatGPT", "Gemini Argon", "JULES EDGE", "JULES EDGE v2", "Eden", ...D.references, "Toutes"];
  const bloc = D.ecarts_references || {};
  document.getElementById("bilan-ecarts").textContent = "Paris uniques réglés · " +
    ["Polymarket", "Smarkets"].map(nom => {
      const x = bloc[nom] || {};
      return `écart vs ${nom} ${x.n ? pct(x.moyenne) : "—"}` + (x.n ? ` (${x.n})` : "");
    }).join(" · ");
  document.getElementById("puces-ref").innerHTML = refs.map(r =>
    `<button data-r="${r}" class="${r===refBilan?"actif":""}">${NOMS_REF[r] || r}</button>`).join("");
  document.getElementById("bilan-quoi").textContent = QUOI[refBilan] || `Paris repérés par ${refBilan}.`;
  document.getElementById("voir-chatgpt").hidden = refBilan !== "ChatGPT";
  document.getElementById("voir-gemini").hidden = refBilan !== "Gemini Argon";
  document.getElementById("voir-jules").hidden = refBilan !== "JULES EDGE";
  document.getElementById("voir-jules-v2").hidden = refBilan !== "JULES EDGE v2";
  document.getElementById("voir-eden").hidden = refBilan !== "Eden";
  document.querySelectorAll("#puces-ref button").forEach(b => b.onclick = () => { refBilan = b.dataset.r; rendreBilan(); });
  const ligne = (titre, b) => !b ? `<tr><td>${titre}</td><td>0</td><td>—</td><td>—</td></tr>`
    : `<tr><td>${titre}</td><td>${b.regles}<small>${b.evenements_regles ?? "—"} matchs</small>${b.regles ? `<small>${b.gagnes} gagné${b.gagnes > 1 ? "s" : ""} · <b>${Math.round(100 * b.gagnes / b.regles)} %</b></small>` : ""}${b.en_cours ? `<small>${b.en_cours} en cours</small>` : ""}</td>
<td class="${signe(b.gains)}">${eurC(b.gains)}<small class="roi ${signe(b.roi)}">${b.roi==null ? "" : pctC(b.roi)}</small></td>
<td class="${signe(b.clv_moyenne)}">${pctC(b.clv_moyenne)}${b.regles ? `<small>${b.clv_n}/${b.regles} tickets</small><small>Par match ${pctC(b.clv_evenement)} · ${b.clv_evenements_n ?? 0}/${b.evenements_regles ?? "—"}</small>` : ""}</td></tr>`;
  document.getElementById("liste-bilan").innerHTML = `<tr><th>Simul.</th><th>Paris</th><th>Gain<small>ROI</small></th><th>CLV</th></tr>` +
    Object.entries(D.simulations).filter(([s]) => !(["Stratégie", "ChatGPT", "Gemini Argon", "JULES EDGE", "JULES EDGE v2", "Eden", "M3", "Convergence ≥ 2"].includes(refBilan) && s === "X")).map(([s, nom]) => ligne(`<b>${s}</b> <small>${e(nom)}</small>`, D.bilan[s + "|" + refBilan])).join("") +
    ligne(`<b>Total</b> <select id="cumul" class="cumul">${CUMULS.map((l, i) =>
      `<option value="${i}"${i===cumul?" selected":""}>${nomCumul(l)}</option>`).join("")}</select>`,
      additionner(CUMULS[cumul])).replace("<tr>", '<tr class="total">');
  document.getElementById("cumul").onchange = ev => { cumul = Number(ev.target.value); rendreBilan(); };
  // réel contre espéré d'après la CLV, et paris dont la CLV n'a pas pu être mesurée (selon la sélection du Total)
  const tc = additionner(CUMULS[cumul]);
  document.getElementById("bilan-clv").innerHTML = !tc ? "" :
    `<tr><th>Selon la CLV</th><th>Paris</th><th>Réel</th><th>Espéré</th></tr>
<tr><td><b>CLV mesurée</b><small>${pctC(tc.clv_moyenne)} en moyenne</small></td><td>${tc.clv_n}</td>
<td class="${signe(tc.gains_avec_clv)}">${eurC(tc.gains_avec_clv)}</td><td class="${signe(tc.espere_clv)}">${eurC(tc.espere_clv)}</td></tr>
<tr><td><b>Sans CLV</b><small>référence absente avant le match</small></td><td>${tc.regles_sans_clv}</td>
<td class="${signe(tc.gains_sans_clv)}">${eurC(tc.gains_sans_clv)}</td><td>—</td></tr>`;
  rendreCourbe();
  document.getElementById("bilan-tranches").innerHTML = `<tr><th>Cote</th><th>Paris</th><th>Gain<small>ROI</small></th><th>CLV</th></tr>` +
    (D.tranches || []).map(t => ligne(`<b>${e(t)}</b>`, (D.bilan_tranches || {})[t + "|" + refBilan])).join("");
}
// --- graphique : gain cumulé au fil des paris réglés (référence et simulations choisies dans le bilan)
function pas(etendue) {               // pas « rond » pour 3 à 5 graduations
  const brut = etendue / 4, p = Math.pow(10, Math.floor(Math.log10(brut || 1)));
  return [1, 2, 2.5, 5, 10].map(m => m * p).find(v => v >= brut) || 10 * p;
}
function rendreCourbe() {
  const sims = CUMULS[cumul];
  const pts = ((D.courbes || {})[refBilan] || []).filter(p => sims.includes(p[2]));
  const svg = document.getElementById("courbe-svg"), bulle = document.getElementById("bulle");
  document.getElementById("courbe-quoi").textContent = "· " + (NOMS_REF[refBilan] || refBilan) +
    (sims.length === SIMS.length ? "" : " · " + nomCumul(sims));
  const cum = [0], att = [0];
  for (const p of pts) { cum.push(cum[cum.length - 1] + p[1]); att.push(att[att.length - 1] + (p[3] || 0)); }
  const avecAttendu = pts.some(p => p[3] != null);
  const total = cum[cum.length - 1];
  document.getElementById("legende").innerHTML = pts.length < 2 ? "" :
    `<span><i style="background:var(--serie)"></i>Réel <b class="${signe(total)}">${eurC(total)}</b></span>` +
    (avecAttendu ? `<span><i style="background:var(--attendu)"></i>Attendu <b class="${signe(att[att.length - 1])}">${eurC(att[att.length - 1])}</b></span>` : "");
  if (pts.length < 2) { svg.innerHTML = `<text x="50%" y="50%" text-anchor="middle">Pas encore assez de paris réglés.</text>`; return; }
  const W = svg.clientWidth || 340, H = 170, g = 46, d = 8, h = 8, b = 20;
  const tous = avecAttendu ? cum.concat(att) : cum;
  let lo = Math.min(0, ...tous), hi = Math.max(0, ...tous);
  const st = pas(hi - lo || 10); lo = Math.floor(lo / st) * st; hi = Math.ceil(hi / st) * st;
  const X = i => g + (W - g - d) * i / (cum.length - 1), Y = v => h + (H - h - b) * (hi - v) / (hi - lo || 1);
  let grille = "";
  for (let v = lo; v <= hi + 1e-9; v += st)
    grille += `<line x1="${g}" x2="${W - d}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--ligne)" stroke-width="${v === 0 ? 1.5 : 1}"/>
<text x="${g - 6}" y="${Y(v) + 4}" text-anchor="end">${eurC(v)}</text>`;
  const jour = t => new Date(t * 60000).toLocaleDateString("fr-FR", {day: "numeric", month: "numeric"});
  const axe = `<text x="${g}" y="${H - 4}">${jour(pts[0][0])}</text><text x="${W - d}" y="${H - 4}" text-anchor="end">${jour(pts[pts.length - 1][0])}</text>
<text x="${(g + W - d) / 2}" y="${H - 4}" text-anchor="middle">${pts.length} paris réglés</text>`;
  const trace = serie => serie.map((v, i) => `${i ? "L" : "M"}${X(i).toFixed(1)},${Y(v).toFixed(1)}`).join("");
  const chemin = (serie, coul) => `<path d="${trace(serie)}" fill="none" stroke="var(${coul})" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>`;
  svg.innerHTML = grille + axe + (avecAttendu ? chemin(att, "--attendu") : "") + chemin(cum, "--serie") + `
<line id="viseur" y1="${h}" y2="${H - b}" stroke="var(--doux)" stroke-width="1" visibility="hidden"/>
<circle id="point" r="4.5" fill="var(--serie)" stroke="var(--carte)" stroke-width="2" visibility="hidden"/>
<rect x="${g}" y="0" width="${W - g - d}" height="${H}" fill="transparent" id="zone"/>`;
  const zone = svg.querySelector("#zone"), viseur = svg.querySelector("#viseur"), point = svg.querySelector("#point");
  const montrer = ev => {
    const r = svg.getBoundingClientRect();
    const i = Math.max(1, Math.min(cum.length - 1, Math.round((ev.clientX - r.left - g) / (W - g - d) * (cum.length - 1))));
    const p = pts[i - 1], x = X(i), y = Y(cum[i]);
    viseur.setAttribute("x1", x); viseur.setAttribute("x2", x); viseur.setAttribute("visibility", "visible");
    point.setAttribute("cx", x); point.setAttribute("cy", y); point.setAttribute("visibility", "visible");
    bulle.innerHTML = `Pari ${i} · réglé le ${quand(new Date(p[0] * 60000).toISOString())} · ce pari ${eur(p[1])}<br>Réel <b>${eurC(cum[i])}</b>` +
      (avecAttendu ? ` · attendu <b>${eurC(att[i])}</b>` : "");
    bulle.style.display = "block";
    // à droite du point, ou à gauche s'il n'y a pas la place ; positions relatives à la carte
    const gauche = x + 12 + bulle.offsetWidth > W ? x - 12 - bulle.offsetWidth : x + 12;
    const c = document.getElementById("courbe").getBoundingClientRect();     // (un <svg> n'a pas d'offsetTop)
    bulle.style.left = (r.left - c.left + Math.max(0, gauche)) + "px";
    // au-dessus du point, ou en dessous quand il est en haut du graphique (ne pas cacher la courbe)
    const haut = y - bulle.offsetHeight - 10 >= 0 ? y - bulle.offsetHeight - 10 : Math.min(y + 14, H - bulle.offsetHeight);
    bulle.style.top = (r.top - c.top + haut) + "px";
  };
  const cacher = () => { viseur.setAttribute("visibility", "hidden"); point.setAttribute("visibility", "hidden"); bulle.style.display = "none"; };
  zone.addEventListener("pointermove", montrer); zone.addEventListener("pointerdown", montrer);
  zone.addEventListener("pointerleave", cacher);
}
window.addEventListener("resize", () => { rendreCourbe(); if (document.getElementById("o-strategies").classList.contains("actif")) rendreStrategies(); });
rendreBilan();
document.getElementById("infos").innerHTML = [
  ["Cotes françaises lues", (dc.cotes||{}).francaises], ["Matchs comparés", dc.matchs_francais],
  ["Erreurs au dernier passage", dc.opportunites],
  // sources en panne ou incomplètes au dernier passage (une absence de résultat n'est pas toujours normale)
  ["Sources en panne", Object.entries(dc.etapes || {}).filter(([k, v]) => !v.ok || v.degrade)
    .map(([k]) => e(k.replace(/^resultats_/, ""))).join(", ") || "aucune"]
].map(([a,b]) => `<div>${a}<b>${b ?? "—"}</b></div>`).join("");

// --- Paris : fiches déjà regroupées (un même pari pris par plusieurs simulations = une seule fiche)
const recentes = new Map(D.paris.map(p => [p.id,p]));
const fiches = D.catalogue ? D.catalogue.lignes.map(ligne => {
  const p = Object.fromEntries(D.catalogue.champs.map((cle,i) => [cle,ligne[i]]));
  for (const cle of Object.keys(D.strategies_badges || {})) p[cle] = p.strategies.includes(cle);
  return {...p, sims:[p.simulation], trace:recentes.get(p.id)?.trace || []};
}) : D.paris;
if(D.laboratoire?.navigation?.paris) {
  const parId=new Map(fiches.map(p=>[p.id,p]));
  for(const [id,meta] of Object.entries(D.laboratoire.navigation.paris)) {
    const p=parId.get(id);
    if(p) D.laboratoire.navigation.paris[id]={...p,...meta};
  }
}
document.getElementById("nb-paris").textContent = fiches.length || "";
const normaliserRecherche = s => String(s || "").normalize("NFD").replace(/[\u0300-\u036f]/g,"").toLocaleLowerCase("fr");
let parisFiltres = [];
const FILTRES = {sim:["sims","Simulations"], ref:["reference","Références"], statut:["statut","Statuts"],
  cote:["tranche","Cotes"], book:["bookmaker","Bookmakers"], sport:["sport","Sports"]};
for (const [id,[champ,tous]] of Object.entries(FILTRES)) {
  // cotes : les tranches du bilan ; simulations : + « Stratégie », « ChatGPT », « Gemini Argon »
  const vals = champ === "tranche" ? D.tranches || [] : [...((D.valeurs_filtres || {})[champ] || []),
    ...(champ === "sims" ? ["Stratégie", "ChatGPT", "Gemini Argon", "JULES EDGE", "JULES EDGE v2", "Eden", "M3", "Convergence ≥ 2", ...Object.keys(D.variantes || {})] : [])];
  const sel = document.getElementById("f-" + id);
  sel.innerHTML = `<option value="">${tous}</option>` + vals.map(v => `<option value="${e(v)}">${e(
    champ==="statut" ? STATUTS[v]||v : champ==="sims" && D.simulations[v] ? v + " " + D.simulations[v] : v)}</option>`).join("");
  sel.setAttribute("aria-label", tous);
  sel.onchange = () => { limite = 50; rendreParis(); };
}
let limite = 50;
let strategieChoisie = null;
document.getElementById("f-q").oninput = () => { limite=50; rendreParis(); };
document.getElementById("reinitialiser-filtres").onclick = () => {
  strategieChoisie=null; limite=50; puceStatut="";
  document.getElementById("f-q").value="";
  document.getElementById("paris-horaire").value="";
  document.getElementById("paris-tri").value="";
  for (const id of Object.keys(FILTRES)) document.getElementById("f-"+id).value="";
  rendreParis();
};
const COLONNES_CSV = ["date_detecte","debut","sport","ligue","domicile","exterieur","pari","bookmaker","cote","reference","cote_juste","ecart","ecart_polymarket","ecart_smarkets","clv","statut","gain","strategies","collecte_recue","collecte_debut","prix_revu","prix_revu_le"];
// Les cellules texte ne doivent pas devenir des formules à l'ouverture dans un tableur.
const celluleCSV = valeur => {
  if (valeur == null) return '""';
  let texte = String(valeur);
  if (typeof valeur === "string" && /^[\s\u0000-\u001f]*[=+@-]/.test(texte)) texte = "'"+texte;
  return '"'+texte.replace(/"/g,'""')+'"';
};
function csvParis(liste) {
  const lignes = liste.map(p => {
    const noms = (p.strategies || []).map(cle => D.strategies_badges?.[cle] || cle);
    if (p.convergence) noms.push("Convergence ≥ 2");
    const row = {...p,date_detecte:p.detecte,strategies:noms.join(" | ")};
    return COLONNES_CSV.map(cle => celluleCSV(row[cle])).join(";");
  });
  return "\ufeff"+[COLONNES_CSV.join(";"),...lignes].join("\r\n")+"\r\n";
}
document.getElementById("export-csv").onclick = () => {
  const blob = new Blob([csvParis(parisFiltres)], {type:"text/csv;charset=utf-8"});
  const url = URL.createObjectURL(blob), a = document.createElement("a");
  a.href=url; a.download="cotes-value-paris-"+new Date().toISOString().slice(0,10)+".csv";
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url),1000);
};
// Une ligne par pari : couleur selon le règlement, cote française suivie de la cote de référence.
const ETAT_LIGNE = {gagne:["gagne","✓ Gagné"], demi_gagne:["gagne","✓ ½ gagné"], perdu:["perdu","✗ Perdu"],
  demi_perdu:["perdu","✗ ½ perdu"], rembourse:["rembourse","Remboursé"], a_regler:["regler","À régler"]};
const etatLigne = p => ETAT_LIGNE[p.statut] || (p.a_regler ? ETAT_LIGNE.a_regler : ["cours","En cours"]);
const REF_COURTE = {Pinnacle:"", Polymarket:"Poly ", Consensus:"Cons. ", Smarkets:"Sm. "};
const heureEnvoi = p => {
  const t = new Date(p.alerte_demande_le || p.detecte || "");
  if (!Number.isFinite(t.getTime())) return "";
  const opts = {timeZone:"Europe/Paris",hour:"2-digit",minute:"2-digit"};
  return jourParis(t) === jourParis(new Date()) ? t.toLocaleTimeString("fr-FR",opts)
    : t.toLocaleString("fr-FR",{...opts,day:"2-digit",month:"2-digit"});
};
const nomSport = s => (typeof nomsSports !== "undefined" && nomsSports[s]) || s || "Sport";
const carteParis = p => { const [etat,libelle] = etatLigne(p); return `<details class="ligne-detail ligne-pari pari-ligne etat-${etat}" id="pari-${e(encodeURIComponent(JSON.stringify([p.id,p.bookmaker,p.match_id,p.pari,p.detecte,p.reference])))}"><summary>
<span class="pari-gauche"><span class="pari-tete"><span class="puce-sport">${e(nomSport(p.sport))}</span><span class="pari-ligue">${e(p.ligue)}</span></span>
<span class="ligne-nom pari-match">${e(p.domicile)} – ${e(p.exterieur)}</span><span class="pari-selection">${e(p.pari)}</span></span>
<span class="pari-milieu"><span class="pari-bookmaker">${e(p.bookmaker)}${heureEnvoi(p) ? " · "+heureEnvoi(p) : ""}</span>
<span><b class="ligne-cote" aria-label="Cote ${cote(p.cote)}">${cote(p.cote)}</b> <span class="pari-ref" title="Cote ${e(p.reference)} sans marge">(${e(REF_COURTE[p.reference] ?? (p.reference||"")+" ")}${cote(p.cote_juste)})</span></span></span>
<span class="pari-droite"><b class="ligne-valeur">${p.gain!=null ? eur(p.gain) : pct(p.ecart)}</b><span class="pari-etat">${libelle}</span></span></summary><div class="ligne-corps"><article class="carte">
<div class="l1"><span class="match">${e(p.domicile)} – ${e(p.exterieur)}</span>${horairePari(p)}</div>
<div class="l1">${collectePari(p)}</div>
<div class="l2">${e(p.pari)}</div>
<div class="l3"><span><b>${e(p.bookmaker)} ${cote(p.cote)}</b></span><span>${e(p.reference)} ${cote(p.cote_juste)}</span>
<span class="ecart">${pct(p.ecart)}</span>${ecartsReferences(p)}</div>
<div class="l4"><span class="badge ${p.statut}">${STATUTS[p.statut]||p.statut}</span>
${badgeStrategies(p)}
${p.gain!=null ? `<b class="${signe(p.gain)}">${eur(p.gain)}</b>` : ""}
<span>CLV <span class="${signe(p.clv)}">${pct(p.clv)}</span></span></div>
${(p.trace||[]).length ? `<details class="trace"><summary>Détails</summary>${p.trace.map(t => `<p>${e(t)}</p>`).join("")}</details>` : ""}
</article></div></details>`; };
// Puces de statut : les demi-règlements rejoignent les gagnés ou les perdus.
const PUCES = [["","Tous"],["en_cours","En cours"],["a_regler","À régler"],["gagne","Gagnés"],["perdu","Perdus"]];
let puceStatut = "";
const accepteePuce = p => !puceStatut || (puceStatut === "gagne" ? ["gagne","demi_gagne"].includes(p.statut)
  : puceStatut === "perdu" ? ["perdu","demi_perdu"].includes(p.statut)
  : puceStatut === "a_regler" ? p.statut === "a_regler" || (p.a_regler && p.statut === "en_cours")
  : puceStatut === "en_cours" ? p.statut === "en_cours" && !p.a_regler : true);
document.getElementById("paris-puces").onclick = ev => {
  const b = ev.target?.closest?.("button[data-puce]");
  if (!b) return;
  puceStatut = b.dataset.puce; limite = 50; rendreParis();
};
const resumeParis = L => {
  const regles = L.filter(p => p.gain != null), net = regles.reduce((s,p) => s+p.gain, 0),
    mises = regles.reduce((s,p) => s+(p.mise ?? 10), 0);
  return `<span><b>${regles.length}</b> réglé${regles.length>1?"s":""} sur ${L.length}</span>
<span>Net <b class="${signe(net)}">${eur(net)}</b></span><span>ROI <b class="${signe(net)}">${mises ? pct(net/mises) : "—"}</b></span>`;
};
function rendreParis() {
  document.getElementById("paris-puces").innerHTML = PUCES.map(([v,t]) =>
    `<button type="button" data-puce="${v}" aria-pressed="${v===puceStatut}">${t}</button>`).join("");
  const f = Object.fromEntries(Object.entries(FILTRES).map(([id,[champ]]) => [champ, document.getElementById("f-"+id).value]));
  const navigation = D.laboratoire?.navigation;
  const ids = strategieChoisie ? (navigation?.selections?.[strategieChoisie.id]?.[strategieChoisie.periode] || []) : null;
  const source = ids ? ids.map(id => navigation.paris[id]).filter(Boolean).map(p => {
    if (strategieChoisie.periode === "futur") return p;
    const badges = p.strategies_historiques || [];
    return {...p, ...Object.fromEntries(Object.keys(D.strategies_badges || {}).map(cle => [cle,badges.includes(cle)])),
      strategies:badges, convergence:p.convergence_historique || false};
  }) : fiches;
  const q = normaliserRecherche(document.getElementById("f-q").value).trim();
  const maintenant=Date.now(),triHoraire=document.getElementById('paris-tri').value;
  const L = trierHoraires(source.filter(p => accepteHoraire(p,document.getElementById('paris-horaire').value,maintenant) && accepteePuce(p) &&
    (!q || normaliserRecherche([p.domicile,p.exterieur,p.ligue,p.pari].join(" ")).includes(q)) &&
    Object.entries(f).every(([k,v]) => !v || (k==="sims" ? (v==="Stratégie" ? p.strategie : v==="ChatGPT" ? p.chatgpt : v==="Gemini Argon" ? p.gemini : v==="JULES EDGE" ? p.jules : v==="JULES EDGE v2" ? p.jules_v2 : v==="Eden" ? p.eden : v==="M3" ? p.m3 : v==="Convergence ≥ 2" ? p.convergence : D.variantes?.[v] ? p[D.variantes[v].cle] : (p.sims||[]).includes(v)) : p[k]===v))),triHoraire);
  parisFiltres = L;
  document.getElementById("paris-resume").innerHTML = resumeParis(L);
  document.getElementById("paris-compte").textContent = `${L.length} prise(s) · ${Math.min(limite,L.length)} affichées · export des ${L.length} prises filtrées.`;
  const banner = document.getElementById("paris-strategie-banner");
  const plus = document.getElementById("plus");
  banner.hidden = !strategieChoisie;
  if (strategieChoisie) {
    banner.innerHTML = `<div><b>${e(strategieChoisie.nom)}</b><div class="aide">${e(STRAT_PERIODES[strategieChoisie.periode])}
      · ${L.length} pari(s) · cotes simulées à la détection. Les statistiques historiques restent figées au relevé.</div></div>
      <button class="btn" id="paris-tout">Tous les paris</button>`;
    document.getElementById("paris-tout").onclick = () => {
      strategieChoisie = null;
      document.getElementById("f-q").value = "";
      for (const id of Object.keys(FILTRES)) document.getElementById("f-"+id).value = "";
      limite = 50;
      rendreParis();
    };
  }
  if (strategieChoisie && !triHoraire) {
    const now = Date.now();
    const aVenir = L.filter(p => p.statut === "en_cours" && new Date(p.debut).getTime() > now)
      .sort((a,b) => new Date(a.debut)-new Date(b.debut));
    const enCours = L.filter(p => p.statut === "a_regler" ||
      (p.statut === "en_cours" && !(new Date(p.debut).getTime() > now)))
      .sort((a,b) => new Date(b.debut)-new Date(a.debut));
    const termines = L.filter(p => !["en_cours","a_regler"].includes(p.statut))
      .sort((a,b) => new Date(b.debut)-new Date(a.debut));
    const parties = [["À venir",aVenir],["En cours ou à régler",enCours],["Terminés",termines]];
    let compteur = 0;
    document.getElementById("liste-paris").innerHTML = L.length ? parties.map(([titre,paris]) => {
      const restant = Math.max(0, limite-compteur), visibles = paris.slice(0,restant);
      compteur += visibles.length;
      return `<h3 class="groupe-paris">${titre} (${paris.length})</h3>` +
        (visibles.length ? visibles.map(carteParis).join("") : (paris.length ? "" : '<p class="aide">Aucun pour le moment.</p>'));
    }).join("") : '<div class="vide">Aucun pari pour cette stratégie et ces filtres.</div>';
  } else {
    document.getElementById("liste-paris").innerHTML = L.length ? L.slice(0,limite).map(carteParis).join("")
      : '<div class="vide">Aucun pari pour ces filtres.</div>';
  }
  plus.style.display = L.length > limite ? "" : "none";
  plus.onclick = () => { limite += 50; rendreParis(); };
}
for(const id of ['paris-horaire','paris-tri']) document.getElementById(id).onchange=()=>{limite=50;rendreParis();};
// Bandeau de santé : âge du dernier relevé et étapes en panne (une étape désactivée n'est pas une panne).
// Santé du système : une seule lecture pour le bandeau de Paris et la page Santé.
function diagnosticSante(maintenant=Date.now()) {
  const dc = (D.etat||{}).dernier_cycle || {};
  const etapes = Object.entries(dc.etapes || {}).filter(([,v]) => !v.desactive);
  const pannes = etapes.filter(([,v]) => !v.ok).map(([k]) => k.replace(/^resultats_/,"").replace(/_direct$/,""));
  const mineures = etapes.filter(([,v]) => v.ok && v.degrade).length;
  const t = new Date(dc.fin || dc.debut || "").getTime();
  const age = Number.isFinite(t) ? Math.max(0, Math.round((maintenant-t)/60000)) : null;
  const depuis = age == null ? "" : age < 1 ? "à l’instant" : age < 60 ? `il y a ${age} min` : `il y a ${Math.floor(age/60)} h ${String(age%60).padStart(2,"0")}`;
  const [niveau,texte] = age == null ? ["alerte","Pas encore de relevé"]
    : pannes.length ? ["panne",`En panne : ${pannes.join(", ")} · relevé ${depuis}`]
    : age > 60 ? ["panne",`Relevés arrêtés · dernier ${depuis}`]
    : age > 15 ? ["alerte",`Relevés en retard · dernier ${depuis}`]
    : ["ok",`Tout fonctionne · relevé ${depuis}`];
  return {dc, niveau, texte, mineures, age, depuis};
}
function rendreSanteParis(maintenant=Date.now()) {
  const {niveau, texte, mineures} = diagnosticSante(maintenant);
  const b = document.getElementById("paris-sante");
  b.className = "paris-sante sante-"+niveau;
  b.innerHTML = `<span class="sante-point" aria-hidden="true"></span><span class="sante-texte">${e(texte)}</span>`+
    `<span class="sante-suite">${mineures ? mineures+" alerte"+(mineures>1?"s":"")+" mineure"+(mineures>1?"s":"") : "Détails"} ›</span>`;
  b.onclick = () => { ouvrir("controle"); window.scrollTo(0,0); };
}
rendreSanteParis();
rendreParis();

// --- Bilan, paris uniques : chaque cote française comptée une fois, par écart, par cote et par sport
const BU_PERIODES = [["7","7 j"],["30","30 j"],["","Tout"]];
let periodeBU = "";
const NOMS_ECART = {A:"A · 2 à 3 %",B:"B · 3 à 4 %",C:"C · 4 à 5 %",D:"D · 5 à 7 %",E:"E · 7 % et +",X:"X · cote > 10"};
const statsBU = L => {
  const net = L.reduce((s,p) => s+p.gain, 0), mises = L.reduce((s,p) => s+(p.mise ?? 10), 0);
  const gagnes = L.filter(p => ["gagne","demi_gagne"].includes(p.statut)).length;
  return {n:L.length, net, mises, roi:mises ? net/mises : null, reussite:L.length ? gagnes/L.length : null};
};
const pctEntier = x => x==null ? "—" : Math.round(100*x)+" %";
function tableBU(groupes) {
  const lignes = groupes.map(([nom,L]) => ({nom, ...statsBU(L)})).filter(r => r.n);
  if (!lignes.length) return '<p class="aide">Aucun pari réglé sur cette période.</p>';
  const eligibles = lignes.filter(r => r.n >= 50);
  const meilleur = eligibles.length ? eligibles.reduce((a,b) => b.roi > a.roi ? b : a) : null;
  return `<div class="bu-ligne bu-entete"><span></span><span>Paris</span><span>Réuss.</span><span>Net</span><span>ROI</span></div>` +
    lignes.map(r => `<div class="bu-ligne"><span>${e(r.nom)}${r===meilleur ? ' <b class="bu-etoile" title="Meilleur ROI, 50 paris ou plus">★</b>' : ""}</span>
<span>${r.n}</span><span>${pctEntier(r.reussite)}</span><span class="${signe(r.net)}">${eurC(r.net)}</span><b class="${signe(r.net)}">${pct(r.roi)}</b></div>`).join("");
}
function rendreBilanUniques(maintenant=Date.now()) {
  const depuis = maintenant - Number(periodeBU)*86400000;
  const L = fiches.filter(p => p.unique_bilan && p.gain != null &&
    (!periodeBU || Date.parse(p.regle_le || p.debut || p.detecte) >= depuis));
  const periodes = document.getElementById("bu-periodes");
  periodes.innerHTML = BU_PERIODES.map(([v,t]) => `<button type="button" data-periode="${v}" aria-pressed="${v===periodeBU}">${t}</button>`).join("");
  periodes.onclick = ev => {
    const b = ev.target?.closest?.("button[data-periode]");
    if (b) { periodeBU = b.dataset.periode; rendreBilanUniques(); }
  };
  const s = statsBU(L);
  document.getElementById("bu-kpis").innerHTML = [["Gain net",eur(s.net),signe(s.net)],["ROI",pct(s.roi),signe(s.net)],
    ["Réussite",pctEntier(s.reussite),""]].map(([t,v,c]) => `<div><span>${t}</span><b class="${c}">${v}</b></div>`).join("");
  document.getElementById("bu-note").textContent =
    `${s.n} paris réglés · mise ${Math.round(s.mises).toLocaleString("fr-FR")} € · chaque cote française comptée une fois`;
  document.getElementById("bu-ecart").innerHTML = tableBU(Object.entries(NOMS_ECART).map(([k,nom]) => [nom, L.filter(p => p.simulation===k)]));
  document.getElementById("bu-cote").innerHTML = tableBU((D.tranches || []).map(t => [t, L.filter(p => p.tranche===t)]));
  const parSport = new Map();
  for (const p of L) parSport.set(p.sport, [...(parSport.get(p.sport) || []), p]);
  const sports = [...parSport].sort((a,b) => b[1].length-a[1].length);
  const autres = sports.slice(5).flatMap(([,l]) => l);
  document.getElementById("bu-sport").innerHTML = tableBU([...sports.slice(0,5).map(([sp,l]) => [nomSport(sp),l]),
    ...(autres.length ? [["Autres",autres]] : [])]);
}
rendreBilanUniques();
document.getElementById("voir-chatgpt").onclick = () => {
  strategieChoisie = null;
  document.getElementById("f-q").value = "";
  for (const id of Object.keys(FILTRES)) document.getElementById("f-" + id).value = "";
  document.getElementById("f-sim").value = "ChatGPT";
  limite = 50;
  rendreParis();
  ouvrir("paris");
};
document.getElementById("voir-gemini").onclick = () => {
  strategieChoisie = null;
  document.getElementById("f-q").value = "";
  for (const id of Object.keys(FILTRES)) document.getElementById("f-" + id).value = "";
  document.getElementById("f-sim").value = "Gemini Argon";
  limite = 50;
  rendreParis();
  ouvrir("paris");
};
document.getElementById("voir-jules").onclick = () => {
  strategieChoisie = null;
  document.getElementById("f-q").value = "";
  for (const id of Object.keys(FILTRES)) document.getElementById("f-" + id).value = "";
  document.getElementById("f-sim").value = "JULES EDGE";
  limite = 50;
  rendreParis();
  ouvrir("paris");
};
document.getElementById("voir-eden").onclick = () => {
  strategieChoisie = null;
  document.getElementById("f-q").value = "";
  for (const id of Object.keys(FILTRES)) document.getElementById("f-" + id).value = "";
  document.getElementById("f-sim").value = "Eden";
  limite = 50;
  rendreParis();
  ouvrir("paris");
};
document.getElementById("voir-jules-v2").onclick = () => {
  strategieChoisie = null;
  document.getElementById("f-q").value = "";
  for (const id of Object.keys(FILTRES)) document.getElementById("f-" + id).value = "";
  document.getElementById("f-sim").value = "JULES EDGE v2";
  limite = 50;
  rendreParis();
  ouvrir("paris");
};

// --- Segments : les groupes de paris qui marchent, avec ce qui relève de la chance
let triSeg = "roi";
const TRIS = {roi: "Meilleur ROI", reussite: "Réussite au-dessus de l'attendu"};
const verdict = s => (s.sigma_fiable === true && s.ecart_sigma >= 2 && (s.clv_moyenne || 0) > 0.01) ? ["À confirmer", "en_cours"]
  : (s.roi > 0 && (s.clv_moyenne || 0) > 0) ? ["Piste", "en_cours"]
  : s.roi > 0 ? ["CLV à vérifier", "a_regler"] : ["Perdant", "perdu"];
const limitesSigma = s => (s.sigma_limites || []).map(k => ({effectif_faible:"moins de 30 paris",
  tickets_meme_evenement:"tickets sur les mêmes matchs",reglements_non_binaires:"demi-règlements ou remboursements",
  attendus_extremes:"probabilités extrêmes"})[k]).filter(Boolean).join(" · ");
const nomSeg = s => [s.tranche && "Cotes " + s.tranche, s.bookmaker, s.sport && s.sport.replace("_", " "), s.reference && "Réf. " + s.reference]
  .filter(Boolean).join(" · ");
const dansSeg = s => x => (!s.tranche || x[9] === s.tranche) && (!s.bookmaker || x[2] === s.bookmaker) && (!s.sport || x[10] === s.sport) && (!s.reference || x[11] === s.reference);
const aVenir = s => (D.paris_a_venir_segments || []).filter(x => new Date(x[8]) > Date.now()).filter(dansSeg(s));
function rendreSegments() {
  document.getElementById("puces-seg").innerHTML = Object.entries(TRIS).map(([k, v]) =>
    `<button data-t="${k}" class="${k===triSeg?"actif":""}">${v}</button>`).join("");
  document.querySelectorAll("#puces-seg button").forEach(b => b.onclick = () => { triSeg = b.dataset.t; rendreSegments(); });
  const L = (D.segments || []).filter(s => triSeg === "roi" ? s.roi > 0 : s.ecart_sigma > 0)
    .sort((a, b) => triSeg === "roi" ? b.roi - a.roi : b.ecart_sigma - a.ecart_sigma).slice(0, 40);
  document.getElementById("seg-quoi").textContent = triSeg === "roi"
    ? "Segments au ROI positif (paris uniques réglés), du meilleur au moins bon."
    : "Segments qui gagnent plus souvent que la cote ne le prévoit, du plus net au moins net.";
  document.getElementById("liste-segments").innerHTML = L.length ? L.map((s, i) => {
    const [v, c] = verdict(s);
    return `<details class="ligne-detail ligne-segment" id="segment-${D.segments.indexOf(s)}" data-i="${D.segments.indexOf(s)}"><summary><span class="ligne-nom">${e(nomSeg(s))}</span><span class="ligne-volume">${s.n} p.</span><span class="ligne-roi ${signe(s.roi)}">${pctC(s.roi)}</span><b class="ligne-valeur ${signe(s.gains)}">${eurC(s.gains)}</b></summary><div class="ligne-corps"><article class="carte seg">
<div class="l1"><span class="match">${e(nomSeg(s))}</span><span class="badge ${c}">${v}</span></div>
<div class="l3"><span>${s.n} paris${Number.isInteger(s.evenements) ? ` · ${s.evenements} matchs` : ""} · <b>${s.gagnes} gagnés = ${Math.round(100 * s.gagnes / s.n)} %</b></span>
<span><i>attendu</i> ${Math.round(100 * s.attendus / s.n)} %</span>
<span><i>écart</i> <span class="${signe(s.ecart_sigma)}">${s.ecart_sigma > 0 ? "+" : ""}${String(s.ecart_sigma).replace(".", ",")}</span></span></div>
<p class="aide">${s.sigma_fiable === true ? "Sigma descriptif sous hypothèse d'indépendance ; essais multiples non corrigés." : `Sigma fragile${limitesSigma(s) ? " : " + e(limitesSigma(s)) : " : conditions statistiques non vérifiées"}.`}</p>
<div class="l4"><span>ROI <b class="${signe(s.roi)}">${pctC(s.roi)}</b> (${eurC(s.gains)})</span>
<span>CLV <span class="${signe(s.clv_moyenne)}">${pctC(s.clv_moyenne)}</span> <i>${s.clv_n}/${s.n}</i></span>
${(n => n ? `<span class="badge en_cours">${n} à venir</span>` : "")(aVenir(s).length)}</div></article></div></details>`;
  }).join("") : `<div class="vide">Aucun segment pour l'instant.</div>`;
  // toucher un segment déroule ses paris à venir, puis ses paris réglés (ceux qu'il compte), du plus récent au plus ancien
  document.querySelectorAll("#liste-segments > details").forEach(d => d.ontoggle = () => {
    if (!d.open || d.querySelector(".seg-paris")) return;
    const a = d.querySelector(".seg");
    const s = D.segments[Number(d.dataset.i)];
    const L = (D.paris_segments || []).filter(dansSeg(s)), V = aVenir(s);
    a.insertAdjacentHTML("beforeend", `<div class="seg-paris">
<div class="sp-titre">À venir (${V.length})</div>${V.length ? V.map(x => `<div class="sp">
<div class="l1"><span class="match">${e(x[0])}</span>${horairePari({debut:x[8]})}</div>
<div class="l3"><span>${e(x[1])}</span><span><b>${e(x[2])} ${cote(x[3])}</b> <i>juste${cote(x[4])}</i></span>
<span><i>écart</i> <span class="${signe(x[5])}">${pct(x[5])}</span></span>
<span>CLV <span class="${signe(x[7])}">${pct(x[7])}</span> <i>pour l'instant</i></span></div></div>`).join("")
  : `<div class="sp"><i>Aucun pari à venir dans ce segment pour l'instant.</i></div>`}
<div class="sp-titre">Réglés (${L.length})</div>${L.map(x => `<div class="sp">
<div class="l1"><span class="match">${e(x[0])}</span>${horairePari({debut:x[8]})}</div>
<div class="l3"><span>${e(x[1])}</span><span><b>${e(x[2])} ${cote(x[3])}</b> <i>juste${cote(x[4])}</i></span>
<span class="badge ${x[5]}">${STATUTS[x[5]] || x[5]}</span><b class="${signe(x[6])}">${eur(x[6])}</b>
<span>CLV <span class="${signe(x[7])}">${pct(x[7])}</span></span></div></div>`).join("")}</div>`);
  });
}
rendreSegments();

// --- À régler
const manUniques = new Map();
D.paris.filter(p => p.a_regler).forEach(p => {
  const cle = JSON.stringify([p.match_id,p.marche,p.periode,p.ligne,p.issue,p.joueur]);
  if (!manUniques.has(cle)) manUniques.set(cle,p);
});
const man = [...manUniques.values()];
const jr = (D.etat||{}).dernier_cycle_reglement || {}, diagnostics = ((jr.resultats||{}).non_regles||[]);
const dr = new Map(diagnostics.map(x => [x.match+"|"+x.sport+"|"+x.debut,x]));
const groupesReglement = new Map();
man.forEach(p => {
  const cle = p.sport+"|"+p.domicile+"|"+p.exterieur+"|"+p.debut;
  if (!groupesReglement.has(cle)) groupesReglement.set(cle, []);
  groupesReglement.get(cle).push(p);
});
const panneAP = Object.values(jr.etapes||{}).some(x => (x.erreurs||[]).some(t => /suspended/i.test(t)));
const prop = jr.propline || {};
document.getElementById("reglement-etat").innerHTML =
  `<p>${man.length} sélections sur ${groupesReglement.size} affiches.</p>` +
  (jr.debut ? `<p>Dernière recherche : ${quand(jr.debut)}.${Number.isInteger(jr.resultats?.paris_regles) ? ` ${jr.resultats.paris_regles} enregistrements réglés à ce passage.` : ""}</p>` : "") +
  (panneAP ? `<p>API-Sports : compte suspendu. Les autres sources continuent. Les quatre clés The Odds API partagent la même couverture ; elles ne couvrent pas toutes les compétitions ni les mi-temps.</p>` : "") +
  (prop.configure ? `<p>Prop-Line : ${prop.requetes_scores||0} appel(s) scores à ce passage, ${prop.matchs_valides||0} affiche(s) validée(s)${Number.isFinite(prop.quota_restant) ? " · "+prop.quota_restant+" requêtes restantes aujourd’hui" : ""}. ${(prop.erreurs||[]).length ? "Lecture dégradée : "+(prop.erreurs||[]).map(e).join(" ; ")+"." : "Les compétitions et périodes sans couverture restent en attente."}</p>` :
    (Object.prototype.hasOwnProperty.call(jr,"propline") ? `<p>Prop-Line : clé absente. Les autres sources continuent.</p>` : ""));
document.getElementById("liste-regler").innerHTML = man.length ? [...groupesReglement.values()].map(ps => {
  const p = ps[0], d = dr.get(p.domicile+" – "+p.exterieur+"|"+p.sport+"|"+p.debut);
  const validation = d && d.validation_apres;
  return `<details class="carte"><summary>${e(p.domicile)} – ${e(p.exterieur)} · ${ps.length} sélection${ps.length>1?"s":""}${horairePari(p)}</summary>
<div class="l4"><span>${quand(p.debut)}</span><span>${e(p.ligue||"")}</span></div>
<p class="aide">${e(d ? d.raison : "Recherche automatique en cours")}${validation ? " · nouvelle validation possible après "+quand(validation) : ""}.</p>
${ps.map(x => `<div class="l4"><span>${e(x.bookmaker)} · ${e(x.pari)}</span><span>${e(x.reference)}</span></div>`).join("")}</details>`;
}).join("") : `<div class="vide">Aucun résultat en attente.</div>`;
document.getElementById("copier").style.display = man.length ? "" : "none";
document.getElementById("copier").onclick = () => {
  const txt = "Paris à régler (cotes-value) :\n" + man.map(p =>
    `- [${p.match_id}] ${p.domicile} – ${p.exterieur} (${p.sport}, ${p.ligue||""}, ${new Date(p.debut).toLocaleString("fr-FR")}) : ${p.pari}`).join("\n");
  navigator.clipboard.writeText(txt).then(() => { const b = document.getElementById("copier"); b.textContent = "Copié ✓";
    setTimeout(() => b.textContent = "Copier la liste", 2000); });
};

// --- Contrôle
const CTL = {non_conforme:"Non conformes", a_verifier:"À vérifier", conforme:"Conformes"};
const cg = (D.controle||{}).groupes || [], cm = (D.controle||{}).matchs || [];
const nbc = s => cg.filter(g => g.statut===s).length;
document.getElementById("ctl-resume").innerHTML = [["Conformes", nbc("conforme")], ["À vérifier", nbc("a_verifier")],
  ["Non conformes", nbc("non_conforme")], ["Matchs mal associés ?", cm.length]].map(([a,b]) => `<div>${a}<b>${b}</b></div>`).join("");
let ctlVue = nbc("non_conforme") ? "non_conforme" : "a_verifier";
const num = x => x==null ? "—" : Number(x).toFixed(2).replace(".", ",");
function rendreControle() {
  document.getElementById("ctl-puces").innerHTML = [...Object.entries(CTL), ["matchs","Matchs"]].map(([k,v]) =>
    `<button data-v="${k}" class="${k===ctlVue?"actif":""}">${v}</button>`).join("");
  document.querySelectorAll("#ctl-puces button").forEach(b => b.onclick = () => { ctlVue = b.dataset.v; rendreControle(); });
  let html;
  if (ctlVue === "matchs") {
    html = cm.length ? cm.map(m => `<article class="carte"><div class="l1"><span class="match">${e(m.match)}</span>
<span>${e(m.bookmaker)}</span></div><div class="l4">Rapport médian ${num(m.rapport_median)} sur tous les marchés du match</div></article>`).join("")
      : `<div class="vide">Aucun match suspect au dernier passage.</div>`;
  } else {
    const L = cg.filter(g => g.statut === ctlVue).slice(0, 300);
    html = L.length ? L.map(g => `<article class="carte">
<div class="l1"><span class="match">${e(g.bookmaker)} · ${e(g.sport)} · ${e(g.marche)} ${e(g.periode)}</span>
<span class="quand">${g.n} mesure${g.n>1?"s":""}</span></div>
<div class="l2">« ${e(g.type)} »</div>
<div class="l4"><span>Rapport médian <b>${num(g.mediane)}</b></span><span>au-dessus de 1,12 : ${g.part_haute==null?"—":Math.round(100*g.part_haute)+" %"}</span>
${g.dispersion_autre_periode!=null && g.dispersion_autre_periode < 0.8*g.dispersion ? `<b class="neg">suit mieux l'autre période (temps réglementaire / prolongation)</b>` : ""}</div>
${(g.exemples||[]).map(x => `<div class="l4"><span>${e(x.match)}</span><span>${e(x.libelle)}${x.ligne!=null?" ["+e(x.ligne)+"]":""} ${e(x.issue)}</span>
<span>${cote(x.cote)} / ${e(x.reference)}${cote(x.cote_juste)}</span></div>`).join("")}</article>`).join("")
      : `<div class="vide">Aucun intitulé dans cette catégorie.</div>`;
  }
  document.getElementById("ctl-liste").innerHTML = html;
}
rendreControle();

// --- Santé : état des automatismes et des sources, en mots simples
const SOURCES_COTES = [["pinnacle","Pinnacle"],["polymarket","Polymarket"],["netbet","NetBet"],["winamax_direct","Winamax"],
  ["betclic_direct","Betclic"],["unibet_direct","Unibet"],["pmu_direct","PMU"],["olybet","OlyBet"],["smarkets","Smarkets"]];
const SOURCES_RESULTATS = [["espn","ESPN"],["flashscore","Flashscore"],["livescore","LiveScore"],["nhl","NHL officiel"],
  ["theodds","The Odds API"],["propline","Propline"]];
const MOTS_SANTE = {ok:"✓ OK", alerte:"! Alerte", panne:"✗ En panne"};
const ligneSante = (nom, detail, niveau) => `<div class="sante-ligne"><div><b>${e(nom)}</b><small>${e(detail)}</small></div>`+
  `<span class="sante-mot sante-mot-${niveau}">${MOTS_SANTE[niveau]}</span></div>`;
function detailEtape(v) {
  if (!v) return "Pas de lecture au dernier relevé";
  if (!v.ok) return "Arrêtée au dernier passage";
  const err = Array.isArray(v.erreurs) ? v.erreurs : [];
  if (v.degrade && err.length) {
    const http = err.map(t => /HTTP (\d{3})/.exec(t)?.[1]).filter(Boolean);
    if (http.length === err.length) return `Refus (${[...new Set(http)].join(", ")}) sur ${err.length} requête${err.length>1?"s":""} · reprise automatique`;
    if (err.some(t => /budget/i.test(t))) return "Lecture partielle : limite de temps atteinte";
    if (err.some(t => /bid\/ask/i.test(t))) return "Prix invalides sur quelques marchés, ignorés";
    return err[0] + (err.length>1 ? ` (+${err.length-1})` : "");
  }
  return v.degrade ? "Lecture partielle" : v.cache ? "Données gardées en mémoire" : "Lu normalement";
}
const niveauEtape = v => !v || !v.ok ? "panne" : v.degrade ? "alerte" : "ok";
const PIRE = ["ok","alerte","panne"];
function rendreSante(maintenant=Date.now()) {
  const {dc, niveau, texte, mineures, age} = diagnosticSante(maintenant);
  const etapes = dc.etapes || {}, jr = (D.etat||{}).dernier_cycle_reglement || {};
  const cotes = dc.cotes?.francaises, duree = dc.debut && dc.fin ? Math.round((new Date(dc.fin)-new Date(dc.debut))/1000) : null;
  const g = document.getElementById("sante-global");
  g.className = "carte sante-global sante-"+niveau;
  g.innerHTML = `<div class="sante-global-titre"><span class="sante-point" aria-hidden="true"></span><b>${e(texte)}</b></div>`+
    `<p class="aide">${[cotes ? cotes.toLocaleString("fr-FR")+" cotes françaises" : "", duree != null ? duree+" s" : "",
      mineures ? mineures+" alerte"+(mineures>1?"s":"")+" mineure"+(mineures>1?"s":"")+(niveau==="ok" ? " sans effet sur les paris" : "") : ""].filter(Boolean).join(" · ")}</p>`;
  const ageReglement = jr.debut ? Math.round((maintenant-new Date(jr.fin || jr.debut))/60000) : null;
  const nReglements = jr.resultats?.paris_regles;
  document.getElementById("sante-auto").innerHTML =
    ligneSante("Collecte et comparaison", dc.debut ? `Dernier relevé ${hm(dc.debut)}${duree != null ? " · "+duree+" s" : ""} · toutes les 5 min environ` : "Aucun relevé", age == null ? "panne" : age > 60 ? "panne" : age > 15 ? "alerte" : "ok") +
    ligneSante("Règlement des paris", jr.debut ? `Dernier passage ${quand(jr.debut)}${Number.isInteger(nReglements) ? " · "+nReglements+" enregistrement"+(nReglements>1?"s":"")+" réglé"+(nReglements>1?"s":"") : ""}` : "Aucun passage enregistré",
      ageReglement == null ? "alerte" : ageReglement > 720 ? "panne" : ageReglement > 180 ? "alerte" : "ok");
  const secours = dc.pinnacle_secours;
  document.getElementById("sante-cotes").innerHTML = SOURCES_COTES.filter(([k]) => etapes[k]).map(([k,nom]) =>
    ligneSante(nom, k === "smarkets" && !etapes[k].degrade ? "Lu · affiché seulement, hors consensus" : detailEtape(etapes[k]), niveauEtape(etapes[k]))
      + (k === "pinnacle" && secours ? ligneSante("Pinnacle · secours (pinnodds, PinBook)", secours.lignes ? `${secours.lignes} cotes · ${(secours.sports || []).length} sport${(secours.sports || []).length > 1 ? "s" : ""}` : secours.pause ? "En pause entre deux lectures" : (secours.erreurs || [])[0] || "Aucune cote reprise", secours.lignes ? "alerte" : "panne") : "")).join("")
    || '<p class="aide sante-vide">Aucune lecture enregistrée.</p>';
  const parSource = new Map();
  for (const [k,v] of Object.entries(jr.etapes || {})) {
    const m = /^resultats_([^_]+(?:-[^_]+)*)(?:_|$)/.exec(k);
    if (m) parSource.set(m[1], [...(parSource.get(m[1]) || []), v]);
  }
  const reglesPar = jr.resultats?.sources_reglement || {};
  document.getElementById("sante-resultats").innerHTML = SOURCES_RESULTATS.filter(([k]) => parSource.has(k)).map(([k,nom]) => {
    const vs = parSource.get(k), pire = vs.map(niveauEtape).reduce((a,b) => PIRE.indexOf(b) > PIRE.indexOf(a) ? b : a, "ok");
    const n = reglesPar[k];
    return ligneSante(nom, n ? `${n} enregistrement${n>1?"s":""} réglé${n>1?"s":""} au dernier passage` : pire === "ok" ? "Lu normalement" : detailEtape(vs.find(v => niveauEtape(v) === pire)), pire);
  }).join("") || '<p class="aide sante-vide">Aucun passage de règlement enregistré.</p>';
  const attente = jr.resultats?.paris_en_attente;
  document.getElementById("sante-attente").textContent = Number.isInteger(attente) ? `${attente} paris attendent un résultat.` : "";
  document.getElementById("sante-saisie").textContent = `Matchs à saisir à la main${man.length ? " ("+groupesReglement.size+")" : ""} ›`;
}
rendreSante();

// Famille publiée une fois : aucun nouveau classement choisi selon le test final.
// Comparaison complète : même ligne de données pour le tableau et le graphique.
const STRAT_PERIODES = {futur:"Depuis le lancement", ensemble:"Historique 7–13 oct.",
  construction:"7–10 oct.", validation:"11–12 oct.", test:"13 oct."};
const courbesMasquees = new Set();
const COULEURS_COMPARATEURS = {"Claude (rejeu)":"var(--courbe-claude,#2675ce)", "ChatGPT v1 (rejeu)":"var(--courbe-chatgpt,#d15b13)",
  "Gemini Argon v1 (rejeu)":"var(--courbe-gemini,#16884c)", "JULES EDGE v1 (rejeu)":"var(--courbe-jules1,#b04baf)",
  "JULES EDGE v2 (rejeu)":"var(--courbe-jules2,#865fe0)", "Eden (rejeu)":"var(--courbe-eden,#1a7a6d)", "M3 (rejeu)":"var(--courbe-m3,#16838b)", "Convergence ≥ 2":"var(--courbe-convergence2,#c44862)", "Claude 1/match · max 10/j":"var(--courbe-claudeprudent,#b47b00)", "Convergence ≥ 3 hors M3":"var(--courbe-convergence3,#d13f8c)", "M3 · Max 3/match":"var(--courbe-m3structure,#7f9225)"};
function rendreCourbesStrategies(rows) {
  const legend = document.getElementById("strategies-legende"), svg = document.getElementById("strategies-courbes");
  const toutes = rows.map(r => ({...r, points:D.laboratoire.navigation?.courbes?.[r.id]?.[periodeStrategies] || []}));
  const nomsCourts = {"M3 (rejeu)":"M3", "Convergence ≥ 2":"Conv. ≥ 2",
    "JULES EDGE v1 (rejeu)":"Jules v1", "JULES EDGE v2 (rejeu)":"Jules v2",
    "ChatGPT v1 (rejeu)":"ChatGPT v1", "Gemini Argon v1 (rejeu)":"Gemini v1", "Eden (rejeu)":"Eden"};
  legend.innerHTML = toutes.map(r => {
    const gain = r.points.length ? r.points.at(-1)[1] : (r.stats?.regles ? r.stats.gain : null);
    return `<button data-courbe="${e(r.id)}" aria-label="${e(r.nom)} : ${e(eurC(gain))}" aria-pressed="${!courbesMasquees.has(r.id)}" class="${courbesMasquees.has(r.id) ? "" : "actif"}"><span style="color:${COULEURS_COMPARATEURS[r.id] || "var(--texte)"}">●</span> ${e(D.variantes?.[r.id]?.court || nomsCourts[r.id] || r.nom)} ${e(eurC(gain))}</button>`;
  }).join("");
  const masquerTout = rows.some(r => !courbesMasquees.has(r.id));
  if (rows.length) legend.innerHTML += `<button id="strategies-tout">${masquerTout ? "Tout masquer" : "Tout afficher"}</button>`;
  for (const b of legend.querySelectorAll("button[data-courbe]")) b.onclick = () => {
    courbesMasquees.has(b.dataset.courbe) ? courbesMasquees.delete(b.dataset.courbe) : courbesMasquees.add(b.dataset.courbe);
    rendreCourbesStrategies(rows);
  };
  if (rows.length) document.getElementById("strategies-tout").onclick = () => {
    for (const r of rows) masquerTout ? courbesMasquees.add(r.id) : courbesMasquees.delete(r.id);
    rendreCourbesStrategies(rows);
  };
  const series = toutes.filter(r => !courbesMasquees.has(r.id));
  const points = series.flatMap(r => r.points);
  const vide = document.getElementById("strategies-courbes-vide");
  vide.textContent = !rows.length ? "Choisis toutes les références ou les comparateurs pour afficher leurs courbes."
    : !series.length ? "Toutes les courbes sont masquées. Touche une légende pour en afficher une."
    : !points.length ? "Aucun pari réglé sur cette période pour les courbes affichées." : "";
  svg.style.display = points.length ? "" : "none";
  if (!points.length) { svg.innerHTML=""; return; }
  const W=Math.max(320,Math.min(1100,svg.getBoundingClientRect?.().width || 640)),H=W<500?260:300,left=65,right=16,top=22,bottom=40;
  const debut=Math.min(...points.map(p => p[0]))-60, fin=Math.max(...points.map(p => p[0]))+60;
  const min=Math.min(0,...points.map(p => p[1])), max=Math.max(0,...points.map(p => p[1]));
  const st=Math.max(1,Math.ceil(pas(max-min || 10)));
  const lo=Math.floor(min/st)*st, hi=Math.max(lo+st,Math.ceil(max/st)*st);
  const x=t => left+(t-debut)/(fin-debut)*(W-left-right), y=g => top+(hi-g)/(hi-lo)*(H-top-bottom);
  const court = fin-debut-120 < 48*3600;
  const date=t => {
    const d=new Date(t*1000), jour=d.toLocaleDateString("fr-FR",{timeZone:"Europe/Paris",day:"2-digit",month:"2-digit"});
    if (!court) return jour;
    const heure=d.toLocaleTimeString("fr-FR",{timeZone:"Europe/Paris",hour:"2-digit",minute:"2-digit",hourCycle:"h23"});
    return jour+" "+heure.replace(":","h");
  };
  const niveaux=Array.from({length:Math.round((hi-lo)/st)+1},(_,i) => lo+i*st);
  const graduations=niveaux.map(g => `<line x1="${left}" y1="${y(g)}" x2="${W-right}" y2="${y(g)}" stroke="var(--ligne)"/><text x="${left-8}" y="${y(g)+6}" text-anchor="end" fill="var(--doux)" font-size="12">${e(eurC(g))}</text>`).join("");
  svg.setAttribute("viewBox",`0 0 ${W} ${H}`);
  svg.innerHTML = `<title>Gains cumulés — ${e(STRAT_PERIODES[periodeStrategies])}, 10 € fictifs par pari</title>${graduations}`+
    [debut,(debut+fin)/2,fin].map(t => `<text x="${x(t)}" y="${H-9}" text-anchor="${t===debut ? "start" : t===fin ? "end" : "middle"}" fill="var(--doux)" font-size="12">${date(t)}</text>`).join("")+
    series.filter(r => r.points.length).map((r,i) => {
      let path=`M ${x(debut)} ${y(0)}`;
      for (const [t,g] of r.points) path+=` H ${x(t)} V ${y(g)}`;
      path+=` H ${x(fin)}`;
      const dernier=r.points.at(-1)[1];
      return `<path data-serie="${e(r.id)}" d="${path}" fill="none" stroke="${COULEURS_COMPARATEURS[r.id] || "var(--texte)"}" stroke-width="2.5" vector-effect="non-scaling-stroke" ${r.id.includes("v2") ? 'stroke-dasharray="7 4"' : D.variantes?.[r.id] ? 'stroke-dasharray="3 3"' : ""}><title>${e(r.nom)} : ${e(eur(dernier))} · ${r.points.length} réglés</title></path>`;
    }).join("");
}
let periodeStrategies = "futur";
function rendreStrategies() {
  const lignesOuvertes=new Set([...document.querySelectorAll("#strategies-mobile > details[open]")].map(d=>d.id));
  const L = D.laboratoire;
  if (!L || (!L.resultats?.length && !Object.keys(L.comparateurs || {}).length)) {
    document.getElementById("strategies-quoi").textContent = "Aucune comparaison disponible.";
    return;
  }
  const pp = n => n == null ? "—" : pct(n/100);
  const bornes = n => String(n).replace(".",",");
  const futur = new Map((L.futur || []).map(r => [r.id,r]));
  // Règles numérotées par référence (Pinnacle 1, 2…) ; le détail reste dans la fiche.
  const numeros = {};
  let rows = (L.resultats || []).map(r => ({id:r.regle.id,
    nom:`${r.regle.reference} ${numeros[r.regle.reference] = (numeros[r.regle.reference] || 0) + 1}`, reference:r.regle.reference,
    detail:`Cotes ${bornes(r.regle.cote_min)}–${bornes(r.regle.cote_max)} · edge ≥ ${r.regle.edge_min*100} % · ≤ ${r.regle.avance_max_h} h`,
    graphe:`${bornes(r.regle.cote_min)}–${bornes(r.regle.cote_max)} · ≥ ${r.regle.edge_min*100} % · ${r.regle.avance_max_h} h`,
    stats:periodeStrategies === "futur" ? futur.get(r.regle.id) : r[periodeStrategies]}));
  for (const [id,per] of Object.entries(L.comparateurs || {})) {
    const variante = D.variantes?.[id];
    if(variante?.prospectif_seulement && periodeStrategies!=="futur") continue;
    const nomComp = variante ? variante.nom : id.startsWith("Convergence") ? "Convergence ≥ 2 stratégies"
    : id.startsWith("JULES EDGE v2") ? "JULES EDGE V2"
    : id.startsWith("JULES") ? "JULES EDGE V1"
    : id.startsWith("Claude") ? "Claude"
      : id.startsWith("M3") ? "M3 · MultiSport"
      : id.startsWith("Gemini") ? "Gemini Argon V1"
      : id.startsWith("Eden") ? "Eden"
      : "ChatGPT V1";
    const detailComp = variante ? (periodeStrategies === "futur"
      ? `Depuis le ${quand(variante.debut)} · ${variante.regles}`
      : `Rejeu exploratoire après audit · ${variante.regles}`) : periodeStrategies === "futur"
      ? (id.startsWith("Convergence") ? "Depuis le 15/10 à 01 h · 2 familles minimum · M3 incluse · Eden à partir du 19/10"
         : id.startsWith("JULES EDGE v2") ? "Depuis le 15/10 à 00 h 30 · multi-réf. · max 8/j"
         : id.startsWith("JULES") ? "Depuis le 14/10 à 23 h 04 · 1 pari/match · max 6/j"
         : id.startsWith("M3") ? "Depuis le 15/10 · simulation, 10 € / sélection"
         : id.startsWith("Gemini") ? "Multi-réf. adaptative · 1 pari/match · max 8/j"
         : id.startsWith("Eden") ? "Depuis le 19/10 à 20 h · Pinnacle et Polymarket · 1,30–2,00"
         : "Nouvelles prises officielles depuis le 14/10 à 14 h")
      : (id.startsWith("Convergence") ? "Rejeu exploratoire · même prise, prix et instant · 2 familles minimum"
         : id.startsWith("JULES EDGE v2") ? "Rejeu a posteriori · multi-réf. · 1,30–2,80 · edge 2,5–12 % · max 8/j"
         : id.startsWith("JULES") ? "Rejeu a posteriori · Pinnacle · 1,30–2,50 · edge 3–12 % · max 6/j"
         : id.startsWith("M3") ? "Optimisation a posteriori · 3 sports · 1,30–3,00 · 2–12 % d’edge"
         : id.startsWith("Gemini") ? "Rejeu hypothétique · Pin ≤ 2,15 / Bet+Poly ≤ 2,60 · edge ≥ 2,5 %"
         : id.startsWith("Eden") ? "Rejeu descriptif · Pinnacle et Polymarket · 1,30–2,00 · edge 2–12 % · 30 min–24 h"
         : "Rejeu hypothétique · mêmes dates que la famille");
    rows.push({id, nom:nomComp, reference:"comparateurs", detail:detailComp,
      graphe:"Comparateur", stats:periodeStrategies === "futur" ? L.comparateurs_futur?.[id] : per[periodeStrategies]});
  }
  rows = rows.filter(r => r.stats).map(r => ({...r, reussite:r.stats.regles ? 100*r.stats.gagnes/r.stats.regles : null}));
  // Courbe d'une règle reconstituée depuis ses paris réglés (les comparateurs ont la leur, calculée au relevé).
  const courbeDe = r => L.navigation?.courbes?.[r.id]?.[periodeStrategies] || (() => {
    let total = 0;
    return (L.navigation?.selections?.[r.id]?.[periodeStrategies] || []).map(id => L.navigation.paris[id])
      .filter(p => p && p.gain != null && p.regle_le).sort((a,b) => Date.parse(a.regle_le)-Date.parse(b.regle_le))
      .map(p => [Math.floor(Date.parse(p.regle_le)/1000), total = Math.round((total+p.gain)*100)/100]);
  })();
  // ★ : meilleur ROI parmi les stratégies d'au moins 30 paris réglés sur la période.
  const eligibles = rows.filter(r => r.stats.regles >= 30 && r.stats.roi != null);
  const meilleure = eligibles.length ? eligibles.reduce((a,b) => b.stats.roi > a.stats.roi ? b : a) : null;
  if (meilleure) meilleure.nomCourt = meilleure.nom + " ★";
  const ref = document.getElementById("strategies-ref").value;
  if (ref) rows = rows.filter(r => r.reference === ref);
  const tri = document.getElementById("strategies-tri").value;
  rows.sort((a,b) => {
    if (tri === "nom") return a.nom.localeCompare(b.nom,"fr") || a.id.localeCompare(b.id);
    const av = tri === "reussite" ? a.reussite : a.stats[tri], bv = tri === "reussite" ? b.reussite : b.stats[tri];
    return (bv ?? -Infinity) - (av ?? -Infinity) || a.id.localeCompare(b.id);
  });
  const boutonPeriode = ([id,nom]) => `<button data-p="${id}" class="${periodeStrategies===id ? "actif" : ""}" aria-pressed="${periodeStrategies===id}">${id==="futur" ? "Suivi prospectif" : nom}</button>`;
  document.getElementById("strategies-periodes").innerHTML = Object.entries(STRAT_PERIODES).slice(0,2).map(boutonPeriode).join("") +
    `<details class="periodes-detail"${!["futur","ensemble"].includes(periodeStrategies)?" open":""}><summary>Découper l’historique</summary><div>${Object.entries(STRAT_PERIODES).slice(2).map(boutonPeriode).join("")}</div></details>`;
  const contexte=document.getElementById("strategies-contexte");
  contexte.textContent=periodeStrategies==="futur" ? "Suivi prospectif" : "Rejeu historique";
  contexte.classList.toggle("historique",periodeStrategies!=="futur");
  for (const b of document.querySelectorAll("#strategies-periodes button")) b.onclick = () => { periodeStrategies=b.dataset.p; rendreStrategies(); };
  const edenPicks = L.eden_paris || [];
  document.getElementById("eden-picks-list").innerHTML = edenPicks.length
    ? edenPicks.map(p => `<article style="padding:8px 0;border-top:1px solid var(--ligne)">
       <b>${e(p.domicile)} – ${e(p.exterieur)}</b> <small>${e(p.sport)} · ${e(p.bookmaker)} (${e(p.reference)})</small>
       <div>${e(p.pari)} · cote ${cote(p.cote)} · edge ${pct(p.ecart)}</div>
       ${collectePari(p)}<small>${horairePari(p)} · ${e(p.statut)}${p.gain==null ? "" : " · "+eur(p.gain)}</small>
       </article>`).join("")
    : '<p class="aide">Aucune nouvelle sélection Eden depuis le 19/10 à 20 h (Paris).</p>';
  const gemPicks = L.gemini_paris || [];
  const suivis = L.suivis_prudents || {};
  const navPrudent = L.navigation?.paris || {};
  document.getElementById("prudentes-picks").innerHTML = Object.values(suivis.officiel || {}).map(v => {
    const picks = (v.ids || []).map(id => navPrudent[id]).filter(Boolean).slice(-20).reverse();
    return `<details><summary>${e(v.nom)} · ${v.stats.paris} prises · ${v.stats.regles} réglées</summary>` +
      (picks.length ? picks.map(p => `<article class="carte"><b>${e(p.domicile)} – ${e(p.exterieur)}</b>
       <div>${e(p.pari)} · ${e(p.bookmaker)} · ${cote(p.cote)}</div>${horairePari(p)}${collectePari(p)}<small>Prise ${quand(p.detecte)} · ${e(p.statut)}</small></article>`).join("")
       : '<p class="aide">Aucune prise depuis le lancement de cette variante.</p>') + '</details>';
  }).join("");
  document.getElementById("prudentes-reconstitution").innerHTML = Object.values(suivis.reconstitution_exploratoire || {}).map(v =>
    `<p><b>${e(v.nom)}</b> : ${v.stats.paris} prises, ${v.stats.regles} réglées, ${eur(v.stats.gain)} · ROI ${pct(v.stats.roi == null ? null : v.stats.roi/100)}</p>`).join("");
  document.getElementById("gemini-picks-list").innerHTML = gemPicks.length
    ? gemPicks.map(p => `<article style="padding:8px 0;border-top:1px solid var(--ligne)">
       <b>${e(p.domicile)} – ${e(p.exterieur)}</b> <small>${e(p.sport)} · ${e(p.bookmaker)} (${e(p.reference)})</small>
       <div>${e(p.pari)} · cote ${cote(p.cote)} · edge ${pct(p.ecart)}</div>
       ${collectePari(p)}<small>${horairePari(p)} · ${e(p.statut)}${p.gain==null ? "" : " · "+eur(p.gain)}</small>
       </article>`).join("")
    : '<p class="aide">Aucune nouvelle sélection Gemini Argon depuis son démarrage prospectif.</p>';
  const julesPicks = L.jules_paris || [];
  document.getElementById("jules-picks-list").innerHTML = julesPicks.length
    ? julesPicks.map(p => `<article style="padding:8px 0;border-top:1px solid var(--ligne)">
       <b>${e(p.domicile)} – ${e(p.exterieur)}</b> <small>${e(p.sport)} · ${e(p.bookmaker)}</small>
       <div>${e(p.pari)} · cote ${cote(p.cote)} · edge ${pct(p.ecart)}</div>
       ${collectePari(p)}<small>${horairePari(p)} · ${e(p.statut)}${p.gain==null ? "" : " · "+eur(p.gain)}</small>
       </article>`).join("")
    : '<p class="aide">Aucune nouvelle sélection JULES EDGE depuis sa publication du 14/10 à 23 h 04.</p>';
  const v2Picks = L.jules_v2_paris || [];
  document.getElementById("jules-v2-picks-list").innerHTML = v2Picks.length
    ? v2Picks.map(p => `<article style="padding:8px 0;border-top:1px solid var(--ligne)">
       <b>${e(p.domicile)} – ${e(p.exterieur)}</b> <small>${e(p.sport)} · ${e(p.bookmaker)} (${e(p.reference)})</small>
       <div>${e(p.pari)} · cote ${cote(p.cote)} · edge ${pct(p.ecart)}</div>
       ${collectePari(p)}<small>${horairePari(p)} · ${e(p.statut)}${p.gain==null ? "" : " · "+eur(p.gain)}</small>
       </article>`).join("")
    : '<p class="aide">Aucune nouvelle sélection JULES EDGE v2 depuis le lancement du 15/10 à 00 h 30.</p>';
  const picks = L.m3_paris || [];
  document.getElementById("m3-picks-list").innerHTML = picks.length
    ? picks.map(p => `<article style="padding:8px 0;border-top:1px solid var(--ligne)">
       <b>${e(p.domicile)} – ${e(p.exterieur)}</b> <small>${e(p.sport)} · ${e(p.bookmaker)}</small>
       <div>${e(p.pari)} · cote ${cote(p.cote)} · edge ${pct(p.ecart)}</div>
       ${collectePari(p)}<small>${horairePari(p)} · ${e(p.statut)}${p.gain==null ? "" : " · "+eur(p.gain)}</small>
       </article>`).join("")
    : '<p class="aide">Aucune nouvelle sélection M3 depuis son démarrage prospectif du 15 octobre.</p>';
  const active = rows.filter(r => r.stats.paris), reglees = rows.filter(r => r.stats.regles);
  document.getElementById("strategies-total").textContent = `${rows.length} stratégies · ${reglees.length} avec des règlements · résultats non cumulables.`;
  const descriptions = {
    futur:"Suivi depuis le lancement propre à chaque stratégie : famille le 14/10 à 14 h, Gemini à 20 h, Jules v1 à 23 h 04, M3 le 15/10 à 0 h, Jules v2 à 00 h 30, convergence à 01 h, variantes prudentes le 15/10 à 06 h, M3 Max 3 le 17/10 à 03 h, Eden le 19/10 à 20 h (Paris). Les décisions sont figées à partir de la mise en service du registre ; les prises antérieures restent des reconstructions. Les paris en attente ne sont pas comptés comme perdus. Aucun résultat ancien n’est ajouté à ce suivi.",
    ensemble:"Historique figé : matchs du 7 au 13 octobre, règlements disponibles au relevé du 14/10 à 12 h 09 (Paris), y compris les règlements tardifs. Rejeu rétrospectif, distinct du suivi depuis lancement.",
    construction:"Construction : matchs du 7 au 10 octobre ; seuls les règlements connus avant le 11 octobre à 0 h (Paris) sont inclus. Les autres restent en attente.",
    validation:"Validation : matchs des 11 et 12 octobre ; seuls les règlements connus avant le 13 octobre à 0 h (Paris) sont inclus. Les autres restent en attente.",
    test:"Test final : matchs du 13 octobre ; règlements disponibles au relevé du 14/10 à 12 h 09 (Paris). Les paris non réglés restent en attente."
  };
  document.getElementById("strategies-quoi").textContent = descriptions[periodeStrategies] +
    (periodeStrategies === "futur" && !active.length ? " Aucune nouvelle sélection enregistrée : la dernière collecte disponible précède ce lancement. Le bouton Historique affiche la comparaison existante." : "") +
    ` ${(L.resultats || []).length} règles et ${Object.keys(L.comparateurs || {}).length} comparateurs (Claude, ChatGPT V1, Gemini Argon V1, Jules v1/v2, Eden, M3, convergence ≥ 2 et trois variantes encadrées) ; aucune rentabilité future démontrée.`;
  document.getElementById("strategies-table").innerHTML = `<thead><tr><th scope="col">Stratégie</th><th scope="col">Paris</th><th scope="col">Gagnés</th><th scope="col">Perdus</th><th scope="col">Réussite</th><th scope="col">ROI</th><th scope="col">CLV</th><th scope="col">Gains</th><th scope="col">Pertes</th><th scope="col">Gain net</th></tr></thead><tbody>` + rows.map(r => {
    const s=r.stats;
    return `<tr data-strategie="${e(r.id)}"><td><b>${e(r.nomCourt || r.nom)}</b><span class="mini-courbe-table">${miniCourbe(courbeDe(r),COULEURS_COMPARATEURS[r.id] || "var(--accent)")}</span><small>${e(r.detail)}</small></td>
      <td>${s.paris}<small>${s.regles} réglés (${s.evenements_regles ?? "—"} matchs) · ${s.attente} en attente</small></td><td>${s.gagnes}</td><td>${s.perdus}</td>
      <td>${r.reussite == null ? "—" : r.reussite.toFixed(1).replace(".",",")+" %"}</td><td class="${signe(s.roi)}">${pp(s.roi)}</td>
      <td class="${signe(s.clv)}">${pp(s.clv)}<small>${s.clv_n || 0}/${s.regles} tickets mesurés</small><small>Par match ${pp(s.clv_evenement)} · ${s.clv_evenements_n ?? 0}/${s.evenements_regles ?? "—"}</small></td>
      <td class="pos">${s.regles ? eur(s.gains_bruts) : "—"}</td><td class="neg">${s.regles ? eur(-s.pertes_brutes) : "—"}</td>
      <td class="${signe(s.gain)}"><b>${s.regles ? eur(s.gain) : "—"}</b></td></tr>`;
  }).join("") + `</tbody>`;
  document.getElementById("strategies-mobile").innerHTML=rows.length ? rows.map(r =>
    carteStrategieVisuelle(r,courbeDe(r),COULEURS_COMPARATEURS[r.id] || "var(--accent)")).join("")
    : '<div class="vide">Aucune stratégie pour ces filtres. Choisis une autre référence.</div>';
  for(const d of document.querySelectorAll("#strategies-mobile > details")) d.open=lignesOuvertes.has(d.id);
  // Le résumé déplie la ligne ; seul le bouton explicite ouvre la liste des paris.
  document.querySelectorAll("#strategies-table tbody tr, #strategies-mobile button[data-strategie]").forEach(tr => {
    const ligne = rows.find(r => r.id === tr.dataset.strategie);
    if (!ligne) return;
    tr.tabIndex = 0;
    if (tr.tagName !== "BUTTON") tr.setAttribute("role", "link");
    tr.setAttribute("aria-label", "Voir les paris de " + ligne.nom + " : " + ligne.detail);
    const aller = () => {
      strategieChoisie = {id:ligne.id, nom:ligne.nom + " · " + ligne.detail, periode:periodeStrategies};
      document.getElementById("paris-horaire").value="";
      document.getElementById("paris-tri").value="";
      document.getElementById("f-q").value = "";
      for (const id of Object.keys(FILTRES)) document.getElementById("f-"+id).value = "";
      limite = 50;
      rendreParis();
      ouvrir("paris");
      window.scrollTo({top:0,behavior:"instant"});
    };
    tr.onclick = aller;
    tr.onkeydown = ev => {
      if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); aller(); }
    };
  });
  rendreCourbesStrategies(rows.filter(r => r.reference === "comparateurs"));
  const graph = document.getElementById("strategies-graph");
  if (!reglees.length) {
    graph.innerHTML = `<p class="aide">Le graphique apparaîtra après les premiers règlements de cette période. Choisis « Historique 7–13 oct. » pour voir les gains déjà observés.</p>`;
    return;
  }
  const min = Math.min(0,...reglees.map(r => r.stats.gain)), max = Math.max(0,...reglees.map(r => r.stats.gain));
  const span = max-min || 1, zero = -min/span*100;
  graph.innerHTML = `<div class="strat-axe"><span>${eur(min)}</span><span>${eur(max)}</span></div>` + rows.map(r => {
    const g = r.stats.gain, left = (Math.min(0,g)-min)/span*100, width = Math.abs(g)/span*100;
    return `<div class="strat-bar-row" title="${e(r.nom+" · "+r.detail)}"><div class="strat-bar-label">${e(r.nom)}<small>${e(r.graphe)}</small></div>
      <div class="strat-bar-track"><i class="strat-zero" style="left:${zero}%"></i>${r.stats.regles ? `<i class="strat-bar ${signe(g)}" style="left:${left}%;width:${width}%"></i>` : ""}</div>
      <span class="strat-bar-value ${signe(g)}">${r.stats.regles ? eur(g) : "—"}</span></div>`;
  }).join("");
}
document.getElementById("strategies-ref").onchange = rendreStrategies;
document.getElementById("strategies-tri").onchange = rendreStrategies;
rendreStrategies();

function rendreLaboratoire() {
  const L = D.laboratoire;
  const box = document.getElementById("laboratoire");
  if (!L || (!L.resultats?.length && !Object.keys(L.comparateurs || {}).length)) { box.hidden = true; return; }
  const pp = n => n == null ? "—" : pct(n / 100);
  const metrique = s => `<b class="${signe(s.roi)}">${pp(s.roi)}</b><small>${s.regles} réglés (${s.evenements_regles ?? "—"} matchs) · ${s.attente} en attente</small>`;
  const deja = new Date() >= new Date(L.debut_suivi);
  const source = `https://github.com/Matttgic/cotes-value/tree/${encodeURIComponent(L.source.commit)}`;
  const rapport = "https://github.com/Matttgic/cotes-value/blob/ccr-148b8ccc-phitmr/docs/comparaison-strategies.md";
  box.innerHTML = `<h2 style="font-size:16px;margin:0 0 6px">Règles et contrôle du laboratoire</h2>
    <p style="margin:0 0 8px"><b>${L.decision.candidate ? "Candidate expérimentale : " + e(L.decision.candidate) : "Aucune stratégie retenue par le protocole"}.</b>
    Rentabilité future non estimable avec cet historique.</p>
    <details><summary>Examiner une règle en détail</summary>
    <p class="aide" style="margin-top:10px">Trois références, trois plages de cotes, deux seuils d’edge et deux délais.
    10 € fictifs par sélection, un pari par match dans chaque règle. Les règles se recoupent : ne pas additionner leurs mises ou leurs gains.</p>
    <p class="aide">Historique figé : matchs du 7 au 13 octobre 2026, heure de Paris.
    Il a déjà été consulté ; ce n’est pas une validation indépendante. Les seuils restent inchangés malgré les résultats.
    <a href="${rapport}" target="_blank" rel="noopener">Méthode et résultats</a> · <a href="${source}" target="_blank" rel="noopener">Données du relevé</a>.</p>
    <label for="labo-regle">Règle à examiner</label><br>
    <select id="labo-regle" style="max-width:100%;margin:6px 0 10px">${L.resultats.map(r => `<option value="${e(r.regle.id)}">${e(r.regle.nom)}</option>`).join("")}</select>
    <div id="labo-detail"></div>
    <details style="margin-top:12px"><summary>Les 36 résultats historiques</summary>
    <p class="aide">Chaque cellule affiche le ROI sur mises réglées, puis les effectifs. Ordre fixe, sans tri selon la période de test.</p>
    <div class="tableau"><table><tr><th>Règle</th><th>7–10 oct.</th><th>11–12 oct.</th><th>13 oct.</th></tr>
    ${L.resultats.map(r => `<tr><td>${e(r.regle.id)}</td>${["construction","validation","test"].map(p => `<td>${metrique(r[p])}</td>`).join("")}</tr>`).join("")}</table></div></details>
    <details style="margin-top:12px"><summary>Comparateurs : Claude, ChatGPT V1, Gemini Argon V1, JULES EDGE V1/V2, Eden et M3</summary>
    <p class="aide">Rejeux hypothétiques avant leurs lancements, distincts des bilans officiels ci-dessous.
    Claude et M3 peuvent sélectionner plusieurs paris par match ; l’exposition diffère. Aucun comparateur ne participe au classement.</p>
    <div class="tableau"><table><tr><th>Rejeu</th><th>7–10 oct.</th><th>11–12 oct.</th><th>13 oct.</th></tr>
    ${Object.entries(L.comparateurs).map(([nom,r]) => `<tr><td>${e(nom)}</td>${["construction","validation","test"].map(p => `<td>${metrique(r[p])}</td>`).join("")}</tr>`).join("")}</table></div></details>
    <details style="margin-top:12px"><summary>Suivi futur des 36 règles</summary>
    <p class="aide">${deja ? "Depuis le" : "Début le"} ${e(new Date(L.debut_suivi).toLocaleString("fr-FR", {timeZone:"Europe/Paris"}))} (Paris).
    Actualisé à chaque collecte. Un gain positif provisoire ne déclenche aucun changement automatique.</p>
    <div class="tableau"><table><tr><th>Règle</th><th>ROI / effectif</th><th>Gain net</th><th>CLV</th></tr>
    ${L.futur.map(s => `<tr><td>${e(s.id)}</td><td>${metrique(s)}</td><td>${s.regles ? eur(s.gain) : "—"}</td><td>${pp(s.clv)}<small>${s.clv_n} mesures</small></td></tr>`).join("")}</table></div></details>
    </details>`;
  function detail() {
    const id = document.getElementById("labo-regle").value;
    const r = L.resultats.find(r => r.regle.id === id), f = L.futur.find(r => r.id === id);
    const intervalle = s => s.ic95 ? `${pp(s.ic95[0])} à ${pp(s.ic95[1])}` : "Non estimable";
    const fail = [];
    if (r.construction.regles < 20) fail.push("moins de 20 paris réglés en construction");
    if (!(r.construction.roi > 0)) fail.push("ROI de construction non positif");
    if (!(r.construction.clv > 0)) fail.push("CLV de construction non positive ou absente");
    if (!(r.construction.couverture_clv >= 50)) fail.push("couverture de CLV inférieure à 50 %");
    document.getElementById("labo-detail").innerHTML = `<p class="aide">${fail.length ? "Non retenue : " + fail.join(" ; ") + "." : "Seuils de construction satisfaits ; voir le protocole pour le classement et la validation."}</p>
      <div class="tableau"><table><tr><th>Période</th><th>ROI / effectif</th><th>Gain net</th><th>CLV</th></tr>
      ${[["Construction",r.construction],["Validation",r.validation],["Test final",r.test],["Suivi futur",f]].map(([nom,s]) => `<tr><td>${nom}</td><td>${metrique(s)}</td><td>${s.regles ? eur(s.gain) : "—"}</td><td>${pp(s.clv)}<small>${s.clv_n}/${s.regles} mesurés</small></td></tr>`).join("")}</table></div>
      <p class="aide" style="margin-top:8px">Seuil d’edge ${pp(r.regle.edge_min*100)}, plafond 12 %. Cotes de référence âgées de 15 min au maximum.
      Suivi futur ${deja ? "depuis le" : "à partir du"} 14 octobre à 14 h (Paris), uniquement sur les nouvelles détections.</p>
      <details><summary>Incertitude et résistance aux pertes</summary>
      <div class="tableau"><table><tr><th>Période</th><th>IC 95 % du ROI</th><th>Gain sans<br>meilleur pari</th><th>ROI si cotes<br>−1 %</th><th>Baisse max.</th></tr>
      ${[["Construction",r.construction],["Validation",r.validation],["Test final",r.test]].map(([nom,s]) => `<tr><td>${nom}</td><td>${intervalle(s)}</td><td>${s.regles ? eur(s.gain_sans_meilleur) : "—"}</td><td>${pp(s.roi_cote_moins_1pct)}</td><td>${s.regles ? cote(s.drawdown)+" €" : "—"}</td></tr>`).join("")}</table></div>
      <p class="aide">Bootstrap par match, conditionnel à chaque règle ; aucune correction des 36 essais ni des corrélations entre matchs.
      Avec très peu de paris ou des résultats identiques, l’intervalle peut être trompeusement étroit. Il ne prédit pas la rentabilité future.
      Les cotes simulées ne prouvent pas une prise réelle disponible.</p></details>
      <details style="margin-top:8px"><summary>Paris sélectionnés depuis le lancement (${f.paris})</summary>
      <p class="aide">Les 30 dernières sélections de cette règle. Statistiques ci-dessus sur toutes ses sélections.</p>
      ${!f.paris ? '<p class="aide">Aucune sélection depuis le début du suivi.</p>' : f.ids_recents.slice().reverse().map(id => {
        const p = L.paris_recents.find(p => p.id === id);
        if (!p) return "";
        return `<div class="carte"><b>${e(p.domicile)} — ${e(p.exterieur)}</b><div>${e(p.pari)} · ${e(p.bookmaker)} ·${cote(p.cote)}</div>
        ${horairePari(p)}${collectePari(p)}<small>Détecté ${e(quand(p.detecte))} · edge ${pct(p.ecart)}<br>${e(STATUTS[p.statut] || p.statut)}${p.gain == null ? "" : " · " + eur(p.gain)}</small></div>`;
      }).join("")}</details>`;
  }
  document.getElementById("labo-regle").onchange = detail;
  detail();
}
rendreLaboratoire();

// onglet de départ : celui de l'adresse, sinon le dernier ouvert, sinon Paris (« #jouer » reste un ancien raccourci vers Paris)
const depart = location.hash.slice(1) || lire("onglet") || "paris";
__NOTIFICATIONS_JS__
const ONGLETS = ["jouer","bilan","strategies","segments","paris","notifications","regler","controle","analyses"];
ouvrir(ONGLETS.includes(depart) ? depart : "paris");
window.addEventListener("hashchange", () => { const o = location.hash.slice(1); if (ONGLETS.includes(o)) ouvrir(o); });

__ANALYSES_JS__
initialiserAnalyses();
initialiserInterface();
__ACTUALISATION_JS__
const champsVue = ["f-q", "paris-horaire", "paris-tri", ...Object.keys(FILTRES).map(k => "f-"+k), "strategies-ref", "strategies-tri", "labo-regle", "analyse-selection", "analyse-periode", "analyse-sport", "analyse-book"];
const cleDetail = d => d.id || (d.closest("section")?.id || "") + ":" +
  (d.querySelector("summary")?.textContent || "").replace(/\d+/g,"#").trim();
installerActualisation({
  version:"__VERSION_SITE__",
  // Les choix de notification restent sous le contrôle de leur formulaire.
  protegee:() => document.getElementById("o-notifications").classList.contains("actif"),
  capturer:() => ({presentation:"lignes-v1", refBilan, cumul, limite, strategieChoisie, triSeg, ctlVue, periodeStrategies,
    courbes:[...courbesMasquees], champs:Object.fromEntries(champsVue.map(id => [id,document.getElementById(id)?.value])),
    details:[...document.querySelectorAll("details[open]")].map(cleDetail), y:window.scrollY,
    defilements:[...document.querySelectorAll("[id]")].filter(x => x.scrollLeft > 0).map(x => [x.id,x.scrollLeft])}),
  restaurer:s => {
    for (const id of champsVue) {
      if (id === "strategies-ref" && s.presentation !== "lignes-v1") continue;
      const el = document.getElementById(id), valeur = s.champs?.[id];
      if (el && typeof valeur === "string" && (el.tagName !== "SELECT" || [...el.options].some(o => o.value===valeur))) el.value = valeur;
    }
    refBilan = typeof s.refBilan === "string" ? s.refBilan : "Uniques";
    cumul = Number.isInteger(s.cumul) && CUMULS[s.cumul] ? s.cumul : CUMULS.length-1;
    limite = Number.isInteger(s.limite) && s.limite >= 50 ? s.limite : 50;
    strategieChoisie = s.strategieChoisie || null;
    triSeg = s.triSeg in TRIS ? s.triSeg : "roi";
    ctlVue = typeof s.ctlVue === "string" ? s.ctlVue : ctlVue;
    periodeStrategies = s.periodeStrategies in STRAT_PERIODES ? s.periodeStrategies : "futur";
    courbesMasquees.clear();
    for (const id of s.courbes || []) courbesMasquees.add(id);
    rendreBilan(); rendreBilanUniques(); rendreParis(); rendreSante(); rendreSegments(); rendreControle(); rendreStrategies(); rendreAnalyses();
    document.getElementById("labo-regle")?.onchange?.();
    adapterTableaux();
    for (const d of document.querySelectorAll("details")) d.open = (s.details || []).includes(cleDetail(d));
    requestAnimationFrame(() => {
      for (const [id,x] of s.defilements || []) {const el=document.getElementById(id); if(el) el.scrollLeft=x;}
      window.scrollTo(0, Number(s.y) || 0);
    });
  }
});
</script>
</body>
</html>
"""
