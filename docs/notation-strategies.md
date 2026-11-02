# Note des stratégies sur 100

Objectif : classer les stratégies en préférant la **régularité et la solidité** au gain brut. Une stratégie qui
fait +1 000 € un mois et −800 € le suivant doit être moins bien notée qu'une stratégie qui gagne un peu, mais
souvent et sur beaucoup de paris. Code : `cotes/notation.py`, appelé par `laboratoire.resume` pour chaque
stratégie et chaque période, en mise fixe comme en Kelly.

## Formule

Note = rentabilité prudente (30) + valeur (25) + régularité (25) + solidité (20). Chaque part est une échelle
linéaire bornée : 0 sous le seuil bas, le maximum au-dessus du seuil haut.

| Part | Mesure | 0 point | Maximum |
|---|---|---|---|
| Rentabilité prudente /30 | Borne basse à 80 % de l'intervalle de confiance du ROI (estimateur de ratio, comme l'IC du Bilan) | −10 % | +5 % |
| Valeur /15 | CLV moyenne × k / (k + 50), k = nombre de CLV mesurées | −1 % | +3 % |
| Valeur /10 | Part des paris qui battent la clôture, (positifs + 25) / (k + 50) | 45 % | 65 % |
| Régularité /12,5 | Part des jours gagnants, (jours gagnants + 2) / (jours + 4) | 35 % | 65 % |
| Régularité /12,5 | Plus forte baisse / (mise moyenne × √n) | 3,0 | 0,5 |
| Solidité /12 | log10 du nombre de paris réglés | 20 paris | 500 paris |
| Solidité /4 | Jours d'observation | 0 | 15 jours |
| Solidité /4 | Cote moyenne | 8 | 3 |

- Pas de note sous 10 paris réglés ; note **provisoire** sous 50.
- Les termes ajoutés (+ 50, + 25, + 2, + 4) ramènent vers une valeur neutre les mesures faites sur peu de
  paris, pour qu'une chance passagère ne fasse pas monter la note.
- La plus forte baisse est rapportée à √n : un hasard équilibré produit une baisse de l'ordre de la mise
  moyenne × √n. En dessous de 0,5, la stratégie a peu reculé ; au-dessus de 3, ses baisses sont plus
  violentes que le hasard ne l'explique.
- La cote moyenne pénalise les longues cotes : au-delà de 5, les cotes justes surestiment la probabilité
  d'environ moitié (docs/etude-longues-cotes.md).

## Lecture

- 70 et plus : rentable avec une marge de sécurité, régulière, sur un échantillon sérieux.
- 40 à 70 : prometteuse ou solide sans rentabilité démontrée.
- Moins de 40 : rentabilité non démontrée, irrégulière ou trop peu de paris.

## Exemple : suivi prospectif au 2/11/2026, mise fixe

| Stratégie | Note | Paris réglés | ROI | CLV | Rentabilité | Valeur | Régularité | Solidité |
|---|---|---|---|---|---|---|---|---|
| Pinnacle · cotes 1,5–3, écart ≥ 2 %, 36 h | 88 | 296 | +12,1 % | +1,28 % | 28,8 | 16,7 | 24,8 | 18,0 |
| Pinnacle · cotes 1,3–2, écart ≥ 2 %, 36 h | 87 | 234 | +12,8 % | +0,80 % | 30,0 | 14,5 | 25,0 | 17,2 |
| Grok 8 · Polymarket hors foot | 75 (provisoire) | 22 | +38,6 % | +4,83 % | 30,0 | 13,8 | 24,3 | 6,5 |
| Défi 4 · Pinnacle très gros écart | 44 | 57 | +0,9 % | +6,24 % | 0,0 | 24,4 | 9,8 | 9,8 |

Grok 8 a le meilleur ROI, mais sur 22 paris seulement : sa solidité le place derrière les règles larges.
Défi 4 bat largement la clôture, mais ses résultats sont irréguliers et sans rentabilité démontrée.

## Limites

Note descriptive : aucune stratégie n'en dépend, et une bonne note ne garantit aucun gain futur. Les
stratégies se recoupent (mêmes paris) et sont comparées sur des périodes de longueurs différentes. Les
seuils sont des choix raisonnés, pas ajustés pour faire gagner une stratégie.
