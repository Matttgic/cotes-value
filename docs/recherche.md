# Recherche : prédire la clôture Pinnacle, autres références

Fait le 14/11/2026 sur la branche `donnees` (commit `9951a30`, 23:06 UTC) et sur 7 saisons de football-data.co.uk.
Tous les chiffres de la partie 1 sortent de `python scripts/recherche_cloture.py --donnees <dossier> --football <dossier>`
(lecture seule, 40 secondes, graine fixe). Suite de [avantage-reel.md](avantage-reel.md) et de
[duree-values.md](duree-values.md). Rien n'est changé dans la détection.

« Mouvement » : variation de la proba juste Pinnacle entre un relevé et la clôture. « R² hors échantillon » : part du
mouvement expliquée sur des données que le modèle n'a pas vues, contre « la cote ne bouge pas » (0 % = n'apporte
rien, négatif = pire). Intervalles à 95 % par bootstrap des matchs entiers.

## Conclusion

1. **Le sens se prédit, contre nous.** Après la détection d'une value, la proba juste Pinnacle baisse pour 65 % des
   paris testés (novembre) ; sur l'ensemble, −2,8 % en moyenne pour un écart moyen de 4,4 %. Une seule constante apprise sur
   octobre bat « la cote ne bouge pas » en novembre : R² +9,1 % [+2,7 ; +15,2].
2. **L'ampleur, pari par pari, ne se prédit pas avec ce qu'on sait de Pinnacle.** L'écart, le délai et la cote
   n'ajoutent rien à la constante (R² −0,5 % à −0,1 %). L'élan de Pinnacle (mouvement de la dernière heure) ne prédit
   rien à 12, 6, 3 et 1 h du match (R² de −0,7 % à +0,4 %, bon sens 48 à 56 %).
3. **Ce qui prédit la clôture, c'est le prix d'un autre marché.** Le prix Polymarket du même pari : R² +16,4 %
   [+3,9 ; +26,9] de plus que la constante (191 paris testés). Polymarket d'accord : CLV +4,4 % ; pas d'accord :
   −1,6 %. Sur football-data, l'écart à Betfair Exchange explique 3,4 % [+2,3 ; +4,5] du mouvement en 1N2, la moyenne
   du marché 1,2 %.
4. **Attendre coûte.** Le même pari pris plus tard chez le même bookmaker, contre la même clôture : −1,7 point de
   CLV après 15 min, −3,6 après 1 h, −6,1 au coup d'envoi. La cote est plus haute après l'attente dans 1 à 11 % des
   cas, plus basse dans 20 à 65 %.
5. **Parier loin du match ne paie pas.** Values détectées plus de 12 h avant : CLV +0,1 % [−0,8 ; +1,1]. À 3 h au
   plus : +2,5 % [+1,7 ; +3,3], dans les deux périodes.
6. **Sources** : une seule nouvelle source gratuite et sans compte tient à la vérification, l'historique de prix de
   Polymarket. SX Bet, tennis-data et Betdaq sont écartées ; Betfair Exchange reste la référence qui vaudrait le plus
   et reste bloquée.

Donc : parier dès l'alerte, jamais plus tard ; compter sur une CLV d'environ l'écart moins 3 points ; se servir d'un
second marché pour trier, pas de l'historique de Pinnacle.

## 1. Peut-on prédire la clôture Pinnacle ?

### Football-data.co.uk : du relevé d'avant-match à la clôture

48 400 matchs de 22 championnats, saisons 2019-20 à 2025-26. Relevé d'avant-match : le vendredi après-midi pour le
week-end, le mardi après-midi pour la semaine (notice du site). Appris jusqu'à 2023-24, testé sur 2024-25 et
2025-26. Variables : écart entre la proba juste d'une autre source et celle de Pinnacle, au relevé.

