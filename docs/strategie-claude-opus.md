# Claude Opus : Valeur solide et déclinaisons

Stratégie conçue le 2/11/2026 par Claude (Opus 5.5). Suivie à partir du **3/11/2026 à 00:00 UTC** (01:00 à Paris),
figée au lancement, sans rejeu : seules les nouvelles détections comptent. Code : `cotes/strategie_claude_opus.py`,
clé `claude_opus_solide`.

## Idée

Ne parier que là où la cote juste est fiable et où l'avantage est réel plutôt que du bruit. Chaque règle a une
raison, mesurée sur la période de construction ou sur l'étude de calibration (docs/etude-longues-cotes.md) :

| Règle | Raison |
|---|---|
| Pinnacle, Polymarket, Betfair ou Consensus, lus depuis ≤ 180 s | Références sharp, prix récent (lue depuis 3 à 5 min : ROI −28 %) |
| Betclic, Unibet, PMU ou NetBet | Books qui corrigent lentement. Winamax corrige vite (CLV −0,44 %), OlyBet perd (−20 %) |
| Cote 1,60–3,50 | Cotes justes calibrées. Sous 1,60, la marge mange l'avantage (ROI −1,9 % malgré la CLV) |
| Écart 4–15 % | Les écarts de 2–3 % battent à peine la clôture (CLV +0,24 %). Au-delà de 15 %, plutôt une erreur d'association |
| Match dans les 12 h | Plus tôt, la référence bouge encore : CLV +0,12 % au-delà de 12 h |
| Ni score exact ni mi-temps/fin | Probabilités surestimées de moitié |
| Équipes non inversées, une mise par cote française | Comme les autres stratégies : la première détection qui passe la règle |

Mise fictive de 10 €, aucun plafond par jour ni par match. Les plafonds ont été testés : ils dégradaient
les deux périodes.

## Méthode

- Données : paris enregistrés, branche `donnees` au 2/11/2026 15:44 UTC. Sélection causale : la première
  détection qui passe la règle pour chaque cote française, sans lire ni statut, ni gain, ni CLV.
- **Construction** : détections du 7 au 22/10. **Validation** : du 23 au 2/11, évaluée une seule fois, sans retouche.
- Sept candidates, toutes listées ci-dessous. Le choix s'est fait sur la **note /100 de la construction**
  (docs/notation-strategies.md), pas sur la validation.

| Candidate | Construction : paris · ROI · CLV · note | Validation : paris · ROI · CLV · note |
|---|---|---|
| B0 base : marchés classiques, cote ≤ 5, références sharp | 1 550 · +7,9 % · +1,68 % · 88 | 1 040 · −0,7 % · −0,48 % · 52 |
| **C1 : books lents, écart 4–15 %, cote 1,6–3,5, ≤ 12 h, référence ≤ 180 s (retenue)** | **219 · +23,4 % · +6,94 % · 90** | **136 · +2,9 % · +4,21 % · 57** |
| C2 : C1 hors football | 161 · +30,4 % · +6,91 % · 87 | 107 · +3,5 % · +4,49 % · 54 |
| C3 : C1, marchés principaux et handicaps | 150 · +31,3 % · +7,22 % · 88 | 77 · +5,5 % · +3,88 % · 48 |
| C4 : C1 + 1 pari par match, ≤ 10 par jour | 110 · +4,8 % · +4,88 % · 58 | 73 · −9,2 % · +2,87 % · 36 |
| C5 : C2 + 1 pari par match, ≤ 10 par jour | 87 · +11,2 % · +4,38 % · 66 | 64 · −1,4 % · +3,62 % · 42 |
| C6 : C3 hors football + 1 pari par match | 62 · +33,9 % · +4,91 % · 83 | 37 · +16,8 % · +2,99 % · 49 |

## Validation de C1

- Les deux moitiés sont positives : du 23 au 27/10, 56 paris, ROI +4,3 %, CLV +4,59 % ; du 28/10 au 2/11,
  80 paris, ROI +1,9 %, CLV +3,97 %.
- La CLV est positive pour chaque référence (Pinnacle +3,55 %, Polymarket +6,48 %), chaque bookmaker et presque
  chaque sport.
