"""Prise des paris du cycle (déplacée de scripts/cycle.py, E3.4) : chargement des paris, retrait des supprimés,
placement, fusions, pauses, décisions figées, redécision, Qwen, suivi des prix et de la clôture."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from cotes import comparaison, echecs, simulation, stockage
from cotes.depot.json_io import ecrire_json, lire_json
from cotes.pipeline.contexte import Contexte
from cotes.pipeline.outils import charger_paris, etape


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


def prendre(ctx: Contexte) -> None:
    """Remplit ``ctx.paris`` (paris de paris.json, suivis) et ``ctx.nouveaux`` (paris pris à ce cycle)."""
    donnees, maintenant, journal = ctx.donnees, ctx.maintenant, ctx.journal
    opportunites, francais, index, hors = ctx.opportunites, ctx.francais, ctx.index, ctx.hors_consensus
    paris = charger_paris(donnees, journal)
    # paris annulés à la main (pris sur un match mal associé) : « supprime » dans resultats_manuels.json
    manuels = lire_json(donnees / "resultats_manuels.json", {})
    paris = [p for p in paris if manuels.get(p["id"]) != "supprime"]
    nouveaux = simulation.placer(opportunites, paris)
    from cotes.decisions import figer_nouveaux, redecider_ouverts
    from cotes.strategie_recommandee import charger_fusions
    charger_fusions(donnees)          # fusions automatiques actives : leurs prises sont notées avec les autres
    from cotes import pauses
    pauses.charger(donnees)           # stratégies en pause (pauses.json) : plus de nouveaux paris
    registre = stockage.fusionner_paris(paris, stockage.lire_archives(donnees))
    figer_nouveaux(registre, nouveaux)
    redecider(registre, maintenant, journal, redecider_ouverts)
    suivre_qwen(donnees, registre, opportunites, maintenant, journal)
    simulation.suivre_prix(paris, francais)
    prudentes: set[tuple] = set()     # clôtures lues au prix d'achat de Polymarket : CLV minimale
    justes = etape("cotes_cloture", journal, comparaison.cotes_justes_depuis, index,
                   hors_consensus=hors, prudentes=prudentes) or {}
    simulation.suivre_cloture(paris, justes, prudentes=prudentes)      # heure réelle : un match peut commencer pendant le cycle
    ctx.paris, ctx.nouveaux = paris, nouveaux
