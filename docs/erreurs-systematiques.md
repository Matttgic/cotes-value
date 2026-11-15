# Erreurs systématiques des bookmakers français

Fait le 15/11/2026 sur la branche `donnees` (commit `3a123d8`, 19:35 UTC) : 5 256 paris uniques réglés du 05/10 au
15/11, dont 2 967 avec une clôture Pinnacle. Chiffres : `python etudes/erreurs_systematiques.py --donnees <dossier>`
(lecture seule, graine fixe). Toutes les lignes : [erreurs-systematiques-tableaux.md](erreurs-systematiques-tableaux.md).
Suite de [avantage-reel.md](avantage-reel.md).

## Méthode en bref

- **Erreur mesurée = CLV contre la clôture Pinnacle** des paris uniques réglés : de combien la cote française
  dépassait la cote juste où le marché sharp a fini. Une CLV positive est une vraie erreur du bookmaker ; un écart à
  la prise qui disparaît à la clôture était un bruit de la référence. Le ROI est donné, mais il ne tranche pas à ce
  volume (avantage-reel, point 5).
- **Cotes ≤ 5 seulement** pour les familles principales : au-dessus, la CLV ne s'est pas montrée liée au ROI
  (avantage-reel, section 3). Les marchés à grosses cotes (score exact, mi-temps / fin) sont à part, avec cette réserve.
- **Test** : bootstrap studentisé par match, correction de Holm sur les 56 segments testés, dans les deux sens.
  « Prouvé » = p de Holm < 5 %.
- **Stabilité** : même mesure avant et après le 24/10 à 23 h (date médiane des paris mesurés), et part des semaines
  à CLV positive.
- **Cause probable** (paris depuis le 25/10, quand le mouvement Pinnacle est enregistré) : *modèle copié* = même
  cote chez un autre bookmaker français au même cycle ; *mise à jour lente* = probabilité juste Pinnacle de l'issue
  montée d'au moins 0,5 % juste avant la prise, que le bookmaker n'a pas suivie ; *marge mal répartie* = ni l'un ni
  l'autre, alors que le marché du bookmaker garde une marge normale (TRJ ≤ 97 %). Sur l'ensemble : 4 % copie, 61 %
  lent, 31 % marge, 3 % autre (TRJ inconnu, double chance et score exact par exemple). C'est un classement indicatif, pas une preuve de cause.

## Conclusion

1. **Une erreur nette, stable et compatible avec le ROI : PMU sur le 1N2 / vainqueur.** CLV +2,52 %
   [+1,45 ; +3,63], prouvée (p Holm 0,006), identique dans les deux moitiés (+2,50 % puis +2,53 %), positive 6
   semaines sur 6 ; ROI +9,4 % [−0,9 ; +20,3]. Cause dominante : **mise à jour lente** (65 % des paris suivent une
   hausse récente de la probabilité Pinnacle), copie 7 %.
2. **PMU garde du retard sur tout ce qui est « temps réglementaire »** (hockey, basket, football sans prolongation) :
   CLV +3,39 % [+2,16 ; +4,83], prouvée, stable (+3,76 % puis +3,20 %, 6 semaines sur 6), **83 % après un mouvement
   Pinnacle** : le cas le plus net de mise à jour lente. Même tendance chez PMU sur les totaux d'équipe (+1,93 %,
   prouvée, stable) et les totaux (+1,87 %, p Holm 0,09, stable).
3. **La double chance est mal cotée, surtout chez PMU** : +3,48 % tous bookmakers, +3,10 % chez PMU (prouvées),
   positive toutes les semaines, plus faible ensuite (+4,81 % puis +2,47 %). PMU semble dériver la double chance de son
   1N2 sans suivre les mouvements (71 % après un mouvement Pinnacle).
4. **À moins d'une heure du coup d'envoi**, les cotes françaises battent la clôture de +2,49 % [+1,33 ; +3,42]
   (prouvée, 5 semaines sur 6, +3,31 % puis +1,74 %), 72 % après un mouvement Pinnacle : les bookmakers ne suivent pas
   l'information de dernière heure (compositions, argent sharp). À plus de 24 h, aucune erreur (−0,16 %) : les écarts
   repérés tôt ne tiennent pas.
5. **Score exact : la plus grosse erreur mesurée, mais pas encore exploitable.** CLV +8,69 % [+6,62 ; +11,18],
   prouvée, stable (+7,99 % puis +10,38 %, 5 semaines sur 5), surtout Betclic (287 des 419 paris à grosse cote mesurés).
   Raison probable : **marge mal répartie** entre une vingtaine de scores (la cote française y est en médiane 34 % sous
   la cote juste, rapport 0,66, mais quelques scores restent au-dessus du juste). Réserves : cote moyenne 51, ROI −44,9 %
   [−79,1 ; +76,0] sans aucune valeur informative, lien CLV → ROI jamais montré au-dessus de 5, et cote juste Pinnacle
   d'un marché à beaucoup d'issues moins sûre.
