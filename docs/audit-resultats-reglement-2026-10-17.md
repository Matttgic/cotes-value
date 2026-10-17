# Revue contradictoire — Résultats et règlement, 17 octobre 2026

## Verdict et décisions

L’audit signale de vrais défauts de cache et de traçabilité. En revanche, plusieurs résultats de ses tests proposés sont incorrects. Ils ne doivent pas servir à modifier le moteur.

| Point de l’audit | Décision |
| --- | --- |
| Statut inconnu dans `gain()` | `ValueError` explicite, avec le statut en cause. Aucun gain de 0 € inventé. |
| Handicap européen à trois issues | Calcul conservé. Tests de non-régression corrigés ; aucune division n’intervient dans ce calcul. |
| Basket : seuil global `max >= 20` | Refusé pour une source seule. Exception limitée aux faibles scores corroborés par deux validateurs distincts, avec quatre périodes au minimum et une somme cohérente. |
| Résultats sans date | Toujours exclus ; diagnostic générique dédupliqué, borné à 100 entrées par cycle et conservé dans `etat.json`. |
| Statut HTTP API-Sports | Vérifié avant de lire le JSON. Échec HTTP : aucun remplacement du cache. |
| Réponses vides/inexploitables | Conservation du cache précédent, sans rafraîchir artificiellement sa date. |
| Pari sans date | Alerte idempotente et passage à `a_regler`, sans règlement ni P&L inventé. Les champs sans fuseau sont également refusés. |

## Les trois exemples de règlement à corriger

La convention du dépôt est un handicap appliqué au domicile. Pour `HANDICAP_3`, on évalue `domicile + ligne − extérieur`, puis on choisit DOM/NUL/EXT. Il n’y a pas de remboursement dû à une égalité : le nul est une issue à sélectionner.

| Pari | Score | Résultat exact | Calcul |
| --- | --- | --- | --- |
| Européen DOM −1 | 2–1 | Perdu | Score corrigé 1–1 : seule l’issue NUL gagne. |
| Européen DOM −1 | 2–0 | Gagné | Score corrigé 1–0. |
| Asiatique DOM −1 | 2–1 | Remboursé | Marché asiatique à deux issues, différent du précédent. |
| Plus de 2,25 | 2–0 | Demi-perdu | Moitié sur plus de 2 : remboursée ; moitié sur plus de 2,5 : perdue. |
| Asiatique DOM −0,75 | 1–1 | Perdu | Les deux demi-mises à −0,5 et −1 perdent. |
| Asiatique DOM −0,75 | 2–1 | Demi-gagné | −0,5 gagné, −1 remboursé. |
| Asiatique DOM −0,25 | 1–1 | Demi-perdu | 0 remboursé, −0,5 perdu. |

Les calculs d’origine sont conservés. Les nouveaux tests vérifient les résultats corrigés, y compris les trois issues du handicap européen.

## Cache API-Sports

Le nouveau chemin vérifie, dans cet ordre :

1. Réponse HTTP réussie.
2. JSON objet, sans erreur API.
3. Présence d’une liste `response`, composée d’objets.
4. Extraction de matchs terminés avec score numérique non négatif et date exploitable.
5. Écriture du cache uniquement si des matchs exploitables sont présents, ou si le vide est explicitement confirmé (`response=[]`, `results=0`) et ne contredit pas un cache contenant déjà des résultats.

Un HTTP 429/500, JSON illisible, quota dépassé, schéma invalide, résultats finaux sans heure, liste non vide sans match exploitable ou vide contradictoire laisse le cache identique. Son ancien contenu reste disponible aux validateurs habituels ; il ne reçoit pas une date de lecture fictivement récente. Les règles de correspondance et de consensus restent nécessaires pour utiliser ce contenu.

Une réponse HTTP 200 n’est pas une preuve d’absence de matchs. Une liste vide sans compteur explicite ne suffit pas ici à effacer des résultats. Cette décision est plus prudente que le pseudo-code proposé dans l’audit.

## Basket

Un score de 20–18 peut être un score intermédiaire. Le seul seuil `max >= 20` ne permet donc pas de distinguer la fin d’un match d’un score figé. Le seuil précédent reste appliqué à une source unique, même après 24 heures.

Un score sous le seuil précédent peut désormais passer si :

- deux validateurs distincts identifient le même événement et donnent exactement le même score ;
- le score est non négatif, non nul, sans égalité, avec au moins 40 points pour une équipe ;
- au moins une source fournit au minimum quatre périodes, toutes numériquement valides, dont la somme correspond exactement au score final ;
- les règles usuelles de majorité et de désaccord ne le refusent pas.

Exemple de test synthétique : 45–28 avec quatre quarts cohérents et deux validateurs est accepté ; la même donnée isolée, deux lignes du même fournisseur ou deux sources sans détail complet restent refusées. Cette exception ne prétend pas traiter les forfaits ni toutes les compétitions à format particulier.

Les validateurs doivent déjà fournir des résultats déclarés terminés : `plausible()` ne prouve jamais, à elle seule, la fin d’un événement. Les scores négatifs, booléens ou de structure invalide sont également refusés.

## Diagnostics

- `RESULTATS_IGNORES` est un diagnostic générique des données de source exclues. Il n’est pas rangé dans `ERREURS_ESPN` lorsqu’il provient d’un autre validateur.
- Le journal du règlement contient `resultats.ignores`, sa limite et le nombre de paris ouverts ayant une alerte.
- `alertes` dans le pari signale `date_debut_absente_ou_invalide` ou `statut_reglement_inconnu`, une seule fois par code malgré les reprises du cycle.
- Une date invalide laisse le pari non réglé avec `gain=None`, et le place en revue. Le diagnostic affiché en « À régler » explique le problème. Un résultat manuel explicitement valide peut toujours le régler.
- `a_regler` ne désactive pas les tentatives automatiques ultérieures : les paris ouverts et ceux en revue sont tous deux réexaminés. Ce statut ne remplace pas les contrôles de score.

## Validation et limites

Les tests couvrent les pannes HTTP/JSON/quota, le cache périmé conservé, son actualisation par un nouveau résultat valide, le vide confirmé, les heures absentes, la déduplication des alertes et les contre-exemples de règlement ci-dessus. Ils n’appellent aucune API réelle et ne déclenchent pas un règlement massif des données du dépôt.

- 481 tests Python et 36 tests JavaScript passent, soit 517 au total.
- Les scores mal structurés sont exclus avant orientation des équipes ; les paires JSON valides sont normalisées sans modifier la source.
- Comparaison avant/après sur 12 712 paris : sélections et indicateurs financiers historiques identiques.
- Génération du site réussie ; syntaxe du JavaScript embarqué et différences Git vérifiées.

Les paris déjà réglés ne sont pas réécrits. Les tests valident les conventions implémentées ; cette passe ne constitue pas une nouvelle revue exhaustive des conditions contractuelles de chaque bookmaker.
