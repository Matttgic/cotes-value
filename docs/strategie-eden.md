# Eden v1

Simulation depuis le **19 octobre 2026 à 16 h, heure de Paris**
(`2026-10-19T14:00:00+00:00`). Aucun pari réel. Le bilan de suivi ne compte que
les détections à partir de cette heure. Sur le relevé utilisé pour écrire la
règle, ce suivi est vide.

## Règle

Eden ne retient une cote française que si, à l'instant de la détection :

- la référence est Pinnacle sans marge ;
- le bookmaker est Winamax, Betclic, Unibet ou PMU, et la ligne n'est pas marquée suspecte ;
- le sport est le football, le basket, le hockey, le baseball, le rugby, le handball, le football américain, le tennis ou le volley ;
- le marché est un 1N2, un vainqueur, un total ou un handicap, sur le match entier ou le temps réglementaire ;
- le tennis et le volley ne sont pris qu'en vainqueur du match ;
- la ligne de total ou de handicap n'est pas un quart de point ;
- la cote est entre 1,30 et 2,00, l'edge entre 2 % et 8 %, et l'edge est cohérent avec la cote juste (écart d'au plus 0,002) ;
- le match commence entre 30 minutes et 12 heures plus tard ;
- la référence a été lue depuis 10 minutes au plus ;
- la preuve de correspondance porte un identifiant de match, une ressemblance d'au moins 0,85 et un contrôle conforme ;
- les intitulés ne désignent pas des jeunes, une réserve ou une compétition féminine non alignée.

Chaque bookmaker français du même match peut recevoir sa mise de 10 €. Deux
références du même bookmaker n'en font qu'une. Six prises maximum par jour
civil de Paris. À heure égale : edge décroissant, cote croissante, bookmaker,
puis identifiant. Le filtre ne lit ni le statut, ni le gain, ni la CLV, ni la
date de règlement.

Eden vote dans Convergence ≥ 2 à partir de son lancement. Elle ne rejoint pas
Convergence ≥ 3 hors M3, dont le texte figé ne nomme que Claude, ChatGPT,
Gemini et Jules.

## Pourquoi ces bornes

Le [protocole du 14 octobre](comparaison-strategies.md) n'a retenu aucune des
36 règles. Les quatre variantes qui atteignaient 20 paris réglés en
construction avaient un ROI négatif, dont Pinnacle 1,30–2,00 / edge 2 % / 36 h
à −1,04 % (28 réglés) et Pinnacle 2,00–5,00 entre −43 % et −61 %. Eden ne
promeut pas la cellule qui a le mieux rendu ensuite. Elle resserre une
enveloppe de risque déjà écrite, puis se mesure à blanc.

Les chiffres ci-dessous décrivent le filtre de qualité commun
(Pinnacle, Betfair, Polymarket) sur la branche `donnees`, commit
`c404b5c3fe62065968bed0bf796b2f8aab19e2c9`, dernière détection
`2026-10-19T11:20:54+00:00` : 824 prises, 782 réglées, ROI +4,34 %, CLV
+2,42 %. Avant le 14 octobre à 12:00 UTC, ce même filtre est à −5,52 %
(404 réglés) avec une CLV de +2,25 %. Après, il est à +14,88 % (378 réglés).
Cette seconde moitié est une série courte. Elle ne valide rien.

- **Pinnacle seulement.** Sur ce filtre, Pinnacle a une CLV de +2,70 %
  (399 clôtures exploitables sur 519 réglés) et un ROI de +8,61 %. Polymarket
  est à −0,06 % de CLV. Betfair est à −18,46 % de ROI (83 réglés). Une CLV
  positive ne démontre pas un gain futur.
- **Cotes 1,30–2,00.** Le plafond est une borne de la grille du protocole.
  Au-dessus de 5,00, le ROI du filtre de qualité est de −55,5 % (94 réglés) ;
  sur Pinnacle seul, −100 % (38 réglés). La bande 3,01–5,00 passe de −16 %
  avant le 14 octobre à +50 % après. La bande 1,51–2,00 reste positive des
  deux côtés (+21,4 % puis +19,0 %). Le plancher 1,30 est celui de la grille.
- **Edge 2–8 %.** Le plancher est celui du protocole. Dans la fenêtre
  Pinnacle, cotes 1,30–2,00 et 30 min–12 h, l'edge 3–5 % passe de +38 %
  (25 réglés) à −10 % (32 réglés) de part et d'autre du 14 octobre. L'edge
  2–3 % reste positif des deux côtés, sur 18 puis 17 réglés. Relever le
  plancher aurait donc choisi la tranche qui s'inverse. Avant le 14 octobre,
  sur tout le filtre de qualité, 8–12 % est à −20 % et au-delà de 12 % à
  −64 %, avec une CLV très haute : des cotes aberrantes, pas un edge plus
  fort. Huit pour cent coupe cette queue. Ce n'est pas un optimum.
- **30 minutes à 12 heures.** Au-delà de 24 heures, la CLV du filtre de
  qualité est de −1,65 % (−2,08 % avant le 14 octobre). Douze heures est
  l'horizon de Claude et de Jules ; les règles à 36 heures n'ont pas passé
  le protocole. La tranche 12–24 h change de signe. Le plancher de 30 minutes
  est celui de Gemini, parce que 15–30 minutes laisse trop peu de temps.
  Sur tout le relevé ce créneau est à −26 % (42 réglés), mais avant le
  14 octobre il ne compte que 12 paris, de signe opposé.
- **Fraîcheur 10 minutes, ressemblance 0,85.** Toutes les prises de qualité
  de ce relevé avaient moins de 4 minutes. Le plafond de 10 minutes ne change
  donc pas l'historique ; il borne les lectures futures. La ressemblance
  0,85–0,90 est négative sur l'ensemble (−26 %), mais positive quand la cote
  est d'au plus 2,00. Le seuil commun de 0,85 est conservé.
- **Marchés et sports inchangés par rapport à Jules.** Le football du filtre
  de qualité est à −8 % de ROI malgré une CLV positive. Le basket est fort,
  et c'est précisément le piège de M3, choisie après les résultats. Le 1N2
  est négatif et le handicap positif. Aucun de ces constats ne sert à retirer
  un marché ou un sport.

Le football féminin, les jeunes et les réserves sont écartés par les mêmes
mots que Gemini. OlyBet n'est pas dans le périmètre des stratégies déjà
lancées.

## Rejeu descriptif

Même relevé, sélecteur Eden appliqué depuis le 7 octobre 2026 à 00:00
(Paris), avec le plafond de six prises par jour. Coupure de connaissance :
tous les règlements antérieurs au 20 octobre 2026 à 00:00 UTC. Empreinte
SHA-256 de `paris.json` :
`500745fdc1c0c222e68a728a289788a62422a8230833ecdfd09c7332a0c4b04d`.
Empreinte des 44 identifiants sélectionnés :
`883a2f3260a8fade3830dd11ec721e3b9c581a340274365892c4687aac827c14`.
Le détail chiffré est dans [strategie-eden.json](strategie-eden.json).

| Fenêtre | Réglés | Gain net | ROI | CLV |
|---|---:|---:|---:|---:|
| Ensemble, 7–19 octobre | 44 | −8,70 € | −1,98 % | +1,33 % (28/44) |
| Détections avant le 14/10 à 12:00 UTC | 19 | +31,90 € | +16,79 % | +1,79 % (13/19) |
| Détections après | 25 | −40,60 € | −16,24 % | +0,94 % (15/25) |
| Construction (début de match, 7–10 oct.) | 8 | +21,20 € | +26,50 % | +0,73 % (3/8) |
| Validation (11–12 oct.) | 6 | −8,40 € | −14,00 % | +2,74 % (5/6) |
| Test (13 oct.) | 4 | +10,60 € | +26,50 % | −0,45 % (4/4) |

La construction n'atteint ni 20 réglés ni 50 % de couverture de CLV. La
validation a un ROI négatif. Le test a une CLV négative. Le signe du ROI
s'inverse après le 14 octobre. Dans le sélecteur complet, la tranche d'edge
2–3 % est négative des deux côtés de cette date : le constat sur la fenêtre
de favoris sans plafond journalier ne se retrouve pas une fois la règle
assemblée. Rien de tout cela n'est une validation.

Le suivi officiel sur ce relevé compte **0 pari** : la dernière détection est
à 11:20 UTC, avant les 14:00 UTC du lancement.

## Lecture sur le site

- **Bilan → Eden** : détections depuis le 19 octobre à 16 h (Paris).
- **Voir les paris Eden** : sélections de ce suivi.
- **Stratégies → Eden** : ligne prospective, vide tant qu'aucune détection
  postérieure au lancement n'est présente.
- **Stratégies → Historique** : rejeu descriptif depuis le 7 octobre. Il ne
  remplace pas le bilan de suivi.

Aucun rendement futur n'est annoncé.
