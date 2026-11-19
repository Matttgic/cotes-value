# Optimisée 19/11 (et sa variante + Polymarket)

Code : `cotes/strategie_optimisee.py`. Suivie dès le **19/11/2026 à 18 h (Paris)**, sans rejeu, inscrite au
protocole (`docs/protocole.md`). Origine : [analyse-paris-19-11.md](analyse-paris-19-11.md).

## Règle

**Optimisée 19/11** : la stratégie figée du 14/11 ([strategie-mises.md](strategie-mises.md)), moins deux segments
sans CLV.

- Toutes les références, cote ≤ 5, écart annoncé ≥ 3 %.
- Tous les bookmakers sauf Winamax et OlyBet.
- Ni volley, ni total au basket (le total d'une équipe reste).
- Détecté au plus 24 h avant le début, match pas commencé, équipes non inversées.
- Une mise par cote française : la première détection qui passe la règle.

**Optimisée 19/11 + Polymarket** : même règle, référence Pinnacle seulement, et Polymarket voit aussi un écart
≥ 5 % (`ecart_polymarket`). Piste à confirmer : 231 paris et 49 clôtures mesurées au 19/11. À juger vers le 5/12.

## Pourquoi

Sur 4 589 paris réglés à cote ≤ 5 (05/10 au 19/11) :

| Ensemble | Paris | CLV Pinnacle [IC 95 %] |
|---|---|---|
| Règle figée du 14/11, depuis le 15/11 (paris neufs) | 126 | +6,1 % [+1,5 ; +12,8] |
| Paris qu'elle écarte | 2 942 | −0,2 % [−0,8 ; +0,5] |
| Règle figée sans volley | 1 575 | +4,0 % [+3,0 ; +5,1] |
| Confirmation Polymarket ≥ 5 % | 231 | +9,3 % [+4,9 ; +13,9] |

Volley : ROI −15,8 % [−27 ; −3], négatif sur les trois périodes. Total au basket : CLV −1,5 %.

## Mise conseillée dans les notifications

Depuis le 19/11, la mise des notifications (Pushover, ntfy, récapitulatif « Encore jouables ») est un **Kelly au ¼
sur l'avantage « compté »** de l'étude du 14/11 (`mise_conseillee`). Le même jour, un premier essai au 1/16 a été
jugé trop petit en euros et remplacé.

    mise = bankroll × ¼ × avantage compté / (cote − 1), plafonnée à 2 % de la bankroll

| Écart annoncé | < 3 % | 3 % | 4 % | 5 % | 7 % | ≥ 10 % |
|---|---|---|---|---|---|---|
| Avantage compté | 0 | +0,18 % | +1,01 % | +2,19 % | +4,64 % | +8,15 % |

Entre deux points, interpolation linéaire. Exemples pour 1 000 € : cote 2,00 à 4 %, 2,52 € ; à 7 %, 11,60 € ; cote
1,50 à 10 %, 20 € (plafond). La mise affichée est arrondie à l'euro supérieur, 1 € au moins.

Rejeu sur les 1 447 paris gardés au 19/11, bankroll fixe de 1 000 € :

| Mise | Total misé | Gain | ROI |
|---|---|---|---|
| Fixe 10 € | 14 470 € | +519 € | +3,6 % |
| Kelly ¼ sur l'écart brut (ancienne) | 18 271 € | +883 € | +4,8 % |
| **Kelly ¼ sur l'avantage compté** | 9 341 € | +550 € | +5,9 % |
| Kelly 1/16 sur l'avantage compté | 2 517 € | +161 € | +6,4 % |

Le plafond de 2 % coupe les gros écarts : c'est pourquoi le Kelly ¼ compté ne fait pas 4 fois le gain du 1/16.

**Bankroll** : `PUSHOVER_BANKROLL` (variable GitHub, 1 000 € par défaut), réglée à la main. Conseil : la baisser dès
que la bankroll réelle tombe 10 % sous la valeur déclarée, la monter par paliers de +20 % (1 000 → 1 200 → 1 440…).

Ne change pas : les bilans du site gardent leur mode Kelly ¼ sur l'écart brut (`simulation.mise_kelly`), déjà publié.
La mise ne retire pas ce qui est déjà misé sur le même match : à faire à la main si plusieurs paris tombent sur un
match.

## Règle appliquée à tout le site (comme le plafond de cote du 11/11)

Depuis le 19/11/2026, la même règle (`simulation.motif_hors_regle`) s'applique **à la prise et à tous les bilans** :

- `placer` ne prend plus de pari hors règle : cote > 5, écart < 3 %, Winamax, OlyBet, volley, total au basket, plus
  de 24 h avant le match. Une cote vue à plus de 24 h est prise à sa première détection dans les 24 h, si elle est
  encore là.
- Le site retire les anciens paris hors règle de tous les bilans (Bilan, Paris, stratégies), sans les supprimer des
  données : ils sont dans `hors_plafond.json`, avec leur nombre par motif sous le Bilan.

Effet sur les paris uniques réglés au 19/11 : **1 447 gardés, +519 €, ROI +3,6 %** ; 4 112 exclus, −3 563 €,
ROI −8,7 %. Motifs, sur tous les paris enregistrés (écart < 3 % : 2 501 ; cote > 5 : 1 095 ; plus de 24 h : 609 ; Winamax : 428 ; OlyBet : 212 ; total au
basket : 158 ; volley : 75 ; un pari peut avoir plusieurs motifs, seul le premier est compté).

Conséquence : les stratégies qui prenaient ces paris les perdent aussi, dans leurs bilans et à l'avenir (règles à
écart ≥ 2 %, Fusion 1, Liquidité sûre, bookmakers Winamax…), comme les cotes > 5 le 11/11. Le protocole
(`scripts/protocole.py`) garde sa propre mesure, figée le 15/11. La stratégie « Optimisée 19/11 » fait désormais
presque doublon avec le Bilan ; elle reste suivie (inscrite au protocole).

## Limites

Choisie sur l'historique : seul le suivi depuis le 19/11 compte. Les intervalles sont larges (un mois et demi de
données). Rejeu indicatif du 15/11 au 19/11 : 121 paris pour la règle, 11 pour la variante + Polymarket.
