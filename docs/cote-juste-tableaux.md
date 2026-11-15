# Cote juste : tableaux complets

Sortie de `scripts/cote_juste.py` du 14/11/2026 (2 000 tirages, graine fixe). Football : 330 fichiers de
football-data.co.uk, 22 divisions, saisons 2012/13 à 2026/27. Données du site : branche `donnees`, commit `f13913e`
(14/11/2026, 11:38 UTC). Lecture et conclusions : [cote-juste.md](cote-juste.md).

Écarts de log-loss et d'erreur : négatif = mieux que la référence ; en gras quand l'intervalle à 95 % exclut zéro.
« Pente de calibration » : 1 = calibré, plus de 1 = les favoris gagnent plus souvent qu'annoncé.

## Football : cotes et résultats de football-data.co.uk

### Pinnacle · 1N2 · avant-match : 101874 matchs, saisons 1213 à 2526, marge moyenne 3,34 %

| Méthode | Log-loss | Brier | Écart de log-loss avec la puissance ×10⁴, IC 95 % | Pente de calibration ± IC | Marchés à probabilité ≤ 0 |
|---|---|---|---|---|---|
| Multiplicative | 1,00427 | 0,60080 | **+2,45 [+1,35 ; +3,50]** | 1,051 ± 0,016 | 0 |
| Additive | 1,00404 | 0,60069 | +0,15 [-0,07 ; +0,39] | 1,011 ± 0,015 | 0 |
| Puissance (actuelle) | 1,00403 | 0,60068 | référence | 1,009 ± 0,015 | 0 |
| Shin | 1,00408 | 0,60070 | **+0,46 [+0,10 ; +0,81]** | 1,021 ± 0,016 | 0 |
| Odds ratio | 1,00408 | 0,60070 | **+0,56 [+0,10 ; +0,99]** | 1,025 ± 0,016 | 0 |

Courbe de calibration (toutes issues) : probabilité annoncée moyenne → fréquence observée, en %.

| Tranche (puissance) | Issues | Observée ± IC | Multiplicative | Additive | Puissance (actuelle) | Shin | Odds ratio |
|---|---|---|---|---|---|---|---|
| 0 à 5 % | 1568 | 3,06 ± 0,85 | 4,03 | 3,72 | 3,79 | 3,82 | 3,91 |
| 5 à 10 % | 6178 | 7,51 ± 0,66 | 7,83 | 7,83 | 7,82 | 7,83 | 7,82 |
| 10 à 15 % | 11982 | 12,44 ± 0,59 | 12,77 | 12,75 | 12,73 | 12,75 | 12,73 |
| 15 à 20 % | 21004 | 17,66 ± 0,52 | 17,73 | 17,71 | 17,71 | 17,71 | 17,71 |
| 20 à 30 % | 120806 | 26,03 ± 0,25 | 26,09 | 26,01 | 26,01 | 26,03 | 26,04 |
| 30 à 40 % | 63922 | 34,15 ± 0,37 | 34,07 | 34,09 | 34,09 | 34,09 | 34,08 |
| 40 à 50 % | 38776 | 44,43 ± 0,49 | 44,63 | 44,65 | 44,65 | 44,65 | 44,64 |
| 50 à 60 % | 22183 | 54,59 ± 0,66 | 54,51 | 54,53 | 54,53 | 54,53 | 54,52 |
| 60 à 70 % | 10980 | 64,13 ± 0,90 | 64,39 | 64,38 | 64,38 | 64,38 | 64,38 |
| 70 à 80 % | 5490 | 75,79 ± 1,13 | 74,38 | 74,39 | 74,39 | 74,40 | 74,40 |
| 80 à 90 % | 2455 | 85,21 ± 1,40 | 83,60 | 83,86 | 83,91 | 83,81 | 83,81 |
| 90 à 100 % | 278 | 91,01 ± 3,36 | 91,36 | 91,63 | 91,81 | 91,53 | 91,56 |

Favori à 75 % ou plus (4170 matchs) :

| Méthode | Log-loss | Brier | Écart de log-loss avec la puissance ×10⁴, IC 95 % | Pente de calibration ± IC | Marchés à probabilité ≤ 0 |
|---|---|---|---|---|---|
| Multiplicative | 0,53708 | 0,27956 | **+33,45 [+17,44 ; +49,71]** | 1,118 ± 0,041 | 0 |
| Additive | 0,53398 | 0,27828 | +2,38 [-2,35 ; +6,80] | 1,057 ± 0,039 | 0 |
| Puissance (actuelle) | 0,53374 | 0,27814 | référence | 1,050 ± 0,038 | 0 |
| Shin | 0,53453 | 0,27852 | **+7,95 [+1,81 ; +14,10]** | 1,073 ± 0,039 | 0 |
| Odds ratio | 0,53466 | 0,27849 | **+9,24 [+3,03 ; +15,27]** | 1,075 ± 0,039 | 0 |

### Pinnacle · 1N2 · clôture : 101468 matchs, saisons 1213 à 2526, marge moyenne 3,01 %

| Méthode | Log-loss | Brier | Écart de log-loss avec la puissance ×10⁴, IC 95 % | Pente de calibration ± IC | Marchés à probabilité ≤ 0 |
|---|---|---|---|---|---|
| Multiplicative | 1,00018 | 0,59809 | **+2,16 [+1,16 ; +3,21]** | 1,053 ± 0,016 | 0 |
| Additive | 0,99996 | 0,59798 | -0,06 [-0,33 ; +0,19] | 1,015 ± 0,015 | 0 |
| Puissance (actuelle) | 0,99997 | 0,59798 | référence | 1,013 ± 0,015 | 0 |
| Shin | 1,00000 | 0,59800 | +0,27 [-0,10 ; +0,63] | 1,024 ± 0,015 | 0 |
| Odds ratio | 1,00002 | 0,59800 | **+0,54 [+0,14 ; +0,93]** | 1,028 ± 0,015 | 0 |

Courbe de calibration (toutes issues) : probabilité annoncée moyenne → fréquence observée, en %.

| Tranche (puissance) | Issues | Observée ± IC | Multiplicative | Additive | Puissance (actuelle) | Shin | Odds ratio |
|---|---|---|---|---|---|---|---|
| 0 à 5 % | 1840 | 2,93 ± 0,77 | 3,93 | 3,58 | 3,66 | 3,69 | 3,79 |
| 5 à 10 % | 6607 | 7,08 ± 0,62 | 7,85 | 7,85 | 7,83 | 7,85 | 7,86 |
| 10 à 15 % | 12606 | 12,60 ± 0,58 | 12,75 | 12,75 | 12,74 | 12,75 | 12,75 |
| 15 à 20 % | 21564 | 17,76 ± 0,51 | 17,72 | 17,72 | 17,72 | 17,72 | 17,72 |
| 20 à 30 % | 117144 | 25,91 ± 0,25 | 26,07 | 26,01 | 26,01 | 26,03 | 26,03 |
| 30 à 40 % | 64824 | 34,15 ± 0,37 | 33,98 | 34,00 | 34,00 | 34,00 | 34,00 |
| 40 à 50 % | 37927 | 44,78 ± 0,50 | 44,61 | 44,64 | 44,64 | 44,63 | 44,63 |
| 50 à 60 % | 21975 | 54,07 ± 0,66 | 54,55 | 54,58 | 54,58 | 54,57 | 54,57 |
| 60 à 70 % | 11197 | 64,50 ± 0,89 | 64,39 | 64,40 | 64,41 | 64,41 | 64,41 |
| 70 à 80 % | 5637 | 76,57 ± 1,11 | 74,38 | 74,36 | 74,36 | 74,35 | 74,36 |
| 80 à 90 % | 2722 | 84,79 ± 1,35 | 83,82 | 84,08 | 84,10 | 84,00 | 83,99 |
| 90 à 100 % | 361 | 91,41 ± 2,89 | 91,48 | 91,86 | 92,03 | 91,84 | 91,87 |

