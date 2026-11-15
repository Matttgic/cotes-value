# Stratégie de mises : quoi couper, quoi figer, combien miser

Fait le 14/11/2026 sur la branche `donnees` (commit `4283860`, 17:17 UTC) : 5 040 paris uniques réglés du 05/10 au
14/11. Tous les chiffres sortent de `python scripts/strategie_mises.py --donnees <dossier>` (lecture seule, une
minute, graine fixe : deux exécutions donnent le même fichier). Tous les tableaux :
[strategie-mises-tableaux.md](strategie-mises-tableaux.md). Suite de [avantage-reel.md](avantage-reel.md) et de
[cote-juste.md](cote-juste.md).

## Conclusion

1. **Quatre segments ne rapportent rien ou perdent, sur les deux périodes** : les cotes > 5 (ROI −39 % puis
   −55 %), l'écart annoncé de 2 à 3 % (41 % des paris à cote ≤ 5, CLV Pinnacle −0,3 % deux fois), Winamax (CLV
   −0,2 % puis −3,0 %) et OlyBet (CLV −1,4 % puis −6,3 %).
2. **Stratégie à figer** : cote ≤ 5, écart ≥ 3 %, hors Winamax et OlyBet, pari pris au plus 24 h avant le match.
   Choisie sur les matchs du 05/10 au 25/10, validée sur ceux du 26/10 au 14/11 : **la CLV tient** (+1,98 %
   [+0,48 ; +3,48] contre −0,47 % pour les paris écartés), **le ROI ne valide rien** (−1,9 % [−13,6 ; +11,3]).
3. **Aucun gain n'est prouvé.** Sur la période de validation, la stratégie figée fait moins bien en ROI que les
   paris qu'elle écarte (−1,9 % contre +4,5 %, écart non significatif). 674 paris ne peuvent pas juger un ROI.
4. **L'écart annoncé surestime l'avantage.** Un modèle ajusté sur la première période annonçait +5,27 % sur la
   seconde : la CLV observée est +1,98 %. Seuls les écarts de 7 % et plus gardent une CLV nette sur les deux
   périodes.
5. **Mise proposée : Kelly au 1/16**, sur un avantage rétréci selon l'écart, moins ce qui est déjà misé sur le même
   match. Mise moyenne : 0,16 % de la bankroll, soit 1,60 € pour 1 000 €.
6. **La mise fixe de 10 € demande environ 5 000 € de bankroll.** Avec 1 000 €, s'il n'y a pas d'avantage réel,
   elle perd la moitié de la bankroll 7 années sur 10 et la ruine plus d'une année sur deux ; Kelly au 1/16 : 0,7 %
   et 0 %.
7. **Kelly ne crée pas de gain** : sur la période de validation, son ROI (−2,5 % à −3,4 %) ne se distingue pas de
   celui de la mise fixe (−1,9 %). Il réduit la perte maximale et le risque de ruine, parce qu'il mise moins et
   que la mise baisse avec la bankroll.

## Méthode en bref

- **Deux périodes.** A : les 1 417 matchs détectés avant le 26/10 (2 839 paris). B : les 1 005 suivants (2 201
  paris). Un match est entier dans une période.
- **Tout est choisi sur A** par une règle mécanique, écrite avant de regarder B : segments écartés, modèle
  d'avantage, corrélation. B sert seulement à vérifier.
- **Mesure : la CLV contre la clôture Pinnacle**, la seule qui prédit le rendement à cote ≤ 5
  ([avantage-reel.md](avantage-reel.md), partie 3). Le ROI est donné à côté, à mise fixe de 10 €.
- **Unité de hasard : le match.** Intervalles à 95 % par bootstrap sur les matchs, 10 000 tirages.

## 1. Ce qui ne rapporte rien ou fait perdre

Huit découpages : tranche de cote, écart annoncé, sport, marché, période de jeu, bookmaker, référence, avance sur
le match. Hors tranche de cote, cotes ≤ 5 seulement. Règle d'exclusion : **CLV Pinnacle négative sur A avec au
moins 50 mesures**.

### Écartés

