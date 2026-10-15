# Secours de règlement Prop-Line

Ajouter le secret GitHub Actions `PROPLINE_API_KEY` puis lancer le workflow
**Règlement des paris**. Ne jamais inscrire la clé dans un fichier du dépôt.
Les workflows de collecte et de règlement transmettent ce secret ; les comptes
API-Sports suspendus ne sont plus interrogés par ces workflows.

Documentation vérifiée le 15/10/2026 : https://prop-line.com/docs et
https://api.prop-line.com/openapi.json. L'offre gratuite annonce 1 000 requêtes
par jour et inclut `GET /v1/sports/{sport_key}/scores?days_from=3`.
`/results`, qui fournit des verdicts par pari, demande un abonnement : il n'est
pas utilisé. Le module ne collecte pas de cotes et ne place aucun pari.

Le secours intervient après les sources existantes, seulement pour les paris
encore sans résultat validé, commencés depuis au moins six heures. Un appel
renvoie les scores de toute une compétition. Les résultats sont conservés huit
jours, les appels espacés d'une heure et limités à 24 par cycle, 800 par jour
localement, avec une réserve de 100 sur le quota remonté. Les refus d'accès et
quotas bloquent les appels suivants pendant au moins une heure (`Retry-After`
respecté). La clé passe par l'en-tête `X-API-Key`, jamais dans l'URL ; ni la clé
ni les corps d'erreur ne sont journalisés.

Seul `status: final` avec deux scores entiers est recevable. `expired`, les
annulations, reports, abandons et périodes partielles ne règlent rien.
Le rapprochement exige deux équipes fortement compatibles, une compétition
explicite, un horaire à ±30 minutes et un candidat unique. Une contradiction
avec une autre source bloque le règlement. La preuve contient l'identifiant
Prop-Line, l'horaire, le statut final et la date de lecture.

Couverture initiale : NBA, WNBA, NCAAB, NHL (vainqueur seulement), NFL/NCAAF,
et certaines ligues de football identifiées explicitement dans le module.
Pas de coupes ou ligues de football à playoffs : le score à 90 minutes n'est
pas distingué. Pas de tennis, MLB/doubleheaders, volley, KHL, basket européen,
mi-temps ou paris joueurs dans ce raccordement. Un catalogue marketing ou
une clé valide ne garantit pas que les scores d'une compétition seront fournis.

Le même score n'autorise que les identifiants de paris compatibles : les autres
marchés du match restent en attente. Prop-Line réutilisant notamment ESPN,
ses réponses ne sont pas ajoutées comme une voix indépendante au consensus.

`etat.json` → `dernier_cycle_reglement.propline` expose appels, quota restant,
couverture, conflits et erreurs sans secret. L'onglet **À régler** en affiche
un résumé. La présence du secret ne signifie pas « clé validée » tant qu'aucune
requête pertinente n'a reçu une réponse exploitable. Les 16 tickets encore
en attente au relevé du 15/10 à 15h29 ne sont pas garantis couverts.