Favori à 75 % ou plus (4605 matchs) :

| Méthode | Log-loss | Brier | Écart de log-loss avec la puissance ×10⁴, IC 95 % | Pente de calibration ± IC | Marchés à probabilité ≤ 0 |
|---|---|---|---|---|---|
| Multiplicative | 0,53983 | 0,28212 | **+20,24 [+4,75 ; +35,38]** | 1,097 ± 0,038 | 0 |
| Additive | 0,53763 | 0,28131 | -1,79 [-6,76 ; +3,14] | 1,040 ± 0,036 | 0 |
| Puissance (actuelle) | 0,53781 | 0,28128 | référence | 1,034 ± 0,036 | 0 |
| Shin | 0,53800 | 0,28144 | +1,96 [-4,77 ; +8,09] | 1,055 ± 0,037 | 0 |
| Odds ratio | 0,53833 | 0,28147 | +5,25 [-0,70 ; +10,83] | 1,057 ± 0,037 | 0 |

### Pinnacle · Total 2,5 buts · avant-match : 48309 matchs, saisons 1920 à 2526, marge moyenne 3,96 %

| Méthode | Log-loss | Brier | Écart de log-loss avec la puissance ×10⁴, IC 95 % | Pente de calibration ± IC | Marchés à probabilité ≤ 0 |
|---|---|---|---|---|---|
| Multiplicative | 0,67699 | 0,48412 | +0,90 [-0,16 ; +1,85] | 1,089 ± 0,055 | 0 |
| Additive | 0,67692 | 0,48405 | +0,17 [-0,19 ; +0,49] | 1,043 ± 0,053 | 0 |
| Puissance (actuelle) | 0,67690 | 0,48404 | référence | 1,020 ± 0,052 | 0 |
| Shin | 0,67692 | 0,48405 | +0,17 [-0,18 ; +0,52] | 1,043 ± 0,053 | 0 |
| Odds ratio | 0,67691 | 0,48405 | +0,14 [-0,17 ; +0,45] | 1,040 ± 0,053 | 0 |

Favori à 65 % ou plus (3194 matchs) :

| Méthode | Log-loss | Brier | Écart de log-loss avec la puissance ×10⁴, IC 95 % | Pente de calibration ± IC | Marchés à probabilité ≤ 0 |
|---|---|---|---|---|---|
| Multiplicative | 0,61053 | 0,42028 | +5,04 [-4,52 ; +15,09] | 1,084 ± 0,097 | 0 |
| Additive | 0,61012 | 0,41999 | +0,91 [-2,70 ; +4,37] | 1,032 ± 0,093 | 0 |
| Puissance (actuelle) | 0,61002 | 0,41995 | référence | 1,006 ± 0,090 | 0 |
| Shin | 0,61012 | 0,41999 | +0,91 [-2,63 ; +4,30] | 1,032 ± 0,093 | 0 |
| Odds ratio | 0,61009 | 0,41998 | +0,70 [-2,28 ; +3,61] | 1,029 ± 0,092 | 0 |

### Pinnacle · Total 2,5 buts · clôture : 48504 matchs, saisons 1920 à 2526, marge moyenne 3,59 %

| Méthode | Log-loss | Brier | Écart de log-loss avec la puissance ×10⁴, IC 95 % | Pente de calibration ± IC | Marchés à probabilité ≤ 0 |
|---|---|---|---|---|---|
| Multiplicative | 0,67463 | 0,48185 | +0,83 [-0,23 ; +1,80] | 1,070 ± 0,051 | 0 |
| Additive | 0,67457 | 0,48180 | +0,16 [-0,18 ; +0,51] | 1,027 ± 0,049 | 0 |
| Puissance (actuelle) | 0,67455 | 0,48179 | référence | 1,006 ± 0,048 | 0 |
| Shin | 0,67457 | 0,48180 | +0,16 [-0,19 ; +0,53] | 1,027 ± 0,049 | 0 |
| Odds ratio | 0,67456 | 0,48179 | +0,12 [-0,19 ; +0,43] | 1,025 ± 0,049 | 0 |

Courbe de calibration (toutes issues) : probabilité annoncée moyenne → fréquence observée, en %.

| Tranche (puissance) | Issues | Observée ± IC | Multiplicative | Additive | Puissance (actuelle) | Shin | Odds ratio |
|---|---|---|---|---|---|---|---|
| 10 à 15 % | 32 | 0,00 ± 0,00 | 13,76 | 13,53 | 13,01 | 13,53 | 13,50 |
| 15 à 20 % | 79 | 21,52 ± 9,06 | 17,92 | 17,82 | 17,67 | 17,82 | 17,81 |
| 20 à 30 % | 1575 | 27,81 ± 2,21 | 27,45 | 27,30 | 27,21 | 27,30 | 27,31 |
| 30 à 40 % | 12385 | 36,25 ± 0,85 | 36,45 | 36,37 | 36,31 | 36,37 | 36,37 |
| 40 à 50 % | 33915 | 45,25 ± 0,53 | 45,38 | 45,35 | 45,32 | 45,35 | 45,34 |
| 50 à 60 % | 34951 | 54,61 ± 0,52 | 54,49 | 54,52 | 54,55 | 54,52 | 54,52 |
| 60 à 70 % | 12385 | 63,75 ± 0,85 | 63,55 | 63,63 | 63,69 | 63,63 | 63,63 |
| 70 à 80 % | 1575 | 72,19 ± 2,21 | 72,53 | 72,70 | 72,79 | 72,70 | 72,68 |
| 80 à 90 % | 111 | 84,68 ± 6,70 | 82,54 | 83,19 | 83,67 | 83,19 | 83,27 |

Favori à 65 % ou plus (4469 matchs) :

| Méthode | Log-loss | Brier | Écart de log-loss avec la puissance ×10⁴, IC 95 % | Pente de calibration ± IC | Marchés à probabilité ≤ 0 |
|---|---|---|---|---|---|
| Multiplicative | 0,60910 | 0,41897 | +4,46 [-2,83 ; +12,18] | 1,072 ± 0,081 | 0 |
| Additive | 0,60874 | 0,41871 | +0,81 [-1,95 ; +3,58] | 1,024 ± 0,077 | 0 |
| Puissance (actuelle) | 0,60866 | 0,41868 | référence | 1,000 ± 0,075 | 0 |
| Shin | 0,60874 | 0,41871 | +0,81 [-1,81 ; +3,64] | 1,024 ± 0,077 | 0 |
| Odds ratio | 0,60872 | 0,41870 | +0,63 [-1,90 ; +2,98] | 1,021 ± 0,077 | 0 |

### Pinnacle · Handicap asiatique · avant-match : 19689 matchs, saisons 1920 à 2526, marge moyenne 3,15 %

| Méthode | Log-loss | Brier | Écart de log-loss avec la puissance ×10⁴, IC 95 % | Pente de calibration ± IC | Marchés à probabilité ≤ 0 |
|---|---|---|---|---|---|
| Multiplicative | 0,69164 | 0,49850 | +0,12 [-0,23 ; +0,47] | 1,148 ± 0,291 | 0 |
| Additive | 0,69163 | 0,49849 | +0,03 [-0,09 ; +0,15] | 1,110 ± 0,281 | 0 |
| Puissance (actuelle) | 0,69163 | 0,49849 | référence | 1,093 ± 0,277 | 0 |
| Shin | 0,69163 | 0,49849 | +0,03 [-0,08 ; +0,15] | 1,110 ± 0,281 | 0 |
| Odds ratio | 0,69163 | 0,49849 | +0,03 [-0,08 ; +0,14] | 1,109 ± 0,281 | 0 |

### Pinnacle · Handicap asiatique · clôture : 19591 matchs, saisons 1920 à 2526, marge moyenne 2,78 %