| Segment | Paris | CLV sur A | CLV sur B | ROI, tout | Verdict |
|---|---|---|---|---|---|
| Cote > 5 | 970 | (non fiable) | (non fiable) | −43,7 % [−69,8 ; +22,8] | **perd** : −39,3 % sur A, −55,3 % sur B |
| Écart de 2 à 3 % | 1 671 | −0,27 % | −0,32 % | +2,0 % [−3,6 ; +7,8] | **ne rapporte rien**, confirmé sur B |
| Winamax | 473 | −0,22 % | −3,00 % | +7,0 % [−5,2 ; +19,6] | **ne bat pas la clôture**, confirmé sur B |
| OlyBet | 228 | −1,37 % | −6,30 % [−9,74 ; −2,68] | −8,1 % [−26,9 ; +12,1] | **perd**, confirmé sur B |
| Pari pris plus de 24 h avant | 905 | −1,22 % | +0,12 % | +9,0 % [−0,8 ; +19,8] | négatif sur A, **non confirmé** sur B |

- **Cote > 5** : déjà plafonné sur le site depuis le 11/11, sur toutes les données. A seule aurait donné la même
  décision. La CLV y est positive (+6,3 % et +8,4 %) et trompeuse : la cote juste des longues cotes est trop basse
  ([cote-juste.md](cote-juste.md), longues cotes).
- **Winamax** : ROI positif et CLV négative. Le ROI (473 paris) est du bruit, la CLV dit que ces cotes ne battent
  pas le marché.
- **Plus de 24 h** : la CLV est nulle sur B au lieu d'être négative. L'exclusion reste dans la stratégie figée,
  telle que choisie sur A ; elle ne coûte rien en CLV.

### Rien de mesurable, sur les deux périodes

CLV proche de zéro sur A et sur B, intervalle contenant zéro : rien ne dit que ces paris rapportent.

| Segment | Paris | CLV sur A | CLV sur B | ROI, tout |
|---|---|---|---|---|
| Football | 1 902 | +0,64 % | +0,46 % | +1,6 % [−5,5 ; +9,3] |
| 1N2 | 779 | +0,59 % | +0,16 % | +5,4 % [−5,6 ; +17,3] |
| Total | 868 | +0,93 % | +0,45 % | +3,2 % [−6,6 ; +12,8] |
| Vainqueur | 621 | +0,99 % | −0,43 % | +9,9 % [+1,6 ; +19,0] |
| Cote de 3 à 5 | 585 | +0,21 % | −0,27 % | +12,2 % [−3,7 ; +29,2] |
| 1re mi-temps | 445 | +0,57 % | +0,71 % | −5,7 % [−15,8 ; +4,4] |
| Volley | 159 | +1,73 % | −1,53 % | −13,7 % [−26,6 ; +0,8] |

Le football pèse 47 % des paris à cote ≤ 5. « Vainqueur » a un ROI dont l'intervalle est au-dessus de zéro, sans
correction pour la cinquantaine de segments regardés et sans CLV : pas un signal.

### Positif sur A, disparu sur B

Basket (CLV +3,59 % puis −0,50 %), handicap (+3,68 % puis −0,21 % ; ROI +7,8 % puis −14,8 %), Betclic (+2,66 %
puis −0,06 %), écart de 3 à 4 % (+1,68 % puis −0,94 %), cote de 1,51 à 2 (+1,74 % puis −0,51 %). Sur B, l'ensemble
des paris à cote ≤ 5 ne bat plus la clôture : +0,41 % [−0,49 ; +1,29], contre +1,88 % sur A. **Ces segments ne
sont pas écartés** : le faire maintenant serait choisir sur B. À regarder sur la prochaine période.

### Ce qui tient sur les deux périodes

CLV au-dessus de zéro sur A et sur B : PMU (+2,53 % puis +1,96 %), écart de 7 à 10 % (+4,59 % puis +3,22 %), écart
de 10 % et plus (+9,94 % puis +7,04 %), total d'équipe (+1,56 % puis +1,88 %), double chance (+4,97 % puis
+2,10 %), sports hors football, basket, hockey, tennis et volley (+2,60 % puis +2,19 %). Aucun n'a un ROI prouvé.

## 2. Stratégie à figer

**Règles** : un pari par cote (paris uniques), cote ≤ 5, écart annoncé ≥ 3 %, tous bookmakers sauf Winamax et
OlyBet, détecté au plus 24 h avant le début. Environ 36 paris par jour, 36 % des paris à cote ≤ 5.

