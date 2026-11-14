# Revue de bugs : association des matchs, traduction des marchés, lecteurs directs

Faite le 14/11/2026 sur la branche `donnees` (commit `a71c003`) : 554 787 opportunités archivées du 05/10 au
14/11, 9 185 associations de matchs, 6 368 paris. Fichiers revus : `cotes/correspondance.py`, `cotes/pulsescore.py`,
`cotes/marches.py`, `cotes/comparaison.py`, `cotes/direct/`.

## Verdict

1. **11 bugs corrigés, chacun avec un test** (`tests/test_revue_bugs.py`, 12 tests qui échouent tous sur l'ancien code).
2. **156 paris ont été pris sur un match ou une période faux**, pour −42,5 € au total. Les deux plus gros : 74 paris
   « FC Tokyo – Kashiwa » comparés à un autre match, 41 paris sur un derby de Cali lu à l'envers.
3. **Aucune ligne inversée (plus/moins, signe du handicap) trouvée dans les lecteurs directs.**
4. **Cotes périmées : une mesure, pas de correction.** Un prix Pinnacle de 5 à 15 minutes donne une CLV de −1,9 %
   (320 paris) contre +2,1 % en dessous. Le seuil est un choix de stratégie : à décider.
5. **Écarts « minimum » : rien ne les distinguait dans les paris.** Corrigé ; 4 paris concernés à ce jour.

## Méthode

- Toutes les associations archivées ont été relues avec leurs noms réels, puis rejouées avec le code corrigé.
- Les intitulés ont été groupés par bookmaker, sport, marché et période : un groupe dont les écarts sont
  aberrants face à Pinnacle trahit une mauvaise traduction.
- La CLV des paris a été découpée par bookmaker, marché, âge des cotes et limite Pinnacle.
- Chaque soupçon a été confirmé en exécutant le code actuel sur l'exemple.

## Bugs corrigés

| # | Bug | Exemple réel | Effet | Correction |
|---|---|---|---|---|
| 1 | Domicile et extérieur inversés quand les deux équipes partagent un nom de ville sans être un « derby » reconnu | Polymarket « América de Cali – AD Cali », 08/11 : PMU, Betclic, Winamax et OlyBet « America de Cali – Deportivo Cali » associés à l'envers (0,63 / 0,62 croisé contre 1,0 / 0,57 direct) | 41 paris, −178,4 € | `correspondance._ordre` : un nom identique fixe l'ordre, toujours |
| 2 | Deux noms seulement approchants (0,6 à 0,75) acceptés à la même heure | Winamax et PMU « Derby County – Stoke City » = Betfair « Newport County – York City », 17/10. Aussi « Odense – Silkeborg » = Smarkets « Viborg – Horsens » (01/11), « Pärnu JK Vaprus – Nõmme Kalju » = « Harju JK Laagri – Nomme United » (13/10) | 22 paris, −142,8 € | `associer` : un des deux noms doit atteindre 0,75 |
| 3 | Un même match de référence donné à deux matchs d'un bookmaker | Betclic, 13/10 : « Pärnu JK Vaprus – Nõmme Kalju » (0,6) et « Harju JK Laagri – FC Nõmme United » (1,0) sur le match Pinnacle 1637810025. Six bookmakers, 21/10 : « FC Tokyo – Kashiwa Reysol » sur Smarkets « Yokohama F. Marinos – Tokyo Verdy » | 75 paris, +285,7 € | `correspondance._exclusifs` : le mieux noté garde la référence |
| 4 | L'association ne voyait que les matchs de référence ayant une cote fiable ; le vrai match absent, un sosie le remplaçait | Liiga, 30/10 : « Tappara – Ilves » de six bookmakers associé à l'envers au match Pinnacle 1639061776 « Ilves – Tappara » (0,85, autre catégorie), alors que Betclic a aussi été associé au bon match 1639048394. Même jour : « TPS – Pelicans » | 5 paris, −17,5 € | `comparaison.indexer` : association sur tous les matchs, comparaison sur les cotes fiables |
| 5 | Tennis : simple associé à un double | OlyBet, 04/11 : « W. Falkowska – M. Rajeshwaran Revathi » = Pinnacle « Kucmova / Laboutkova – Bhamidipaty / Rajeshwaran Revathi ». Winamax, 04/11 : « Montgomery – Vandromme » | 0 pari | `associer` : simple et double jamais rapprochés |
| 6 | Sport individuel : un seul joueur reconnu suffisait | OlyBet, 21/10 : « Onclin – Struff » = Polymarket « Blockx – Struff » | 0 pari | `associer` : règle « une équipe identique » réservée aux sports d'équipe |
| 7 | « B » et « II » pris pour deux catégories contradictoires | Betclic « Real Sociedad B – Almeria » et Pinnacle « Real Sociedad II – Almeria », 17/10 : ressemblance 0. Aussi Porto B, Benfica B, Sporting B, Celta B | Matchs non comparés, aucun faux pari | `correspondance._normaliser` : même marqueur |
| 8 | Baseball : « 5 premières manches » en français lu comme le match entier | PMU « Handicap - 5 1eres manches », Samsung Lions – KT Wiz, 07/11 : +1,5 à 2,45 comparé au handicap du match (pari `a6f086dc8b1ee13f`). Aussi « Total de Runs - 7 1ers Tours de Batte » | 27 sélections, 12 paris, +20,5 € | `pulsescore.MANCHES` : 5 manches reconnues, 3 et 7 non comparées |
| 9 | PMU : « Dernière équipe à marquer » et « To score Goal 2 » pris pour le vainqueur | Füchse Berlin – Partizan, 29/10 : « To score Goal 2 » à 1,66 pour une cote juste de 1,02 (+63 %). Irlande – Argentine, 05/11 | 35 sélections, 0 pari (bloqué par le contrôle des intitulés) | `direct/pmu._PAS_RESULTAT` |
| 10 | Winamax, hockey : handicap ±0,5 classé « temps réglementaire » alors qu'il compte la prolongation | Björklöven – Örebro, 12/11 : handicap ±0,5 à 1,90 / 1,60, comme le vainqueur à 2 issues ; 1N2 des 60 minutes à 2,50 / 3,65 / 2,05. Faux écart de +8,7 % | 5 sélections, 0 pari | `pulsescore.HANDICAP_DEMI_PROLONGATION` |
| 11 | Écart « minimum » perdu à la prise du pari | Pelicans – Nets, 11/11, paris `b2005ed099a8dd6b` et `0c816a6ecca9e08c` : pris au prix d'achat de Polymarket (écart 2,1 %), CLV de +9,4 % calculée sur une autre base | 4 paris | Voir « Écarts minimum » |

Les paris cités restent dans les bilans : leur règlement est juste, seul leur écart annoncé était faux.

## Mesure sur l'archive

5 695 couples de noms distincts rejoués avec le code corrigé :

- 12 associations fausses refusées (lignes 2, 5 et 6 du tableau) ;
- 7 associations retrouvées (équipes B) ;
- 3 ordres corrigés (derby de Cali) ;
- **7 associations justes perdues** par la règle 2, soit 0,1 % : Deportivo Pasto – Junior (2), Osaka Marvelous –
  Aranmare, AO Amintas – Olympiakos, Kladno – Pardubice, Storhamar – Podravka, Atletico PR – Atletico MG.
  Ces matchs ne sont plus comparés à cette référence. C'est le prix de la règle.

Les règles 3 et 4 dépendent des autres matchs du cycle : elles ne se rejouent pas couple par couple. Elles sont
vérifiées par les tests.

## Ce qui reste possible

- **Sosie quand personne ne liste le vrai match.** Betclic « Burgos – Valence » (ACB, 08/11) associé à l'envers à
  Pinnacle « Caja 87 Baloncesto – Tizona Burgos » : 1 pari (`76a420f21c13cc23`, −10 €). Par les noms seuls, ce cas
  ne se distingue pas de « Lyon – Nice » = « Olympique Lyonnais – OGC Nice », qui est juste. Les règles 3 et 4 ne
  le rattrapent que si le bookmaker ou la référence liste aussi le vrai match.
- **Ligne 4 : mécanisme lu dans le code, non rejoué.** L'archive des références du 30/10 n'est plus sur la branche.
- **Smarkets, Betfair, Matchbook** : un marché sans carnet n'a aucune ligne, donc son match reste invisible à
  l'association. La règle 4 ne couvre que les lignes existantes (Pinnacle, Polymarket).

## Périodes et prolongation

- Bugs 8, 9 et 10 ci-dessus.
- Betclic, hockey, « Écart entre les équipes (tps rég.) » ±0,5 : 20 paris, dont 5 sur un match nul après
  60 minutes, tous les 5 réglés sur ce score (Langnau – Davos 2-2 puis 2-3, handicap −0,5 perdu).
- Aucun autre groupe aberrant depuis le 22/10 (début des lecteurs directs).

## Lignes inversées

- **Handicap et plus/moins** : aucun groupe d'intitulés d'un lecteur direct n'a d'écarts aberrants face à Pinnacle.
- **`marches.inverser`** : relu, juste (issues, score exact, mi-temps/fin, totaux par équipe, signe du handicap).
- **Domicile/extérieur** : bugs 1 et 4.

Limite : un marché à plusieurs lignes dans une même liste de sélections garderait une cote d'une ligne avec le
handicap d'une autre (`pulsescore._marche`). Aucun exemple réel trouvé ; non modifié.

## Cotes périmées

Les lecteurs datent chaque cote à l'heure de début de leur lecture, jamais après : pas de cote ancienne présentée
comme fraîche. Le défaut est du côté de la référence.

Paris pris contre Pinnacle depuis le 20/10 (2 221), selon l'âge réel du prix Pinnacle (écart de lecture + âge du
cache) :