| Méthode | Log-loss | Brier | Écart de log-loss avec la puissance ×10⁴, IC 95 % | Pente de calibration ± IC | Marchés à probabilité ≤ 0 |
|---|---|---|---|---|---|
| Multiplicative | 0,69262 | 0,49946 | **-0,39 [-0,73 ; -0,07]** | 0,704 ± 0,275 | 0 |
| Additive | 0,69264 | 0,49949 | **-0,14 [-0,25 ; -0,02]** | 0,683 ± 0,267 | 0 |
| Puissance (actuelle) | 0,69266 | 0,49950 | référence | 0,673 ± 0,264 | 0 |
| Shin | 0,69264 | 0,49949 | **-0,14 [-0,24 ; -0,02]** | 0,683 ± 0,267 | 0 |
| Odds ratio | 0,69264 | 0,49949 | **-0,13 [-0,23 ; -0,03]** | 0,683 ± 0,267 | 0 |

Courbe de calibration (toutes issues) : probabilité annoncée moyenne → fréquence observée, en %.

| Tranche (puissance) | Issues | Observée ± IC | Multiplicative | Additive | Puissance (actuelle) | Shin | Odds ratio |
|---|---|---|---|---|---|---|---|
| 15 à 20 % | 1 | 100,00 ± 0,01 | 19,11 | 18,18 | 17,67 | 18,18 | 18,13 |
| 20 à 30 % | 2 | 50,00 ± 69,30 | 24,86 | 24,26 | 26,97 | 24,26 | 24,24 |
| 30 à 40 % | 15 | 46,67 ± 25,25 | 37,96 | 37,67 | 38,42 | 37,67 | 37,65 |
| 40 à 50 % | 18950 | 48,26 ± 0,71 | 47,85 | 47,79 | 47,76 | 47,79 | 47,79 |
| 50 à 60 % | 20196 | 51,63 ± 0,69 | 52,02 | 52,07 | 52,10 | 52,07 | 52,07 |
| 60 à 70 % | 15 | 53,33 ± 25,25 | 62,04 | 62,33 | 61,58 | 62,33 | 62,35 |
| 70 à 80 % | 2 | 50,00 ± 69,30 | 75,14 | 75,74 | 73,03 | 75,74 | 75,76 |
| 80 à 90 % | 1 | 0,00 ± 0,01 | 80,89 | 81,82 | 82,33 | 81,82 | 81,87 |

### bet365 · 1N2 · avant-match : 110018 matchs, saisons 1213 à 2627, marge moyenne 6,05 %

| Méthode | Log-loss | Brier | Écart de log-loss avec la puissance ×10⁴, IC 95 % | Pente de calibration ± IC | Marchés à probabilité ≤ 0 |
|---|---|---|---|---|---|
| Multiplicative | 1,00333 | 0,60008 | **+4,80 [+2,88 ; +6,60]** | 1,069 ± 0,015 | 0 |
| Additive | 1,00289 | 0,59985 | +0,37 [-0,05 ; +0,78] | 0,997 ± 0,015 | 1 |
| Puissance (actuelle) | 1,00285 | 0,59983 | référence | 0,994 ± 0,014 | 0 |
| Shin | 1,00292 | 0,59986 | **+0,68 [+0,03 ; +1,31]** | 1,016 ± 0,015 | 0 |
| Odds ratio | 1,00291 | 0,59985 | +0,65 [-0,10 ; +1,35] | 1,022 ± 0,015 | 0 |

Favori à 75 % ou plus (4348 matchs) :

| Méthode | Log-loss | Brier | Écart de log-loss avec la puissance ×10⁴, IC 95 % | Pente de calibration ± IC | Marchés à probabilité ≤ 0 |
|---|---|---|---|---|---|
| Multiplicative | 0,53367 | 0,27721 | **+61,81 [+36,61 ; +87,81]** | 1,147 ± 0,041 | 0 |
| Additive | 0,52781 | 0,27483 | +3,22 [-5,57 ; +11,99] | 1,041 ± 0,037 | 1 |
| Puissance (actuelle) | 0,52749 | 0,27463 | référence | 1,028 ± 0,037 | 0 |
| Shin | 0,52868 | 0,27519 | **+11,93 [+1,00 ; +22,72]** | 1,070 ± 0,038 | 0 |
| Odds ratio | 0,52888 | 0,27511 | **+13,92 [+4,12 ; +24,04]** | 1,070 ± 0,038 | 0 |

### bet365 · 1N2 · clôture : 55663 matchs, saisons 1920 à 2627, marge moyenne 6,62 %

| Méthode | Log-loss | Brier | Écart de log-loss avec la puissance ×10⁴, IC 95 % | Pente de calibration ± IC | Marchés à probabilité ≤ 0 |
|---|---|---|---|---|---|
| Multiplicative | 0,99894 | 0,59690 | **+5,57 [+2,88 ; +8,34]** | 1,076 ± 0,021 | 0 |
| Additive | 0,99839 | 0,59662 | +0,09 [-0,55 ; +0,70] | 0,999 ± 0,020 | 0 |
| Puissance (actuelle) | 0,99838 | 0,59661 | référence | 0,994 ± 0,020 | 0 |
| Shin | 0,99844 | 0,59664 | +0,58 [-0,43 ; +1,58] | 1,019 ± 0,020 | 0 |
| Odds ratio | 0,99847 | 0,59663 | +0,82 [-0,27 ; +1,96] | 1,025 ± 0,020 | 0 |

Favori à 75 % ou plus (2181 matchs) :

| Méthode | Log-loss | Brier | Écart de log-loss avec la puissance ×10⁴, IC 95 % | Pente de calibration ± IC | Marchés à probabilité ≤ 0 |
|---|---|---|---|---|---|
| Multiplicative | 0,54179 | 0,28233 | **+55,76 [+16,56 ; +93,92]** | 1,132 ± 0,056 | 0 |
| Additive | 0,53623 | 0,28019 | +0,16 [-12,53 ; +12,71] | 1,025 ± 0,052 | 0 |
| Puissance (actuelle) | 0,53621 | 0,28012 | référence | 1,009 ± 0,051 | 0 |
| Shin | 0,53702 | 0,28048 | +8,08 [-8,27 ; +24,57] | 1,053 ± 0,053 | 0 |
| Odds ratio | 0,53732 | 0,28045 | +11,09 [-3,61 ; +25,71] | 1,052 ± 0,053 | 0 |

### bet365 · Total 2,5 buts · avant-match : 55567 matchs, saisons 1920 à 2627, marge moyenne 5,57 %

| Méthode | Log-loss | Brier | Écart de log-loss avec la puissance ×10⁴, IC 95 % | Pente de calibration ± IC | Marchés à probabilité ≤ 0 |
|---|---|---|---|---|---|
| Multiplicative | 0,67703 | 0,48417 | **+1,57 [+0,27 ; +2,83]** | 1,108 ± 0,053 | 0 |
| Additive | 0,67690 | 0,48405 | +0,28 [-0,17 ; +0,74] | 1,042 ± 0,049 | 0 |
| Puissance (actuelle) | 0,67687 | 0,48403 | référence | 1,010 ± 0,048 | 0 |
| Shin | 0,67690 | 0,48405 | +0,28 [-0,16 ; +0,73] | 1,042 ± 0,049 | 0 |
| Odds ratio | 0,67689 | 0,48405 | +0,22 [-0,20 ; +0,63] | 1,038 ± 0,049 | 0 |

Favori à 65 % ou plus (3962 matchs) :

