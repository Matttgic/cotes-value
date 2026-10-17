# Audit final contradictoire et consolidé — 17 octobre 2026

## Verdict et limites

Le rapport d'Argon mélange des observations anciennes, des recommandations justifiées et quelques corrections qui dégraderaient la fiabilité. Plusieurs de ses dernières « anomalies » ont déjà été traitées lors des étapes précédentes.

Cette passe vérifie le code courant, l'historique du code, les diagnostics historiques ciblés, les artefacts publics et les permissions réelles des notifications Supabase. Elle ajoute des protections sans modifier les stratégies, les mises ou les règlements historiques.

**L'audit n'est pas une certification exhaustive de sécurité ni de rentabilité.** La revue approfondie des cinq moteurs Gemini, Jules v1, M3, stratégies prudentes et laboratoire reste à effectuer. Les configurations GitHub protégées non accessibles aux outils ne sont pas supposées sûres ou modifiées.

## État des quinze recommandations

| Recommandation | État vérifié et décision |
|---|---|
| Retirer la clé Pinnacle du code | **Ouvert.** Surcharge par `PINNACLE_API_KEY` déjà disponible, mais valeur guest conservée en secours. Aucun retrait complet ni rotation annoncé. |
| Ignorer `.env` | Déjà fait : `.env`, `.env.*`, exception `.env.example`. Ajout des fichiers système usuels. |
| Ajouter `.env.example` | Déjà présent ; enrichi avec l'espacement PulseScore et les variables serveur Supabase. Les quatre noms réels The Odds API sont documentés, pas un nom de variable inutilisé. |
| Passer à `main` | **Non exécuté.** Nom de branche non standard, mais pas une faille. Migration à coordonner avec Actions et l'autorisation OIDC déployée. |
| Ajouter la CI pytest | Déjà présente et exécutée. Elle teste toutes les branches poussées et les PR, en Python et JavaScript. Ajout du contrôle de secrets et de permissions `contents: read`. |
| Corriger les dates du contrôle | Traité : analyse de dates avec fuseau et comparaison temporelle, au lieu du seul ordre lexical ISO. |
| Refuser les comparaisons sans date | Traité : une fraîcheur sans horodatages fiables n'est pas acceptée. |
| Vérifier HTTP avant le JSON API-Sports | Traité, avec protection du cache en cas d'erreur fournisseur. API-Sports reste désactivé dans les workflows usuels. |
| Résister aux archives corrompues | Traité : lecture stricte par défaut pour ne pas produire un faux bilan incomplet ; mode partiel explicite disponible avec diagnostics. Ignorer silencieusement une archive financière n'est pas retenu. |
| Empêcher pertes/doublons d'archive | Traité : identifiants stables, copies identiques dédupliquées, conflits explicites, écritures temporaires validées et reprise idempotente. |
| Refuser les cotes non finies | Traité dans la marge et les validations des connecteurs concernés. |
| Rendre Pinnacle brut non pariable | Traité : témoin explicitement séparé, nouvelles créations coupées dans le workflow, lignes individuelles exclues du catalogue public ; agrégats historiques conservés. |
| Sécuriser `tranche()` | Traité : entrées invalides signalées explicitement, sans classement financier fictif. |
| Sécuriser `gain()` | Traité : statut inconnu signalé par `ValueError`. Retourner zéro aurait masqué une incohérence de règlement. |
| Ajouter et exécuter les tests | **773 tests Python + 39 JavaScript = 812 tests** sur cette version. Les tests ne constituent pas une mesure complète de couverture de toutes les branches du code. |

## Secrets : recherche effectuée et ce qu'elle ne prouve pas

Le dépôt local a été récupéré sans limite superficielle pour examiner le passé du code. La recherche ciblée parcourt :

- l'arbre des fichiers suivis de la version courante ;
- **631 blobs texte de l'historique de la branche de code** avant ce correctif : trois occurrences de la valeur guest déjà identifiée, aucun autre format sensible détecté ;
- **1 449 blobs historiques de `etat.json` et `notifications_diagnostic.json`**, sur les références disponibles : aucune alerte selon les motifs utilisés.

