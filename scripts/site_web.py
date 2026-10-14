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
    gardees += [f for f in fiches if (f["chatgpt"] or f["gemini"]) and id(f) not in deja]
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
                + ([GEMINI["nom"]] if id(p) in gemini else []))
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
    passe = [p for p in paris if heure(p.get("detecte")) and heure(p.get("debut"))
             and debut_historique <= heure(p["debut"]) < fin_historique
             and heure(p["detecte"]) <= releve]
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

    # Le rejeu historique commence avant le lancement officiel de ces stratégies.
    for nom, historique, a_venir in (
        ("Claude (rejeu)", claude_rejouee(passe),
         [p for p in futur if id(p) in paris_strategie(paris)]),
        ("ChatGPT v1 (rejeu)", [p for p in passe if id(p) in paris_chatgpt(passe, depuis=DEBUT_ETUDE)],
         [p for p in futur if id(p) in paris_chatgpt(paris)]),
        ("Gemini Argon v1 (rejeu)", [p for p in passe if id(p) in paris_gemini(passe, depuis=DEBUT_ETUDE)],
         [p for p in futur if id(p) in paris_gemini(paris)]),
        ("M3 (rejeu)", [p for p in passe if id(p) in paris_m3(passe, depuis=DEBUT_ETUDE)],
         [p for p in futur if id(p) in paris_m3(paris)]),
    ):
        if nom in laboratoire.get("comparateurs", {}):
            enregistrer(nom, historique, a_venir)

    champs = CHAMPS_FICHE + ("simulation", "id")
    return {
        "selections": selection,
        "paris": {pid: {**{k: index[pid].get(k) for k in champs},
                        "sims": [index[pid].get("simulation")],
                        "strategie": False, "chatgpt": False, "gemini": False, "trace": []}
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
        # Calcul dynamique du rejeu Gemini Argon v1 s'il n'est pas encore dans comparaison-strategies.json
        if "Gemini Argon v1 (rejeu)" not in laboratoire.get("comparateurs", {}):
            releve_dt = heure(releve_str) or heure(maintenant)
            passe_gem = [p for p in paris if heure(p.get("detecte")) and heure(p["detecte"]) <= releve_dt]
            gem_rejeu_ids = paris_gemini(passe_gem, depuis=DEBUT_ETUDE)
            gem_rows = [p for p in passe_gem if id(p) in gem_rejeu_ids]
            gem_ens = [p for p in gem_rows if heure(DEBUT_ETUDE) <= heure(p["debut"]) < heure(PERIODES[-1][2])]
            laboratoire.setdefault("comparateurs", {})["Gemini Argon v1 (rejeu)"] = {
                **evaluer(gem_rows, releve_str),
                "ensemble": resume(gem_ens, releve_str, incertitude=False),
            }
        laboratoire["navigation"] = navigation_strategies(paris, laboratoire, maintenant)
        laboratoire["resultats"] = [{k: v for k, v in r.items() if k != "ids_selections"}
                                    for r in laboratoire["resultats"]]
        laboratoire.update(debut_suivi=DEBUT_SUIVI, futur=suivi_futur(paris, DEBUT_SUIVI, maintenant))
        gemini_ids = paris_gemini(paris)
        officiels = {
            "Claude (rejeu)": paris_strategie(paris),
            "ChatGPT v1 (rejeu)": paris_chatgpt(paris),
            "Gemini Argon v1 (rejeu)": gemini_ids,
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
        laboratoire["comparateurs_futur"] = {
            nom: resume([p for p in paris if id(p) in ids and heure(p.get("detecte"))
                         and heure(DEBUT_SUIVI) <= heure(p["detecte"]) < heure(maintenant)],
                        maintenant, incertitude=False) for nom, ids in officiels.items()}
        ids_labo = {i for r in laboratoire["futur"] for i in r["ids_recents"]}
        laboratoire["paris_recents"] = [{k: p.get(k) for k in (
            "id", "domicile", "exterieur", "bookmaker", "pari", "cote", "ecart",
            "detecte", "debut", "statut", "gain")} for p in paris if p["id"] in ids_labo]
    data = {"paris": liste, "fiches_total": fiches_total, "valeurs_filtres": valeurs, "etat": etat, "actuelles": actuelles[:300], "bilan": bilan(paris),
            "bilan_tranches": bilan_tranches(paris), "courbes": courbes