| Méthode | Log-loss | Brier | Écart de log-loss avec la puissance ×10⁴, IC 95 % | Pente de calibration ± IC | Marchés à probabilité ≤ 0 |
|---|---|---|---|---|---|
| Multiplicative | 0,60913 | 0,41899 | +5,96 [-4,63 ; +16,49] | 1,081 ± 0,087 | 0 |
| Additive | 0,60861 | 0,41860 | +0,76 [-3,25 ; +4,75] | 1,017 ± 0,081 | 0 |
| Puissance (actuelle) | 0,60853 | 0,41857 | référence | 0,984 ± 0,079 | 0 |
| Shin | 0,60861 | 0,41860 | +0,76 [-3,22 ; +4,90] | 1,017 ± 0,081 | 0 |
| Odds ratio | 0,60858 | 0,41858 | +0,48 [-3,12 ; +4,23] | 1,013 ± 0,081 | 0 |

### bet365 · Total 2,5 buts · clôture : 55652 matchs, saisons 1920 à 2627, marge moyenne 5,59 %

| Méthode | Log-loss | Brier | Écart de log-loss avec la puissance ×10⁴, IC 95 % | Pente de calibration ± IC | Marchés à probabilité ≤ 0 |
|---|---|---|---|---|---|
| Multiplicative | 0,67448 | 0,48172 | +1,32 [-0,10 ; +2,76] | 1,085 ± 0,048 | 0 |
| Additive | 0,67436 | 0,48161 | +0,14 [-0,37 ; +0,64] | 1,021 ± 0,045 | 0 |
| Puissance (actuelle) | 0,67435 | 0,48160 | référence | 0,989 ± 0,044 | 0 |
| Shin | 0,67436 | 0,48161 | +0,14 [-0,38 ; +0,64] | 1,021 ± 0,045 | 0 |
| Odds ratio | 0,67436 | 0,48161 | +0,09 [-0,32 ; +0,54] | 1,017 ± 0,045 | 0 |

Favori à 65 % ou plus (5492 matchs) :

| Méthode | Log-loss | Brier | Écart de log-loss avec la puissance ×10⁴, IC 95 % | Pente de calibration ± IC | Marchés à probabilité ≤ 0 |
|---|---|---|---|---|---|
| Multiplicative | 0,60708 | 0,41703 | +4,25 [-5,58 ; +13,39] | 1,074 ± 0,072 | 0 |
| Additive | 0,60666 | 0,41670 | +0,01 [-3,71 ; +3,64] | 1,010 ± 0,068 | 0 |
| Puissance (actuelle) | 0,60666 | 0,41672 | référence | 0,977 ± 0,066 | 0 |
| Shin | 0,60666 | 0,41670 | +0,01 [-3,51 ; +3,64] | 1,010 ± 0,068 | 0 |
| Odds ratio | 0,60664 | 0,41669 | -0,15 [-3,23 ; +2,84] | 1,005 ± 0,068 | 0 |

### bet365 · Handicap asiatique · avant-match : 22722 matchs, saisons 1920 à 2627, marge moyenne 3,91 %

| Méthode | Log-loss | Brier | Écart de log-loss avec la puissance ×10⁴, IC 95 % | Pente de calibration ± IC | Marchés à probabilité ≤ 0 |
|---|---|---|---|---|---|
| Multiplicative | 0,69182 | 0,49868 | +0,19 [-0,32 ; +0,74] | 1,094 ± 0,277 | 0 |
| Additive | 0,69182 | 0,49867 | +0,09 [-0,12 ; +0,34] | 1,047 ± 0,264 | 0 |
| Puissance (actuelle) | 0,69181 | 0,49867 | référence | 1,023 ± 0,258 | 0 |
| Shin | 0,69182 | 0,49867 | +0,09 [-0,12 ; +0,35] | 1,047 ± 0,264 | 0 |
| Odds ratio | 0,69181 | 0,49867 | +0,03 [-0,12 ; +0,19] | 1,045 ± 0,263 | 0 |

### bet365 · Handicap asiatique · clôture : 22706 matchs, saisons 1920 à 2627, marge moyenne 3,91 %

| Méthode | Log-loss | Brier | Écart de log-loss avec la puissance ×10⁴, IC 95 % | Pente de calibration ± IC | Marchés à probabilité ≤ 0 |
|---|---|---|---|---|---|
| Multiplicative | 0,69271 | 0,49955 | **-0,69 [-1,18 ; -0,17]** | 0,676 ± 0,262 | 0 |
| Additive | 0,69275 | 0,49959 | **-0,25 [-0,42 ; -0,09]** | 0,645 ± 0,251 | 0 |
| Puissance (actuelle) | 0,69278 | 0,49962 | référence | 0,630 ± 0,245 | 0 |
| Shin | 0,69275 | 0,49959 | **-0,25 [-0,44 ; -0,08]** | 0,645 ± 0,251 | 0 |
| Odds ratio | 0,69276 | 0,49960 | **-0,23 [-0,38 ; -0,08]** | 0,643 ± 0,250 | 0 |

## Données du site : enjeu par type de marché (marchés Pinnacle de references/)

Écart : |cote juste de la méthode / cote juste « puissance » − 1|, par issue.

| Type | Marchés | Marge médiane | Marge, 9e décile | Favori ≥ 75 % | Multiplicative : médiane · 95e centile · part > 2 % | Additive : médiane · 95e centile · part > 2 % | Shin : médiane · 95e centile · part > 2 % | Odds ratio : médiane · 95e centile · part > 2 % |
|---|---|---|---|---|---|---|---|---|
| 1N2 | 2792 | 7,13 % | 10,65 % | 5 % | 2,35 % · 13,5 % · 56 % | 0,21 % · 3,3 % · 8 % | 0,55 % · 4,7 % · 15 % | 0,94 % · 6,0 % · 21 % |
| Deux issues | 5227 | 5,46 % | 9,45 % | 24 % | 2,31 % · 22,4 % · 55 % | 0,82 % · 10,4 % · 24 % | 0,82 % · 10,4 % · 24 % | 0,71 % · 8,1 % · 19 % |
| Totaux | 56904 | 6,88 % | 9,10 % | 4 % | 1,47 % · 7,6 % · 39 % | 0,52 % · 3,0 % · 10 % | 0,52 % · 3,0 % · 10 % | 0,45 % · 2,4 % · 7 % |
| Handicaps | 45975 | 6,94 % | 9,25 % | 6 % | 1,77 % · 9,0 % · 45 % | 0,62 % · 3,5 % · 13 % | 0,62 % · 3,5 % · 13 % | 0,54 % · 2,9 % · 10 % |
| Props joueurs | 2451 | 6,96 % | 7,11 % | 4 % | 0,96 % · 7,3 % · 28 % | 0,34 % · 2,8 % · 7 % | 0,34 % · 2,8 % · 7 % | 0,30 % · 2,3 % · 6 % |

## Données du site : marchés Pinnacle réglés (dernière cote avant le début, non sélectionnés)

### 1N2 : 54 marchés, 43 matchs, marge moyenne 6,75 %

| Méthode | Log-loss | Brier | Écart de log-loss avec la puissance ×10⁴, IC 95 % | Pente de calibration ± IC | Marchés à probabilité ≤ 0 |
|---|---|---|---|---|---|
| Multiplicative | 0,94384 | 0,56331 | -12,03 [-185,99 ; +127,45] | 1,017 ± 0,531 | 0 |
| Additive | 0,94430 | 0,56418 | -7,43 [-30,93 ; +12,21] | 0,934 ± 0,491 | 0 |
| Puissance (actuelle) | 0,94504 | 0,56456 | référence | 0,926 ± 0,487 | 0 |
| Shin | 0,94401 | 0,56385 | -10,29 [-63,31 ; +36,56] | 0,956 ± 0,501 | 0 |
| Odds ratio | 0,94453 | 0,56402 | -5,14 [-71,79 ; +46,94] | 0,959 ± 0,503 | 0 |

### Deux issues : 129 marchés, 60 matchs, marge moyenne 5,40 %