| Ensemble | Période | Paris | ROI | IC 95 % | CLV Pinnacle | IC 95 % |
|---|---|---|---|---|---|---|
| Stratégie figée | A (choix) | 792 | +5,2 % | [−4,4 ; +15,3] | +5,10 % | [+3,89 ; +6,68] |
| Stratégie figée | **B (validation)** | 674 | −1,9 % | [−13,6 ; +11,3] | +1,98 % | [+0,48 ; +3,48] |
| Paris écartés, cote ≤ 5 | B | 1 262 | +4,5 % | [−3,2 ; +12,7] | −0,47 % | [−1,43 ; +0,50] |
| Site actuel, cote ≤ 5 | B | 1 936 | +2,2 % | [−4,7 ; +9,7] | +0,41 % | [−0,49 ; +1,29] |
| Stratégie figée − écartés | B | | −6,3 % | [−19,3 ; +7,3] | +2,45 % | [+0,83 ; +4,05] |

- **Validée sur la CLV** : sur des matchs qu'elle n'a pas vus, la stratégie bat la clôture Pinnacle et fait 2,45
  points de mieux que les paris écartés. Trois exclusions sur quatre sont confirmées une à une.
- **Pas validée sur le ROI** : négatif sur B, et inférieur à celui des paris écartés. Les deux intervalles
  contiennent zéro. Ce n'est ni une preuve qu'elle perd, ni une preuve qu'elle gagne.
- **La CLV de A était gonflée** : +5,10 % sur la période qui a servi à choisir, +1,98 % ensuite. Le chiffre à
  retenir est le second.
- **Jugée sur la référence Pinnacle seulement** : les 410 paris d'une autre référence (28 %) n'ont que 39 clôtures
  Pinnacle. Leur ROI : +0,2 % [−13,1 ; +13,8].

**Suite** : appliquer ces règles à partir du 15/11 sans les changer. Juger vers le 05/12, sur la CLV Pinnacle des
paris pris depuis le gel : il faut environ 400 mesures (620 paris, 18 jours) pour distinguer +2 % de zéro. Réussite :
intervalle au-dessus de zéro. Échec : CLV moyenne négative ou nulle. Par le ROI, il faudrait 36 000 paris, soit
près de 3 ans.

## 3. Mise de Kelly fractionnée

### Formule

    mise = bankroll × 1/16 × avantage compté / (cote − 1) − exposition déjà prise sur le match

plafonnée à 2 % de la bankroll par pari et à 50 % de mises en cours. Pas de mise si le résultat est négatif.

| Écart annoncé | Avantage prévu | Incertitude | Part gardée | Avantage compté |
|---|---|---|---|---|
| 3 % | +1,04 % | 2,31 % | 0,17 | +0,18 % |
| 4 % | +2,15 % | 2,29 % | 0,47 | +1,01 % |
| 5 % | +3,26 % | 2,28 % | 0,67 | +2,19 % |
| 7 % | +5,47 % | 2,32 % | 0,85 | +4,64 % |
| 10 % et plus | +8,80 % | 2,49 % | 0,93 | +8,15 % |

Exemples pour 1 000 € de bankroll : cote 2,00 et écart de 4 %, 0,63 € ; cote 2,00 et écart de 7 %, 2,90 € ; cote
1,50 et écart de 10 %, 10,19 €.

### Incertitude sur la cote juste : trois étages

