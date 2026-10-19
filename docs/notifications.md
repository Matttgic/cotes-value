# Notifications Chrome — Cotes Value

Dans Chrome sur Android, ouvrir l'onglet **Notifications**, cocher les stratégies,
puis **Activer les notifications** et accepter la permission Chrome. Le bouton
**Envoyer un test** vérifie la réception sur cet appareil. Aucune installation
d'application n'est nécessaire. Les choix sont propres à chaque appareil.

Toutes les stratégies du site peuvent être suivies, en trois groupes : les comparateurs
(Claude, ChatGPT, Gemini, Jules, Eden, M3, variantes et convergences), puis les 12 règles
Pinnacle et les 12 règles Polymarket de la page Stratégies, avec la même numérotation
(« Pinnacle 2 » = cotes 1,30–2,00, edge ≥ 2 %, jusqu'à 36 h avant le match). Chaque règle
affiche ses paris réglés, sa réussite et son ROI depuis le 14/10. Une règle du laboratoire
garde ses prises depuis ce début de suivi, une par match. Le service Supabase accepte toute
clé de stratégie bien formée (comparateur ou `labo:<règle>`) : ajouter une stratégie au site
ne demande plus de le redéployer.

Les nouvelles sélections sont transmises à la fin des scans (environ cinq
minutes, parfois davantage si GitHub ou les API retardent un cycle). Une cote
peut bouger entre sa détection et l'ouverture du bookmaker. Cette fonctionnalité
ne promet pas de réserver un prix et ne place aucun pari.

## Sélection et dédoublonnage

- Choix des six comparateurs de base, de Convergence ≥2 et des deux variantes
  prudentes ; Jules v1 et v2 restent une famille unique dans les convergences.
- Le flux utilise les sélections officielles, avec leurs plafonds, dates de
  lancement et dédoublonnages. Il ne réapplique pas seulement des seuils d'edge.
- Même bookmaker, match, marché, période, ligne, issue, joueur et prix que la
  cote encore proposée au dernier passage. Témoins et offres suspectes exclus.
- Un identifiant stable regroupe les références et votes : une seule alerte par
  appareil et par sélection au même prix, même si plusieurs stratégies votent.
- Les dates sont conservées par stratégie. Ajouter une stratégie ne transforme
  pas les prises anciennes des autres stratégies en nouvelles alertes.
- Seules les prises après activation ou changement des préférences sont
  recevables. Pas de rattrapage historique à l'inscription.
- Prise datant de moins de 15 minutes, coup d'envoi à plus d'une minute,
  relevé transmis depuis moins de dix minutes. Expiration du push après cinq
  minutes au maximum ; une notification reçue trop tard n'est pas affichée.

## Architecture

`cotes/notifications.py` produit `site/notifications.json` à partir des mêmes
prises que les badges du site. `scripts/envoyer_notifications.py` transmet ce
flux après sauvegarde des données, avant la publication Pages, pour éviter
de retarder les alertes avec le déploiement du HTML. Une panne de notification
ne bloque pas le scanner ; l'étape GitHub Actions indique l'erreur.

Le service `cv-notifications` est isolé dans le projet Supabase déjà actif
`EdgeScope` (`tapotyftgyacbnjmeovn`). Il ne modifie pas les tables ou fonctions
de cette application. Les trois nouvelles tables `cv_push_*` sont fermées aux
rôles publics : RLS activée, aucun droit `anon`/`authenticated`. Le schéma est
reproduit dans `notifications-schema.sql` ; migration appliquée via Supabase.

La clé VAPID privée est générée côté serveur et conservée dans `cv_push_config`.
La page ne reçoit que la clé publique. La configuration vérifie la création
d'une requête chiffrée sans l'envoyer. Les dépendances directes de l'expéditeur
sont fixées à `web-push@3.6.7` et `jose@6.1.0`.

Chaque appareil possède un UUID et un secret aléatoire de 256 bits, stockés
localement. Le serveur ne conserve que l'empreinte de ce secret. Lecture des
préférences, test et désactivation exigent cette preuve. L'inscription valide
l'abonnement navigateur, impose une origine CORS exacte et limite le service
à 20 appareils. Seuls les endpoints HTTPS des fournisseurs de push autorisés
sont acceptés, sans redirections. Aucun abonnement n'est publié dans GitHub.

L'envoi de nouvelles alertes exige un jeton OIDC GitHub signé : issuer,
audience, dépôt immuable `1404917041`, nom, branche et chemin du workflow de
collecte sont contrôlés. Aucun secret d'envoi n'est à copier dans GitHub.
`verify_jwt=false` à la passerelle Supabase est nécessaire pour cette identité
externe ; l'authentification est assurée dans la fonction.

Les livraisons utilisent une réservation atomique en base, jusqu'à trois essais
espacés d'au moins deux minutes. Le service worker dédoublonne aussi dans
IndexedDB. Les abonnements expirés (HTTP 404/410) sont retirés, les appareils
non actualisés depuis 90 jours supprimés, les livraisons nettoyées après huit
jours. **Désactiver** supprime l'abonnement ; si le serveur est momentanément
injoignable, le navigateur se désabonne tout de même.

`sw.js` n'intercepte aucune requête et ne met pas le HTML en cache. Le clic sur
une notification ouvre **À jouer**. Les versions du site antérieures au
déploiement doivent être rechargées une fois pour afficher le nouvel onglet.

## Validation et limites

Tests Python du flux, de l'identité GitHub et des prix ; tests Node des
préférences, de la fraîcheur, du refus des envois non autorisés, des endpoints,
des doublons et du service worker. Inscription/préférences/désactivation et
réservation atomique vérifiées sur le service déployé avec un appareil
synthétique supprimé immédiatement, sans push envoyé.

La réception Android doit être confirmée par le bouton **Envoyer un test** sur
le téléphone. Les permissions Android, l'économie de batterie, l'arrêt forcé
de Chrome et les coupures réseau peuvent retarder ou empêcher la livraison.
Le plafond d'une stratégie atteint avant l'activation ne sera pas contourné.

Références : https://developer.mozilla.org/en-US/docs/Web/API/Push_API ;
https://supabase.com/docs/guides/functions/auth ;
https://docs.github.com/en/actions/concepts/security/openid-connect.

## Fraîcheur et chemin rapide — 17 octobre 2026

La collecte Actions s'exécute en trois phases sous le même verrou des données :

1. `cycle.py --reglement non --sans-site` collecte, compare et sauvegarde les prises ; commit/push des données.
2. `envoyer_notifications.py --donnees donnees --flux notifications-rapides.json` recalcule les mêmes sélections officielles et demande les envois, avant la génération du site et les sources de résultats.
3. `cycle.py --seulement-reglement --reglement auto` conserve le rattrapage du règlement horaire et construit le site ; second commit des résultats et diagnostics.

Une erreur d'envoi ne bloque pas la phase de règlement. Les alertes ne précèdent jamais la sauvegarde distante des prises. Les plafonds, règles et prix d'origine des stratégies restent identiques.

Pour les nouveaux relevés PulseScore, `collecte_recue` est l'heure de réception de la réponse par page, avant la pause volontaire entre requêtes ; `collecte_debut` décrit le début de sa requête logique, retries compris. Pinnacle horodate la réponse des marchés par sport. Ces heures locales ne prouvent pas l'heure de mise à jour interne du fournisseur, qu'on ne possède pas toujours. Les anciens `detecte` ne sont pas réécrits et restent parfois des heures de début de lot.

Les alertes écartent les prix de plus de cinq minutes à la préparation et les dates futures. L'heure du prix figure dans le texte de notification, sans changement nécessaire du service Supabase. La déduplication et la date de validation de chaque stratégie restent intactes. Une notification n'est pas une réservation de cote : le prix peut encore changer avant le clic, et Chrome peut retarder la réception.

`notifications_diagnostic.json` conserve les 100 dernières tentatives de cycles : préparation, début/fin de demande d'envoi, métadonnées publiques des signaux et bilan agrégé de l'expéditeur. Aucun jeton ni abonnement n'y figure. `sent` signifie une acceptation par le service Push, pas une réception certifiée sur le téléphone, et n'est pas un résultat individuel par signal. Le site affiche « Envoi demandé », jamais une réception inventée.

`prix_revu` / `prix_revu_le` suivent la dernière lecture API du même marché, période, ligne et issue. Ils ne modifient pas `cote`, `ecart`, `mise` ou les résultats de la prise. Une ligne absente ne produit pas un faux nouveau prix ; sa dernière observation vieillit simplement. Les cotes modifiées et l'heure de lecture sont visibles dans Paris et les listes de stratégies, avec l'heure du relevé initial.

### Variante M3 Max 3 et décisions figées (17 octobre)

`m3_structure` est un abonnement distinct, jamais activé automatiquement. Le
service Push accepte cette nouvelle clé ; les abonnements existants gardent
leurs choix. La variante ne donne aucun vote supplémentaire aux convergences.
Les nouvelles prises enregistrent leurs sélections et leurs refus avant la
sauvegarde utilisée par l’envoi. Le registre n’est pas rempli rétroactivement.

## Webhook Pinnacle 2

En plus des alertes Chrome, chaque nouvelle prise de la stratégie `labo:PIN-1.3-2-e2-h36` (Pinnacle 2) est
envoyée en JSON, une requête par alerte, à l'URL du secret GitHub `ALERTE_WEBHOOK_URL` (la clé du secret
`ALERTE_WEBHOOK_KEY` est envoyée dans l'en-tête `x-api-key`, ou celui de la variable de dépôt
`ALERTE_WEBHOOK_CLE_ENTETE`). Sans `ALERTE_WEBHOOK_URL`, rien n'est envoyé. L'URL doit être en https.

Corps : `id`, `match`, `ligue`, `debut` (UTC), `marche`, `selection`, `bookmaker`, `cote`, `cote_min`
(max(1,30 ; cote juste × 1,02) : en dessous, l'edge tombe sous 2 %), `cote_juste`, `cote_pinnacle` (cote brute,
marge comprise), `ecart` (edge) et `recheck`.

- Les paris ajoutés par la re-décision (`redecider_ouverts`) sont envoyés avec `recheck: true`, tant que le match
  n'a pas commencé, même s'ils datent de plus de 15 minutes : le prix a pu bouger, à revérifier contre `cote_min`.
- Les id déjà envoyés sont gardés trois jours dans `webhook_envoyes.json` (branche `donnees`) : pas de doublon.
- Délai de 5 s par requête et 25 s au total, 20 alertes au plus par passage. Une erreur est comptée dans
  `notifications_diagnostic.json` (champ `webhook`, sans URL ni clé) et ne bloque ni le scan ni les alertes Chrome.
