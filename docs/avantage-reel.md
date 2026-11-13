# Avantage réel : ce que les paris réglés prouvent

Fait le 13/11/2026 sur la branche `donnees` (commit `db927c7`, 18:42 UTC) : 6 227 paris détectés du 05/10 au
13/11, dont 6 027 réglés. Tous les chiffres sortent de `python scripts/avantage_reel.py --donnees <dossier>`
(lecture seule, 8 minutes, graine fixe : deux exécutions donnent les mêmes chiffres). Toutes les colonnes de chaque
ligne : [avantage-reel-tableaux.md](avantage-reel-tableaux.md). ROI = gain / mises, mise fixe de 10 €. Suite de
[audit-bilans.md](audit-bilans.md).

## Conclusion

1. **Aucun avantage n'est prouvé.** 105 lignes regardées (46 stratégies, 24 règles du laboratoire, 6 bookmakers,
   7 références, 12 seuils et tranches, 4 vues d'ensemble), 96 avec assez de paris pour un test. Après correction,
   la meilleure p-valeur vaut 0,50 (Polymarket · 2–5 · ≥ 2 % · ≤ 36 h : +32,5 % sur 165 paris, p brute 0,003).
   6 lignes passent 5 % avant correction pour un ROI positif et 10 pour un ROI négatif : le hasard seul en donne
   environ 5 de chaque côté sur 96.
2. **Un petit avantage est probable sur les cotes ≤ 5, par la CLV et non par le ROI.** Paris uniques, cote ≤ 5 :
   CLV contre la clôture Pinnacle +1,08 % [+0,45 ; +1,73], prouvée après correction ; ROI +3,2 % [−1,4 ; +8,0],
   zéro compris. Les 10 lignes « avantage probable » sont ce même fait vu par morceaux, pas dix découvertes.
3. **Une seule ligne est négative** : OlyBet à cote ≤ 5 (ROI −11,2 %, CLV Pinnacle −3,85 % [−6,59 ; −0,72]).
   Six autres ont un ROI dont l'intervalle est sous zéro, sans tenir après correction : la référence Kalshi
   (−28,4 %, p corrigée 0,10, la plus proche), la référence Pinnacle toutes cotes (−12,1 %), OlyBet toutes cotes
   (−22,7 %), Claude Défi 2 (−45,0 %), Claude Défi 5 (−37,9 %) et Claude Fusion (−33,3 %).
4. **Les 7 stratégies de base et la convergence sont « non prouvé »** : ROI entre −7,5 % et +3,2 %, tous les
   intervalles contiennent zéro, aucune CLV Pinnacle ne tient après correction.
5. **Le ROI ne tranchera pas avant des années.** Si le vrai avantage des cotes ≤ 5 vaut leur CLV (+1 %), il faut
   encore 375 000 paris uniques réglés : 10 ans au rythme actuel (98 par jour).
6. **La CLV Pinnacle prédit le ROI à cote ≤ 5** : un point de CLV vaut 1,23 point de rendement [0,55 ; 1,89]. Les
   clôtures des autres références ne le prédisent pas (pente −0,03 [−0,93 ; +0,90]). Entre stratégies, la CLV ne
   classe encore rien (corrélation −0,44).

Le plafond de cote à 5 a été choisi le 11/11 sur ces mêmes résultats (audit, problème 1). Sans lui, les paris
uniques font −6,1 % [−12,7 ; +4,6]. Le « probable » du point 2 tient à la CLV, qui n'a pas servi à choisir le
plafond ; depuis le plafond, il n'y a que 72 paris réglés (ROI −2,7 % [−24,0 ; +26,1]).

## Verdict par ligne

« p corrigée » : p-valeur de Holm, dans le sens du ROI observé, sur les 192 tests (96 lignes, deux sens).
« — » : trop peu de paris ou de mesures. Les stratégies sont suivies depuis le 14/10 ou depuis leur lancement.
« CLV Pinnacle » : moyenne des seuls paris qui ont une clôture Pinnacle (leur nombre est dans les tableaux
complets ; 28 sur 191 pour la référence Kalshi, par exemple).

### Ensemble

| Ligne | Réglés | ROI | IC 95 % | p corrigée (Holm) | CLV Pinnacle | IC 95 % | Verdict |
|---|---|---|---|---|---|---|---|
| Paris uniques, toutes cotes | 4883 | -6,1 % | [-12,7 ; +4,6] | 1,000 | +1,94 % | [+1,29 ; +2,65] | **non prouvé** : CLV Pinnacle prouvée, ROI négatif |
| Paris uniques, cote ≤ 5 (vue du site) | 3913 | +3,2 % | [-1,4 ; +8,0] | 1,000 | +1,08 % | [+0,45 ; +1,73] | **avantage probable** : CLV Pinnacle prouvée, ROI positif mais non prouvé |
| Paris uniques, cote > 5 | 970 | -43,7 % | [-70,2 ; +22,6] | 1,000 | +6,75 % | [+4,78 ; +9,42] | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Paris uniques pris depuis le plafond (11/11) | 72 | -2,7 % | [-24,0 ; +26,1] | 1,000 | +0,17 % | [-2,84 ; +2,70] | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |

### Bookmakers (paris uniques)

| Ligne | Réglés | ROI | IC 95 % | p corrigée (Holm) | CLV Pinnacle | IC 95 % | Verdict |
|---|---|---|---|---|---|---|---|
| PMU, toutes cotes | 1915 | -0,7 % | [-7,3 ; +6,8] | 1,000 | +2,00 % | [+1,22 ; +2,86] | **non prouvé** : CLV Pinnacle prouvée, ROI négatif |
| PMU, cote ≤ 5 | 1802 | +2,4 % | [-3,9 ; +9,1] | 1,000 | +2,04 % | [+1,32 ; +2,82] | **avantage probable** : CLV Pinnacle prouvée, ROI positif mais non prouvé |
| Betclic, toutes cotes | 1591 | -13,3 % | [-28,6 ; +28,4] | 1,000 | +2,99 % | [+1,94 ; +4,09] | **non prouvé** : CLV Pinnacle prouvée, ROI négatif |
| Betclic, cote ≤ 5 | 1015 | +5,8 % | [-2,7 ; +14,2] | 1,000 | +1,33 % | [+0,10 ; +2,66] | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Winamax, toutes cotes | 545 | +3,2 % | [-12,5 ; +27,0] | 1,000 | -0,15 % | [-1,98 ; +2,07] | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Winamax, cote ≤ 5 | 464 | +5,3 % | [-6,6 ; +17,6] | 1,000 | -1,11 % | [-2,77 ; +0,61] | **non prouvé** : CLV de la meilleure référence négative après correction, ROI positif |
| Unibet, toutes cotes | 479 | -4,7 % | [-21,8 ; +28,7] | 1,000 | +2,93 % | [+0,50 ; +6,82] | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Unibet, cote ≤ 5 | 350 | +7,2 % | [-4,9 ; +20,0] | 1,000 | +0,91 % | [-1,45 ; +3,72] | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| OlyBet, toutes cotes | 275 | -22,7 % | [-38,3 ; -0,8] | 1,000 | -1,71 % | [-4,48 ; +1,61] | **non prouvé** : tendance négative, non confirmée après correction |
| OlyBet, cote ≤ 5 | 214 | -11,2 % | [-29,8 ; +8,2] | 1,000 | -3,85 % | [-6,59 ; -0,72] | **négatif** : ROI négatif et CLV Pinnacle négative après correction |
| NetBet, toutes cotes | 78 | -5,3 % | [-35,5 ; +36,2] | 1,000 | -0,46 % | [-5,99 ; +4,18] | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| NetBet, cote ≤ 5 | 68 | -3,5 % | [-33,9 ; +30,6] | 1,000 | -0,46 % | [-6,01 ; +4,19] | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |

### Références (tous leurs paris)

| Ligne | Réglés | ROI | IC 95 % | p corrigée (Holm) | CLV Pinnacle | IC 95 % | Verdict |
|---|---|---|---|---|---|---|---|
| Référence Pinnacle | 3541 | -12,1 % | [-18,4 ; -3,7] | 0,696 | +1,85 % | [+1,21 ; +2,51] | **non prouvé** : tendance négative, non confirmée après correction |
| Référence Betfair | 212 | +5,3 % | [-18,6 ; +35,5] | 1,000 | +8,56 % | [+3,81 ; +15,52] | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Référence Polymarket | 1131 | +15,4 % | [-2,8 ; +64,1] | 1,000 | +4,25 % | [+2,71 ; +6,16] | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Référence Matchbook | 264 | +0,6 % | [-21,4 ; +28,2] | 1,000 | +3,35 % | [+0,54 ; +6,03] | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Référence Smarkets | 165 | +4,5 % | [-31,2 ; +60,4] | 1,000 | +0,84 % | — | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Référence Kalshi | 191 | -28,4 % | [-43,6 ; -11,9] | 0,104 | +10,65 % | — | **non prouvé** : tendance négative, non confirmée après correction |
| Référence Consensus | 523 | +5,9 % | [-8,2 ; +23,8] | 1,000 | +4,03 % | [+2,60 ; +6,00] | **avantage probable** : CLV Pinnacle prouvée, ROI positif mais non prouvé |

### Seuils d'écart et tranches de cote (paris uniques)

