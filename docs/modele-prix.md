# Modèle de prix indépendant des bookmakers

Fait le 15/11/2026. Football seulement : 174 333 matchs de football-data.co.uk (38 ligues, du 02/03/2012 au
09/11/2026), avec le score et les cotes de clôture Pinnacle. Tous les chiffres sortent de `etudes/modele_prix.py`
(lecture seule, graine fixe) ; tous les tableaux : [modele-prix-tableaux.md](modele-prix-tableaux.md). Suite de
[avantage-reel.md](avantage-reel.md) et [cote-juste.md](cote-juste.md).

## Conclusion

1. **Le modèle ne peut pas servir de cote juste.** Sur 77 461 matchs qu'aucun réglage n'a vus (01/07/2019 au
   14/01/2026), les trois modèles (Elo, Poisson Dixon-Coles, Poisson + tirs cadrés) sont nettement moins bons que
   la clôture Pinnacle, sur le 1N2, le total 2,5 buts et le handicap asiatique. Ils retrouvent 72 à 73 % de ce que
   Pinnacle sait de plus qu'une fréquence fixe.
2. **Il n'apporte aucune information positive, nulle part.** Dans un mélange avec Pinnacle, son poids n'est
   positif dans aucun des 23 segments regardés (type de ligue, moment de la saison, favori, année), ni contre les
   cinq autres références (Pinnacle avant-match, bet365 avant-match et clôture, moyenne du marché, Betfair
   Exchange).
3. **Son désaccord avec Pinnacle est un signal à l'envers.** Le poids du modèle est négatif (−0,11 ± 0,05), sur
   la période de réglage comme sur le test : quand le modèle donne plus que Pinnacle à une issue, elle gagne encore
   moins souvent que Pinnacle ne l'annonce, et inversement. L'effet vaut environ 2 points de rendement de chaque
   côté.
4. **Parier sur les écarts du modèle perd deux fois la marge** : −6,1 % [−7,2 ; −4,9] aux cotes de clôture Pinnacle
   (toutes les issues : −3,5 %), −9,5 % chez bet365. Parier contre lui ne gagne pas non plus aux cotes Pinnacle :
   −1,1 % [−2,1 ; −0,1].
5. **Seul usage possible : trier les values du site, à vérifier.** À la meilleure cote du marché, les values
   repérées par Pinnacle rapportent +5,3 % [+3,7 ; +6,9] quand le modèle donne moins que Pinnacle, +0,1 %
   [−2,9 ; +3,0] quand il donne plus. Chez bet365 seul (1 700 à 2 200 paris), l'écart n'est pas mesurable. Ce tri a
   été regardé après coup : c'est une piste, pas une preuve.
6. **Il n'annonce pas le mouvement de Pinnacle sur le 1N2** (pente 0,004 ± 0,005 depuis 2019 ; 0,033 ± 0,005 avant :
   l'information a disparu). Sur le total de buts, la clôture se rapproche un peu du modèle avec tirs (7 % de
   l'écart, 1,5 % du mouvement expliqué) : trop peu pour un pari.
7. **Où il est le moins bon** : gros favoris (favori à 60 % ou plus), début de saison, premières divisions des
   petits pays d'Europe, et surtout quand il s'écarte de Pinnacle de 10 points ou plus : c'est Pinnacle qui a
   raison.
8. **Tennis, basket, hockey : rien n'a pu être construit.** Aucune source gratuite de résultats et de cotes
   Pinnacle n'a pu être lue depuis cette session (voir « Sources »).
9. **Aucun changement de code proposé.** Pinnacle reste la référence ; un modèle de ce type ne la remplace pas et ne
   la corrige pas.

## Sources

Chaque adresse a été lue avant usage ; les liens des 16 ligues supplémentaires viennent des pages du site lui-même.

