# Revue contradictoire — Connecteurs externes, partie 2, 17 octobre 2026

## Verdict

L'audit identifie des défauts réels de journalisation, de conversion et de cache. Son appréciation « globalement bien conçus » ne suffit toutefois pas à garantir un comportement sûr sur des réponses partielles. Les correctifs proposés ne doivent pas être repris littéralement partout.

Cette passe concerne Kalshi, PulseScore et Prop-Line, avec les raccordements nécessaires dans le cycle. Elle ne modifie ni critères de stratégie, ni mises, ni décisions figées, ni résultats historiques. Elle ne place aucun pari réel.

## Kalshi

### HTTP, pagination et fraîcheur

- Les erreurs HTTP sont visibles dans un journal borné à 30 messages distincts et remontent dans l'état du cycle comme source dégradée.
- Aucun corps de réponse, paramètre, URL complète ou texte d'exception n'est journalisé.
- 401/403/429 coupent les nouvelles requêtes Kalshi restantes du cycle. Des appels déjà en vol peuvent se terminer, puisque les séries sont lues en parallèle.
- Les erreurs réseau, 408 et 5xx ont au plus trois essais ; les autres erreurs permanentes ne sont pas réessayées. Aucun délai après le dernier échec.
- Un objet JSON est exigé. Séries, tags, événements, marchés et curseurs sont contrôlés ; une pagination qui répète son curseur s'arrête.
- Chaque page porte sa véritable heure de réception HTTP. Elle n'est plus remplacée par l'heure de fin de la collecte entière.

Cette date prouve la réception de la réponse, pas la date de dernière mise à jour interne des ordres par le fournisseur. L'arrêt sur 429 est limité au cycle ; aucun ordonnanceur persistant Kalshi fondé sur `Retry-After` n'est ajouté.

### Heure estimée

Le constat d'Argon doit être précisé : après association, `comparer()` utilise déjà le coup d'envoi du bookmaker français, et `suivre_cloture()` utilise cette même date enregistrée dans le pari. L'heure estimée Kalshi n'était donc pas directement l'horloge de placement ou de CLV.

Elle intervient dans le radar et dans le rapprochement des événements. Le radar tolère désormais cinq heures autour de son horizon pour les seules dates approximatives, en cohérence avec la tolérance d'association déjà existante. Une estimation passée ne suffit plus à retirer un sport exclusif de la collecte française. Cela ne prouve ni qu'un match est ouvert au pari ni qu'il n'a pas commencé : l'horaire français et les garde-fous de placement restent obligatoires.

Les règles de rapprochement ne changent pas. Des affiches répétées ou une estimation particulièrement mauvaise restent une limite de cette référence.

### Prix et nul

Les prix doivent être numériques, finis, non booléens et vérifier `0 < bid <= ask < 1`. La liquidité invalide devient zéro. Un groupe incomplet, une issue fermée ou inconnue, des noms d'issues identiques ou un nombre d'issues incohérent empêchent la renormalisation entière. On ne transforme plus trois issues dont une invalide en référence à deux issues.

`Draw`, `Tie` et quelques suffixes explicites comme `Draw (90 mins)` sont reconnus. Un simple `startswith("tie")` est écarté : il confondrait notamment `Tielemans FC` avec un nul. Les variantes inconnues restent refusées plutôt que devinées.

Le milieu bid/ask reste un indicateur de référence, pas un prix d'exécution garanti.

## PulseScore

### Diagnostic et quotas

Les deux usages de `repr(exception)` sont supprimés. Une erreur réseau garde un message générique ; une exception inattendue de collecte ne garde que son type. Les paramètres, l'en-tête `X-Secret` et le texte d'une exception ne sont pas recopiés dans les diagnostics.

Les réponses doivent être des objets JSON ; les listes d'événements sont vérifiées. Les dates sans fuseau sont refusées. Les cotes et lignes numériques sont converties en valeurs finies ; booléens, NaN, infinis et chaînes invalides sont exclus. Une sélection défectueuse n'empêche pas de traiter les autres sélections valides. Un marché mal formé n'annule pas les autres marchés exploitables.

Un nul annoncé mais doté d'une cote invalide reste constitutif du type 1N2 : ses deux autres issues ne deviennent pas un marché « vainqueur » à deux issues.

