# Analyse de tous les paris : quoi couper, quoi garder, quoi ajouter

Relevé : branche `donnees`, commit `a6dca2f` (19/11/2026, 14:17 UTC). Paris uniques réglés (première détection de
chaque cote française, comme le Bilan, chargés par `etudes/strategie_mises.charger`), mise fixe de 10 €.
**5 559 paris** du 05/10 au 19/11, dont 4 589 à cote ≤ 5. Suite de [strategie-mises.md](strategie-mises.md)
(14/11).

Trois périodes de détection : **A** avant le 26/10 (2 837 paris), **B** du 26/10 au 7/11 (1 649), **C** depuis le
8/11 (1 073). Mesure principale : la **CLV contre la clôture Pinnacle** ; le ROI est donné à côté. Intervalles à
95 % par bootstrap sur les matchs.

## Pourquoi juger sur la CLV

Sur les 2 801 paris à cote ≤ 5 dont la clôture est mesurée, la CLV prédit bien le gain :

| CLV observée | Paris | ROI |
|---|---|---|
| < −5 % | 618 | −13,7 % |
| −5 à −2 % | 254 | −5,2 % |
| −2 à 0 % | 203 | −2,1 % |
| 0 à 2 % | 282 | −8,8 % |
| 2 à 5 % | 626 | +6,5 % |
| > 5 % | 818 | +13,5 % |

Le ROI de chaque segment, lui, est du bruit : il faudrait des dizaines de milliers de paris pour le juger.

## 1. Bilan global

| Ensemble | Paris | Gain | ROI | CLV [IC 95 %] |
|---|---|---|---|---|
| Tous les paris | 5 559 | −3 044 € | −5,5 % | +2,0 % [+1,3 ; +2,6] |
| Cote > 5 (coupées le 11/11) | 970 | −4 235 € | −43,7 % | trompeuse |
| **Cote ≤ 5 (règle actuelle)** | 4 589 | **+1 191 €** | +2,6 % [−1,8 ; +7,1] | +1,3 % [+0,7 ; +1,9] |

Le plafond à 5 a supprimé toute la perte. Mais **64 % des paris à cote ≤ 5 n'ont aucune CLV** (ceux qu'écarte la stratégie figée, partie 2).

## 2. La stratégie figée du 14/11 est validée sur des paris neufs

Règles : cote ≤ 5, écart ≥ 3 %, hors Winamax et OlyBet, pari pris au plus 24 h avant le match.

| Ensemble | Paris | Gain | ROI | CLV [IC 95 %] |
|---|---|---|---|---|
| Stratégie figée, tout | 1 647 | +339 € | +2,1 % | **+3,8 % [+2,9 ; +4,9]** |
| Stratégie figée, **depuis le 15/11** (jamais vu) | 126 | +206 € | +16,3 % | **+6,1 % [+1,5 ; +12,8]** |
| Paris qu'elle écarte (cote ≤ 5) | 2 942 | +852 € | +2,9 % | −0,2 % [−0,8 ; +0,5] |

La CLV tient sur les trois périodes (+5,1 %, +1,8 %, +4,0 %). Les paris écartés ne battent jamais la clôture.
Elle n'est **pas appliquée** au site : la simulation principale prend encore tout à cote ≤ 5.

## 3. À couper

| Segment (cote ≤ 5) | Paris | Gain | ROI | CLV | CLV A / B / C | Verdict |
|---|---|---|---|---|---|---|
| Écart 2 à 3 % (simulation A) | 1 872 | +246 € | +1,3 % | −0,2 % | −0,3 / −0,4 / +0,3 | rien à gagner |
| OlyBet | 284 | −392 € | −13,8 % | −3,5 % | −1,4 / −6,5 / −2,5 | **perd** |
| Winamax | 543 | +388 € | +7,1 % | −1,1 % | −0,2 / −2,6 / −1,5 | ROI chanceux, CLV < 0 |
| Volley | 189 | −299 € | −15,8 % [−27 ; −3] | +0,4 % | +1,7 / −1,7 / +0,6 | **perd** sur les 3 périodes |
| Basket · total | 293 | −122 € | −4,2 % | −1,5 % | −0,1 / −2,1 / −2,2 | CLV < 0 |
| Football · handicap | 284 | −262 € | −9,2 % | −0,8 % | +0,1 / −5,6 / +2,2 | ROI < 0 sur les 3 périodes |
| Pari pris > 24 h avant | 1 015 | +695 € | +6,8 % | −0,2 % | −1,2 / −0,6 / +1,5 | CLV nulle |

Dans la stratégie figée, deux segments restent sans CLV : **volley** (72 paris, CLV 0,0 %, ROI −17 %) et
**basket · total** (128 paris, CLV −0,4 %).

## 4. À garder ou renforcer