| Source | Contenu | État |
|---|---|---|
| football-data.co.uk, `mmz4281/SAISON/DIVISION.csv` | 22 divisions d'Europe, 2012/13 à 2026/27 : score, tirs cadrés, cotes Pinnacle (avant-match et clôture), bet365, moyenne et meilleure cote du marché, Betfair Exchange | Lue : 330 fichiers, 110 277 matchs |
| football-data.co.uk, `new/PAYS.csv` | 16 ligues (Argentine, Autriche, Brésil, Chine, Danemark, Finlande, Irlande, Japon, Mexique, Norvège, Pologne, Roumanie, Russie, Suède, Suisse, États-Unis) : score et cotes de clôture | Lue : 16 fichiers, 64 056 matchs |
| tennis-data.co.uk | Tennis | Refuse la lecture (erreur 403), comme le 14/11 |
| aussportsbetting.com | Non lu | Hôte fermé par le réseau de la session : contenu non vérifié |
| Dépôts GitHub hors du projet (résultats de tennis) | Non lu | Hors du périmètre de la session |

- **Cotes Pinnacle** : jusqu'au 14/01/2026 dans les fichiers principaux, 14/12/2025 dans les 16 ligues. Après, les
  colonnes sont vides : 11 578 matchs récents ne sont pas jugés contre Pinnacle.
- **Total 2,5 buts et handicap Pinnacle** : depuis juillet 2019, fichiers principaux seulement.
- **Tirs cadrés** : 87 168 matchs des fichiers principaux, aucun dans les 16 ligues.
- **Buts attendus (xG)** : présents depuis 2026/27 seulement (2 007 matchs, sans cote Pinnacle) : non utilisés.

## Les trois modèles

Chaque prévision n'utilise que les matchs joués avant la date du match.

| Modèle | Principe | Marchés |
|---|---|---|
| Elo | Une note par équipe, mise à jour après chaque match selon l'écart de buts ; avantage du terrain par division, appris en continu ; retour partiel vers la moyenne à chaque saison ; la différence de notes donne 1N2 par un logit ordonné | 1N2 |
| Poisson (Dixon-Coles) | Attaque et défense par équipe, terrain par division, réajustés avant chaque journée sur 4 ans de matchs pondérés par leur ancienneté (demi-vie 9 mois) ; toutes les divisions d'un pays sont ajustées ensemble, ce qui place un promu ; correction des petits scores | 1N2, total, handicap |
| Poisson + tirs cadrés | Un second modèle de Poisson prévoit les tirs cadrés ; les buts attendus combinent les deux (exposants 0,77 pour les buts, 0,29 pour les tirs) | 1N2, total, handicap |

**Réglage** : sur les matchs d'avant le 01/07/2019 uniquement (60 761 matchs notés, après deux saisons de rodage).
Les grilles ont été élargies deux fois et la forme du modèle avec tirs changée une fois, toujours sur cette période.
La mesure sur les matchs suivants a été lancée une fois les réglages figés. Sur la période de réglage : Elo 1,0173,
Poisson 1,0173 ; les tirs cadrés gagnent 0,0012 de log-loss.

## 1. Niveau et calibration

Test : matchs depuis le 01/07/2019. Écart de log-loss ×10⁴, intervalle à 95 % par bootstrap sur les matchs ;
positif = le modèle est moins bon. Pente : 1 = calibré ; moins de 1 = probabilités trop tranchées. Pinnacle : méthode
puissance, celle du site.

| Marché | Modèle | Matchs | Log-loss modèle | Log-loss Pinnacle | Écart | Pente modèle | Pente Pinnacle |
|---|---|---|---|---|---|---|---|
| 1N2 | Elo | 77 461 | 1,0214 | 1,0011 | **+203 [+190 ; +218]** | 0,956 ± 0,018 | 1,007 ± 0,017 |
| 1N2 | Poisson | 77 461 | 1,0218 | 1,0011 | **+208 [+194 ; +220]** | 1,046 ± 0,020 | 1,007 ± 0,017 |
| 1N2 | Poisson + tirs | 45 300 | 1,0149 | 0,9969 | **+180 [+165 ; +194]** | 1,111 ± 0,026 | 1,016 ± 0,023 |
| Total 2,5 buts | Poisson | 48 504 | 0,6856 | 0,6745 | **+111 [+99 ; +122]** | 0,677 ± 0,044 | 1,006 ± 0,048 |
| Total 2,5 buts | Poisson + tirs | 45 212 | 0,6835 | 0,6739 | **+96 [+86 ; +107]** | 0,734 ± 0,046 | 1,007 ± 0,049 |
| Handicap asiatique | Poisson | 19 591 | 0,7126 | 0,6927 | **+200 [+173 ; +226]** | 0,300 ± 0,073 | 0,673 ± 0,264 |
| Handicap asiatique | Poisson + tirs | 18 290 | 0,7099 | 0,6926 | **+173 [+148 ; +198]** | 0,300 ± 0,082 | 0,685 ± 0,273 |

