# Audit de la justesse des bilans

Fait le 13/11/2026 sur la branche `donnees` (commit `e727827`) : 6 117 paris détectés du 05/10 au 13/11, dont
6 008 réglés. Tous les chiffres sortent de `python scripts/audit_bilans.py --donnees <dossier>` (lecture seule,
10 secondes). ROI = gain / mises, mise fixe de 10 €.

## Verdict

1. **Le ROI affiché (+3,19 %, « Paris uniques ») n'existe que par le plafond de cote à 5, choisi le 11/11 sur
   ces mêmes résultats.** Sans lui : −6,20 %. Depuis le plafond : 82 paris, −1,05 %. Rien n'est démontré.
2. **L'incertitude affichée est trop étroite de 39 %** : les paris d'un même match gagnent ou perdent ensemble.
   Intervalle à 95 % réel du ROI affiché : [−1,5 ; +7,9], zéro compris.
3. **« Toutes réf. » compte 1 157 paris deux fois ou plus** (même cote vue par plusieurs références).
4. **Le règlement est juste à 4 paris près sur 5 688 recalculés** : 3 « vainqueur » de hockey remboursés à
   tort (corrigé dans le code) et 1 score contradictoire. 12 autres paris dépendent d'une règle non lue.
5. **Aucune anticipation ni tri de survivants dans les horodatages et les suppressions** : 0 anomalie mesurée.

Limite : les scores eux-mêmes n'ont pas pu être recontrôlés sur une source extérieure. Depuis cette session,
`site.api.espn.com`, `www.thesportsdb.com` et `www.flashscore.fr` sont bloqués par le réseau, et la recherche web
ne connaît pas ces matchs. Le contrôle des scores est donc interne (recoupements entre bookmakers et sources).

## Problèmes trouvés

| # | Problème | Où | Exemple réel | Effet sur le ROI | État |
|---|---|---|---|---|---|
| 1 | Plafond de cote appliqué après coup à tout l'historique | `scripts/site_web.py:613-614`, `cotes/simulation.py:36` | 1 095 paris à cote > 5 (−46,73 %) sortis des bilans le 11/11 | Uniques : −6,20 % → **+3,19 %** (+9,4 pts) ; Toutes : −4,35 % → +5,09 % | À décider |
| 2 | Intervalle de confiance calculé comme si les paris étaient indépendants | `web/modele.html:488-489`, `cotes/simulation.py:381` | 26 paris uniques sur un seul match ; 2,07 en moyenne | Écart-type 1,73 → 2,40 pts ; IC [−0,2 ; +6,6] → [−1,5 ; +7,9] | À décider |
| 3 | « Toutes » : un pari par référence pour la même cote | `cotes/simulation.py:356` | PMU, Bermuda – Barbados, « Barbados » à 1,55 : 5 paris gagnés (Betfair, Consensus, Kalshi, Pinnacle, Polymarket) | 662 cotes, 1 157 paris en plus ; Toutes −4,35 % contre Uniques −6,20 % | Connu : lire « Uniques » |
| 4 | Hockey : score des 60 minutes pris pour un score final, « vainqueur » remboursé | `cotes/reglement.py:122` puis `:269` | `016561fae52bf691` Winamax, Colorado Eagles – Abbotsford Canucks 10/10, 3-3 (betmgm, interwetten-de), cote 1,58 ; aussi `54684aa01562052b`, `b603d0cd9c7293e8` | 3 paris : entre −30 € et +24,5 € (±0,08 pt sur le ROI affiché) | **Corrigé** (`reglement.py:262`) ; les 3 paris restent à vérifier |
| 5 | Même match, deux scores différents retenus au même cycle | `cotes/resultats.py:365` (rapprochement), détecté par `:658` | Dungannon – Carrick Rangers 10/10 : Winamax réglé sur 1-3 (espn, pmu, draftkings, unibet-uk), Betclic sur 2-4 (betmgm, draftkings, unibet-uk). « Score exact 1-3 » gagné chez l'un (`4cbbc836d7e78f49`, 17,0), perdu chez l'autre (`aa8ef1ac0718c6a3`, 18,75) | Un des deux est faux : +187,5 € ou −170 € (±0,3 pt sur Toutes ; hors plafond, donc 0 sur le site) | À vérifier à la main |
| 6 | PMU « Moneyline - 20UP Paiement anticipé » réglé comme une simple victoire | `cotes/pulsescore.py:300-304` | `ba24970488010699` Pelicans – Kings 30/10, Kings à 3,3, perdu 120-132 | 5 paris, 4 perdus ; au plus +128 € si l'équipe a mené de 20 points (improbable) | À décider |
| 7 | Tennis, abandon : « vainqueur » remboursé chez tous, règle Betclic et OlyBet non lue | `cotes/reglement.py:170-193` | `671e4f6041b07e22` Betclic, Pridankina – Badosa 03/11, 7-5 puis abandon, Pridankina à 3,8 | 2 paris : 0 ou +59 € | À vérifier |
| 8 | Basket, vainqueur de la 1re mi-temps remboursé sur égalité (Betclic), règle non lue | `cotes/reglement.py:269-270` | `b91fedda77d802c4` Leuven – Leiden 24/10, 25-25 à la mi-temps, cote 1,75 | 5 paris : 0 ou −50 € | À vérifier |
| 9 | Remboursés comptés dans les mises | `cotes/simulation.py:391` | 184 remboursés (3,1 % des mises) | Toutes : −4,35 % → −4,49 % sur les mises vraiment risquées | Convention, à garder en tête |
| 10 | « Avance ou gagne » : paris décidables laissés « à régler » | `cotes/reglement.py:272-287` | 0 pari en base (marché ajouté le 12/11) | Aucun à ce jour | **Corrigé** |

