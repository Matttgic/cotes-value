# Étude : les cotes justes sont-elles fiables sur les longues cotes ?

Relevé : branche `donnees` du 2/11/2026 à 15:44 UTC. Paris uniques réglés (première détection d'une cote
française, comme le Bilan), remboursements exclus. 3 689 paris : 3 073 sur les marchés classiques, 616 sur
le score exact et la mi-temps/fin de match.

## Question

Sur les paris Pinnacle, le score exact et la mi-temps/fin perdent 67 % (521 paris, −3 500 €) alors que leur
CLV est de +7 %. Défaut de calcul ou limite des cotes justes elles-mêmes ?

## Ce qui n'était pas faisable : la méthode de Shin

La méthode de Shin (retrait de marge qui corrige le biais des outsiders) a besoin de toutes les issues du
marché Pinnacle. Les paris n'en gardent qu'une : la cote retenue, sa cote juste et la marge du marché. La
comparaison Shin / « power » n'est donc pas calculable après coup. À la place, on mesure directement la
**calibration** : pour chaque groupe de paris, gains observés contre gains attendus (somme des probabilités
justes à la prise). Un rapport de 1 veut dire des cotes justes exactes ; 0,5, des probabilités surestimées
de moitié.

## Résultats

### Par famille de marché et cote

| Groupe | Paris | Gains observés | Gains attendus | Observés / attendus (IC 95 %) | ROI |
|---|---|---|---|---|---|
| Classiques · cote 1–2 | 1 524 | 971 | 977,1 | 0,99 [0,93 ; 1,06] | +3,6 % |
| Classiques · cote 2–3 | 894 | 396 | 404,0 | 0,98 [0,89 ; 1,08] | +3,5 % |
| Classiques · cote 3–5 | 430 | 128 | 122,9 | 1,04 [0,87 ; 1,24] | +10,0 % |
| Classiques · cote 5–10 | 149 | 13 | 25,7 | **0,51 [0,27 ; 0,87]** | −45,6 % |
| Classiques · cote 10–25 | 35 | 2 | 2,6 | 0,77 [0,09 ; 2,78] | −14,3 % |
| Classiques · cote 25+ | 41 | 0 | 1,3 | 0,00 [0,00 ; 2,83] | −100 % |
| Exotiques · cote 10–25 | 97 | 5 | 7,3 | 0,69 [0,22 ; 1,60] | −18,6 % |
| Exotiques · cote 25+ | 508 | 6 | 12,0 | 0,50 [0,18 ; 1,09] | −37,6 % |

### Exotiques par référence

| Référence · marché | Paris | Gains observés | Gains attendus | Observés / attendus (IC 95 %) | ROI |
|---|---|---|---|---|---|
| Pinnacle · score exact (match) | 217 | 2 | 6,3 | 0,32 [0,04 ; 1,15] | −89,9 % |
| Pinnacle · score exact (1re mi-temps) | 172 | 1 | 3,9 | 0,26 [0,00 ; 1,43] | −65,1 % |
| Pinnacle · mi-temps/fin | 131 | 2 | 5,4 | 0,37 [0,04 ; 1,33] | −32,8 % |
| Polymarket · score exact | 39 | 4 | 1,0 | 3,89 [1,05 ; 9,96] | +394,9 % |
| Smarkets · score exact | 37 | 2 | 3,3 | 0,61 [0,07 ; 2,21] | −37,8 % |

### Recalibration logistique

Modèle `logit(observé) = a + b · logit(p annoncée)`, ajusté sur les résultats :

- marchés classiques (3 073 paris) : a = −0,04, b = 1,04 (± 0,11). Calibration correcte ; une probabilité
  annoncée de 5 % correspond à 4,4 % observés.
- exotiques (616 paris) : a = −0,98, b = 0,88 (± 0,65). Une probabilité annoncée de 5 % correspond à
  **2,8 %** observés.

## Conclusions

1. **Jusqu'à une cote de 5, les cotes justes sont fiables.** Les marchés classiques sont calibrés à quelques
   pour cent près, avec un ROI positif dans chaque tranche.
2. **Au-delà de 5, elles surestiment la probabilité d'environ moitié**, marchés classiques compris. Le seul
   écart significatif est en cote 5–10 (IC 0,27–0,87). C'est la « malédiction du gagnant » : plus la cote juste
   est incertaine, plus les écarts que l'on retient sont faits de bruit plutôt que de vraie valeur.
   L'avantage annoncé (+10 % en moyenne) ne compense pas une probabilité divisée par deux.
3. **La CLV positive des exotiques ne prouve rien.** Elle est mesurée contre la même cote juste biaisée.
4. Le score exact contre Polymarket (4 gains pour 1 attendu) repose sur 39 paris : de la chance, très
   probablement, pas un résultat.
5. **Pas de défaut de calcul trouvé** hormis le gonflement des marchés incomplets, corrigé le 2/11 (8 paris).

## Recommandations

- Pour une stratégie de valeur fondée sur ces références : **cote française ≤ 5**, marchés classiques.
- Les longues cotes restent suivies (Gemini Défi 5, tranche X du Bilan) : ce sont des expériences, pas des
  stratégies rentables démontrées.
- Pour tester Shin plus tard, il faudrait garder toutes les issues des marchés exotiques Pinnacle au
  moment de la prise.

## Limites

Peu de gains attendus sur les longues cotes, donc des intervalles larges. Les paris d'un même match sont
corrélés. Un seul mois de données, sans tenir compte de la saison ni des championnats.
