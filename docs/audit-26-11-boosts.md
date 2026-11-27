# Audit des boosts — 26/11/2026

**Verdict** : ne jouer aucun boost « à l'aveugle ». Sur 9 boosts évalués contre la cote juste du 16 au 26/11, la value
moyenne est de −7,2 % (2 positifs). Les 58 boosts réglés ont gagné comme leur cote le prévoit (18 gagnés pour 19,0
attendus), pas mieux : le boost compense à peu près la marge, sans plus. Jouer seulement les boosts dont la value
contre la cote juste est positive ; ignorer tout boost sans cote juste (combinés, paris de saison).

Données : branche `donnees` au 26/11 23:05 UTC — `boosts.json` (262 épisodes lus du 16/11 06:35 au 26/11 17:21) et
`boosts_resultats.json` (58 boosts réglés, matchs du 16 au 25/11, tous avant la remise à zéro du 26/11).

## Corrections (tests : `tests/test_audit_26_11_boosts.py`, 24 sur 30 échouent sur l'ancien code)

| Problème constaté | Cas réels | Correction |
|---|---|---|
| Paris de saison non reconnus : « Jouer » par la marge seuil, puis « à régler » dès la fin de l'offre | Unibet : Marseille podium de Ligue 1 (6,00 contre 4,50), France gagne la Ligue des Nations (6,00), France gagne le Tournoi (2,85), Spurs champions NBA (5,00) | `boosts_sites.long_terme` (« 2026/2027 », « champions NBA », « podium de Ligue 1 », « remporte la Ligue des Nations / le Tournoi ») ; verdict « passer » ; jamais à régler (7 à régler au 26/11 → 5) |
| Une date prise pour une saison | « Ligue 2 - 20/11 », « (23/11) » : 10 multis du jour Unibet notés « pari à long terme » | années consécutives ≥ 20 seulement ; « meilleur marqueur du match » n'est plus un pari de saison |
| Mauvaise traduction | NetBet « Marseille/Le Mans - Gouiri ou Harit premier buteur ? » traduit en buteur d'un joueur nommé « Marseille/Le Mans - Gouiri Ou Harit Premier » | « premier buteur » et « X ou Y » écartés |
| Boost republié sous un autre identifiant : réglé autant de fois | NetBet Troyes/Le Havre (3 identifiants, 20/11), Unibet « Lyon gagne 1:0, 2:0 ou 3:0 » (2, 26/11) ; aucun « jouer » encore | un seul à régler par (bookmaker, intitulé, début) ; aucun s'il est déjà réglé |

## 1. Traduction

Part des boosts reliés à un match traduits en pari standard (198 épisodes reliés sur 262 ; les 64 autres sont des
multis de plusieurs matchs ou des paris de saison) :

| Bookmaker | Reliés | Traduits avant | Après |
|---|---|---|---|
| Winamax | 130 | 23 (18 %) | 30 (23 %) |
| Unibet | 50 | 0 | 0 |
| OlyBet | 10 | 1 | 3 |
| NetBet | 8 | 3 | 5 |
| **Total** | **198** | **27 (14 %)** | **38 (19 %)** |

Par sport (avant) : football 11/84, tennis 8/33, basket 5/43, hockey 2/19, rugby 0/7, football américain 0/8.
Non traduits : 121 sur 171 sont des combinés (2 sélections ou plus), surtout « X gagne et … » et « A et B marquent
chacun … » ; restent écartés. Ajouts sûrs : premier set (tennis), total de sets « lors du match », les deux équipes
marquent / total d'une équipe en 1re mi-temps, « gagne par au moins N buts » et « gagne de N buts ou plus » (OlyBet),
« Troyes/Le Havre - … » (NetBet), « (hors prol. et TAB) » = temps réglementaire. Toujours écartés (ambigus ou sans
référence) : buteur en 1re mi-temps, « gagne les deux mi-temps », « sans encaisser », scores de sets, « remboursé si
non titulaire ».

## 2. Value et calibration