| Âge du prix Pinnacle | Paris | CLV moyenne |
|---|---|---|
| moins de 2 min | 1 607 | +2,0 % |
| 2 à 5 min | 288 | +2,7 % |
| 5 à 10 min | 184 | −1,9 % |
| 10 à 15 min | 136 | −1,9 % |

- **OlyBet est le révélateur** : ses cotes suivent le marché asiatique en quelques minutes. Avec un prix Pinnacle
  de 5 minutes ou plus : 52 paris, CLV −8,7 %. CLV médiane d'OlyBet toutes cotes : −4,0 %, seul bookmaker négatif.
- Exemple : Tourcoing – Reims, 13/11, pari `18a213b63c9b4167`. Pinnacle ouvre Reims −3 à 1,846 (limite 50 €) à
  21:19 et passe à 2,197 à 21:28. OlyBet monte de 1,67 à 1,89 à 21:24. La comparaison de 21:24 lit le prix de
  21:19 : +2,4 % annoncés, CLV −35 %.

**À décider** : ramener la fenêtre de 15 à 5 minutes (`controle.FENETRE_MIN`, `simulation.FRAICHEUR_PRISE_MIN`)
retirerait 14 % des paris pris contre Pinnacle. Non modifié : c'est un seuil de stratégie.

## Écarts minimum