- **Repère** : annoncer toujours les fréquences de 2014-2019 (domicile 44,7 %, nul 26,1 %, extérieur 29,2 %) donne
  1,0764. Pinnacle gagne 0,0753 sur ce repère ; Elo en obtient 73 %, Poisson 72 %.
- **Calibration du 1N2** : correcte entre 20 et 50 %, fausse aux extrêmes. Une issue annoncée à 64 % par Poisson
  gagne 67 % du temps, une issue annoncée à 8 % gagne 6,7 % du temps. Pinnacle : 64,4 % annoncé, 64,9 % observé.
- **Total de buts** : le modèle est trop tranché (pente 0,68). Il annonce des écarts entre matchs que les buts ne
  confirment qu'aux deux tiers.
- **Handicap** : sur une ligne que le marché a déjà placée à 50/50, l'avis du modèle ne vaut presque rien (pente
  0,30).
- **Les tirs cadrés aident**, sans changer le classement : −25 [−29 ; −22] sur le 1N2, −19 [−23 ; −15] sur le
  total, sur les mêmes matchs.

## 2. Information ajoutée à la référence

Mélange p ∝ référence^a · modèle^b. b = 0 : le modèle n'apporte rien ; b > 0 : il faut se rapprocher de lui ; b < 0 :
il faut s'en éloigner. a et b sont ajustés sur une période puis figés. « Gain » : log-loss du mélange figé moins celui
de la référence recalibrée seule, ×10⁴, sur la période suivante ; négatif = le mélange fait mieux.

| Marché | Référence | Modèle | Ajusté sur | b ajusté | Jugé sur | Gain | b sur la période de jugement |
|---|---|---|---|---|---|---|---|
| 1N2 | Pinnacle, clôture | Elo | 59 806 | −0,114 | 77 461 | +0,2 [−1,2 ; +1,7] | **−0,051 ± 0,040** |
| 1N2 | Pinnacle, clôture | Poisson | 59 806 | −0,112 | 77 461 | **−1,3 [−2,5 ; −0,1]** | **−0,106 ± 0,045** |
| 1N2 | Pinnacle, clôture | Poisson + tirs | 26 537 | −0,127 | 45 300 | **−2,6 [−4,2 ; −1,1]** | **−0,183 ± 0,070** |
| 1N2 | Pinnacle, avant-match | Poisson | 38 282 | −0,073 | 48 407 | **−1,6 [−2,5 ; −0,7]** | **−0,155 ± 0,066** |
| 1N2 | bet365, avant-match | Poisson | 38 909 | −0,042 | 55 577 | **−0,7 [−1,2 ; −0,3]** | **−0,116 ± 0,061** |
| 1N2 | bet365, clôture | Poisson | 22 341 | −0,114 | 38 937 | −1,2 [−2,9 ; +0,5] | **−0,106 ± 0,066** |
| 1N2 | Moyenne du marché, clôture | Poisson | 21 767 | −0,133 | 89 006 | **−2,0 [−3,4 ; −0,7]** | **−0,135 ± 0,043** |
| 1N2 | Betfair Exchange, clôture | Poisson | — | — | 27 451 | — | **−0,166 ± 0,078** |
| Total 2,5 buts | Pinnacle, clôture | Poisson | 22 337 | −0,193 | 26 167 | −1,0 [−4,1 ; +2,0] | **−0,127 ± 0,094** |
| Total 2,5 buts | Pinnacle, clôture | Poisson + tirs | 20 899 | −0,168 | 24 313 | **−2,5 [−5,0 ; −0,1]** | **−0,193 ± 0,109** |
| Handicap asiatique | Pinnacle, clôture | Poisson | 8 924 | −0,146 | 10 667 | +1,9 [−3,2 ; +7,1] | −0,035 ± 0,102 |

- **b est négatif dans les 28 lignes du tableau complet**, significatif dans 22. Aucune référence, pas même
  bet365 avant-match, ne gagne à se rapprocher du modèle.
