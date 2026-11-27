# Audit stratégie du 26/11/2026 : que jouer, quoi arrêter, combien miser

Mesuré sur la branche `donnees`, commit `2737020` du 26/11/2026 à 23 h 05 UTC : 7 279 paris détectés du 05/10 au
26/11, dont 7 226 réglés. Tous les chiffres sortent de `python etudes/audit_26_11.py --donnees <dossier>` (lecture
seule, 3 minutes, 10 000 tirages, graine 20261126 : deux exécutions donnent les mêmes chiffres). Suite de
[avantage-reel.md](avantage-reel.md) (13/11), [strategie-mises.md](strategie-mises.md) (14/11) et
[regle-principale.md](regle-principale.md) (20/11).

**Méthode en bref.** ROI à 10 € fixes ; CLV contre la clôture Pinnacle sans marge (mesure du protocole). Univers :
la règle de prise actuelle (cote ≤ 5, écart ≥ 3 %, hors Winamax et OlyBet, ≤ 24 h avant le match), une mise par cote
française ; ce que la règle exclut est mesuré en relâchant sa seule contrainte. Stratégies : sélection officielle du
registre dans la règle, depuis leur lancement (les bilans du site). Le match est l'unité de hasard : intervalles à
95 % par bootstrap-t groupé par match ; p-valeurs CLV par Student par match. « Réglés (matchs) » = paris et matchs.
**Hors échantillon** = paris détectés depuis le gel de la règle (15/11/2026) : la règle a été choisie avant, toutes
les stratégies testées aussi.

## Verdict

**Aucun gain n'est prouvé. Un avantage est probable, mesuré par la CLV, sur la seule règle principale.** Jouer cette
règle et rien d'autre, à petite mise (0,2 % de la bankroll par pari, 0,5 % au plus par match), et juger toute idée
nouvelle sur la CLV, jamais sur le ROI.

## Cinq conclusions

1. **La règle principale bat la clôture hors échantillon.** Depuis le gel : CLV +2,92 % [+1,07 ; +4,76], p = 0,001
   (Student unilatéral par match), 362 réglés (232 matchs), CLV mesurée pour 302 (83 %). C'est le test fixé
   d'avance dans `cotes/regle_principale.py` : il passe. ROI +13,4 % [−3,3 ; +30,2] : rien de prouvé en argent. Sur
   toute la période : CLV +3,43 % [+2,60 ; +4,36], ROI +3,8 % [−2,9 ; +10,9], 1 968 réglés (1 127 matchs).
2. **Aucun ROI ne résiste aux tests multiples.** 129 lignes testées (57 segments, 6 exclusions, 66 stratégies) :
   3 ROI à p brute < 5 % alors que le hasard seul en donne 6,5 ; 0 après Benjamini-Hochberg, 0 après Holm. Les ROI
   de stratégies ne disent rien : leur dispersion (écart type 8,7 % sur 39 stratégies) est plus petite que l'erreur
   type d'un seul ROI (médiane 9,5 %).
3. **La CLV prédit le ROI pari par pari, pas entre stratégies.** Dans la règle, un point de CLV vaut 1,56 point de
   rendement [0,67 ; 2,45] (1 278 paris, 802 matchs) ; ROI par cinquième de CLV : −21,4 %, +3,4 %, +8,9 %, +12,5 %,
   +24,5 %. Sur les seuls paris d'après l'étude du 13/11, la pente (0,80 [−0,71 ; 2,65], 339 paris) ne tranche pas
   encore. Entre stratégies, corrélation CLV–ROI −0,50 (rangs −0,18) : le bruit du ROI couvre tout.
4. **Robuste = la règle vue par morceaux.** Découverte avant le gel puis confirmation après (BH, ROI pas sous la
   CLV) : 13 lignes sur 68 découvertes (50 testables après). Toutes sont des parts de la règle (Pinnacle, PMU,
   football, totaux, 1N2, écart 3–4 %, ≤ 1 h…). Deux seulement font mieux que la moyenne de la règle, intervalles
   disjoints : écart ≥ 7 % (CLV +8,00 % [+6,10 ; +10,25], 423 réglés) et cote repérée par 2 références ou plus
   (+6,08 % [+4,40 ; +8,16], 396 réglés). Aucune ligne n'est négative de façon robuste ; seule OlyBet est négative
   après correction (CLV −5,14 % [−8,66 ; −0,87]).