## 1. Anticipation

- **Horodatages** : 0 pari dont la cote, la référence ou la clôture est lue après le coup d'envoi ; 0 référence lue
  après la décision ; 0 règlement avant le début.
- **Prise fidèle** : les 6 117 paris sont retrouvés dans l'archive des opportunités. Sur les 5 814 pris à leur
  première vue, 0 cote et 0 heure de début diffèrent de ce qui était affiché à ce moment.
- **Match déjà commencé** : 12 paris pris après une heure de début annoncée plus tôt pour le même match
  (tennis décalé, NFL à 5 minutes près). 0,2 % des paris, sans effet mesurable.
- **Plafond rétroactif (problème 1)** : c'est le seul vrai biais d'anticipation, et le plus gros chiffre de
  l'audit. Le seuil de 5 a été choisi en regardant les résultats, puis appliqué aux paris d'avant.
  - 61 % du gain des cotes ≤ 5 vient de la seule tranche ]3 ; 4] : +29,46 % ± 25,7 sur 520 paris. Les tranches
    voisines font −0,31 % (]2 ; 3]) et −1,83 % (]4 ; 5]).
  - Par semaine, cotes ≤ 5 : −1,91 %, +13,47 %, +1,05 %, +9,08 %, −5,56 %, +17,31 %.
  - Hors échantillon (pris après le 11/11 15:30) : 82 paris, −1,05 %.
- **Stratégies** : 1 979 paris d'avant le registre du 17/10 n'ont pas de sélection figée ; leur appartenance à une
  stratégie est recalculée avec les règles d'aujourd'hui. À traiter stratégie par stratégie.

*Ce qui rendrait la conclusion fausse* : un ROI positif sur des paris pris après le plafond. Avec l'écart-type
mesuré, distinguer +3 % de zéro demande environ 10 000 paris uniques ; il y en a 82.

## 2. Survivant

- **27 paris supprimés à la main** (`scripts/cycle.py:988`, `:1125`) : tous retrouvés dans l'archive. 21 sur
  Dungannon – Carrick Rangers, 4 sur Olympiakos Nicosie – Aris Limassol, 2 sur Bridgeport – Toronto. Réglés avec
  le score de leurs frères : 13 gagnés, 11 perdus, 3 inconnus, **+313,8 € pour 240 € misés**. La suppression a
  donc retiré des gains : avec eux, Toutes passerait de −4,35 % à −3,81 %. Elle n'a pas embelli le bilan.
- **Remboursements à la main** : 91 statuts « remboursé » contre 15 gagnés et 15 perdus. Ils portent sur 43
  matchs entiers (annulés, forfaits) ; aucun de ces matchs n'a aussi un pari gagné ou perdu. Pas de tri pari par pari.
- **Non réglés** : 19 paris dont le match a commencé. Tous perdus : −4,65 % ; tous gagnés : −3,97 %.
- **Sans trace de règlement** : 190 paris des 5 au 7/10, +30,23 %. Invérifiables. Sur le site (≤ 5) : 152 paris, +3,57 %.
- **CLV** : 23 % des paris réglés n'ont pas de CLV de clôture, et ils font −16,64 % contre −0,77 % pour les
  autres. La CLV moyenne de « Toutes » (+2,34 %) décrit donc le meilleur sous-ensemble. Sur la vue du site,
  l'écart s'inverse (+7,30 % sans CLV, +2,15 % avec) : pas de biais dans un sens constant.

*Ce qui rendrait la conclusion fausse* : des suppressions faites hors de `resultats_manuels.json` (dans l'historique
git de `donnees`). Non contrôlé : l'historique local ne garde que 676 commits.

## 3. Double comptage

- 0 identifiant en double ; archives et registre fusionnés sans doublon.
- Entre références : 662 cotes sur 4 960, 1 157 paris en plus (problème 3).
- Entre bookmakers, dans « Uniques » : 351 sélections identiques, 459 paris en plus. Voulu (on mesure chaque
  bookmaker), mais ce ne sont pas des résultats indépendants.
- Par match : un seul pari par match (le premier) donne −7,73 % sur 2 365 matchs.
- Conséquence chiffrée : problème 2. La variance par match vaut 1,9 fois celle supposée par la page.

