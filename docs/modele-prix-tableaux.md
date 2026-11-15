# Modèle de prix : tous les tableaux

Sortie de `python scripts/modele_prix.py mesurer` puis `regler`, le 15/11/2026, sur les fichiers de
football-data.co.uk lus le 14/11/2026. Conclusions et lecture : [modele-prix.md](modele-prix.md).

Matchs lus : 174 333 du 02/03/2012 au 09/11/2026. Réglage : 60 761 matchs (01/07/2014 au 30/06/2019). Test : 89 162 matchs depuis le 01/07/2019, dont 77 461 avec la clôture Pinnacle.
Elo : P(domicile) = σ(0,604·x − 0,598), x en centaines de points. Poisson + tirs : buts attendus = exp(-0,362) · (buts attendus)^0,773 · (tirs cadrés attendus)^0,293.

## 1. Les modèles face à Pinnacle (test, matchs jamais vus par les réglages)

Écart de log-loss avec la référence, ×10⁴, intervalle à 95 % par bootstrap sur les matchs ; positif = le modèle est moins bon. Pente : 1 = calibré, moins de 1 = probabilités trop tranchées.

| Marché | Modèle | Matchs | Log-loss modèle | Log-loss Pinnacle | Écart | Brier modèle | Brier Pinnacle | Pente modèle | Pente Pinnacle |
|---|---|---|---|---|---|---|---|---|---|
| 1N2 | Elo | 77 461 | 1,0214 | 1,0011 | **+203,3 [+190,0 ; +217,8]** | 0,6124 | 0,5986 | 0,956 ± 0,018 | 1,007 ± 0,017 |
| 1N2 | Poisson (Dixon-Coles) | 77 461 | 1,0218 | 1,0011 | **+207,5 [+194,4 ; +220,2]** | 0,6127 | 0,5986 | 1,046 ± 0,020 | 1,007 ± 0,017 |
| 1N2 | Poisson + tirs cadrés | 45 300 | 1,0149 | 0,9969 | **+179,6 [+164,8 ; +194,4]** | 0,6079 | 0,5957 | 1,111 ± 0,026 | 1,016 ± 0,023 |
| Total 2,5 buts | Poisson (Dixon-Coles) | 48 504 | 0,6856 | 0,6745 | **+110,6 [+99,0 ; +122,1]** | 0,4923 | 0,4818 | 0,677 ± 0,044 | 1,006 ± 0,048 |
| Total 2,5 buts | Poisson + tirs cadrés | 45 212 | 0,6835 | 0,6739 | **+96,1 [+86,2 ; +106,8]** | 0,4903 | 0,4812 | 0,734 ± 0,046 | 1,007 ± 0,049 |
| Handicap asiatique | Poisson (Dixon-Coles) | 19 591 | 0,7126 | 0,6927 | **+199,8 [+173,4 ; +226,2]** | 0,5183 | 0,4995 | 0,300 ± 0,073 | 0,673 ± 0,264 |
| Handicap asiatique | Poisson + tirs cadrés | 18 290 | 0,7099 | 0,6926 | **+172,9 [+147,8 ; +197,5]** | 0,5159 | 0,4995 | 0,300 ± 0,082 | 0,685 ± 0,273 |

Poisson + tirs moins Poisson, sur les mêmes matchs : 1N2 **-25,3 [-29,1 ; -21,6]** (45 300 matchs) ; total 2,5 buts **-18,8 [-22,6 ; -15,1]** (45 212 matchs).

Repère 1N2 : fréquences fixes (domicile 44,7 %, nul 26,1 %, extérieur 29,2 %) : log-loss 1,0764. Pinnacle gagne 0,0753 sur ce repère ; part de ce gain obtenue par chaque modèle : Elo 73 % ; Poisson (Dixon-Coles) 72 %.

### Calibration par tranche (1N2, toutes issues, test, modèle Poisson)

