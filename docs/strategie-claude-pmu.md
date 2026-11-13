# Claude · PMU régulier

Stratégie de Claude, figée le 13/11/2026, suivie dès le **13/11/2026 à 02:00 UTC** (`cotes/strategie_claude_pmu.py`).

## Règle

PMU · référence Pinnacle ou Polymarket · cote 1,50–3,00 · écart 2–7 % · ni score exact ni mi-temps/fin · équipes non
inversées · match pas commencé · une mise fictive de 10 € par cote française (première détection qui passe la règle).

## Pourquoi

Paris uniques réglés du 10/10 au 12/11/2026, CLV par match, période coupée en trois tiers, hors écarts ≥ 7 %, scores
exacts et cotes > 10 :

| Sous-ensemble | Matchs | CLV | CLV par tiers | ROI |
|---|---|---|---|---|
| PMU, tout | 756 | +0,7 % | +1,1 / +0,9 / +0,9 | +1,0 % |
| PMU, cotes 2,01–3,00 | 281 | +1,4 % | +1,6 / +1,8 / +1,6 | +5,5 % |

Les écarts ≥ 7 %, scores exacts et cotes > 10 ont une CLV de +6 à +16 % mais un ROI de −17 à −100 % : surtout des
erreurs de cote ou d'association. Ils sont exclus.

## Limites

Règle choisie après avoir regardé 102 sous-ensembles : le meilleur résultat peut être dû au hasard, et ne passe pas
une correction stricte des tests multiples. L'avantage mesuré est mince (+0,7 %). Seul le suivi depuis le lancement
compte ; pas de rejeu.