- **Le signe tient d'une période à l'autre** : −0,112 sur 2014-2019, −0,106 sur 2019-2026, contre la clôture
  Pinnacle. Il tient aussi contre Betfair Exchange, qui n'a pas de marge à retirer : ce n'est pas un effet du
  retrait de marge.
- **Le gain est minuscule** : 1 à 3 dix-millièmes de log-loss, quand Pinnacle en a 753 d'avance sur le repère.
- **Deux lectures possibles, non départagées.** Le marché ne va pas assez loin quand il s'écarte des résultats
  passés (blessures, compositions, nouvelles) ; ou le marché suit lui aussi un peu trop la forme récente, que le
  modèle suit encore plus. Dans les deux cas, la bonne correction est du côté opposé au modèle.

## 3. Par segment

1N2, clôture Pinnacle, modèle Poisson, test. « b » ajusté sur le segment lui-même ; p de Holm sur les 23 segments.

| Segment | Matchs | Écart modèle − Pinnacle | b | p corrigée |
|---|---|---|---|---|
| Cinq grands championnats, 1re division | 11 605 | +200 [+169 ; +232] | −0,178 ± 0,130 | 0,095 |
| Cinq grands championnats, 2e division | 13 041 | +184 [+154 ; +213] | −0,177 ± 0,119 | 0,056 |
| Angleterre divisions 3 à 5, Écosse 2 à 4 | 13 048 | +181 [+150 ; +213] | −0,060 ± 0,120 | 1,000 |
| Autres 1res divisions d'Europe (6 pays) | 10 898 | +249 [+215 ; +281] | −0,185 ± 0,119 | 0,040 |
| 16 ligues supplémentaires | 28 869 | +218 [+195 ; +241] | −0,061 ± 0,068 | 0,605 |
| Début de saison (moins de 6 matchs joués) | 13 949 | +251 [+219 ; +282] | −0,200 ± 0,102 | 0,002 |
| Reste de la saison | 63 512 | +198 [+183 ; +212] | −0,083 ± 0,050 | 0,023 |
| Favori Pinnacle à moins de 45 % | 31 843 | +163 [+146 ; +179] | −0,141 ± 0,070 | 0,002 |
| Favori de 45 à 60 % | 30 133 | +180 [+159 ; +201] | −0,076 ± 0,072 | 0,379 |
| Favori à 60 % et plus | 15 485 | +354 [+318 ; +392] | −0,083 ± 0,106 | 0,805 |
| Désaccord avec Pinnacle sous 5 points | 33 541 | +31 [+24 ; +39] | −0,152 ± 0,155 | 0,500 |
| Désaccord de 5 à 10 points | 26 190 | +165 [+145 ; +183] | −0,146 ± 0,087 | 0,019 |
| Désaccord de 10 points et plus | 17 730 | +604 [+558 ; +653] | −0,083 ± 0,068 | 0,198 |
| Matchs à huis clos (03/2020 à 06/2021) | 13 656 | +224 [+191 ; +258] | −0,114 ± 0,099 | 0,262 |

- **Aucun segment n'a un poids positif.** Le seul b positif du tableau complet est l'année 2019 (+0,099 ± 0,160),
  dans le bruit.
- **Les ligues peu suivies ne font pas exception** : divisions 3 à 5 anglaises, 16 ligues supplémentaires, le
  modèle y est aussi loin de Pinnacle qu'ailleurs (+181 à +218) et n'y ajoute rien.
- **L'écart se creuse** avec le favori (+354 à 60 % et plus) et en début de saison (+251) : Pinnacle sait ce que
  l'intersaison a changé, le modèle ne l'apprend qu'au fil des matchs.
- **Un désaccord fort est une erreur du modèle** : à 10 points ou plus d'écart (23 % des matchs), il perd 604.

## 4. Mouvement de Pinnacle entre l'avant-match et la clôture

Pente de (clôture − avant-match) sur (modèle − avant-match), en logit. 0 : le modèle ne sait rien de plus que
l'avant-match ; 1 : la clôture rejoint le modèle.

