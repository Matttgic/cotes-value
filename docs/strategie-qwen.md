# Qwen (`qwen_persistence`)

Stratégie suivie depuis le 20/10/2026, en parallèle des autres : elle ne compte pas dans Convergence et ne change
aucune stratégie existante (même statut que M3 Max 3 : variante prospective, sans rejeu historique).

## Règles

| Règle | Valeur |
|---|---|
| Référence (cote juste) | Pinnacle seul, marge retirée |
| Marchés | résultat 1N2, vainqueur, handicap (quarts de ligne compris), total ; match entier ou temps réglementaire ; tennis et volley : vainqueur seulement |
| Cote française | 1,45 à 3,20 |
| Edge | `ecart` ≥ 3,5 % (cote française × probabilité juste − 1, **marge de Pinnacle retirée**) |
| Délai avant le match | 15 min à 2 h, mesuré à la validation |
| Bookmakers | Winamax et Betclic |
| Persistance | 2 cycles consécutifs avec cote et edge conformes |
| Plafond | 3 paris validés par jour (jour de Paris), dans l'ordre d'edge décroissant au sein d'un cycle |
| Mise | 10 € fictifs |

Pourquoi `ecart` et pas `cote / cote_pinnacle − 1` : la cote brute de Pinnacle contient sa marge (6,9 % en médiane
sur nos paris). L'écart brut médian est de 12,2 % quand l'écart réel est de 4,1 % : un seuil de 3,5 % en brut
reviendrait à parier à valeur négative.

## Persistance

`donnees/persistance_qwen.json` garde, pour chaque prise (bookmaker, match, marché, période, ligne, issue) vue au
dernier cycle, le nombre de cycles consécutifs. Une prise absente d'un cycle repart de 1 ; un trou de plus de
12 minutes entre deux cycles remet tout à zéro. Les opportunités portent un `cycle_id` (heure de début du cycle).

## Prix et décision

Le pari simulé est celui de la **première détection** (prix enregistré par `placer`). À la validation :

- cote actuelle **inférieure** à la cote du pari : refus (« pas de dérive négative ») ;
- cote actuelle supérieure ou égale : validé, au prix de la première détection.

La décision est ajoutée aux `selections_figees` du pari avec sa date (`decide_le`, `cycles`, `cote_confirmee`). Elle
n'est jamais retirée. Les alertes (Chrome, webhook) partent à la validation, avec le prix du 2ᵉ cycle.

## Limites

- Aucun rejeu historique : la persistance ne se déduit pas d'une prise isolée.
- Le pari ne coûte pas le prix du 2ᵉ cycle : le ROI est mesuré au prix de la première détection, qui n'est atteignable
  que si la ligne n'a pas baissé (d'où la règle ci-dessus).
- Avec le cache de 15 minutes de Pinnacle, un cycle sur trois environ n'a pas de référence fraîche : la persistance
  peut être interrompue (remise à 1).