1. **L'écart annoncé n'est pas l'avantage.** Avantage prévu = −2,28 % + 1,11 × écart, l'écart compté jusqu'à 10 %
   (ajusté sur la CLV Pinnacle des 893 paris retenus qui l'ont). La cote juste bouge entre la détection et la
   clôture : la CLV d'un pari a un écart-type de 10,3 %, et on ne voit un pari que quand l'erreur va dans le bon
   sens. Un écart de 3 % vaut 1 % d'avantage.
2. **Cet avantage est lui-même mal connu.** Le modèle ajusté sur A (avantage ≈ écart) annonçait +5,27 % sur B,
   pour +1,98 % observé : 3,30 points de trop [1,90 ; 4,68]. Le niveau d'avantage varie donc d'une période à
   l'autre, d'environ 2,2 points. Cette incertitude réduit la mise par le facteur avantage² / (avantage² +
   incertitude²) (Baker et McHale, 2013) : 0,17 pour un écart de 3 %, 0,93 pour 10 %.
3. **La CLV n'est pas un gain prouvé.** C'est la raison de la fraction 1/16 et des scénarios ci-dessous.

Le classement, lui, tient : sur B, le tiers des paris au plus fort avantage prévu a une CLV de +5,58 %, le tiers le
plus bas −0,25 %.

### Corrélation entre paris d'un même match

Mesurée sur A, résultats centrés sur la probabilité juste : **0,27 [0,18 ; 0,35]** entre deux paris différents du
même match (2 075 paires, 387 matchs) ; **1** pour la même sélection chez un autre bookmaker (mesuré : 1,07 [0,92 ;
1,26]).

Règle : au pari k, on retire de sa mise de Kelly, pour chaque pari j déjà pris sur le match,
corrélation × √(variance j / variance k) × mise j. Deux bookmakers sur la même sélection se partagent donc une seule
mise ; un deuxième pari sur le même match reçoit sa mise diminuée de 27 % de la première. Résultat : 14 % des paris
ne reçoivent aucune mise.

### Fraction

Critère fixé avant la simulation : la plus grande fraction qui, **s'il n'y a aucun avantage réel**, fait perdre la
moitié de la bankroll en un an dans moins de 5 % des cas. Au 1/8 : 17,7 %. **Au 1/16 : 0,7 %.**

### Simulation contre la mise fixe de 10 €

2 000 trajectoires d'un an. Chaque jour est un jour réel tiré au hasard (36 paris en moyenne, leurs cotes, leurs
matchs) ; les résultats sont tirés selon un avantage réel supposé, avec la corrélation mesurée dans un match.
Bankroll de départ : 1 000 €, sauf la deuxième ligne. Perte maximale : baisse depuis le plus haut atteint. « Perd
la moitié » : passe sous 50 % du départ ; « ruine » : sous 10 %.

| Avantage réel | Mise | ROI médian | Perte maximale médiane | Perte maximale, 1 an sur 20 | Perd la moitié | Ruine |
|---|---|---|---|---|---|---|
| Celui du modèle (+3,7 %) | Fixe 10 € | +3,7 % | 33 % | 81 % | 12,9 % | 2,8 % |
| | Fixe 10 €, bankroll 5 000 € | +3,7 % | 11 % | 22 % | 0,0 % | 0,0 % |
| | Kelly 1/8 | +5,2 % | 18 % | 29 % | 0,0 % | 0,0 % |
| | **Kelly 1/16** | +5,4 % | 10 % | 16 % | 0,0 % | 0,0 % |
| La moitié (+1,9 %) | Fixe 10 € | +1,9 % | 51 % | 100 % | 34,5 % | 15,2 % |
| | Fixe 10 €, bankroll 5 000 € | +1,9 % | 17 % | 36 % | 0,5 % | 0,0 % |
| | Kelly 1/8 | +2,5 % | 26 % | 44 % | 0,2 % | 0,0 % |
| | **Kelly 1/16** | +2,6 % | 14 % | 24 % | 0,0 % | 0,0 % |
| Aucun | Fixe 10 € | +0,1 % | 99 % | 100 % | 70,1 % | 54,6 % |
| | Fixe 10 €, bankroll 5 000 € | +0,1 % | 29 % | 66 % | 11,3 % | 0,5 % |
| | Kelly 1/8 | −0,3 % | 43 % | 68 % | 17,7 % | 0,0 % |
| | **Kelly 1/16** | −0,1 % | 23 % | 42 % | 0,7 % | 0,0 % |
| −2 % | Fixe 10 € | −2,0 % | 100 % | 100 % | 96,8 % | 94,2 % |
| | Fixe 10 €, bankroll 5 000 € | −2,0 % | 63 % | 100 % | 64,5 % | 16,9 % |
| | Kelly 1/8 | −2,3 % | 65 % | 82 % | 72,5 % | 0,1 % |
| | **Kelly 1/16** | −2,2 % | 39 % | 57 % | 13,9 % | 0,0 % |

- **ROI** : si le modèle dit vrai, Kelly fait 1,7 point de mieux que la mise fixe, parce qu'il mise plus sur les
  gros écarts. S'il n'y a pas d'avantage, il fait un peu moins bien. Il ne transforme pas un avantage nul en gain.
- **Perte maximale et ruine** : 10 € sur 1 000 € de bankroll, c'est 1 % par pari sur 36 paris par jour, six fois la
  mise moyenne de Kelly au 1/16. Même avec l'avantage du modèle, cette mise fixe perd la moitié de la bankroll
  une année sur huit.