| Segment (cote ≤ 5) | Paris | ROI | CLV | CLV A / B / C |
|---|---|---|---|---|
| Écart ≥ 10 % | 336 | +11,3 % | **+9,3 %** | +9,9 / +6,0 / +14,4 |
| Écart 7 à 10 % | 383 | −1,2 % | +4,0 % | +4,6 / +1,6 / +6,3 |
| PMU | 2 104 | +2,0 % | +2,5 % | +2,5 / +1,6 / +3,7 |
| Hockey | 679 | +4,8 % | +1,9 % | +3,2 / +0,4 / +2,6 |
| Autres sports (NFL, rugby, baseball…) | 229 | +7,0 % | +2,9 % | +2,2 / +4,0 / +3,8 |
| Double chance | 129 | +7,0 % | +3,2 % | +5,0 / +2,0 / +1,7 |
| Remboursé si nul | 107 | +16,7 % | +3,9 % | +2,0 / +2,8 / +7,9 |
| Les deux marquent | 96 | +23,5 % | +3,2 % | +6,6 / +0,7 / +3,0 |
| Référence Matchbook | 166 | +16,1 % | +7,1 % (48 mesures) | – / +3,3 / +8,8 |
| Référence Polymarket | 864 | +4,9 % | +3,7 % (111 mesures) | +6,3 / +1,2 / +3,1 |

La CLV monte avec l'écart annoncé : +0,8 % de 3 à 5 %, +1,7 % de 5 à 7 %, +4,0 % de 7 à 10 %, +8,6 % au-delà.

## 5. À ajouter

- **Confirmation Polymarket.** Sur les paris Pinnacle (cote ≤ 5, écart ≥ 3 %) où Polymarket voit aussi un écart
  ≥ 5 % : 231 paris, ROI +10,6 %, CLV **+9,3 % [+4,9 ; +13,9]**. Polymarket contre (écart < −2 %) : CLV −3,9 %.
  À tester comme signal, pas encore comme règle (49 clôtures mesurées).
- **Rien à ajouter côté cotes > 5** : 5 à 10, ROI −40 % ; > 10, −45 %. Le plafond reste.
- **Rien côté marchés exotiques** (score exact, mi-temps/fin) : tous au-dessus de 5.
- Liquidité Pinnacle, marge Pinnacle, TRJ du bookmaker, âge de la cote, heure de prise : aucun signal stable.

## 6. Scénarios

| Règle | Paris | Gain | ROI | CLV [IC 95 %] | Depuis le 15/11 : CLV |
|---|---|---|---|---|---|
| Actuelle (cote ≤ 5) | 4 589 | +1 191 € | +2,6 % | +1,3 % [+0,7 ; +1,9] | +2,1 % |
| Figée du 14/11 | 1 647 | +339 € | +2,1 % | +3,8 % [+2,9 ; +4,9] | +6,1 % |
| Figée sans volley | 1 575 | +464 € | +2,9 % | +4,0 % [+3,0 ; +5,1] | +6,2 % |
| Figée, écart ≥ 4 % | 1 063 | +465 € | +4,4 % | +4,8 % [+3,6 ; +6,1] | +7,3 % |
| Figée, écart ≥ 5 % | 715 | +175 € | +2,4 % | +5,6 % [+4,1 ; +7,4] | +10,5 % |

Le gain total en euros est plus haut avec la règle actuelle parce qu'elle mise trois fois plus : ce surplus vient de
paris sans CLV, donc de la chance. Avantage par pari : ×3 avec la figée, ×4 avec écart ≥ 4 %.

## Recommandations

**Appliquées le 19/11** (points 1 à 4), à la prise et à tous les bilans du site : voir [strategie-optimisee.md](strategie-optimisee.md).

1. **Appliquer la stratégie figée** au site (simulation principale ou stratégie suivie à part) : cote ≤ 5, écart
   ≥ 3 %, hors Winamax et OlyBet, ≤ 24 h avant le match.
2. **Couper le volley** et le **total au basket**.
3. **Mises** : plus fortes sur les écarts ≥ 7 % (Kelly 1/16 de [strategie-mises.md](strategie-mises.md)), au
   minimum ne pas miser plus sur 3 % que sur 10 %.
4. **Suivre la confirmation Polymarket** comme filtre candidat ; décider vers le 5/12.
5. **Ne rien rouvrir** : cotes > 5, marchés exotiques, Winamax, OlyBet.

## Limites

Un mois et demi de données. Paris d'un même match corrélés (bootstrap par match). Près de 60 segments regardés :
quelques « signaux » sont des faux positifs ; seuls ceux qui tiennent sur les trois périodes sont retenus. La CLV
n'est mesurée que pour les paris avec une clôture Pinnacle (58 % des paris), surtout de référence Pinnacle.