| Méthode | Log-loss | Brier | Écart de log-loss avec la puissance ×10⁴, IC 95 % | Pente de calibration ± IC | Marchés à probabilité ≤ 0 |
|---|---|---|---|---|---|
| Multiplicative | 0,60967 | 0,42013 | -115,38 [-344,57 ; +45,98] | 0,954 ± 0,454 | 0 |
| Additive | 0,61406 | 0,42165 | -71,41 [-202,75 ; +15,91] | 0,856 ± 0,415 | 0 |
| Puissance (actuelle) | 0,62120 | 0,42350 | référence | 0,777 ± 0,387 | 0 |
| Shin | 0,61406 | 0,42165 | -71,41 [-198,19 ; +13,41] | 0,856 ± 0,415 | 0 |
| Odds ratio | 0,61679 | 0,42245 | -44,10 [-121,79 ; +12,36] | 0,829 ± 0,407 | 0 |

### Totaux : 746 marchés, 63 matchs, marge moyenne 5,45 %

| Méthode | Log-loss | Brier | Écart de log-loss avec la puissance ×10⁴, IC 95 % | Pente de calibration ± IC | Marchés à probabilité ≤ 0 |
|---|---|---|---|---|---|
| Multiplicative | 0,66562 | 0,47401 | +0,76 [-21,07 ; +22,67] | 1,065 ± 0,346 | 0 |
| Additive | 0,66548 | 0,47394 | -0,66 [-9,82 ; +7,53] | 0,995 ± 0,323 | 0 |
| Puissance (actuelle) | 0,66554 | 0,47399 | référence | 0,957 ± 0,312 | 0 |
| Shin | 0,66548 | 0,47394 | -0,66 [-9,94 ; +7,61] | 0,995 ± 0,323 | 0 |
| Odds ratio | 0,66550 | 0,47395 | -0,43 [-7,33 ; +6,22] | 0,988 ± 0,321 | 0 |

### Handicaps : 631 marchés, 63 matchs, marge moyenne 5,39 %

| Méthode | Log-loss | Brier | Écart de log-loss avec la puissance ×10⁴, IC 95 % | Pente de calibration ± IC | Marchés à probabilité ≤ 0 |
|---|---|---|---|---|---|
| Multiplicative | 0,65679 | 0,46495 | -15,95 [-58,34 ; +18,43] | 0,948 ± 0,294 | 0 |
| Additive | 0,65754 | 0,46538 | -8,44 [-27,24 ; +6,27] | 0,875 ± 0,273 | 0 |
| Puissance (actuelle) | 0,65839 | 0,46582 | référence | 0,830 ± 0,262 | 0 |
| Shin | 0,65754 | 0,46538 | -8,44 [-26,70 ; +6,18] | 0,875 ± 0,273 | 0 |
| Odds ratio | 0,65772 | 0,46547 | -6,66 [-19,89 ; +4,77] | 0,865 ± 0,271 | 0 |

### Props joueurs : 0 marchés réglés, trop peu pour une mesure

## Données du site : chaque méthode face au prix des bourses, une heure avant le début

Divergence de Kullback-Leibler du prix de bourse vers la probabilité de la méthode, ×10⁴ ; écart avec la puissance et intervalle à 95 % par match. Dernière colonne : probabilité du favori selon la méthode moins celle de la bourse, en points.

| Bourse | Type | Marchés | Marchés / matchs | Puissance | Multiplicative − puissance | Additive − puissance | Shin − puissance | Odds ratio − puissance | Favori : Multiplicative · Additive · Puissance · Shin · Odds |
|---|---|---|---|---|---|---|---|---|---|
| Matchbook | 1N2 | tous | 89 / 83 | 5,10 | **+6,94 [+4,03 ; +9,81]** | **-1,08 [-2,40 ; -0,15]** | -1,32 [-3,49 ; +0,33] | -0,09 [-2,28 ; +1,58] | -1,36 · +0,07 · +0,23 · -0,30 · -0,36 |
| Matchbook | Deux issues | tous | 119 / 106 | 4,20 | +0,05 [-1,63 ; +1,75] | **-1,31 [-2,31 ; -0,56]** | **-1,31 [-2,24 ; -0,60]** | **-1,22 [-2,06 ; -0,61]** | -0,36 · +0,31 · +0,68 · +0,31 · +0,36 |
| Matchbook | Handicaps | tous | 305 / 65 | 2,81 | +0,48 [-0,26 ; +1,28] | **-0,70 [-1,00 ; -0,39]** | **-0,70 [-1,00 ; -0,40]** | **-0,67 [-0,92 ; -0,40]** | -0,57 · +0,09 · +0,45 · +0,09 · +0,14 |
| Matchbook | Totaux | tous | 167 / 71 | 2,93 | **+1,44 [+0,14 ; +2,77]** | **-1,64 [-2,18 ; -1,15]** | **-1,64 [-2,18 ; -1,13]** | **-1,57 [-2,06 ; -1,12]** | -0,79 · +0,12 · +0,64 · +0,12 · +0,20 |
| Polymarket | 1N2 | tous | 153 / 99 | 4,38 | **+6,18 [+4,04 ; +8,50]** | -0,50 [-1,44 ; +0,24] | **-0,96 [-2,12 ; -0,07]** | +0,22 [-0,88 ; +1,18] | -1,15 · +0,22 · +0,31 · -0,14 · -0,24 |
| Polymarket | Deux issues | tous | 525 / 454 | 6,41 | **-2,20 [-3,52 ; -0,90]** | **-2,50 [-3,16 ; -1,92]** | **-2,50 [-3,21 ; -1,90]** | **-2,26 [-2,80 ; -1,77]** | -0,24 · +0,46 · +0,85 · +0,46 · +0,51 |
| Polymarket | Deux issues | favori ≥ 75 % | 98 / 97 | 16,89 | -6,30 [-13,37 ; +0,54] | **-9,52 [-12,79 ; -6,68]** | **-9,52 [-12,56 ; -6,76]** | **-8,58 [-11,08 ; -6,41]** | -1,00 · +0,59 · +1,57 · +0,59 · +0,77 |
| Polymarket | Handicaps | tous | 503 / 260 | 1,57 | -0,09 [-0,40 ; +0,24] | **-0,53 [-0,69 ; -0,39]** | **-0,53 [-0,69 ; -0,38]** | **-0,49 [-0,64 ; -0,37]** | -0,20 · +0,18 · +0,38 · +0,18 · +0,20 |
| Polymarket | Totaux | tous | 1029 / 284 | 2,74 | **-0,39 [-0,71 ; -0,07]** | **-1,07 [-1,26 ; -0,87]** | **-1,07 [-1,27 ; -0,88]** | **-0,98 [-1,16 ; -0,81]** | -0,37 · +0,19 · +0,50 · +0,19 · +0,23 |
| Polymarket | Totaux | favori ≥ 75 % | 83 / 52 | 6,88 | +2,02 [-0,45 ; +4,67] | **-5,02 [-6,08 ; -3,95]** | **-5,02 [-6,07 ; -3,98]** | **-4,69 [-5,67 ; -3,74]** | -1,41 · +0,23 · +1,21 · +0,23 · +0,40 |

## Données du site : paris réglés de référence Pinnacle, marchés à deux issues (échantillon sélectionné)

Log-loss de l'issue jouée ; « gardés » : paris dont l'écart reste ≥ 2 % avec la méthode ; ROI à mise fixe.

### Deux issues : 410 paris, 365 matchs, 64,39 % gagnés

