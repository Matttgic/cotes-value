# Cote juste : retrait de la marge et consensus

Fait le 14/11/2026. Deux jeux de données : 330 fichiers de football-data.co.uk (22 divisions, saisons 2012/13 à
2026/27, cotes Pinnacle et bet365 avec le score), et la branche `donnees` (commit `f13913e`, 14/11 à 11:38 UTC :
paris réglés depuis le 05/10, `references/` depuis le 12/11). Tous les chiffres sortent de
`scripts/cote_juste.py` (lecture seule, graine fixe) ; tous les tableaux : [cote-juste-tableaux.md](cote-juste-tableaux.md).
Suite de [avantage-reel.md](avantage-reel.md).

## Conclusion

1. **Aucun changement de code : aucun gain n'est mesuré.** Ni une autre méthode de retrait de marge, ni une autre
   pondération du consensus ne bat l'existant sur des données qu'elle n'a pas vues.
2. **Marge, 1N2 : la méthode puissance (actuelle) est la meilleure ou à égalité.** Sur 101 874 matchs Pinnacle et
   110 018 matchs bet365, la multiplicative est nettement moins bonne, Shin et odds ratio un peu moins bonnes,
   l'additive égale mais elle peut rendre une probabilité négative.
3. **Marge, totaux et handicaps : aucune méthode ne se distingue** sur les résultats (48 000 à 56 000 totaux,
   20 000 handicaps). La puissance a la meilleure calibration sur les totaux.
4. **Marge, deux issues avec un gros favori (tennis, basket) : non tranché.** C'est là que le choix compte le plus
   (24 % de nos marchés ont un favori à 75 % ou plus) et là que les données manquent : 129 marchés réglés. Trois
   indices disent que la puissance donne trop au favori, aucun n'est une preuve. À re-mesurer vers le 05/12.
5. **Props joueurs : non mesurable.** Aucun marché réglé dans `references/`, 77 paris papier.
6. **Longues cotes : même la puissance surestime les issues à moins de 10 %.** À la clôture Pinnacle, une issue
   annoncée à 3,66 % gagne 2,93 % du temps, une issue annoncée à 7,83 % gagne 7,08 % du temps. Les autres méthodes
   font pire. Cela va dans le sens du plafond de cote à 5.
7. **Consensus : la moyenne simple Pinnacle + Polymarket, avec les filtres actuels, n'est battue par rien.** La
   pondération proposée (fraîcheur, liquidité, écart achat/vente) gagne sur les matchs qui l'ont ajustée et perd
   sur les 78 matchs jamais vus.
8. **Les filtres actuels font déjà le travail de la pondération.** Hors du filtre (écart achat/vente de 5 à 8
   points), Polymarket dégrade la moyenne. Dans le filtre, ni la liquidité ni l'âge du prix ne changent le résultat.
9. **Matchbook reste hors du consensus** : gain sur les matchs d'ajustement, perte sur les matchs de test.
10. **Sur les résultats réels, Pinnacle seul fait au moins aussi bien que la moyenne** (692 paris, écart non
    significatif) et mieux que Polymarket quand les deux se contredisent.
11. **DraftKings : non mesurable.** Aucune de ses cotes n'est conservée dans `donnees`.

## 1. Retrait de la marge

Cinq méthodes (q = 1/cote, B = somme des q, n issues) :

| Méthode | Formule | Effet |
|---|---|---|
| Multiplicative | p = q / B | Retire la marge au prorata : laisse le biais favori/outsider |
| Additive | p = q − (B − 1) / n | Retire la même quantité à chaque issue ; peut passer sous zéro |
| Puissance (actuelle, `cotes/marge.py`) | p = q^k, k tel que la somme vaut 1 | Retire plus aux outsiders |
| Shin | modèle de parieurs informés, un paramètre z | Entre multiplicative et puissance |
| Odds ratio | p / (1 − p) = q / (1 − q) / c | Entre multiplicative et puissance |

Sur deux issues, Shin et additive donnent exactement le même résultat.

Mesures : log-loss et Brier sur l'issue gagnante ; pente de calibration (1 = calibré, plus de 1 = les favoris
gagnent plus souvent qu'annoncé, donc la marge n'a pas été assez retirée aux outsiders) ; écart de log-loss avec la
puissance, match par match, intervalle à 95 % par bootstrap. Les écarts sont multipliés par 10⁴ ; négatif = mieux
que la puissance.