| Ligne | Réglés | ROI | IC 95 % | p corrigée (Holm) | CLV Pinnacle | IC 95 % | Verdict |
|---|---|---|---|---|---|---|---|
| Seuil A (écart 2 à 3 %) | 1652 | +1,5 % | [-4,5 ; +7,5] | 1,000 | -0,51 % | [-1,19 ; +0,18] | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Seuil B (écart 3 à 4 %) | 789 | -1,4 % | [-9,8 ; +7,4] | 1,000 | +0,65 % | [-0,47 ; +1,78] | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Seuil C (écart 4 à 5 %) | 495 | +2,8 % | [-7,1 ; +13,4] | 1,000 | +1,70 % | [+0,49 ; +2,90] | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Seuil D (écart 5 à 7 %) | 499 | +2,7 % | [-8,6 ; +15,2] | 1,000 | +1,57 % | [+0,01 ; +3,14] | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Seuil E (écart 7 % et plus) | 677 | +0,9 % | [-10,8 ; +14,3] | 1,000 | +5,57 % | [+3,88 ; +7,21] | **avantage probable** : CLV Pinnacle prouvée, ROI positif mais non prouvé |
| Seuil X (cote > 10) | 771 | -44,6 % | [-76,5 ; +46,4] | 1,000 | +7,83 % | [+5,81 ; +10,37] | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Cote 1,01 – 1,50 | 604 | +2,4 % | [-3,2 ; +7,4] | 1,000 | +0,71 % | [+0,04 ; +1,30] | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Cote 1,51 – 2,00 | 1531 | +2,1 % | [-3,3 ; +7,3] | 1,000 | +0,60 % | [-0,08 ; +1,24] | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Cote 2,01 – 3,00 | 1218 | +1,2 % | [-7,0 ; +9,6] | 1,000 | +2,45 % | [+1,17 ; +3,87] | **avantage probable** : CLV Pinnacle prouvée, ROI positif mais non prouvé |
| Cote 3,01 – 5,00 | 560 | +11,7 % | [-4,3 ; +29,2] | 1,000 | -0,10 % | [-1,99 ; +1,76] | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Cote 5,01 – 10 | 199 | -39,9 % | [-65,5 ; +0,8] | 1,000 | +2,18 % | [-2,68 ; +7,75] | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Cote plus de 10 | 771 | -44,6 % | [-76,6 ; +46,5] | 1,000 | +7,83 % | [+5,81 ; +10,39] | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |

### Stratégies (suivi officiel)