| 1N2 | Appris | Testés | R² hors échantillon | Bon sens | Bon sens, 10 % les plus forts | Coefficient |
|---|---|---|---|---|---|---|
| Écart à la moyenne du marché | 75 594 | 21 190 | +1,2 % [+0,9 ; +1,5] | 53 % | 59 % | +0,31 |
| Écart à bet365 | 75 474 | 21 188 | +1,1 % [+0,9 ; +1,3] | 53 % | 59 % | +0,13 |
| Moyenne, bet365, meilleur prix, niveau, marge | 75 474 | 21 186 | +1,5 % [+1,1 ; +2,0] | 54 % | 60 % | — |
| Écart à Betfair Exchange (appris 2024-25, testé 2025-26) | 14 212 | 5 582 | +3,4 % [+2,3 ; +4,5] | 55 % | 70 % | +0,23 |
| Écart à la moyenne (mêmes saisons) | 14 212 | 5 582 | +2,1 % [+1,1 ; +3,2] | 54 % | 60 % | +0,33 |
| Betfair Exchange et moyenne (mêmes saisons) | 14 212 | 5 582 | +3,8 % [+2,4 ; +5,1] | 56 % | 67 % | +0,20 ; +0,22 |

Lecture du coefficient : Pinnacle fait jusqu'à la clôture 31 % du chemin vers la moyenne du marché, 23 % vers
Betfair Exchange. Total 2,5 buts : presque rien (bet365 +0,5 % [+0,2 ; +0,8], cinq variables −0,5 %).

1N2, saisons de test, par cinquième de la prévision (modèle à cinq variables) :

| Cinquième | Proba Pinnacle : variation prévue | Variation réelle | Cote bet365 : clôture / relevé |
|---|---|---|---|
| 1 | −2,16 % | −1,82 % [−2,21 ; −1,43] | −0,04 % [−0,40 ; +0,36] |
| 2 | −0,74 % | −0,67 % [−0,93 ; −0,39] | +0,45 % [+0,17 ; +0,74] |
| 3 | −0,36 % | −0,60 % [−0,84 ; −0,35] | +1,00 % [+0,75 ; +1,24] |
| 4 | −0,06 % | −0,27 % [−0,52 ; −0,01] | +1,22 % [+0,97 ; +1,46] |
| 5 | +0,54 % | +0,43 % [+0,14 ; +0,69] | +1,94 % [+1,65 ; +2,23] |

- En moyenne par groupe, la prévision est juste. Pari par pari, elle explique 1,5 % du mouvement : le reste est du
  bruit.
- **Le premier cinquième regroupe les issues que le marché cote plus haut que Pinnacle** : c'est là que naissent
  les values. La proba Pinnacle y baisse de 1,8 %, et attendre n'y apporte rien (cote bet365 inchangée). Ailleurs,
  attendre donne une cote bet365 plus haute de 0,5 à 1,9 %, sur des issues que le marché cote plus bas.

« Values » des saisons de test, 1N2 (meilleur prix du marché contre la cote juste Pinnacle) :

| Écart au relevé | Issues | Écart moyen | CLV, pari pris au relevé | CLV, même issue prise à la clôture |
|---|---|---|---|---|
| 2 à 5 % | 667 | +2,98 % | +0,85 % [+0,06 ; +1,65] | −0,70 % [−1,05 ; −0,37] |
| 5 % et plus | 225 | +9,71 % | +3,44 % [+1,13 ; +5,70] | −1,40 % [−2,59 ; −0,18] |

Un tiers de l'écart reste à la clôture. Le modèle prévoit une baisse de la proba Pinnacle pour 98 à 100 % de ces
values.

### Paris du projet : de la détection à la clôture

Paris uniques de référence Pinnacle, cote ≤ 5, clôture mesurée : 1 701 appris (05/10 au 31/10), 793 testés (01/11
au 14/11). Testés : écart moyen +4,39 %, CLV +1,51 % [+0,35 ; +2,66].

