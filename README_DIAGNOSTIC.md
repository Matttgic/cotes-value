# Diagnostic de fraîcheur — utilisation

Ce ZIP est une proposition additive, non intégrée au dépôt. Ne remplacez aucun fichier existant sans comparer les versions. Les deux fichiers Python sont nouveaux ; aucune stratégie n'est modifiée.

## Vérification

Depuis la racine du dépôt après revue des fichiers :

```bash
python -m unittest discover -s tests -p test_diagnostic_fraicheur.py -v
```

## Diagnostic sur une copie locale des réserves

Le fichier d'entrée doit être une liste de lignes normalisées, un objet `{"lignes": [...]}` ou un dictionnaire de réserves contenant de tels objets. `etat.json`, les opportunités et les paris ne sont pas des inventaires complets de cotes.

```bash
python scripts/diagnostiquer_fraicheur.py donnees/horizon_direct.json --seuil-s 60 --sortie diagnostic-fraicheur-run1
```

Adapter le chemin d'entrée à la copie locale réelle. Le dossier de sortie doit être nouveau ; le programme refuse l'écrasement. Deux fichiers sont créés : rapport.json et rapport.csv. L'entrée n'est pas modifiée.

Pour un export historique, utiliser son heure d'évaluation réelle afin de ne pas confondre vieillissement de l'archive et retard de collecte :

```bash
python scripts/diagnostiquer_fraicheur.py export.json --maintenant 2026-10-20T01:00:00+00:00 --sortie diagnostic-historique-run1
```

La date ci-dessus est un exemple de syntaxe, pas une heure supposée de vos données. Les tests fournis utilisent des données synthétiques, pas des prix de production.

Plusieurs exports disjoints peuvent être fournis. Les fichiers sont additionnés sans déduplication inter-fichiers : ne pas fournir un export complet et son sous-ensemble ensemble. Aucun réseau n'est contacté ; ce script n'est pas un collecteur.

## Lecture des indicateurs

- `observations_dans_objectif` : date d'observation dans le seuil, indépendamment de la disponibilité ou du cache.
- `observation_et_cache_dans_objectif` : date et cache documenté dans le seuil, sans suspension/péremption signalée. Ne prouve pas l'âge du prix en amont.
- `statuts` : détail des causes de refus ou d'incertitude.
- `prix_amont_verifie` reste faux : les champs analysés ne permettent pas de certifier ce point.

Le cache est évalué par `age_cache_s`, s'il existe. Aucun en-tête HTTP manquant n'est inventé. La date `collecte_recue` est prioritaire sur `collecte`, avec repli si elle est illisible. Une provenance manquante reste `inconnue`. Les marchés absents ne peuvent pas être comptés sans inventaire attendu indépendant.

## État de validation

23 tests unitaires réussis. Une exécution CLI sur une réserve synthétique a produit les deux rapports ; une seconde exécution vers le même dossier a été refusée. Aucun test réseau, aucun test sur les grandes réserves de production, et aucune exécution de la suite complète du dépôt.