- Sur la même période, l'univers de base perd (CLV −0,48 %). Les filtres de C1 gardent donc leur effet.
- Sur tout l'historique (7/10–2/11) : 355 paris, ROI +15,5 %, CLV +5,8 %, note 92. **Chiffre optimiste** : il
  inclut la période qui a servi à choisir les règles.

## Déclinaisons (deuxième salve du 2/11)

Six autres idées, testées avec le même protocole. Les seuils de choix ont été fixés **avant** de regarder la
validation : note de construction ≥ 75, et en validation CLV ≥ +1 % et ROI ≥ −5 %.

| Idée | Construction : paris · ROI · CLV · note | Validation : paris · ROI · CLV · note | Décision |
|---|---|---|---|
| Proche : ≤ 3 h, écart 3–15 %, cote 1,5–3,5, référence ≤ 120 s | 76 · −41,8 % · +3,32 % · 34 | 99 · −11,7 % · +3,41 % · 35 | écartée |
| Consensus seul, cote 1,5–4, écart ≥ 3 %, ≤ 24 h | 60 · +16,2 % · +7,03 % · 57 | 26 · +14,8 % · +4,81 % · 41 | écartée (trop peu de paris), à surveiller |
| **Handicaps : lignes, books lents, cote 1,6–2,6, écart 4–15 %** | 87 · +43,3 % · +9,10 % · 88 | 29 · −1,5 % · +5,47 % · 36 | **retenue** |
| Polymarket seul, hors Winamax, cote 1,6–3,5, écart 4–15 %, ≤ 24 h | 46 · −8,1 % · +6,74 % · 42 | 31 · +18,1 % · +4,54 % · 47 | écartée |
| **Hors football : Valeur solide sans le football** | 161 · +30,4 % · +6,91 % · 87 | 107 · +3,5 % · +4,49 % · 54 | **retenue** |
| **Favoris réguliers : cote 1,6–2,2, écart 4–12 %** | 141 · +20,8 % · +5,38 % · 89 | 84 · +0,8 % · +3,89 % · 48 | **retenue** |

Retenues, lancées en même temps que Valeur solide (3/11/2026 00:00 UTC), mêmes règles communes :

| Stratégie (clé) | Différence avec Valeur solide | Tout l'historique : paris · ROI · CLV · note |
|---|---|---|
| Claude Opus · Favoris réguliers (`claude_opus_favoris`) | cote 1,60–2,20, écart 4–12 % : moins de variance par pari | 225 · +13,3 % · +4,75 % · 89 |
| Claude Opus · Hors football (`claude_opus_hors_foot`) | sans le football, le marché le plus efficient | 268 · +19,6 % · +5,85 % · 89 |
| Claude Opus · Handicaps (`claude_opus_handicaps`) | lignes seulement (asiatique, à 3 issues, jeux, sets), cote 1,60–2,60 | 116 · +32,1 % · +8,15 % · 87 |

Les chiffres sur tout l'historique sont optimistes : ils incluent la période qui a servi à choisir. Ce sont
des **sous-ensembles de Valeur solide**, donc fortement corrélés avec elle : quand elle a une mauvaise semaine,
elles en auront une aussi. Les suivre ensemble montre lequel des trois angles (cotes courtes, hors football,
lignes) tient le mieux dans la durée. Ce n'est pas une diversification.

## Ce qu'il faut en attendre

Le signal solide, c'est la **CLV de +4 % en validation**. Les cotes prises battent nettement la clôture. Le ROI
de validation (+2,9 % sur 136 paris) n'est pas significatif à lui seul. Attente raisonnable : un ROI positif de
quelques pour cent, avec des semaines négatives. Pas les +23 % de la construction.

## Limites

- Choix fait après exploration de la période de construction (plusieurs découpages regardés) : les résultats
  de construction sont optimistes par nature.
- Recoupe en partie Claude Défi 5 (Betclic et PMU, cote 1,30–3, écart 6–30 %), sans être identique.
- Un mois de données ; les paris d'un même match sont corrélés. Aucune rentabilité future démontrée.