### L'enjeu sur nos marchés

Marchés Pinnacle de `references/`, dernier état avant le début. Les cotes brutes sont recalculées depuis la
probabilité juste et la marge enregistrées. « Part > 2 % » : part des issues dont la cote juste change de plus de
2 % (le seuil de détection) si on remplace la puissance par la méthode.

| Type | Marchés | Marge médiane | Favori ≥ 75 % | Multiplicative : part > 2 % | Additive | Shin | Odds ratio |
|---|---|---|---|---|---|---|---|
| 1N2 | 2 792 | 7,13 % | 5 % | 56 % | 8 % | 15 % | 21 % |
| Deux issues | 5 227 | 5,46 % | 24 % | 55 % | 24 % | 24 % | 19 % |
| Totaux | 56 904 | 6,88 % | 4 % | 39 % | 10 % | 10 % | 7 % |
| Handicaps | 45 975 | 6,94 % | 6 % | 45 % | 13 % | 13 % | 10 % |
| Props joueurs | 2 451 | 6,96 % | 4 % | 28 % | 7 % | 7 % | 6 % |

Notre lecture de Pinnacle a 5,5 à 7 % de marge, deux fois celle des fichiers de football (3 %) : bet365 (6 %) y est
le meilleur équivalent. Le choix de la méthode n'est pas un détail : il déplace un quart des cotes justes des
marchés à deux issues de plus que le seuil.

### 1N2 : football-data.co.uk

| Bookmaker, moment | Matchs | Marge | Multiplicative | Additive | Shin | Odds ratio | Pente de la puissance |
|---|---|---|---|---|---|---|---|
| Pinnacle, avant-match | 101 874 | 3,34 % | **+2,45 [+1,35 ; +3,50]** | +0,15 [−0,07 ; +0,39] | **+0,46 [+0,10 ; +0,81]** | **+0,56 [+0,10 ; +0,99]** | 1,009 ± 0,015 |
| Pinnacle, clôture | 101 468 | 3,01 % | **+2,16 [+1,16 ; +3,21]** | −0,06 [−0,33 ; +0,19] | +0,27 [−0,10 ; +0,63] | **+0,54 [+0,14 ; +0,93]** | 1,013 ± 0,015 |
| bet365, avant-match | 110 018 | 6,05 % | **+4,80 [+2,88 ; +6,60]** | +0,37 [−0,05 ; +0,78] | **+0,68 [+0,03 ; +1,31]** | +0,65 [−0,10 ; +1,35] | 0,994 ± 0,014 |
| bet365, clôture | 55 663 | 6,62 % | **+5,57 [+2,88 ; +8,34]** | +0,09 [−0,55 ; +0,70] | +0,58 [−0,43 ; +1,58] | +0,82 [−0,27 ; +1,96] | 0,994 ± 0,020 |

- La puissance est calibrée : pente de 0,99 à 1,01. La multiplicative laisse une pente de 1,05 à 1,08.
- L'écart grandit avec la marge et avec le favori : à 75 % ou plus, la multiplicative perd +20 à +62 selon le
  bookmaker, Shin et odds ratio +2 à +14.
- L'additive fait jeu égal, mais elle a rendu une probabilité négative sur un marché bet365, et plus la marge
  monte, plus cela arrive. Aucune raison de la préférer.

### Totaux et handicaps : football-data.co.uk

