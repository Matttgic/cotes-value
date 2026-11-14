# Durer : limitation des comptes et robustesse des sources

Fait le 14/11/2026. Partie 1 sur la branche `donnees` (commit `f4324c4`, 17:45 UTC) : 5 050 paris uniques réglés
du 05/10 au 14/11, chiffres de `python scripts/durer.py --donnees <dossier>` (lecture seule, deux minutes, graine
fixe). Tous les tableaux : [durer-tableaux.md](durer-tableaux.md). Suite de
[strategie-mises.md](strategie-mises.md), dont la stratégie figée sert de base.

## Conclusion

1. **Le signal principal est la CLV, et il ne se cache pas.** Un compte qui bat la cote de clôture est repérable
   par définition. Un profil discret retarde le repérage, il ne l'empêche pas.
2. **Profil le moins repérable** : marchés principaux du match entier, grandes compétitions de football, tennis et
   basket, mise ronde et constante loin des plafonds, pari pris dans les dernières heures, quelques paris par jour
   et par bookmaker, un seul par match.
3. **Ce profil garde 7 à 15 % de l'avantage de la stratégie figée.** Il passe de 37 à 3,6 paris par jour. La CLV
   par pari ne baisse pas de façon mesurable (+2,55 % contre +3,60 %, écart non significatif) : la perte est une
   perte de volume. En euros attendus à 10 € la mise : environ 1 € par jour au lieu de 7 à 13 €.
4. **En ROI, rien n'est mesurable** : −16,3 % [−34,3 ; +5,7] sur 141 paris, contre +2,0 % [−5,5 ; +9,9] pour la
   stratégie figée. L'écart (−20,3 points [−39,4 ; +0,5]) contient zéro et la CLV ne le confirme pas.
5. **Le plafond de paris par jour est la règle la plus chère** : 3 paris par jour et par bookmaker, pris dans l'ordre
   d'arrivée, gardent 8 à 15 % de l'avantage. Monter le seuil d'écart à 7 % donne le même nombre de paris et garde
   49 à 81 %.
6. **Deux règles ne coûtent rien** : la mise ronde et constante, et les marchés où Pinnacle accepte plus de 500
   (CLV +4,69 % [+1,50 ; +8,63], contre +0,87 % sous 100 ; une seule période, à confirmer).
7. **À notre niveau de mise (1,60 à 10 €), le risque principal n'est pas le montant.** C'est le profil : 37 paris
   par jour, des ligues mineures, la moitié de l'avantage chez PMU seul.
8. **Robustesse : une détection de dérive est en place** (`cotes/derive.py`) : volume anormal, marché disparu,
   marchés non reconnus en hausse, cotes figées. Alerte sur la page Santé et par Pushover. Elle aurait signalé
   un gel silencieux de PMU le 10/11 (75 minutes sans aucun changement de cote, aucun incident au journal).

## 1. Limitation des comptes

### Ce qui est public

Le site de l'ANJ n'était pas joignable depuis cette session (`anj.fr` hors des domaines autorisés) : les points 1 à
3 viennent des extraits renvoyés par la recherche, pas du texte complet. Les liens sont en fin de document.

