"""Génère le site (une page HTML autonome, en onglets) à partir des données de la branche « donnees »."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cotes.simulation import (REFERENCES, SIMULATIONS, STRATEGIE, TEMOIN, TRANCHES, bilan,  # noqa: E402
                              bilan_bookmakers, bilan_tranches, paris_strategie, premiers_par_selection,
                              REGLES, clv_finale, segments, tranche)
from cotes.stockage import lire_archives  # noqa: E402
from cotes.strategie_chatgpt import CHATGPT, paris_chatgpt  # noqa: E402
from cotes.strategie_gemini import GEMINI, paris_gemini  # noqa: E402
from cotes.strategie_jules import JULES, JULES_V2, paris_jules, paris_jules_v2  # noqa: E402
from cotes.strategie_m3 import M3, paris_m3  # noqa: E402
from cotes.laboratoire import (DEBUT_ETUDE, DEBUT_SUIVI, PERIODES, REGLES as REGLES_LABO,
                              evaluer, heure, resume, selectionner, suivi_futur)  # noqa: E402


def _lire(chemin: Path, defaut):
    """Fichier absent : `defaut`. Fichier illisible : erreur (une page aux bilans vides passerait pour un
    état valable)."""
    try:
        texte = chemin.read_text(encoding="utf-8")
    except FileNotFoundError:
        return defaut
    return json.loads(texte)


EN_COURS_AFFICHES = 400        # paris en cours les plus récents
REGLES_AFFICHES = 600          # paris réglés les plus récemment (+ tous ceux à régler à la main)
CHAMPS_FILTRES = {"sims": "simulation", "reference": "reference", "statut": "statut", "bookmaker": "bookmaker",
                  "sport": "sport"}


def cle_fiche(p: dict) -> tuple:
    """Un même pari pris par plusieurs simulations = une seule fiche (même clé que la page)."""
    return (p.get("reference"), p.get("match_id"), p.get("marche"), p.get("periode"), p.get("ligne"), p.get("issue"))


CHAMPS_FICHE = ("reference", "match_id", "marche", "periode", "ligne", "issue", "domicile", "exterieur", "debut",
                "pari", "bookmaker", "cote", "cote_juste", "ecart", "statut", "gain", "clv", "detecte", "sport",
                "ligue", "regle_le", "reporte_au")


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
        f["tranche"] = tranche(f["cote"]) if f.get("cote") else None
        fiches.append(f)
    recents = lambda champ: lambda f: f.get(champ) or ""      # noqa: E731
    ouverts = sorted((f for f in fiches if f["statut"] == "en_cours"), key=recents("detecte"), reverse=True)
    finis = sorted((f for f in fiches if f["statut"] not in ("en_cours", "a_regler")), key=recents("regle_le"),
                   reverse=True)
    # le témoin « Pinnacle brut » (des centaines de paris par cycle) a sa propre part, plus petite
    temoin = lambda f: f["reference"] == TEMOIN                 # noqa: E731
    gardees = ([f for f in ouverts if not temoin(f)][:en_cours] + [f for f in finis if not temoin(f)][:regles]
               + [f for f in ouverts if temoin(f)][:en_cours // 4] + [f for f in finis if temoin(f)][:regles // 4]
               + [f for f in fiches if f["a_regler"]])
    # Les filtres ChatGPT et Gemini donnent accès à l'ensemble de leurs paris, même si les
    # simulations très volumineuses ont repoussé une fiche hors des plus récentes.
    deja = {id(f) for f in gardees}
    gardees += [f for f in fiches if (f["chatgpt"] or f["gemini"] or f["jules"] or f["jules_v2"]) and id(f) not in deja]
    gardees.sort(key=recents("detecte"), reverse=True)
    valeurs = {f: sorted({str(p.get(c)) for p in paris if p.get(c) is not None}) for f, c in CHAMPS_FILTRES.items()}
    return gardees, sum(f["reference"] != TEMOIN for f in fiches), valeurs


def courbes(paris: list[dict]) -> dict[str, list]:
    """Pour le graphique du gain cumulé : par vue du bilan (Uniques, chaque référence, Toutes), les paris
    réglés dans l'ordre du règlement, chacun en [minute du règlement, gain, simulation, gain attendu] (la
    page fait le cumul selon les simulations choisies). Gain attendu = mise × (cote / cote juste − 1) : ce que
    le pari rapporte en moyenne si la cote juste est exacte (absent pour le témoin, comparé à une cote avec
    marge)."""
    uniques, strategie = premiers_par_selection(paris), paris_strategie(paris)
    chatgpt = paris_chatgpt(paris)
    gemini = paris_gemini(paris)
    jules = paris_jules(paris)
    jules_v2 = paris_jules_v2(paris)
    out: dict[str, list] = {}
    regles = [p for p in paris if p.get("statut") not in ("en_cours", "a_regler") and p.get("regle_le")]
    regles.sort(key=lambda p: (p["regle_le"], p.get("debut") or ""))
    for p in regles:
        try:
            t = int(datetime.fromisoformat(p["regle_le"].replace("Z", "+00:00")).timestamp() // 60)
        except ValueError:
            continue
        attendu = (round(p["mise"] * (p["cote"] / p["cote_juste"] - 1), 2)
                   if p["reference"] != TEMOIN and p.get("cote_juste") else None)
        point = [t, round(p.get("gain") or 0, 2), p.get("simulation"), attendu]
        vues = ([p["reference"]] + ([] if p["reference"] == TEMOIN else ["Toutes"])
                + (["Uniques"] if id(p) in uniques else [])
                + ([STRATEGIE["nom"]] if id(p) in strategie else [])
                + ([CHATGPT["nom"]] if id(p) in chatgpt else [])
                + ([GEMINI["nom"]] if id(p) in gemini else [])
                + ([JULES["nom"]] if id(p) in jules else [])
                + ([JULES_V2["nom"]] if id(p) in jules_v2 else []))
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
             p.get("sport")] for p in regles]


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
             p.get("sport")] for p in venir]


def navigation_strategies(paris: list[dict], laboratoire: dict, maintenant: str) -> dict:
    """Relie les lignes du laboratoire aux paris exacts, sans perdre les anciens paris.

    Les IDs historiques des 36 règles viennent du relevé *figé* ; les sélections
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
        "M3 (rejeu)": paris_m3(observes, depuis=DEBUT_ETUDE),
    }
    officiels = {
        "Claude (rejeu)": paris_strategie(paris),
        "ChatGPT v1 (rejeu)": paris_chatgpt(paris),
        "Gemini Argon v1 (rejeu)": paris_gemini(paris),
        "JULES EDGE v1 (rejeu)": paris_jules(paris),
        "JULES EDGE v2 (rejeu)": paris_jules_v2(paris),
        "M3 (rejeu)": paris_m3(paris),
    }
    for nom, historique_ids in historiques.items():
        if nom in laboratoire.get("comparateurs", {}):
            enregistrer(nom, [p for p in passe if id(p) in historique_ids],
                        [p for p in futur if id(p) in officiels[nom]])

    champs = CHAMPS_FICHE + ("simulation", "id")
    return {
        "selections": selection,
        "paris": {pid: {**{k: index[pid].get(k) for k in champs},
                        "sims": [index[pid].get("simulation")],
                        "strategie": False, "chatgpt": False, "gemini": False, "jules": False, "jules_v2": False, "trace": []}
                 for pid in toutes if pid in index},
    }


