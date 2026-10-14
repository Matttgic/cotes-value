# Scores de secours : The Odds API

Secrets GitHub Actions : `THE_ODDS_API_KEY_1`, `THE_ODDS_API_KEY_2`,
`THE_ODDS_API_KEY_3`, `THE_ODDS_API_KEY_4`. Ajouter seulement les comptes disponibles.
Les valeurs ne doivent figurer ni dans le code, ni dans les fichiers de données.
Le workflow `reglement.yml` les transmet au moteur ; la collecte des cotes ne les utilise pas.

Le moteur interroge d'abord PulseScore, ESPN puis API-Sports. Il ne demande à
The Odds API que les scores des matchs encore sans résultat accepté, commencés depuis
au moins 6 heures. `/sports?all=true`, gratuit, vérifie chaque clé au premier usage et
chaque nouveau mois. Une clé refusée est retestée au plus une fois par heure.

## Quotas et cache

Le plan gratuit donne 500 crédits mensuels par compte. `/scores?daysFrom=3`
coûte 2 crédits par compétition, pour ses résultats des trois derniers jours.
Une réponse sert à tous les paris de la compétition et tous les comptes partagent
le cache : ajouter des comptes n'ajoute aucune voix au consensus.

- 16 crédits maximum par jour UTC et par compte, soit 496 au plus sur 31 jours.
- 500 crédits maximum par mois UTC et par compte ; prise en compte également du
  quota restant renvoyé par l'API, notamment si le compte sert ailleurs.
- 4 requêtes scores maximum par cycle, essais sur d'autres comptes compris.
- Compétition relue au plus toutes les 3 heures, une heure après une erreur.
- Répartition entre les comptes disponibles, et priorité aux compétitions les moins
  récemment lues. Réservation prudente de 2 crédits même en cas de timeout.
- Résultats terminés conservés 8 jours : ils peuvent servir après la fenêtre de
  3 jours, s'ils avaient été récupérés à temps. Pas de rattrapage historique illimité.

Avec quatre comptes distincts, le plafond quotidien est donc de 64 crédits,
soit 32 appels scores. Les clés identiques sont dédupliquées. Les crédits réservés
par le moteur peuvent dépasser la consommation réelle après une panne ; ils sont
volontairement prudents et ne représentent pas une facture.

## Règlement et couverture

Le résultat doit avoir `completed: true`, deux scores entiers valides et un match
identifié sans ambiguïté : compétition explicitement associée, deux noms ressemblants
à au moins 0,9, marqueurs féminin/jeunes compatibles, heure à 30 minutes près.
Un désaccord avec un autre résultat trouvé bloque ce secours. La nouvelle date d'un
match reporté est utilisée pour le retrouver et décider s'il est temps de le lire.

Les associations explicites figurent dans `cotes/theodds.py`. La liste de tous les
sports offerts en cotes n'est pas une liste de sports disponibles en résultats.

- Basket (NBA, WNBA, Euroligue masculine, NBL Australie, NCAA), football américain
  (NFL, NCAA) : marchés sur le score du match entier, prolongation comprise.
- Football : certains championnats nationaux identifiés ; score du temps
  réglementaire. Coupes, phases finales et compétitions à playoffs avec prolongation
  ne sont pas associés, car l'API ne fournit pas le détail 90 minutes/prolongation.
- Hockey (NHL, SHL, HockeyAllsvenskan) : vainqueur du match entier uniquement.
  Aucun total ni handicap n'est réglé avec ce secours, faute de détail des tirs au but.
- Handball : Bundesliga allemande identifiée, marchés sur le score du match.
- Tennis, baseball, volley, rugby et autres compétitions : pas de règlement avec
  cette première intégration. Les périodes, abandons ou conditions de match ne sont
  pas suffisamment détaillés dans cette réponse pour appliquer leurs règles.

Mi-temps, quart-temps, temps réglementaire des sports à prolongation, joueurs,
corners, cartons et mi-temps/fin ne sont jamais ajoutés au résultat de secours.
L'autorisation est donnée **par identifiant de pari** : un résultat sur le match
entier ne peut pas régler accidentellement un autre pari du même match.

Une trace `preuve_reglement.preuve_source` contient l'identifiant The Odds API,
la compétition, l'heure de début, l'heure de lecture et `completed: true`.
Le résultat reste une simulation ; aucune mise n'est effectuée.

## Diagnostic

Dans la branche `donnees`, `etat.json` → `dernier_cycle_reglement.theodds` contient :
clés configurées et valides, requêtes scores de ce cycle, matchs trouvés, conflits,
crédits réservés par jour/mois et quota API restant par compte. Le même bilan est
imprimé dans l'étape « Régler les paris sans scanner les cotes » de GitHub Actions.
Les erreurs indiquent uniquement un numéro de compte et un état HTTP ; aucune URL,
clé ni réponse d'erreur brute n'est publiée. `theodds.json` garde les compteurs et
scores, avec une empreinte non réversible pour distinguer un remplacement de clé.

Sources officielles vérifiées le 14/10/2026 :
[documentation V4](https://the-odds-api.com/liveapi/guides/v4/),
[couverture des résultats](https://the-odds-api.com/sports-odds-data/sports-apis.html),
[offres](https://the-odds-api.com/).
