# Revue contradictoire — Stockage et convergence, 17 octobre 2026

## Verdict

Les risques d’archive illisible et d’écrasement silencieux sont confirmés. En revanche, deux propositions ne doivent pas être appliquées littéralement : ignorer une archive dans un bilan officiel, et refuser toute copie identique lors d’une reprise.

La convergence respecte déjà les familles distinctes et le prix exact. La protection contre une cote absente fonctionne bien par court-circuit ; ce n’était pas une `KeyError` confirmée. Le test Jules v1/v2 demandé existait déjà et a été étendu à plusieurs références.

## Décisions sur les six recommandations

| Point | Décision |
| --- | --- |
| Archive corrompue | Erreur contextualisée et journalisée par défaut. Un mode partiel explicite existe pour diagnostiquer les autres fichiers, jamais pour alimenter automatiquement les bilans ou décisions. |
| Identifiant absent / doublon | Identifiant stable obligatoire. Copie identique fusionnée une seule fois ; contenu contradictoire refusé. Pas de choix arbitraire du premier ou du dernier contenu. |
| Relecture du temporaire | Mise en place : compression, relecture intégrale gzip/JSON, vérification du contenu avant remplacement. Tous les mois sont préparés avant le premier remplacement. |
| Cote invalide dans `votes()` | Contrôle conservé, partagé avec la validation des badges et couvert par des tests : clé absente, `None`, booléen, chaîne, valeur ≤ 1, NaN et infini. |
| Familles / représentant | Jules v1/v2 restent une seule famille ; les variantes prudentes ne donnent aucun vote supplémentaire. Départage rendu déterministe pour plusieurs prix simultanés. |
| Prix différent | Prix exact toujours exigé. Le site distingue une prise antérieure à un autre prix d’une sélection jamais validée. Aucun ancien badge n’est transféré au nouveau prix. |

## Pourquoi ne pas simplement ignorer une archive ?

Une archive omise peut retirer des gains comme des pertes. Elle peut aussi retirer des prises qui occupaient un plafond de stratégie. Un simple message dans un journal ne suffit pas à rendre fiables les chiffres calculés ensuite.

`lire_archives(donnees)` conserve donc une lecture stricte. Une archive tronquée, gzip invalide, erreur UTF-8, JSON invalide, schéma incorrect, identifiant absent ou conflit est signalé avec son nom. Les constantes JSON non finies sont refusées.

La lecture partielle n’est disponible que sur demande explicite :

```python
erreurs = []
partiel = lire_archives(donnees, erreurs=erreurs)
# `partiel` est incomplet : destiné à l'investigation, pas à un bilan officiel.
```

Ce mode conserve les archives valides et remplit le diagnostic fourni. Il ne modifie aucun fichier défectueux. Le cycle, l’expéditeur de notifications, les scripts de comparaison et le site ne l’utilisent pas.

Si la génération rencontre une archive invalide, elle échoue avant d’écrire une nouvelle page : la publication précédente demeure disponible. L’erreur remonte dans les journaux d’exécution. Il n’y a pas de bannière annonçant un bilan partiel, puisque ce bilan n’est pas publié.

## Reprise d’archivage et identifiants

L’archivage et la sauvegarde de `paris.json` sont deux opérations distinctes. Une interruption peut survenir après avoir archivé un pari, mais avant de le retirer du fichier actif. Au passage suivant, le même identifiant et le même contenu réapparaissent normalement.

Refuser systématiquement cet identifiant bloquerait la reprise. L’ignorer sans vérifier le contenu pourrait masquer une contradiction. La règle retenue est :

- identifiant absent, vide ou non textuel : refus explicite ;
- même identifiant et même contenu JSON : une seule copie logique ;
- même identifiant et contenus différents : erreur explicite, sans écrasement ;
- listes de scores relues depuis JSON et tuples équivalents en mémoire : contenus considérés identiques.

`fusionner_paris()` applique cette règle à la lecture des archives et au rapprochement actifs/archives. Les consommateurs partagent cette fusion : site, notifications, registre des décisions et scripts d’analyse. Cela évite de compter deux fois un pari encore actif après une interruption. Les objets du premier lot sont conservés pour ne pas casser les liens `id()` des nouvelles décisions.

Le test historique d’idempotence était déjà présent dans `test_stockage.py`. Il reste passant. Une fixture de test représentant Pinnacle et Pinnacle brut avec le même ID a été corrigée : ces deux références produisent réellement des IDs distincts via `_id()`.

## Écriture et limites de l’atomicité