| Tranche | Issues (modèle) | Annoncé par le modèle | Observé | Issues (Pinnacle) | Annoncé par Pinnacle | Observé |
|---|---|---|---|---|---|---|
| 0 à 5 % | 294 | 3,87 | 3,40 ± 2,07 | 1 155 | 3,57 | 2,68 ± 0,93 |
| 5 à 10 % | 2 201 | 7,99 | 6,68 ± 1,04 | 4 605 | 7,89 | 7,14 ± 0,74 |
| 10 à 20 % | 19 487 | 16,32 | 15,45 ± 0,51 | 27 276 | 15,96 | 16,15 ± 0,44 |
| 20 à 30 % | 96 676 | 25,87 | 25,92 ± 0,28 | 88 613 | 25,80 | 25,74 ± 0,29 |
| 30 à 40 % | 53 982 | 34,19 | 33,63 ± 0,40 | 49 179 | 33,96 | 33,98 ± 0,42 |
| 40 à 50 % | 32 627 | 44,59 | 44,67 ± 0,54 | 28 352 | 44,62 | 44,65 ± 0,58 |
| 50 à 60 % | 17 103 | 54,34 | 55,08 ± 0,75 | 17 718 | 54,59 | 54,15 ± 0,73 |
| 60 à 70 % | 6 962 | 64,17 | 67,22 ± 1,10 | 9 085 | 64,42 | 64,94 ± 0,98 |
| 70 à 80 % | 2 435 | 74,09 | 76,51 ± 1,68 | 4 370 | 74,22 | 75,58 ± 1,27 |
| 80 à 100 % | 616 | 83,85 | 87,34 ± 2,63 | 2 030 | 85,10 | 84,83 ± 1,56 |

## 2. Le modèle apporte-t-il une information que la référence n'a pas ?