5. **Le ROI ne tranchera pas avant 16 mois.** Prouver +3 % de ROI à la cote moyenne de 2,29 demande 16 562 paris
   (unilatéral 5 %, puissance 80 %, effet de match 1,87 compris) : 493 jours à 33,6 paris par jour. Une CLV de +2 %
   se prouve avec 393 paris mesurés, 18 jours.

## Ce que ces chiffres contredisent

| Affirmation | Source | Aujourd'hui (chiffres de ce script) |
|---|---|---|
| Un gros écart (≥ 6 %) n'est pas un bon signe | strategies-retirees.md, 19/11 | Dans la règle, écart ≥ 7 % : CLV +8,00 % [+6,10 ; +10,25], ROI +6,4 % [−8,5 ; +23,2], ROI − CLV −2,7 % [−22,3 ; +18,9] ; après le gel CLV +10,23 % [+3,66 ; +16,79] (61 réglés) |
| Prix Pinnacle de plus de 5 min : CLV −1,82 % | regle-principale.md, 20/11 | Âge du cache > 5 min : −1,28 % avant le gel (145), +3,67 % [+0,71 ; +6,62] après (132) : pas stable |
| Retirer sur un ROI négatif à 100 réglés | strategies-retirees.md, 27/11 | Les 18 retirées assez fournies pour un test (30 réglés ou plus) ont toutes une CLV positive ; Claude Défi 4 (retirée le 27/11, ROI −9,5 %) est la seule stratégie confirmée après le gel : CLV +10,06 % [+3,35 ; +16,77], 42 réglés |
| Écart 2–3 % : CLV −0,3 % | strategie-mises.md, 14/11 | Hors Winamax et OlyBet, ≤ 24 h : +0,84 % [+0,24 ; +1,47], 1 327 réglés : positif mais quatre fois sous la règle |

## Tableaux

### Règle principale

| Période | Réglés (matchs) | ROI [IC 95 %] | CLV Pinnacle [IC 95 %] | CLV mesurées | ROI − CLV [IC 95 %] |
|---|---|---|---|---|---|
| Toute la période | 1968 (1127) | +3,8 % [−2,9 ; +10,9] | +3,43 % [+2,60 ; +4,36] | 1278 | +2,2 % [−5,4 ; +10,3] |
| Avant le gel (≤ 14/11) | 1606 (895) | +1,6 % [−5,8 ; +9,1] | +3,59 % [+2,60 ; +4,58] | 976 | +0,1 % [−9,0 ; +9,2] |
| Après le gel (≥ 15/11) | 362 (232) | +13,4 % [−3,3 ; +30,2] | +2,92 % [+1,07 ; +4,76] | 302 | +8,8 % [−7,4 ; +25,0] |

### Segments de la règle (toute la période)