Les contrôles recherchent notamment jetons GitHub reconnaissables, clés secrètes Supabase, JWT `service_role`, clés privées PEM, affectations sensibles à forte entropie et secrets dans certains paramètres d'URL. Les rapports n'affichent que chemin, ligne, type et empreinte. Le test de l'outil vérifie qu'une valeur retirée du fichier courant reste détectée dans un ancien commit, sans l'imprimer.

**Limite importante :** les références locales comprennent environ 19,5 Go de blobs historiques, essentiellement les snapshots de données sportives. Tous les anciens `paris.json`, relevés de cotes et autres données volumineuses n'ont pas été balayés exhaustivement. Les objets supprimés/inaccessibles aux références, les copies GitHub externes, les logs Actions et les archives de services tiers ne sont pas certifiés par cette recherche. Une recherche à motifs peut manquer un secret propriétaire ou encodé.

La valeur Pinnacle est identifiée par empreinte dans le contrôle et reste une exception visible. Le contrôle n'a pas l'autorisation de lire/créer les secrets GitHub Actions ; l'existence d'une configuration de remplacement valide n'est donc pas supposée. Enlever le secours sans cette validation risquerait de couper la principale référence. La migration reste à terminer : secret `PINNACLE_API_KEY` compatible, collecte validée, retrait du défaut. Une vraie clé de compte exposée nécessiterait également révocation/rotation, pas seulement un changement de fichier.

## Supabase vérifié en production, sans lire les abonnements

La vérification porte uniquement sur les objets `cv_push_*` du projet utilisé par le dépôt. Aucun abonnement, jeton d'appareil ou contenu de la table de configuration n'est extrait.

| Objet | Contrôle observé |
|---|---|
| `cv_push_config` | RLS active ; aucune permission de lecture/écriture `anon` ou `authenticated` |
| `cv_push_devices` | RLS active ; aucune permission de lecture/écriture `anon` ou `authenticated` |
| `cv_push_deliveries` | RLS active ; aucune permission de lecture/écriture `anon` ou `authenticated` |
| `cv_push_claim`, `cv_push_register` | `SECURITY INVOKER` ; exécution refusée à `anon`/`authenticated`, permise au rôle serveur |

Les avis « RLS activée sans politique » sur ces tables privées ne justifient pas d'ajouter une politique publique : l'accès est volontairement réservé au backend serveur. Les autres objets du projet Supabase ne font pas partie de cette revue.

La fonction déployée a été comparée au code du dépôt avant modification. Sa vérification JWT de passerelle désactivée est intentionnelle : les inscriptions d'appareil sont publiques, tandis que l'envoi `/dispatch` vérifie lui-même la signature GitHub OIDC, l'émetteur, l'audience, l'âge, le dépôt, la branche et le workflow. La clé service role n'est lue que par le runtime serveur. Le navigateur ne reçoit aucune clé Supabase anon ou service role ; le point `/config` ne renvoie que la clé publique VAPID et les stratégies.

Deux protections supplémentaires sont appliquées :

- contrôle exact de l'identifiant immuable du propriétaire GitHub, en plus des contrôles du dépôt et du workflow ;
- lecture des requêtes bornée à **200 000 octets**, même sans `Content-Length` ou avec une taille mensongère. La lecture est annulée dès dépassement ; l'ancien contrôle après `req.text()` pouvait charger tout le corps en mémoire. Une chaîne UTF-8 coupée entre deux blocs est correctement décodée.

Les réponses restent `Cache-Control: no-store` et ajoutent `X-Content-Type-Options: nosniff`. Aucun test de cette revue n'envoie de notification réelle à un utilisateur. Le service conserve ses limites existantes : inscription sans compte, plafond de vingt appareils, restrictions des fournisseurs Push et anti-doublons. L'absence de compte ne constitue pas une protection complète contre l'abus d'inscriptions ; une exposition commerciale demanderait une politique d'accès et de débit adaptée.

## Interface, cache et publication

Le dossier `web/` est frontend. Le backend existe ailleurs : `supabase/functions/cv-notifications`. L'absence de serveur dans `web/` ne signifie donc pas l'absence de backend dans le projet.

