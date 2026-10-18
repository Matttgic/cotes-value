# Revue contradictoire — Connecteurs externes, partie 1, 17 octobre 2026

## Verdict et périmètre

Les défauts de conversion et les diagnostics HTTP manquants sont confirmés. La robustesse n’était donc pas aussi complète que le verdict initial le suggérait : une valeur non numérique ou un schéma inattendu pouvait interrompre une source entière.

Cette passe concerne The Odds API, Pinnacle et Polymarket. Les critères des stratégies et les données historiques restent inchangés. Les contrôles supplémentaires portent sur les nouvelles lectures de référence.

## Configuration Pinnacle : amélioration appliquée, retrait complet non effectué

Le connecteur utilise l’endpoint `guest.api.arcadia.pinnacle.com`, sans compte personnel dans son code. L’audit qualifie sa valeur embarquée de clé publique guest ; cette passe ne certifie pas ce statut à partir d’une documentation officielle. Aucun constat de compromission d’une clé de compte personnelle n’est établi ici.

La configuration évolue ainsi :

- depuis le 18/10/2026, la clé du cycle vient d'abord de `app.json` (`api.haywire.apiKey`), puis de `PINNACLE_API_KEY`, puis de la valeur historique ;
- la collecte, la sonde et le journal papier passent par le même constructeur d’en-têtes ;
- les workflows de collecte, de sonde et de vérification transmettent le secret optionnel portant ce nom ;
- `.env.example` contient uniquement des emplacements vides ; `.env` et ses variantes sont ignorés par Git ;
- `etat.json` indique seulement le mode `site`, `environnement` ou `guest_historique`, jamais la valeur ;
- aucun chargement automatique de `.env` ni dépendance supplémentaire n’est ajouté.

**La valeur guest historique reste présente en secours lorsque la variable est vide. Ce n’est pas une suppression complète de la clé du code.** La rendre obligatoire sans configuration validée aurait coupé la principale référence. Les outils de dépôt disponibles ne permettent pas de créer ou vérifier les secrets GitHub Actions ; leur présence n’a pas été supposée.

Pour terminer une migration sans secours embarqué, il faut d’abord configurer une clé compatible avec l’endpoint guest dans le secret `PINNACLE_API_KEY` et valider une collecte authentifiée par cette configuration, puis supprimer le défaut. Une variable d’environnement ne retire pas une ancienne valeur des commits Git ; aucune purge d’historique ni rotation de clé n’est réalisée par cette passe.

## The Odds API

Le contrôle HTTP proposé existait déjà, ainsi que le commentaire expliquant la réservation prudente des crédits avant l’appel. Ces comportements sont conservés : une panne réseau peut avoir consommé le crédit côté fournisseur.

Le diagnostic distingue désormais :

- réponse HTTP autre que 200, avec invalidation du compte sur 401/403 ;
- JSON invalide ;
- JSON valide mais de type inattendu ;
- erreur réseau.

Les messages restent génériques : aucune représentation de l’exception, URL avec clé, réponse brute ou en-tête d’authentification n’est journalisé. Les plafonds de quatre appels de scores par cycle et les budgets ne changent pas. Les quatre clés restent une seule source de résultats, pas quatre validateurs indépendants.

## Pinnacle

### Requêtes et schémas

Les diagnostics sont bornés et dédupliqués, puis remontés dans le journal du cycle. Ils contiennent la catégorie de requête et le numéro du sport, sans URL complète ni paramètres sensibles.