Deux cas : Polymarket lu au prix d'achat (`prix_prudent`) et Betclic « avance ou gagne » comparé à la simple
victoire. L'opportunité portait la mention, le pari la perdait. Conséquences dans les bilans :

- l'écart d'une borne était moyenné avec les écarts exacts (`simulation.moyennes_ecarts`) ;
- les « gagnés contre attendus » prenaient la borne pour la probabilité (`simulation.segments`) ;
- la CLV comparait une prise au prix d'achat à une clôture lue tantôt au milieu, tantôt au prix d'achat.

Corrections :

- `simulation.placer` : le pari garde `ecart_minimum`, `prix_prudent` et `proba_milieu` ;
- `simulation.suivre_cloture` : `clv_minimum` quand la clôture est elle-même une borne ;
- `simulation.proba_attendue` : milieu du carnet pour un pari au prix d'achat ; un segment contenant un « avance ou
  gagne » est marqué `probabilites_minorees` ;
- `simulation.moyennes_ecarts` : les bornes sont comptées à part (`minimums`).

Les 4 paris déjà pris n'ont pas ces champs. Le site n'affiche pas encore « minimum » à côté de l'écart.

## Limites de la revue

- Les 6 000 lignes de `cotes/direct/` n'ont pas été relues une à une : la revue part des anomalies de l'archive.
  Un bug qui ne produit aucune opportunité ne se voit pas ainsi.
- Les noms des matchs de référence ne sont connus que pour les matchs ayant eu une opportunité.
- Les sources US (`draftkings.py`, `fanduel.py`) et les paris joueurs n'ont pas été revus.
