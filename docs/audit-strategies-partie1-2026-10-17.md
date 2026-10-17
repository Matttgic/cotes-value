# Revue contradictoire — Stratégies, partie 1, 17 octobre 2026

## Périmètre et verdict

Cette passe approfondit **ChatGPT v1 et Jules v2 reconstruite**, leurs validations, leur diagnostic et leur articulation avec le registre de décisions. Elle ne certifie pas les cinq moteurs mentionnés comme restant à examiner : Gemini, Jules v1, M3, stratégies prudentes et laboratoire.

Les deux sélecteurs utilisent les informations de prise et ne consultent pas les résultats, gains ou clôtures futures. Cela établit une propriété du code, pas une preuve de rentabilité ni de validation statistique indépendante. La qualité et l'horodatage des champs d'entrée restent essentiels.

Les trois principaux plantages proposés par Argon étaient en grande partie déjà filtrés. Les problèmes confirmés concernent surtout des structures de preuves mal formées, des conversions numériques extrêmes et la lisibilité du diagnostic. Les critères, seuils, plafonds, mises, dates de lancement et versions de stratégie sont conservés.

## ChatGPT : corrections nécessaires et faux positifs

### Preuve absente

Une preuve absente ou vide était déjà refusée par `motif_refus()` avant l'accès direct à `preuve_prise["match_id_reference"]`. Le test proposé n'établissait donc pas un plantage de cet accès.

En revanche, une preuve non vide mais de type liste/chaîne, ou un contrôle de conformité non dictionnaire, pouvait lever `AttributeError` dans le filtre lui-même. Ces schémas sont désormais refusés proprement. La conformité, la ressemblance minimale et l'identifiant de référence restent obligatoires.

### Tri

Une cote ou un edge `None`, NaN ou infini ne parvenait pas au tri : les validations les éliminaient déjà. Ajouter une date fictive au 1er janvier 1970 aurait masqué un problème d'entrée et introduit un ordre chronologique inventé. Cette proposition n'est pas appliquée.

Un défaut distinct existait dans le dernier départage : si `id` et `match_id` étaient tous deux absents, il pouvait lever `KeyError` malgré une preuve valide. Le départage utilise désormais une chaîne vide dans ce cas. Ce secours ne permet pas de sauvegarder une décision sans identifiant persistant : `figer_nouveaux()` conserve sa vérification bloquante. Les données normales ont leurs identifiants ; rien ne change dans leur ordre.

Les nombres entiers trop grands pour être convertis en flottants sont également refusés sans exception.

### Jour de plafond

Le plafond était déjà calculé en `Europe/Paris`. Un commentaire le précise et les tests vérifient le passage à minuit en heure d'hiver en plus des cas d'été existants. Le plafond reste de cinq paris par jour civil français.

## Jules v2 : identité et diagnostic

### Date de début

`_correspondance()` vérifiait déjà une date de début valide avant l'appel à `_cles()`. La date absente ne provoquait donc pas le plantage décrit via le sélecteur public.

Une protection locale est ajoutée dans `_cles()` : sans date valide, aucune clé d'équipes datée n'est produite. Cela ne rend pas le pari admissible. Les noms et libellés mal typés ne sont pas transmis au normaliseur comme s'il s'agissait de chaînes.

Les identités restent séparées par fournisseur, avec conservation des marqueurs de catégorie. Le graphe est construit dans l'ordre des détections ; aucun regroupement avec des alias futurs n'est préconstruit. Une fusion tardive peut révéler plusieurs prises sur un même événement ; elle est signalée sans annuler rétroactivement l'une d'elles.

### Le diagnostic n'était pas perdu partout

`analyser_jules_v2()` exposait déjà les refus, doublons, plafonds et fusions tardives. Le script `verifier_strategie_jules_v2.py` l'utilisait déjà. Le sélecteur public renvoyait seulement l'ensemble d'identifiants en mémoire attendu par les bilans : c'était son contrat.