| Segment | Réglés (matchs) | ROI [IC 95 %] | CLV Pinnacle [IC 95 %] | CLV mesurées | q BH (CLV) |
|---|---|---|---|---|---|
| Référence Pinnacle | 1369 (834) | +3,4 % [−4,3 ; +11,6] | +3,33 % [+2,48 ; +4,26] | 1131 | < 0,001 |
| Référence Polymarket | 358 (233) | −1,1 % [−16,1 ; +14,6] | +3,43 % [+0,63 ; +6,86] | 86 | 0,043 |
| Référence Matchbook | 96 (78) | +21,3 % [−11,7 ; +56,7] | +5,99 % [+1,42 ; +13,30] | 37 | 0,040 |
| PMU | 971 (650) | +3,0 % [−5,9 ; +13,0] | +3,91 % [+2,89 ; +5,16] | 680 | < 0,001 |
| Betclic | 708 (395) | +2,0 % [−8,8 ; +12,9] | +2,72 % [+1,34 ; +4,23] | 450 | < 0,001 |
| Unibet | 222 (160) | +12,3 % [−4,1 ; +29,5] | +3,26 % [+0,63 ; +6,49] | 102 | 0,037 |
| NetBet | 67 (61) | +6,4 % [−23,1 ; +40,5] | +3,65 % [−0,87 ; +8,01] | 46 | 0,134 |
| Football | 807 (449) | +0,8 % [−10,6 ; +13,4] | +3,96 % [+2,37 ; +5,82] | 456 | < 0,001 |
| Basket | 505 (210) | +7,1 % [−7,2 ; +21,9] | +3,22 % [+1,47 ; +5,70] | 331 | 0,003 |
| Hockey | 242 (159) | +10,2 % [−8,0 ; +29,3] | +3,58 % [+1,60 ; +5,67] | 209 | 0,002 |
| Volley | 103 (90) | −4,7 % [−23,0 ; +15,7] | +0,25 % [−2,30 ; +2,43] | 90 | 0,834 |
| Total | 474 (297) | −0,7 % [−13,7 ; +12,8] | +3,39 % [+2,09 ; +4,86] | 285 | < 0,001 |
| Handicap | 454 (263) | +5,5 % [−8,7 ; +20,2] | +4,34 % [+2,66 ; +6,44] | 298 | < 0,001 |
| 1N2 | 338 (266) | +5,5 % [−12,1 ; +24,6] | +2,81 % [+1,01 ; +4,70] | 223 | 0,007 |
| Vainqueur | 273 (242) | +6,5 % [−6,2 ; +20,7] | +1,45 % [−0,09 ; +3,07] | 185 | 0,091 |
| Écart B (3 à 4 %) | 752 (595) | −0,6 % [−9,0 ; +7,8] | +1,89 % [+0,93 ; +2,89] | 507 | < 0,001 |
| Écart C (4 à 5 %) | 412 (336) | +14,3 % [+2,5 ; +26,3] | +3,05 % [+1,78 ; +4,25] | 270 | < 0,001 |
| Écart D (5 à 7 %) | 381 (295) | −1,7 % [−13,5 ; +11,1] | +2,42 % [+0,96 ; +3,86] | 252 | 0,003 |
| Écart E (7 % et plus) | 423 (253) | +6,4 % [−8,5 ; +23,2] | +8,00 % [+6,10 ; +10,25] | 249 | < 0,001 |
| Cote 1,01 – 1,50 | 211 (179) | +5,2 % [−3,6 ; +12,9] | +2,27 % [+1,48 ; +3,02] | 154 | < 0,001 |
| Cote 1,51 – 2,00 | 729 (525) | +2,9 % [−4,4 ; +10,3] | +1,79 % [+0,89 ; +2,65] | 496 | < 0,001 |
| Cote 2,01 – 3,00 | 714 (489) | +2,8 % [−8,3 ; +14,2] | +5,08 % [+3,56 ; +6,86] | 464 | < 0,001 |
| Cote 3,01 – 5,00 | 314 (250) | +7,2 % [−13,9 ; +30,5] | +4,83 % [+2,45 ; +7,88] | 164 | 0,001 |
| ≤ 1 h avant le match | 400 (265) | +1,3 % [−12,1 ; +16,3] | +4,55 % [+3,40 ; +5,58] | 300 | < 0,001 |
| 1–3 h | 311 (191) | −0,3 % [−20,2 ; +22,5] | +3,15 % [+0,97 ; +5,13] | 201 | 0,005 |
| 3–6 h | 240 (172) | +4,8 % [−13,1 ; +23,1] | +1,79 % [+0,04 ; +3,76] | 157 | 0,078 |
| 6–12 h | 536 (310) | +7,4 % [−6,0 ; +22,6] | +4,51 % [+2,37 ; +7,26] | 324 | < 0,001 |
| 12–24 h | 481 (328) | +4,1 % [−7,6 ; +16,5] | +2,18 % [+0,46 ; +4,05] | 296 | 0,027 |
| Prix Pinnacle ≤ 1 min | 120 (80) | +5,4 % [−23,1 ; +39,2] | +3,87 % [+0,73 ; +6,54] | 105 | 0,014 |
| Prix Pinnacle 1–2 min | 80 (62) | −8,6 % [−40,8 ; +28,8] | +2,62 % [+0,65 ; +5,98] | 75 | 0,054 |
| Prix Pinnacle 2–5 min | 265 (177) | +6,9 % [−10,2 ; +24,6] | +3,61 % [+1,82 ; +5,89] | 214 | 0,001 |
| Prix Pinnacle > 5 min | 277 (185) | +0,9 % [−17,2 ; +21,3] | +1,63 % [−0,57 ; +4,15] | 209 | 0,191 |
| Âge du prix inconnu | 1226 (722) | +4,4 % [−3,7 ; +12,8] | +3,96 % [+2,84 ; +5,31] | 675 | < 0,001 |
| Détecté 0 h – 8 h (Paris) | 463 (292) | +6,9 % [−7,7 ; +24,0] | +3,37 % [+1,57 ; +5,45] | 316 | 0,001 |
| 8 h – 12 h | 341 (224) | +11,6 % [−3,5 ; +28,6] | +3,50 % [+1,37 ; +6,75] | 237 | 0,009 |
| 12 h – 16 h | 365 (257) | −4,3 % [−17,8 ; +10,7] | +2,97 % [+1,53 ; +4,51] | 225 | < 0,001 |
| 16 h – 20 h | 509 (311) | +4,1 % [−9,6 ; +19,4] | +4,00 % [+2,39 ; +5,70] | 330 | < 0,001 |
| 20 h – 24 h | 290 (182) | −0,7 % [−17,9 ; +17,2] | +2,96 % [+0,69 ; +5,43] | 170 | 0,024 |
| Octobre | 1070 (626) | +7,0 % [−1,6 ; +15,9] | +4,12 % [+2,97 ; +5,50] | 645 | < 0,001 |
| Novembre | 898 (502) | −0,0 % [−10,9 ; +11,7] | +2,73 % [+1,50 ; +4,11] | 633 | < 0,001 |
| 1 référence | 1572 (966) | +0,2 % [−6,5 ; +7,3] | +2,66 % [+1,78 ; +3,64] | 990 | < 0,001 |
| 2 références ou plus | 396 (250) | +18,2 % [+1,2 ; +36,9] | +6,08 % [+4,40 ; +8,16] | 288 | < 0,001 |