| Ligne | Réglés | ROI | IC 95 % | p corrigée (Holm) | CLV Pinnacle | IC 95 % | Verdict |
|---|---|---|---|---|---|---|---|
| Claude | 1046 | -3,6 % | [-11,4 ; +4,3] | 1,000 | +1,30 % | [+0,39 ; +2,26] | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| ChatGPT v1 | 73 | -6,1 % | [-29,5 ; +19,1] | 1,000 | +1,39 % | [-0,88 ; +3,32] | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Gemini Argon v1 | 179 | +2,8 % | [-10,9 ; +16,2] | 1,000 | +1,25 % | [-0,25 ; +2,78] | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| JULES EDGE v1 | 99 | -2,8 % | [-21,6 ; +16,2] | 1,000 | +0,77 % | [-1,31 ; +2,76] | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| JULES EDGE v2 | 163 | -7,5 % | [-22,6 ; +8,1] | 1,000 | +0,96 % | [-0,84 ; +2,76] | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Eden | 233 | +3,2 % | [-8,2 ; +14,2] | 1,000 | +0,63 % | [-0,78 ; +2,04] | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| M3 | 441 | +2,9 % | [-12,3 ; +18,4] | 1,000 | +0,20 % | [-1,82 ; +2,55] | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Convergence ≥ 2 | 430 | +1,8 % | [-10,4 ; +14,3] | 1,000 | +1,41 % | [+0,08 ; +2,89] | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Claude 1/match · max 10/j | 272 | -7,1 % | [-17,5 ; +3,5] | 1,000 | +1,13 % | [-0,01 ; +2,28] | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Convergence ≥ 3 hors M3 | 94 | -7,9 % | [-27,3 ; +11,8] | 1,000 | +0,16 % | [-2,11 ; +2,11] | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| M3 · Max 3/match | 184 | -5,2 % | [-19,4 ; +9,1] | 1,000 | -1,39 % | [-3,79 ; +0,83] | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Qwen | 13 | -4,5 % | — | — | +5,57 % | — | **non prouvé** : trop peu de paris (13 réglés) |
| Cœur value | 59 | +3,5 % | [-21,2 ; +27,1] | 1,000 | -2,40 % | [-5,20 ; -0,07] | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Liquidité sûre | 167 | +14,1 % | [-3,8 ; +33,6] | 1,000 | -0,10 % | [-1,63 ; +1,43] | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Grok 1 · Polymarket mid | 51 | +9,8 % | [-16,5 ; +34,4] | 1,000 | +3,20 % | — | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Grok 2 · Pinnacle low | 94 | +5,1 % | [-13,0 ; +22,1] | 1,000 | +0,37 % | [-1,89 ; +2,24] | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Grok 3 · Consensus mid | 31 | +21,2 % | [-13,4 ; +50,7] | 1,000 | +3,16 % | — | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Grok 4 · Polymarket low-odds | 39 | +11,3 % | [-16,4 ; +33,1] | 1,000 | +0,92 % | — | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Grok 5 · Multi-sharp low | 51 | +2,9 % | [-21,2 ; +24,2] | 1,000 | +1,56 % | — | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Grok 6 · Pinnacle hors foot | 123 | -5,5 % | [-23,5 ; +13,2] | 1,000 | +1,30 % | [-0,53 ; +3,02] | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Grok 7 · Pinnacle cote moyenne | 92 | +5,4 % | [-15,7 ; +26,3] | 1,000 | +0,29 % | [-2,07 ; +2,71] | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Grok 8 · Polymarket hors foot | 53 | +26,1 % | [-3,0 ; +54,7] | 1,000 | -0,01 % | — | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Grok 9 · Valeur Pinnacle | 237 | +4,3 % | [-13,9 ; +23,2] | 1,000 | +1,77 % | [-0,53 ; +4,04] | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Grok 10 · Valeur Polymarket | 100 | +2,3 % | [-27,1 ; +33,2] | 1,000 | +5,23 % | — | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Conseil · bookmaker en retard (hors foot) | 112 | +0,1 % | [-19,3 ; +22,1] | 1,000 | +1,15 % | [-1,39 ; +3,27] | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Défi 1 · Écart fort, match proche | 169 | -5,9 % | [-28,9 ; +21,8] | 1,000 | +6,28 % | [+2,45 ; +9,83] | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Défi 4 · Pinnacle très gros écart | 106 | +8,4 % | [-22,8 ; +50,0] | 1,000 | +9,41 % | [+6,24 ; +12,18] | **avantage probable** : CLV Pinnacle prouvée, ROI positif mais non prouvé |
| Gemini Défi 1 · Indoor & Glace | 161 | -9,8 % | [-35,2 ; +18,7] | 1,000 | +1,81 % | [-1,92 ; +6,27] | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Gemini Défi 3 · Sniper principaux | 75 | +27,8 % | [-18,3 ; +89,1] | 1,000 | +3,13 % | [-3,03 ; +7,88] | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Gemini Défi 4 · Lignes asiatiques | 119 | -3,9 % | [-29,3 ; +23,1] | 1,000 | +2,80 % | [-1,25 ; +8,35] | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Claude Défi 1 · Gros écart 12 h | 106 | -32,3 % | [-56,1 ; +5,4] | 1,000 | +8,73 % | [+3,53 ; +13,25] | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Claude Défi 2 · Handicaps | 47 | -45,0 % | [-66,0 ; -10,4] | 1,000 | +7,60 % | [+0,74 ; +14,79] | **non prouvé** : tendance négative, non confirmée après correction |
| Claude Défi 3 · Books lents 2–12 h | 75 | -29,8 % | [-54,5 ; +4,8] | 1,000 | +8,52 % | [+2,30 ; +15,62] | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Claude Défi 4 · Gros écart hors Winamax | 58 | -40,9 % | [-68,2 ; +5,3] | 1,000 | +15,00 % | [+7,86 ; +19,38] | **non prouvé** : CLV Pinnacle prouvée, ROI négatif |
| Claude Défi 5 · Books lents, cotes courtes | 94 | -37,9 % | [-57,3 ; -12,7] | 0,608 | +8,42 % | [+4,53 ; +12,59] | **non prouvé** : tendance négative, non confirmée après correction |
| Claude Défi 6 · Polymarket tôt | 100 | -1,8 % | [-34,0 ; +52,7] | 1,000 | +3,82 % | — | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Claude Fusion · Défi 4 + Défi 5 | 113 | -33,3 % | [-54,3 ; -5,7] | 1,000 | +9,30 % | [+4,80 ; +13,23] | **non prouvé** : tendance négative, non confirmée après correction |
| Claude Opus · Valeur solide | 121 | -21,5 % | [-43,4 ; +5,9] | 1,000 | +2,74 % | [-1,02 ; +6,16] | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Claude Opus · Favoris réguliers | 73 | +3,3 % | [-24,7 ; +33,4] | 1,000 | +1,45 % | [-2,23 ; +3,92] | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Claude Opus · Hors football | 85 | -17,3 % | [-46,7 ; +19,4] | 1,000 | +2,73 % | [-1,32 ; +6,34] | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Claude Opus · Handicaps | 33 | -29,0 % | [-68,3 ; +36,6] | 1,000 | +1,80 % | — | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Claude Signal · Double avis | 3 | -100,0 % | — | — | +4,26 % | — | **non prouvé** : trop peu de paris (3 réglés) |
| Claude Signal · Prix frais | 22 | +9,9 % | — | — | +1,03 % | — | **non prouvé** : trop peu de paris (22 réglés) |
| Claude · Méthode humaine | 5 | +2,0 % | — | — | +4,04 % | — | **non prouvé** : trop peu de paris (5 réglés) |
| Claude · PMU régulier | 2 | +124,0 % | — | — | +4,01 % | — | **non prouvé** : trop peu de paris (2 réglés) |
| Fusion 1 · recommandées du 8/11 | 57 | +15,5 % | [-12,3 ; +45,9] | 1,000 | -1,88 % | [-5,28 ; +0,82] | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |

### Laboratoire (24 règles de seuils)

| Ligne | Réglés | ROI | IC 95 % | p corrigée (Holm) | CLV Pinnacle | IC 95 % | Verdict |
|---|---|---|---|---|---|---|---|
| Pinnacle · 1.3–2 · ≥ 2 % · ≤ 12 h | 214 | +4,4 % | [-7,0 ; +15,5] | 1,000 | +0,90 % | [-0,25 ; +2,01] | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Pinnacle · 1.3–2 · ≥ 2 % · ≤ 36 h | 353 | +9,2 % | [+0,6 ; +17,4] | 1,000 | +0,65 % | [-0,31 ; +1,55] | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Pinnacle · 1.3–2 · ≥ 5 % · ≤ 12 h | 49 | +4,9 % | [-22,0 ; +29,7] | 1,000 | +1,67 % | [-1,88 ; +4,47] | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Pinnacle · 1.3–2 · ≥ 5 % · ≤ 36 h | 89 | +12,3 % | [-6,5 ; +29,6] | 1,000 | +2,74 % | [+0,52 ; +4,66] | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Pinnacle · 1.5–3 · ≥ 2 % · ≤ 12 h | 274 | +5,4 % | [-6,7 ; +17,6] | 1,000 | +1,61 % | [+0,43 ; +2,73] | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Pinnacle · 1.5–3 · ≥ 2 % · ≤ 36 h | 441 | +8,2 % | [-1,4 ; +17,9] | 1,000 | +1,36 % | [+0,35 ; +2,34] | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Pinnacle · 1.5–3 · ≥ 5 % · ≤ 12 h | 82 | +5,1 % | [-18,2 ; +29,1] | 1,000 | +4,30 % | [+1,51 ; +6,76] | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Pinnacle · 1.5–3 · ≥ 5 % · ≤ 36 h | 146 | +9,2 % | [-8,3 ; +26,7] | 1,000 | +4,19 % | [+2,26 ; +6,05] | **avantage probable** : CLV Pinnacle prouvée, ROI positif mais non prouvé |
| Pinnacle · 2–5 · ≥ 2 % · ≤ 12 h | 198 | +7,2 % | [-11,3 ; +27,2] | 1,000 | +2,70 % | [+1,22 ; +4,07] | **avantage probable** : CLV Pinnacle prouvée, ROI positif mais non prouvé |
| Pinnacle · 2–5 · ≥ 2 % · ≤ 36 h | 342 | +12,2 % | [-2,7 ; +28,0] | 1,000 | +1,25 % | [-0,14 ; +2,59] | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Pinnacle · 2–5 · ≥ 5 % · ≤ 12 h | 67 | +7,5 % | [-22,1 ; +40,6] | 1,000 | +6,20 % | [+3,24 ; +8,91] | **avantage probable** : CLV Pinnacle prouvée, ROI positif mais non prouvé |
| Pinnacle · 2–5 · ≥ 5 % · ≤ 36 h | 123 | +16,6 % | [-7,9 ; +43,5] | 1,000 | +4,80 % | [+2,58 ; +6,83] | **avantage probable** : CLV Pinnacle prouvée, ROI positif mais non prouvé |
| Polymarket · 1.3–2 · ≥ 2 % · ≤ 12 h | 36 | -4,3 % | [-37,7 ; +26,4] | 1,000 | +3,27 % | — | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Polymarket · 1.3–2 · ≥ 2 % · ≤ 36 h | 74 | +16,8 % | [-3,6 ; +34,3] | 1,000 | +3,09 % | — | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Polymarket · 1.3–2 · ≥ 5 % · ≤ 12 h | 8 | -9,7 % | — | — | +2,59 % | — | **non prouvé** : trop peu de paris (8 réglés) |
| Polymarket · 1.3–2 · ≥ 5 % · ≤ 36 h | 15 | +2,6 % | — | — | +5,82 % | — | **non prouvé** : trop peu de paris (15 réglés) |
| Polymarket · 1.5–3 · ≥ 2 % · ≤ 12 h | 55 | -9,4 % | [-36,2 ; +20,3] | 1,000 | +2,99 % | — | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Polymarket · 1.5–3 · ≥ 2 % · ≤ 36 h | 135 | +21,6 % | [+3,2 ; +40,1] | 1,000 | +4,10 % | [+1,89 ; +6,37] | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Polymarket · 1.5–3 · ≥ 5 % · ≤ 12 h | 15 | -30,3 % | — | — | +2,62 % | — | **non prouvé** : trop peu de paris (15 réglés) |
| Polymarket · 1.5–3 · ≥ 5 % · ≤ 36 h | 35 | +27,7 % | [-8,0 ; +63,6] | 1,000 | +5,52 % | — | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Polymarket · 2–5 · ≥ 2 % · ≤ 12 h | 68 | -16,4 % | [-46,7 ; +23,0] | 1,000 | +5,10 % | — | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Polymarket · 2–5 · ≥ 2 % · ≤ 36 h | 165 | +32,5 % | [+9,8 ; +56,7] | 0,497 | +3,61 % | [+0,13 ; +7,04] | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |
| Polymarket · 2–5 · ≥ 5 % · ≤ 12 h | 13 | -48,5 % | — | — | +8,81 % | — | **non prouvé** : trop peu de paris (13 réglés) |
| Polymarket · 2–5 · ≥ 5 % · ≤ 36 h | 46 | +39,5 % | [-3,8 ; +89,7] | 1,000 | +5,73 % | — | **non prouvé** : ni le ROI ni la CLV ne se distinguent de zéro |