| Marché | Modèle | Période | Matchs | Pente | Part du mouvement expliquée |
|---|---|---|---|---|---|
| 1N2, domicile | Poisson | 2014-2019 | 37 630 | **0,033 ± 0,005** | 0,57 % |
| 1N2, domicile | Poisson | test | 48 393 | 0,004 ± 0,005 | 0,01 % |
| 1N2, domicile | Poisson + tirs | 2014-2019 | 26 319 | **0,040 ± 0,007** | 0,79 % |
| 1N2, domicile | Poisson + tirs | test | 45 122 | **0,023 ± 0,006** | 0,19 % |
| Total 2,5 buts, plus | Poisson | test | 48 294 | **0,043 ± 0,005** | 0,66 % |
| Total 2,5 buts, plus | Poisson + tirs | test | 45 022 | **0,072 ± 0,006** | 1,50 % |

Le prix d'avant-match contient déjà ce que le modèle sait du 1N2. Sur le total, la clôture fait 7 % du chemin vers
le modèle avec tirs : pour un désaccord de 10 % sur la cote, 0,7 % de mouvement attendu, sous la marge.

## 5. Parier avec ou contre le modèle

Test, 1N2, cote ≤ 5, mise fixe, intervalle par bootstrap sur les matchs. « Avec » : la cote dépasse la cote juste du
modèle Poisson d'au moins 2 %. « Contre » : Pinnacle donne à l'issue au moins 10 % de plus que le modèle.

| Cotes jouées | Toutes les issues | Avec le modèle | Contre le modèle | Méthode du site (Pinnacle, ≥ 2 %) |
|---|---|---|---|---|
| Pinnacle, clôture | −3,5 % (204 709) | **−6,1 % [−7,2 ; −4,9]** (64 170) | **−1,1 % [−2,1 ; −0,1]** (54 623) | — |
| bet365, avant-match | −6,3 % (131 250) | **−9,5 % [−11,1 ; −7,9]** (31 726) | **−3,1 % [−4,4 ; −1,7]** (30 400) | +1,3 % [−6,9 ; +8,6] (1 696) |
| bet365, clôture | −6,2 % (134 458) | **−9,4 % [−10,9 ; −7,8]** (34 626) | **−2,9 % [−4,1 ; −1,8]** (34 564) | +1,4 % [−4,8 ; +7,9] (2 199) |
| Meilleure cote du marché, clôture | −0,6 % (202 045) | **−3,0 % [−4,0 ; −2,1]** (76 684) | **+2,6 % [+1,6 ; +3,6]** (54 211) | **+3,8 % [+2,4 ; +5,2]** (34 229) |

- **Le modèle annonce +15 % d'écart moyen sur ses paris et perd 6 %** : ses écarts sont ses erreurs.
- **L'effet n'est pas celui du favori** : les paris « contre » ont des cotes plus courtes (2,5 contre 3,4), mais
  Pinnacle leur prévoyait −2,9 % et ils font −1,1 % ; il prévoyait −4,0 % aux paris « avec » et ils font −6,1 %.
- **Avec le modèle à tirs, parier contre lui fait jeu égal aux cotes Pinnacle** : −0,1 % [−1,3 ; +1,2] sur 28 836
  paris. Pas un gain.
- **La meilleure cote du marché** est celle du plus offrant parmi des dizaines de bookmakers : personne ne
  l'obtient à chaque pari. Elle sert de borne haute, pas de prévision.
- Les lignes « contre » ont été ajoutées après avoir vu le poids négatif de la partie 2.

## 6. Le modèle trie-t-il les values du site ?

Paris de la méthode du site (cote ≥ cote juste Pinnacle + 2 %, cote ≤ 5), selon l'avis du modèle Poisson sur la même
issue.

| Cotes jouées | Paris | Nombre | ROI [IC 95 %] |
|---|---|---|---|
| Meilleure cote du marché, clôture | Tous | 34 229 | **+3,8 % [+2,4 ; +5,1]** |
| Meilleure cote du marché, clôture | Le modèle donne plus que Pinnacle | 10 236 | +0,1 % [−2,9 ; +3,0] |
| Meilleure cote du marché, clôture | Le modèle donne moins que Pinnacle | 23 993 | **+5,3 % [+3,7 ; +6,9]** |
| Meilleure cote du marché, clôture | Le modèle donne au moins 10 % de moins | 13 560 | **+7,0 % [+4,9 ; +9,1]** |
| bet365, avant-match | Le modèle donne plus que Pinnacle | 603 | −1,6 % [−14,7 ; +12,3] |
| bet365, avant-match | Le modèle donne moins que Pinnacle | 1 093 | +2,9 % [−6,1 ; +11,9] |
| bet365, clôture | Le modèle donne plus que Pinnacle | 862 | +1,8 % [−8,7 ; +12,8] |
| bet365, clôture | Le modèle donne moins que Pinnacle | 1 337 | +1,1 % [−6,5 ; +9,0] |