Betfair, Kalshi et Smarkets (moins de 30 CLV mesurées), les petits sports et marchés : tableau complet avec
`--markdown`. Aucun segment n'a un ROI qui tient après correction.

### Ce que la règle exclut

| Exclu (contrainte relâchée seule) | Réglés (matchs) | ROI [IC 95 %] | CLV Pinnacle [IC 95 %] | CLV mesurées | q BH (CLV) |
|---|---|---|---|---|---|
| Winamax | 297 (212) | +12,1 % [−3,5 ; +29,6] | +0,27 % [−1,96 ; +2,89] | 158 | 0,834 |
| OlyBet | 144 (86) | −10,7 % [−31,8 ; +13,0] | −5,14 % [−8,66 ; −0,87] | 83 | 0,013 |
| Écart 2–3 % (A) | 1327 (962) | +1,5 % [−5,0 ; +8,0] | +0,84 % [+0,24 ; +1,47] | 815 | 0,015 |
| Cote 5–10 | 109 (91) | −31,6 % [−70,9 ; +46,0] | +5,32 % [−0,67 ; +12,96] | 44 | 0,143 |
| Cote > 10 | 588 (357) | −63,5 % [−88,1 ; +15,5] | +7,91 % [+6,18 ; +9,83] | 297 | < 0,001 |
| Plus de 24 h avant le match | 532 (338) | +8,8 % [−2,6 ; +20,9] | +1,12 % [−0,52 ; +2,77] | 337 | 0,223 |