6. **Petits championnats : pas d'erreur systématique.** Matchs où Pinnacle accepte au plus 300 € : CLV +0,15 %
   [−0,90 ; +1,28] sur 910 paris. Les plus liquides (> 1 500 €) font +3,72 %, sur 70 paris seulement. L'idée « les
   bookmakers français se trompent sur les petites ligues » ne se vérifie pas ici.
7. **Mi-temps : erreur non confirmée à cote ≤ 5.** 1re mi-temps +0,66 % [−0,25 ; +1,42] ; le +2,6 % vu sans plafond
   venait des scores exacts à la mi-temps. Seul PMU a un intervalle au-dessus de zéro (+1,17 % [+0,09 ; +1,99], 6
   semaines sur 6), sans tenir après correction.
8. **Les handicaps se sont corrigés.** +1,91 % au total, mais +3,53 % avant le 24/10 et +0,05 % après ; même chute chez
   Betclic (+4,48 % puis +1,59 %) et PMU (+3,81 % puis +1,12 %). Même chose pour le basket (+3,80 % puis −0,30 %).
9. **Faux signaux (CLV négative) : ce n'est pas le bookmaker qui se trompe.** Winamax totaux −3,78 % [−6,90 ; −1,16]
   (0 semaine positive sur 4), Winamax 1N2 −1,55 %, OlyBet 1N2 −3,37 % [−6,00 ; −0,30], nuls du 1N2 −1,15 % (−3,63 %
   après le 24/10), Betclic 1N2 −0,42 %. Quand ces cotes paraissent au-dessus du juste, le marché finit par leur donner
   raison : référence en retard ou mal associée, pas une erreur exploitable.
10. **Le « modèle copié » explique peu.** Une même cote chez deux bookmakers français au même cycle n'apparaît que
    pour 4 % des paris ; un peu plus sur le 1N2 de Winamax et d'Unibet (≈ 20 %) et sur les nuls (22 %), là où la CLV
    est nulle ou négative. Paires les plus fréquentes : Winamax = Unibet (12 paris), Winamax = Betclic (11), Unibet =
    Betclic (9). Ces cotes copiées viennent d'une source commune plutôt juste.

## Tableau de synthèse (cote ≤ 5 sauf mention)

| Marché | Paris (CLV) | CLV Pinnacle | IC 95 % | p Holm | 1re moitié → 2de | Semaines > 0 | Cause probable | Verdict |
|---|---|---|---|---|---|---|---|---|
| PMU · 1N2 / vainqueur | 344 | +2,52 % | [+1,45 ; +3,63] | 0,006 | +2,50 → +2,53 | 6/6 | mise à jour lente (65 %) | **erreur prouvée, stable** |
| PMU · temps réglementaire | 239 | +3,39 % | [+2,16 ; +4,83] | 0,006 | +3,76 → +3,20 | 6/6 | mise à jour lente (83 %) | **erreur prouvée, stable** |
| PMU · total d'une équipe | 264 | +1,93 % | [+0,91 ; +3,00] | 0,019 | +1,82 → +2,02 | 5/6 | mise à jour lente (71 %) | **erreur prouvée, stable** |
| Double chance (PMU 73 sur 95) | 95 | +3,48 % | [+1,92 ; +5,53] | 0,006 | +4,81 → +2,47 | 5/5 | mise à jour lente (70 %) | **erreur prouvée**, en baisse |
| Moins d'1 h avant le match | 447 | +2,49 % | [+1,33 ; +3,42] | 0,010 | +3,31 → +1,74 | 5/6 | mise à jour lente (72 %) | **erreur prouvée**, en baisse |
| Autres sports (rugby, football américain, baseball…) | 148 | +2,74 % | [+1,39 ; +4,13] | 0,006 | +2,11 → +3,87 | 5/5 | marge mal répartie (56 %, 9 paris) | **erreur prouvée, stable** |
| Score exact (cotes > 5) | 232 | +8,69 % | [+6,62 ; +11,18] | 0,006 | +7,99 → +10,38 | 5/5 | marge mal répartie (TRJ inconnu) | **erreur prouvée, stable, ROI non mesurable** |
| Mi-temps / fin (cotes > 5) | 91 | +6,98 % | [+3,73 ; +11,04] | 0,006 | +6,98 → — | 1/1 | — | erreur passée, plus mesurée |
| PMU · total | 317 | +1,87 % | [+0,72 ; +3,02] | 0,092 | +2,07 → +1,73 | 6/6 | mise à jour lente (71 %) | probable, stable |
| Hockey | 485 | +2,08 % | [+0,76 ; +3,37] | 0,099 | +3,04 → +1,62 | 5/6 | mise à jour lente (76 %) | probable |
| Handicap (tous) | 579 | +1,91 % | [+0,58 ; +3,39] | 0,155 | +3,53 → +0,05 | 5/6 | lent 53 %, marge 46 % | **corrigée** |
| Basket | 547 | +1,43 % | [−0,06 ; +3,29] | 1 | +3,80 → −0,30 | 4/6 | mise à jour lente (65 %) | corrigée |
| 1re mi-temps | 318 | +0,66 % | [−0,25 ; +1,42] | 1 | +0,67 → +0,65 | 5/6 | mise à jour lente (75 %) | non prouvée |
| Limite Pinnacle ≤ 300 € (petites ligues) | 910 | +0,15 % | [−0,90 ; +1,28] | 1 | — → +0,15 | 3/4 | — | **pas d'erreur** |
| Plus de 24 h avant le match | 573 | −0,16 % | [−1,57 ; +1,38] | 1 | −1,15 → +0,51 | 1/6 | — | pas d'erreur |
| 1N2 : nul | 107 | −1,15 % | [−3,28 ; +0,53] | 1 | +0,72 → −3,63 | 3/5 | copie (22 %) | faux signal |
| Winamax · total | 58 | −3,78 % | [−6,90 ; −1,16] | 0,228 | −3,17 → −4,40 | 0/4 | — | faux signal |
| OlyBet · 1N2 / vainqueur | 67 | −3,37 % | [−6,00 ; −0,30] | 1 | −3,84 → −3,11 | 0/2 | — | faux signal |

