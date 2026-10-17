# Exécution du contre-audit du 17 octobre 2026

## Fiabilité des nouvelles observations

- Contradictions explicites U19/U21, jeunes/réserves et équipe première/réserve : association refusée. Un marqueur absent conserve la pénalité d’incertitude. Les règles des stratégies et les prises déjà enregistrées ne sont pas réécrites.
- Pinnacle et PulseScore : l’heure locale de réception par réponse/page est déjà enregistrée depuis le correctif `9cc5b76`. Elle ne garantit pas la fraîcheur interne du fournisseur.
- Placement : heure réelle contrôlée pour chaque prise, abandon à moins de 30 secondes du début, absence de date valide bloquante. `decide_le` et `lot_decision` sont enregistrés. L’horodatage `detecte` conserve son sens de lecture du prix.
- Clôture : une nouvelle lecture prouvée antérieure au début peut être intégrée après le départ. Aucun retour arrière, aucune lecture au départ ou après. La couverture CLV finale reste limitée aux 30 dernières minutes pré-match. Aucune réparation des anciennes clôtures n’est inventée.
- Betfair : prix décimaux finis >1, meilleur back ≤ meilleur lay ; rejet du marché entier si son carnet est croisé/invalide. Les spreads négatifs sont aussi refusés par `_fiable`.

## Registre prospectif

Chaque nouvelle prise reçoit `selections_figees` et `registre_version=1`, dans le cycle de placement, avant la sauvegarde et les alertes. Chaque sélection porte la version et `decide_le`. Le dictionnaire vide signifie « évalué, non retenu ». Un champ absent signifie « ancienne prise reconstruite », jamais « décision connue à l’époque ».

Les six moteurs de base, la convergence existante, les variantes et les 36 règles du laboratoire sont enregistrés. Les vues officielles réutilisent ces décisions ; un rejeu explicitement demandé conserve son calcul rétrospectif. Le registre n’est jamais complété sur les anciennes prises et n’est pas réécrit lors des règlements. Les identifiants de version actuels sont conservés (dont Jules v2 « 2-reconstruite ») : aucune réoptimisation.

Limite : les anciens historiques sans registre restent des reconstructions. Les critères actuels servent encore à calculer les candidats des nouvelles prises ; toute future modification de paramètres devra créer une nouvelle version et vérifier les plafonds déjà consommés.

## M3 Max 3/match v1

Départ annoncé : **17 octobre 2026, 03 h à Paris (01 h UTC)**. Uniquement prospectif ; aucun bilan historique ajouté.

Critères M3 inchangés, mise papier 10 € par ticket, jusqu’à trois familles par événement identifié :

1. Vainqueur.
2. Handicap : une seule ligne et direction, tous bookmakers et références confondus.
3. Total : total du match ou total extérieur, une seule sélection au total.

Au premier lot admissible de chaque famille, retenir le meilleur edge du lot disponible, puis l’ID en cas d’égalité. Une famille non encore prise peut être ajoutée dans un cycle ultérieur. Un meilleur edge ultérieur ne remplace jamais une prise passée. M3 Rafale et Convergence ≥2 gardent leurs paramètres, leurs votes et leurs historiques.

Les identités utilisent les liens vérifiés connus à la décision, sans recherche floue supplémentaire. Une fusion tardive ne supprime pas rétroactivement un ticket : le plafond s’applique aux événements identifiables à cet instant, pas à une identité future encore inconnue. Les mêmes liens empêchent toute prise supplémentaire dans les familles déjà occupées après fusion.

## Statistiques et interface

- Stratégies et Bilan : tickets réglés et événements reliés affichés ensemble.
- CLV par événement : moyenne des CLV valides des tickets de l’événement, puis moyenne non pondérée de ces moyennes. Couverture en événements affichée séparément de celle en tickets. Les événements sans CLV restent absents de la moyenne.
- Les indicateurs par événement ajoutent du contexte aux bilans ; ils ne changent aucun gain, ROI, résultat ni chiffre de clôture enregistré.
- « À jouer » retire les départs dépassés à chaque minute, même sans filtre horaire. Les compteurs et les puces suivent ce retrait.
- Jour/heure Paris et âge du prix restent visibles sur les lignes fermées.
- Les tickets témoins Pinnacle brut sont exclus du catalogue mobile. Leurs agrégats, courbes, données originales et éléments à régler restent conservés. Les contrats ne sont plus dupliqués intégralement pour la navigation des stratégies.
- Le chemin d’alerte déjà corrigé reste : sauvegarde des prises → envoi → règlement → construction du site. Un prix de plus de cinq minutes à la préparation n’est pas envoyé ; aucune réception instantanée sur téléphone n’est garantie.

## Interprétation méthodologique

Quelques jours positifs et une CLV mesurée sur peu de rencontres ne prouvent ni la rentabilité future de M3 ni l’existence d’une erreur sur toute la grille. La variante sert à comparer prospectivement une exposition encadrée au mode Rafale, sans effacer celui-ci. Le regroupement réduit l’effet d’empilement ; il ne rend pas les marchés d’un match indépendants.

## Vérifications avant publication

- Suite : 409 tests Python et 36 tests JavaScript réussis.
- Comparaison avant/après sur **12 712 prises** : mêmes gains, ROI, CLV par ticket, nombres de tickets et sélections de tous les moteurs existants, sur les trois ensembles de bilans (global, bookmaker, tranche).
- Le fichier de données de contrôle n’est pas modifié par ces vérifications.
- HTML de contrôle : environ **3,12 Mo** au lieu de 8,01 Mo (−61 %), environ 490 ko compressés en gzip. L’objectif de 1,2 Mo n’est pas atteint : courbes, segments, preuves et agrégats restent disponibles. Ce poids sera différent à chaque collecte.
- Service Push : nouvelle clé `m3_structure` ajoutée ; aucune modification des appareils ni des abonnements, aucun test envoyé aux appareils.