Les cinq exclusions restent justifiées par la CLV. Au-dessus de 10, une CLV de +7,91 % va avec un ROI de −63,5 % :
la CLV n'y mesure pas l'avantage (même constat qu'en [etude-longues-cotes.md](etude-longues-cotes.md)).

### Stratégies (66 testées sur 79 avec des paris réglés, dont 22 retirées)

Extrait : CLV la plus haute, puis les stratégies actives à CLV quasi nulle. Tous les ROI : q BH = 1,00.

| Stratégie | Réglés (matchs) | ROI [IC 95 %] | CLV | q BH (CLV) | Après le gel : réglés, CLV | Robustesse |
|---|---|---|---|---|---|---|
| Défi 4 · Pinnacle très gros écart | 90 (60) | +12,3 % [−20,7 ; +50,8] | +11,0 % | < 0,001 | 27, +12,2 % | en attente (< 30 CLV) |
| Claude Défi 4 (retirée 27/11) | 103 (60) | −9,5 % [−42,3 ; +38,5] | +10,4 % | < 0,001 | 42, +10,1 % | robuste |
| Claude Défi 1 (retirée 19/11) | 159 (77) | −22,2 % [−46,4 ; +16,2] | +7,7 % | 0,001 | 39, +8,2 % | non confirmée |
| Défi 1 (retirée 27/11) | 207 (109) | −3,9 % [−26,2 ; +24,0] | +7,1 % | < 0,001 | 53, +6,4 % | non confirmée |
| Claude Défi 3 · Books lents 2–12 h | 141 (78) | +5,5 % [−22,5 ; +45,9] | +6,2 % | 0,008 | 51, +6,1 % | non confirmée |
| Grok 9 · Valeur Pinnacle | 199 (124) | +17,2 % [−4,4 ; +39,4] | +3,3 % | 0,006 | 57, +3,2 % | non confirmée |
| Claude (retirée 27/11) | 685 (430) | −1,5 % [−10,9 ; +7,9] | +2,9 % | < 0,001 | 154, +1,3 % | non confirmée |
| Convergence ≥ 2 | 375 (277) | +1,1 % [−10,9 ; +12,8] | +1,7 % | 0,032 | 83, −0,3 % | non confirmée |
| ChatGPT v1 | 90 (90) | −8,7 % [−29,4 ; +13,3] | +0,7 % | 0,519 | 17, −1,3 % | — |
| Néon 1 · Socle sharp | 34 (34) | +7,7 % [−29,3 ; +45,1] | +0,6 % | 0,772 | 34, +0,6 % | — |
| Claude Opus · Favoris réguliers | 170 (111) | +7,6 % [−12,8 ; +26,8] | +0,5 % | 0,634 | 72, −0,6 % | — |
| Grok 2 · Pinnacle low | 95 (95) | −3,9 % [−22,1 ; +13,8] | +0,2 % | 0,813 | 33, +0,6 % | — |
| Claude · Drop Pinnacle | 45 (37) | +11,7 % [−23,6 ; +49,0] | −0,5 % | 0,813 | 45, −0,5 % | — |
| Claude · Drop z-score | 35 (29) | +11,0 % [−28,0 ; +56,9] | −1,0 % | 0,673 | 35, −1,0 % | — |
| Cœur value | 63 (63) | −4,6 % [−28,3 ; +18,4] | −1,3 % | 0,341 | 22, +1,0 % | — |

## Tests multiples et faux positifs

| Mesure | Lignes testées | p brute < 5 % | Attendues par hasard | BH positif | BH négatif | Holm positif | Holm négatif |
|---|---|---|---|---|---|---|---|
| ROI | 129 | 3 | 6,5 | 0 | 0 | 0 | 0 |
| CLV Pinnacle | 115 | 83 | 5,8 | 78 | 1 | 41 | 0 |

Avant cet audit, ces données avaient déjà servi à 105 lignes (13/11), 56 segments (15/11) et 97 stratégies (20/11).
Les 78 CLV positives après BH ne sont pas 78 découvertes : la règle entière a une CLV de +3,43 % et chaque morceau en
hérite. La grille « robuste » (découverte avant le gel, confirmation après, BH à chaque étape, ROI pas nettement sous
la CLV) en garde 13 : Pinnacle, PMU, football, total, 1N2, écart 3–4 %, écart ≥ 7 %, cote 3–5, ≤ 1 h, 16 h – 20 h,
novembre, 2 références ou plus, Claude Défi 4.

## Puissance et variance

| Erreur type du ROI (cote moyenne 2,29, effet de match compris) | 100 paris | 300 | 1 000 | 3 000 | 10 000 |
|---|---|---|---|---|---|
| | 15,5 % | 9,0 % | 4,9 % | 2,8 % | 1,6 % |

| Objectif | Paris nécessaires | Jours à 33,6 paris par jour |
|---|---|---|
| ROI +3 %, unilatéral 5 %, puissance 80 % | 16 562 | 493 |
| ROI +3 %, bilatéral 5 % | 21 026 | 626 |
| ROI +3 %, seuil du protocole (200 places) | 50 049 | 1 491 |
| CLV +2 %, unilatéral 5 % | 393 mesurés | 18 |
| CLV +1 %, unilatéral 5 % | 1 570 mesurés | 72 |
| CLV +2 %, seuil du protocole | 1 186 mesurés | 54 |

Rythme : 33,6 paris de la règle par jour du 20/11 au 26/11 (33,3 depuis le gel, 12 jours). Les jours de CLV
comptent la part de paris mesurés sur toute la période (65 % ; 83 % depuis le gel, donc un peu plus rapide).
Écart type d'une CLV : 10,6 %.

## Recommandations

**(a) Quoi jouer.** La règle principale seule : cote ≤ 5, écart ≥ 3 %, hors Winamax et OlyBet, au plus 24 h avant
le match, une mise par cote française. C'est la seule ligne testée d'avance qui passe hors échantillon. Rien
d'autre n'est prouvé, ni en ROI ni en CLV au-delà de la règle.

**(b) Quoi arrêter** (décision de l'utilisateur, rien n'est retiré ici).
- Choisir ou retirer une stratégie sur son ROI : 0 ROI sur 129 tient après correction ; le retrait du 27/11 a sorti
  la seule stratégie confirmée hors échantillon (Claude Défi 4). Juger sur la CLV (protocole).
- Les stratégies actives qui sélectionnent sous la règle (CLV ≤ +0,7 % pour +3,43 % à la règle) : ChatGPT v1,
  Néon 1, Claude Opus · Favoris réguliers, Grok 2, Claude · Drop Pinnacle, Claude · Drop z-score, Cœur value. Elles
  n'ajoutent rien à la règle ; les retirer allégerait la correction des autres.
- Garder Winamax, OlyBet, l'écart 2–3 %, les cotes > 5 et les paris à plus de 24 h hors de la règle (tableau
  ci-dessus).

