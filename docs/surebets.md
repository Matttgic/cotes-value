# Surebets entre bookmakers français

Ajouté le 16/11/2026. Code : `cotes/surebets.py` (détection, suivi), `cotes/pipeline/analyse.py` (`surebets_du_cycle`),
`web/boosts.js` (onglet **Boosts**), `cotes/alertes/promos.py` (Pushover), `etudes/etude_surebets.py` (rejeu).

## Principe

Un surebet : des cotes de bookmakers différents qui, jouées ensemble, gagnent quoi qu'il arrive. Pour un même marché
(même match, période et ligne), on prend la meilleure cote française de chaque issue. Si Σ 1/cote < 1, une mise
proportionnelle à 1/cote sur chaque issue rend la même somme quel que soit le résultat :

    rendement = 1 / Σ(1/cote) − 1

Exemple : Winamax 2,10 sur un joueur, Betclic 2,10 sur l'autre ; 50 € de chaque côté rendent 105 € quoi qu'il arrive.

## Détection, à chaque cycle

- **Même match** : l'association du cycle relie déjà chaque match français à une rencontre de référence. Deux matchs
  français reliés à la même rencontre (Pinnacle d'abord, puis Polymarket, Matchbook, Smarkets) sont le même match ; un
  match relié à l'envers est retourné avant la comparaison.
- **Marchés sans remboursement possible** : 1N2 et handicap à trois issues ; vainqueur, les deux équipes marquent,
  handicaps et totaux à demi-ligne (2,5, −1,5…) ; double chance contre l'issue qui lui manque au 1N2. Lignes entières,
  quarts de ligne, remboursé si nul, score exact et mi-temps/fin sont écartés.
- **Garde-fous** : deux bookmakers au moins ; match pas commencé ; cotes lues depuis moins de 10 minutes (25, 32 et
  39 minutes pour un match à plus de 6 h chez PMU, Unibet et Betclic, qui le relisent par tranches, comme les
  alertes) ; intitulé contrôlé conforme et match bien associé (`cotes/controle.py`) ; une cote qui a une cote juste à
  la référence doit en être proche (−30 % à +25 %).
- **Vérifié** : toutes les jambes ont une cote juste chez la référence et leurs probabilités justes font 1 (à 3 points
  près) : les issues couvrent bien tous les résultats. **Non vérifié** : la référence ne propose pas la ligne ; affiché
  avec un avertissement (contrôler période et prolongation avant de miser).
- **Suspect** (affiché à part, jamais suivi ni envoyé) : rendement au-delà de 15 %, ou de 5 % quand il n'est pas
  vérifié.

Les mises sont arrondies à l'euro, sans dépasser la somme choisie, de façon que le pire résultat rapporte le plus
(`repartir` ; la page refait le même calcul pour la somme saisie).

## Suivi et fichiers

`donnees/surebets.json` (JSON compact, réécrit à chaque cycle) : les surebets du cycle (`actuels`), les épisodes des
21 derniers jours (`episodes` : premier et dernier relevé, nombre de relevés, rendement à la détection et au maximum,
jambes) et le journal du cycle (familles comparées, raisons d'exclusion). Un trou de moins de 11 minutes ne coupe pas
un épisode. « Gain si tous pris » : 100 € répartis aux cotes du premier relevé de chaque épisode.

## Alertes

Case **Surebets** du bloc « Alertes Pushover » (onglet Notifs) : un message par épisode, dès que le rendement atteint
`SUREBET_SEUIL_ALERTE` (1 % par défaut), relevé de moins de 12 minutes. Mises calculées pour 10 % de
`PUSHOVER_BANKROLL` (100 € par défaut), lien vers le match chez le premier bookmaker.

## Ce que l'historique contient déjà (rejeu des 13 et 14/11/2026)

`python etudes/etude_surebets.py --donnees donnees --jours 2026-11-13 2026-11-14 [--horizon 36]` rejoue cycle par cycle
les cotes françaises (`cotes/`), les cotes justes (`references/`) et les rapprochements (`correspondances/`), avec le
même détecteur. Limites du rejeu : une cote non retirée est supposée encore proposée, l'âge des cotes n'est pas
mesurable et le contrôle des intitulés n'est pas rejoué. C'est donc un **plafond**.

| Matchs pris | Surebets (épisodes) | dont vérifiés | Rendement des vérifiés | Gain si tous pris (100 € répartis) | Vus un seul relevé |
|---|---|---|---|---|---|
| Début dans les 6 h | 13 (10 le 13/11, 3 le 14/11) | 5 | 2 sous 0,5 %, 2 de 0,5 à 1 %, 1 de 1 à 2 % | 11,70 € (vérifiés : 1,24 €) | 7 |
| Tous (36 h) | 30 (11 et 19) | 9 | 4 sous 0,5 %, 2 de 0,5 à 1 %, 3 de 1 à 2 % | 28,15 € (vérifiés : 3,48 €) | 16 |

Paires de bookmakers (36 h) : Betclic + PMU 12, OlyBet + PMU 9, Betclic + Winamax 2, OlyBet + Winamax 2. Le plus gros
vérifié : Grenade – St Kitts et Nevis, handicap +2,5, PMU 1,57 et OlyBet 2,90 (+1,86 %, un seul relevé). Écartés :
117 relevés suspects (trop beaux sans cote juste) ; au premier rejeu, sans les règles des 5 et 15 %, les handicaps de
Chypre – Norvège (basket) donnaient huit « surebets » de 9 à 12 %, dus à une cote Betclic 23 % au-dessus de la cote
juste.

Lecture : les surebets entre bookmakers français existent mais sont rares (une quinzaine par jour au plus, plafond du
rejeu) et petits (moins de 2 % une fois vérifiés), souvent concentrés sur un match mal coté par un bookmaker lent (PMU,
OlyBet). La moitié ne dure qu'un relevé (5 minutes) : sans alerte, ils sont invisibles. Rapporté à 100 € par surebet,
c'est quelques euros par jour au mieux : un complément, pas une source de revenu. Les plus gros « surebets » sont
presque tous des erreurs de lecture, d'où les règles des 15 % (cote contre cote juste) et des 5 % (sans cote juste).

## Limites

Garanti sur le papier seulement : la deuxième cote peut bouger avant la deuxième mise (jouer d'abord la cote la plus
rare), la mise peut être plafonnée, et les comptes qui ne jouent que des surebets finissent limités. Tennis : en cas
d'abandon, Winamax, Unibet, NetBet et PMU annulent le vainqueur du match (docs/reglements.md) ; la règle de Betclic et
d'OlyBet n'a pas pu être lue, un surebet de tennis avec l'un d'eux reste exposé à un abandon. Hockey et basket : une
période différente d'un bookmaker à l'autre (prolongation) casse le surebet ; c'est ce que la vérification par la
cote juste contrôle.