| Méthode | Log-loss | Écart avec la puissance ×10⁴, IC 95 % | Probabilité annoncée moyenne | Gardés | ROI des gardés en %, IC 95 % | Écartés | ROI des écartés en %, IC 95 % |
|---|---|---|---|---|---|---|---|
| Multiplicative | 0,56543 | +46,53 [-11,98 ; +97,53] | 61,73 % | 203 | +6,7 [-8,8 ; +23,5] | 207 | +3,3 [-5,2 ; +11,7] |
| Additive | 0,56228 | +15,03 [-8,80 ; +36,63] | 62,57 % | 275 | +5,9 [-6,4 ; +18,3] | 135 | +3,0 [-6,2 ; +11,8] |
| Puissance (actuelle) | 0,56078 | référence | 63,11 % | 409 | +4,9 [-4,0 ; +13,5] | 1 | — |
| Shin | 0,56228 | +15,03 [-10,02 ; +37,01] | 62,57 % | 275 | +5,9 [-7,0 ; +18,1] | 135 | +3,0 [-6,0 ; +12,2] |
| Odds ratio | 0,56187 | +10,90 [-7,74 ; +28,13] | 62,70 % | 287 | +5,5 [-5,9 ; +17,8] | 123 | +3,7 [-6,0 ; +12,7] |

### Totaux : 1065 paris, 629 matchs, 52,68 % gagnés

| Méthode | Log-loss | Écart avec la puissance ×10⁴, IC 95 % | Probabilité annoncée moyenne | Gardés | ROI des gardés en %, IC 95 % | Écartés | ROI des écartés en %, IC 95 % |
|---|---|---|---|---|---|---|---|
| Multiplicative | 0,67061 | -5,59 [-24,12 ; +12,79] | 55,35 % | 664 | -1,5 [-12,6 ; +9,8] | 401 | -2,4 [-10,7 ; +6,3] |
| Additive | 0,67089 | -2,81 [-10,09 ; +4,02] | 55,69 % | 829 | -0,7 [-10,6 ; +9,1] | 236 | -5,9 [-17,0 ; +4,5] |
| Puissance (actuelle) | 0,67117 | référence | 55,89 % | 1061 | -1,8 [-10,1 ; +6,2] | 4 | — |
| Shin | 0,67089 | -2,81 [-9,85 ; +4,39] | 55,69 % | 829 | -0,7 [-10,7 ; +9,7] | 236 | -5,9 [-16,3 ; +4,9] |
| Odds ratio | 0,67092 | -2,54 [-8,36 ; +3,16] | 55,73 % | 848 | -0,7 [-9,8 ; +8,9] | 217 | -6,5 [-18,2 ; +4,1] |

### Handicaps : 694 paris, 407 matchs, 53,17 % gagnés

| Méthode | Log-loss | Écart avec la puissance ×10⁴, IC 95 % | Probabilité annoncée moyenne | Gardés | ROI des gardés en %, IC 95 % | Écartés | ROI des écartés en %, IC 95 % |
|---|---|---|---|---|---|---|---|
| Multiplicative | 0,66665 | -5,27 [-31,05 ; +16,60] | 54,88 % | 458 | -1,1 [-14,8 ; +12,8] | 236 | +0,1 [-11,6 ; +11,1] |
| Additive | 0,66684 | -3,45 [-13,77 ; +5,22] | 55,20 % | 578 | +1,4 [-10,4 ; +12,5] | 116 | -10,8 [-26,5 ; +4,2] |
| Puissance (actuelle) | 0,66718 | référence | 55,39 % | 691 | -0,8 [-10,9 ; +9,4] | 3 | — |
| Shin | 0,66684 | -3,45 [-13,66 ; +5,53] | 55,20 % | 578 | +1,4 [-10,8 ; +13,0] | 116 | -10,8 [-25,5 ; +3,6] |
| Odds ratio | 0,66692 | -2,59 [-10,57 ; +4,74] | 55,23 % | 589 | +1,3 [-9,2 ; +12,7] | 105 | -11,9 [-26,6 ; +3,0] |

### Tous : 2169 paris, 1194 matchs, 55,05 % gagnés

| Méthode | Log-loss | Écart avec la puissance ×10⁴, IC 95 % | Probabilité annoncée moyenne | Gardés | ROI des gardés en %, IC 95 % | Écartés | ROI des écartés en %, IC 95 % |
|---|---|---|---|---|---|---|---|
| Multiplicative | 0,64947 | +4,37 [-12,36 ; +20,15] | 56,41 % | 1325 | -0,1 [-8,2 ; +8,8] | 844 | -0,3 [-6,4 ; +5,4] |
| Additive | 0,64906 | +0,36 [-6,52 ; +6,82] | 56,84 % | 1682 | +1,1 [-5,5 ; +8,1] | 487 | -4,6 [-11,7 ; +2,2] |
| Puissance (actuelle) | 0,64903 | référence | 57,10 % | 2161 | -0,2 [-6,0 ; +5,9] | 8 | — |
| Shin | 0,64906 | +0,36 [-6,40 ; +6,57] | 56,84 % | 1682 | +1,1 [-5,7 ; +8,1] | 487 | -4,6 [-11,5 ; +2,7] |
| Odds ratio | 0,64903 | -0,01 [-5,39 ; +4,86] | 56,88 % | 1724 | +1,0 [-5,4 ; +7,8] | 445 | -5,0 [-12,4 ; +2,0] |

## Consensus : 496 matchs commencés du 12/11 03:10 au 14/11 11:30 UTC, 40107 lignes (pari × avance de 1, 3, 6, 12 h)