Le service worker ne définit aucun gestionnaire `fetch` et ne crée aucun cache réseau. Il ne stocke en IndexedDB que l'identifiant et la date des notifications déjà vues. Les préférences et le jeton aléatoire d'appareil restent dans le stockage local du navigateur ; ce sont des données pseudonymes à protéger, pas des données anonymes garanties.

Les appels privés du navigateur précisent désormais `cache: no-store`, sans cookies ni référent. La configuration publique et le contrôle de version utilisent déjà `no-store`. Le HTML et les données sportives restent soumis au CDN GitHub Pages ; l'actualisation automatique existante utilise une empreinte de version pour éviter les pages durablement anciennes. Une balise HTML ne permettrait pas de changer à elle seule les en-têtes du CDN.

Avant toute écriture, le générateur vérifie les données destinées au HTML, au journal papier et au flux public d'alertes. Les champs privés connus (`subscription`, jetons, autorisation, clés privées, etc.) ou des motifs de secrets provoquent un refus explicite. Lorsqu'un secret est présent dans l'environnement du build, sa valeur exacte est aussi contrôlée. La page précédente n'est pas remplacée par un artefact dangereux. Ce contrôle est une défense supplémentaire, pas une autorisation à stocker des secrets dans la branche de données.

Le JSON embarqué échappe désormais `<`, `>` et `&`, y compris les formes `<script` et `<!--`, tout en préservant les données après décodage. Les données affichées continuent d'être échappées par le rendu existant. Les tests injectent des contenus de balisage et vérifient que la structure du script n'est pas modifiée.

## Branche par défaut et migration

La branche par défaut réelle est `ccr-148b8ccc-phitmr`. Son nom ne donne pas de privilèges à un attaquant. Renommer seul la branche ne corrigerait aucune des failles ci-dessus.

La migration doit couvrir au minimum :

1. Les déclencheurs de collecte, règlement, publication et sondes qui mentionnent explicitement cette branche.
2. La règle `validClaims()` de la fonction déployée, qui autorise actuellement le seul workflow de collecte de cette branche.
3. La branche par défaut GitHub, les protections et les éventuelles références externes de lancement.
4. Une validation du flux de collecte et d'authentification des alertes après bascule.

Aucun nom de branche, réglage de protection, chaîne de collecte ou droit d'envoi n'est élargi dans cette passe. Les outils disponibles ne permettent pas de modifier les réglages de branche par défaut/protection ni les secrets GitHub ; leur état exact ne doit pas être inventé.

## Vérification des bilans et livrables

Les contrôles financiers et de sélection restent identiques sur le relevé local de **12 712 paris**. Il s'agit d'un relevé de contrôle, pas d'une certification du dernier état des paris en production.

Le site se génère, son JavaScript est syntaxiquement valide, les tests Python et Node passent. Les tests ajoutés couvrent la publication refusée sans écraser la page précédente, l'échappement des données, les formats de secrets et leur historique, l'identité du propriétaire GitHub, la limite de corps en octets et l'absence de cache réseau du service worker.

Les comptes rendus précédents restent disponibles :

- [Marge, comparaison et contrôle](audit-marge-controle-2026-10-17.md)
- [Résultats et règlement](audit-resultats-reglement-2026-10-17.md)
- [Simulation et décisions](audit-simulation-decisions-2026-10-17.md)
- [Stockage et convergence](audit-stockage-convergence-2026-10-17.md)
- [Connecteurs, partie 1](audit-connecteurs-partie1-2026-10-17.md)
- [Connecteurs, partie 2](audit-connecteurs-partie2-2026-10-17.md)
- [Stratégies, partie 1](audit-strategies-partie1-2026-10-17.md)

Références officielles consultées pour la revue Supabase : [sécurité de la Data API](https://supabase.com/docs/guides/api/securing-your-api), [authentification des Edge Functions](https://supabase.com/docs/guides/functions/auth), [changelog](https://supabase.com/changelog). La récupération Markdown du changelog n'étant pas prise en charge par le lecteur, sa version HTML a été examinée. Aucun changement récent pertinent ne nécessite de modifier l'architecture utilisée ici.