| Marché, bookmaker, moment | Matchs | Marge | Multiplicative | Additive = Shin | Odds ratio | Pente : puissance · additive |
|---|---|---|---|---|---|---|
| Total 2,5, Pinnacle, avant-match | 48 309 | 3,96 % | +0,90 [−0,16 ; +1,85] | +0,17 [−0,19 ; +0,49] | +0,14 [−0,17 ; +0,45] | 1,020 · 1,043 |
| Total 2,5, Pinnacle, clôture | 48 504 | 3,59 % | +0,83 [−0,23 ; +1,80] | +0,16 [−0,18 ; +0,51] | +0,12 [−0,19 ; +0,43] | 1,006 · 1,027 |
| Total 2,5, bet365, avant-match | 55 567 | 5,57 % | **+1,57 [+0,27 ; +2,83]** | +0,28 [−0,17 ; +0,74] | +0,22 [−0,20 ; +0,63] | 1,010 · 1,042 |
| Total 2,5, bet365, clôture | 55 652 | 5,59 % | +1,32 [−0,10 ; +2,76] | +0,14 [−0,37 ; +0,64] | +0,09 [−0,32 ; +0,54] | 0,989 · 1,021 |
| Handicap asiatique, Pinnacle, avant-match | 19 689 | 3,15 % | +0,12 [−0,23 ; +0,47] | +0,03 [−0,09 ; +0,15] | +0,03 [−0,08 ; +0,14] | 1,093 · 1,110 |
| Handicap asiatique, Pinnacle, clôture | 19 591 | 2,78 % | **−0,39 [−0,73 ; −0,07]** | **−0,14 [−0,25 ; −0,02]** | **−0,13 [−0,23 ; −0,03]** | 0,673 · 0,683 |
| Handicap asiatique, bet365, avant-match | 22 722 | 3,91 % | +0,19 [−0,32 ; +0,74] | +0,09 [−0,12 ; +0,34] | +0,03 [−0,12 ; +0,19] | 1,023 · 1,047 |
| Handicap asiatique, bet365, clôture | 22 706 | 3,91 % | **−0,69 [−1,18 ; −0,17]** | **−0,25 [−0,42 ; −0,09]** | **−0,23 [−0,38 ; −0,08]** | 0,630 · 0,645 |

- **Totaux** : la puissance est devant partout, sans que l'écart avec additive, Shin ou odds ratio sorte du bruit.
  Sa pente est la plus proche de 1.
- **Handicaps** : lignes à 50/50, les méthodes donnent presque la même chose (écarts dix fois plus petits que sur
  le 1N2). À la clôture la multiplicative est devant, avant-match derrière : pas de gagnant. La pente de 0,63 à
  0,70 à la clôture vaut pour toutes les méthodes : le côté légèrement favori gagne moins qu'annoncé, et aucun
  retrait de marge ne le corrige.
- Handicap asiatique : lignes entières et demies seulement (un quart de but partage la mise).

### Deux issues, totaux, handicaps : nos données

Trois mesures, de la plus neutre à la moins neutre.

**a. Marchés Pinnacle réglés, non sélectionnés** (dernière cote avant le début, matchs dont le score est connu
par un pari réglé) :

| Type | Marchés / matchs | Additive = Shin − puissance | Pente : puissance · additive · multiplicative |
|---|---|---|---|
| 1N2 | 54 / 43 | −7 [−31 ; +12] | 0,93 · 0,93 · 1,02 (± 0,5) |
| Deux issues | 129 / 60 | −71 [−203 ; +16] | 0,78 · 0,86 · 0,95 (± 0,4) |
| Totaux | 746 / 63 | −1 [−10 ; +8] | 0,96 · 1,00 · 1,07 (± 0,3) |
| Handicaps | 631 / 63 | −8 [−27 ; +6] | 0,83 · 0,88 · 0,95 (± 0,3) |

Soixante matchs : tous les intervalles contiennent zéro, toutes les pentes sont compatibles avec 1.

**b. Paris réglés de référence Pinnacle, deux issues** (2 169 paris, 1 194 matchs, depuis le 05/10 ; échantillon
choisi par la puissance, donc biaisé) :

| Type | Paris | Additive = Shin − puissance | Odds ratio − puissance | Multiplicative − puissance |
|---|---|---|---|---|
| Deux issues | 410 | +15 [−9 ; +37] | +11 [−8 ; +28] | +47 [−12 ; +98] |
| Totaux | 1 065 | −3 [−10 ; +4] | −3 [−8 ; +3] | −6 [−24 ; +13] |
| Handicaps | 694 | −3 [−14 ; +5] | −3 [−11 ; +5] | −5 [−31 ; +17] |
| Tous | 2 169 | +0 [−7 ; +7] | −0 [−5 ; +5] | +4 [−12 ; +20] |

Rien de significatif. Les 487 paris que l'additive aurait écartés (écart sous 2 % avec elle) font −4,6 %
[−11,7 ; +2,2], les 1 682 gardés +1,1 % [−5,5 ; +8,1] : un indice, pas une preuve.

