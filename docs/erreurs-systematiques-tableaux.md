# Erreurs systématiques : tableaux complets

Produit par `python etudes/erreurs_systematiques.py` sur « donnees » au commit 3a123d8 du 2026-11-15T19:35:13+00:00 : 5256 paris uniques réglés du 2026-10-05 au 2026-11-15, dont 2967 avec une clôture Pinnacle. Coupure des deux moitiés : 2026-10-24T23:06. 56 segments testés (correction de Holm, deux sens). Familles mesurées sur les cotes ≤ 5 ; « Grosses cotes (> 5) » à part. Causes (copie, lent, marge) : paris depuis le 25/10/2026. Conclusions : [erreurs-systematiques.md](erreurs-systematiques.md).

| Famille | Segment | Paris | CLV mesurées | Écart à la prise | CLV Pinnacle | IC 95 % | p Holm | % > 0 | 1re moitié | 2de moitié | Semaines > 0 | Copie | Lent | Marge | ROI | IC 95 % du ROI | ROI − CLV, IC 95 % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Type de marché | 1N2 / vainqueur | 1483 | 852 | +4,9 % | +0,42 % | [−0,45 % ; +1,28 %] | 1,000 | 58 % | +0,77 % [−0,45 % ; +2,01 %] (370) | +0,15 % [−1,10 % ; +1,33 %] (482) | 3/6 | 10 % | 60 % | 30 % | +5,9 % | [−1,36 % ; +13,45 %] | [−3,77 % ; +14,69 %] |
| Type de marché | Total | 958 | 552 | +4,5 % | +0,53 % | [−0,56 % ; +1,63 %] | 1,000 | 59 % | +0,89 % [−0,65 % ; +2,46 %] (217) | +0,30 % [−1,20 % ; +1,88 %] (335) | 3/6 | 1 % | 68 % | 31 % | +1,5 % | [−7,48 % ; +10,66 %] | [−14,14 % ; +8,47 %] |
| Type de marché | Handicap | 930 | 579 | +4,9 % | +1,91 % | [+0,58 % ; +3,39 %] | 0,155 | 64 % | +3,53 % [+1,97 % ; +5,56 %] (309) | +0,05 % [−2,01 % ; +2,33 %] (270) | 5/6 | 1 % | 53 % | 46 % | −2,3 % | [−11,55 % ; +7,23 %] | [−16,83 % ; +4,02 %] |
| Type de marché | Total d'une équipe | 522 | 321 | +3,9 % | +1,65 % | [+0,51 % ; +2,76 %] | 0,202 | 65 % | +1,65 % [+0,04 % ; +3,25 %] (162) | +1,65 % [+0,04 % ; +3,26 %] (159) | 5/6 | 0 % | 70 % | 30 % | −1,7 % | [−11,63 % ; +8,62 %] | [−12,55 % ; +10,02 %] |
| Type de marché | Double chance | 120 | 95 | +5,0 % | +3,48 % | [+1,92 % ; +5,53 %] | 0,006 | 75 % | +4,81 % [+2,05 % ; +9,48 %] (41) | +2,47 % [+0,57 % ; +4,13 %] (54) | 5/5 | 0 % | 70 % | 0 % | +10,0 % | [−5,24 % ; +24,86 %] | [−1,96 % ; +30,67 %] |
| Type de marché | Remboursé si nul | 101 | 64 | +4,2 % | +2,61 % | [−0,73 % ; +5,09 %] | 1,000 | 77 % | +2,43 % [−5,05 % ; +6,00 %] (27) | +2,74 % [−1,50 % ; +6,12 %] (37) | 3/4 | 12 % | 71 % | 17 % | +15,8 % | [−0,24 % ; +35,40 %] | [−18,48 % ; +22,37 %] |
| Type de marché | Les deux marquent | 90 | 37 | +3,9 % | +3,24 % | — | — | 76 % | +5,83 % — (12) | +2,00 % [+0,24 % ; +4,06 %] (25) | 1/1 | 0 % | 62 % | 38 % | +26,9 % | — | — |
| Type de marché | Handicap à 3 issues | 80 | 47 | +4,9 % | −0,27 % | [−6,15 % ; +5,48 %] | 1,000 | 60 % | +1,73 % [−6,86 % ; +9,82 %] (27) | −2,98 % [−12,07 % ; +5,13 %] (20) | 0/2 | 0 % | 69 % | 31 % | −9,6 % | [−40,94 % ; +29,00 %] | [−51,57 % ; +41,63 %] |
| Période | Match entier | 3283 | 1809 | +4,7 % | +1,03 % | [+0,26 % ; +1,86 %] | 0,361 | 61 % | +1,90 % [+0,89 % ; +3,07 %] (900) | +0,16 % [−0,96 % ; +1,40 %] (909) | 4/6 | 5 % | 60 % | 35 % | +3,9 % | [−1,49 % ; +9,48 %] | [−6,63 % ; +6,67 %] |
| Période | 1re mi-temps | 462 | 318 | +4,0 % | +0,66 % | [−0,25 % ; +1,42 %] | 1,000 | 63 % | +0,67 % [−1,20 % ; +1,93 %] (108) | +0,65 % [−0,43 % ; +1,59 %] (210) | 5/6 | 0 % | 75 % | 25 % | −6,5 % | [−16,44 % ; +3,70 %] | [−15,48 % ; +5,98 %] |
| Période | Temps réglementaire | 422 | 365 | +5,4 % | +1,90 % | [+0,41 % ; +3,40 %] | 0,470 | 64 % | +2,81 % [+0,69 % ; +5,56 %] (134) | +1,37 % [−0,63 % ; +3,19 %] (231) | 5/6 | 5 % | 76 % | 16 % | +6,3 % | [−7,52 % ; +20,56 %] | [−7,94 % ; +20,39 %] |
| Période | Autre partie (MT2, quart-temps, set, période) | 119 | 56 | +4,1 % | +2,20 % | [−0,65 % ; +4,01 %] | 1,000 | 84 % | +2,29 % [−2,29 % ; +5,18 %] (24) | +2,13 % [−2,42 % ; +4,45 %] (32) | 1/2 | 0 % | 40 % | 60 % | −7,9 % | [−27,32 % ; +12,87 %] | [−49,90 % ; +4,30 %] |
| Sport | football | 2002 | 1081 | +4,4 % | +0,44 % | [−0,60 % ; +1,53 %] | 1,000 | 58 % | +0,70 % [−0,65 % ; +2,17 %] (536) | +0,18 % [−1,41 % ; +1,88 %] (545) | 3/6 | 5 % | 60 % | 34 % | +0,1 % | [−7,19 % ; +7,77 %] | [−11,82 % ; +6,21 %] |
| Sport | basket | 887 | 547 | +4,6 % | +1,43 % | [−0,06 % ; +3,29 %] | 1,000 | 61 % | +3,80 % [+1,57 % ; +7,28 %] (231) | −0,30 % [−2,18 % ; +1,83 %] (316) | 4/6 | 3 % | 65 % | 32 % | +7,4 % | [−3,53 % ; +18,37 %] | [−6,21 % ; +19,01 %] |
| Sport | hockey | 644 | 485 | +5,3 % | +2,08 % | [+0,76 % ; +3,37 %] | 0,099 | 66 % | +3,04 % [+1,13 % ; +5,50 %] (159) | +1,62 % [−0,16 % ; +3,18 %] (326) | 5/6 | 4 % | 76 % | 18 % | +4,9 % | [−6,10 % ; +16,17 %] | [−7,27 % ; +18,23 %] |
| Sport | tennis | 263 | 64 | +5,3 % | +0,84 % | [−1,16 % ; +2,41 %] | 1,000 | 70 % | +0,59 % [−2,89 % ; +2,80 %] (38) | +1,20 % [−1,10 % ; +3,49 %] (26) | 3/4 | 0 % | 32 % | 68 % | +12,9 % | [−2,03 % ; +30,08 %] | [−41,82 % ; +23,64 %] |
| Sport | autres sports | 210 | 148 | +4,5 % | +2,74 % | [+1,39 % ; +4,13 %] | 0,006 | 77 % | +2,11 % [+0,18 % ; +3,63 %] (95) | +3,87 % [+2,01 % ; +7,49 %] (53) | 5/5 | 0 % | 44 % | 56 % | +4,8 % | [−10,09 % ; +19,85 %] | [−7,72 % ; +25,15 %] |
| Sport | volley | 183 | 156 | +4,9 % | +0,22 % | [−1,37 % ; +1,66 %] | 1,000 | 61 % | +1,71 % [−0,67 % ; +3,97 %] (72) | −1,07 % [−3,35 % ; +0,65 %] (84) | 3/6 | 0 % | 76 % | 24 % | −13,1 % | [−25,27 % ; −0,28 %] | [−31,48 % ; −5,98 %] |
| Sport | handball | 97 | 67 | +4,2 % | +1,88 % | [−0,23 % ; +3,86 %] | 1,000 | 69 % | +3,67 % [+1,57 % ; +6,80 %] (35) | −0,08 % [−4,02 % ; +2,81 %] (32) | 4/4 | 0 % | 71 % | 29 % | −5,0 % | [−27,47 % ; +17,60 %] | [−43,50 % ; +3,18 %] |
| Liquidité du match | limite Pinnacle ≤ 300 € | 1189 | 910 | +4,6 % | +0,15 % | [−0,90 % ; +1,28 %] | 1,000 | 57 % | — | +0,15 % [−0,93 % ; +1,27 %] (910) | 3/4 | 4 % | 66 % | 29 % | +0,7 % | [−7,96 % ; +9,77 %] | [−10,37 % ; +6,64 %] |
| Liquidité du match | limite Pinnacle 300 à 1 500 € | 429 | 288 | +4,1 % | +0,52 % | [−0,98 % ; +2,09 %] | 1,000 | 60 % | — | +0,52 % [−0,98 % ; +2,10 %] (288) | 1/3 | 5 % | 53 % | 40 % | −0,2 % | [−13,47 % ; +14,07 %] | [−17,80 % ; +13,66 %] |
| Liquidité du match | limite Pinnacle > 1 500 € | 154 | 70 | +4,0 % | +3,72 % | [+0,32 % ; +11,49 %] | 1,000 | 76 % | — | +3,72 % [+0,30 % ; +11,58 %] (70) | 2/2 | 1 % | 59 % | 38 % | +0,8 % | [−22,31 % ; +27,42 %] | [−17,80 % ; +62,15 %] |
| Délai avant le match | 6 à 24 h avant | 1709 | 959 | +4,7 % | +1,25 % | [+0,17 % ; +2,48 %] | 0,828 | 59 % | +2,77 % [+1,22 % ; +4,72 %] (482) | −0,30 % [−1,77 % ; +1,20 %] (477) | 4/6 | 4 % | 62 % | 33 % | +2,4 % | [−4,50 % ; +9,58 %] | [−11,13 % ; +6,57 %] |
| Délai avant le match | plus de 24 h avant | 959 | 573 | +5,1 % | −0,16 % | [−1,57 % ; +1,38 %] | 1,000 | 52 % | −1,15 % [−3,10 % ; +0,71 %] (231) | +0,51 % [−1,47 % ; +2,80 %] (342) | 1/6 | 3 % | 62 % | 33 % | +7,6 % | [−2,03 % ; +18,44 %] | [−5,89 % ; +15,90 %] |
| Délai avant le match | 1 à 6 h avant | 952 | 569 | +4,3 % | +1,17 % | [+0,05 % ; +2,34 %] | 1,000 | 61 % | +1,81 % [+0,36 % ; +3,45 %] (238) | +0,71 % [−0,90 % ; +2,42 %] (331) | 5/6 | 5 % | 63 % | 31 % | +1,9 % | [−8,51 % ; +12,66 %] | [−8,95 % ; +15,60 %] |
| Délai avant le match | moins d'1 h avant | 666 | 447 | +4,5 % | +2,49 % | [+1,33 % ; +3,42 %] | 0,010 | 83 % | +3,31 % [+1,98 % ; +4,26 %] (215) | +1,74 % [−0,22 % ; +3,29 %] (232) | 5/6 | 3 % | 72 % | 24 % | −2,7 % | [−13,33 % ; +8,78 %] | [−19,46 % ; +6,59 %] |
| Issue (1N2) | 1N2 : domicile | 340 | 232 | +5,0 % | +1,64 % | [−0,30 % ; +3,54 %] | 1,000 | 57 % | +1,57 % [−0,95 % ; +4,16 %] (122) | +1,71 % [−1,35 % ; +4,61 %] (110) | 3/6 | 6 % | 60 % | 34 % | +10,2 % | [−7,71 % ; +30,85 %] | [−9,62 % ; +29,10 %] |
| Issue (1N2) | 1N2 : extérieur | 272 | 183 | +5,2 % | −0,02 % | [−2,24 % ; +1,83 %] | 1,000 | 56 % | −0,76 % [−3,64 % ; +1,79 %] (79) | +0,54 % [−2,97 % ; +3,20 %] (104) | 3/6 | 11 % | 61 % | 28 % | −11,9 % | [−29,37 % ; +8,46 %] | [−31,59 % ; +14,16 %] |
| Issue (1N2) | 1N2 : nul | 204 | 107 | +4,7 % | −1,15 % | [−3,28 % ; +0,53 %] | 1,000 | 55 % | +0,72 % [−1,00 % ; +2,18 %] (61) | −3,63 % [−7,84 % ; −0,22 %] (46) | 3/5 | 22 % | 68 % | 10 % | +11,0 % | [−15,42 % ; +41,21 %] | [−7,17 % ; +71,32 %] |
| Issue (totaux) | Total : moins | 816 | 496 | +4,2 % | +0,91 % | [−0,15 % ; +2,05 %] | 1,000 | 61 % | +1,74 % [+0,31 % ; +3,18 %] (223) | +0,24 % [−1,32 % ; +2,03 %] (273) | 5/6 | 1 % | 65 % | 34 % | −0,9 % | [−9,90 % ; +8,08 %] | [−12,07 % ; +8,47 %] |
| Issue (totaux) | Total : plus | 664 | 377 | +4,4 % | +0,98 % | [−0,39 % ; +2,40 %] | 1,000 | 62 % | +0,47 % [−1,74 % ; +2,55 %] (156) | +1,34 % [−0,48 % ; +3,33 %] (221) | 3/6 | 0 % | 74 % | 26 % | +1,9 % | [−9,95 % ; +14,62 %] | [−17,91 % ; +12,54 %] |
| Bookmaker × marché | PMU · 1N2 / vainqueur | 550 | 344 | +4,7 % | +2,52 % | [+1,45 % ; +3,63 %] | 0,006 | 68 % | +2,50 % [+0,89 % ; +4,23 %] (142) | +2,53 % [+1,14 % ; +4,02 %] (202) | 6/6 | 7 % | 65 % | 28 % | +9,4 % | [−0,91 % ; +20,33 %] | [−1,49 % ; +24,89 %] |
| Bookmaker × marché | PMU · Total | 515 | 317 | +4,4 % | +1,87 % | [+0,72 % ; +3,02 %] | 0,092 | 70 % | +2,07 % [+0,31 % ; +3,88 %] (124) | +1,73 % [+0,20 % ; +3,31 %] (193) | 6/6 | 1 % | 71 % | 28 % | −3,0 % | [−14,24 % ; +8,46 %] | [−19,69 % ; +7,21 %] |
| Bookmaker × marché | PMU · Total d'une équipe | 411 | 264 | +3,3 % | +1,93 % | [+0,91 % ; +3,00 %] | 0,019 | 66 % | +1,82 % [+0,29 % ; +3,60 %] (129) | +2,02 % [+0,66 % ; +3,41 %] (135) | 5/6 | 0 % | 71 % | 29 % | −3,4 % | [−14,45 % ; +8,46 %] | [−17,06 % ; +6,85 %] |
| Bookmaker × marché | Betclic · 1N2 / vainqueur | 407 | 259 | +4,8 % | −0,42 % | [−1,88 % ; +1,04 %] | 1,000 | 58 % | +0,88 % [−1,55 % ; +3,31 %] (117) | −1,48 % [−3,30 % ; +0,13 %] (142) | 1/6 | 7 % | 61 % | 33 % | +5,2 % | [−5,01 % ; +16,37 %] | [−12,02 % ; +13,04 %] |
| Bookmaker × marché | Betclic · Handicap | 348 | 208 | +4,8 % | +3,06 % | [+0,79 % ; +5,73 %] | 0,312 | 68 % | +4,48 % [+1,54 % ; +8,50 %] (106) | +1,59 % [−1,87 % ; +5,75 %] (102) | 5/6 | 0 % | 56 % | 44 % | −3,2 % | [−20,57 % ; +13,48 %] | [−14,30 % ; +24,70 %] |
| Bookmaker × marché | Betclic · Total | 244 | 129 | +4,8 % | +0,83 % | [−1,29 % ; +3,13 %] | 1,000 | 53 % | +2,43 % [−1,56 % ; +7,37 %] (42) | +0,06 % [−2,47 % ; +2,90 %] (87) | 2/5 | 0 % | 79 % | 21 % | +6,5 % | [−13,66 % ; +26,87 %] | [−20,79 % ; +29,96 %] |
| Bookmaker × marché | PMU · Handicap | 243 | 169 | +4,3 % | +2,41 % | [+0,85 % ; +3,95 %] | 0,141 | 69 % | +3,81 % [+1,84 % ; +5,87 %] (81) | +1,12 % [−1,23 % ; +3,36 %] (88) | 5/6 | 0 % | 54 % | 46 % | −4,7 % | [−18,81 % ; +9,72 %] | [−30,60 % ; +3,16 %] |
| Bookmaker × marché | Winamax · 1N2 / vainqueur | 234 | 113 | +5,2 % | −1,55 % | [−3,69 % ; +0,85 %] | 1,000 | 48 % | −1,22 % [−3,47 % ; +0,88 %] (58) | −1,89 % [−5,65 % ; +2,68 %] (55) | 1/6 | 21 % | 43 % | 36 % | +5,8 % | [−8,90 % ; +21,80 %] | [−20,85 % ; +25,47 %] |
| Bookmaker × marché | Winamax · Handicap | 139 | 86 | +5,4 % | +1,28 % | [−1,82 % ; +4,26 %] | 1,000 | 59 % | +2,21 % [−1,84 % ; +4,56 %] (53) | −0,20 % [−5,81 % ; +8,13 %] (33) | 3/4 | 0 % | 56 % | 44 % | +11,1 % | [−13,25 % ; +36,71 %] | [−29,16 % ; +23,82 %] |
| Bookmaker × marché | Unibet · 1N2 / vainqueur | 130 | 46 | +5,5 % | −0,05 % | [−3,65 % ; +3,49 %] | 1,000 | 57 % | −0,02 % [−4,11 % ; +4,16 %] (28) | −0,10 % — (18) | 1/3 | 20 % | 60 % | 20 % | +8,2 % | [−11,96 % ; +30,65 %] | [−34,84 % ; +45,13 %] |
| Bookmaker × marché | OlyBet · 1N2 / vainqueur | 119 | 67 | +5,1 % | −3,37 % | [−6,00 % ; −0,30 %] | 1,000 | 33 % | −3,84 % [−7,97 % ; +0,54 %] (24) | −3,11 % [−6,71 % ; +1,20 %] (43) | 0/2 | 10 % | 42 % | 48 % | −5,6 % | [−26,93 % ; +19,35 %] | [−38,17 % ; +28,30 %] |
| Bookmaker × marché | Unibet · Handicap | 97 | 45 | +5,5 % | +4,06 % | [+0,03 % ; +11,79 %] | 1,000 | 67 % | +4,46 % [+0,32 % ; +12,69 %] (43) | −4,58 % — (2) | 2/2 | 0 % | 0 % | 100 % | +15,3 % | [−6,34 % ; +39,30 %] | [−35,87 % ; +35,18 %] |
| Bookmaker × marché | Winamax · Total | 95 | 58 | +4,6 % | −3,78 % | [−6,90 % ; −1,16 %] | 0,228 | 40 % | −3,17 % [−7,53 % ; +0,38 %] (29) | −4,40 % [−10,13 % ; −0,13 %] (29) | 0/4 | 0 % | 56 % | 44 % | +14,5 % | [−16,22 % ; +44,21 %] | [−36,30 % ; +36,99 %] |
| Bookmaker × marché | PMU · Double chance | 80 | 73 | +4,4 % | +3,10 % | [+1,44 % ; +5,69 %] | 0,010 | 73 % | +4,17 % [+0,90 % ; +11,17 %] (30) | +2,35 % [+0,58 % ; +4,06 %] (43) | 4/4 | 0 % | 71 % | 0 % | +9,3 % | [−8,97 % ; +26,53 %] | [−7,96 % ; +28,13 %] |
| Bookmaker × marché | OlyBet · Handicap | 78 | 52 | +5,5 % | −4,08 % | [−9,56 % ; +2,44 %] | 1,000 | 38 % | +0,35 % [−5,67 % ; +7,22 %] (21) | −7,08 % [−14,63 % ; +4,26 %] (31) | 1/3 | 6 % | 39 % | 56 % | −36,2 % | [−57,82 % ; −5,37 %] | [−65,13 % ; −6,41 %] |
| Bookmaker × marché | PMU · Les deux marquent | 69 | 30 | +3,3 % | +2,97 % | — | — | 70 % | +6,90 % — (6) | +1,98 % [+0,18 % ; +4,13 %] (24) | 1/1 | 0 % | 60 % | 40 % | +11,5 % | — | — |
| Bookmaker × marché | Unibet · Total | 63 | 25 | +4,1 % | −3,16 % | — | — | 32 % | −3,63 % — (18) | −1,95 % — (7) | 0/0 | 0 % | 100 % | 0 % | −7,7 % | — | — |
| Bookmaker × marché | PMU · Remboursé si nul | 49 | 33 | +3,4 % | +2,08 % | — | — | 73 % | −1,43 % — (11) | +3,84 % [+0,56 % ; +9,13 %] (22) | 0/0 | 0 % | 85 % | 15 % | +7,9 % | — | — |
| Bookmaker × marché | NetBet · 1N2 / vainqueur | 43 | 23 | +5,2 % | −0,05 % | — | — | 52 % | −10,45 % — (1) | +0,43 % [−7,93 % ; +6,78 %] (22) | 0/0 | 11 % | 89 % | 0 % | −6,6 % | — | — |
| Bookmaker × période | PMU · Temps réglementaire | 279 | 239 | +5,3 % | +3,39 % | [+2,16 % ; +4,83 %] | 0,006 | 71 % | +3,76 % [+1,26 % ; +7,75 %] (81) | +3,20 % [+1,85 % ; +4,59 %] (158) | 6/6 | 0 % | 83 % | 12 % | +6,4 % | [−7,44 % ; +20,79 %] | [−10,44 % ; +18,91 %] |
| Bookmaker × période | PMU · 1re mi-temps | 253 | 180 | +3,5 % | +1,17 % | [+0,09 % ; +1,99 %] | 1,000 | 66 % | +1,73 % [+0,64 % ; +2,77 %] (74) | +0,78 % [−0,94 % ; +1,96 %] (106) | 6/6 | 0 % | 71 % | 29 % | −10,0 % | [−21,09 % ; +1,08 %] | [−18,91 % ; +6,84 %] |
| Bookmaker × période | Betclic · 1re mi-temps | 139 | 104 | +4,0 % | +1,16 % | [−0,17 % ; +2,48 %] | 1,000 | 63 % | +2,21 % — (17) | +0,95 % [−0,55 % ; +2,37 %] (87) | 3/4 | 0 % | 81 % | 19 % | −1,0 % | [−20,27 % ; +18,32 %] | [−18,67 % ; +17,60 %] |
| Bookmaker × période | PMU · Autre partie (MT2, quart-temps, set, période) | 101 | 48 | +3,9 % | +2,52 % | [−0,16 % ; +3,89 %] | 1,000 | 88 % | +2,89 % [+0,50 % ; +4,52 %] (20) | +2,26 % [−3,08 % ; +4,37 %] (28) | 1/1 | 0 % | 25 % | 75 % | −3,8 % | [−25,72 % ; +19,04 %] | [−47,88 % ; +14,50 %] |
| Bookmaker × période | Betclic · Temps réglementaire | 94 | 82 | +5,1 % | +0,94 % | [−2,31 % ; +4,60 %] | 1,000 | 56 % | +1,67 % [−2,78 % ; +7,18 %] (44) | +0,09 % [−5,19 % ; +5,50 %] (38) | 1/4 | 5 % | 76 % | 19 % | +9,9 % | [−17,29 % ; +40,17 %] | [−15,99 % ; +44,54 %] |
| Bookmaker × période | Winamax · 1re mi-temps | 45 | 27 | +4,7 % | −4,91 % | — | — | 44 % | −6,60 % — (14) | −3,09 % — (13) | 0/1 | 0 % | 100 % | 0 % | +2,4 % | — | — |
| Grosses cotes (> 5) par marché | Score exact | 572 | 232 | +13,5 % | +8,69 % | [+6,62 % ; +11,18 %] | 0,006 | 79 % | +7,99 % [+5,88 % ; +10,43 %] (164) | +10,38 % [+5,45 % ; +17,18 %] (68) | 5/5 | 9 % | 28 % | 0 % | −44,9 % | [−79,05 % ; +76,00 %] | [−112,07 % ; +773,79 %] |
| Grosses cotes (> 5) par marché | 1N2 / vainqueur | 188 | 78 | +9,5 % | +5,04 % | [−1,87 % ; +19,98 %] | 1,000 | 58 % | +5,64 % [−4,76 % ; +29,96 %] (50) | +3,95 % [−2,70 % ; +11,42 %] (28) | 3/4 | 4 % | 56 % | 41 % | −64,8 % | [−84,58 % ; −23,05 %] | [−103,61 % ; −19,26 %] |
| Grosses cotes (> 5) par marché | Mi-temps / fin | 131 | 91 | +10,7 % | +6,98 % | [+3,73 % ; +11,04 %] | 0,006 | 73 % | +6,98 % [+3,76 % ; +11,04 %] (91) | — | 1/1 | — | — | — | −32,1 % | [−102,11 % ; +4337,60 %] | [−124,41 % ; +3775,58 %] |
| Grosses cotes (> 5) par bookmaker | Betclic | 576 | 287 | +10,7 % | +6,46 % | [+4,60 % ; +8,41 %] | 0,006 | 75 % | +6,33 % [+4,28 % ; +8,45 %] (243) | +7,17 % [+3,11 % ; +13,34 %] (44) | 5/5 | 8 % | 44 % | 0 % | −47,0 % | [−86,51 % ; +180,07 %] | [−105,61 % ; +1335,12 %] |
| Grosses cotes (> 5) par bookmaker | Unibet | 129 | 43 | +15,0 % | +10,18 % | [+2,64 % ; +30,03 %] | 0,202 | 70 % | +13,22 % [+1,09 % ; +62,00 %] (25) | +5,94 % — (18) | 1/1 | 8 % | 17 % | 25 % | −37,1 % | [−88,84 % ; +282,18 %] | [−129,73 % ; −102,69 %] |
| Grosses cotes (> 5) par bookmaker | PMU | 113 | 52 | +11,3 % | +1,19 % | [−5,54 % ; +7,48 %] | 1,000 | 58 % | +1,68 % [−7,83 % ; +10,77 %] (31) | +0,47 % [−9,99 % ; +9,50 %] (21) | 2/3 | 0 % | 59 % | 41 % | −51,1 % | [−79,06 % ; +4,91 %] | [−88,96 % ; +98,38 %] |
| Grosses cotes (> 5) par bookmaker | Winamax | 81 | 16 | +16,7 % | +14,90 % | — | — | 81 % | +8,58 % — (9) | +23,01 % — (7) | 0/0 | 25 % | 50 % | 0 % | −8,4 % | — | — |
| Grosses cotes (> 5) par bookmaker | OlyBet | 61 | 21 | +15,6 % | +11,33 % | — | — | 67 % | +2,22 % — (9) | +18,16 % — (12) | 0/0 | 0 % | 17 % | 50 % | −63,0 % | — | — |