**(c) Mise.** Avantage retenu : la borne basse de la CLV après le gel, +1,07 %. Kelly à la cote moyenne de 2,36 :
0,79 % ; au quart, **0,20 % de la bankroll, soit 2,40 € pour 1 212,89 €** (Kelly au 1/8 sur la CLV ponctuelle
+2,92 % : 0,27 %, 3,26 €). **Plafond par match : 0,5 % de la bankroll (≈ 6 €)**, tous paris confondus : 24 % des
matchs ont plusieurs paris (jusqu'à 12) et les paris d'un même match sont corrélés à 0,45. Le 1/16 de
[strategie-mises.md](strategie-mises.md) (0,13 % ici) reste le choix le plus prudent.

**(d) Tester les idées suivantes.**
1. Une idée = un filtre observé (`cotes/filtres_observes.py`), écrit et commité **avant** les paris qui le jugent :
   règle exacte, date de gel, test unique, date de lecture.
2. Test unique : CLV Pinnacle > 0, Student unilatéral par match, 5 % ; ROI affiché sans verdict.
3. Échantillon : 393 CLV mesurées pour voir +2 %. Un filtre qui garde une part *f* des paris de la règle demande
   18 / *f* jours (2 références ou plus, 20 % des paris de la règle : environ 90 jours).
4. Date du verdict fixée au départ ; pas de lecture intermédiaire qui change la règle.
5. Prochaine idée candidate, non suivie aujourd'hui : écart ≥ 7 % toutes sources (CLV +8,00 %, confirmée après le gel,
   ROI non contredit). Les filtres observés du 26/11 ne la couvrent qu'avec 2 sources ou plus. À décider à la lecture
   du 5/12 : l'ajouter aujourd'hui changerait une liste figée le 26/11 et son test.

## Limites

- Après le gel : 12 jours, 232 matchs, une seule période de la saison. La règle a été choisie sur la CLV du 05/10 au
  25/10 : la période « avant le gel » est flatteuse pour elle.
- CLV mesurée pour 65 % des réglés de la règle (83 % depuis le gel) ; l'âge du prix Pinnacle n'est connu que pour
  38 % (742 sur 1 968).
- Les stratégies partagent leurs paris : Holm reste valable, BH suppose des tests qui varient dans le même sens.
- Corrélations entre stratégies et entre segments : descriptives, lignes non indépendantes.

## Reproduire

```bash
python etudes/audit_26_11.py --donnees donnees --markdown audit.md --json audit.json
```

Demande numpy. Les données changent toutes les heures : se placer sur le commit `2737020` de `donnees`.
