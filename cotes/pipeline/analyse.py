"""Analyse du cycle (déplacée de scripts/cycle.py, E3.3) : association des matchs, historique des références,
contrôle des intitulés, comparaison, props, mouvement de la cote juste et écarts d'affichage."""
from __future__ import annotations

from cotes import comparaison, controle, echecs, historiques
from cotes.depot.json_io import ecrire_json
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
    ctx.index, ctx.etat_controle, ctx.opportunites = index, etat_controle, opportunites