**c. Chaque méthode face au prix des bourses** (Polymarket ou Matchbook au même instant, une heure avant le début,
écart achat/vente ≤ 3 points). Un prix de bourse n'a pas de marge à retirer, mais ce n'est pas la vérité.

| Bourse, type | Marchés / matchs | Additive = Shin − puissance | Multiplicative − puissance | Favori, en points : multiplicative · additive · puissance |
|---|---|---|---|---|
| Polymarket, 1N2 | 153 / 99 | −0,50 [−1,44 ; +0,24] (Shin : **−0,96**) | **+6,18 [+4,04 ; +8,50]** | −1,15 · +0,22 · +0,31 |
| Polymarket, deux issues | 525 / 454 | **−2,50 [−3,16 ; −1,92]** | **−2,20 [−3,52 ; −0,90]** | −0,24 · +0,46 · +0,85 |
| Polymarket, deux issues, favori ≥ 75 % | 98 / 97 | **−9,52 [−12,79 ; −6,68]** | −6,30 [−13,37 ; +0,54] | −1,00 · +0,59 · +1,57 |
| Polymarket, totaux | 1 029 / 284 | **−1,07 [−1,26 ; −0,87]** | **−0,39 [−0,71 ; −0,07]** | −0,37 · +0,19 · +0,50 |
| Polymarket, handicaps | 503 / 260 | **−0,53 [−0,69 ; −0,39]** | −0,09 [−0,40 ; +0,24] | −0,20 · +0,18 · +0,38 |
| Matchbook, 1N2 | 89 / 83 | **−1,08 [−2,40 ; −0,15]** | **+6,94 [+4,03 ; +9,81]** | −1,36 · +0,07 · +0,23 |
| Matchbook, deux issues | 119 / 106 | **−1,31 [−2,31 ; −0,56]** | +0,05 [−1,63 ; +1,75] | −0,36 · +0,31 · +0,68 |
| Matchbook, totaux | 167 / 71 | **−1,64 [−2,18 ; −1,15]** | **+1,44 [+0,14 ; +2,77]** | −0,79 · +0,12 · +0,64 |
| Matchbook, handicaps | 305 / 65 | **−0,70 [−1,00 ; −0,39]** | +0,48 [−0,26 ; +1,28] | −0,57 · +0,09 · +0,45 |

Sur deux issues, la puissance place le favori 0,4 à 0,9 point au-dessus des bourses (1,6 point pour un favori à
75 % ou plus), l'additive 0,1 à 0,5 point, la multiplicative en dessous. Les bourses sont plus proches de
l'additive, nettement.

**Lecture.** Les trois indices (bourses, 60 matchs réglés, paris écartés) vont dans le même sens : sur deux issues,
la puissance retirerait trop de marge à l'outsider. Mais :

- seul l'accord avec les bourses est significatif, et une bourse surcote elle-même les outsiders (biais connu des
  marchés d'échange) : s'en rapprocher n'est pas se rapprocher de la vérité ;
- sur les résultats, là où l'échantillon est grand (totaux du football, 1N2), la puissance ne retire pas trop :
  elle retire juste assez, ou pas assez pour les issues à moins de 10 % ;
- sur les résultats de nos paris, Pinnacle lu avec la puissance fait mieux que Polymarket (partie 2).

