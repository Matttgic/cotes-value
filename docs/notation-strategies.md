# Note des stratégies sur 100

Objectif : classer les stratégies en préférant un résultat **solide** au gain brut. Code : `cotes/notation.py`,
appelé par `laboratoire.resume` pour chaque stratégie et chaque période, en mise fixe comme en Kelly.

## Version 2 (8/11/2026) : la note compte les matchs

Plusieurs paris sur un même match (total, handicap, vainqueur…) ne sont pas des essais indépendants : quand le
match tourne bien, ils gagnent ensemble. La version 1 comptait chaque pari comme un essai : une stratégie qui
prenait 15 paris sur un match gagnant voyait son intervalle de confiance se resserrer et sa solidité monter, alors
qu'elle n'avait eu qu'une seule chance.

La version 2 réunit d'abord les paris de chaque match (gains et mises additionnés, liens de matchs de
`cotes/evenements.py`), puis calcule tout sur ces matchs.

## Formule

Note = rentabilité prudente (25) + robustesse (20) + valeur (25) + régularité (15) + solidité (15). Chaque part est
une échelle linéaire bornée : 0 sous le seuil bas, le maximum au-dessus du seuil haut.

| Part | Mesure | 0 point | Maximum |
|---|---|---|---|
| Rentabilité prudente /25 | Borne basse à 80 % de l'intervalle de confiance du ROI, variance calculée **par match** | −10 % | +5 % |
| Robustesse /12 | ROI sans les meilleurs matchs (5 % des matchs, au moins un) | −5 % | +3 % |
| Robustesse /8 | Part du meilleur match dans les gains (somme des matchs gagnants) | 30 % | 5 % |
| Valeur /15 | CLV moyenne par match × k / (k + 30), k = matchs avec une CLV | −1 % | +3 % |
| Valeur /10 | Part des matchs qui battent la clôture, (positifs + 15) / (k + 30) | 45 % | 65 % |
| Régularité /7,5 | Part des jours gagnants, (jours gagnants + 2) / (jours + 4) | 35 % | 65 % |
| Régularité /7,5 | Plus forte baisse / (mise moyenne par match × √matchs) | 3,0 | 0,5 |
| Solidité /9 | log10 du nombre de matchs réglés | 20 matchs | 400 matchs |
| Solidité /3 | Jours d'observation | 0 | 15 jours |
| Solidité /3 | Cote moyenne | 8 | 3 |

- Pas de note sous 10 matchs réglés ; note **provisoire** sous 50 matchs.
- Les termes ajoutés (+ 30, + 15, + 2, + 4) ramènent vers une valeur neutre les mesures faites sur peu de matchs.
- La robustesse répond directement à la question « le résultat tient-il à un ou deux matchs chanceux ? ».
- La cote moyenne pénalise les longues cotes (docs/etude-longues-cotes.md).

La note publiée garde ses mesures (`note.mesures`) : ROI, borne basse, ROI sans les meilleurs matchs, nombre de
matchs retirés, part du meilleur match, paris par match, CLV ajustée, part de CLV positives, jours gagnants, baisse
normalisée, cote moyenne.

## Effet sur les données réelles (suivi au 8/11/2026, mise fixe)

| Stratégie | Paris réglés | Matchs | ROI | Note v1 | Note v2 | Ce qui change |
|---|---|---|---|---|---|---|
| Polymarket · 1,5–3 · ≥ 2 % · 36 h | 110 | 109 | +22,3 % | 85 | 88 | Un pari par match : rien ne bouge |
| Pinnacle · 1,3–2 · ≥ 2 % · 36 h | 284 | 284 | +8,9 % | 82 | 85 | Idem |
| Gemini Défi 3 · Sniper principaux | 55 | 31 | +30,1 % | 71 | 38 | 40 % des gains viennent d'un match ; ROI −4 % sans ses 2 meilleurs |
| Base · Polymarket | 721 | 425 | +10,1 % | 69 | 56 | ROI −15 % sans ses 22 meilleurs matchs |
| Convergence ≥ 2 | 341 | 236 | +1,6 % | 63 | 52 | Borne basse −6,7 % par match (−4,8 % par pari) |

## Mise à jour et progression

La note est recalculée à chaque cycle (environ toutes les 5 minutes), pour chaque période et chaque mise. Le dernier
calcul de chaque jour (heure de Paris, mise fixe, suivi prospectif) est gardé 60 jours dans `notes_historique.json`
(branche `donnees`, `cotes/historique_notes.py`), avec la version de la formule : les notes de la version 1 ne sont
pas comparées aux notes de la version 2 (l'historique repart du 8/11/2026). La page Stratégies montre l'évolution
depuis la veille et sur 7 jours (▲ / ▼).

## Lecture

- 70 et plus : rentable avec une marge de sécurité, robuste, régulière, sur un échantillon sérieux.
- 40 à 70 : prometteuse ou solide sans rentabilité démontrée.
- Moins de 40 : rentabilité non démontrée, fragile, irrégulière ou trop peu de matchs.

Les stratégies recommandées (docs/recommandees.md) s'appuient sur cette note.

## Limites

Note descriptive : une bonne note ne garantit aucun gain futur. Les stratégies se recoupent (mêmes paris) et sont
comparées sur des périodes de longueurs différentes. Deux matchs d'une même journée ne sont pas tout à fait
indépendants non plus (forme, météo, erreurs de cotes communes) : la note ne le corrige pas. Les seuils sont des
choix raisonnés, pas ajustés pour faire gagner une stratégie.
