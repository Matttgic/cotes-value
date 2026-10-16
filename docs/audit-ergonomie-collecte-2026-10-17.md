# Audit et décisions du 17 octobre 2026

L'audit fourni par Argon sert de point de départ. Ses chiffres portent sur ses relevés des 14–15 octobre, pas sur un nouveau décompte actuel de `paris.json`. Ce changement vérifie le code et ne recalcule aucun bilan historique.

## Décisions méthodologiques

- Plusieurs paris EV+ peuvent augmenter l'espérance totale. Leur corrélation augmente toutefois la variance du portefeuille : `Var(somme X) = somme Var(X) + 2 somme Cov(Xi, Xj)`. Cinq tickets d'un même match ne constituent pas cinq observations indépendantes.
- Les deux exemples gagnants ne prouvent ni un edge exploitable durable, ni une corrélation de 85 %. Cette valeur et une limitation de compte « très rapide » ne sont pas établies par les données présentées.
- La CLV est un indice de qualité du prix, conditionnel à la qualité du rapprochement, du contrat (règlement à 60 minutes ou prolongations, ligne, période), de la référence et du retrait de marge. Une CLV très élevée doit déclencher un contrôle, pas une certitude de gain.
- Le retrait de marge power est cohérent mais dépend d'hypothèses sur la répartition de la marge. La double chance dérivée du 1N2 est pertinente. Aucun de ces traitements ne garantit la justesse de la probabilité réelle.
- M3 a été optimisée a posteriori. On ne retire pas son vote d'un comparateur déjà suivi sous le même nom : cela modifierait rétrospectivement sa définition. Convergence ≥ 2 reste exploratoire et explicitement identifiée comme incluant M3. Le suivi distinct Convergence ≥ 3 hors M3 existe déjà ; ses votes demeurent aussi des règles corrélées, pas des experts indépendants.

### Compromis à tester, sans modifier les stratégies officielles

Proposition papier : budget fixe d'une unité par événement, deux sélections au maximum, au plus une par famille de marché et période (handicap, total match, total équipe, etc.), en conservant les contrôles de conformité et de fraîcheur. Un seuil d'edge supérieur à 4 % n'est pas validé par cet audit ; ne pas l'optimiser sur les exemples gagnants.

Pour un budget illustratif de 10 €, réserver 5 € à la première sélection et 5 € à une seconde famille éventuelle. Si une seule est détectée, 5 € restent inutilisés. Ne jamais diviser rétroactivement la première mise quand une autre sélection apparaît plus tard. Une politique différente peut affecter les 10 € dès la première prise et interdire tout ajout ensuite : elle correspond au mode 1/match existant.

Cette variante doit avoir un lancement propre et des mises enregistrées à la détection. Évaluer volume, CLV et couverture, ROI, perte maximale par événement et drawdown sur un suivi futur, avec incertitude regroupée par match. Aucun nouveau classement rentable n'est annoncé ici.

## Interface appliquée

- Horaires visibles sans ouverture des lignes dans À jouer, Paris, listes des stratégies, segments, laboratoire et À régler ; heure civile Europe/Paris, reports distingués.
- Aujourd'hui/demain sont calculés selon le calendrier parisien, y compris les changements d'heure. Compte à rebours à moins de deux heures, rafraîchi chaque minute sans rechargement.
- Filtres temporels et tri composés avec les filtres existants ; l'export CSV suit la même sélection. Les choix survivent à l'actualisation automatique.
- À jouer : en-tête de match commun, sport/ligue/horaire, tous les marchés et bookmakers visibles, plus grand edge mis en avant. Le plus grand edge n'est pas nécessairement le pari le plus fiable.
- Regroupement visuel conservateur par noms complets, sport et horaire : aucune fusion floue entre catégories ou matchs de dates différentes ; il ne change pas les sélecteurs.

## Backend appliqué

1. Pinnacle, Polymarket et Kalshi démarrent en parallèle. Les bookmakers français sont lus dès Pinnacle et Polymarket disponibles, sans attendre Kalshi. Un sport présent uniquement chez Kalshi conserve une lecture complémentaire ; pas de deuxième lecture des sports déjà couverts. Les erreurs de source restent isolées et les requêtes comptabilisées.
2. Les horodatages réels des lignes sont exposés dans `etat.json` / `dernier_cycle.fraicheur_prematch`. L'enveloppe est une borne globale, pas l'écart d'un match particulier. Le réseau peut toujours dépasser 45 secondes : ce délai n'est pas promis et les contrôles de contemporanéité existants restent actifs. Polymarket peut encore retarder l'étape si sa lecture est plus lente que Pinnacle.
3. `TEMOIN_PINNACLE_BRUT=non` dans la collecte : arrêt des nouveaux témoins à partir du premier cycle exécutant ce code. L'option `temoin_brut` du comparateur conserve son défaut antérieur pour les scripts et rejeux explicites. Aucun témoin historique n'est supprimé, annulé ou laissé volontairement sans règlement. Les anciennes archives et les bilans restent inchangés. Le poids du fichier actuel ne baisse donc pas immédiatement ; l'archivage existant continue.
4. `LIVE_PAPIER` désactivé par défaut (variable de dépôt explicite pour un éventuel diagnostic). Les journaux papier restent consultables. Pas de substitution de `received_at` aux timestamps source : recevoir une réponse maintenant ne démontre pas la fraîcheur de son score ou de ses prix. Pas de production artificielle de profils Gaussiens/Poisson depuis une seule cote ; il faut d'abord des contrats complets, des paramètres calibrés et une clôture archivée avant le début.
5. Le règlement automatique avec reprise dans la collecte reste actif. Paralléliser les cotes et arrêter les nouveaux témoins ne crée pas les résultats manquants : compétition, période et règles doivent être couvertes par les sources. Aucun score n'est inventé ni accord inter-sources assoupli.

## Validation

Tests Python existants et nouveaux tests d'ordonnancement, isolation des pannes et parité des opportunités calculées avec/sans témoin. Tests Node sur les dates à Paris, changements d'heure, reports, fenêtre de deux heures, regroupement et conservation des marchés ; tests existants de notifications, actualisation et analyses. Génération du HTML et contrôle syntaxique du JavaScript intégré.