## Ce qui n'a pas pu être mesuré

- **Props joueurs** : ils n'entrent pas dans les paris (pour ne pas modifier les stratégies figées) ; les paris
  papier ne commencent que le 10/11 (89, dont 6 réglés). Au dernier cycle, les 1 026 cotes de props de Winamax et
  d'Unibet ont un rapport médian de 0,86 avec la cote juste Pinnacle (≈ 14 % de marge) et moins de 1 % sont au-dessus
  du juste (0,6 % Winamax, 0,4 % Unibet) : rien de systématique sur cet instantané, mais aucune mesure dans le temps.
- **Cotes boostées** : jamais lues (aucun libellé de pari ni marché inconnu ne les mentionne). À ajouter aux lecteurs
  pour les étudier.
- **Mi-temps / fin** : les opportunités se comptaient par milliers jusqu'au 12/10 et ont presque disparu après le
  13/10 (le marché n'est plus comparé) ; la stabilité n'est pas mesurable.
- **Liquidité** : la limite de mise Pinnacle n'est enregistrée que depuis le 25/10.

## Limites

- **Sélection** : seuls les écarts d'au moins 2 % à la prise deviennent des paris. La CLV dit si ces écarts-là sont
  réels, pas quelle part de toutes les cotes d'un marché est fausse. La vue « population » (`controle.json`, toutes les
  cotes appariées) montre que la cote française est presque toujours sous le juste : 0 à 5 % des rapports dépassent 1
  selon le marché (tableaux complets).
- **Une seule période** de 41 jours, et la coupure en deux moitiés croise des changements de notre code (garde-fou
  « cote Pinnacle figée » le 01/11, plafond de cote le 11/11) : une baisse de CLV peut venir de nous autant que des
  bookmakers. Les erreurs dites stables le sont sur les deux moitiés malgré ces changements.
- **Causes** : indicateurs indirects. 61 % de tous les paris suivent déjà un mouvement Pinnacle ; une cause n'est
  retenue que si elle dépasse nettement cette base (PMU temps réglementaire 83 %) ou si les autres sont absentes.
- **CLV Pinnacle** mesurée sur 56 % des paris uniques réglés ; 56 segments testés, lignes non indépendantes
  (bookmaker × marché recoupe marché).

## Décisions proposées

1. Cibler PMU sur le 1N2, le temps réglementaire, les totaux d'équipe et la double chance, de préférence dans
   l'heure avant le match : les seules erreurs prouvées, stables et compatibles avec le ROI. À inscrire au protocole
   (`python scripts/protocole.py --inscrire`) avant tout suivi, pour ne pas réutiliser ces mêmes données comme preuve.
2. Ne pas prendre les écarts sur les nuls, les totaux Winamax ni le 1N2 OlyBet : leur CLV est négative.
3. Garder le score exact en observation (paris papier) tant que le lien CLV → ROI n'est pas montré au-dessus de 5.
4. Lire les cotes boostées et prolonger les paris papier sur les props avant de conclure sur ces deux marchés.

## Reproduire

```bash
bash scripts/cloner_donnees.sh https://github.com/Matttgic/cotes-value donnees
```

```bash
git -C donnees sparse-checkout add '/opportunites/*'
```

```bash
python etudes/erreurs_systematiques.py --donnees donnees --markdown docs/erreurs-systematiques-tableaux.md
```

Demande numpy (`requirements-dev.txt`). Pour retrouver ces chiffres, se placer sur le commit `3a123d8` de `donnees`.