*Ce qui rendrait la conclusion fausse* : des paris d'un même match indépendants. Mesuré : ils ne le sont pas.

## 4. Règlement

Contrôles faits, sur les 5 688 paris réglés qui gardent leurs scores :

- **Recalcul par le code actuel** : 3 changent de statut (les 3 hockey du problème 4), 0 gain incohérent.
- **Moteur écrit à part** (`regler_independant`, deux demi-mises) : 0 désaccord.
- **Libellés** : sur 2 691 handicaps et totaux, 0 écart entre le texte du pari et la ligne ou le sens enregistrés.
- **Entre bookmakers** : 351 sélections identiques, 0 réglée différemment ; 1 conflit de score (problème 5).

Par règle demandée :

- **Quarts asiatiques** : 0 pari en x,25 ou x,75 dans les données. Le code est juste sur toutes les lignes de
  −3,5 à +3,5 et tous les scores jusqu'à 4-4 (test). **Push** : 77 lignes entières réglées, 22 remboursées, toutes justes.
- **Hockey** : 86 matchs sur 412 à égalité après 60 minutes. Le but de prolongation ou de tirs au but est
  compté, sauf quand les sources donnent le score des 60 minutes comme final (problème 4). 27 handicaps
  libellés « temps réglementaire » sont réglés prolongation incluse : lignes ±1,5 et ±3,5 seulement, 0 statut
  différent sur 60 minutes (une prolongation ne donne qu'un but d'écart).
- **Basket** : somme des périodes égale au score sur tous les paris ; prolongation incluse partout, comme les libellés.
- **Périodes** : aucun libellé « prolongation » rangé en temps réglementaire.
- **Football sans mi-temps** : 486 paris sur 193 matchs réglés sur le seul score final (`reglement.py:109-110`),
  dont 49 paris sur 19 matchs de coupe où une prolongation est possible. ESPN, LiveScore et Flashscore
  écartent ou ramènent à 90 minutes ces matchs ; les flux de bookmakers (betmgm, pmu, unibet-uk…) ne le
  garantissent pas. Aucune anomalie mesurée (cotes ≤ 5 : +6,26 % sans mi-temps, +1,80 % avec), mais **non vérifié**.
- **Tennis** : 10 abandons, tous remboursés (règle lue chez Winamax, Unibet, NetBet, PMU ; problème 7 pour les
  autres). 18 matchs sur 139 annulés ou jamais joués, sans pari gagné ou perdu sur ces matchs.
- **« Avance ou gagne »** : 0 pari. Le code laissait « à régler » des paris déjà perdus (2-2 avec 1-1 à la
  mi-temps : jamais plus d'un but d'avance). Corrigé et vérifié contre toutes les suites de buts possibles.

*Ce qui rendrait la conclusion fausse* : des scores faux à la source, identiques chez deux sources. Le seul test
possible ici (recoupement entre bookmakers) en trouve 1 sur 2 365 matchs ; un contrôle externe reste à faire.

## Ce qui a été corrigé

- `cotes/reglement.py:262` : au hockey, un score final nul ne règle plus aucun pari « prolongation incluse » ;
  le pari reste « à régler ». Les paris sur le temps réglementaire ne changent pas.
- `cotes/reglement.py:283-287` : « avance ou gagne » perdu dès que l'avance demandée était impossible.
- `tests/test_audit_bilans.py` (9 tests, cas réels) ; `tests/test_avance_ou_gagne.py` mis à jour.
- `scripts/audit_bilans.py` : refait tous les chiffres de ce rapport.

Aucune correction n'a été écrite sur `donnees` : aucun vrai résultat n'a pu être confirmé par une source extérieure.

## À faire à la main

| Pari | À chercher | Si confirmé, dans `resultats_manuels.json` |
|---|---|---|
| `016561fae52bf691`, `54684aa01562052b` | Colorado Eagles – Abbotsford Canucks, AHL, 10/10 01:05 UTC : vainqueur après prolongation | `"gagne"` si Abbotsford, sinon `"perdu"` |
| `b603d0cd9c7293e8` | Grizzlys Wolfsburg – Krefeld Pinguine, DEL, 15/10 : vainqueur après prolongation | `"gagne"` si Krefeld, sinon `"perdu"` |
| `aa8ef1ac0718c6a3` ou `4cbbc836d7e78f49` | Dungannon – Carrick Rangers, 10/10 : 1-3 ou 2-4 | 1-3 : `"aa8ef1ac0718c6a3": "gagne"` ; 2-4 : `"4cbbc836d7e78f49": "perdu"` |

## Décisions proposées

1. Afficher à côté du ROI celui des paris pris depuis le plafond (11/11), seul chiffre non choisi après coup.
2. Calculer l'intervalle de confiance par match (ajouter gain et mise par match à `evenements_detail`).
3. Lire les règles d'abandon de Betclic et d'OlyBet, et celle de la 1re mi-temps au basket chez Betclic.
4. Sortir le « 20UP Paiement anticipé » de PMU de la comparaison, ou le ranger en « avance ou gagne ».
