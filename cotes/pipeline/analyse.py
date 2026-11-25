"""Analyse du cycle (déplacée de scripts/cycle.py, E3.3) : association des matchs, historique des références,
contrôle des intitulés, comparaison, props, mouvement de la cote juste, écarts d'affichage et surebets."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from cotes import boosts, comparaison, controle, echecs, historiques, surebets
from cotes.depot.json_io import ecrire_json, lire_json
from cotes.pipeline.contexte import Contexte
from cotes.pipeline.outils import etape
from cotes.pipeline.sauvegarde import lire_controle
from cotes.sources import registre as registre_sources


def analyser(ctx: Contexte) -> None:
    """Remplit ``ctx.index``, ``ctx.etat_controle`` et ``ctx.opportunites`` ; écrit props_joueurs.json et
    props_papier.json."""
    donnees, maintenant, journal = ctx.donnees, ctx.maintenant, ctx.journal
    francais, references, hors = ctx.francais, ctx.references, ctx.hors_consensus
    pin, poly, sm_lignes = ctx.pinnacle, ctx.polymarket, ctx.smarkets
    # 3. contrôle de conformité des marchés (cumulé d'un cycle à l'autre), comparaison et paris simulés :
    #    seules les cotes dont l'intitulé est contrôlé conforme peuvent donner un pari.
    #    Le contrôle reste celui des références déjà en place : Smarkets a sa table,
    #    pas une nouvelle mesure de conformité.
    index = etape("association", journal, comparaison.indexer, francais, references) or {}
    if comparaison.ERREURS_INDEX:          # une référence défaillante, les autres associées quand même
        journal["association_erreurs"] = dict(comparaison.ERREURS_INDEX)
    try:            # historique des références, relevé des sources et rapprochements : jamais bloquant
        journal["historique_references"] = historiques.enregistrer(donnees, francais, references, index,
                                                                              maintenant)
    except Exception as e:  # noqa: BLE001
        journal["historique_references"] = {"erreur": echecs.noter(journal, "historique_references", e, maintenant)}
    index_controle = {n: v for n, v in index.items() if n not in registre_sources.hors_controle()}
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
    from cotes import props as props_joueurs
    rapproches = props_joueurs.comparer(francais, references) or []
    journal["props_joueurs"] = {
        **props_joueurs.compter(list(pin) + list(francais)),
        "rapproches": len(rapproches),
        "valeur": sum(1 for r in rapproches if r.get("valeur")),
    }
    ecrire_json(donnees / "props_joueurs.json",
                {"maj": journal["debut"], "lignes": rapproches}, compact=True)
    from cotes import props_papier
    papier = props_papier.lire(donnees)
    seuil_props = props_papier.seuil()
    journal["props_papier"] = {
        "seuil": seuil_props,
        "nouveaux": props_papier.enregistrer(papier, rapproches, maintenant, seuil_props),
        "clotures": props_papier.clotures(papier, pin, maintenant),
        "polymarket": props_papier.verdict_polymarket(poly),
    }
    papier["polymarket"] = journal["props_papier"]["polymarket"]
    papier["fanduel"] = journal.get("props_fanduel") or {}
    papier["draftkings"] = {"props": journal.get("props_draftkings") or {}, "matchs": journal.get("matchs_draftkings") or {},
                            "lecture": journal.get("draftkings") or {}}
    props_papier.ecrire(donnees, papier)
    for o in opportunites:           # marqueur de cycle : sert à la persistance (Qwen) et au diagnostic
        o["cycle_id"] = journal["debut"]
    # Mouvement de la cote juste de Pinnacle (dropping odds), inscrit dans le pari. Garde-fou : une cote Pinnacle de
    # référence inchangée depuis 10 min ou plus (copie de cache figée) rend l'opportunité suspecte, avant le placement.
    from cotes import mouvement
    journal["mouvement"] = mouvement.annoter(
        opportunites, index,
        ctx.reprise.with_name("ancres_mouvement.json.gz") if ctx.reprise else None, maintenant)
    # Écarts d'affichage, y compris quand Smarkets ne décide pas. Avant le placement :
    # le pari enregistre les trois champs.
    # L'index de l'association contient déjà Polymarket et Smarkets (mêmes lignes) : pas de seconde association.
    references_ecarts = {"Polymarket": poly, "Smarkets": sm_lignes}
    comparaison.annoter_ecarts(opportunites, francais, references_ecarts,
                               index={n: index[n] for n in references_ecarts
                                      if n in index and references.get(n) is references_ecarts[n]})
    # Surebets entre bookmakers français : mêmes cotes, même association, même contrôle des intitulés.
    journal["surebets"] = surebets_du_cycle(donnees, francais, index, (etat_controle, suspects), journal)
    # Cotes boostées comparées à la cote juste (cycle complet seulement : quelques demandes réseau de plus).
    if ctx.mode == "complet" and os.environ.get("SOURCE_BOOSTS", "direct").strip().lower() != "off":
        journal["boosts"] = boosts_du_cycle(donnees, francais, index, journal, controle=(etat_controle, suspects))
    # Page Euria : milieux en value et meilleures conversions de freebets (cotes/euria.py).
    journal["euria"] = euria_du_cycle(donnees, francais, index, (etat_controle, suspects), journal)
    ctx.index, ctx.etat_controle, ctx.opportunites = index, etat_controle, opportunites


def surebets_du_cycle(donnees: Path, francais: list[dict], index: dict, controle_du_cycle: tuple[dict, dict],
                      journal: dict, maintenant: datetime | None = None) -> dict:
    """Détecte les surebets du cycle, met à jour leurs épisodes et écrit ``surebets.json``. Jamais bloquant.

    Heure de détection : l'heure réelle (les cotes françaises sont lues après le début du cycle)."""
    try:
        maintenant = maintenant or datetime.now(timezone.utc)
        actuels, bilan = surebets.detecter(francais, index, maintenant, controle_du_cycle)
        etat = surebets.suivre(lire_json(donnees / "surebets.json", {}), actuels, maintenant)
        ecrire_json(donnees / "surebets.json", surebets.publier(actuels, etat, maintenant, bilan), compact=True)
        return {"surebets": bilan["surebets"], "suspects": bilan["suspects"],
                "verifies": sum(bool(s.get("verifie")) for s in actuels if not s.get("suspect")),
                "familles": bilan["familles"]}
    except Exception as e:  # noqa: BLE001 - un surebet ne doit jamais arrêter le cycle
        return {"erreur": echecs.noter(journal, "surebets", e, maintenant)}