L’archivage vérifie les identifiants et les conflits avant toute écriture. Seuls les cinq statuts de règlement reconnus sont archivables ; une date sans fuseau, absente ou invalide laisse le pari dans le fichier actif.

Pour chaque mois à compléter :

1. Le contenu est sérialisé sans NaN ni infini.
2. Un temporaire unique est créé dans le même dossier que sa destination.
3. Le gzip fermé est relu entièrement, JSON compris, puis son contenu est vérifié.
4. Après préparation de tous les mois, chaque fichier est remplacé avec `os.replace()`.
5. Les temporaires sont nettoyés, y compris sur erreur.

L’atomicité porte sur chaque fichier, pas sur une transaction regroupant toutes les archives et `paris.json`. Une panne entre deux remplacements peut donc laisser un mois publié et l’autre non. Ce cas est testé : le fichier actif n’est pas modifié par la fonction en échec ; la fusion élimine les copies identiques et la reprise termine sans perte ni double comptage.

Le verrou GitHub Actions du groupe `donnees` demeure nécessaire pour sérialiser les écrivains. Les temporaires uniques ne remplacent pas ce verrou et ne garantissent pas, seuls, la sûreté de deux processus concurrents indépendants. La relecture vérifie la lisibilité, pas une garantie de durabilité matérielle après panne électrique.

## Convergence : règles conservées et cas supplémentaire

Les conditions restent : même contrat français, même prix, même instant UTC, au moins deux familles différentes. Les versions Jules partagent toujours leur famille. M3 conserve son vote dans Convergence ≥ 2 ; les variantes ne l’altèrent pas.

Le représentant était déterministe à l’intérieur d’un groupe de prix. Mais si deux groupes convergents partageaient le même contrat et le même instant avec des prix différents, l’ordre du fichier pouvait décider lequel était retenu.

Ce cas est maintenant départagé par instant, priorité de référence, identifiant, puis prix en dernier recours. Aucun résultat, gain ou CLV n’intervient. Les 24 permutations d’un exemple synthétique donnent désormais le même représentant. Le relevé de contrôle ne contient aucun groupe convergent ambigu de ce type ; ses sélections restent identiques. Une période de rejeu invalide retourne une sélection vide.

## « Prix modifié » dans À jouer

Le pseudo-code `prix_change = item is None` aurait affiché un prix modifié même pour un signal jamais sélectionné. Il n’est pas utilisé.

Le nouveau message exige :

- une prise antérieure effectivement retenue par une stratégie ;
- le même bookmaker, match, marché, période, ligne, issue et joueur ;
- une cote actuelle valide, différente de tous les prix enregistrés pour cette sélection ;
- une date de prise antérieure au relevé affiché.

Le prix précédent et sa date sont disponibles, ainsi que les anciennes étiquettes. « Prix modifié » est visible sans déplier la ligne. Les détails expliquent l’ancienne prise et, le cas échéant, l’ancienne convergence. La cote peut avoir monté ou baissé : le texte n’affirme pas qu’elle est moins bonne ou que le pari a perdu tout intérêt.

Les stratégies et convergences du prix actuel restent vides si aucun enregistrement ne correspond exactement. Un retour au prix enregistré peut retrouver ses badges, selon le comportement antérieur. Aucun nouveau pari, vote ni notification n’est créé à partir des anciennes étiquettes.

## Validation

- **584 tests Python et 36 tests JavaScript passent**, soit **620 tests**.
- Pannes simulées : gzip tronqué, JSON/UTF-8/schéma invalides, conflits d’identifiants, non-finis, corruption d’un temporaire, échec de sérialisation d’un deuxième mois et interruption entre deux remplacements.
- Reprises et fusion actifs/archives vérifiées, y compris dans la génération réelle du site ; une archive invalide ne remplace pas la page précédente.
- Familles Jules, exclusion des variantes du vote, prix différents, retour au prix enregistré et représentant indépendant de l’ordre vérifiés.
- JavaScript exécuté pour vérifier que « Prix modifié » est visible dans le résumé et qu’aucun badge n’est transféré.
- Sélections et indicateurs financiers historiques inchangés sur **12 712 paris** du relevé de contrôle disponible, terminé le **17 octobre à 01 h 58 min 42 s, heure de Paris**. Ce n’est pas une mesure en direct du dernier cycle de production.
- Génération du site et syntaxe du JavaScript embarqué vérifiées ; aucun fichier de données de production n’a été réécrit par cette passe.

L’audit de la persistance n’est pas un audit exhaustif de toutes les stratégies ni de leurs sources externes. La prochaine étape peut examiner les connecteurs HTTP, quotas et schémas sans confondre un échec de fournisseur avec un résultat sportif absent.
