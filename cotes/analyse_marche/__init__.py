"""Analyse du marché : comment les bookmakers et les références bougent, en lecture seule.

Module indépendant de la détection (rien ici n'est importé par le cycle). Il lit les fichiers journaliers de la
branche « donnees » un par un, en flux, sans tout charger en mémoire :

- ``cotes/`` (bookmakers, changements seuls, cotes/historiques.py) ;
- ``opportunites/`` (écarts d'au moins 2 % à chaque cycle) ;
- ``references/``, ``releves/`` et ``correspondances/`` quand ils existent (depuis le 12/11/2026,
  cotes/historiques.py).

Chaque jour terminé est résumé une fois et gardé en cache (cache.py) : le passé n'est jamais recalculé. Deux
études pour l'instant :

- opportunites.py : durée des opportunités et cause de leur disparition (le bookmaker a corrigé, la référence a
  bougé, le match a commencé, ou inconnue). Une fin non observée laisse la durée inconnue ;
- meneurs.py : entre deux bookmakers français, lequel bouge en premier sur la même sélection.

segments.py agrège les résumés par segment (sport, marché, délai avant le match…), avec la taille de chaque
échantillon. Point d'entrée : ``python etudes/analyse_marche.py --donnees donnees``.
"""