- **À la meilleure cote, le tri sépare** : pente du gain sur l'avis du modèle −0,19 ± 0,10. Une value que le modèle
  « confirme » ne rapporte rien ; une value qu'il contredit rapporte le plus.
- **Chez un bookmaker réel, rien n'est mesuré** : bet365 dépasse rarement la cote juste Pinnacle de 2 % (1 696
  issues sur 131 250), les intervalles font 16 à 27 points de large.
- **Une value confirmée par un modèle statistique n'est donc pas plus sûre.** C'est l'inverse de l'intuition, et le
  seul enseignement directement utile au site.

## Limites

- **Football seulement**, et le 1N2 pour l'essentiel. Aucun marché à deux issues très déséquilibré, aucune prop.
- **Modèles simples** : scores et tirs cadrés. Ni compositions, ni blessures, ni buts attendus, ni calendrier. Un
  modèle plus riche ferait mieux ; rien ici ne dit de combien.
- **Pas de cote Pinnacle après le 14/01/2026** dans les fichiers.
- **Cotes Pinnacle des fichiers à 3 % de marge**, notre lecture à 5,5 à 7 % (cote-juste.md).
- **Parties 5 (lignes « contre ») et 6** : ajoutées après lecture des premiers résultats du test. Le poids négatif
  lui-même a été ajusté sur 2014-2019 puis vérifié sur 2019-2026.
- **Meilleure cote du marché** : borne haute, non jouable telle quelle ; une saisie fausse y compte comme une value.
- **Promus de hors fichiers** : placés à 90 % du niveau moyen de leur division, faute d'historique.

## Décisions proposées

1. Ne pas utiliser un modèle statistique comme cote juste ni comme référence, sur aucun marché du football.
2. Ne pas présenter l'accord d'un modèle comme une confirmation d'une value.
3. Une seule mesure à faire avant toute règle : sur les paris 1N2 de football réglés du site, comparer les values
   où le modèle donne moins que Pinnacle aux autres, par la CLV Pinnacle. Une ligne de test, pas une stratégie
   (avantage-reel.md, décision 5).
4. Tennis et basket : il faut des fichiers de résultats, fournis à la main ou venus d'une source que la session
   peut lire. `references/` garde les clôtures Pinnacle depuis le 12/11 : elles serviront de juge.

## Reproduire

Fichiers principaux (330 requêtes, 40 Mo), comme pour cote-juste.md :

```bash
mkdir -p football && for s in 1213 1314 1415 1516 1617 1718 1819 1920 2021 2122 2223 2324 2425 2526 2627; do for d in E0 E1 E2 E3 EC SC0 SC1 SC2 SC3 D1 D2 I1 I2 SP1 SP2 F1 F2 N1 B1 P1 T1 G1; do curl -sSL -o "football/$s-$d.csv" "https://www.football-data.co.uk/mmz4281/$s/$d.csv"; sleep 0.2; done; done
```

Les 16 ligues supplémentaires (9 Mo) :

```bash
mkdir -p football-plus && for p in ARG AUT BRA CHN DNK FIN IRL JPN MEX NOR POL ROU RUS SWE SWZ USA; do curl -sSL -o "football-plus/$p.csv" "https://www.football-data.co.uk/new/$p.csv"; sleep 0.3; done
```

Mesure (2 minutes, 4 processus) :

```bash
python etudes/modele_prix.py mesurer --football football --football-plus football-plus
```

Réglage, sur les matchs d'avant le 01/07/2019 (3 minutes) :

```bash
python etudes/modele_prix.py regler --football football --football-plus football-plus
```

Demande numpy (`requirements-dev.txt`). Les fichiers du site sont complétés deux fois par semaine : les chiffres de
la saison en cours bougent, ceux du test contre Pinnacle (clos au 14/01/2026) non.