## Population entière (controle.json, intitulés conformes)

| Bookmaker | Marché | Période | Rapports | Médiane cote / juste | Part > 1 | Part > 1,03 |
|---|---|---|---|---|---|---|
| pmu | Handicap | Autre partie (MT2, quart-temps, set, période) | 900 | 0,877 | 4,8 % | 0,0 % |
| pmu | 1N2 / vainqueur | Autre partie (MT2, quart-temps, set, période) | 1254 | 0,916 | 3,7 % | 2,2 % |
| pmu | Total d'une équipe | Autre partie (MT2, quart-temps, set, période) | 3900 | 0,872 | 3,3 % | 0,0 % |
| pmu | Handicap | Match entier | 4424 | 0,870 | 3,2 % | 2,2 % |
| pmu | Total | Temps réglementaire | 600 | 0,917 | 3,2 % | 0,5 % |
| betclic | Score exact | 1re mi-temps | 300 | 0,843 | 3,0 % | 2,3 % |
| betclic | Total | Match entier | 2400 | 0,880 | 2,5 % | 0,1 % |
| pmu | Total d'une équipe | 1re mi-temps | 3000 | 0,877 | 2,3 % | 0,1 % |
| pmu | 1N2 / vainqueur | Match entier | 5100 | 0,890 | 2,2 % | 0,3 % |
| tous | Total d'une équipe | Autre partie (MT2, quart-temps, set, période) | 7500 | 0,866 | 1,7 % | 0,0 % |
| tous | 1N2 / vainqueur | Autre partie (MT2, quart-temps, set, période) | 3698 | 0,875 | 1,2 % | 0,8 % |
| tous | Handicap | Match entier | 16136 | 0,864 | 1,1 % | 0,6 % |
| tous | Total | Temps réglementaire | 1800 | 0,879 | 1,1 % | 0,2 % |
| tous | Handicap | Autre partie (MT2, quart-temps, set, période) | 4200 | 0,877 | 1,0 % | 0,0 % |
| pmu | Total | Match entier | 5944 | 0,878 | 1,0 % | 0,0 % |
| pmu | Total | 1re mi-temps | 2428 | 0,852 | 0,9 % | 0,8 % |
| tous | 1N2 / vainqueur | Match entier | 17997 | 0,884 | 0,9 % | 0,2 % |
| betclic | 1N2 / vainqueur | Match entier | 2100 | 0,913 | 0,9 % | 0,0 % |
| pmu | Double chance | Temps réglementaire | 600 | 0,942 | 0,8 % | 0,0 % |
| winamax | 1N2 / vainqueur | Match entier | 2409 | 0,881 | 0,7 % | 0,2 % |
| tous | Total | Match entier | 17076 | 0,862 | 0,7 % | 0,0 % |
| pmu | Total d'une équipe | Match entier | 5400 | 0,871 | 0,7 % | 0,2 % |
| tous | Score exact | 1re mi-temps | 1500 | 0,742 | 0,6 % | 0,5 % |
| betclic | Handicap | Match entier | 3000 | 0,899 | 0,6 % | 0,0 % |
| pmu | Total | Autre partie (MT2, quart-temps, set, période) | 3000 | 0,856 | 0,6 % | 0,1 % |
| tous | Handicap | Temps réglementaire | 910 | 0,886 | 0,5 % | 0,5 % |
| tous | Total | 1re mi-temps | 5728 | 0,863 | 0,5 % | 0,3 % |
| betclic | Total | 1re mi-temps | 1500 | 0,875 | 0,5 % | 0,0 % |
| pmu | Handicap | 1re mi-temps | 1814 | 0,858 | 0,4 % | 0,1 % |
| tous | Total d'une équipe | 1re mi-temps | 19800 | 0,864 | 0,3 % | 0,0 % |
| tous | Double chance | Temps réglementaire | 1800 | 0,902 | 0,3 % | 0,0 % |
| winamax | Handicap | Match entier | 3012 | 0,865 | 0,3 % | 0,1 % |
| olybet | 1N2 / vainqueur | Match entier | 2078 | 0,871 | 0,2 % | 0,2 % |
| tous | Total | Autre partie (MT2, quart-temps, set, période) | 7886 | 0,863 | 0,2 % | 0,0 % |
| unibet-fr | Total | Match entier | 3000 | 0,855 | 0,2 % | 0,0 % |
| unibet-fr | Handicap | Match entier | 2700 | 0,851 | 0,2 % | 0,0 % |
| tous | Handicap | 1re mi-temps | 4514 | 0,863 | 0,2 % | 0,0 % |
| unibet-fr | 1N2 / vainqueur | Match entier | 4210 | 0,871 | 0,1 % | 0,0 % |
| tous | Total d'une équipe | Match entier | 33616 | 0,867 | 0,1 % | 0,0 % |
| netbet | 1N2 / vainqueur | Match entier | 2100 | 0,882 | 0,1 % | 0,0 % |
| netbet | Handicap | Match entier | 2400 | 0,843 | 0,0 % | 0,0 % |
| winamax | Double chance | Match entier | 300 | 0,909 | 0,0 % | 0,0 % |
| tous | Double chance | Match entier | 2100 | 0,902 | 0,0 % | 0,0 % |
| winamax | Remboursé si nul | Match entier | 300 | 0,858 | 0,0 % | 0,0 % |
| tous | Remboursé si nul | Match entier | 2100 | 0,860 | 0,0 % | 0,0 % |
| winamax | Total d'une équipe | Match entier | 20416 | 0,861 | 0,0 % | 0,0 % |
| winamax | Score exact | 1re mi-temps | 300 | 0,766 | 0,0 % | 0,0 % |
| winamax | Total | Match entier | 3032 | 0,862 | 0,0 % | 0,0 % |
| winamax | Double chance | 1re mi-temps | 300 | 0,889 | 0,0 % | 0,0 % |
| tous | Double chance | 1re mi-temps | 1200 | 0,882 | 0,0 % | 0,0 % |
| winamax | Remboursé si nul | 1re mi-temps | 300 | 0,852 | 0,0 % | 0,0 % |
| tous | Remboursé si nul | 1re mi-temps | 1200 | 0,844 | 0,0 % | 0,0 % |
| winamax | Les deux marquent | 1re mi-temps | 300 | 0,828 | 0,0 % | 0,0 % |
| tous | Les deux marquent | 1re mi-temps | 1200 | 0,844 | 0,0 % | 0,0 % |
| winamax | 1N2 / vainqueur | 1re mi-temps | 300 | 0,808 | 0,0 % | 0,0 % |
| tous | 1N2 / vainqueur | 1re mi-temps | 2108 | 0,839 | 0,0 % | 0,0 % |
| winamax | Les deux marquent | Match entier | 300 | 0,861 | 0,0 % | 0,0 % |
| tous | Les deux marquent | Match entier | 2400 | 0,867 | 0,0 % | 0,0 % |
| winamax | Total d'une équipe | 1re mi-temps | 14400 | 0,861 | 0,0 % | 0,0 % |
| winamax | Handicap | 1re mi-temps | 1200 | 0,865 | 0,0 % | 0,0 % |
| winamax | Total | 1re mi-temps | 1200 | 0,865 | 0,0 % | 0,0 % |
| winamax | Score exact | Match entier | 300 | 0,669 | 0,0 % | 0,0 % |
| tous | Score exact | Match entier | 2100 | 0,661 | 0,0 % | 0,0 % |
| winamax | 1N2 / vainqueur | Autre partie (MT2, quart-temps, set, période) | 300 | 0,872 | 0,0 % | 0,0 % |
| winamax | Total | Autre partie (MT2, quart-temps, set, période) | 1500 | 0,868 | 0,0 % | 0,0 % |
| winamax | Handicap | Autre partie (MT2, quart-temps, set, période) | 900 | 0,858 | 0,0 % | 0,0 % |
| winamax | Double chance | Temps réglementaire | 300 | 0,904 | 0,0 % | 0,0 % |
| betclic | Double chance | Match entier | 600 | 0,914 | 0,0 % | 0,0 % |
| betclic | Les deux marquent | Match entier | 300 | 0,861 | 0,0 % | 0,0 % |
| betclic | Total d'une équipe | Match entier | 3600 | 0,883 | 0,0 % | 0,0 % |
| betclic | Handicap à 3 issues | Match entier | 300 | 0,873 | 0,0 % | 0,0 % |
| tous | Handicap à 3 issues | Match entier | 1500 | 0,834 | 0,0 % | 0,0 % |
| betclic | Score exact | Match entier | 300 | 0,709 | 0,0 % | 0,0 % |
| betclic | Total | Autre partie (MT2, quart-temps, set, période) | 2486 | 0,874 | 0,0 % | 0,0 % |
| betclic | Handicap | Autre partie (MT2, quart-temps, set, période) | 2100 | 0,882 | 0,0 % | 0,0 % |
| betclic | 1N2 / vainqueur | Autre partie (MT2, quart-temps, set, période) | 944 | 0,878 | 0,0 % | 0,0 % |
| betclic | 1N2 / vainqueur | Temps réglementaire | 600 | 0,896 | 0,0 % | 0,0 % |
| tous | 1N2 / vainqueur | Temps réglementaire | 2700 | 0,875 | 0,0 % | 0,0 % |
| betclic | Total d'une équipe | Temps réglementaire | 600 | 0,892 | 0,0 % | 0,0 % |
| tous | Total d'une équipe | Temps réglementaire | 3300 | 0,863 | 0,0 % | 0,0 % |
| betclic | Total d'une équipe | Autre partie (MT2, quart-temps, set, période) | 3000 | 0,861 | 0,0 % | 0,0 % |
| betclic | Double chance | Temps réglementaire | 300 | 0,910 | 0,0 % | 0,0 % |
| betclic | Total | Temps réglementaire | 600 | 0,878 | 0,0 % | 0,0 % |
| betclic | Handicap | 1re mi-temps | 1200 | 0,881 | 0,0 % | 0,0 % |
| unibet-fr | Double chance | Match entier | 600 | 0,921 | 0,0 % | 0,0 % |
| unibet-fr | Score exact | Match entier | 600 | 0,675 | 0,0 % | 0,0 % |
| unibet-fr | Les deux marquent | Match entier | 600 | 0,859 | 0,0 % | 0,0 % |
| unibet-fr | Handicap à 3 issues | Match entier | 600 | 0,848 | 0,0 % | 0,0 % |
| unibet-fr | Total d'une équipe | Match entier | 3600 | 0,878 | 0,0 % | 0,0 % |
| unibet-fr | Remboursé si nul | Match entier | 600 | 0,876 | 0,0 % | 0,0 % |
| unibet-fr | 1N2 / vainqueur | Autre partie (MT2, quart-temps, set, période) | 900 | 0,849 | 0,0 % | 0,0 % |
| unibet-fr | Handicap | Autre partie (MT2, quart-temps, set, période) | 300 | 0,835 | 0,0 % | 0,0 % |
| unibet-fr | Total | Autre partie (MT2, quart-temps, set, période) | 900 | 0,822 | 0,0 % | 0,0 % |
| unibet-fr | Double chance | Temps réglementaire | 600 | 0,880 | 0,0 % | 0,0 % |
| pmu | 1N2 / vainqueur | 1re mi-temps | 608 | 0,836 | 0,0 % | 0,0 % |
| pmu | Score exact | 1re mi-temps | 600 | 0,684 | 0,0 % | 0,0 % |
| pmu | Handicap à 3 issues | Match entier | 300 | 0,801 | 0,0 % | 0,0 % |
| pmu | Remboursé si nul | 1re mi-temps | 600 | 0,844 | 0,0 % | 0,0 % |
| pmu | Score exact | Match entier | 600 | 0,617 | 0,0 % | 0,0 % |
| pmu | Les deux marquent | Match entier | 600 | 0,892 | 0,0 % | 0,0 % |
| pmu | Les deux marquent | 1re mi-temps | 600 | 0,862 | 0,0 % | 0,0 % |
| pmu | Remboursé si nul | Match entier | 600 | 0,855 | 0,0 % | 0,0 % |
| pmu | Double chance | Match entier | 300 | 0,900 | 0,0 % | 0,0 % |
| pmu | Double chance | 1re mi-temps | 600 | 0,878 | 0,0 % | 0,0 % |
| pmu | 1N2 / vainqueur | Temps réglementaire | 600 | 0,873 | 0,0 % | 0,0 % |
| pmu | Total d'une équipe | Temps réglementaire | 900 | 0,859 | 0,0 % | 0,0 % |
| netbet | Double chance | Match entier | 300 | 0,829 | 0,0 % | 0,0 % |
| winamax | Total d'une équipe | Temps réglementaire | 600 | 0,865 | 0,0 % | 0,0 % |
| unibet-fr | Total d'une équipe | Temps réglementaire | 1200 | 0,850 | 0,0 % | 0,0 % |
| pmu | Les deux marquent | Autre partie (MT2, quart-temps, set, période) | 600 | 0,858 | 0,0 % | 0,0 % |
| tous | Les deux marquent | Autre partie (MT2, quart-temps, set, période) | 900 | 0,845 | 0,0 % | 0,0 % |
| betclic | Remboursé si nul | Match entier | 300 | 0,890 | 0,0 % | 0,0 % |
| betclic | Total d'une équipe | 1re mi-temps | 1200 | 0,881 | 0,0 % | 0,0 % |
| winamax | 1N2 / vainqueur | Temps réglementaire | 300 | 0,874 | 0,0 % | 0,0 % |
| unibet-fr | Total | Temps réglementaire | 600 | 0,855 | 0,0 % | 0,0 % |
| betclic | 1N2 / vainqueur | 1re mi-temps | 600 | 0,856 | 0,0 % | 0,0 % |
| olybet | Handicap à 3 issues | Match entier | 300 | 0,806 | 0,0 % | 0,0 % |
| olybet | 1N2 / vainqueur | 1re mi-temps | 300 | 0,843 | 0,0 % | 0,0 % |
| olybet | Handicap | Match entier | 600 | 0,862 | 0,0 % | 0,0 % |
| olybet | Total | Match entier | 300 | 0,869 | 0,0 % | 0,0 % |
| olybet | Les deux marquent | Match entier | 300 | 0,871 | 0,0 % | 0,0 % |
| olybet | Total d'une équipe | Match entier | 600 | 0,869 | 0,0 % | 0,0 % |
| olybet | Score exact | Match entier | 300 | 0,611 | 0,0 % | 0,0 % |
| olybet | Remboursé si nul | Match entier | 300 | 0,874 | 0,0 % | 0,0 % |
| olybet | 1N2 / vainqueur | Temps réglementaire | 600 | 0,867 | 0,0 % | 0,0 % |
| netbet | Total | Match entier | 2400 | 0,834 | 0,0 % | 0,0 % |
| netbet | Les deux marquent | Match entier | 300 | 0,859 | 0,0 % | 0,0 % |
| netbet | Handicap | Temps réglementaire | 300 | 0,817 | 0,0 % | 0,0 % |
| netbet | 1N2 / vainqueur | Temps réglementaire | 300 | 0,858 | 0,0 % | 0,0 % |
| unibet-fr | 1N2 / vainqueur | Temps réglementaire | 300 | 0,854 | 0,0 % | 0,0 % |
| betclic | Handicap | Temps réglementaire | 600 | 0,908 | 0,0 % | 0,0 % |
| unibet-fr | 1N2 / vainqueur | 1re mi-temps | 300 | 0,869 | 0,0 % | 0,0 % |
| unibet-fr | Double chance | 1re mi-temps | 300 | 0,893 | 0,0 % | 0,0 % |
| unibet-fr | Remboursé si nul | 1re mi-temps | 300 | 0,855 | 0,0 % | 0,0 % |
| unibet-fr | Total | 1re mi-temps | 600 | 0,851 | 0,0 % | 0,0 % |
| unibet-fr | Total d'une équipe | 1re mi-temps | 1200 | 0,854 | 0,0 % | 0,0 % |
| unibet-fr | Handicap | 1re mi-temps | 300 | 0,842 | 0,0 % | 0,0 % |
| unibet-fr | Score exact | 1re mi-temps | 300 | 0,687 | 0,0 % | 0,0 % |
| unibet-fr | Total d'une équipe | Autre partie (MT2, quart-temps, set, période) | 600 | 0,806 | 0,0 % | 0,0 % |
| unibet-fr | Les deux marquent | 1re mi-temps | 300 | 0,788 | 0,0 % | 0,0 % |
| unibet-fr | Les deux marquent | Autre partie (MT2, quart-temps, set, période) | 300 | 0,812 | 0,0 % | 0,0 % |
| netbet | 1N2 / vainqueur | Autre partie (MT2, quart-temps, set, période) | 300 | 0,852 | 0,0 % | 0,0 % |
