# Durée de vie des values, « CLV maison » et origine de la value

Étude du 11/11/2026 sur l'historique des cotes françaises (`donnees/cotes/`, depuis le 30/10/2026 : PMU, Betclic,
Unibet, NetBet). Script : `python scripts/etude_duree_values.py --donnees donnees`. Paris uniques détectés du 30/10
au 10/11, cote ≤ 5, ni score exact ni mi-temps/fin : 744 paris dont l'historique retrouve la cote prise (449 sans
historique exploitable).

## 1. Combien de temps pour jouer ?

Part des values encore jouables (la cote n'a pas baissé, le match n'a pas commencé) :

| Bookmaker | Paris | Après 5 min | Après 15 min | Après 60 min | Tenue jusqu'au match | Quand elle baisse : délai médian |
|---|---|---|---|---|---|---|
| Ensemble | 744 | 99 % | 80 % | 55 % | 28 % | 43,5 min |
| Betclic | 251 | 97 % | 60 % | 41 % | 24 % | 14,2 min |
| PMU | 440 | 100 % | 93 % | 64 % | 29 % | 64,5 min |
| NetBet | 27 | 100 % | 76 % | 27 % | 33 % | 18,8 min |
| Unibet | 26 | 100 % | 73 % | 59 % | 50 % | 14,0 min |

Betclic corrige quatre fois plus vite que PMU. Une alerte reçue en deux minutes laisse presque toujours le temps de
jouer ; au-delà d'un quart d'heure, quatre values Betclic sur dix ont disparu. Limite : les relevés sont espacés de
une à cinq minutes, une baisse entre deux relevés est datée du relevé suivant.

## 2. Le bookmaker nous donne-t-il raison ? (« CLV maison »)

CLV maison = cote prise / dernière cote du même bookmaker avant le match − 1. Elle ne dépend d'aucune référence.

| Ce que le bookmaker a fait ensuite | Paris réglés | ROI | CLV contre la référence |
|---|---|---|---|
| Il a baissé sa cote | 451 | +4,7 % | +3,5 % |
| Il n'a pas bougé | 179 | +0,1 % | +1,8 % |
| Il a **monté** sa cote | 64 | −27,5 % | −10,3 % |

Six fois sur dix, le bookmaker baisse sa cote après la détection : il corrige lui-même l'erreur (CLV maison moyenne
+7,2 %). Quand il la monte, c'est notre référence qui se trompait : la « value » était fausse, et les deux mesures
indépendantes (ROI, CLV de référence) le disent ensemble.

## 3. D'où vient la value ?

Dans l'heure avant la détection, le bookmaker avait-il bougé ? Cette information est connue au moment de parier.

| Origine | Paris réglés | ROI | CLV contre la référence |
|---|---|---|---|
| Cote du bookmaker stable depuis une heure (la référence a bougé sans lui) | 311 | +6,9 % | +3,2 % |
| Le bookmaker venait de monter sa cote | 136 | +4,5 % | −1,2 % |
| Le bookmaker venait de baisser sa cote | 124 | −19,2 % | +3,8 % |
| Cote apparue dans l'heure | 123 | 0,0 % | 0,0 % |

Une value créée par le bookmaker qui monte sa cote ne bat pas la clôture (−1,2 %) : il sait peut-être quelque chose
(blessure, composition). Une value créée par la référence qui bouge sans lui est la bonne (+3,2 %).

## Limites et suite

- Douze jours, 744 paris, des sous-groupes de 60 à 450 paris : des tendances, pas des preuves. Le ROI de « venait de
  baisser » (−19 %) contredit sa CLV (+3,8 %) : bruit probable.
- Aucune règle n'est appliquée. Deux suites possibles, à décider sur un mois de données : enregistrer l'origine de
  la value dans le pari à la prise (filtre à tester du Bilan), et publier la CLV maison à côté de la CLV de
  référence dans les fiches des stratégies.