## 1. ROI, intervalle et p-valeurs

- **Unité de hasard : le match**, pas le pari. Les paris d'un même match gagnent ou perdent ensemble (audit,
  problème 2) ; le bootstrap retire des matchs entiers.
- **Intervalle à 95 % et p-valeur : bootstrap studentisé**, 50 000 tirages. Il tient compte des gains très
  asymétriques (quelques grosses cotes font tout le résultat) : l'intervalle des cotes > 5 est [−70,2 ; +22,6]
  pour −43,7 % observé, là où un calcul symétrique annoncerait à tort un ROI sûrement négatif.
- **Correction** : une seule famille, les 96 lignes testées dans les deux sens (192 tests). Holm : aucune
  fausse découverte au seuil de 5 %. Benjamini-Hochberg : 5 % de fausses découvertes parmi les lignes retenues.
- **Résultat** : aucune ligne sous 5 % après Holm ni après Benjamini-Hochberg, dans aucun sens. Plus petites
  p corrigées (Holm) : Kalshi 0,10 (ROI négatif), Polymarket · 2–5 · ≥ 2 % · ≤ 36 h 0,50 (ROI positif).
- **Les 5 règles Polymarket « ≤ 36 h » aux ROI de +17 % à +40 % ne sont pas un signal** : elles partagent leurs
  paris (45 des 46 paris de « 2–5 · ≥ 5 % » sont dans « 2–5 · ≥ 2 % »), les mêmes règles « ≤ 12 h » font de −4 % à
  −16 %, et leur p corrigée vaut 0,50 à 1.
- **Pas de tableau stratégie × bookmaker** : 46 × 6 cases de quelques dizaines de paris, et 276 tests de plus à
  corriger. Les bookmakers sont testés sur les paris uniques.

## 2. Paris encore nécessaires pour conclure