Mélange p ∝ référence^a · modèle^b. « b » : poids du modèle (0 = il n'apporte rien), ajusté sur la période d'ajustement puis figé. « Gain hors échantillon » : log-loss du mélange figé moins celui de la référence recalibrée seule (a ajusté sur la même période, b = 0), ×10⁴, sur la période de jugement ; négatif = le modèle ajoute de l'information. « b sur la période de jugement » : ajusté sur elle-même, ± 1,96 erreur type.

| Marché | Référence | Modèle | Matchs d'ajustement | a · b ajustés | Gain hors échantillon | Matchs de jugement | b sur la période de jugement |
|---|---|---|---|---|---|---|---|
| 1N2 | Pinnacle, clôture | Elo | 59 806 | 1,119 · -0,114 | +0,2 [-1,2 ; +1,7] | 77 461 | **-0,051 ± 0,040** |
| 1N2 | Pinnacle, clôture | Poisson (Dixon-Coles) | 59 806 | 1,111 · -0,112 | **-1,3 [-2,5 ; -0,1]** | 77 461 | **-0,106 ± 0,045** |
| 1N2 | Pinnacle, clôture | Poisson + tirs cadrés | 26 537 | 1,127 · -0,127 | **-2,6 [-4,2 ; -1,1]** | 45 300 | **-0,183 ± 0,070** |
| 1N2 | Pinnacle, avant-match | Elo | 38 282 | 1,135 · -0,138 | -1,1 [-3,0 ; +0,7] | 48 407 | **-0,103 ± 0,058** |
| 1N2 | Pinnacle, avant-match | Poisson (Dixon-Coles) | 38 282 | 1,074 · -0,073 | **-1,6 [-2,5 ; -0,7]** | 48 407 | **-0,155 ± 0,066** |
| 1N2 | Pinnacle, avant-match | Poisson + tirs cadrés | 26 331 | 1,075 · -0,069 | **-1,4 [-2,1 ; -0,6]** | 45 136 | **-0,169 ± 0,076** |
| 1N2 | bet365, clôture | Elo | 22 341 | 1,038 · -0,090 | +0,2 [-1,4 ; +1,7] | 38 937 | -0,040 ± 0,057 |
| 1N2 | bet365, clôture | Poisson (Dixon-Coles) | 22 341 | 1,048 · -0,114 | -1,2 [-2,9 ; +0,5] | 38 937 | **-0,106 ± 0,066** |
| 1N2 | bet365, clôture | Poisson + tirs cadrés | 20 903 | 1,070 · -0,144 | -1,4 [-3,5 ; +0,7] | 31 105 | **-0,137 ± 0,084** |
| 1N2 | bet365, avant-match | Elo | 38 909 | 1,102 · -0,123 | -0,6 [-2,1 ; +1,1] | 55 577 | **-0,080 ± 0,053** |
| 1N2 | bet365, avant-match | Poisson (Dixon-Coles) | 38 909 | 1,031 · -0,042 | **-0,7 [-1,2 ; -0,3]** | 55 577 | **-0,116 ± 0,061** |
| 1N2 | bet365, avant-match | Poisson + tirs cadrés | 26 555 | 1,026 · -0,028 | **-0,4 [-0,7 ; -0,1]** | 51 936 | **-0,120 ± 0,070** |
| 1N2 | Moyenne du marché, clôture | Elo | 21 767 | 1,109 · -0,100 | -0,8 [-2,0 ; +0,2] | 89 006 | **-0,077 ± 0,038** |
| 1N2 | Moyenne du marché, clôture | Poisson (Dixon-Coles) | 21 767 | 1,133 · -0,133 | **-2,0 [-3,4 ; -0,7]** | 89 006 | **-0,135 ± 0,043** |
| 1N2 | Moyenne du marché, clôture | Poisson + tirs cadrés | 20 931 | 1,162 · -0,210 | **-3,6 [-6,5 ; -0,6]** | 31 096 | **-0,208 ± 0,087** |
| 1N2 | Betfair Exchange, clôture | Elo | — | — | — | 27 451 | **-0,114 ± 0,069** |
| 1N2 | Betfair Exchange, clôture | Poisson (Dixon-Coles) | — | — | — | 27 451 | **-0,166 ± 0,078** |
| 1N2 | Betfair Exchange, clôture | Poisson + tirs cadrés | — | — | — | 16 187 | **-0,179 ± 0,116** |
| Total 2,5 buts | Pinnacle, clôture | Poisson (Dixon-Coles) | 22 337 | 1,148 · -0,193 | -1,0 [-4,1 ; +2,0] | 26 167 | **-0,127 ± 0,094** |
| Total 2,5 buts | Pinnacle, clôture | Poisson + tirs cadrés | 20 899 | 1,142 · -0,168 | **-2,5 [-5,0 ; -0,1]** | 24 313 | **-0,193 ± 0,109** |
| Total 2,5 buts | Pinnacle, avant-match | Poisson (Dixon-Coles) | 22 222 | 1,100 · -0,114 | -0,6 [-2,4 ; +1,1] | 26 087 | -0,092 ± 0,099 |
| Total 2,5 buts | Pinnacle, avant-match | Poisson + tirs cadrés | 20 790 | 1,060 · -0,057 | -0,7 [-1,5 ; +0,1] | 24 247 | **-0,129 ± 0,114** |
| Total 2,5 buts | bet365, clôture | Poisson (Dixon-Coles) | 22 336 | 1,130 · -0,188 | +0,2 [-2,3 ; +2,8] | 33 316 | **-0,086 ± 0,082** |
| Total 2,5 buts | bet365, clôture | Poisson + tirs cadrés | 20 898 | 1,126 · -0,167 | -1,1 [-3,3 ; +1,2] | 31 099 | **-0,130 ± 0,094** |
| Handicap asiatique | Pinnacle, clôture | Poisson (Dixon-Coles) | 8 924 | 0,797 · -0,146 | +1,9 [-3,2 ; +7,1] | 10 667 | -0,035 ± 0,102 |
| Handicap asiatique | Pinnacle, clôture | Poisson + tirs cadrés | 8 374 | 0,791 · -0,137 | +0,1 [-4,5 ; +4,7] | 9 916 | -0,067 ± 0,117 |
| Handicap asiatique | Pinnacle, avant-match | Poisson (Dixon-Coles) | 9 041 | 1,248 · -0,181 | +2,6 [-3,7 ; +8,2] | 10 648 | -0,041 ± 0,112 |
| Handicap asiatique | Pinnacle, avant-match | Poisson + tirs cadrés | 8 494 | 1,268 · -0,164 | +1,8 [-3,2 ; +6,8] | 9 894 | -0,038 ± 0,127 |

## 3. Où ? Poids du modèle par segment (1N2, clôture Pinnacle, test)

Modèle : Poisson (toutes les ligues). « b » ajusté sur le segment lui-même (descriptif) ; p corrigée de Holm sur tous les segments du tableau. « Écart » : log-loss du modèle moins celui de Pinnacle, ×10⁴.

| Segment | Matchs | Écart modèle − Pinnacle | b (poids du modèle) | p corrigée (Holm) |
|---|---|---|---|---|
| Tous | 77 461 | **+207,5 [+194,8 ; +220,5]** | -0,106 ± 0,045 | 0,000 |
| Cinq grands championnats, 1re division | 11 605 | **+199,5 [+169,0 ; +232,3]** | -0,178 ± 0,130 | 0,095 |
| Cinq grands championnats, 2e division | 13 041 | **+183,7 [+154,2 ; +212,9]** | -0,177 ± 0,119 | 0,056 |
| Divisions inférieures (Angleterre 3 à 5, Écosse 2 à 4) | 13 048 | **+181,3 [+150,0 ; +213,4]** | -0,060 ± 0,120 | 1,000 |
| Autres 1res divisions d'Europe (Écosse, Pays-Bas, Belgique, Portugal, Turquie, Grèce) | 10 898 | **+248,9 [+214,6 ; +281,1]** | -0,185 ± 0,119 | 0,040 |
| 16 ligues supplémentaires (Amériques, Asie, Nord et Est de l'Europe) | 28 869 | **+217,8 [+194,7 ; +241,1]** | -0,061 ± 0,068 | 0,605 |
| Début de saison (une équipe à moins de 6 matchs joués) | 13 949 | **+250,9 [+219,0 ; +281,9]** | -0,200 ± 0,102 | 0,002 |
| Reste de la saison | 63 512 | **+198,0 [+183,1 ; +211,9]** | -0,083 ± 0,050 | 0,023 |
| Favori Pinnacle à moins de 45 % | 31 843 | **+162,6 [+145,6 ; +179,4]** | -0,141 ± 0,070 | 0,002 |
| Favori de 45 à 60 % | 30 133 | **+180,0 [+159,3 ; +200,9]** | -0,076 ± 0,072 | 0,379 |
| Favori à 60 % et plus | 15 485 | **+353,7 [+318,0 ; +392,1]** | -0,083 ± 0,106 | 0,805 |
| Désaccord modèle / Pinnacle sous 5 points | 33 541 | **+31,4 [+24,1 ; +38,9]** | -0,152 ± 0,155 | 0,500 |
| Désaccord de 5 à 10 points | 26 190 | **+164,6 [+145,1 ; +182,5]** | -0,146 ± 0,087 | 0,019 |
| Désaccord de 10 points et plus | 17 730 | **+604,3 [+558,0 ; +652,7]** | -0,083 ± 0,068 | 0,198 |
| Matchs à huis clos (mars 2020 à juin 2021) | 13 656 | **+224,4 [+190,6 ; +257,7]** | -0,114 ± 0,099 | 0,262 |
| Décembre à février | 18 925 | **+176,3 [+151,0 ; +202,0]** | -0,078 ± 0,096 | 0,805 |
| Année 2019 | 6 337 | **+136,7 [+93,4 ; +181,6]** | 0,099 ± 0,160 | 1,000 |
| Année 2020 | 9 529 | **+201,3 [+161,6 ; +240,6]** | -0,073 ± 0,118 | 1,000 |
| Année 2021 | 13 104 | **+219,1 [+187,9 ; +249,5]** | -0,160 ± 0,111 | 0,069 |
| Année 2022 | 12 255 | **+245,3 [+211,5 ; +278,6]** | -0,163 ± 0,113 | 0,069 |
| Année 2023 | 12 710 | **+206,2 [+176,2 ; +237,7]** | -0,060 ± 0,112 | 1,000 |
| Année 2024 | 12 414 | **+225,3 [+192,8 ; +257,9]** | -0,226 ± 0,115 | 0,002 |
| Année 2025 | 10 953 | **+181,1 [+147,9 ; +214,3]** | -0,049 ± 0,123 | 1,000 |

## 4. Le modèle annonce-t-il le mouvement de Pinnacle entre l'avant-match et la clôture ?

Régression de (clôture − avant-match) sur (modèle − avant-match), en logit de la victoire à domicile (ou du « plus de 2,5 »). Pente 0 : le modèle ne sait rien que l'avant-match ne sache ; pente 1 : la clôture rejoint le modèle.

| Marché | Modèle | Période | Matchs | Pente | Part du mouvement expliquée |
|---|---|---|---|---|---|
| 1N2, domicile | Elo | réglage | 37 630 | **0,023 ± 0,006** | 0,24 % |
| 1N2, domicile | Elo | test | 48 393 | -0,001 ± 0,005 | 0,00 % |
| 1N2, domicile | Poisson (Dixon-Coles) | réglage | 37 630 | **0,033 ± 0,005** | 0,57 % |
| 1N2, domicile | Poisson (Dixon-Coles) | test | 48 393 | 0,004 ± 0,005 | 0,01 % |
| 1N2, domicile | Poisson + tirs cadrés | réglage | 26 319 | **0,040 ± 0,007** | 0,79 % |
| 1N2, domicile | Poisson + tirs cadrés | test | 45 122 | **0,023 ± 0,006** | 0,19 % |
| Total 2,5 buts, plus | Poisson (Dixon-Coles) | test | 48 294 | **0,043 ± 0,005** | 0,66 % |
| Total 2,5 buts, plus | Poisson + tirs cadrés | test | 45 022 | **0,072 ± 0,006** | 1,50 % |

## 5. Parier avec ou contre le modèle (test, cote ≤ 5, 1N2)

Un pari par issue retenue, mise fixe. ROI par pari, intervalle à 95 % par bootstrap sur les matchs. « Avec le modèle » : la cote dépasse la cote juste du modèle d'au moins le seuil. « Contre le modèle » : Pinnacle (sans marge, au même moment) donne à l'issue une probabilité supérieure d'au moins le seuil à celle du modèle. « Pinnacle (méthode du site) » : la cote dépasse la cote juste Pinnacle du seuil.

| Cotes jouées | Sélection | Seuil | Paris | Cote moyenne | Écart moyen selon le modèle | Écart moyen selon Pinnacle | ROI en % [IC 95 %] |
|---|---|---|---|---|---|---|---|
| Pinnacle, clôture | Toutes les issues | — | 204 709 | 3,00 | — | -3,5 % | **-3,5 [-3,8 ; -3,3]** |
| Pinnacle, clôture | Avec le modèle Poisson | ≥ 2 % | 64 170 | 3,37 | +15,3 % | -4,0 % | **-6,1 [-7,2 ; -4,9]** |
| Pinnacle, clôture | Avec le modèle Poisson | ≥ 5 % | 51 270 | 3,42 | +18,3 % | -4,0 % | **-6,1 [-7,4 ; -4,9]** |
| Pinnacle, clôture | Avec le modèle Poisson | ≥ 10 % | 35 228 | 3,49 | +23,3 % | -4,1 % | **-6,9 [-8,5 ; -5,2]** |
| Pinnacle, clôture | Contre le modèle Poisson | ≥ 10 % | 54 623 | 2,50 | -20,5 % | -2,9 % | **-1,1 [-2,1 ; -0,1]** |
| Pinnacle, clôture | Contre le modèle Poisson | ≥ 25 % | 17 564 | 2,39 | -29,8 % | -2,8 % | -1,2 [-2,9 ; +0,6] |
| Pinnacle, clôture | Contre le modèle Poisson | ≥ 50 % | 3 113 | 2,47 | -41,9 % | -3,0 % | -2,3 [-6,5 ; +2,0] |
| Pinnacle, clôture | Avec le modèle Poisson + tirs | ≥ 2 % | 35 661 | 3,42 | +13,7 % | -3,9 % | **-7,8 [-9,3 ; -6,3]** |
| Pinnacle, clôture | Avec le modèle Poisson + tirs | ≥ 5 % | 27 797 | 3,48 | +16,7 % | -4,0 % | **-8,1 [-9,8 ; -6,3]** |
| Pinnacle, clôture | Avec le modèle Poisson + tirs | ≥ 10 % | 18 343 | 3,57 | +21,5 % | -4,1 % | **-9,2 [-11,2 ; -7,0]** |
| Pinnacle, clôture | Contre le modèle Poisson + tirs | ≥ 10 % | 28 836 | 2,41 | -18,9 % | -2,7 % | -0,1 [-1,3 ; +1,2] |
| Pinnacle, clôture | Contre le modèle Poisson + tirs | ≥ 25 % | 7 047 | 2,27 | -28,1 % | -2,6 % | +0,4 [-2,2 ; +2,9] |
| Pinnacle, clôture | Contre le modèle Poisson + tirs | ≥ 50 % | 835 | 2,34 | -40,7 % | -2,8 % | +1,3 [-6,3 ; +9,0] |
| bet365, avant-match | Toutes les issues | — | 131 250 | 2,96 | — | -6,2 % | **-6,3 [-6,5 ; -6,0]** |
| bet365, avant-match | Avec le modèle Poisson | ≥ 2 % | 31 726 | 3,40 | +13,1 % | -6,4 % | **-9,5 [-11,1 ; -7,9]** |
| bet365, avant-match | Avec le modèle Poisson | ≥ 5 % | 24 055 | 3,46 | +16,1 % | -6,5 % | **-10,4 [-12,3 ; -8,5]** |
| bet365, avant-match | Avec le modèle Poisson | ≥ 10 % | 15 159 | 3,58 | +21,3 % | -6,6 % | **-11,8 [-14,3 ; -9,5]** |
| bet365, avant-match | Contre le modèle Poisson | ≥ 10 % | 30 400 | 2,42 | -21,0 % | -4,8 % | **-3,1 [-4,4 ; -1,7]** |
| bet365, avant-match | Contre le modèle Poisson | ≥ 25 % | 8 040 | 2,34 | -30,2 % | -4,9 % | **-3,3 [-5,9 ; -0,8]** |
| bet365, avant-match | Contre le modèle Poisson | ≥ 50 % | 1 038 | 2,44 | -42,3 % | -5,0 % | -0,0 [-7,4 ; +7,3] |
| bet365, avant-match | Avec le modèle Poisson + tirs | ≥ 2 % | 27 881 | 3,46 | +12,0 % | -6,3 % | **-10,0 [-11,8 ; -8,3]** |
| bet365, avant-match | Avec le modèle Poisson + tirs | ≥ 5 % | 20 578 | 3,54 | +15,0 % | -6,4 % | **-10,7 [-12,8 ; -8,7]** |
| bet365, avant-match | Avec le modèle Poisson + tirs | ≥ 10 % | 12 409 | 3,67 | +20,1 % | -6,5 % | **-11,2 [-13,9 ; -8,5]** |
| bet365, avant-match | Contre le modèle Poisson + tirs | ≥ 10 % | 25 785 | 2,36 | -19,9 % | -4,6 % | **-3,4 [-4,9 ; -2,1]** |
| bet365, avant-match | Contre le modèle Poisson + tirs | ≥ 25 % | 5 470 | 2,27 | -29,4 % | -4,7 % | -1,9 [-4,8 ; +0,9] |
| bet365, avant-match | Contre le modèle Poisson + tirs | ≥ 50 % | 571 | 2,34 | -42,4 % | -4,8 % | +7,6 [-1,7 ; +17,2] |
| bet365, avant-match | Pinnacle (méthode du site) | ≥ 2 % | 1 696 | 3,48 | — | +4,0 % | +1,3 [-6,9 ; +8,6] |
| bet365, avant-match | Pinnacle (méthode du site) | ≥ 5 % | 337 | 3,63 | — | +7,5 % | +9,9 [-7,9 ; +28,1] |
| bet365, clôture | Toutes les issues | — | 134 458 | 2,96 | — | -6,2 % | **-6,2 [-6,5 ; -5,9]** |
| bet365, clôture | Avec le modèle Poisson | ≥ 2 % | 34 626 | 3,42 | +14,6 % | -6,5 % | **-9,4 [-10,9 ; -7,8]** |
| bet365, clôture | Avec le modèle Poisson | ≥ 5 % | 27 169 | 3,48 | +17,6 % | -6,6 % | **-10,3 [-12,0 ; -8,5]** |
| bet365, clôture | Avec le modèle Poisson | ≥ 10 % | 18 227 | 3,57 | +22,6 % | -6,8 % | **-11,1 [-13,2 ; -8,8]** |
| bet365, clôture | Contre le modèle Poisson | ≥ 10 % | 34 564 | 2,42 | -21,7 % | -5,0 % | **-2,9 [-4,1 ; -1,8]** |
| bet365, clôture | Contre le modèle Poisson | ≥ 25 % | 10 237 | 2,28 | -31,0 % | -5,3 % | -2,0 [-4,2 ; +0,2] |
| bet365, clôture | Contre le modèle Poisson | ≥ 50 % | 1 515 | 2,36 | -43,0 % | -5,7 % | **-6,8 [-12,5 ; -1,3]** |
| bet365, clôture | Avec le modèle Poisson + tirs | ≥ 2 % | 29 993 | 3,46 | +13,3 % | -6,5 % | **-10,8 [-12,3 ; -9,2]** |
| bet365, clôture | Avec le modèle Poisson + tirs | ≥ 5 % | 22 966 | 3,53 | +16,3 % | -6,7 % | **-11,3 [-13,2 ; -9,4]** |
| bet365, clôture | Avec le modèle Poisson + tirs | ≥ 10 % | 14 704 | 3,65 | +21,3 % | -6,8 % | **-13,0 [-15,4 ; -10,4]** |
| bet365, clôture | Contre le modèle Poisson + tirs | ≥ 10 % | 28 952 | 2,37 | -20,6 % | -4,8 % | **-2,1 [-3,3 ; -0,8]** |
| bet365, clôture | Contre le modèle Poisson + tirs | ≥ 25 % | 7 073 | 2,23 | -30,0 % | -5,1 % | -2,0 [-4,6 ; +0,5] |
| bet365, clôture | Contre le modèle Poisson + tirs | ≥ 50 % | 843 | 2,31 | -42,3 % | -5,4 % | -2,3 [-10,4 ; +5,4] |
| bet365, clôture | Pinnacle (méthode du site) | ≥ 2 % | 2 199 | 3,36 | — | +4,7 % | +1,4 [-4,8 ; +7,9] |
| bet365, clôture | Pinnacle (méthode du site) | ≥ 5 % | 618 | 3,44 | — | +8,8 % | +6,6 [-5,2 ; +19,2] |
| Meilleure cote du marché, clôture | Toutes les issues | — | 202 045 | 3,07 | — | -0,6 % | **-0,6 [-0,9 ; -0,4]** |
| Meilleure cote du marché, clôture | Avec le modèle Poisson | ≥ 2 % | 76 684 | 3,39 | +15,4 % | -0,9 % | **-3,0 [-4,0 ; -2,1]** |
| Meilleure cote du marché, clôture | Avec le modèle Poisson | ≥ 5 % | 61 463 | 3,44 | +18,4 % | -1,0 % | **-3,2 [-4,4 ; -2,1]** |
| Meilleure cote du marché, clôture | Avec le modèle Poisson | ≥ 10 % | 42 139 | 3,51 | +23,5 % | -1,0 % | **-4,4 [-5,8 ; -2,9]** |
| Meilleure cote du marché, clôture | Contre le modèle Poisson | ≥ 10 % | 54 211 | 2,58 | -17,6 % | +0,7 % | **+2,6 [+1,6 ; +3,6]** |
| Meilleure cote du marché, clôture | Contre le modèle Poisson | ≥ 25 % | 17 380 | 2,46 | -26,9 % | +1,2 % | **+3,1 [+1,3 ; +4,8]** |
| Meilleure cote du marché, clôture | Contre le modèle Poisson | ≥ 50 % | 3 073 | 2,57 | -39,0 % | +1,9 % | +3,6 [-0,7 ; +8,2] |
| Meilleure cote du marché, clôture | Avec le modèle Poisson + tirs | ≥ 2 % | 43 740 | 3,44 | +13,9 % | -0,8 % | **-4,1 [-5,5 ; -2,8]** |
| Meilleure cote du marché, clôture | Avec le modèle Poisson + tirs | ≥ 5 % | 34 107 | 3,50 | +16,9 % | -0,8 % | **-4,9 [-6,4 ; -3,3]** |
| Meilleure cote du marché, clôture | Avec le modèle Poisson + tirs | ≥ 10 % | 22 526 | 3,60 | +21,8 % | -0,9 % | **-6,1 [-8,2 ; -4,1]** |
| Meilleure cote du marché, clôture | Contre le modèle Poisson + tirs | ≥ 10 % | 28 701 | 2,49 | -15,9 % | +0,9 % | **+3,6 [+2,3 ; +4,9]** |
| Meilleure cote du marché, clôture | Contre le modèle Poisson + tirs | ≥ 25 % | 6 994 | 2,35 | -25,2 % | +1,4 % | **+4,5 [+1,9 ; +7,4]** |
| Meilleure cote du marché, clôture | Contre le modèle Poisson + tirs | ≥ 50 % | 832 | 2,46 | -37,7 % | +2,1 % | +6,7 [-1,5 ; +15,1] |
| Meilleure cote du marché, clôture | Pinnacle (méthode du site) | ≥ 2 % | 34 229 | 2,95 | — | +4,9 % | **+3,8 [+2,4 ; +5,2]** |
| Meilleure cote du marché, clôture | Pinnacle (méthode du site) | ≥ 5 % | 11 140 | 3,08 | — | +8,5 % | **+5,6 [+3,1 ; +8,4]** |
| Meilleure cote du marché, clôture | Pinnacle (méthode du site) | ≥ 10 % | 2 407 | 3,20 | — | +15,0 % | **+10,5 [+4,5 ; +16,4]** |

## 6. Le modèle trie-t-il les values repérées par Pinnacle ? (même moment)

Paris que la méthode du site aurait pris (cote ≥ cote juste Pinnacle + 2 %, cote ≤ 5), séparés selon l'avis du modèle Poisson sur la même issue. « Avis » : probabilité du modèle / probabilité Pinnacle − 1. La meilleure cote du marché est celle du plus offrant parmi des dizaines de bookmakers : personne ne l'obtient à chaque pari.

| Cotes jouées | Paris | Nombre | ROI en % [IC 95 %] |
|---|---|---|---|
| bet365, avant-match | Tous | 1 696 | +1,3 [-6,2 ; +8,8] |
| bet365, avant-match | Le modèle donne plus que Pinnacle | 603 | -1,6 [-14,7 ; +12,3] |
| bet365, avant-match | Le modèle donne moins que Pinnacle | 1 093 | +2,9 [-6,1 ; +11,9] |
| bet365, avant-match | Le modèle voit aussi ≥ 2 % d'écart sur la cote | 702 | -4,0 [-15,4 ; +7,9] |
| bet365, avant-match | Le modèle donne au moins 10 % de moins que Pinnacle | 451 | -2,7 [-15,7 ; +11,1] |
| bet365, avant-match | Pente du gain sur l'avis du modèle | 1 696 | 0,06 ± 0,54 |
| bet365, clôture | Tous | 2 199 | +1,4 [-4,3 ; +7,9] |
| bet365, clôture | Le modèle donne plus que Pinnacle | 862 | +1,8 [-8,7 ; +12,8] |
| bet365, clôture | Le modèle donne moins que Pinnacle | 1 337 | +1,1 [-6,5 ; +9,0] |
| bet365, clôture | Le modèle voit aussi ≥ 2 % d'écart sur la cote | 1 014 | +1,8 [-7,6 ; +11,8] |
| bet365, clôture | Le modèle donne au moins 10 % de moins que Pinnacle | 572 | +3,9 [-7,6 ; +16,7] |
| bet365, clôture | Pente du gain sur l'avis du modèle | 2 199 | -0,14 ± 0,38 |
| Meilleure cote du marché, clôture | Tous | 34 229 | **+3,8 [+2,4 ; +5,1]** |
| Meilleure cote du marché, clôture | Le modèle donne plus que Pinnacle | 10 236 | +0,1 [-2,9 ; +3,0] |
| Meilleure cote du marché, clôture | Le modèle donne moins que Pinnacle | 23 993 | **+5,3 [+3,7 ; +6,9]** |
| Meilleure cote du marché, clôture | Le modèle voit aussi ≥ 2 % d'écart sur la cote | 12 480 | +0,7 [-1,9 ; +3,3] |
| Meilleure cote du marché, clôture | Le modèle donne au moins 10 % de moins que Pinnacle | 13 560 | **+7,0 [+4,9 ; +9,1]** |
| Meilleure cote du marché, clôture | Pente du gain sur l'avis du modèle | 34 229 | **-0,19 ± 0,10** |

## Réglage (matchs d'avant le 01/07/2019 seulement)

Sortie de `regler` : recherche coordonnée par coordonnée à partir des réglages retenus ; aucun voisin ne fait
mieux. Oubli des tirs retenu : 0,008 (plateau de 0,008 à 0,012).

```
Matchs d'avant le 01/07/2019 : 85 171, dont notés (depuis le 01/07/2014) : 60 761

## Elo

tour 1, k : 10.0 -> log-loss 1,0173
tour 1, gamma : 0.9 -> log-loss 1,0173
tour 1, terrain : 60.0 -> log-loss 1,0173
tour 1, k_terrain : 1.2 -> log-loss 1,0173
tour 1, retour : 0.2 -> log-loss 1,0173
tour 1, ecart_niveau : 150.0 -> log-loss 1,0173
tour 1, ecart_nouveau : 50.0 -> log-loss 1,0173
tour 2, k : 10.0 -> log-loss 1,0173
tour 2, gamma : 0.9 -> log-loss 1,0173
tour 2, terrain : 60.0 -> log-loss 1,0173
tour 2, k_terrain : 1.2 -> log-loss 1,0173
tour 2, retour : 0.2 -> log-loss 1,0173
tour 2, ecart_niveau : 150.0 -> log-loss 1,0173
tour 2, ecart_nouveau : 50.0 -> log-loss 1,0173

Elo retenu : {'k': 10.0, 'gamma': 0.9, 'terrain': 60.0, 'k_terrain': 1.2, 'retour': 0.2, 'ecart_niveau': 150.0, 'ecart_nouveau': 50.0}, log-loss 1,0173

## Poisson

xi : 0.0026 -> log-loss 1,0173
kappa : 6.0 -> log-loss 1,0173
nouveau : 0.9 -> log-loss 1,0173
rho -0.12 : log-loss 1,0180
rho -0.09 : log-loss 1,0175
rho -0.06 : log-loss 1,0173
rho -0.03 : log-loss 1,0174
rho 0.0 : log-loss 1,0177

Poisson retenu (hors rho) : {'xi': 0.0026, 'kappa': 6.0, 'nouveau': 0.9, 'fenetre': 1460, 'rho': -0.06}

## Poisson + tirs cadrés (matchs avec tirs)

oubli des tirs 0.0026 : 34 715 matchs, coefficients [-0.388  0.754  0.315], log-loss 1,0201 (buts seuls, mêmes matchs : 1,0210)
oubli des tirs 0.005 : 34 715 matchs, coefficients [-0.333  0.781  0.272], log-loss 1,0201 (buts seuls, mêmes matchs : 1,0210)
oubli des tirs 0.008 : 34 715 matchs, coefficients [-0.362  0.773  0.293], log-loss 1,0198 (buts seuls, mêmes matchs : 1,0210)
oubli des tirs 0.012 : 34 715 matchs, coefficients [-0.342  0.789  0.276], log-loss 1,0197 (buts seuls, mêmes matchs : 1,0210)
oubli des tirs 0.02 : 34 715 matchs, coefficients [-0.176  0.867  0.148], log-loss 1,0206 (buts seuls, mêmes matchs : 1,0210)
```