Value à la première lecture (9 boosts, 16–25/11) : −17,4 %, −13,9 %, −10,8 %, −8,0 %, −7,5 %, −6,1 % (Winamax,
handicaps et totaux d'équipe), −5,8 % (OlyBet Lens ne perd pas), +0,5 % (NetBet, même pari à 3,60), +3,9 % (Winamax
Brunson 30 points). Aucun groupe (bookmaker, sport, marché, cote, hausse) n'a assez de boosts évalués pour conclure.

Boosts réglés (58, mise = mise max) — attendus = Σ 1/cote, intervalle à 95 % :

| Groupe | Réglés | Gagnés | Attendus | ROI |
|---|---|---|---|---|
| Tous | 58 | 18 | 19,0 ± 6,9 | −1,3 % (−16,25 € sur 1 255 €) |
| Winamax | 36 | 11 | 10,9 ± 5,3 | +6,9 % |
| Unibet | 21 | 7 | 7,8 ± 4,3 | −10,7 % |
| Combiné multi-matchs | 21 | 6 | 6,7 ± 4,1 | −10,2 % |
| Joueur | 19 | 7 | 7,0 ± 4,1 | +5,6 % |
| Simple | 12 | 3 | 3,4 ± 3,0 | −3,4 % |

Aucun écart n'atteint 1,5 σ : les boosts sont calibrés sur leur cote boostée. Historique cotes-boostees (constantes du
code, 979 boosts) : 305 gagnés pour 322 attendus, ROI −6,6 %. 24 des 58 réglés n'ont pas de score saisi (non
vérifiables) ; les 34 autres sont cohérents avec le score dans l'ordre domicile-extérieur de l'enregistrement.

## 3. Règlement

0 identifiant réglé deux fois, 0 boost « passer » réglé, 65 « jouer » commencés = 58 réglés + 7 à régler (dont 2 paris
de saison, retirés). Mises et gains conformes (mise max ; gagné = mise × (cote − 1)).

## 4. Boosts couverts et surebets

Aucun boost couvert du 16 au 26/11 (`episodes_couverts` vide). Cas réel du 24/11 : NetBet « Lens ne perd pas » 3,60 ;
meilleure victoire de Leipzig avant 08:31 = 1,30 (Betclic, OlyBet, PMU) : 1/3,60 + 1/1,30 = 1,047 > 1, rejet correct.
Mises : boost toujours à sa mise max (OlyBet : 25 € de gain net / (cote − 1)), couvertures arrondies aux 10 c au mieux
pour le pire résultat, cotes de couverture de moins de 10 min (mêmes garde-fous que les surebets) : rien à corriger.

## 5. Onglet (Bilan › Boosts, `web/boosts.js`)

« À jouer » en tête (value décroissante, puis jugés sans cote juste), avec mise conseillée (mise max) et gain attendu
(mise × value, comme le gain espéré du bilan), total en tête ; « À passer (N) » replié avec le motif. Aucun calcul
Python modifié. Les classes `bo-resume` et `bo-conseil` n'ont pas de style propre (à voir avec `interface.css`).

## 6. À faire (non fait)

- Jouer systématiquement : les boosts « Jouer » avec value ≥ 3 % (seuil d'alerte) ; aucun groupe n'est prouvé
  rentable (9 évalués, 58 réglés).
- Ignorer : combinés multi-matchs (−10,2 % sur 21, 68 gagnés pour 73,9 attendus dans l'historique), paris de saison, et tout
  « Jouer » sans cote juste tant que la règle de marge (6 % + 5 points) n'est pas mesurée sur les réglés.
- Enregistrer le marché et l'issue dans `boosts_resultats.json` (aujourd'hui seulement l'intitulé) pour régler les
  boosts traduits automatiquement avec `cotes/reglement.py`, et exiger le score à la saisie.
- L'onglet « Boosts et surebets » n'affiche pas les cotes boostées : un conteneur dans `web/modele.html` permettrait
  d'y reprendre le bloc « À jouer ».