Paris réglés qu'il manque pour passer le seuil corrigé (5 % / 192, celui d'un « avantage prouvé ») avec 80 % de
chances, selon l'écart-type par pari mesuré sur la ligne. Deux hypothèses : le vrai ROI est le ROI observé
(optimiste pour les meilleures lignes, choisies parce qu'elles ont eu de la chance) ; le vrai ROI est la CLV
moyenne (réaliste). Entre parenthèses : sans correction (5 % bilatéral), soit 2,4 fois moins.

| Ligne | Réglés (par jour) | Si le ROI observé est le vrai : encore | soit | Si la CLV est le vrai ROI : encore | soit |
|---|---|---|---|---|---|
| Paris uniques, cote ≤ 5 | 3 913 (98) | 36 114 (12 988) | 1 an | 374 550 (155 892) | 10,5 ans |
| PMU, cote ≤ 5 | 1 802 (45) | 59 741 (24 185) | 3,6 ans | 94 957 (39 054) | 5,8 ans |
| Betclic, cote ≤ 5 | 1 015 (25) | 9 137 (3 272) | 12 mois | 113 272 (47 242) | 12,2 ans |
| Winamax, cote ≤ 5 | 464 (12) | 11 229 (4 474) | 2,7 ans | — (CLV négative) | — |
| Unibet, cote ≤ 5 | 350 (9) | 4 615 (1 747) | 1,4 an | plus d'un million | — |
| Claude | 1 046 (34) | 21 719 (8 567) | 1,8 an | 75 624 (31 328) | 6,1 ans |
| Convergence ≥ 2 | 430 (14) | 92 361 (38 751) | 17,7 ans | 61 601 (25 762) | 11,8 ans |
| M3 | 441 (15) | 56 849 (23 750) | 10,6 ans | 416 238 (175 500) | 77,6 ans |
| Eden | 233 (9) | 13 320 (5 490) | 4,1 ans | 142 864 (60 189) | 43,7 ans |
| Liquidité sûre | 167 (8) | 1 201 (411) | 5 mois | — (CLV négative) | — |
| Pinnacle · 1.5–3 · ≥ 2 % · ≤ 36 h | 441 (14) | 2 462 (785) | 6 mois | 104 019 (43 667) | 20 ans |
| Pinnacle · 2–5 · ≥ 5 % · ≤ 36 h | 123 (4) | 1 249 (457) | 10 mois | 16 384 (6 848) | 11,3 ans |
| Polymarket · 2–5 · ≥ 2 % · ≤ 36 h | 165 (5) | 242 (7) | 45 jours | 108 778 (45 836) | 56 ans |

Pour les stratégies au ROI négatif (Claude, par exemple), le nombre est celui qu'il faut pour conclure qu'elles
perdent. Les autres lignes sont dans [avantage-reel-tableaux.md](avantage-reel-tableaux.md).

Lecture : un avantage de 1 à 2 % ne se prouve pas par le ROI à ce volume. Une ligne qui « conclurait » en
quelques mois (Polymarket ≤ 36 h, Liquidité sûre) suppose un vrai ROI de +14 % à +32 %, que sa CLV dément.

## 3. CLV

- **Référence** : la clôture Pinnacle sans marge, lue dans les 30 minutes avant le début. Elle existe pour 3 558
  paris réglés sur 6 027 (59 %) : 2 744 dont Pinnacle est la référence, et 814 d'une autre référence dont la même
  cote (même bookmaker, match, marché, issue) a aussi été repérée par Pinnacle. À défaut, la clôture de la
  référence du pari : 1 169 paris de plus. **1 300 paris réglés (22 %) n'ont aucune CLV.**
- **Les paris sans CLV font pire** : paris uniques, −19,8 % sans CLV contre −1,8 % avec. La CLV moyenne décrit donc
  le meilleur sous-ensemble (à cote ≤ 5 l'écart s'inverse : +6,5 % sans, +2,4 % avec).
- **CLV Pinnacle prouvée après correction (Holm) sur 22 lignes**, dont : paris uniques ≤ 5 (+1,08 %, 62 % des paris
  au-dessus de zéro), PMU ≤ 5 (+2,04 % [+1,32 ; +2,82]), écart ≥ 7 % (+5,57 % [+3,88 ; +7,21]), cotes 2 à 3
  (+2,45 %). Non prouvée : Betclic ≤ 5 (+1,33 % [+0,10 ; +2,66]), Unibet ≤ 5 (+0,91 %), écart de 2 à 3 % (−0,51 %
  [−1,19 ; +0,18]) : **le premier seuil d'écart ne bat pas la clôture**.
- **CLV négative** : OlyBet ≤ 5 (−3,85 %, 38 % des paris au-dessus de zéro) et Winamax ≤ 5 (−1,87 % [−3,45 ;
  −0,27], meilleure référence), malgré un ROI de +5,3 % chez Winamax.

### La CLV prédit-elle le ROI ?

Paris uniques réglés qui ont une CLV (3 715).

| Sous-ensemble | Paris | CLV moyenne | ROI | ROI − CLV, IC 95 % | Pente du rendement sur la CLV, IC 95 % |
|---|---|---|---|---|---|
| Clôture Pinnacle, cote ≤ 5 | 2 325 | +1,08 % | +1,6 % | [−5,1 ; +6,4] | **1,23 [0,55 ; 1,89]** |
| Autre clôture, cote ≤ 5 | 808 | +0,96 % | +4,6 % | [−6,5 ; +14,2] | −0,03 [−0,93 ; +0,90] |
| Cote > 5, toute clôture | 582 | +7,82 % | −24,3 % | [−73,5 ; +92,5] | 1,67 [−0,97 ; +6,63] |
| Tous | 3 715 | +2,11 % | −1,8 % | [−11,8 ; +10,2] | 1,04 [−0,34 ; +3,37] |

Une pente de 1 veut dire : un point de CLV en plus, un point de rendement en plus.

| Cinquième de CLV (clôture Pinnacle, cote ≤ 5) | Paris | CLV moyenne | ROI | IC 95 % |
|---|---|---|---|---|
| −54,0 % à −5,8 % | 465 | −13,46 % | −11,9 % | [−24,9 ; +1,5] |
| −5,8 % à +0,4 % | 465 | −2,34 % | −6,5 % | [−17,2 ; +5,1] |
| +0,4 % à +3,3 % | 465 | +2,07 % | −0,9 % | [−10,5 ; +8,7] |
| +3,3 % à +7,2 % | 465 | +4,99 % | +11,8 % | [+1,1 ; +22,8] |
| +7,2 % à +58,3 % | 465 | +14,11 % | +15,6 % | [+0,4 ; +31,8] |

- **Oui, pari par pari, contre la clôture Pinnacle et à cote ≤ 5** : la pente vaut 1 aux erreurs près, le ROI suit
  la CLV dans les cinq cinquièmes, et le ROI de l'ensemble est compatible avec sa CLV.
- **Non pour les clôtures des autres références** (Polymarket, Consensus, Matchbook, Betfair, Kalshi, Smarkets) :
  leur pente exclut 1. Leur CLV ne doit pas servir à juger une stratégie.
- **Non mesurable au-dessus de 5** : CLV de +7,8 % pour un ROI de −24,3 %, avec un intervalle de 166 points.
- **Non, pas encore, entre stratégies** : sur 31 stratégies et règles d'au moins 100 paris réglés, la corrélation
  entre CLV moyenne et ROI vaut −0,44 (rangs : −0,27). Le bruit du ROI d'une stratégie (±10 à ±25 points) est bien
  plus large que l'écart de CLV entre stratégies (0 à 9 points), et deux des plus fortes CLV sont Claude Défi 1 et
  Claude Fusion, qui partagent leurs paris et perdent 32 % et 33 %. Lignes non indépendantes : chiffre descriptif.

## Règles du verdict

- **Avantage prouvé** : ROI positif, p de Holm < 5 %.
- **Avantage probable** : ROI positif avec p de Benjamini-Hochberg < 5 % ; ou bien ROI positif, CLV Pinnacle
  positive avec p de Holm < 5 %, mesurée sur au moins la moitié des paris réglés, et ROI des paris mesurés
  compatible avec leur CLV (l'intervalle de ROI − CLV n'est pas sous zéro).
- **Négatif** : ROI négatif, avec p de Benjamini-Hochberg < 5 % sur le ROI ou sur une CLV négative.
- **Non prouvé** : tout le reste, dont les lignes de moins de 30 paris réglés ou de 10 matchs. La raison est
  écrite à côté (« tendance négative » : intervalle du ROI sous zéro, sans tenir après correction).

« Probable » veut donc dire : ces paris battent la clôture Pinnacle, c'est établi ; que cela se traduise en gain
est cohérent avec les résultats, pas démontré par eux. Défi 4 (CLV +9,41 %, ROI +8,4 %) est classé « probable »
alors que Claude Défi 4 et 5, même genre de paris à gros écart (un quart en commun) et CLV de +8 % à +15 %, perdent
38 % et 41 % : à lire avec cette réserve. Les 4 règles Pinnacle « probables » du laboratoire partagent aussi leurs
paris (64 des 67 paris de « 2–5 · ≥ 5 % · ≤ 12 h » sont dans « ≤ 36 h »).

Ces règles ont été fixées après un premier passage sur les données, pas avant. La première version (« probable » =
ROI positif à p brute < 5 % et CLV positive) retenait 4 lignes sur 96, pas plus que le hasard : elle a été remplacée
par la règle ci-dessus, plus exigeante sur la CLV. C'est une grille de lecture, pas un test annoncé à l'avance.

## Limites

- **Plafond de cote** : les lignes « cote ≤ 5 » reprennent un seuil choisi sur ces résultats. Les stratégies sont
  mesurées sans plafond, avec leurs paris au-dessus de 5 (9 au plus par stratégie).
- **Stratégies reconstruites** : 615 sélections sur 9 103 (7 %) datent d'avant le registre du 17/10 et sont
  recalculées avec les règles d'aujourd'hui.
- **Lignes non indépendantes** : les stratégies partagent leurs paris. Holm reste valable ; Benjamini-Hochberg
  suppose que les lignes varient dans le même sens.
- **CLV manquante** pour 22 % des paris réglés, et clôture Pinnacle pour 59 % seulement.
- **Scores non recontrôlés** sur une source extérieure (audit) ; 12 paris dépendent d'une règle non lue.
- **Durée** : 40 jours, une seule période de la saison.

## Décisions proposées

1. Juger les stratégies sur la CLV contre la clôture Pinnacle, pas sur le ROI ni sur la CLV des autres références.
2. Enregistrer la clôture Pinnacle de chaque pari, quelle que soit sa référence : elle manque à 41 % des réglés.
3. Ne promouvoir aucune règle sur son ROI actuel, en particulier les règles Polymarket « ≤ 36 h ».
4. Regarder de près la référence Kalshi (191 paris, −28,4 %) et OlyBet avant d'en reprendre des paris.
5. Tester moins de lignes : chaque stratégie ajoutée durcit la correction pour toutes les autres.

## Reproduire

```bash
bash scripts/cloner_donnees.sh https://github.com/Matttgic/cotes-value donnees
```

```bash
python scripts/avantage_reel.py --donnees donnees --markdown docs/avantage-reel-tableaux.md
```

Demande numpy (`requirements-dev.txt`). La sortie standard est le tableau « Verdict par ligne ». Les données
changent toutes les heures : pour retrouver ces chiffres, se placer sur le commit `db927c7` de `donnees`.
