# Fichiers de « donnees » et des caches

Tableau produit par `python -m cotes.depot.catalogue --markdown` (source : `cotes/depot/catalogue.py`). Un fichier
écrit sous « donnees » ou dans la mémoire sans être déclaré fait échouer `tests/test_catalogue.py`.

Zones : **chaud** (racine de la branche, réécrit), **froid** (branche, ajout seul ou archives), **memoire** (cache
Actions `memoire/`, sauvé après un push réussi), **reprise** et **envoyes** (caches Actions toujours sauvés).

Depuis le 15/11/2026, `references/` n'est plus dans la branche : le jour en cours est dans `memoire/references/`,
chaque jour terminé dans la release GitHub `references-AAAA-MM`. Pour une étude :
`python -m cotes references --telecharger donnees/references` (option `--mois AAAA-MM`).

| Fichier | Zone | Format | Écrit par | Lu par | Rétention |
|---|---|---|---|---|---|
| `paris.json` | chaud | json indent=1, UTF-8 (ensure_ascii=False) | scripts/cycle.py | scripts/site_web.py, scripts/envoyer_notifications.py, cotes/recap_jouables.py, études | paris réglés depuis moins de 30 jours (stockage.archiver) |
| `etat.json` | chaud | json indent=1, UTF-8 (ensure_ascii=False) | scripts/cycle.py, cotes/echecs.py | scripts/site_web.py, scripts/envoyer_notifications.py | dernier cycle, journal du règlement, 200 derniers cycles |
| `controle.json` | chaud | json compact, UTF-8 (ecrire_json compact) | scripts/cycle.py | scripts/cycle.py, scripts/site_web.py | publié au plus toutes les 55 min ; groupes mesurés depuis 30 jours |
| `opportunites_actuelles.json` | chaud | json indent=1, UTF-8 (ensure_ascii=False) | scripts/cycle.py | scripts/site_web.py, scripts/envoyer_notifications.py | réécrit à chaque passage |
| `marches_inconnus.json` | chaud | json indent=1, UTF-8 (ensure_ascii=False) | scripts/cycle.py | scripts/site_web.py | relevés cumulés (inconnus.fusionner) |
| `props_joueurs.json` | chaud | json compact, UTF-8 (ecrire_json compact) | scripts/cycle.py | scripts/site_web.py | réécrit à chaque passage |
| `surebets.json` | chaud | json compact (separators=(',', ':')), UTF-8 | scripts/cycle.py | scripts/site_web.py, scripts/envoyer_notifications.py, scripts/cycle.py | surebets du cycle ; épisodes des 21 derniers jours (2 500 au plus) |
| `boosts.json` | chaud | json compact (separators=(',', ':')), UTF-8 | scripts/cycle.py | scripts/site_web.py, scripts/envoyer_notifications.py, scripts/cycle.py | boosts du cycle ; épisodes des 30 derniers jours (1 500 au plus) |
| `euria.json` | chaud | json compact (separators=(',', ':')), UTF-8 | scripts/cycle.py | scripts/site_web.py, scripts/envoyer_notifications.py, scripts/cycle.py | page Euria : milieux et conversions de freebets du cycle ; épisodes des milieux (21 jours) |
| `props_papier.json` | chaud | json compact (separators=(',', ':')), UTF-8 | cotes/props_papier.py | scripts/cycle.py, scripts/site_web.py | réécrit à chaque passage |
| `persistance_qwen.json` | chaud | json indent=1, UTF-8 (ensure_ascii=False) | scripts/cycle.py | scripts/cycle.py | réécrit à chaque passage |
| `resultats_manuels.json` | chaud | json écrit à la main | à la main | scripts/cycle.py, études | permanent ; « supprime » retire un pari |
| `resultats_a_saisir.json` | chaud | json indent=1, UTF-8 (ensure_ascii=False) | scripts/cycle.py | scripts/site_web.py | réécrit à chaque passage |
| `theodds.json` | chaud | json indent=1, UTF-8 (ensure_ascii=False) | scripts/cycle.py | scripts/cycle.py | budget du jour (The Odds API) |
| `thesportsdb.json` | chaud | json indent=1, UTF-8 (ensure_ascii=False) | scripts/cycle.py | scripts/cycle.py | budget du jour (TheSportsDB) |
| `propline.json` | chaud | json indent=1, UTF-8 (ensure_ascii=False) | scripts/cycle.py | scripts/cycle.py | budget du jour (PropLine) |
| `pinnacle_secours.json` | chaud | json indent=1, UTF-8 (ensure_ascii=False) | cotes/pinnacle_secours.py | cotes/pinnacle_secours.py | budget du jour des secours Pinnacle |
| `sante_alertes.json` | chaud | json indent=1, UTF-8 (ensure_ascii=False) | cotes/surveillance.py | cotes/surveillance.py | réécrit à chaque passage |
| `sante_incidents.json` | chaud | json indent=1, UTF-8 (ensure_ascii=False) | cotes/surveillance.py | scripts/site_web.py | incidents ouverts |
| `sante_historique.json` | chaud | json indent=1, UTF-8 (ensure_ascii=False) | cotes/surveillance.py | cotes/surveillance.py | incidents clos (surveillance.archiver) |
| `notifications_diagnostic.json` | chaud | json indent=1, UTF-8 (ensure_ascii=False) | scripts/envoyer_notifications.py | scripts/site_web.py | derniers cycles d'alertes |
| `pushover_envoyes.json` | chaud | json indent=1, UTF-8 (ensure_ascii=False) | scripts/envoyer_notifications.py | scripts/envoyer_notifications.py, scripts/envoyes_secours.py | dédoublonnage des alertes Pushover |
| `webhook_envoyes.json` | chaud | json indent=1, UTF-8 (ensure_ascii=False) | scripts/envoyer_notifications.py | scripts/envoyer_notifications.py, scripts/envoyes_secours.py | dédoublonnage des alertes webhook |
| `pushover_recap.json` | chaud | json indent=1, UTF-8 (ensure_ascii=False) | scripts/envoyer_notifications.py | cotes/recap_jouables.py | dernier récapitulatif envoyé |
| `recommandees.json` | chaud | json compact (separators=(',', ':')), UTF-8 | cotes/recommandations.py | scripts/site_web.py, cotes/strategie_recommandee.py | revue tous les 7 jours |
| `notes_historique.json` | chaud | json compact (separators=(',', ':')), UTF-8 | cotes/notation.py | scripts/site_web.py | une note par jour (heure de Paris) |
| `pauses.json` | chaud | json compact (separators=(',', ':')), UTF-8 | cotes/pauses.py | scripts/cycle.py, scripts/site_web.py, scripts/envoyer_notifications.py | réécrit à chaque passage |
| `protocole.json` | chaud | json indent=1, UTF-8 (ensure_ascii=False) + saut de ligne final | cotes/protocole.py | scripts/site_web.py | lectures du protocole, écrites une seule fois |
| `pannes_strategies.json` | chaud | json compact (separators=(',', ':')), UTF-8 | cotes/protection.py | cotes/protection.py | échecs consécutifs par stratégie |
| `serveur_direct.json` | chaud | json indent=1, UTF-8 (ensure_ascii=False) | scripts/serveur_direct.py | scripts/serveur_actif.py, scripts/envoyer_notifications.py, cotes/direct/betfair.py | battement du serveur en direct |
| `cotes/*.jsonl.gz` | froid | jsonl gzip, ajout par membre gzip niveau 9 (historiques.ajouter_gzip) | cotes/historiques.py | études | permanent ; mois passés aussi en release (archivage-donnees.yml) |
| `references/*.jsonl.gz` | froid | jsonl gzip, ajout par membre gzip niveau 9 (historiques.ajouter_gzip) | cotes/historiques.py | études | jours du 12 au 15/11/2026 seulement (ensuite en mémoire puis en release) ; archivage mensuel |
| `releves/*.jsonl.gz` | froid | jsonl gzip, ajout par membre gzip niveau 9 (historiques.ajouter_gzip) | cotes/historiques.py | études | permanent |
| `correspondances/*.jsonl.gz` | froid | jsonl gzip, ajout par membre gzip niveau 9 (historiques.ajouter_gzip) | cotes/historiques.py | études | permanent |
| `opportunites/*.jsonl.gz` | froid | jsonl gzip, ajout par membre gzip niveau 9 (historiques.ajouter_gzip) | scripts/cycle.py | cotes/recap_jouables.py, cotes/analyse_marche/lecture.py, études | permanent ; mois passés aussi en release |
| `archives/paris-*.json.gz` | froid | json gzip (stockage.archiver) | cotes/stockage.py | scripts/site_web.py, scripts/cycle.py, études | permanent : paris réglés depuis plus de 30 jours |
| `memoire/horizon_direct.json.gz` | memoire | json compact gzip niveau 5, mtime 0 (memoire.ecrire) | scripts/cycle.py | scripts/cycle.py | réserves des lecteurs directs, props, historique des cotes |
| `memoire/controle.json.gz` | memoire | json compact gzip niveau 5, mtime 0 (memoire.ecrire) | scripts/cycle.py | scripts/cycle.py | contrôle de chaque cycle |
| `memoire/smarkets_cache.json.gz` | memoire | json compact gzip niveau 5, mtime 0 (memoire.ecrire) | scripts/cycle.py | scripts/cycle.py | Smarkets relu toutes les 15 min |
| `memoire/pinnacle_secours_cache.json.gz` | memoire | json compact gzip niveau 5, mtime 0 (memoire.ecrire) | cotes/pinnacle_secours.py | cotes/pinnacle_secours.py | réécrit à chaque passage |
| `memoire/derive_sources.json.gz` | memoire | json compact gzip niveau 5, mtime 0 (memoire.ecrire) | cotes/derive.py | cotes/derive.py | réécrit à chaque passage |
| `memoire/historique_references.json.gz` | memoire | json compact gzip niveau 5, mtime 0 (memoire.ecrire) | cotes/historiques.py | cotes/historiques.py | dernières cotes de référence écrites |
| `memoire/historique_correspondances.json.gz` | memoire | json compact gzip niveau 5, mtime 0 (memoire.ecrire) | cotes/historiques.py | cotes/historiques.py | derniers rapprochements écrits |
| `memoire/references/*.jsonl.gz` | memoire | jsonl gzip, ajout par membre gzip niveau 9 (historiques.ajouter_gzip) | cotes/historiques.py | cotes/depot/references.py | jour UTC en cours ; jour terminé publié en release « references-AAAA-MM » (python -m cotes references), puis retiré |
| `reprise/derniere_lecture.json.gz` | reprise | json gzip (reprise.ecrire) | cotes/reprise.py | cotes/reprise.py | dernier bon passage de chaque sport |
| `reprise/sports_cycle.json` | reprise | json indent=1, UTF-8 (ensure_ascii=False) | scripts/cycle.py | scripts/cycle.py | sports vus depuis 2 heures |
| `reprise/ancres_mouvement.json.gz` | reprise | json gzip (mouvement.ecrire) | cotes/mouvement.py | cotes/mouvement.py | cote juste de départ de chaque sélection |
| `reprise/stats_mouvement.json.gz` | reprise | json gzip (mouvement.ecrire) | cotes/mouvement.py | cotes/mouvement.py | moyenne et variance des mouvements par marché (z-score) |
| `envoyes/pushover_envoyes.json` | envoyes | json indent=1, UTF-8 (ensure_ascii=False) | scripts/envoyes_secours.py | scripts/envoyes_secours.py | réécrit à chaque passage |
| `envoyes/webhook_envoyes.json` | envoyes | json indent=1, UTF-8 (ensure_ascii=False) | scripts/envoyes_secours.py | scripts/envoyes_secours.py | réécrit à chaque passage |