`Retry-After` accepte un nombre de secondes ou une date HTTP. Une valeur invalide utilise le délai de repli ; elle n'arrive jamais telle quelle dans `sleep()`. Les attentes de plus de 60 secondes sont différées sans sommeil bloquant. Les refus 401/403 suspendent le bookmaker une heure. Les délais sont enregistrés dans `pulsescore_attentes.json`, partagé par la collecte pré-match et la lecture des résultats, sous le verrou de données existant.

L'état ne contient qu'une empreinte de la clé et les dates d'attente par bookmaker. Un changement de clé réinitialise les attentes. Un 429 Winamax ne bloque pas Betclic, y compris lorsque les résultats utilisent un client commun. Les compteurs continuent de compter chaque tentative HTTP émise.

Le journal papier Live et les sondes indépendantes ne sont pas raccordés à ce fichier d'attente dans cette passe. Leurs appels constituent donc encore un périmètre distinct. Les erreurs serveur PulseScore conservent leur comportement précédent : diagnostic et retour à l'appelant, sans nouvelle politique de réessai 5xx ajoutée ici.

### Périodes

La table hockey mentionnée par l'audit était effectivement inaccessible, car la fonction refuse volontairement une période canonique ambiguë sans libellé explicite. L'activer aurait élargi les traductions sans preuve.

Le code mort est supprimé. Le hockey continue d'exiger son libellé de période. Au tennis, les alias établis `FIRST_SET`, `SECOND_SET` et `FIRST_HALF` sont conservés ; les replis incohérents vers des mi-temps ou quarts-temps sont supprimés. Les règles de prolongation par bookmaker restent intactes.

## Prop-Line

### Pourquoi ne pas conserver aveuglément le dernier final ?

Le correctif « ne supprimer que si `deleted == True` » laisserait exploiter un ancien final même si le fournisseur vient de déclarer le match annulé, en cours ou incomplet sans ce champ. C'est un risque de règlement faux.

Le compromis retenu :

1. Conserver le dernier score final valide dans le cache.
2. Si une nouvelle réponse du même identifiant et de la même compétition ne confirme plus ce final, ou le marque supprimé, inscrire son identifiant dans `a_reconfirmer`.
3. Exclure ce score du règlement automatique, même s'il reste stocké.
4. Réessayer selon les budgets et espacements existants. Seul un nouveau final valide lève la suspension ; une liste vide ou un échec HTTP/JSON ne la lève pas.
5. Nettoyer ces marqueurs avec la durée de conservation de huit jours et afficher leur nombre dans le diagnostic `matchs_a_reconfirmer`.

Une panne HTTP/JSON sans contradiction identifiée ne détruit pas les autres scores validés en cache. Le JSON invalide a désormais son propre diagnostic, sans texte de réponse ni clé.

Cette protection concerne les paris encore à régler. Elle ne réécrit pas automatiquement les règlements déjà enregistrés, et ne transforme pas un statut fournisseur « annulé » en remboursement : les règles de règlement restent séparées.

Les plafonds ne changent pas : 24 appels maximum par cycle, budget local de 800 appels/jour, arrêt à 100 crédits restants annoncés. Le budget local ne voit pas les appels effectués ailleurs avec la même clé. Les trous de couverture tennis, volley, périodes et certaines compétitions ne sont pas résolus par ces correctifs de robustesse.

## Validation

- **710 tests Python et 36 tests JavaScript : 746 tests au total.**
- 58 nouveaux cas Python couvrent notamment les erreurs HTTP/JSON, les diagnostics sans secret, les délais persistants par bookmaker, les prix invalides, les issues incomplètes, les périodes et la suspension/reconfirmation du cache.
- Les tests sont simulés, sans requêtes aux fournisseurs ni pari réel.
- Les tests d'intégration vérifient le radar complémentaire Kalshi, la remontée des erreurs et l'autorité de l'heure française pour placement/clôture malgré une estimation décalée de ±2 heures.
- Sur le relevé de contrôle de **12 712 paris**, les sélections préexistantes et indicateurs financiers comparés sont identiques. Il s'agit du relevé local de contrôle, pas d'une certification des dernières données de production.
- Génération du site réussie et JavaScript embarqué accepté par `node --check`.
- Aucun fichier de paris ou résultat de production n'est modifié par cette revue.

Les tests ne certifient ni la disponibilité actuelle des API, ni la latence réelle d'une notification, ni l'absence de secrets dans tout l'historique Git. La revue des stratégies annoncée pour l'étape 7 reste distincte.