Une fonction dédiée `diagnostic_jules_v2()` est maintenant disponible et utilisée par le script. Elle renvoie un objet JSON, sans ensemble d'`id()` Python, avec :

- mode explicite `rejeu_diagnostic`, version et début d'étude ;
- nombre de lignes examinées et de sélections rejouées ;
- nombre de lignes exclues dès le contrôle de correspondance ;
- refus ultérieurs, doublons, plafond, prises par jour et fusions tardives.

Le compteur des lignes exclues dès la correspondance manquait au diagnostic précédent. La somme des sélections, refus, doublons, plafonds et exclusions préalables permet désormais de retrouver le nombre total de lignes analysées. Les fusions sont un indicateur distinct, pas un motif de rejet supplémentaire.

### Rejeu et suivi figé restent différents

Ce diagnostic rejoue les règles sur les données fournies. Il ne doit pas être présenté comme le journal des décisions réellement prises. Si des champs d'entrée ont été corrigés depuis, il peut différer du registre.

Les bilans prospectifs continuent d'utiliser `paris_jules_v2()` et les `selections_figees` lorsqu'elles existent. Un dictionnaire vide reste un refus déjà enregistré. Aucune décision ancienne n'est ajoutée, supprimée ou recalculée par le diagnostic.

## Validations communes et versions

`cotes/strategie_commune.py` contient les seules validations pures partagées par ces deux sélecteurs : nombres finis, structure de preuve, conformité/ressemblance, cohérence de l'edge, lignes entières/demi-points et issues autorisées.

Les paramètres restent dans chaque stratégie. Les nuances existantes sont conservées : ChatGPT et Jules v2 n'ont notamment pas exactement la même condition de période pour tennis/volley. Les autres moteurs ne sont pas refactorisés dans cette passe.

Les versions `ChatGPT 1` et `Jules 2-reconstruite` restent identiques, car les règles applicables aux prises valides ne changent pas. La version technique du moteur est actualisée pour tracer cette maintenance. Le rapport de Jules conserve ses empreintes existantes et ajoute celles des dépendances du sélecteur, dont le nouveau module commun.

Une modification future d'un seuil, d'un plafond, d'une fenêtre, d'un marché admis ou de la politique d'identité doit créer une nouvelle variante avec son propre identifiant, sa version et son début de suivi. Modifier seulement le numéro de version en réutilisant le même comparateur ne suffit pas à séparer deux protocoles. Les tests ne remplacent pas cette discipline de publication.

## Vérifications

- **755 tests Python et 36 tests JavaScript : 791 tests au total.**
- 45 nouveaux cas Python couvrent les preuves/contrôles mal formés, dates et nombres invalides, débordements numériques, absence d'accès aux champs futurs, jour civil de Paris, diagnostic JSON, fusions tardives, empreintes des dépendances et décisions figées après rechargement JSON.
- Les critères valides sont testés par des contrôles positifs : une mauvaise ligne ne doit pas masquer une autre ligne admissible.
- Le test de causalité vérifie qu'ajouter un lien découvert plus tard ne remplace pas les décisions des préfixes déjà observés.
- Sur le relevé local de **12 712 paris**, comparaison avant/après des paramètres et des identifiants retenus : identiques pour les deux stratégies, en rejeu depuis le 7 octobre, en rejeu depuis le 14 octobre à 14 h Paris, et via leur suivi par défaut. Ces nombres décrivent des lignes retenues dans ce relevé, pas uniquement des paris réglés d'une fenêtre de matchs.
- Les indicateurs financiers et les sélections préexistantes des autres comparateurs vérifiés restent également identiques sur ce relevé.
- Le site se génère et son JavaScript embarqué passe `node --check`.
- Aucun fichier de paris ou résultat de production n'est réécrit. Aucune API sportive n'est appelée pour ces tests.

Le relevé de contrôle n'est pas une certification des toutes dernières données de production. Cette passe ne démontre ni le rendement futur des stratégies ni l'absence de défaut dans les cinq autres moteurs ou la sécurité globale du dépôt.
