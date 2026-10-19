# Eden v1

Simulation depuis le **19 octobre 2026 à 20 h, heure de Paris**
(`2026-10-19T18:00:00+00:00`). Aucun pari réel. Le bilan de suivi ne compte que
les détections à partir de cette heure. Sur le relevé utilisé pour figer la
règle, ce suivi est vide : la dernière détection est à 13:36 UTC.

## Règle

Eden retient une cote française si, à l'instant de la détection :

- la référence est Pinnacle sans marge ou Polymarket ;
- le bookmaker est Winamax, Betclic, Unibet ou PMU, et la ligne n'est pas suspecte ;
- la cote est entre 1,30 et 2,00 ;
- l'edge est entre 2 % et 12 %, cohérent avec la cote juste à 0,002 près ;
- le match commence entre 30 minutes et 24 heures plus tard ;
- la référence a été lue depuis 15 minutes au plus ;
- la preuve de correspondance a un identifiant de match, une ressemblance d'au moins 0,85 et un contrôle conforme ;
- le marché est un 1N2, un vainqueur, une double chance, un remboursé si nul, un total ou un handicap, sur le match entier ou le temps réglementaire ;
- le tennis et le volley ne sont pris qu'en vainqueur du match ;
- la ligne de total ou de handicap n'est pas un quart de point ;
- les équipes ne sont pas des jeunes ni une réserve.

Chaque bookmaker français du même match peut recevoir sa mise de 10 €. Deux
références du même bookmaker n'en font qu'une. Il n'y a pas de plafond
journalier. Le filtre ne lit ni le statut, ni le gain, ni la CLV.

Les matchs explicitement féminins restent inclus. Les retirer, comme le fait
le filtre linguistique de Gemini, fait passer la validation sous zéro. Les
jeunes sont exclus ; ce relevé n'en contenait aucun dans la règle.

Eden vote dans Convergence ≥ 2 à partir de son lancement. Elle ne rejoint pas
Convergence ≥ 3 hors M3.

## Comment la règle a été choisie

Grille déclarée avant de regarder le test : 5 références × 7 bandes de cotes ×
6 plages d'edge × 6 horizons, soit **1 260 combinaisons**, sur les prises qui
passent le contrôle de qualité commun. Sport et marché libres. Coupure par
début de match, heure de Paris :

- construction : jusqu'au 14 octobre à 0 h ;
- validation : du 14 au 16 octobre ;
- test : du 17 au 19 octobre.

Une combinaison n'était gardée que si la construction avait au moins 20 réglés,
un ROI positif, une CLV positive, une couverture de CLV d'au moins 50 %, et un
ROI encore positif sans le meilleur pari — et la même chose en validation, avec
au moins 10 réglés. Le test n'entrait pas dans ce filtre.

La région qui ressort est celle des favoris 1,30–2,00. Au-dessus de 2,00, le
test s'aplatit (1,30–2,50 : ROI de test +2,6 % ; 1,50–3,00 : +1,2 %, et négatif
sans le meilleur pari). Au-delà de 24 h, la CLV de construction est négative.
Avant 30 minutes, le ROI de construction est négatif (7 réglés, −33 %). Betfair
n'est plus collecté. Polymarket seul n'a pas le volume. Pinnacle seul laisse
la fenêtre du 11–12 octobre négative ; Pinnacle et Polymarket ensemble la
laissent légèrement positive.

Les stratégies déjà en place, rejouées sur les mêmes fenêtres, ne tiennent pas
toutes les trois : Gemini est négative en validation, Jules et Jules v2 sont
négatives sur le test, Convergence ≥ 2 aussi. M3 reste positive mais sa règle
a été choisie après les résultats, et son test sans le meilleur pari est négatif.

## Chiffres du sélecteur livré

Relevé `donnees`, commit `a13b37bd9dd7408621e745b370bdc0b2f8289dcb`.
SHA-256 de `paris.json` :
`d68b163039f0af297746b571bd91667271909668fa29fe8703166374bb32676a`.
Sélecteur appliqué depuis le 7 octobre 2026 à 0 h (Paris). Une mise par
bookmaker. Détail dans [strategie-eden.json](strategie-eden.json).

| Fenêtre | Réglés | Gain net | ROI | ROI sans le meilleur | CLV |
|---|---:|---:|---:|---:|---:|
| Construction (jusqu'au 13 oct.) | 48 | +112,20 € | +23,38 % | +21,74 % | +2,40 % (37/48) |
| Validation (14–16 oct.) | 41 | +71,50 € | +17,44 % | +15,38 % | +0,93 % (33/41) |
| Test (17–19 oct.) | 45 | +89,90 € | +19,98 % | +18,20 % | +0,87 % (29/45) |
| Dont 7–10 oct. | 21 | +40,00 € | +19,05 % | +15,00 % | +2,76 % (13/21) |
| Dont 11–12 oct. | 16 | +6,00 € | +3,75 % | −2,40 % | +0,70 % (15/16) |

Le test compte 6 prises encore non réglées au relevé. Elles ne sont ni gagnées
ni perdues. La baisse maximale du cumul est de 35,90 € en construction, 40 €
en validation et 21,90 € sur le test. Le pire jour est de −13,40 €, −14,50 €
et −6,50 €.

Une mise par match, tous bookmakers confondus, reste positive sur les trois
fenêtres. Le 11–12 octobre, retirer le meilleur pari suffit à rendre ces 16
paris légèrement négatifs. C'est la fenêtre la plus fragile.

**Sensibilité sport.** La validation est portée par le basket (17 des 41
réglés). Sans le basket, la validation passe à −5,12 % (24 réglés, CLV
+0,45 %). La construction sans basket reste à +16,63 % (41 réglés, CLV
+3,57 %). Le test sans basket reste à +20,14 % (42 réglés, CLV +0,72 %).
Retirer les intitulés féminins fait la même chose à la validation (−5,96 %,
25 réglés) : ces matchs sont surtout du basket féminin qui avait passé le
contrôle de correspondance. Ils sont donc gardés. Ce n'est pas une niche
ajoutée après coup, c'est l'univers de qualité tel qu'il est enregistré.

Le suivi officiel sur ce relevé compte **0 pari**.

## Lecture sur le site

- **Bilan → Eden** : détections depuis le 19 octobre à 20 h (Paris).
- **Stratégies → Eden** : la ligne prospective démarre vide sur ce relevé.
- **Stratégies → Historique** : rejeu descriptif depuis le 7 octobre.

Ces rendements sont ceux d'un rejeu. Ils ne sont pas une prévision.
