# Notifications Chrome — Cotes Value

Dans Chrome sur Android, ouvrir l'onglet **Notifications**, cocher les stratégies,
puis **Activer les notifications** et accepter la permission Chrome. Le bouton
**Envoyer un test** vérifie la réception sur cet appareil. Aucune installation
d'application n'est nécessaire. Les choix sont propres à chaque appareil.

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