Ajustement : matchs commencés avant le 2026-11-13 12:00 UTC (245) ; test : après (251), dont 82 commencés après le gel de la méthode (2026-11-14 00:20 UTC). Erreurs en points de probabilité (racine de l'erreur quadratique moyenne) ; écarts d'erreur quadratique ×10⁴, intervalle à 95 % par match, négatif = mieux.

### Chaque source et la moyenne simple à deux, lignes fiables selon la règle du site

| Source | Période | Lignes / matchs | Pinnacle → clôture Pinnacle | Source → clôture Pinnacle | Moyenne → clôture Pinnacle | Moyenne − Pinnacle, cible clôture Pinnacle | Moyenne − Pinnacle, cible moyenne des deux clôtures |
|---|---|---|---|---|---|---|---|
| Polymarket | Tout | 17268 / 418 | 2,48 | 2,55 | 2,46 | **-0,11 [-0,21 ; -0,02]** | **-0,50 [-0,62 ; -0,40]** |
| Polymarket | Ajustement | 7340 / 203 | 2,48 | 2,53 | 2,45 | **-0,17 [-0,33 ; -0,01]** | **-0,62 [-0,82 ; -0,43]** |
| Polymarket | Test | 9928 / 215 | 2,48 | 2,56 | 2,46 | -0,08 [-0,19 ; +0,03] | **-0,42 [-0,56 ; -0,29]** |
| Polymarket | Test, après le gel | 3313 / 75 | 2,72 | 2,82 | 2,73 | +0,02 [-0,12 ; +0,17] | **-0,36 [-0,57 ; -0,18]** |
| Matchbook | Tout | 9965 / 159 | 2,93 | 2,97 | 2,90 | -0,19 [-0,43 ; +0,04] | **-0,56 [-0,83 ; -0,32]** |
| Matchbook | Ajustement | 3687 / 75 | 3,27 | 3,16 | 3,16 | **-0,72 [-1,31 ; -0,22]** | **-1,10 [-1,73 ; -0,59]** |
| Matchbook | Test | 6278 / 84 | 2,72 | 2,86 | 2,74 | +0,12 [-0,08 ; +0,33] | **-0,24 [-0,43 ; -0,04]** |
| Matchbook | Test, après le gel | 1341 / 18 | 3,40 | 3,61 | 3,46 | **+0,42 [+0,00 ; +0,86]** | -0,01 [-0,46 ; +0,49] |
| Smarkets | Tout | 6030 / 113 | 2,53 | 2,76 | 2,55 | +0,09 [-0,18 ; +0,37] | **-0,43 [-0,65 ; -0,21]** |
| Smarkets | Ajustement | 2365 / 51 | 2,60 | 2,88 | 2,64 | +0,21 [-0,27 ; +0,70] | -0,38 [-0,74 ; +0,04] |
| Smarkets | Test | 3665 / 62 | 2,49 | 2,69 | 2,49 | +0,02 [-0,28 ; +0,34] | **-0,46 [-0,71 ; -0,21]** |
| Smarkets | Test, après le gel | 626 / 14 | 2,35 | 2,57 | 2,39 | +0,17 [-0,30 ; +0,75] | -0,02 [-0,58 ; +0,81] |

### Fraîcheur, liquidité, écart achat/vente : la moyenne simple contre Pinnacle seul, par tranche

Les autres conditions de la règle du site sont respectées ; seule la variable étudiée sort de la règle.

| Source | Variable | Tranche | Lignes / matchs | Pinnacle → clôture Pinnacle | Source → clôture Pinnacle | Moyenne − Pinnacle, cible clôture Pinnacle | Moyenne − Pinnacle, cible moyenne des deux clôtures |
|---|---|---|---|---|---|---|---|
| Polymarket | Écart achat/vente (points) | 0 à 2 | 7456 / 352 | 2,45 | 2,46 | **-0,25 [-0,39 ; -0,11]** | **-0,55 [-0,68 ; -0,43]** |
| Polymarket | Écart achat/vente (points) | 2 à 3 | 4887 / 365 | 2,53 | 2,63 | -0,02 [-0,14 ; +0,10] | **-0,38 [-0,55 ; -0,22]** |
| Polymarket | Écart achat/vente (points) | 3 à 5 | 4136 / 292 | 2,51 | 2,62 | -0,04 [-0,20 ; +0,10] | **-0,59 [-0,82 ; -0,40]** |
| Polymarket | Écart achat/vente (points) | 5 à 8 | 1647 / 131 | 2,34 | 2,57 | **+0,22 [+0,03 ; +0,42]** | **-0,49 [-0,96 ; -0,13]** |
| Polymarket | Écart achat/vente (points) | 8 à 12 | 359 / 74 | 2,64 | 3,01 | +0,36 [-0,20 ; +1,01] | -0,50 [-1,27 ; +0,18] |
| Polymarket | Liquidité | 100 à 1000 | 1233 / 180 | 2,95 | 3,03 | -0,29 [-0,69 ; +0,10] | **-1,27 [-1,77 ; -0,79]** |
| Polymarket | Liquidité | 1000 à 3000 | 3616 / 289 | 3,20 | 3,30 | -0,05 [-0,26 ; +0,14] | **-0,65 [-0,90 ; -0,41]** |
| Polymarket | Liquidité | 3000 à 10000 | 5327 / 309 | 2,40 | 2,49 | -0,06 [-0,19 ; +0,07] | **-0,40 [-0,56 ; -0,24]** |
| Polymarket | Liquidité | 10000 à ∞ | 7092 / 227 | 1,98 | 2,00 | **-0,16 [-0,25 ; -0,06]** | **-0,38 [-0,47 ; -0,29]** |
| Polymarket | Âge du prix (heures) | 0 à 0,1 | 2371 / 260 | 2,74 | 2,81 | **-0,21 [-0,44 ; -0,02]** | **-0,72 [-0,98 ; -0,47]** |
| Polymarket | Âge du prix (heures) | 0,1 à 0,5 | 4394 / 339 | 2,52 | 2,59 | -0,11 [-0,25 ; +0,02] | **-0,51 [-0,67 ; -0,36]** |
| Polymarket | Âge du prix (heures) | 0,5 à 2 | 5434 / 362 | 2,52 | 2,57 | **-0,16 [-0,28 ; -0,04]** | **-0,54 [-0,70 ; -0,37]** |
| Polymarket | Âge du prix (heures) | 2 à 6 | 3653 / 335 | 2,42 | 2,49 | -0,07 [-0,20 ; +0,04] | **-0,40 [-0,52 ; -0,29]** |
| Polymarket | Âge du prix (heures) | 6 à 48 | 1416 / 185 | 1,79 | 1,97 | +0,06 [-0,10 ; +0,22] | **-0,28 [-0,48 ; -0,10]** |
| Matchbook | Écart achat/vente (points) | 0 à 2 | 3307 / 134 | 2,34 | 2,39 | -0,11 [-0,29 ; +0,05] | **-0,37 [-0,54 ; -0,21]** |
| Matchbook | Écart achat/vente (points) | 2 à 3 | 2163 / 138 | 3,06 | 3,16 | -0,02 [-0,48 ; +0,40] | **-0,44 [-0,89 ; -0,02]** |
| Matchbook | Écart achat/vente (points) | 3 à 5 | 4469 / 138 | 3,24 | 3,25 | -0,33 [-0,77 ; +0,02] | **-0,75 [-1,21 ; -0,38]** |
| Matchbook | Écart achat/vente (points) | 5 à 8 | 1956 / 129 | 3,69 | 3,73 | -0,37 [-0,99 ; +0,17] | **-0,84 [-1,47 ; -0,26]** |
| Matchbook | Écart achat/vente (points) | 8 à 12 | 502 / 82 | 3,05 | 3,10 | -0,46 [-1,38 ; +0,45] | **-0,91 [-1,83 ; -0,10]** |
| Matchbook | Liquidité | 0 à 100 | 7559 / 158 | 3,10 | 3,13 | -0,20 [-0,54 ; +0,05] | **-0,54 [-0,85 ; -0,26]** |
| Matchbook | Liquidité | 100 à 1000 | 2271 / 138 | 2,36 | 2,45 | -0,14 [-0,42 ; +0,11] | **-0,62 [-0,87 ; -0,38]** |
| Matchbook | Âge du prix (heures) | 0 à 0,1 | 3117 / 133 | 2,98 | 2,91 | **-0,54 [-1,08 ; -0,11]** | **-0,83 [-1,40 ; -0,39]** |
| Matchbook | Âge du prix (heures) | 0,1 à 0,5 | 3341 / 153 | 2,98 | 3,02 | -0,16 [-0,43 ; +0,11] | **-0,57 [-0,86 ; -0,26]** |
| Matchbook | Âge du prix (heures) | 0,5 à 2 | 2653 / 135 | 2,77 | 2,87 | -0,01 [-0,28 ; +0,22] | **-0,41 [-0,69 ; -0,16]** |
| Matchbook | Âge du prix (heures) | 2 à 6 | 765 / 90 | 3,21 | 3,44 | **+0,47 [+0,09 ; +0,84]** | +0,05 [-0,28 ; +0,37] |

### Poids d'une source face à une autre, jugé par la clôture d'une troisième

| Mélange | Clôture cible | Période | Lignes / matchs | Erreur de la 1re | Erreur de la 2e | Poids optimal de la 2e, IC 95 % |
|---|---|---|---|---|---|---|
| Polymarket + Matchbook | Pinnacle | Tout | 6850 / 122 | 1,98 | 1,97 | 0,56 [0,39 ; 0,74] |
| Polymarket + Matchbook | Pinnacle | Ajustement | 2493 / 50 | 2,05 | 2,04 | 0,61 [0,30 ; 0,95] |
| Polymarket + Matchbook | Pinnacle | Test | 4357 / 72 | 1,94 | 1,93 | 0,53 [0,34 ; 0,72] |
| Polymarket + Matchbook | Pinnacle | Test, après le gel | 893 / 15 | 2,20 | 2,18 | 0,61 [0,44 ; 0,76] |
| Pinnacle + Polymarket | Matchbook | Tout | 6652 / 122 | 2,44 | 2,23 | 0,94 [0,82 ; 1,07] |
| Pinnacle + Polymarket | Matchbook | Ajustement | 2477 / 51 | 2,70 | 2,46 | 1,03 [0,80 ; 1,30] |
| Pinnacle + Polymarket | Matchbook | Test | 4175 / 71 | 2,27 | 2,07 | 0,88 [0,76 ; 1,01] |
| Pinnacle + Polymarket | Matchbook | Test, après le gel | 743 / 15 | 2,61 | 2,44 | 0,89 [0,62 ; 1,25] |
| Pinnacle + Matchbook | Polymarket | Tout | 5107 / 119 | 2,38 | 2,15 | 0,93 [0,82 ; 1,05] |
| Pinnacle + Matchbook | Polymarket | Ajustement | 1782 / 49 | 2,72 | 2,47 | 1,01 [0,83 ; 1,20] |
| Pinnacle + Matchbook | Polymarket | Test | 3325 / 70 | 2,18 | 1,97 | 0,89 [0,75 ; 1,03] |
| Pinnacle + Matchbook | Polymarket | Test, après le gel | 671 / 15 | 2,54 | 2,40 | 0,77 [0,45 ; 1,13] |
| Pinnacle + Polymarket | Smarkets | Tout | 5456 / 118 | 2,12 | 1,80 | 0,94 [0,86 ; 1,02] |
| Pinnacle + Polymarket | Smarkets | Ajustement | 2026 / 50 | 2,11 | 1,75 | 0,94 [0,82 ; 1,05] |
| Pinnacle + Polymarket | Smarkets | Test | 3430 / 68 | 2,13 | 1,84 | 0,94 [0,83 ; 1,06] |
| Pinnacle + Polymarket | Smarkets | Test, après le gel | 638 / 16 | 2,17 | 1,98 | 1,13 [0,69 ; 1,66] |
| Pinnacle + Matchbook | Smarkets | Tout | 3287 / 46 | 2,21 | 1,93 | 0,96 [0,80 ; 1,13] |
| Pinnacle + Matchbook | Smarkets | Ajustement | 1116 / 17 | 2,56 | 2,19 | 1,08 [0,72 ; 1,46] |
| Pinnacle + Matchbook | Smarkets | Test | 2171 / 29 | 2,01 | 1,79 | 0,88 [0,77 ; 1,00] |
| Pinnacle + Smarkets | Matchbook | Tout | 3380 / 41 | 2,84 | 2,76 | 0,61 [0,42 ; 0,85] |
| Pinnacle + Smarkets | Matchbook | Ajustement | 1233 / 15 | 3,15 | 3,10 | 0,56 [0,23 ; 0,99] |
| Pinnacle + Smarkets | Matchbook | Test | 2147 / 26 | 2,65 | 2,54 | 0,64 [0,40 ; 0,93] |

### Pondérations ajustées puis testées (Pinnacle, Polymarket, Matchbook)

Poids fixes ajustés sur la clôture Pinnacle : Pinnacle 1, Polymarket 0,58, Matchbook 4,59.

Poids complets ajustés : poids d'une bourse = base (Polymarket 1,69, Matchbook 31,82) × exp(-0,87 × écart en points -1,89 × log10(liquidité / 1 000) -2,49 × ln(1 + âge en heures)) ; poids de Pinnacle = exp(+0,09 × ln(1 + âge en heures) +0,07 × (marge − 5 points) +4,99 × log10(limite / 500)).

| Période | Pondération | Lignes / matchs | Erreur, clôture Pinnacle | Écart avec l'actuel, clôture Pinnacle | Erreur, moyenne des clôtures | Écart avec l'actuel, moyenne des clôtures |
|---|---|---|---|---|---|---|
| Ajustement | Pinnacle seul | 9338 / 229 | 2,87 | **+0,13 [+0,02 ; +0,26]** | 3,05 | **+0,51 [+0,36 ; +0,66]** |
| Ajustement | Actuel : moyenne simple Pinnacle + Polymarket | 9338 / 229 | 2,84 | référence | 2,97 | référence |
| Ajustement | Moyenne simple avec Matchbook | 9338 / 229 | 2,80 | **-0,27 [-0,53 ; -0,06]** | 2,91 | **-0,35 [-0,59 ; -0,16]** |
| Ajustement | Poids fixes par source, ajustés | 9338 / 229 | 2,78 | **-0,34 [-0,74 ; -0,03]** | 2,90 | **-0,41 [-0,78 ; -0,11]** |
| Ajustement | Poids selon fraîcheur, liquidité et écart, ajustés | 9338 / 229 | 2,78 | **-0,37 [-0,80 ; -0,02]** | 2,91 | **-0,34 [-0,74 ; -0,01]** |
| Test | Pinnacle seul | 12962 / 228 | 2,71 | +0,06 [-0,02 ; +0,15] | 2,72 | **+0,35 [+0,26 ; +0,45]** |
| Test | Actuel : moyenne simple Pinnacle + Polymarket | 12962 / 228 | 2,70 | référence | 2,66 | référence |
| Test | Moyenne simple avec Matchbook | 12962 / 228 | 2,72 | **+0,08 [+0,00 ; +0,16]** | 2,65 | -0,04 [-0,12 ; +0,04] |
| Test | Poids fixes par source, ajustés | 12962 / 228 | 2,75 | **+0,23 [+0,09 ; +0,37]** | 2,67 | +0,05 [-0,08 ; +0,18] |
| Test | Poids selon fraîcheur, liquidité et écart, ajustés | 12962 / 228 | 2,77 | **+0,34 [+0,21 ; +0,48]** | 2,70 | **+0,24 [+0,11 ; +0,37]** |
| Test, après le gel | Pinnacle seul | 3993 / 78 | 3,03 | -0,01 [-0,14 ; +0,10] | 3,08 | **+0,33 [+0,18 ; +0,51]** |
| Test, après le gel | Actuel : moyenne simple Pinnacle + Polymarket | 3993 / 78 | 3,03 | référence | 3,03 | référence |
| Test, après le gel | Moyenne simple avec Matchbook | 3993 / 78 | 3,05 | **+0,14 [+0,02 ; +0,27]** | 3,03 | +0,04 [-0,08 ; +0,18] |
| Test, après le gel | Poids fixes par source, ajustés | 3993 / 78 | 3,07 | **+0,28 [+0,06 ; +0,52]** | 3,06 | +0,17 [-0,05 ; +0,42] |
| Test, après le gel | Poids selon fraîcheur, liquidité et écart, ajustés | 3993 / 78 | 3,08 | **+0,34 [+0,13 ; +0,59]** | 3,08 | **+0,34 [+0,12 ; +0,61]** |

### Résultats réels : paris réglés où Pinnacle et une autre source cotent le même pari (échantillon sélectionné)

| Autre source | Pari présent dans la table de | Paris / matchs | Gagnés | Probabilité Pinnacle | Probabilité de l'autre | Log-loss Pinnacle | Log-loss de l'autre | Log-loss de la moyenne | Autre − Pinnacle ×10⁴, IC 95 % | Moyenne − Pinnacle ×10⁴, IC 95 % |
|---|---|---|---|---|---|---|---|---|---|---|
| Polymarket | tous | 692 / 415 | 48,7 % | 48,2 % | 48,1 % | 0,6111 | 0,6170 | 0,6134 | +60 [-2 ; +126] | +23 [-8 ; +54] |
| Polymarket | Pinnacle seul | 212 / 156 | 53,3 % | 52,4 % | 50,0 % | 0,6249 | 0,6274 | 0,6256 | +25 [-98 ; +142] | +6 [-56 ; +64] |
| Polymarket | Polymarket seul | 149 / 107 | 39,6 % | 42,3 % | 45,4 % | 0,5760 | 0,5981 | 0,5853 | **+221 [+37 ; +409]** | **+93 [+10 ; +182]** |
| Polymarket | les deux | 319 / 220 | 51,1 % | 48,5 % | 48,6 % | 0,6264 | 0,6290 | 0,6275 | +26 [-28 ; +82] | +11 [-15 ; +37] |
| Matchbook | tous | 139 / 92 | 41,0 % | 38,8 % | 39,7 % | 0,5742 | 0,5835 | 0,5787 | **+93 [+14 ; +175]** | **+45 [+6 ; +87]** |