| Variables | R² hors échantillon | Contre la constante | Bon sens |
|---|---|---|---|
| Constante apprise (même baisse pour tous : −3,8 % en logarithme) | +9,1 % [+2,7 ; +15,2] | — | — |
| Écart | +8,7 % [+1,9 ; +15,4] | −0,5 % [−1,6 ; +0,6] | 65 % |
| Écart, délai | +9,0 % [+1,1 ; +16,4] | −0,1 % [−2,8 ; +2,6] | 65 % |
| Écart, délai, cote | +8,7 % [+0,4 ; +16,3] | −0,5 % [−3,3 ; +2,4] | 66 % |
| Prix Polymarket du même pari (166 appris, 191 testés) | +24,6 % [+12,7 ; +36,5] | +16,4 % [+3,9 ; +26,9] | 67 % |

Le prix Polymarket : Pinnacle fait 59 % du chemin vers lui ; pour les 10 % de prévisions les plus fortes, le sens
est bon 85 % du temps.

| Second avis Polymarket | Paris | Écart moyen | CLV Pinnacle, IC 95 % | Octobre (n) | Novembre (n) |
|---|---|---|---|---|---|
| D'accord : écart Polymarket ≥ 2 % | 122 | +4,58 % | +4,40 % [+2,18 ; +6,81] | +2,89 % (48) | +5,38 % (74) |
| Écart Polymarket de 0 à 2 % | 92 | +2,98 % | +0,31 % [−1,38 ; +1,93] | +1,13 % (48) | −0,59 % (44) |
| Pas d'accord : écart Polymarket < 0 | 143 | +3,47 % | −1,55 % [−3,41 ; +0,22] | −0,31 % (70) | −2,73 % (73) |
| Pas de prix Polymarket | 2 137 | +4,53 % | +1,21 % [+0,59 ; +1,87] | +1,02 % (1 535) | +1,70 % (602) |

| Écart à la détection | Paris | Écart moyen | CLV Pinnacle, IC 95 % | Octobre (n) | Novembre (n) |
|---|---|---|---|---|---|
| 2 à 3 % | 1 026 | +2,43 % | −0,48 % [−1,09 ; +0,09] | −0,85 % (694) | +0,28 % (332) |
| 3 à 5 % | 813 | +3,83 % | +0,77 % [−0,12 ; +1,67] | +1,05 % (567) | +0,12 % (246) |
| 5 à 8 % | 407 | +6,26 % | +2,06 % [+0,89 ; +3,25] | +2,30 % (267) | +1,60 % (140) |
| 8 % et plus | 248 | +11,56 % | +7,95 % [+5,91 ; +10,04] | +6,49 % (173) | +11,31 % (75) |

| Délai avant le match | Paris | Écart moyen | CLV Pinnacle, IC 95 % | Octobre (n) | Novembre (n) |
|---|---|---|---|---|---|
| 3 h au plus | 737 | +4,48 % | +2,45 % [+1,67 ; +3,26] | +2,19 % (501) | +3,01 % (236) |
| 3 à 12 h | 749 | +4,31 % | +1,39 % [+0,21 ; +2,62] | +1,75 % (501) | +0,67 % (248) |
| Plus de 12 h | 1 008 | +4,45 % | +0,08 % [−0,82 ; +1,06] | −0,34 % (699) | +1,04 % (309) |

Sous 5 % d'écart, la CLV n'est pas distinguable de zéro. À écart égal, une value trouvée près du match garde plus
de la moitié de son écart ; trouvée plus de 12 h avant, elle n'en garde rien.

### Attendre

Paris uniques de référence Pinnacle détectés depuis le 30/10, cote ≤ 5, hors score exact : 982, dont 630 retrouvés
dans l'historique des cotes (440 matchs ; PMU et Betclic surtout). Même pari, même bookmaker, même clôture
Pinnacle ; seule l'heure de prise change.