- **À mise comparable** (10 € sur 5 000 € = 0,2 % par pari, entre Kelly 1/16 et 1/8) : pertes maximales proches
  si l'avantage existe ; sans avantage, Kelly au 1/16 perd la moitié dans 0,7 % des cas contre 11,3 %.
- **Effet de la correction de corrélation**, au 1/16 : sans elle, 28 % de mises en plus, perte maximale d'une
  année sur vingt de 23 % au lieu de 16 % (avantage du modèle), et sans avantage 5,6 % de chances de perdre la
  moitié au lieu de 0,7 %.
- Les bankrolls finales du scénario « modèle » (×2,7 en un an au 1/16) ne sont pas des prévisions : limites de
  mise des bookmakers non simulées, avantage non prouvé.

### Rejeu des paris réels de la période de validation

Paris de B rejoués dans l'ordre, bankroll de 1 000 € au 26/10. Kelly « modèle de A » : test hors échantillon.

| Mise | Paris joués | Mises | Gain | ROI | IC 95 % | Perte maximale |
|---|---|---|---|---|---|---|
| Fixe 10 €, site actuel (cote ≤ 5) | 1 936 | 19 360 € | +435 € | +2,2 % | [−4,7 ; +9,7] | 709 € |
| Fixe 10 €, stratégie figée | 674 | 6 740 € | −128 € | −1,9 % | [−13,4 ; +10,8] | 804 € |
| Kelly 1/8, modèle de A | 594 | 3 675 € | −113 € | −3,1 % | [−12,3 ; +6,2] | 397 € |
| Kelly 1/16, modèle de A | 597 | 1 879 € | −47 € | −2,5 % | [−11,2 ; +6,5] | 192 € |
| Kelly 1/16, modèle proposé (ajusté sur ces paris) | 566 | 921 € | −31 € | −3,4 % | [−14,8 ; +8,6] | 120 € |

Sur 20 jours réels, la stratégie figée perd à mise fixe comme en Kelly, et le site entier gagne : tout est dans le
bruit. Kelly perd moins d'euros parce qu'il en mise moins.

## Limites

- **Plafond de cote à 5** : décidé le 11/11 sur toutes les données. Il n'a pas été rechoisi ici.
- **Les découpages ont été choisis en connaissant les deux rapports précédents**, faits sur toutes les données.
  Seule la règle d'exclusion et ses seuils sont lus sur A.
- **Un seul découpage à la fois** : pas de croisement (bookmaker × sport, par exemple).
- **Le modèle de mise proposé est réajusté sur A et B** après l'échec de niveau du modèle de A : il n'est pas
  validé hors échantillon. Le facteur d'incertitude est là pour ça ; le test sera la période du 15/11 au 05/12.
- **CLV mesurée sur 61 % des paris de la stratégie** (893 sur 1 466), presque tous de référence Pinnacle.
- **CLV et non gain** : un point de CLV vaut 1,23 point de rendement [0,55 ; 1,89] à cote ≤ 5 (avantage-reel.md).
- **Simulation** : résultats gagné ou perdu seulement (3 % de remboursés ignorés), mises du jour calculées sur la
  bankroll du matin, pas d'arrondi ni de mise minimale, pas de limite de mise ni de compte fermé par un bookmaker.
- **41 jours**, une seule partie de la saison ; deux périodes seulement pour estimer ce qui change d'une période à
  l'autre.

## Décisions proposées

1. Figer la stratégie de la partie 2 à partir du 15/11 et ne plus toucher aux règles avant le 05/12.
2. Retirer Winamax et OlyBet des paris à jouer, et ne plus jouer les écarts de 2 à 3 %.
3. Miser en Kelly au 1/16 avec le tableau d'avantage compté ; à défaut, ramener la mise fixe à 0,2 % de la
   bankroll (2 € pour 1 000 €).
4. Ne rien décider sur le basket, les handicaps, Betclic ou l'écart de 3 à 4 % avant la prochaine période.
5. Relancer le script vers le 05/12 et juger la stratégie sur la CLV Pinnacle des paris pris depuis le gel.

## Reproduire

```bash
bash scripts/cloner_donnees.sh https://github.com/Matttgic/cotes-value donnees
```

```bash
python scripts/strategie_mises.py --donnees donnees --markdown docs/strategie-mises-tableaux.md
```

Demande numpy (`requirements-dev.txt`). Les données changent toutes les heures : pour retrouver ces chiffres, se
placer sur le commit `4283860` de `donnees`.