def euria_du_cycle(donnees: Path, francais: list[dict], index: dict, controle_du_cycle: tuple[dict, dict] | None,
                   journal: dict, maintenant: datetime | None = None) -> dict:
    """Milieux et conversions de freebets du cycle, écrits dans ``euria.json`` (page Euria). Jamais bloquant."""
    try:
        from cotes import euria
        maintenant = maintenant or datetime.now(timezone.utc)
        calcul = euria.calculer(francais, index, maintenant, controle_du_cycle)
        etat = lire_json(donnees / "euria.json", {})
        etat = etat if isinstance(etat, dict) else {}
        # milieux réglés : archivés d'abord (euria_regles/AAAA-MM.json, gardés pour toujours), retirés de euria.json
        # ensuite ; l'archive d'un seul fichier du 25/11 (euria_regles.json) est versée dans les mois puis supprimée
        regles = [e for e in etat.get("episodes_milieux") or [] if isinstance(e, dict) and e.get("cle") and "resultat_100" in e]
        ancienne = lire_json(donnees / "euria_regles.json", None)
        if isinstance(ancienne, dict):
            regles += [e for e in ancienne.get("episodes") or [] if isinstance(e, dict)]
        modifies, archives = euria.archiver({m: lire_json(donnees / "euria_regles" / f"{m}.json", {})
                                             for m in {euria.mois(e) for e in regles}}, regles, maintenant)
        for m, doc in modifies.items():
            ecrire_json(donnees / "euria_regles" / f"{m}.json", doc, compact=True)
        if ancienne is not None:
            (donnees / "euria_regles.json").unlink()
        episodes = euria.suivre(etat, calcul["milieux"], maintenant, {e["cle"] for e in regles})
        ecrire_json(donnees / "euria.json", euria.publier(calcul, episodes, maintenant), compact=True)
        value = sum(1 for m in calcul["milieux"] if m.get("en_value", True))
        return {"milieux": value, "hors_value": len(calcul["milieux"]) - value,
                "conversions": sum(len(x) for x in calcul["conversions"].values()), "archives": archives}
    except Exception as e:  # noqa: BLE001 - la page Euria ne doit jamais arrêter le cycle
        return {"erreur": echecs.noter(journal, "euria", e, maintenant)}


def boosts_du_cycle(donnees: Path, francais: list[dict], index: dict, journal: dict,
                    lire=None, maintenant: datetime | None = None, controle: tuple[dict, dict] | None = None) -> dict:
    """Lit les boosts (Winamax, Unibet, NetBet, OlyBet), les évalue, cherche ceux qu'on peut couvrir pour un gain
    garanti, met à jour leurs épisodes et écrit ``boosts.json``. Jamais bloquant.
    ``lire`` remplace la lecture réseau (tests) ; ``controle`` : contrôle des intitulés du cycle (couvertures)."""
    try:
        from cotes.direct import boosts_sites
        maintenant = maintenant or datetime.now(timezone.utc)
        lus, erreurs = (lire or (lambda: boosts_sites.lire_tous(maintenant)))()
        actuels = boosts.evaluer(lus, francais, index, maintenant)
        precedent = lire_json(donnees / "boosts.json", {})
        etat = boosts.suivre(precedent, actuels, maintenant)
        couverts = boosts.couverts(actuels, francais, index, maintenant, controle)
        etat["episodes_couverts"] = boosts.suivre_couverts(precedent, couverts, maintenant)
        par_book: dict[str, int] = {}
        for b in lus:
            par_book[b.get("bookmaker")] = par_book.get(b.get("bookmaker"), 0) + 1
        bilan = {"lus": len(lus), "evalues": sum(b.get("value") is not None for b in actuels),
                 "couverts": sum(not c.get("suspect") for c in couverts), "par_bookmaker": par_book, "erreurs": erreurs}
        ecrire_json(donnees / "boosts.json", boosts.publier(actuels, etat, maintenant, bilan, couverts), compact=True)
        return bilan
    except Exception as e:  # noqa: BLE001 - un boost ne doit jamais arrêter le cycle
        return {"erreur": echecs.noter(journal, "boosts", e, maintenant)}