def construire(donnees: Path, sortie: Path) -> Path:
    paris = _lire(donnees / "paris.json", []) + lire_archives(donnees)     # bilan sur TOUS les paris
    etat = _lire(donnees / "etat.json", {})
    actuelles = [o for o in _lire(donnees / "opportunites_actuelles.json", [])
                 if not o.get("suspect") and o.get("reference") != "Pinnacle brut"]
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
        maintenant = datetime.now(timezone.utc).isoformat()
        releve_str = laboratoire.get("releve") or maintenant
        m3_rapport = _lire(Path(__file__).resolve().parent.parent / "docs/strategie-m3.json", {})
        m3_ids = paris_m3(paris)
        if m3_rapport:
            laboratoire.setdefault("comparateurs", {})["M3 (rejeu)"] = {
                k: m3_rapport[k] for k in ("construction", "validation", "test", "ensemble")
            }
        # Calcul dynamique du rejeu Gemini Argon v1 et JULES EDGE v1 s'ils ne sont pas encore dans comparaison-strategies.json
        releve_dt = heure(releve_str) or heure(maintenant)
        if "Gemini Argon v1 (rejeu)" not in laboratoire.get("comparateurs", {}):
            passe_gem = [p for p in paris if heure(p.get("detecte")) and heure(p["detecte"]) <= releve_dt]
            gem_rejeu_ids = paris_gemini(passe_gem, depuis=DEBUT_ETUDE)
            gem_rows = [p for p in passe_gem if id(p) in gem_rejeu_ids]
            gem_ens = [p for p in gem_rows if heure(DEBUT_ETUDE) <= heure(p["debut"]) < heure(PERIODES[-1][2])]
            laboratoire.setdefault("comparateurs", {})["Gemini Argon v1 (rejeu)"] = {
                **evaluer(gem_rows, releve_str),
                "ensemble": resume(gem_ens, releve_str, incertitude=False),
            }
        if "JULES EDGE v1 (rejeu)" not in laboratoire.get("comparateurs", {}):
            passe_jules = [p for p in paris if heure(p.get("detecte")) and heure(p["detecte"]) <= releve_dt]
            jules_rejeu_ids = paris_jules(passe_jules, depuis=DEBUT_ETUDE)
            jules_rows = [p for p in passe_jules if id(p) in jules_rejeu_ids]
            jules_ens = [p for p in jules_rows if heure(DEBUT_ETUDE) <= heure(p["debut"]) < heure(PERIODES[-1][2])]
            laboratoire.setdefault("comparateurs", {})["JULES EDGE v1 (rejeu)"] = {
                **evaluer(jules_rows, releve_str),
                "ensemble": resume(jules_ens, releve_str, incertitude=False),
            }
        laboratoire["navigation"] = navigation_strategies(paris, laboratoire, maintenant)
        laboratoire["resultats"] = [{k: v for k, v in r.items() if k != "ids_selections"}
                                    for r in laboratoire["resultats"]]
        laboratoire.update(debut_suivi=DEBUT_SUIVI, futur=suivi_futur(paris, DEBUT_SUIVI, maintenant))
        gemini_ids = paris_gemini(paris)
        jules_ids = paris_jules(paris)
        jules_v2_ids = paris_jules_v2(paris)
        officiels = {
            "Claude (rejeu)": paris_strategie(paris),
            "ChatGPT v1 (rejeu)": paris_chatgpt(paris),
            "Gemini Argon v1 (rejeu)": gemini_ids,
            "JULES EDGE v1 (rejeu)": jules_ids,
            "JULES EDGE v2 (rejeu)": jules_v2_ids,
            "M3 (rejeu)": m3_ids,
        }
        laboratoire["m3_paris"] = [{k: p.get(k) for k in
            ("id", "domicile", "exterieur", "sport", "bookmaker", "pari", "cote",
             "reference", "ecart", "detecte", "debut", "statut", "gain")}
            for p in sorted((p for p in paris if id(p) in m3_ids),
                            key=lambda p: p.get("detecte") or "", reverse=True)[:60]]
        laboratoire["gemini_paris"] = [{k: p.get(k) for k in
            ("id", "domicile", "exterieur", "sport", "bookmaker", "pari", "cote",
             "reference", "ecart", "detecte", "debut", "statut", "gain")}
            for p in sorted((p for p in paris if id(p) in gemini_ids),
                            key=lambda p: p.get("detecte") or "", reverse=True)[:60]]
        laboratoire["jules_paris"] = [{k: p.get(k) for k in
            ("id", "domicile", "exterieur", "sport", "bookmaker", "pari", "cote",
             "reference", "ecart", "detecte", "debut", "statut", "gain")}
            for p in sorted((p for p in paris if id(p) in jules_ids),
                            key=lambda p: p.get("detecte") or "", reverse=True)[:60]]
        laboratoire["jules_v2_paris"] = [{k: p.get(k) for k in
            ("id", "domicile", "exterieur", "sport", "bookmaker", "pari", "cote",
             "reference", "ecart", "detecte", "debut", "statut", "gain")}
            for p in sorted((p for p in paris if id(p) in jules_v2_ids),
                            key=lambda p: p.get("detecte") or "", reverse=True)[:60]]
        laboratoire["comparateurs_futur"] = {
            nom: resume([p for p in paris if id(p) in ids and heure(p.get("detecte"))
                         and heure(DEBUT_SUIVI) <= heure(p["detecte"]) < heure(maintenant)],
                        maintenant, incertitude=False) for nom, ids in officiels.items()}
        ids_labo = {i for r in laboratoire["futur"] for i in r["ids_recents"]}
        laboratoire["paris_recents"] = [{k: p.get(k) for k in (
            "id", "domicile", "exterieur", "bookmaker", "pari", "cote", "ecart",
            "detecte", "debut", "statut", "gain")} for p in paris if p["id"] in ids_labo]
    data = {"paris": liste, "fiches_total": fiches_total, "valeurs_filtres": valeurs, "etat": etat, "actuelles": actuelles[:300], "bilan": bilan(paris),
            "bilan_tranches": bilan_tranches(paris), "courbes": courbes(paris), "segments": segments(paris),
            "paris_segments": paris_des_segments(paris), "paris_a_venir_segments": paris_a_venir_des_segments(paris),
            "bilan_bookmakers": bilan_bookmakers(paris), "bookmakers": sorted({p["bookmaker"] for p in paris if p.get("bookmaker")}), "tranches": [t[2] for t in TRANCHES], "controle": controle,
            "strategie": {"debut": STRATEGIE["debut"], "references": list(STRATEGIE["references"]),
                          "cote_max": STRATEGIE["cote_max"], "avance_max_h": STRATEGIE["avance_max_h"]},
            "chatgpt": CHATGPT,
            "gemini": GEMINI,
            "jules": JULES,
            "jules_v2": JULES_V2,
            "m3": M3,
            "laboratoire": laboratoire,
            "simulations": {k: v["nom"].replace(" %", "\u00a0%").replace("≥ ", "≥\u00a0") for k, v in SIMULATIONS.items()}, "references": REFERENCES}
    sortie.mkdir(parents=True, exist_ok=True)
    html = MODELE.replace("__DONNEES__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
    (sortie / "index.html").write_text(html, encoding="utf-8")
    (sortie / ".nojekyll").write_text("", encoding="utf-8")
    return sortie / "index.html"


MODELE = r"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Cotes Value</title>
<style>
:root{--serie:#2a78d6;--attendu:#eb6834;--fond:#f5f6f8;--carte:#fff;--texte:#1b2130;--doux:#677084;--ligne:#e4e7ec;--accent:#2457d6;
--accent-f:#e8eefc;--vert:#0f8a4b;--vert-f:#e2f4e9;--rouge:#c23434;--rouge-f:#fbe6e6;--jaune:#8f6200;--jaune-f:#fff3d1}
@media (prefers-color-scheme:dark){:root{--serie:#3987e5;--attendu:#d95926;--fond:#111419;--carte:#1a1e26;--texte:#e6e9ef;--doux:#9aa2b1;
--ligne:#2a303b;--accent:#7ea4ff;--accent-f:#1f2a44;--vert:#4ec88a;--vert-f:#16321f;--rouge:#ff8080;
--rouge-f:#3a1c1e;--jaune:#f0c35a;--jaune-f:#36301b}}
*{box-sizing:border-box}
body{margin:0;background:var(--fond);color:var(--texte);font:15px/1.4 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
.haut{position:sticky;top:0;z-index:5;background:var(--fond);border-bottom:1px solid var(--ligne)}
.titre{max-width:760px;margin:auto;padding:12px 16px 6px;display:flex;align-items:baseline;justify-content:space-between;gap:8px}
h1{font-size:18px;margin:0}
.maj{color:var(--doux);font-size:12.5px}
nav{max-width:760px;margin:auto;padding:0 12px 8px;display:flex;gap:6px;overflow-x:auto;scrollbar-width:none}
nav button{flex:none;font:inherit;font-size:14px;padding:7px 12px;border-radius:999px;border:1px solid var(--ligne);
background:var(--carte);color:var(--texte);cursor:pointer}
nav button.actif{background:var(--accent);border-color:var(--accent);color:#fff}
nav .nb{font-size:12px;opacity:.75;margin-left:3px}
main{max-width:760px;margin:auto;padding:12px 16px 40px}
.onglet{display:none}.onglet.actif{display:block}
summary{cursor:pointer;font-weight:600}
.courbe{position:relative;background:var(--carte);border:1px solid var(--ligne);border-radius:12px;padding:10px 12px 6px;margin-bottom:12px}
.courbe-tete{display:flex;justify-content:space-between;align-items:baseline;font-size:13px;color:var(--doux)}
.courbe-tete b{font-size:18px}
.legende{display:flex;gap:14px;font-size:12.5px;color:var(--texte);margin:2px 0 4px}
.legende i{display:inline-block;width:14px;height:2px;border-radius:1px;vertical-align:middle;margin-right:5px}
.courbe svg{display:block;width:100%;height:170px;touch-action:pan-y}
.courbe text{fill:var(--doux);font-size:11px;font-variant-numeric:tabular-nums}
.bulle{position:absolute;pointer-events:none;background:var(--texte);color:var(--carte);font-size:12px;line-height:1.35;
padding:5px 8px;border-radius:8px;white-space:nowrap;display:none}
.trace{margin-top:6px;font-size:12.5px;color:var(--doux)}.trace summary{font-weight:500}.trace p{margin:4px 0}
.aide{color:var(--doux);font-size:13px;margin:0 0 10px}
.carte{background:var(--carte);border:1px solid var(--ligne);border-radius:12px;padding:10px 12px;margin-bottom:8px}
.l1{display:flex;justify-content:space-between;gap:10px;font-size:13px;color:var(--doux)}
.l1 .match{color:var(--texte);font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.l1 .quand{flex:none}
.l2{margin:3px 0 6px;font-size:15px}
.l3{display:flex;flex-wrap:wrap;align-items:center;gap:4px 12px;font-size:13.5px}
.l3 i{font-style:normal;color:var(--doux);font-size:12px}
.ecart{margin-left:auto;font-weight:700;color:var(--vert)}
.l4{display:flex;flex-wrap:wrap;gap:4px 10px;margin-top:6px;font-size:12px;color:var(--doux);align-items:center}
.badge{display:inline-block;padding:1px 7px;border-radius:999px;font-size:12px;font-weight:600;background:var(--accent-f);color:var(--accent)}
.gagne,.demi_gagne{background:var(--vert-f);color:var(--vert)}
.perdu,.demi_perdu{background:var(--rouge-f);color:var(--rouge)}
.en_cours,.rembourse{background:var(--ligne);color:var(--doux)}
.a_regler{background:var(--jaune-f);color:var(--jaune)}
.pos{color:var(--vert)}.neg{color:var(--rouge)}
.vide{color:var(--doux);text-align:center;padding:30px 10px}
.seg{cursor:pointer}.seg .l1 .badge{flex:none}
.seg-paris{margin-top:8px;border-top:1px solid var(--ligne);cursor:default}
.seg-paris .sp{padding:7px 0;border-bottom:1px solid var(--ligne)}.seg-paris .sp:last-child{border-bottom:0}
.seg-paris .l3{font-size:12.5px}
.seg-paris .sp-titre{font-weight:700;font-size:13px;padding:9px 0 2px;color:var(--doux)}
.puces{display:flex;gap:6px;overflow-x:auto;margin-bottom:10px;scrollbar-width:none}
.puces button,select,.btn{flex:none;font:inherit;font-size:13px;padding:6px 10px;border-radius:8px;border:1px solid var(--ligne);
background:var(--carte);color:var(--texte);cursor:pointer}
.puces button.actif{border-color:var(--accent);color:var(--accent);font-weight:600}
.btn{background:var(--accent);border-color:var(--accent);color:#fff}
table{width:100%;border-collapse:collapse;background:var(--carte);border:1px solid var(--ligne);border-radius:12px;overflow:hidden;font-size:14px}
th,td{padding:9px 10px;border-bottom:1px solid var(--ligne);text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
@media (max-width:480px){th,td{padding:8px 4px;font-size:12.5px}td small{font-size:11px}
th:first-child,td:first-child{padding-left:8px}th:last-child,td:last-child{padding-right:8px}}
th{font-size:12px;color:var(--doux);font-weight:600;vertical-align:bottom}
th small{display:block;font-size:11px}
th:first-child,td:first-child{text-align:left}
tr:last-child td{border-bottom:0}
td{vertical-align:top}
td small{display:block;color:var(--doux);font-size:11.5px;white-space:nowrap}
td:first-child small{white-space:normal}
.filtres{display:flex;gap:6px;overflow-x:auto;margin-bottom:10px;scrollbar-width:none}
.sous-titre{font-size:15px;margin:18px 0 8px}
.tableau{overflow-x:auto;border-radius:12px}
tr.total td{border-top:2px solid var(--ligne);background:var(--accent-f)}
select.cumul{display:block;margin-top:4px;padding:3px 4px;font-size:12px;max-width:70px}
td small.roi{font-size:12px;font-weight:700;color:inherit}
.infos{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px;margin-top:14px}
.infos div{background:var(--carte);border:1px solid var(--ligne);border-radius:10px;padding:8px 10px;font-size:12.5px;color:var(--doux)}
.infos b{display:block;color:var(--texte);font-size:16px}
/* Tableau complet : nom de la stratégie visible pendant le défilement mobile. */
.strategies-table{min-width:950px}
.strategies-table th:first-child,.strategies-table td:first-child{position:sticky;left:0;background:var(--carte);z-index:1;min-width:180px;max-width:220px;white-space:normal;border-right:1px solid var(--ligne)}
.strategies-table th:first-child{z-index:2}
.strategies-table td:first-child small{max-width:200px;line-height:1.5}
.strategies-table tbody tr{cursor:pointer}
.strategies-table tbody tr:hover td{background:var(--accent-f)}
.strategies-table tbody tr:focus-visible{outline:2px solid var(--accent);outline-offset:-2px}
#paris-strategie-banner{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}
#paris-strategie-banner[hidden]{display:none}
.groupe-paris{font-size:14px;margin:16px 0 8px;color:var(--doux)}
.strat-bar-row{display:grid;grid-template-columns:155px minmax(50px,1fr) 80px;gap:8px;align-items:center;min-height:40px;border-bottom:1px solid var(--ligne)}
.strat-bar-row:last-child{border-bottom:0}
.strat-bar-label{font-size:12px;line-height:1.3}
.strat-bar-label small{display:block;font-size:10.5px;color:var(--doux)}
.strat-bar-track{position:relative;height:22px;background:var(--fond)}
.strat-zero{position:absolute;top:0;bottom:0;width:1px;background:var(--doux)}
.strat-bar{position:absolute;top:4px;height:14px;border-radius:2px}
.strat-bar.pos{background:var(--vert)}.strat-bar.neg{background:var(--rouge)}
.strat-bar-value{text-align:right;font-size:12px;font-variant-numeric:tabular-nums;white-space:nowrap}
.strat-axe{display:flex;justify-content:space-between;margin:0 88px 5px 163px;color:var(--doux);font-size:11px}
@media(max-width:480px){.strategies-table th:first-child,.strategies-table td:first-child{min-width:150px;max-width:160px}
.strat-bar-row{grid-template-columns:112px minmax(45px,1fr) 66px;gap:5px}.strat-bar-value{font-size:11px}.strat-bar-label{font-size:11px}.strat-bar-label small{font-size:9px}
.strat-axe{margin-left:117px;margin-right:71px}}
</style>
</head>
<body>
<div class="haut">
  <div class="titre"><h1>Cotes Value</h1><span class="maj" id="maj"></span></div>
  <nav id="onglets">
    <button data-o="jouer">À jouer<span class="nb" id="nb-jouer"></span></button>
    <button data-o="bilan">Bilan</button>
    <button data-o="strategies">Stratégies</button>
    <button data-o="segments">Segments</button>
    <button data-o="paris">Paris<span class="nb" id="nb-paris"></span></button>
    <button data-o="regler">À régler<span class="nb" id="nb-regler"></span></button>
    <button data-o="controle">Contrôle<span class="nb" id="nb-controle"></span></button>
  </nav>
</div>
<main>
  <section class="onglet" id="o-jouer">
    <p class="aide">Cotes françaises au-dessus de la cote juste, au dernier passage. <span id="jouer-quand"></span></p>
    <div id="jouer"></div>
  </section>
  <section class="onglet" id="o-bilan">
    <p class="aide"><a href="#strategies">Comparer les 36 stratégies, Claude, ChatGPT V1, Gemini Argon et M3</a></p>
    <div class="puces" id="puces-ref"></div>
    <p class="aide" id="bilan-quoi"></p>
    <button id="voir-jules" hidden>Voir les paris JULES EDGE v1</button>
    <button id="voir-jules-v2" hidden>Voir les paris JULES EDGE v2</button>
    <button id="voir-chatgpt" hidden>Voir les paris ChatGPT</button>
    <button id="voir-gemini" hidden>Voir les paris Gemini Argon</button>
    <div class="courbe" id="courbe"><div class="courbe-tete"><span>Gain cumulé <span id="courbe-quoi"></span></span>
    </div><div class="legende" id="legende"></div>
    <svg id="courbe-svg" role="img" aria-label="Gain cumulé réel et attendu au fil des paris réglés"></svg>
    <div class="bulle" id="bulle"></div></div>
    <div class="tableau"><table id="bilan"></table></div>
    <div class="tableau" style="margin-top:10px"><table id="bilan-clv"></table></div>
    <h2 class="sous-titre">Par bookmaker</h2>
    <div class="tableau"><table id="bilan-books"></table></div>
    <p class="aide" style="margin-top:8px">Selon la sélection du Total (A, A+B…).</p>
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
    <p><b>Paris uniques</b> : chaque cote française comptée une fois, même si plusieurs références l'ont signalée.
    <b>Pinnacle, Betfair…</b> : les paris repérés par cette référence, pour comparer les références entre elles.
    <b>Toutes réf.</b> : la somme des références (une même cote peut y compter plusieurs fois).
    <b>Pinnacle brut</b> : témoin, cote Pinnacle avec sa marge.
    <b>Stratégie</b> : les paris qui suivent les critères choisis le 11/10 (voir le texte au-dessus du graphique),
    comptés seulement depuis cette date. <b>ChatGPT</b> : stratégie indépendante, règles figées le 14/10,
    une seule mise par match et cinq nouvelles mises maximum par jour (heure de Paris).
    <b>Gemini Argon</b> : stratégie multi-références à plafond de cote adaptatif (2,15 Pinnacle / 2,60 Betfair & Polymarket),
    un seul pari par match et huit par jour maximum.</p></details>
  </section>
  <section class="onglet" id="o-strategies">
    <h2 class="sous-titre" style="margin-top:0">Toutes les stratégies</h2>
    <div class="puces" id="strategies-periodes" aria-label="Période des stratégies"></div>
    <p class="aide" id="strategies-quoi"></p>
    <div class="filtres">
      <label for="strategies-ref">Référence</label>
      <select id="strategies-ref"><option value="">Toutes</option><option>Pinnacle</option><option>Betfair</option><option>Polymarket</option><option value="comparateurs">Claude / ChatGPT V1 / Gemini Argon / M3</option></select>
      <label for="strategies-tri">Tri</label>
      <select id="strategies-tri"><option value="gain">Gain net</option><option value="roi">ROI</option><option value="regles">Paris réglés</option><option value="gagnes">Paris gagnés</option><option value="reussite">Réussite</option><option value="nom">Nom</option></select>
    </div>
    <p class="aide" id="strategies-total"></p>
    <div class="tableau" tabindex="0" aria-label="Comparaison des stratégies, défilement horizontal sur mobile"><table class="strategies-table" id="strategies-table"></table></div>
    <p class="aide" style="margin-top:8px">10 € fictifs par pari. Réussite = gagnés / réglés (demi-gagnés inclus).
      ROI sur mises réglées. Gains et pertes : résultats nets des paris gagnants et perdants ; net = gains − pertes.
      Les mises des stratégies se recoupent : ne pas additionner les lignes. Claude peut prendre plusieurs paris par match.</p>
    <h2 class="sous-titre">Gain net par stratégie</h2>
    <p class="aide">Même période, mêmes filtres et même ordre que le tableau.</p>
    <div class="carte" id="strategies-graph" role="img" aria-label="Comparaison des gains nets des stratégies"></div>
    <details class="carte" id="gemini-picks">
      <summary><b>Gemini Argon v1</b> — voir les paris depuis le lancement</summary>
      <p class="aide">Pinnacle (1,30–2,15), Betfair & Polymarket (1,30–2,60) · edge 2,5–12 % · 30 min à 24 h · 1 pari/match · max 8/jour · mise fictive 10 €.</p>
      <div id="gemini-picks-list"></div>
    </details>
    <details class="carte" id="m3-picks">
      <summary><b>M3 · MultiSport Value</b> — voir les paris depuis le lancement</summary>
      <p class="aide">Basket, baseball, handball · cotes 1,30–3,00 · edge 2–12 % · mise fictive 10 €.
      Optimisée sur le passé : aucune rentabilité future démontrée. Les sélections d'un même match peuvent être corrélées.</p>
      <div id="m3-picks-list"></div>
    </details>
    <div class="carte" id="laboratoire"></div>
  </section>
  <section class="onglet" id="o-segments">
    <div class="puces" id="puces-seg"></div>
    <p class="aide" id="seg-quoi"></p>
    <div id="segments"></div>
    <details class="aide"><summary>Comment lire</summary>
    <p>Un segment = les paris uniques réglés d'une tranche de cote, d'un bookmaker, d'un sport, ou d'un croisement
    (au moins 10 paris). <b>Attendu</b> : la réussite prévue par la cote juste ; à 1,30, gagner 77 % est normal.
    <b>Écart</b> : réussite réelle moins attendue, en écarts-types ; moins de 2, c'est dans la marge du hasard.</p>
    <p><b>Solide</b> : au moins 30 paris, réussite nettement au-dessus de l'attendu et CLV positive.
    <b>Piste</b> : ROI et CLV positifs, à confirmer. <b>Chance ?</b> : ROI positif mais CLV nulle ou négative
    (on n'a pas battu le marché : sans doute de la chance). Avec près de 100 segments, quelques-uns brillent forcément par hasard.</p>
    <p>Toucher un segment affiche ses paris : d'abord ceux à venir (pas encore commencés, du plus proche au plus lointain), puis ceux déjà réglés. Le toucher à nouveau les replie. Un pari à venir n'entre dans les chiffres du segment qu'une fois réglé.</p></details>
  </section>
  <section class="onglet" id="o-paris">
    <div id="paris-strategie-banner" class="carte" hidden></div>
    <div class="filtres"><select id="f-sim"></select><select id="f-ref"></select><select id="f-statut"></select>
    <select id="f-cote"></select><select id="f-book"></select><select id="f-sport"></select></div>
    <div id="paris"></div>
    <div style="text-align:center"><button class="btn" id="plus" style="display:none">Afficher plus</button></div>
  </section>
  <section class="onglet" id="o-regler">
    <p class="aide">Résultat introuvable automatiquement. Copiez la liste et collez-la à Claude : il cherchera les
    résultats et les enregistrera.</p>
    <p><button class="btn" id="copier">Copier la liste</button></p>
    <div id="regler"></div>
  </section>
  <section class="onglet" id="o-controle">
    <p class="aide">Chaque type d'intitulé de chaque bookmaker est comparé à la référence à chaque passage. Bien
    traduit, un marché est en général un peu sous la cote juste (marge) : rapport médian cote / cote juste entre
    0,70 et 1,02, et moins de 10 % des cotes au-dessus de 1,12. Seuls les intitulés <b>conformes</b> donnent des paris.</p>
    <div class="infos" id="ctl-resume" style="margin:0 0 12px"></div>
    <div class="puces" id="ctl-puces"></div>
    <div id="ctl-liste"></div>
    <h2 class="sous-titre">Dernier passage</h2>
    <div class="infos" id="infos" style="margin-top:0"></div>
  </section>
</main>
<script>
const D = __DONNEES__;
const e = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const cote = x => x==null ? "—" : Number(x).toFixed(2).replace(".", ",");
const pct = x => x==null ? "—" : (x>0?"+":"") + (100*x).toFixed(1).replace(".", ",") + " %";
const eur = x => (x>0?"+":"") + Number(x).toFixed(2).replace(".", ",") + " €";
// bilan : montants compacts (euros entiers, séparateur de milliers ; pourcentages sans décimale au-delà de 100 %)
const eurC = x => x==null ? "—" : (x>0?"+":"") + Math.round(x).toLocaleString("fr-FR") + " €";
const pctC = x => x==null ? "—" : (x>0?"+":"") + (Math.abs(x) >= 1 ? Math.round(100*x).toLocaleString("fr-FR")
  : (100*x).toFixed(1).replace(".", ",")) + " %";
const quand = s => s ? new Date(s).toLocaleString("fr-FR",{weekday:"short",day:"numeric",month:"numeric",hour:"2-digit",minute:"2-digit"}) : "—";
const hm = s => s ? new Date(s).toLocaleTimeString("fr-FR",{hour:"2-digit",minute:"2-digit"}) : "";
const signe = x => x==null ? "" : x>0 ? "pos" : x<0 ? "neg" : "";
const STATUTS = {en_cours:"En cours",gagne:"Gagné",perdu:"Perdu",rembourse:"Remboursé",demi_gagne:"½ gagné",
  demi_perdu:"½ perdu",a_regler:"À régler"};
const lire = k => { try { return localStorage.getItem(k); } catch { return null; } };
const ecrire = (k,v) => { try { localStorage.setItem(k,v); } catch {} };

// --- en-tête et onglets
const dc = (D.etat||{}).dernier_cycle || {};
document.getElementById("maj").textContent = dc.debut ? "mis à jour " + quand(dc.debut) + (dc.mode==="test" ? " · test" : "") : "pas encore de données";
function ouvrir(o) {
  document.querySelectorAll("nav button").forEach(b => b.classList.toggle("actif", b.dataset.o===o));
  document.querySelectorAll(".onglet").forEach(s => s.classList.toggle("actif", s.id==="o-"+o));
  ecrire("onglet", o); history.replaceState(null, "", "#"+o);
}
document.querySelectorAll("nav button").forEach(b => b.onclick = () => ouvrir(b.dataset.o));

// --- À jouer
// une carte par cote française (bookmaker, match, pari), avec les références qui la signalent
const parCote = new Map();
for (const o of D.actuelles) {
  const k = o.bookmaker + "|" + o.match_id + "|" + o.pari;
  if (!parCote.has(k)) parCote.set(k, {...o, refs: []});
  const c = parCote.get(k);
  c.refs.push(o);
  c.ecart = Math.max(c.ecart, o.ecart);
}
const cotesJouer = [...parCote.values()].sort((a, b) => b.ecart - a.ecart);
const minutes = s => s ? Math.max(0, Math.round((Date.now() - new Date(s)) / 60000)) : null;
const carteActuelle = o => `<article class="carte">
<div class="l1"><span class="match">${e(o.domicile)} – ${e(o.exterieur)}</span><span class="quand">${quand(o.debut)}</span></div>
<div class="l2">${e(o.pari)}</div>
<div class="l3"><span><b>${e(o.bookmaker)} ${cote(o.cote)}</b></span><span class="ecart">${pct(o.ecart)}</span></div>
<div class="l4">cote juste : ${o.refs.map(r => `${e(r.reference)} ${cote(r.cote_juste)}`).join(" · ")}</div>
</article>`;
const age = minutes(dc.debut);
document.getElementById("jouer-quand").textContent = dc.debut ? `Relevé à ${hm(dc.debut)}` +
  (age != null ? ` (il y a ${age} min)` : "") + `. La cote a pu bouger depuis : vérifie-la avant de jouer.` : "";
document.getElementById("jouer").innerHTML = cotesJouer.length ? cotesJouer.map(carteActuelle).join("")
  : `<div class="vide">Aucune erreur de cote au dernier passage.</div>`;
document.getElementById("nb-jouer").textContent = cotesJouer.length || "";

// --- Bilan
let refBilan = "Uniques";
const NOMS_REF = {Uniques: "Paris uniques", Toutes: "Toutes réf."};
const ST = D.strategie || {};
const CG = D.chatgpt || {};
const GM = D.gemini || {};
const QUOI = {Uniques: "Ce que tu aurais gagné en jouant chaque cote signalée une seule fois (10 € par pari).",
  Toutes: "Somme des références : une même cote repérée par plusieurs références compte plusieurs fois.",
  "Pinnacle brut": "Témoin : cotes comparées à la cote Pinnacle affichée, marge comprise.",
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
    10 € fictifs par pari, strictly 1 seul pari par match, ${GM.paris_max_jour || 8} par jour maximum.`,
  "JULES EDGE v1": `JULES EDGE v1 — Pinnacle sans marge (1,30–2,50 ; edge 3–12 % ; 15 min à 12 h ; 1/match ; max 6/jour).`,
  "JULES EDGE v2": `JULES EDGE v2 — Multi-références (Pinnacle, Betfair, Polymarket ; 1,30–2,80 ; edge 2,5–12 % ; 15 min à 18 h ; 1/match ; max 8/jour).`};
// ligne « Total » : cumul des simulations choisies (A, A+B, A+B+C…), par défaut toutes
const SIMS = Object.keys(D.simulations);
const CUMULS = [...SIMS.filter(s => s !== "X").map((s, i, l) => l.slice(0, i + 1)), SIMS];
let cumul = CUMULS.length - 1;
const nomCumul = l => l.length === SIMS.length ? "Toutes" : l.join("+");
function additionner(sims, source = D.bilan, prefixe = "") {
  const t = {paris: 0, regles: 0, en_cours: 0, mises: 0, gains: 0, clv_somme: 0, clv_n: 0, gagnes: 0,
    gains_avec_clv: 0, espere_clv: 0, gains_sans_clv: 0, regles_sans_clv: 0};
  let vu = false;
  for (const s of sims) {
    const b = (source || {})[prefixe + s + "|" + refBilan];
    if (!b) continue;
    vu = true;
    for (const k of Object.keys(t)) t[k] += b[k] || 0;
  }
  if (!vu) return null;
  t.roi = t.mises ? t.gains / t.mises : null;
  t.clv_moyenne = t.clv_n ? t.clv_somme / t.clv_n : null;
  return t;
}
function rendreBilan() {
  const refs = ["Uniques", "JULES EDGE v1", "JULES EDGE v2", "ChatGPT", "Gemini Argon", "Stratégie", ...D.references.filter(r => r !== "Pinnacle brut"), "Toutes", "Pinnacle brut"];
  document.getElementById("puces-ref").innerHTML = refs.map(r =>
    `<button data-r="${r}" class="${r===refBilan?"actif":""}">${NOMS_REF[r] || r}</button>`).join("");
  document.getElementById("bilan-quoi").textContent = QUOI[refBilan] || `Paris repérés par ${refBilan}.`;
  document.getElementById("voir-jules").hidden = refBilan !== "JULES EDGE v1";
  document.getElementById("voir-jules-v2").hidden = refBilan !== "JULES EDGE v2";
  document.getElementById("voir-chatgpt").hidden = refBilan !== "ChatGPT";
  document.getElementById("voir-gemini").hidden = refBilan !== "Gemini Argon";
  document.querySelectorAll("#puces-ref button").forEach(b => b.onclick = () => { refBilan = b.dataset.r; rendreBilan(); });
  const ligne = (titre, b) => !b ? `<tr><td>${titre}</td><td>0</td><td>—</td><td>—</td></tr>`
    : `<tr><td>${titre}</td><td>${b.regles}${b.regles ? `<small>${b.gagnes} gagné${b.gagnes > 1 ? "s" : ""} · <b>${Math.round(100 * b.gagnes / b.regles)} %</b></small>` : ""}${b.en_cours ? `<small>${b.en_cours} en cours</small>` : ""}</td>
<td class="${signe(b.gains)}">${eurC(b.gains)}<small class="roi ${signe(b.roi)}">${b.roi==null ? "" : pctC(b.roi)}</small></td>
<td class="${signe(b.clv_moyenne)}">${pctC(b.clv_moyenne)}${b.regles ? `<small>${b.clv_n}/${b.regles}</small>` : ""}</td></tr>`;
  document.getElementById("bilan").innerHTML = `<tr><th>Simul.</th><th>Paris</th><th>Gain<small>ROI</small></th><th>CLV</th></tr>` +
    Object.entries(D.simulations).filter(([s]) => !(["Stratégie", "ChatGPT", "Gemini Argon"].includes(refBilan) && s === "X")).map(([s, nom]) => ligne(`<b>${s}</b> <small>${e(nom)}</small>`, D.bilan[s + "|" + refBilan])).join("") +
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
  document.getElementById("bilan-books").innerHTML = `<tr><th>Bookmaker</th><th>Paris</th><th>Gain<small>ROI</small></th><th>CLV</th></tr>` +
    (D.bookmakers || []).map(bm => ligne(`<b>${e(bm)}</b>`, additionner(CUMULS[cumul], D.bilan_bookmakers, bm + "·"))).join("");
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
  const avecAttendu = pts.some(p => p[3] != null);       // pas pour le témoin (cote avec marge)
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
window.addEventListener("resize", () => rendreCourbe());
rendreBilan();
const mois = new Date().toISOString().slice(0,7);
document.getElementById("infos").innerHTML = [
  ["Cotes françaises lues", (dc.cotes||{}).francaises], ["Matchs comparés", dc.matchs_francais],
  ["Erreurs au dernier passage", dc.opportunites], ["Requêtes PulseScore ce mois", ((D.etat||{}).requetes_par_mois||{})[mois] || 0],
  // sources en panne ou incomplètes au dernier passage (une absence de résultat n'est pas toujours normale)
  ["Sources en panne", Object.entries(dc.etapes || {}).filter(([k, v]) => !v.ok || v.degrade)
    .map(([k]) => e(k.replace(/^resultats_/, ""))).join(", ") || "aucune"]
].map(([a,b]) => `<div>${a}<b>${b ?? "—"}</b></div>`).join("");

// --- Paris : fiches déjà regroupées (un même pari pris par plusieurs simulations = une seule fiche)
const fiches = D.paris;
document.getElementById("nb-paris").textContent = fiches.filter(f => f.reference !== "Pinnacle brut").length || "";
const affiches = fiches.filter(f => f.reference !== "Pinnacle brut").length;
if (D.fiches_total > affiches) document.getElementById("paris").insertAdjacentHTML("beforebegin",
  `<p class="aide">${affiches} paris affichés sur ${D.fiches_total} : les 400 derniers en cours, les 600 derniers réglés et
  ceux à régler (le bilan compte tous les paris). Filtre « Statuts » pour ne voir que les gagnés, perdus… ; le témoin
  « Pinnacle brut » s'affiche en le choisissant dans « Références ».</p>`);
const FILTRES = {sim:["sims","Simulations"], ref:["reference","Références"], statut:["statut","Statuts"],
  cote:["tranche","Cotes"], book:["bookmaker","Bookmakers"], sport:["sport","Sports"]};
for (const [id,[champ,tous]] of Object.entries(FILTRES)) {
  // cotes : les tranches du bilan ; simulations : + « Stratégie », « ChatGPT », « Gemini Argon »
  const vals = champ === "tranche" ? D.tranches || [] : [...((D.valeurs_filtres || {})[champ] || []),
    ...(champ === "sims" ? ["Stratégie", "ChatGPT", "Gemini Argon"] : [])];
  const sel = document.getElementById("f-" + id);
  sel.innerHTML = `<option value="">${tous}</option>` + vals.map(v => `<option value="${e(v)}">${e(
    champ==="statut" ? STATUTS[v]||v : champ==="sims" && D.simulations[v] ? v + " " + D.simulations[v] : v)}</option>`).join("");
  sel.onchange = () => { limite = 50; rendreParis(); };
}
let limite = 50;
let strategieChoisie = null;
const carteParis = p => `<article class="carte">
<div class="l1"><span class="match">${e(p.domicile)} – ${e(p.exterieur)}</span><span class="quand">${p.reporte_au && p.statut === "en_cours"
  ? "reporté au " + quand(p.reporte_au) : quand(p.debut)}</span></div>
<div class="l2">${e(p.pari)}</div>
<div class="l3"><span><b>${e(p.bookmaker)} ${cote(p.cote)}</b></span><span>${e(p.reference)} ${cote(p.cote_juste)}</span>
<span class="ecart">${pct(p.ecart)}</span></div>
<div class="l4"><span class="badge ${p.statut}">${STATUTS[p.statut]||p.statut}</span>
${p.chatgpt ? `<span class="badge">ChatGPT v1</span>` : ""}
${p.gemini ? `<span class="badge">Gemini Argon v1</span>` : ""}
${p.gain!=null ? `<b class="${signe(p.gain)}">${eur(p.gain)}</b>` : ""}
<span>CLV <span class="${signe(p.clv)}">${pct(p.clv)}</span></span></div>
${(p.trace||[]).length ? `<details class="trace"><summary>Détails</summary>${p.trace.map(t => `<p>${e(t)}</p>`).join("")}</details>` : ""}
</article>`;
function rendreParis() {
  const f = Object.fromEntries(Object.entries(FILTRES).map(([id,[champ]]) => [champ, document.getElementById("f-"+id).value]));
  const navigation = D.laboratoire?.navigation;
  const ids = strategieChoisie ? (navigation?.selections?.[strategieChoisie.id]?.[strategieChoisie.periode] || []) : null;
  // Les stratégies ont leurs propres paris exacts : pas uniquement les 400/600
  // dernières fiches fusionnées, qui pourraient masquer des sélections anciennes.
  const source = ids ? ids.map(id => navigation.paris[id]).filter(Boolean) : fiches;
  const L = source.filter(p => (f.reference || p.reference !== "Pinnacle brut") &&
    Object.entries(f).every(([k,v]) => !v || (k==="sims" ? (v==="Stratégie" ? p.strategie : v==="ChatGPT" ? p.chatgpt : v==="Gemini Argon" ? p.gemini : (p.sims||[]).includes(v)) : p[k]===v)));
  const banner = document.getElementById("paris-strategie-banner");
  const plus = document.getElementById("plus");
  banner.hidden = !strategieChoisie;
  if (strategieChoisie) {
    banner.innerHTML = `<div><b>${e(strategieChoisie.nom)}</b><div class="aide">${e(STRAT_PERIODES[strategieChoisie.periode])}
      · ${L.length} pari(s) · cotes simulées à la détection. Les statistiques historiques restent figées au relevé.</div></div>
      <button class="btn" id="paris-tout">Tous les paris</button>`;
    document.getElementById("paris-tout").onclick = () => {
      strategieChoisie = null;
      for (const id of Object.keys(FILTRES)) document.getElementById("f-"+id).value = "";
      limite = 50;
      rendreParis();
    };
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
    document.getElementById("paris").innerHTML = L.length ? parties.map(([titre,paris]) => {
      const restant = Math.max(0, limite-compteur), visibles = paris.slice(0,restant);
      compteur += visibles.length;
      return `<h3 class="groupe-paris">${titre} (${paris.length})</h3>` +
        (visibles.length ? visibles.map(carteParis).join("") : (paris.length ? "" : '<p class="aide">Aucun pour le moment.</p>'));
    }).join("") : '<div class="vide">Aucun pari pour cette stratégie et ces filtres.</div>';
  } else {
    document.getElementById("paris").innerHTML = L.length ? L.slice(0,limite).map(carteParis).join("")
      : '<div class="vide">Aucun pari pour ces filtres.</div>';
  }
  plus.style.display = L.length > limite ? "" : "none";
  plus.onclick = () => { limite += 50; rendreParis(); };
}
rendreParis();
document.getElementById("voir-chatgpt").onclick = () => {
  strategieChoisie = null;
  for (const id of Object.keys(FILTRES)) document.getElementById("f-" + id).value = "";
  document.getElementById("f-sim").value = "ChatGPT";
  limite = 50;
  rendreParis();
  ouvrir("paris");
};
document.getElementById("voir-gemini").onclick = () => {
  strategieChoisie = null;
  for (const id of Object.keys(FILTRES)) document.getElementById("f-" + id).value = "";
  document.getElementById("f-sim").value = "Gemini Argon";
  limite = 50;
  rendreParis();
  ouvrir("paris");
};

// --- Segments : les groupes de paris qui marchent, avec ce qui relève de la chance
let triSeg = "roi";
const TRIS = {roi: "Meilleur ROI", reussite: "Réussite au-dessus de l'attendu"};
const verdict = s => (s.n >= 30 && s.ecart_sigma >= 2 && (s.clv_moyenne || 0) > 0.01) ? ["Solide", "gagne"]
  : (s.roi > 0 && (s.clv_moyenne || 0) > 0) ? ["Piste", "en_cours"]
  : s.roi > 0 ? ["Chance ?", "a_regler"] : ["Perdant", "perdu"];
const nomSeg = s => [s.tranche && "Cotes " + s.tranche, s.bookmaker, s.sport && s.sport.replace("_", " ")]
  .filter(Boolean).join(" · ");
const dansSeg = s => x => (!s.tranche || x[9] === s.tranche) && (!s.bookmaker || x[2] === s.bookmaker) && (!s.sport || x[10] === s.sport);
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
  document.getElementById("segments").innerHTML = L.length ? L.map((s, i) => {
    const [v, c] = verdict(s);
    return `<article class="carte seg" data-i="${D.segments.indexOf(s)}">
<div class="l1"><span class="match">${e(nomSeg(s))}</span><span class="badge ${c}">${v}</span></div>
<div class="l3"><span>${s.n} paris · <b>${s.gagnes} gagnés = ${Math.round(100 * s.gagnes / s.n)} %</b></span>
<span><i>attendu</i> ${Math.round(100 * s.attendus / s.n)} %</span>
<span><i>écart</i> <span class="${signe(s.ecart_sigma)}">${s.ecart_sigma > 0 ? "+" : ""}${String(s.ecart_sigma).replace(".", ",")}</span></span></div>
<div class="l4"><span>ROI <b class="${signe(s.roi)}">${pctC(s.roi)}</b> (${eurC(s.gains)})</span>
<span>CLV <span class="${signe(s.clv_moyenne)}">${pctC(s.clv_moyenne)}</span> <i>${s.clv_n}/${s.n}</i></span>
${(n => n ? `<span class="badge en_cours">${n} à venir</span>` : "")(aVenir(s).length)}</div></article>`;
  }).join("") : `<div class="vide">Aucun segment pour l'instant.</div>`;
  // toucher un segment déroule ses paris à venir, puis ses paris réglés (ceux qu'il compte), du plus récent au plus ancien
  document.querySelectorAll("#segments .seg").forEach(a => a.onclick = ev => {
    if (ev.target.closest(".seg-paris")) return;
    const ouvert = a.querySelector(".seg-paris");
    if (ouvert) { ouvert.remove(); return; }
    const s = D.segments[Number(a.dataset.i)];
    const L = (D.paris_segments || []).filter(dansSeg(s)), V = aVenir(s);
    a.insertAdjacentHTML("beforeend", `<div class="seg-paris">
<div class="sp-titre">À venir (${V.length})</div>${V.length ? V.map(x => `<div class="sp">
<div class="l1"><span class="match">${e(x[0])}</span><span class="quand">${quand(x[8])}</span></div>
<div class="l3"><span>${e(x[1])}</span><span><b>${e(x[2])} ${cote(x[3])}</b> <i>juste${cote(x[4])}</i></span>
<span><i>écart</i> <span class="${signe(x[5])}">${pct(x[5])}</span></span>
<span>CLV <span class="${signe(x[7])}">${pct(x[7])}</span> <i>pour l'instant</i></span></div></div>`).join("")
  : `<div class="sp"><i>Aucun pari à venir dans ce segment pour l'instant.</i></div>`}
<div class="sp-titre">Réglés (${L.length})</div>${L.map(x => `<div class="sp">
<div class="l1"><span class="match">${e(x[0])}</span><span class="quand">${quand(x[8])}</span></div>
<div class="l3"><span>${e(x[1])}</span><span><b>${e(x[2])} ${cote(x[3])}</b> <i>juste${cote(x[4])}</i></span>
<span class="badge ${x[5]}">${STATUTS[x[5]] || x[5]}</span><b class="${signe(x[6])}">${eur(x[6])}</b>
<span>CLV <span class="${signe(x[7])}">${pct(x[7])}</span></span></div></div>`).join("")}</div>`);
  });
}
rendreSegments();

// --- À régler
const vus = new Set(), man = D.paris.filter(p => p.a_regler && !vus.has(p.match_id+p.pari) && vus.add(p.match_id+p.pari));
document.getElementById("nb-regler").textContent = man.length || "";
document.getElementById("regler").innerHTML = man.length ? man.map(p => `<article class="carte">
<div class="l1"><span class="match">${e(p.domicile)} – ${e(p.exterieur)}</span><span class="quand">${quand(p.debut)}</span></div>
<div class="l2">${e(p.pari)}</div><div class="l4"><span>${e(p.bookmaker)}</span><span>${e(p.ligue||"")}</span></div></article>`).join("")
  : `<div class="vide">Rien à régler à la main.</div>`;
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
document.getElementById("nb-controle").textContent = nbc("non_conforme") || "";
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

// Famille publiée une fois : aucun nouveau classement choisi selon le test final.
// Comparaison complète : même ligne de données pour le tableau et le graphique.
const STRAT_PERIODES = {futur:"Depuis le lancement", ensemble:"Historique 7–13 oct.",
  construction:"7–10 oct.", validation:"11–12 oct.", test:"13 oct."};
let periodeStrategies = "futur";
function rendreStrategies() {
  const L = D.laboratoire;
  if (!L?.resultats?.length) {
    document.getElementById("strategies-quoi").textContent = "Aucune comparaison disponible.";
    return;
  }
  const pp = n => n == null ? "—" : pct(n/100);
  const bornes = n => String(n).replace(".",",");
  const futur = new Map((L.futur || []).map(r => [r.id,r]));
  let rows = L.resultats.map(r => ({id:r.regle.id, nom:r.regle.reference, reference:r.regle.reference,
    detail:`Cotes ${bornes(r.regle.cote_min)}–${bornes(r.regle.cote_max)} · edge ≥ ${r.regle.edge_min*100} % · ≤ ${r.regle.avance_max_h} h`,
    graphe:`${bornes(r.regle.cote_min)}–${bornes(r.regle.cote_max)} · ≥ ${r.regle.edge_min*100} % · ${r.regle.avance_max_h} h`,
    stats:periodeStrategies === "futur" ? futur.get(r.regle.id) : r[periodeStrategies]}));
  for (const [id,per] of Object.entries(L.comparateurs || {})) {
  const nomComp = id.startsWith("JULES EDGE v2") ? "JULES EDGE V2"
    : id.startsWith("JULES") ? "JULES EDGE V1"
    : id.startsWith("Claude") ? "Claude"
    : id.startsWith("M3") ? "M3 · MultiSport"
    : id.startsWith("Gemini") ? "Gemini Argon V1"
    : "ChatGPT V1";
    const detailComp = periodeStrategies === "futur"
      ? (id.startsWith("M3") ? "Depuis le 15/10 · simulation, 10 € / sélection"
         : id.startsWith("Gemini") ? "Multi-réf. adaptative · 1 pari/match · max 8/j"
         : "Nouvelles prises officielles depuis le 14/10 à 14 h")
      : (id.startsWith("M3") ? "Optimisation a posteriori · 3 sports · 1,30–3,00 · 2–12 % d’edge"
         : id.startsWith("Gemini") ? "Rejeu hypothétique · Pin ≤ 2,15 / Bet+Poly ≤ 2,60 · edge ≥ 2,5 %"
         : "Rejeu hypothétique · mêmes dates que la famille");
    rows.push({id, nom:nomComp, reference:"comparateurs", detail:detailComp,
      graphe:"Comparateur", stats:periodeStrategies === "futur" ? L.comparateurs_futur?.[id] : per[periodeStrategies]});
  }
  rows = rows.filter(r => r.stats).map(r => ({...r, reussite:r.stats.regles ? 100*r.stats.gagnes/r.stats.regles : null}));
  const ref = document.getElementById("strategies-ref").value;
  if (ref) rows = rows.filter(r => r.reference === ref);
  const tri = document.getElementById("strategies-tri").value;
  rows.sort((a,b) => {
    if (tri === "nom") return a.nom.localeCompare(b.nom,"fr") || a.id.localeCompare(b.id);
    const av = tri === "reussite" ? a.reussite : a.stats[tri], bv = tri === "reussite" ? b.reussite : b.stats[tri];
    return (bv ?? -Infinity) - (av ?? -Infinity) || a.id.localeCompare(b.id);
  });
  document.getElementById("strategies-periodes").innerHTML = Object.entries(STRAT_PERIODES).map(([id,nom]) =>
    `<button data-p="${id}" class="${periodeStrategies===id ? "actif" : ""}" aria-pressed="${periodeStrategies===id}">${nom}</button>`).join("");
  for (const b of document.querySelectorAll("#strategies-periodes button")) b.onclick = () => { periodeStrategies=b.dataset.p; rendreStrategies(); };
  const gemPicks = L.gemini_paris || [];
  document.getElementById("gemini-picks-list").innerHTML = gemPicks.length
    ? gemPicks.map(p => `<article style="padding:8px 0;border-top:1px solid var(--ligne)">
       <b>${e(p.domicile)} – ${e(p.exterieur)}</b> <small>${e(p.sport)} · ${e(p.bookmaker)} (${e(p.reference)})</small>
       <div>${e(p.pari)} · cote ${cote(p.cote)} · edge ${pct(p.ecart)}</div>
       <small>${quand(p.debut)} · ${e(p.statut)}${p.gain==null ? "" : " · "+eur(p.gain)}</small>
       </article>`).join("")
    : '<p class="aide">Aucune nouvelle sélection Gemini Argon depuis son démarrage prospectif.</p>';
  const picks = L.m3_paris || [];
  document.getElementById("m3-picks-list").innerHTML = picks.length
    ? picks.map(p => `<article style="padding:8px 0;border-top:1px solid var(--ligne)">
       <b>${e(p.domicile)} – ${e(p.exterieur)}</b> <small>${e(p.sport)} · ${e(p.bookmaker)}</small>
       <div>${e(p.pari)} · cote ${cote(p.cote)} · edge ${pct(p.ecart)}</div>
       <small>${quand(p.debut)} · ${e(p.statut)}${p.gain==null ? "" : " · "+eur(p.gain)}</small>
       </article>`).join("")
    : '<p class="aide">Aucune nouvelle sélection M3 depuis son démarrage prospectif du 15 octobre.</p>';
  const active = rows.filter(r => r.stats.paris), reglees = rows.filter(r => r.stats.regles);
  document.getElementById("strategies-total").textContent = `${rows.length} stratégies affichées · ${active.length} avec des sélections · ${reglees.length} avec des paris réglés. Glisse le tableau vers la gauche pour voir toutes les colonnes.`;
  const descriptions = {
    futur:"Suivi sur les nouvelles détections depuis le 14 octobre 2026 à 14 h (Paris). Les paris en attente ne sont pas comptés comme perdus. Aucun résultat ancien n’est ajouté à ce suivi.",
    ensemble:"Historique figé : matchs du 7 au 13 octobre, règlements disponibles au relevé du 14/10 à 12 h 09 (Paris), y compris les règlements tardifs. Rejeu rétrospectif, distinct du suivi depuis lancement.",
    construction:"Construction : matchs du 7 au 10 octobre ; seuls les règlements connus avant le 11 octobre à 0 h (Paris) sont inclus. Les autres restent en attente.",
    validation:"Validation : matchs des 11 et 12 octobre ; seuls les règlements connus avant le 13 octobre à 0 h (Paris) sont inclus. Les autres restent en attente.",
    test:"Test final : matchs du 13 octobre ; règlements disponibles au relevé du 14/10 à 12 h 09 (Paris). Les paris non réglés restent en attente."
  };
  document.getElementById("strategies-quoi").textContent = descriptions[periodeStrategies] +
    (periodeStrategies === "futur" && !active.length ? " Aucune nouvelle sélection enregistrée : la dernière collecte disponible précède ce lancement. Le bouton Historique affiche la comparaison existante." : "") +
    " 36 règles et 4 comparateurs (Claude, ChatGPT V1, Gemini Argon V1, M3) ; aucune rentabilité future démontrée.";
  document.getElementById("strategies-table").innerHTML = `<thead><tr><th>Stratégie</th><th>Paris</th><th>Gagnés</th><th>Perdus</th><th>Réussite</th><th>ROI</th><th>Gains</th><th>Pertes</th><th>Gain net</th></tr></thead><tbody>` + rows.map(r => {
    const s=r.stats;
    return `<tr data-strategie="${e(r.id)}"><td><b>${e(r.nom)}</b><small>${e(r.detail)}</small></td>
      <td>${s.paris}<small>${s.regles} réglés · ${s.attente} en attente</small></td><td>${s.gagnes}</td><td>${s.perdus}</td>
      <td>${r.reussite == null ? "—" : r.reussite.toFixed(1).replace(".",",")+" %"}</td><td class="${signe(s.roi)}">${pp(s.roi)}</td>
      <td class="pos">${s.regles ? eur(s.gains_bruts) : "—"}</td><td class="neg">${s.regles ? eur(-s.pertes_brutes) : "—"}</td>
      <td class="${signe(s.gain)}"><b>${s.regles ? eur(s.gain) : "—"}</b></td></tr>`;
  }).join("") + `</tbody>`;
  // Une ligne = une navigation vers tous les paris de cette stratégie et de la
  // période choisie, y compris les terminés et ceux absents des fiches récentes.
  document.querySelectorAll("#strategies-table tbody tr").forEach(tr => {
    const ligne = rows.find(r => r.id === tr.dataset.strategie);
    if (!ligne) return;
    tr.tabIndex = 0;
    tr.setAttribute("role", "link");
    tr.setAttribute("aria-label", "Voir les paris de " + ligne.nom + " : " + ligne.detail);
    const aller = () => {
      strategieChoisie = {id:ligne.id, nom:ligne.nom + " · " + ligne.detail, periode:periodeStrategies};
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
  if (!L?.resultats?.length) { box.hidden = true; return; }
  const pp = n => n == null ? "—" : pct(n / 100);
  const metrique = s => `<b class="${signe(s.roi)}">${pp(s.roi)}</b><small>${s.regles} réglés · ${s.attente} en attente</small>`;
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
    <details style="margin-top:12px"><summary>Comparateurs : Claude, ChatGPT V1, Gemini Argon V1 et M3</summary>
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
        <small>Détecté ${e(quand(p.detecte))} · edge ${pct(p.ecart)}<br>${e(STATUTS[p.statut] || p.statut)}${p.gain == null ? "" : " · " + eur(p.gain)}</small></div>`;
      }).join("")}</details>`;
  }
  document.getElementById("labo-regle").onchange = detail;
  detail();
}
rendreLaboratoire();

// onglet de départ : celui de l'adresse, sinon le dernier ouvert, sinon « À jouer »
const depart = location.hash.slice(1) || lire("onglet") || "jouer";
const ONGLETS = ["jouer","bilan","strategies","segments","paris","regler","controle"];
ouvrir(ONGLETS.includes(depart) ? depart : "jouer");
window.addEventListener("hashchange", () => { const o = location.hash.slice(1); if (ONGLETS.includes(o)) ouvrir(o); });
</script>
</body>
</html>
"""