| Attente | Paris | CLV, pris à la détection | CLV, pris après l'attente | Différence | Cote plus haute | Cote plus basse |
|---|---|---|---|---|---|---|
| 15 min | 584 | +0,90 % [−0,24 ; +2,07] | −0,84 % [−1,91 ; +0,23] | −1,74 % [−2,58 ; −1,05] | 1 % | 20 % |
| 1 h | 523 | +0,81 % [−0,49 ; +2,12] | −2,79 % [−3,93 ; −1,72] | −3,60 % [−4,56 ; −2,73] | 2 % | 43 % |
| 3 h | 450 | +0,19 % [−1,21 ; +1,59] | −4,67 % [−5,81 ; −3,56] | −4,85 % [−5,96 ; −3,86] | 4 % | 61 % |
| Jusqu'au match | 628 | +1,16 % [+0,09 ; +2,26] | −4,94 % [−5,67 ; −4,21] | −6,10 % [−7,24 ; −5,03] | 11 % | 65 % |

| Différence de CLV après l'attente | 15 min | 1 h | 3 h | Jusqu'au match |
|---|---|---|---|---|
| PMU | −0,50 % [−0,86 ; −0,19] | −2,42 % [−3,19 ; −1,74] | −3,46 % [−4,24 ; −2,72] | −5,03 % [−6,16 ; −3,98] |
| Betclic | −3,64 % [−5,78 ; −1,85] | −5,06 % [−7,31 ; −2,98] | −8,10 % [−11,02 ; −5,13] | −7,37 % [−9,79 ; −5,04] |
| Écart de 2 à 3 % | −1,03 % [−1,45 ; −0,65] | −2,54 % [−3,24 ; −1,92] | −3,36 % [−4,18 ; −2,60] | −4,88 % [−5,91 ; −3,89] |
| Écart de 5 % et plus | −2,91 % [−4,99 ; −1,13] | −6,15 % [−8,48 ; −4,05] | −8,64 % [−11,40 ; −6,10] | −9,42 % [−12,08 ; −6,96] |

Aucun sous-groupe ne gagne à attendre. Betclic coûte sept fois plus que PMU au premier quart d'heure.

### Historique des références : élan de Pinnacle, écart aux autres

Séries Pinnacle du 12 au 14/11 (3 203 matchs). Appris sur les matchs d'avant le 14/11, testé sur ceux du 14/11.

| Variable, heures avant le match | Vainqueur et 1N2, tous sports | Totaux et handicaps, football |
|---|---|---|
| Élan de la dernière heure, 12 h | −0,6 % [−1,2 ; −0,2] | −0,3 % [−2,5 ; +1,8] |
| Élan de la dernière heure, 6 h | +0,2 % [−0,7 ; +1,1] | −0,6 % [−2,3 ; +1,2] |
| Élan de la dernière heure, 3 h | −0,1 % [−0,3 ; +0,1] | +0,4 % [−1,4 ; +2,1] |
| Élan de la dernière heure, 1 h | −0,7 % [−1,4 ; −0,1] | −0,4 % [−2,2 ; +1,2] |
| Niveau de la proba, 12 h à 1 h | −0,8 % à +0,1 % | −0,0 % à +1,0 %, zéro compris |

Testés : 1 457 à 2 336 cotes (1 082 à 1 633 matchs) pour vainqueur et 1N2, 4 226 à 10 127 cotes (380 à 871 matchs)
pour totaux et handicaps.

| Écart à une autre référence (1 à 12 h avant) | Appris | Testés | R² hors échantillon | Coefficient |
|---|---|---|---|---|
| Polymarket | 1 005 (118 matchs) | 935 (107 matchs) | −2,5 % [−11,7 ; +4,2] | +0,41 |
| Matchbook | 1 458 (52 matchs) | 1 301 (41 matchs) | +6,1 % [+1,5 ; +9,4] | +0,55 |
| Smarkets | 1 277 (108 matchs) | 981 (78 matchs) | −0,0 % [−2,6 ; +2,4] | +0,21 |