| # | Fait | Source | Fiabilité |
|---|---|---|---|
| 1 | Un opérateur de paris à cote ne peut ni refuser ni limiter les mises d'un joueur sans motif légitime. Motif admis : son exposition financière, par un plafond **égal pour tous les parieurs**. Limitation personnelle admise seulement pour le jeu excessif et la fraude ou le blanchiment (liste exacte non relue). | ANJ, délibération n° 2021-C-01 du 21/10/2021 et communiqué | Officielle, lue par extraits |
| 2 | 21 litiges de limitation de mises en 2022, 8 opérateurs, **PMU environ un tiers**. Un opérateur a limité un joueur qu'il soupçonnait d'utiliser un robot ou un logiciel de trading. | Médiateur des jeux, rapport 2022 | Officielle, lue par extraits |
| 3 | Les opérateurs « s'affranchissent » des règles rappelées par l'ANJ ; trois concentrent la majorité des demandes (noms non lus). Un joueur limité pour des paris « tardifs et sans aléa ». | Médiateur des jeux, rapport 2023 | Officielle, lue par extraits |
| 4 | Winamax se réserve des limites de mise selon le type de match ou de pari, **le profil du joueur et son comportement de pari**. Répéter un pari pour dépasser une limite est interdit. | Règlement des paris Winamax, versions 2021 | Officielle, ancienne |
| 5 | Winamax limite les comptes qui battent régulièrement la cote de clôture, jusqu'à quelques euros par pari ; pratique dite générale. | Avis Eurosport sur Winamax | Site d'affiliation |
| 6 | Un compte qui ne joue que les cotes boostées est averti, puis écarté des boosts. | Blog de value betting, un témoignage (page non identifiée avec certitude) | Faible |
| 7 | Unibet : plafond de mise par sport (1 000 € football, 200 € basket). | Stakemaker (comparateur) | Faible, non vérifié |
| 8 | Signaux suivis par les équipes de risque : CLV, pari juste après un mouvement de cote ailleurs, cote qui baisse après le pari, mises non rondes, mise maximale sur ligues mineures ou marchés peu liquides, arbitrage, bonus seuls, retraits rapides. | Trademate, track360, lettres spécialisées (extraits) | Commentaire du secteur, pas une règle d'opérateur |

Rien trouvé sur **OlyBet** ni sur une pratique propre à **Betclic**. Une décision ANJ n° 2026-132 de juin 2026
modifie la délibération de 2021 : son contenu n'a pas pu être lu. Aucun opérateur ne publie ses critères.

À retenir : en France la limitation personnelle d'un gagnant est interdite sur le papier et pratiquée dans les
faits. Le recours existe (service client, médiateur des jeux, ANJ).

### Le profil le moins repérable