- HTTP 401 ou 429 : arrêt des appels Pinnacle restants pour le cycle.
- HTTP 403 : ce sport seulement est sauté (pas de réessai, pas d'arrêt des sports suivants). Correction du 18/10/2026 : un 403 de localisation sur un sport ne doit pas couper le football et le reste du cycle. Polymarket conserve l'arrêt sur 403.
- Autre erreur HTTP permanente : pas de réessai de cette requête.
- HTTP 408, erreurs serveur 5xx et erreurs réseau : au plus trois essais, avec délais de 2 puis 4 secondes.
- Aucun délai ajouté après le dernier échec.
- HTTP 200 : JSON liste exigé ; JSON invalide ou mauvais type signalé.
- Événements et marchés mal structurés isolés ; les marchés valides peuvent continuer.

Le délai maximal par requête reste celui du connecteur existant. Le blocage 429 est limité au processus du cycle ; il ne constitue pas un ordonnanceur persistant fondé sur `Retry-After`.

### Prix et marchés

`americaine_vers_decimale()` refuse les valeurs absentes, vides, non numériques, booléennes, nulles ou non finies. Les conversions valides restent identiques : +150 → 2,50 ; −200 → 1,50.

Un marché ordinaire avec une cote invalide est rejeté dans son ensemble : on ne retire pas la marge sur une seule issue restante. Les lignes de handicap/total sont converties de façon contrôlée. Un marché dont le `status` est présent et différent de `open` est ignoré. L'absence de `status` (cas des marchés spéciaux) compte comme ouvert. Un spécial avec moins de deux prix est ignoré sans diagnostic « liste de prix invalide » ; un marché ordinaire dans ce cas reste signalé.

Correction du 18/10/2026 : l'en-tête `Age` est stocké (`age_cache_s`). Au-delà de `PINNACLE_AGE_MAX_MIN` (10 minutes par défaut), `cote_perimee` empêche l'usage comme référence de pari. Un en-tête absent sans horodatage du réchauffeur est une péremption (âge inconnu). La clé du cycle vient de `app.json`, puis de `PINNACLE_API_KEY`, puis de la valeur historique. Le snooker est l'identifiant 28 ; 13 est le hockey sur gazon. Esport, cricket et fléchettes ne sont plus demandés.

Avant le retrait de marge, les cotes décimales doivent être numériques, finies et supérieures à 1. Les doublons d’issues, les ensembles d’issues incomplets pour les marchés connus et les groupes mélangeant des contrats différents ne reçoivent pas de probabilités justes. Un groupe refusé conserve des probabilités nulles, donc ne devient pas une référence éligible.

La méthode power et la limite de marge du comparateur restent inchangées.

## Polymarket

### Réponses et données numériques

Les requêtes suivent la même politique de diagnostic et de réessai, avec arrêt du reste du cycle sur 401/403/429. Les erreurs d’objets, de listes et de dates sont traitées explicitement.

Les conversions bid/ask sont protégées et refusent également booléens, NaN et infinis. La condition `0 < bid <= ask < 1` reste obligatoire. Les deux issues doivent être des chaînes distinctes ; un objet JSON avec deux clés ne peut pas être pris pour une liste de deux issues.

Une liquidité absente, négative, non numérique ou non finie devient zéro, avec diagnostic. Ce zéro n’invente pas de liquidité et échoue au seuil du comparateur. Les lignes de total et de handicap doivent être numériques et finies. Les états d’ouverture et d’acceptation d’ordres doivent être des booléens explicites.

Le milieu bid/ask reste une approximation de probabilité pour la comparaison, pas une preuve qu’une mise réelle serait exécutée à ce prix ni une garantie de calibration. Les frais et la profondeur exécutable ne sont pas modélisés par ce changement.

### Dates et 1N2

Deux défauts supplémentaires ont été corrigés :

1. La date des prix provenait auparavant de la fin de toute la collecte. Chaque page garde maintenant ses propres heures de requête et de réception, transmises aux prix issus de cette page.
2. Le test de complétude 1N2 vérifiait seulement trois lignes. Il exige désormais exactement DOM, NUL et EXT, avec des probabilités valides.

Pour un 1N2 composé de plusieurs lectures, la plus ancienne borne sa fraîcheur. Une composante lue après le coup d’envoi ne peut pas devenir une clôture pré-match grâce à cette date ancienne : les prix postérieurs au départ et les groupes les mélangeant sont refusés.

Les heures avec un espace et un fuseau, comme `2026-10-17 18:00:00+00:00`, sont analysées puis normalisées, sans remplacer aveuglément `+00` et produire un fuseau invalide. Les dates absentes ou sans fuseau et les événements hors horizon ne sont pas conservés comme événements pré-match.

## Validation

- **652 tests Python et 36 tests JavaScript passent : 688 tests au total.**
- 68 nouveaux cas Python couvrent les erreurs HTTP/JSON, le nombre d’essais, les diagnostics sans clé, la configuration, les conversions numériques, les marchés incomplets, la liquidité, les dates par page et les lectures traversant le coup d’envoi.
- Le journal réel du cycle est testé pour la remontée d’une erreur Pinnacle sans publier la clé.
- Les tests n’appellent pas les API externes et n’effectuent aucun pari réel.
- Comparaison sur 12 712 paris du relevé de contrôle : sélections et indicateurs financiers historiques identiques.
- Site généré et syntaxe de son JavaScript embarqué vérifiée ; aucune réécriture des fichiers de données de production par l’audit.

La disponibilité réelle des fournisseurs, la valeur configurée dans les secrets GitHub et la rotation de l’identifiant guest ne sont pas validées par des tests simulés. L’examen exhaustif des secrets dans les autres fichiers et l’historique Git appartient à l’étape suivante.
