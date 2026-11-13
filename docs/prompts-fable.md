# Prompts des sessions Fable

Avant chaque session : `/effort high`, puis `/clear`. Une session traite un sujet. Chaque session écrit ses
conclusions dans `docs/`, ce qui permet à la suivante de repartir de là.

Ordre : d'abord les chiffres justes (1), puis l'avantage réel (2), l'amélioration (3 à 5), enfin la durée (6 à 8).

## Session 1 : les bilans sont-ils justes ?

```markdown
Audite la justesse des bilans de la simulation de paris. Lis seulement les fichiers utiles.

1. Biais :
   - anticipation : une cote juste, une cote ou un résultat connus après l'heure du pari ;
   - survivant : paris annulés, marchés retirés ou matchs non réglés qui sortent des bilans ;
   - double comptage : un même pari compté deux fois, ou une même cote vue par plusieurs références.
2. Règlement (`cotes/reglement.py` et les modules de résultats) : trouve les paris réglés à tort. Vérifie les handicaps et totaux asiatiques (quarts, push), les abandons au tennis, les prolongations au hockey et au basket, les périodes, et « avance ou gagne ».

Pour chaque problème, donne le fichier et la ligne, un exemple réel tiré des données et l'effet chiffré sur le ROI. Corrige ce qui est sûr, en ajoutant des tests. Écris les conclusions dans `docs/audit-bilans.md`.
```

## Session 2 : l'avantage est-il réel ?

```markdown
Lis d'abord `docs/audit-bilans.md`. Puis, pour chaque stratégie et chaque bookmaker, sur les paris réglés :

1. Calcule le ROI avec son intervalle de confiance à 95 % (bootstrap), et la p-valeur corrigée pour le nombre de stratégies et de seuils testés (Holm ou Benjamini-Hochberg).
2. Donne le nombre de paris qu'il faudrait encore pour conclure.
3. Calcule la CLV par rapport à la cote de clôture Pinnacle (ou à la meilleure référence disponible) : moyenne, intervalle de confiance et part des paris avec une CLV positive. Est-ce que la CLV prédit le ROI ?

Conclus clairement, stratégie par stratégie : avantage prouvé, probable, non prouvé ou négatif. N'invente aucun chiffre : si une donnée manque, dis-le. Écris les conclusions dans `docs/avantage-reel.md`, avec un script reproductible dans `scripts/`.
```

## Session 3 : la cote juste

```markdown
Lis d'abord `docs/avantage-reel.md`. Améliore le calcul de la cote juste.

1. Retrait de la marge : compare les méthodes multiplicative, additive, puissance, Shin et odds ratio, par type de marché (1N2, deux issues, totaux, handicaps, props). Mesure la calibration sur les résultats réels (log-loss, Brier, courbe de calibration).
2. Consensus : propose une pondération de Pinnacle, Polymarket, Matchbook et DraftKings qui tienne compte de la fraîcheur, de la liquidité et de l'écart achat/vente. Valide-la sur des données qu'elle n'a pas vues.

Ne change le code que si le gain est mesuré. Écris les conclusions dans `docs/cote-juste.md`.
```

## Session 4 : revue de bugs

```markdown
Fais une revue de bugs de la correspondance des matchs (`cotes/correspondance.py`), de la traduction des marchés (`cotes/pulsescore.py`, `cotes/marches.py`) et des lecteurs `cotes/direct/`.

Cherche :
- les matchs mal appariés ;
- les mauvaises périodes ou la prolongation mal prise en compte ;
- les lignes inversées (domicile/extérieur, plus/moins, signe du handicap) ;
- les cotes périmées ;
- les écarts « minimum » (Polymarket au prix d'achat, Betclic « avance ou gagne ») mal traités dans les bilans.

Pour chaque bug, donne un exemple réel. Corrige-le, avec un test. Écris les conclusions dans `docs/revue-bugs.md`.
```

## Session 5 : la stratégie et les mises

```markdown
Lis d'abord `docs/avantage-reel.md` et `docs/cote-juste.md`.

1. Trouve les seuils, sports, marchés et bookmakers qui ne rapportent rien ou font perdre.
2. Propose une stratégie à figer, choisie sur une période et validée sur une autre (pas d'optimisation sur toutes les données).
3. Propose une mise de Kelly fractionnée qui tienne compte de l'incertitude sur la cote juste et de la corrélation entre les paris d'un même match. Simule-la contre la mise fixe de 10 € : ROI, perte maximale, risque de ruine.

Écris les conclusions dans `docs/strategie-mises.md`.
```

## Session 6 : durer

```markdown
1. Limitation des comptes : d'après ce qui est connu publiquement sur Winamax, Betclic, Unibet, PMU et OlyBet, quel profil de paris (marchés, montants, délai avant le match, fréquence) est le moins repérable ? Mesure ce que ce profil coûte en ROI sur nos données.
2. Robustesse : conçois une détection de panne et de dérive des formats pour chaque source directe (marchés non reconnus, cotes figées, volume anormal), avec une alerte. Implémente-la si c'est simple.

Écris les conclusions dans `docs/durer.md`.
```

## Session 7 : simplifier

```markdown
Le projet a beaucoup de modules dans `cotes/` qui se recoupent (stratégies, historiques, mémoire, notes…). Propose une simplification : ce qu'on supprime, ce qu'on fusionne et dans quel ordre, sans perte de données ni de fonctions utilisées. Fais-la par petites étapes. Après chaque étape, les tests doivent passer. Écris le plan et ce qui a été fait dans `docs/simplification.md`.
```

## Session 8 : chercher plus loin

```markdown
Lis d'abord `docs/avantage-reel.md`.

1. Mouvements de cotes : à partir de l'historique, peut-on prédire la cote de clôture Pinnacle (sens et ampleur), pour parier plus tôt ou attendre ? Teste-le sur des données que le modèle n'a pas vues.
2. Quelles autres références sharp ou quels autres marchés gratuits, accessibles sans compte, pourraient ajouter de la valeur ? Vérifie chaque source avant de la proposer, et n'invente aucune URL.

Écris les conclusions dans `docs/recherche.md`.
```
