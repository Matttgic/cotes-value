"""Catalogue des fichiers de la branche « donnees » et des caches Actions (docs/architecture-cible.md, E1.3).

Une entrée par fichier (ou motif) : zone, format exact, écrivains, lecteurs, rétention. Aucun module ne lit ce
catalogue pour l'instant : il décrit l'existant. `tests/test_catalogue.py` refuse un fichier écrit sans y être
déclaré, un fichier obsolète (`scripts/cycle.py › FICHIERS_OBSOLETES`) et une entrée morte.

    python -m cotes.depot.catalogue --markdown     # tableau de docs/donnees.md

Zones : ``chaud`` (racine de « donnees », réécrit), ``froid`` (« donnees », ajout seul ou archives), ``memoire``
(cache Actions ``memoire/``, gzip, sauvé après un push réussi), ``reprise`` et ``envoyes`` (caches toujours sauvés).
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field

ZONES = ("chaud", "froid", "memoire", "reprise", "envoyes")


@dataclass(frozen=True)
class Fichier:
    zone: str
    format: str
    ecrivains: list[str]
    lecteurs: list[str] = field(default_factory=list)
    retention: str = "réécrit à chaque passage"


_JSON = "json indent=1, UTF-8 (ensure_ascii=False)"
_COMPACT = "json compact (separators=(',', ':')), UTF-8"
_JSONL_GZ = "jsonl gzip, ajout par membre gzip niveau 9 (historiques.ajouter_gzip)"
_MEMOIRE = "json compact gzip niveau 5, mtime 0 (memoire.ecrire)"
_CYCLE = "scripts/cycle.py"
_SITE = "scripts/site_web.py"
_ALERTES = "scripts/envoyer_notifications.py"

FICHIERS: dict[str, Fichier] = {
    # --- chaud : racine de « donnees »
    "paris.json": Fichier("chaud", _JSON, [_CYCLE], [_SITE, _ALERTES, "cotes/recap_jouables.py", "études"],
                          "paris réglés depuis moins de 30 jours (stockage.archiver)"),
    "etat.json": Fichier("chaud", _JSON, [_CYCLE, "cotes/echecs.py"], [_SITE, _ALERTES],
                         "dernier cycle, journal du règlement, 200 derniers cycles"),
    "controle.json": Fichier("chaud", "json compact, UTF-8 (ecrire_json compact)", [_CYCLE], [_CYCLE, _SITE],
                             "publié au plus toutes les 55 min ; groupes mesurés depuis 30 jours"),
    "opportunites_actuelles.json": Fichier("chaud", _JSON, [_CYCLE], [_SITE, _ALERTES]),
    "marches_inconnus.json": Fichier("chaud", _JSON, [_CYCLE], [_SITE], "relevés cumulés (inconnus.fusionner)"),
    "props_joueurs.json": Fichier("chaud", "json compact, UTF-8 (ecrire_json compact)", [_CYCLE], [_SITE]),
    "surebets.json": Fichier("chaud", _COMPACT, [_CYCLE], [_SITE, _ALERTES, _CYCLE],
                             "surebets du cycle ; épisodes des 21 derniers jours (2 500 au plus)"),
    "boosts.json": Fichier("chaud", _COMPACT, [_CYCLE], [_SITE, _ALERTES, _CYCLE],
                           "boosts du cycle ; épisodes des 30 derniers jours (1 500 au plus)"),
    "euria.json": Fichier("chaud", _COMPACT, [_CYCLE], [_SITE, _ALERTES, _CYCLE],
                          "page Euria : milieux et conversions de freebets du cycle (300 publiés, tous suivis) ; "
                          "milieux pas encore réglés (60 jours, 10 000 au plus)"),
    "props_papier.json": Fichier("chaud", _COMPACT, ["cotes/props_papier.py"], [_CYCLE, _SITE]),
    "persistance_qwen.json": Fichier("chaud", _JSON, [_CYCLE], [_CYCLE]),
    "resultats_manuels.json": Fichier("chaud", "json écrit à la main", ["à la main"], [_CYCLE, "études"],
                                      "permanent ; « supprime » retire un pari"),
    "resultats_a_saisir.json": Fichier("chaud", _JSON, [_CYCLE], [_SITE]),
    "boosts_resultats.json": Fichier("chaud", _JSON, ["scripts/regler_boosts.py"], [_SITE],
                                     "permanent ; résultats des boosts saisis à la main"),
    "theodds.json": Fichier("chaud", _JSON, [_CYCLE], [_CYCLE], "budget du jour (The Odds API)"),
    "thesportsdb.json": Fichier("chaud", _JSON, [_CYCLE], [_CYCLE], "budget du jour (TheSportsDB)"),
    "propline.json": Fichier("chaud", _JSON, [_CYCLE], [_CYCLE], "budget du jour (PropLine)"),
    "pinnacle_secours.json": Fichier("chaud", _JSON, ["cotes/pinnacle_secours.py"], ["cotes/pinnacle_secours.py"],
                                     "budget du jour des secours Pinnacle"),
    "sante_alertes.json": Fichier("chaud", _JSON, ["cotes/surveillance.py"], ["cotes/surveillance.py"]),
    "sante_incidents.json": Fichier("chaud", _JSON, ["cotes/surveillance.py"], [_SITE], "incidents ouverts"),
    "sante_historique.json": Fichier("chaud", _JSON, ["cotes/surveillance.py"], ["cotes/surveillance.py"],
                                     "incidents clos (surveillance.archiver)"),
    "notifications_diagnostic.json": Fichier("chaud", _JSON, [_ALERTES], [_SITE], "derniers cycles d'alertes"),
    "pushover_envoyes.json": Fichier("chaud", _JSON, [_ALERTES], [_ALERTES, "scripts/envoyes_secours.py"],
                                     "dédoublonnage des alertes Pushover"),
    "webhook_envoyes.json": Fichier("chaud", _JSON, [_ALERTES], [_ALERTES, "scripts/envoyes_secours.py"],
                                    "dédoublonnage des alertes webhook"),
    "pushover_recap.json": Fichier("chaud", _JSON, [_ALERTES], ["cotes/recap_jouables.py"],
                                   "dernier récapitulatif envoyé"),
    "bankroll.json": Fichier("chaud", _JSON, [_ALERTES], [_ALERTES], "bankroll automatique des alertes Pushover"),
    "recommandees.json": Fichier("chaud", _COMPACT, ["cotes/recommandations.py"],
                                 [_SITE, "cotes/strategie_recommandee.py"], "revue tous les 7 jours"),
    "notes_historique.json": Fichier("chaud", _COMPACT, ["cotes/notation.py"], [_SITE],
                                     "une note par jour (heure de Paris)"),
    "pauses.json": Fichier("chaud", _COMPACT, ["cotes/pauses.py"], [_CYCLE, _SITE, _ALERTES]),
    "protocole.json": Fichier("chaud", _JSON + " + saut de ligne final", ["cotes/protocole.py"], [_SITE],
                              "lectures du protocole, écrites une seule fois"),
    "pannes_strategies.json": Fichier("chaud", _COMPACT, ["cotes/protection.py"], ["cotes/protection.py"],
                                      "échecs consécutifs par stratégie"),
    "serveur_direct.json": Fichier("chaud", _JSON, ["scripts/serveur_direct.py"],
                                   ["scripts/serveur_actif.py", _ALERTES, "cotes/direct/betfair.py"],
                                   "battement du serveur en direct"),
    # --- froid : un fichier par jour UTC en ajout seul, archives
    "cotes/*.jsonl.gz": Fichier("froid", _JSONL_GZ, ["cotes/historiques.py"], ["études"],
                                "permanent ; mois passés aussi en release (archivage-donnees.yml)"),
    "references/*.jsonl.gz": Fichier("froid", _JSONL_GZ, ["cotes/historiques.py"], ["études"],
                                     "jours du 12 au 15/11/2026 seulement (ensuite en mémoire puis en release) ; "
                                     "archivage mensuel"),
    "releves/*.jsonl.gz": Fichier("froid", _JSONL_GZ, ["cotes/historiques.py"], ["études"], "permanent"),
    "correspondances/*.jsonl.gz": Fichier("froid", _JSONL_GZ, ["cotes/historiques.py"], ["études"], "permanent"),
    "opportunites/*.jsonl.gz": Fichier("froid", _JSONL_GZ, [_CYCLE],
                                       ["cotes/recap_jouables.py", "cotes/analyse_marche/lecture.py", "études"],
                                       "permanent ; mois passés aussi en release"),
    "euria_regles.json": Fichier("chaud", _COMPACT, ["à la main (25/11/2026)"], [_SITE, _CYCLE],
                                 "ancienne archive des milieux réglés : versée dans euria_regles/ puis supprimée par le cycle"),
    "euria_regles/*.json": Fichier("froid", _COMPACT, [_CYCLE], [_SITE, _CYCLE],
                                   "permanent : milieux réglés de la page Euria, un fichier par mois du match"),
    "archives/paris-*.json.gz": Fichier("froid", "json gzip (stockage.archiver)", ["cotes/stockage.py"],
                                        [_SITE, _CYCLE, "études"], "permanent : paris réglés depuis plus de 30 jours"),
    # --- mémoire de travail (cache Actions memoire/, MEMOIRE_CHEMIN)
    "memoire/horizon_direct.json.gz": Fichier("memoire", _MEMOIRE, [_CYCLE], [_CYCLE],
                                              "réserves des lecteurs directs, props, historique des cotes"),
    "memoire/controle.json.gz": Fichier("memoire", _MEMOIRE, [_CYCLE], [_CYCLE], "contrôle de chaque cycle"),
    "memoire/smarkets_cache.json.gz": Fichier("memoire", _MEMOIRE, [_CYCLE], [_CYCLE], "Smarkets relu toutes les 15 min"),
    "memoire/pinnacle_secours_cache.json.gz": Fichier("memoire", _MEMOIRE, ["cotes/pinnacle_secours.py"],
                                                      ["cotes/pinnacle_secours.py"]),
    "memoire/derive_sources.json.gz": Fichier("memoire", _MEMOIRE, ["cotes/derive.py"], ["cotes/derive.py"]),
    "memoire/historique_references.json.gz": Fichier("memoire", _MEMOIRE, ["cotes/historiques.py"],
                                                     ["cotes/historiques.py"], "dernières cotes de référence écrites"),
    "memoire/historique_correspondances.json.gz": Fichier("memoire", _MEMOIRE, ["cotes/historiques.py"],
                                                          ["cotes/historiques.py"], "derniers rapprochements écrits"),
    "memoire/references/*.jsonl.gz": Fichier("memoire", _JSONL_GZ, ["cotes/historiques.py"],
                                             ["cotes/depot/references.py"],
                                             "jour UTC en cours ; jour terminé publié en release « references-AAAA-MM » "
                                             "(python -m cotes references), puis retiré"),
    # --- reprise (cache Actions reprise/, REPRISE_CHEMIN)
    "reprise/derniere_lecture.json.gz": Fichier("reprise", "json gzip (reprise.ecrire)", ["cotes/reprise.py"],
                                                ["cotes/reprise.py"], "dernier bon passage de chaque sport"),
    "reprise/sports_cycle.json": Fichier("reprise", _JSON, [_CYCLE], [_CYCLE], "sports vus depuis 2 heures"),
    "reprise/ancres_mouvement.json.gz": Fichier("reprise", "json gzip (mouvement.ecrire)", ["cotes/mouvement.py"],
                                                ["cotes/mouvement.py"], "cote juste de départ de chaque sélection"),
    "reprise/stats_mouvement.json.gz": Fichier("reprise", "json gzip (mouvement.ecrire)", ["cotes/mouvement.py"],
                                               ["cotes/mouvement.py"], "moyenne et variance des mouvements par marché (z-score)"),
    # --- envoyes (cache Actions envoyes/) : copie de secours si le push échoue
    "envoyes/pushover_envoyes.json": Fichier("envoyes", _JSON, ["scripts/envoyes_secours.py"],
                                             ["scripts/envoyes_secours.py"]),
    "envoyes/webhook_envoyes.json": Fichier("envoyes", _JSON, ["scripts/envoyes_secours.py"],
                                            ["scripts/envoyes_secours.py"]),
}


def markdown() -> str:
    lignes = ["| Fichier | Zone | Format | Écrit par | Lu par | Rétention |", "|---|---|---|---|---|---|"]
    for nom, f in FICHIERS.items():
        lignes.append(f"| `{nom}` | {f.zone} | {f.format} | {', '.join(f.ecrivains)} | {', '.join(f.lecteurs)} | "
                      f"{f.retention} |")
    return "\n".join(lignes)


def main(argv=None) -> int:
    a = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    a.add_argument("--markdown", action="store_true", help="tableau Markdown du catalogue")
    a.parse_args(argv)
    sys.stdout.write(markdown() + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
