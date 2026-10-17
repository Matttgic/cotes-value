# Sécurité et configuration

Ne publiez jamais de clé de compte, de jeton GitHub, de clé privée Web Push ou d'abonnement de notification dans une issue, un commit ou une capture. En cas d'exposition d'un vrai secret, le révoquer/remplacer d'abord : retirer une ligne du dernier commit ne le supprime pas de l'historique.

## Configuration

`.env` et ses variantes sont ignorés. `.env.example` documente uniquement des emplacements vides et des paramètres publics. Le programme ne charge pas `.env` automatiquement ; les variables doivent être exportées ou configurées dans l'environnement du service.

Les clés des fournisseurs vont dans les secrets GitHub Actions. Les variables `SUPABASE_URL` et `SUPABASE_SERVICE_ROLE_KEY` restent côté fonction serveur Supabase. Le navigateur n'a besoin d'aucune clé Supabase anon/service role : il utilise l'API de notifications. Seule la clé **publique VAPID** peut lui être transmise.

**Point ouvert :** `cotes/pinnacle.py` conserve la valeur guest historique lorsque `PINNACLE_API_KEY` est vide. Cette exception est signalée par le contrôle de secrets. Pour la retirer sans couper la référence, configurer et valider une clé compatible dans le secret GitHub Actions `PINNACLE_API_KEY`, puis supprimer le secours. Ne pas coller cette clé dans le dépôt ou dans une conversation. Le présent audit ne certifie pas le statut juridique/public de la valeur guest.

## Publication et contrôles

- Les données privées connues et certains formats de secrets bloquent la génération avant remplacement du site.
- Les données JSON intégrées au script HTML échappent les caractères de balisage.
- Les réponses des notifications sont `no-store`. Le service worker n'intercepte ni ne met en cache les requêtes réseau.
- Les abonnements et la clé privée VAPID restent dans des tables à RLS activée, sans accès `anon`/`authenticated`. Les fonctions SQL sont réservées au rôle serveur.
- `python scripts/verifier_secrets.py` examine les fichiers suivis ; la CI l'exécute.
- `python scripts/verifier_secrets.py --historique --sortie audit-local.json` examine les blobs de l'historique de `HEAD`. Utiliser une copie non superficielle du dépôt. Le rapport contient des empreintes, jamais les valeurs trouvées.
- Un rapport sans alerte ne garantit pas l'absence de tout secret. Les formats propriétaires, les contenus encodés et les données hors périmètre demandent une revue complémentaire.

Le nom de branche n'est pas un contrôle de sécurité. Une migration vers `main` doit coordonner les déclencheurs Actions, la branche par défaut et la règle OIDC de la fonction de notifications. Les protections de branche sont un réglage GitHub distinct.
