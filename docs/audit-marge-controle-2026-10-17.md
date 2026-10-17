# Revue de l’audit marge / comparaison / conformité — 17 octobre 2026

| Recommandation | Décision | Effet |
| --- | --- | --- |
| Rejeter les cotes infinies | Appliquée | `proba_justes` refuse ±Inf, NaN et les cotes ≤1 ; méthode power inchangée pour les entrées valides. |
| Moyenner les cotes pour le consensus | Non retenue | Aucun argument de calibration n’est apporté pour remplacer la moyenne équipondérée des probabilités. |
| Isoler Pinnacle brut | Renforcée | `pariable=false` sur le témoin ; aucun nouveau ticket brut autorisé par `placer`, même si le champ manque ou si la comparaison brute est réactivée. |
| Refuser les dates absentes ou invalides | Appliquée | Lecture avec fuseau obligatoire, écart absolu ≤15 min, dates manquantes/naïves/illisibles refusées par la comparaison et les mesures de conformité. |
| Purger par instants et non par chaînes | Appliquée | Comparaison de `datetime` avec fuseau ; frontière exacte de 30 jours conservée. |

## Consensus : pourquoi conserver la moyenne des probabilités

Pour deux références complètes sur un même marché, la moyenne de leurs vecteurs de probabilités conserve une somme égale à 1. Exemple : [0,4 ; 0,6] et [0,5 ; 0,5] donnent [0,45 ; 0,55]. Les références ont chacune un poids égal : il ne s’agit pas d’une pondération supérieure des références donnant les plus fortes probabilités.

Moyenner les cotes, puis inverser, revient à prendre une moyenne harmonique des probabilités. Dans cet exemple, cela donne environ [0,4444 ; 0,5455], dont la somme vaut 0,9899. Ce changement abaisse les probabilités et modifie les edges ; il ne prouve pas une amélioration du consensus. Une éventuelle nouvelle méthode doit être versionnée et évaluée prospectivement, en gardant le même calcul à la détection et à la clôture. Aucun calcul de consensus n’est modifié ici.

Cette propriété suppose le même ensemble de références et toutes les issues du marché. Elle ne suffit pas à garantir la calibration ni l’indépendance des références.

## Pinnacle brut : une fausse value est bien possible

Pinnacle à 1,90/1,90 implique une cote juste de 2,00 sur chacune des deux issues après retrait de marge. Une cote française de 1,95 donne :

- contre le brut : 1,95 / 1,90 − 1 = +2,63 % ;
- contre le juste : 1,95 / 2,00 − 1 = −2,50 %.

Le témoin n’est donc pas un filtre plus conservateur. Le rapport d’audit a raison sur ce risque. Sa création était déjà désactivée dans la collecte de production (`TEMOIN_PINNACLE_BRUT=non`), et il était déjà exclu des stratégies et des notifications. La protection est désormais aussi explicite dans les opportunités et dans le placement des simulations. Les anciennes prises, règlements, archives, courbes et agrégats témoins restent conservés.

Une opportunité suspecte porte également `pariable=false`. Les notifications refusent ce champ explicite, en plus des garde-fous déjà présents.

## Politique sur les dates

Aucun mode de compatibilité permissif n’est ajouté à la collecte courante : l’historique des prises enregistrées n’a pas besoin d’être rejoué dans le comparateur.

La purge retient les groupes dont la dernière mesure est exactement sur la frontière des 30 jours. Si l’heure du cycle est valide mais que la date d’un groupe ne l’est pas, le groupe est retiré : sa conformité ne peut pas être conservée indéfiniment sans date vérifiable. Les observations ultérieures reconstruiront ce groupe. Si l’heure du cycle elle-même est invalide, aucune limite de purge n’est inventée.

Deux horodatages proches ne prouvent ni la fraîcheur interne de l’API ni l’égalité des états d’un match. La fenêtre de 15 minutes reste une règle pré-match de proximité entre lectures ; elle ne remplace pas les contrôles Live ni le filtre d’âge des notifications.

## Validation

- 428 tests Python et 36 tests JavaScript réussis (464 au total).
- Invariance vérifiée sur 12 712 prises : mêmes bilans financiers et sélections existantes.
- Génération du HTML et vérification syntaxique JavaScript réussies sur les données de contrôle.

- Tests ciblés : Inf/NaN, normalisation, frontières exactes de 15 min et 30 jours, fuseaux différents, microsecondes, dates absentes et sans fuseau, faux signal brut, refus de placement et d’alerte, consensus conservé.
- Aucun fichier de paris ou d’archives n’est modifié par ce correctif.
- Cette passe couvre les cinq recommandations ci-dessus. Elle ne constitue pas un nouvel audit complet du règlement, de tous les connecteurs ou de l’historique Git des secrets.