Pas de changement. Il faut environ 600 matchs réglés à deux issues pour trancher (dix fois l'échantillon actuel) :
environ trois semaines de `references/` de plus.

### Longues cotes

Courbe de calibration du 1N2 Pinnacle (toutes issues, tranche de probabilité selon la puissance) :

| Tranche | Moment | Issues | Observée ± IC | Multiplicative | Additive | Puissance | Shin | Odds ratio |
|---|---|---|---|---|---|---|---|---|
| 0 à 5 % | avant-match | 1 568 | 3,06 ± 0,85 | 4,03 | 3,72 | 3,79 | 3,82 | 3,91 |
| 0 à 5 % | clôture | 1 840 | 2,93 ± 0,77 | 3,93 | 3,58 | 3,66 | 3,69 | 3,79 |
| 5 à 10 % | avant-match | 6 178 | 7,51 ± 0,66 | 7,83 | 7,83 | 7,82 | 7,83 | 7,82 |
| 5 à 10 % | clôture | 6 607 | 7,08 ± 0,62 | 7,85 | 7,85 | 7,83 | 7,85 | 7,86 |
| 70 à 80 % | clôture | 5 637 | 76,57 ± 1,11 | 74,38 | 74,36 | 74,36 | 74,35 | 74,36 |
| 80 à 90 % | clôture | 2 722 | 84,79 ± 1,35 | 83,82 | 84,08 | 84,10 | 84,00 | 83,99 |

Sous 10 %, toutes les méthodes annoncent plus que la fréquence observée ; au-dessus de 70 %, moins. La cote juste
d'une issue à moins de 5 % est donc trop basse d'environ 20 % (3,66 annoncé pour 2,93 observé), avec n'importe
laquelle des cinq méthodes. Un écart de 5 ou 10 % sur une cote supérieure à 20 n'est pas un avantage.

### Props joueurs

Marge de 7 % sur deux issues presque toujours équilibrées (favori à 75 % ou plus : 4 % des marchés) : le choix de
la méthode déplace 7 % des cotes justes de plus de 2 %. Aucun résultat pour départager : `references/` n'a aucune
prop réglée et les paris papier sont 77.

## 2. Consensus

Aujourd'hui (`cotes/comparaison.py`) : moyenne simple des probabilités de Pinnacle et de Polymarket quand les deux
sont fiables. Fiable : Pinnacle à marge ≤ 12 % et non périmée ; Polymarket à écart achat/vente ≤ 5 points et ≤ 25 %
du prix, liquidité ≥ 100. Matchbook et Smarkets ont leur table mais restent hors de la moyenne.

### Données et méthode

- **496 matchs commencés du 12/11 03:10 au 14/11 11:30**, cotés par Pinnacle et au moins une autre référence :
  418 avec des lignes Polymarket fiables, 159 avec Matchbook, 113 avec Smarkets. Une ligne par pari et par avance
  (1, 3, 6 et 12 h avant le début) : 40 107 lignes. Les matchs sont reliés par la règle d'association du site.
- **Cible : la clôture** (dernier prix avant le début). Les résultats manquent : une soixantaine de matchs de
  `references/` ont un score.
  Deux cibles, qui encadrent la vérité : la clôture Pinnacle (avantage Pinnacle, qui partage ses erreurs avec
  elle-même) et la moyenne des clôtures des sources présentes (avantage au poids égal).
- **Ajustement sur les 245 matchs commencés avant le 13/11 12:00, test sur les 251 suivants.** Parmi eux, 82 ont
  commencé après le gel de la méthode (14/11 00:20) : ni les poids ni les choix d'analyse ne les ont vus.
- Erreur : racine de l'erreur quadratique moyenne, en points de probabilité. Écarts d'erreur quadratique ×10⁴,
  intervalle à 95 % par match, négatif = mieux.
- **Fraîcheur** : âge du prix, temps écoulé depuis son dernier changement. L'heure de lecture, elle, est déjà
  bornée à 15 minutes par la détection.

### La pondération proposée

Poids de Pinnacle : 1, modulé par l'âge de son prix, sa marge et sa limite de mise. Poids d'une bourse :

    poids = base de la source × exp(a × écart achat/vente + b × log10(liquidité) + c × ln(1 + âge du prix en heures))

Huit paramètres, ajustés pour minimiser l'erreur contre la clôture Pinnacle. Valeurs ajustées : écart −0,87 par
point, liquidité −1,89, âge −2,49 ; base Polymarket 1,69, Matchbook 31,82. Une version sans variables (un poids
fixe par source) donne Pinnacle 1, Polymarket 0,58, Matchbook 4,59.

### Validation

| Période | Pondération | Lignes / matchs | Erreur, clôture Pinnacle | Écart avec l'actuel | Erreur, moyenne des clôtures | Écart avec l'actuel |
|---|---|---|---|---|---|---|
| Ajustement | Pinnacle seul | 9 338 / 229 | 2,87 | **+0,13 [+0,02 ; +0,26]** | 3,05 | **+0,51 [+0,36 ; +0,66]** |
| Ajustement | Actuel : moyenne simple Pinnacle + Polymarket | 9 338 / 229 | 2,84 | référence | 2,97 | référence |
| Ajustement | Moyenne simple avec Matchbook | 9 338 / 229 | 2,80 | **−0,27 [−0,53 ; −0,06]** | 2,91 | **−0,35 [−0,59 ; −0,16]** |
| Ajustement | Poids fixes ajustés | 9 338 / 229 | 2,78 | **−0,34 [−0,74 ; −0,03]** | 2,90 | **−0,41 [−0,78 ; −0,11]** |
| Ajustement | Poids selon fraîcheur, liquidité et écart | 9 338 / 229 | 2,78 | **−0,37 [−0,80 ; −0,02]** | 2,91 | **−0,34 [−0,74 ; −0,01]** |
| Test | Pinnacle seul | 12 962 / 228 | 2,71 | +0,06 [−0,02 ; +0,15] | 2,72 | **+0,35 [+0,26 ; +0,45]** |
| Test | Actuel | 12 962 / 228 | 2,70 | référence | 2,66 | référence |
| Test | Moyenne simple avec Matchbook | 12 962 / 228 | 2,72 | **+0,08 [+0,00 ; +0,16]** | 2,65 | −0,04 [−0,12 ; +0,04] |
| Test | Poids fixes ajustés | 12 962 / 228 | 2,75 | **+0,23 [+0,09 ; +0,37]** | 2,67 | +0,05 [−0,08 ; +0,18] |
| Test | Poids selon fraîcheur, liquidité et écart | 12 962 / 228 | 2,77 | **+0,34 [+0,21 ; +0,48]** | 2,70 | **+0,24 [+0,11 ; +0,37]** |
| Jamais vu | Pinnacle seul | 3 993 / 78 | 3,03 | −0,01 [−0,14 ; +0,10] | 3,08 | **+0,33 [+0,18 ; +0,51]** |
| Jamais vu | Actuel | 3 993 / 78 | 3,03 | référence | 3,03 | référence |
| Jamais vu | Moyenne simple avec Matchbook | 3 993 / 78 | 3,05 | **+0,14 [+0,02 ; +0,27]** | 3,03 | +0,04 [−0,08 ; +0,18] |
| Jamais vu | Poids fixes ajustés | 3 993 / 78 | 3,07 | **+0,28 [+0,06 ; +0,52]** | 3,06 | +0,17 [−0,05 ; +0,42] |
| Jamais vu | Poids selon fraîcheur, liquidité et écart | 3 993 / 78 | 3,08 | **+0,34 [+0,13 ; +0,59]** | 3,08 | **+0,34 [+0,12 ; +0,61]** |

- **La pondération proposée est rejetée** : meilleure que l'actuelle sur les matchs qui l'ont ajustée, moins bonne
  sur le test et sur les matchs jamais vus, avec les deux cibles. Ses coefficients ne tiennent pas d'un jour à
  l'autre (une liquidité plus forte y fait baisser le poids).
- **Les poids fixes aussi**, et l'ajout de Matchbook : gain à l'ajustement, perte ensuite.
- **La moyenne actuelle contre Pinnacle seul** : jamais moins bonne, meilleure dès que la cible n'est pas la
  clôture de Pinnacle elle-même.

### Fraîcheur, liquidité, écart achat/vente

Moyenne simple à deux contre Pinnacle seul, cible clôture Pinnacle (la plus sévère pour l'autre source). Seule la
variable étudiée sort du filtre.

| Source | Variable | Tranche | Lignes / matchs | Moyenne − Pinnacle |
|---|---|---|---|---|
| Polymarket | Écart achat/vente | 0 à 2 points | 7 456 / 352 | **−0,25 [−0,39 ; −0,11]** |
| Polymarket | Écart achat/vente | 2 à 3 points | 4 887 / 365 | −0,02 [−0,14 ; +0,10] |
| Polymarket | Écart achat/vente | 3 à 5 points | 4 136 / 292 | −0,04 [−0,20 ; +0,10] |
| Polymarket | Écart achat/vente | 5 à 8 points (hors filtre) | 1 647 / 131 | **+0,22 [+0,03 ; +0,42]** |
| Polymarket | Écart achat/vente | 8 à 12 points (hors filtre) | 359 / 74 | +0,36 [−0,20 ; +1,01] |
| Polymarket | Liquidité | 100 à 1 000 | 1 233 / 180 | −0,29 [−0,69 ; +0,10] |
| Polymarket | Liquidité | 1 000 à 3 000 | 3 616 / 289 | −0,05 [−0,26 ; +0,14] |
| Polymarket | Liquidité | 3 000 à 10 000 | 5 327 / 309 | −0,06 [−0,19 ; +0,07] |
| Polymarket | Liquidité | plus de 10 000 | 7 092 / 227 | **−0,16 [−0,25 ; −0,06]** |
| Polymarket | Âge du prix | moins de 6 minutes | 2 371 / 260 | **−0,21 [−0,44 ; −0,02]** |
| Polymarket | Âge du prix | 30 minutes à 2 h | 5 434 / 362 | **−0,16 [−0,28 ; −0,04]** |
| Polymarket | Âge du prix | 6 à 48 h | 1 416 / 185 | +0,06 [−0,10 ; +0,22] |
| Matchbook | Âge du prix | moins de 6 minutes | 3 117 / 133 | **−0,54 [−1,08 ; −0,11]** |
| Matchbook | Âge du prix | 2 à 6 h | 765 / 90 | **+0,47 [+0,09 ; +0,84]** |

- **Écart achat/vente** : le seuil de 5 points est au bon endroit. En dessous, Polymarket aide ou ne gêne pas ;
  au-dessus, il dégrade. C'est un seuil, pas une pente : un poids qui décroît avec l'écart n'apporte rien de plus.
- **Liquidité** : aucun effet dans le filtre, de 100 à plus de 10 000. Le minimum de 100 n'a pas à monter.
- **Fraîcheur** : un prix qui vient de bouger aide le plus, un prix figé depuis plus de 6 h n'aide plus, sans
  nuire sur Polymarket. Sur Matchbook, un prix figé depuis 2 à 6 h nuit (765 lignes, à confirmer).

### Qui pèse le plus ? Clôture d'une troisième source

Poids optimal de la deuxième source dans un mélange à deux, jugé par la clôture d'une source qui n'est pas dans le
mélange :

| Mélange | Clôture cible | Lignes / matchs | Poids de la 2e, IC 95 % |
|---|---|---|---|
| Polymarket + Matchbook | Pinnacle | 6 850 / 122 | 0,56 [0,39 ; 0,74] |
| Pinnacle + Polymarket | Matchbook | 6 652 / 122 | 0,94 [0,82 ; 1,07] |
| Pinnacle + Matchbook | Polymarket | 5 107 / 119 | 0,93 [0,82 ; 1,05] |
| Pinnacle + Polymarket | Smarkets | 5 456 / 118 | 0,94 [0,86 ; 1,02] |
| Pinnacle + Smarkets | Matchbook | 3 380 / 41 | 0,61 [0,42 ; 0,85] |

- **Polymarket et Matchbook se valent** : poids égaux, jugés par Pinnacle. C'est la seule ligne neutre.
- Les bourses se prédisent entre elles bien mieux que Pinnacle ne les prédit (poids de 0,9 pour la bourse). Cela
  ne prouve pas qu'elles ont raison : elles partagent une part de prix que notre lecture de Pinnacle (marge de 6 à
  7 % à retirer) n'a pas, et les résultats ci-dessous disent le contraire.

### Résultats réels

Paris réglés où Pinnacle et une autre source cotaient le même pari à la détection (champs `ecart_pinnacle`,
`ecart_polymarket` avant le 08/11, composantes du Consensus). Échantillon sélectionné : le pari existe parce
qu'une des sources l'a jugé gagnant.

| Autre source | Pari dans la table de | Paris / matchs | Gagnés | Pinnacle annonce | L'autre annonce | Autre − Pinnacle (log-loss ×10⁴) | Moyenne − Pinnacle |
|---|---|---|---|---|---|---|---|
| Polymarket | toutes | 692 / 415 | 48,7 % | 48,2 % | 48,1 % | +60 [−2 ; +126] | +23 [−8 ; +54] |
| Polymarket | Pinnacle, pas Polymarket | 212 / 156 | 53,3 % | 52,4 % | 50,0 % | +25 [−98 ; +142] | +6 [−56 ; +64] |
| Polymarket | Polymarket, pas Pinnacle | 149 / 107 | 39,6 % | 42,3 % | 45,4 % | **+221 [+37 ; +409]** | **+93 [+10 ; +182]** |
| Polymarket | les deux | 319 / 220 | 51,1 % | 48,5 % | 48,6 % | +26 [−28 ; +82] | +11 [−15 ; +37] |
| Matchbook | toutes | 139 / 92 | 41,0 % | 38,8 % | 39,7 % | **+93 [+14 ; +175]** | **+45 [+6 ; +87]** |

- Quand Pinnacle voit un avantage que Polymarket ne voit pas, le pari gagne 53,3 % du temps : Pinnacle annonçait
  52,4 %, Polymarket 50,0 %.
- Quand Polymarket voit un avantage que Pinnacle ne voit pas, le pari gagne 39,6 % du temps : Pinnacle annonçait
  42,3 %, Polymarket 45,4 %.
- Dans les deux sens Pinnacle est le plus près. La moyenne ne fait pas mieux que Pinnacle seul, sans que l'écart
  soit significatif sur l'ensemble.

### Ce que cela donne

La clôture dit « la moyenne vaut au moins Pinnacle » ; les résultats disent « Pinnacle vaut au moins la moyenne ».
Les deux sont compatibles avec le poids égal actuel, et aucun ne justifie de le déplacer. La pondération par
fraîcheur, liquidité et écart échoue hors échantillon ; les filtres par seuil suffisent.

### DraftKings

Les cotes de DraftKings (matchs NBA, NHL, NFL et props) sont lues à chaque cycle mais seul un résumé est gardé
(`props_papier.json` : écart moyen avec Pinnacle de 0,6 point sur 66 lignes de match). Sans historique, aucun
poids ne peut être mesuré.

## Limites

- **Football seulement** pour les grands échantillons : pas de tennis ni de basket (tennis-data.co.uk refuse les
  lectures automatiques). Le football n'a pas de marché à deux issues très déséquilibré.
- **Marge** : les fichiers de football ont une marge Pinnacle de 3 %, notre lecture 5,5 à 7 %. bet365 (6 %) sert
  d'équivalent, sans être Pinnacle.
- **`references/` a trois jours** : 496 matchs pour le consensus, 60 matchs réglés pour la marge.
- **Clôture et non résultat** pour le consensus : les deux cibles encadrent la vérité sans la donner.
- **Paris réglés** : échantillon choisi par les méthodes mêmes qu'on juge.
- **Fraîcheur** : âge du prix seulement ; l'âge de la lecture n'est pas dans l'historique.
- **Association des matchs** entre Pinnacle et les bourses refaite pour l'étude avec la règle du site. Contrôle
  fait à part sur les données du 14/11 à 00:20 : 522 de ces matchs étaient déjà reliés par le site, tous au même
  match.

## Décisions proposées

1. Garder la méthode puissance et la moyenne simple du consensus, avec les filtres actuels.
2. Relancer `scripts/cote_juste.py` vers le 05/12 : les marchés à deux issues et l'ajout de Matchbook seront
   tranchés par les résultats, pas par la clôture.
3. Enregistrer les cotes de DraftKings dans `references/`, comme les autres références : sans cela il ne sera
   jamais pesé.
4. Se méfier des écarts sur les cotes supérieures à 10 : la cote juste y est trop basse, quelle que soit la méthode.
5. Ne pas élargir le filtre Polymarket au-delà de 5 points d'écart achat/vente.

## Reproduire

Fichiers de football (330 requêtes, 40 Mo) :

```bash
mkdir -p football && for s in 1213 1314 1415 1516 1617 1718 1819 1920 2021 2122 2223 2324 2425 2526 2627; do for d in E0 E1 E2 E3 EC SC0 SC1 SC2 SC3 D1 D2 I1 I2 SP1 SP2 F1 F2 N1 B1 P1 T1 G1; do curl -sSL -o "football/$s-$d.csv" "https://www.football-data.co.uk/mmz4281/$s/$d.csv"; sleep 0.2; done; done
```

Branche `donnees` entière (le clone partiel de `scripts/cloner_donnees.sh` ne suffit pas) :

```bash
git clone --depth 1 --branch donnees https://github.com/Matttgic/cotes-value donnees
```

```bash
python scripts/cote_juste.py marge --football football --donnees donnees
```

```bash
python scripts/cote_juste.py consensus --donnees donnees
```

Demande numpy (`requirements-dev.txt`). Deux minutes pour le football, une minute pour chaque partie sur les
données du site. Les données changent toutes les heures : pour retrouver ces chiffres, se placer sur le commit
`f13913e` de `donnees`.
