# M3 — MultiSport Value (version 1)

**Objectif :** comparer prospectivement une règle construite *après avoir vu* les résultats
historiques de `cotes-value`. **Ni garantie de gain, ni ROI futur estimable.**
Aucun pari réel n'est placé : mise fictive constante de 10 €.

## Règles exactes

- Sports : basket, baseball, handball.
- Références de valeur : Pinnacle **sans marge**, Betfair et Polymarket.
- Bookmakers : Winamax, Betclic, Unibet, PMU.
- Marchés : vainqueur, handicap du match, total du match, total de l'équipe extérieure.
  Match complet exclusivement. Pas de BTTS, corners, cartons ou scores exacts.
- Cote française de 1,30 à 3,00 ; edge théorique de 2 à 12 %.
- Détection avant match, dans les 36 heures ; référence horodatée au plus
  15 minutes avant la détection. Cohérence contrôlée entre cote, cote juste et edge.
- Correspondance dotée d'un identifiant de référence et contrôle d'intitulé **conforme**.
  Quart de point et lignes absentes exclus. Opportunités suspectes exclues.
- Première détection admissible par bookmaker/sélection (match + marché + ligne + issue).
  Plusieurs sélections différentes sur un même match peuvent coexister : **risque de corrélation**.
- Aucune CLV ni aucun résultat sportif n'entre dans le filtre. Aucune sélection
  rétrospective du meilleur cours après la première détection.

## Historique constaté — 7 au 13 octobre 2026

Données figées au commit `56bed648894f383f04fb42f677ee9223d29c2abe`
(`donnees`), relevé du 14/10 à 12h09 heure de Paris.
Rejeu du filtre M3 *après inspection des performances historiques* :

| Période du match | Sélections | Réglés | Gagnés | Perdus | Gain simulé | ROI réglés |
|---|---:|---:|---:|---:|---:|---:|
| 7–10 octobre | 31 | 31 | 21 | 10 | +106,60 € | +34,39 % |
| 11–12 octobre | 29 | 27 | 21 | 6 | +130,50 € | +48,33 % |
| 13 octobre | 23 | 11 | 10 | 1 | +73,60 € | +66,91 % |
| **Total** | **83** | **69** | **52** | **17** | **+310,70 €** | **+45,03 %** |

La méthode de Claude, rejouée sur le même relevé dans
`docs/comparaison-strategies.json`, atteint **+214,70 €** sur **159 réglés**,
soit **+13,50 %** de ROI. M3 dépasse ce total historique de **96 €**,
avec seulement 69 paris réglés.

### Contrôle de corrélation

Les 69 paris réglés concernent plusieurs sélections de rencontres identiques.
En ne gardant que la première détection **par identifiant de match du bookmaker**,
le gain tombe à **+173,20 € sur 38 paris réglés**.
En ne gardant que la première détection **par identifiant de match de référence**,
il tombe à **+106,20 € sur 31 paris réglés**.

Ces deux scénarios ne sont pas les règles M3 officielles ; ils révèlent que
le gain de +310,70 € vient en partie de mises multiples sur les mêmes rencontres.
Avec le second scénario, le gain est **inférieur** à celui de Claude.
Les identifiants ne fusionnent pas nécessairement toutes les rencontres similaires
entre références, donc l'indépendance est encore imparfaite.

**Cette comparaison est descriptive, pas une preuve de supériorité.**
La stratégie M3 a été choisie sur toute la période, **y compris le 13 octobre** :
les colonnes 11–12 et 13 octobre ne sont pas des tests indépendants.
Les règlements connus après chaque fin de période restent inclus au relevé ;
14 des 83 sélections restaient en attente. Les résultats peuvent être corrigés.

### Résultats par sport

| Sport | Réglés | Gain simulé |
|---|---:|---:|
| Basket | 46 | +202,70 € |
| Baseball | 12 | +55,60 € |
| Handball | 11 | +52,40 € |

La majorité du profit dépend du basket et d'un petit nombre de rencontres ;
des marchés d'un même événement peuvent corréler les résultats.
Les preuves de conformité ne garantissent pas que toutes les associations
d'équipes et cotations soient correctes.

## Lancement prospectif

Critères **figés** dans `cotes/strategie_m3.py` à compter du
**15 octobre 2026, 00h00 (Europe/Paris)**. Aucune prise antérieure ne doit
alimenter le bilan officiel. Dans le site : **Stratégies → M3 · MultiSport**
et le panneau **voir les paris depuis le lancement**.

Le rapport machine lisible `docs/strategie-m3.json` reprend toutes les
sélections historiques et la ventilation ; aucun pari réel n'est pris.
Pour comparer avec Claude de manière crédible, conserver les règles inchangées
et suivre les nouvelles prises sur un échantillon important, avec une analyse
par match et des règlements vérifiés ; un gain historique élevé ne permet pas
d'annoncer une rentabilité à venir.