Sur toutes les cotes Pinnacle (et non sur nos seuls paris), Polymarket ne prédit pas le mouvement ; Matchbook oui,
sur 41 matchs et un seul jour. Le second avis Polymarket vaut donc pour trier nos values (là où Pinnacle peut être
en retard), pas pour deviner où ira Pinnacle en général.

## 2. Autres références et autres marchés

Chaque source a été interrogée le 14/11/2026 depuis le conteneur de cette session (pays de sortie inconnu). Aucune
adresse n'est donnée sans réponse reçue.

| Source | Mesure | Verdict |
|---|---|---|
| **Polymarket, historique de prix** (`clob.polymarket.com`, chemin `/prices-history`) | HTTP 200 sans clé. Un marché : 126 points sur 1 jour (pas de 10 min), 675 points sur 31 jours (pas d'1 h) | **Proposée.** Refait le test du second avis sur 40 jours au lieu de 3 : l'historique des références du projet ne commence que le 12/11 |
| **football-data.co.uk** (`mmz4281/<saison>/<division>.csv`) | HTTP 200, 176 fichiers lus. Clôture Pinnacle jusqu'au 14/01/2026 seulement, absente des fichiers 2026-27 ; Betfair Exchange depuis 2024-25 (2 397 matchs en 2026-27) | **Proposée pour la recherche**, pas pour la détection : aucun prix en direct |
| **Moyenne des bookmakers français** | Déjà dans `cotes/`, rien à lire de plus | **À tester** : sur football-data la moyenne du marché prédit la clôture (R² +1,2 %). Pas testable ici : les rapprochements entre bookmakers n'existent que depuis le 12/11 |
| **Matchbook** | Déjà lu | **À suivre** : R² +6,1 % [+1,5 ; +9,4] sur 41 matchs, un jour |
| **Betfair Exchange** | Non remesuré (hôte non autorisé ici). HTTP 403 depuis GitHub le 10/11 ([sources-us.md](sources-us.md)) | **La plus utile, toujours bloquée** : meilleur prédicteur de la clôture dans football-data (+3,4 %). Voies : serveur direct ou relais, déjà décrites |
| **SX Bet** (`api.sx.bet`) | Sports, ligues et marchés : HTTP 200 sans clé (54 ligues actives, dont 21 de football et 10 de tennis). Prix : HTTP 401 `BAD_AUTH` sur `/orders-v3/odds/best` et `/orderbook-v3/snapshot/market` ; sa documentation demande une clé créée depuis un compte | **Écartée** : pas de cotes sans compte |
| **tennis-data.co.uk** | HTTP 403 (page Cloudflare) sur 4 adresses | **Écartée** d'ici, comme dans [cote-juste.md](cote-juste.md) |
| **Betdaq** | Non interrogée. Son centre d'aide, lu par recherche : compte vérifié et 250 £ de frais d'accès | **Écartée** |
| **Novig, ProphetX** | Documentation officielle non jointe (hôtes non autorisés) | **Non vérifiées, non proposées** |
| **Kalshi** | Déjà une référence | Rien de neuf : ROI −28,4 % ([avantage-reel.md](avantage-reel.md)) |

### Types de pari et sports

CLV contre la clôture Pinnacle des mêmes paris (cote ≤ 5), par marché et par sport. Quatorze groupes regardés, sans
correction : une piste, pas une preuve. Retenus ici : ceux qui tiennent dans les deux périodes.

| Groupe | Paris | Écart moyen | CLV Pinnacle, IC 95 % | Octobre (n) | Novembre (n) |
|---|---|---|---|---|---|
| Handicap | 564 | +4,63 % | +2,15 % [+0,88 ; +3,38] | +2,01 % (408) | +2,51 % (156) |
| Double chance | 93 | +4,29 % | +3,46 % [+1,87 ; +5,17] | +3,73 % (63) | +2,88 % (30) |
| Total de l'équipe à l'extérieur | 168 | +3,42 % | +2,00 % [+0,73 ; +3,33] | +1,76 % (121) | +2,63 % (47) |
| 1N2 | 514 | +5,11 % | +0,27 % [−0,75 ; +1,32] | +0,23 % (387) | +0,39 % (127) |
| Total | 510 | +4,42 % | +0,57 % [−0,49 ; +1,60] | +0,27 % (306) | +1,02 % (204) |
| Vainqueur | 313 | +4,23 % | +0,54 % [−0,54 ; +1,65] | +0,01 % (191) | +1,38 % (122) |
| Hockey | 470 | +5,29 % | +1,94 % [+0,78 ; +3,18] | +1,57 % (305) | +2,63 % (165) |
| Basket | 539 | +4,38 % | +1,74 % [+0,25 ; +3,17] | +1,80 % (357) | +1,63 % (182) |
| Football | 1 063 | +4,05 % | +0,43 % [−0,52 ; +1,47] | +0,22 % (737) | +0,92 % (326) |

Les marchés les plus regardés (1N2, total, vainqueur ; football) gardent 5 à 13 % de leur écart. Handicaps, double
chance, hockey et basket en gardent 37 à 81 %.

## Limites

- **Paris du projet** : échantillon choisi (écart ≥ 2 %, clôture mesurée), 40 jours, 14 jours de test. Second avis
  Polymarket : 357 paris.
- **Historique des références** : 3 jours, un seul jour de test.
- **Football-data** : relevé un à trois jours avant le match, plus tôt que nos paris ; football seulement ; bet365
  n'est pas un bookmaker français ; le « meilleur prix » à la clôture ne couvre pas forcément les mêmes bookmakers
  qu'au relevé.
- **Deux pièges écartés.** Handicap asiatique de football-data et totaux/handicaps de basket chez Pinnacle : ne
  garder que les lignes encore cotées à la clôture, c'est choisir d'après l'avenir. Le « retour vers 50 % » qu'on y
  lit (R² apparent jusqu'à +27 %) est fabriqué par ce tri. Le script ne les compte pas.
- **Attendre** : avant le 12/11, une cote retirée ne laisse pas de trace dans l'historique ; 352 paris sur 982 n'y
  sont pas retrouvés.
- **Modèles linéaires seulement.** Aucun modèle plus riche n'a été essayé.
- **Sources** : vérifiées depuis un seul point de sortie ; un blocage par pays peut différer depuis GitHub ou depuis
  la France.

## Décisions proposées

1. Parier dès l'alerte. Ne pas construire d'aide à l'attente.
2. Afficher une CLV attendue à côté de l'écart (écart moins 3 points environ) ; les écarts de 2 à 3 % ne battent
   pas la clôture (−0,48 % [−1,09 ; +0,09], 1 026 paris).
3. Écarter, ou au moins signaler, un pari que Polymarket contredit (écart Polymarket négatif : CLV −1,55 %).
   À confirmer d'abord avec l'historique de prix de Polymarket.
4. Mettre à l'essai un seuil d'écart plus haut pour les values trouvées plus de 12 h avant le match.
5. Enregistrer à la détection la moyenne sans marge des autres bookmakers français, pour la tester dans un mois.
6. Betfair Exchange : reprendre la voie serveur ou relais de [sources-us.md](sources-us.md).

## Reproduire

```bash
git clone --depth 1 --branch donnees https://github.com/Matttgic/cotes-value donnees
```

```bash
mkdir fd && for s in 1920 2021 2122 2223 2324 2425 2526; do for d in E0 E1 E2 E3 EC SC0 SC1 SC2 SC3 D1 D2 I1 I2 SP1 SP2 F1 F2 N1 B1 P1 T1 G1; do curl -sL -o fd/$s-$d.csv https://www.football-data.co.uk/mmz4281/$s/$d.csv; done; done
```

```bash
python scripts/recherche_cloture.py --donnees donnees --football fd
```

Demande numpy (`requirements-dev.txt`) et le clone complet de `donnees` (391 Mo). Les données changent toutes les
heures : pour retrouver ces chiffres, se placer sur le commit `9951a30` de `donnees`.