| Dimension | Profil discret | Notre profil (stratégie figée) |
|---|---|---|
| Marchés | 1N2, vainqueur, total, handicap, match entier | 68 % des paris |
| Compétitions | Grandes ligues de football, tennis, basket | 70 % dans ces trois sports ; après la NBA, les ligues les plus jouées sont mineures (AHL, Coupe d'Europe FIBA, Eurocoupe féminine, Pro D2) |
| Montant | Rond, constant, loin du plafond, jamais fractionné | 10 € fixes : conforme. Kelly au 1/16 donne des montants au centime : à arrondir à l'euro |
| Délai | Dernières heures avant le match | 47 % à moins de 6 h |
| Moment | Pas dans la minute qui suit un mouvement de cote ailleurs | Pari à la première détection : c'est exactement ce signal |
| Fréquence | Quelques paris par jour et par bookmaker, un par match | 37 par jour : PMU 17,8, Betclic 13,8, Unibet 4,5 |
| Écart | Pas d'erreur de cote manifeste | 24 % des paris à 7 % et plus |

### Ce que ce profil coûte

Base : la stratégie figée (cote ≤ 5, écart ≥ 3 %, hors Winamax et OlyBet, au plus 24 h avant). Règles appliquées
l'une après l'autre. « Avantage gardé » = paris × CLV Pinnacle, rapporté à la base.

| Règles cumulées | Paris par jour | ROI | CLV Pinnacle | Avantage gardé | Sur B |
|---|---|---|---|---|---|
| Stratégie figée | 37,0 | +2,0 % [−5,5 ; +9,9] | +3,60 % [+2,62 ; +4,67] | 100 % | 100 % |
| Marchés principaux, match entier | 25,3 | +2,7 % | +3,61 % | 68 % | 54 % |
| + football, tennis, basket | 15,9 | +6,1 % | +3,94 % | 47 % | 33 % |
| + pris au plus 6 h avant | 6,5 | +2,2 % | +3,18 % | 16 % | 21 % |
| + écart < 7 % | 5,4 | −1,9 % | +2,36 % | 10 % | 15 % |
| + 1 par match, 3 par jour, par bookmaker | **3,6** | **−16,3 % [−34,3 ; +5,7]** | **+2,55 % [+0,78 ; +4,45]** | **7 %** | **15 %** |

- **Profil complet contre le reste de la stratégie** : CLV −1,16 point [−3,08 ; +0,74], ROI −20,3 points
  [−39,4 ; +0,5]. Sur la période B seule : CLV +1,68 point [−1,87 ; +5,32], ROI −18,5 points [−47,8 ; +15,2].
  Aucun de ces écarts n'exclut zéro. 141 paris ne jugent pas un ROI.
- **Sur les paris du site** (cote ≤ 5, tous bookmakers) le profil ne garde rien : CLV −0,10 % [−1,63 ; +1,41].
- **Avec Winamax et OlyBet** le résultat ne change pas (CLV du profil +0,64 %) : ces deux bookmakers n'apportent
  pas d'avantage à protéger.

Chaque règle seule, sur la stratégie figée :

| Règle | Paris par jour | CLV | Avantage gardé | Sur B |
|---|---|---|---|---|
| Marchés principaux, match entier | 25,3 | +3,61 % | 68 % | 54 % |
| Football, tennis, basket | 25,8 | +3,66 % | 71 % | 77 % |
| Pris au plus 6 h avant | 17,3 | +3,77 % | 49 % | 80 % |
| Pris au plus 3 h avant | 13,0 | +4,32 % | 42 % | 79 % |
| Écart < 7 % | 28,3 | +2,53 % | 54 % | 24 % |
| 1 par match et par bookmaker | 23,8 | +2,58 % | 46 % | 39 % |
| 1 par match, 3 par jour, par bookmaker | 8,3 | +2,45 % | 15 % | 8 % |
| Écart ≥ 5 % (au lieu de 3 %) | 16,1 | +5,13 % | 62 % | 89 % |
| Écart ≥ 7 % | 8,7 | +7,49 % | 49 % | 81 % |

- **L'avantage est dans les gros écarts** : les retirer est la règle la plus chère par pari.
- **Parier près du match ne coûte que du volume** : la CLV par pari ne baisse pas.
- **Réduire la fréquence par le seuil** vaut 3 à 10 fois mieux que par un plafond dans l'ordre d'arrivée. Mais
  les gros écarts sont aussi les paris les plus voyants : les deux objectifs se contredisent.

Limite de mise acceptée par Pinnacle, connue pour 549 paris de la stratégie figée (période B presque seule) :

| Limite Pinnacle | Paris | CLV | IC 95 % |
|---|---|---|---|
| ≤ 100 | 149 | +0,87 % | [−1,74 ; +3,23] |
| 101 à 500 | 226 | +1,27 % | [−0,64 ; +3,07] |
| > 500 | 174 | +4,69 % | [+1,50 ; +8,63] |

Les marchés liquides sont à la fois les plus discrets et ceux où la CLV est la plus haute. Une seule période, des
intervalles larges : à revoir à la prochaine mesure avant d'en faire une règle.

### Combien de temps avant d'être repéré

Raisonnement, pas un fait publié. Il faut environ 400 mesures pour distinguer une CLV de +2 % de zéro
([strategie-mises.md](strategie-mises.md)) ; un bookmaker qui suit la CLV d'un compte a la même contrainte.

| Bookmaker | Paris par jour (stratégie figée) | 400 paris en |
|---|---|---|
| PMU | 17,8 | 22 jours |
| Betclic | 13,8 | 29 jours |
| Unibet | 4,5 | 89 jours |
| Profil discret (3 par jour au plus) | ≤ 3 | 133 jours ou plus |

Diviser la fréquence divise l'avantage par jour autant qu'elle allonge le délai : le gain total avant repérage ne
change pas. La discrétion n'a d'intérêt que contre les règles simples (ligues mineures, mise maximale, pari juste
après un mouvement), pas contre la mesure de la CLV.

### Recommandation

1. Ne pas adopter le profil complet : il retire 85 à 93 % de l'avantage pour un risque non chiffré.
2. Garder ce qui est gratuit : mise ronde et constante (arrondir Kelly à l'euro), jamais deux fois le même pari.
3. Suivre la limite Pinnacle dans la prochaine mesure ; si le résultat tient, préférer les marchés liquides.
4. Compter les paris par jour et par bookmaker, et noter tout refus ou plafond rencontré : c'est la seule donnée
   propre à nos comptes, et elle manque.
5. PMU porte 50 à 57 % de l'avantage et le tiers des litiges de limitation de 2022 : c'est le compte à ménager en
   premier, et la dépendance à réduire.

## 2. Robustesse : panne et dérive des formats

### Ce qui existait

| Risque | Détection | Alerte |
|---|---|---|
| Source en erreur, refus 403/429, lecture partielle | `cotes/surveillance.py`, journal d'incidents | Page Santé |
| Marché mal traduit (cotes aberrantes) | `cotes/controle.py` : bloque les paris | Page Santé |
| Libellé qu'aucun traducteur ne reconnaît | `cotes/inconnus.py` : relevé | Page Santé, sans seuil |
| Cote Pinnacle figée ou trop vieille | `cotes/mouvement.py`, `cotes/pinnacle.py` | Pari bloqué |
| Stratégie en erreur | `cotes/pannes.py` | Pushover |

Trou : une source lue **sans erreur** dont le contenu a changé. Lecture vide, marché qui disparaît parce que son
libellé a été renommé, cache qui sert les mêmes cotes. Rien ne le signalait.

### Conception

Chaque source est comparée à sa propre habitude récente (moyenne glissante d'une heure), à chaque cycle.

| Signal | Mesure | Anomalie | Sources |
|---|---|---|---|
| Volume | Cotes et matchs lus | Moins de 50 % de l'habituel | Winamax, Betclic, Unibet, PMU, OlyBet, NetBet, Pinnacle, Polymarket, Matchbook, Smarkets |
| Marché disparu | Part des matchs d'un sport qui ont le marché (« football TOTAL MATCH ») | Moins de 30 % de la part habituelle, pour un marché présent d'habitude sur 30 % des matchs, le sport gardant 10 matchs | Les mêmes |
| Marchés non reconnus | Offres non reconnues / offres lues | Part doublée et en hausse de 10 points | Les six bookmakers français |
| Cotes figées | Empreinte de toutes les cotes de la source | Aucun changement depuis 45 min (Betclic, NetBet, OlyBet), 60 min (PMU), 90 min (Unibet), 150 min (Winamax), avec au moins 200 cotes | Les six bookmakers français |

- **Délais en minutes, pas en cycles** : 60 min d'apprentissage, 15 min d'anomalie avant l'alerte. Mêmes durées
  sur GitHub (5 min) et sur le serveur (1 min).
- **Pendant l'anomalie l'habitude ne bouge pas.** Après 6 h, le nouveau niveau devient l'habitude : un changement
  durable est signalé une fois.
- **Une source en panne, coupée ou servie depuis un cache n'est pas jugée** : la panne est déjà suivie. Une
  lecture vide sans erreur, elle, est une chute de volume.
- **Le nombre de matchs du jour ne déclenche rien** : la baisse lente d'une soirée est suivie par la moyenne, et un
  marché est mesuré en part des matchs de son sport.

### Alerte

- **Page Santé** : l'étape passe en « Alerte » avec le motif (« Dérive : 72 cotes, 240 d'habitude ») et entre au
  journal d'incidents, pour toutes les sources.
- **Pushover** : un message par source et par signal, au début de l'anomalie. Les secrets `PUSHOVER_APP_TOKEN` et
  `PUSHOVER_USER_KEY` sont maintenant passés à l'étape de collecte.
- **Aucun pari n'est bloqué.** L'état vit dans la mémoire de travail (`derive_sources`), hors de la branche
  `donnees` ; perdu, il se réapprend en une heure. Coût : 0,25 seconde par cycle.

### Réglage des cotes figées sur l'historique

16 jours de `cotes/*.jsonl.gz` (30/10 au 14/11), changements comptés par bookmaker et par tranche de 5 minutes.

| Bookmaker | Plus longue durée sans changement, hors panne connue | Seuil |
|---|---|---|
| Betclic | 5 min | 45 min |
| NetBet | 15 min | 45 min |
| OlyBet (3 jours d'historique) | moins de 5 min | 45 min |
| PMU | 45 min, et deux épisodes de 75 min | 60 min |
| Unibet (7 jours hors panne) | moins de 30 min | 90 min |
| Winamax (5 jours) | 111 min, la nuit | 150 min |

**Le 10/11 de 08:15 à 09:30 UTC, PMU n'a changé aucune cote** (220 changements par cycle en médiane sur la
période), pendant que Betclic et Winamax bougeaient, sans aucun incident PMU au journal. Cause inconnue. Le seuil de 60
minutes l'aurait signalé à 09:15. Le second épisode (09/11, 02:05 à 03:20) est de nuit et peut être normal : à ce
seuil, compter une alerte PMU de trop toutes les deux semaines.

### Limites

- **Seuils de volume et de marchés non réglés sur l'historique** : le volume par source n'était pas enregistré. Les
  seuils sont prudents (chute de moitié pendant 15 minutes). À revoir après deux semaines d'alertes.
- **Lectures tournantes** (PMU, Unibet, Betclic) : les marchés secondaires viennent en partie de la mémoire du
  cycle précédent. Un marché disparu peut y être vu avec retard.
- **Nouveaux libellés** : non utilisés comme signal. Le relevé garde 200 libellés par bookmaker, PMU et Betclic
  sont au plafond, un libellé ancien y revient comme « nouveau ».
- **FanDuel et DraftKings** : pas jugés. Leurs props n'existent que les jours de match, le volume tombe à zéro
  chaque jour.
- **Références** : pas de détection de cotes figées (aucun historique pour régler un seuil ; Pinnacle a déjà ses
  propres gardes).
- **Suite possible** : écarter des paris les cotes d'une source signalée figée, comme pour Pinnacle. Non fait :
  c'est un changement des règles de prise.

## Sources

Officielles, lues par extraits de recherche (site non joignable depuis la session) :

- ANJ, [communiqué « Limitation des mises des parieurs : l'ANJ rappelle les règles aux opérateurs »](https://anj.fr/limitation-des-mises-des-parieurs-lautorite-nationale-des-jeux-rappelle-les-regles-aux-operateurs)
- ANJ, [délibération n° 2021-C-01 modifiée](https://www.anj.fr/sites/default/files/2026-06/D%C3%A9lib%C3%A9ration%20n%C2%B0%202021-C-01_LimitationMisesParieurs%20modifi%C3%A9e.pdf)
  et [décision n° 2026-132](https://www.anj.fr/sites/default/files/2026-06/D%C3%A9cision%20n%C2%B02026-132_ModificationD%C3%A9lib%C3%A9rationLimitationMisesParieurs.pdf) (contenu non lu)
- Médiateur des jeux, [rapport 2022](https://anj.fr/sites/default/files/2023-06/ANJ%20%20MEDIATEUR%20Rapport%20annuel%20m%C3%A9diation%202022.pdf)
  et [rapport 2023](https://anj.fr/sites/default/files/2024-05/Rapport%20annuel%20m%C3%A9diation%202023.pdf)
- Winamax, règlement des paris sportifs : [février 2021](https://operator-front-static-cdn.winamax.fr/img/content/poker/2021/20210201_TermsPdf/rbetting.pdf),
  [avril 2021](https://operator-front-static-cdn.winamax.fr/img/content/poker/2021/20210420_TermsPdf/betting.pdf) ;
  version en vigueur à relire sur [winamax.fr](https://www.winamax.fr/cgu-paris-sportifs)

Presse, comparateurs et commentaire du secteur :

- Eurosport, [avis Winamax](https://www.eurosport.fr/paris-sportifs/winamax/)
- Stakemaker, [plafonds de mise des bookmakers](https://www.stakemaker.org/guide/mise-maximum/)
- Trademate Sports, [« How Bookmakers Profile Winning Players »](https://www.tradematesports.com/en/blog/bookmaker-profile-winning-players-thoughts-tipsters)
  et [« How to Avoid Getting Limited by Bookmakers »](https://www.tradematesports.com/en/blog/how-to-avoid-getting-limited-by-bookmakers/)
- track360, [guide opérateur sur la limitation des mises](https://track360.io/blog/sportsbook-bet-limiting-sharp-player-liability-operator-guide-2026)
- Sharp Bets Club, [« Anatomy of a limited account »](https://sharpbetsclub.substack.com/p/anatomy-of-a-limited-account-how)
