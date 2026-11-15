# Protocole de validation fixé à l'avance — 15 novembre 2026

Suite de [avantage-reel.md](avantage-reel.md) : aucun avantage n'est prouvé, et les règles de lecture ont été fixées
après avoir vu les résultats. Ce protocole fixe tout avant les paris : l'hypothèse, les règles de chaque stratégie,
le nombre de paris à atteindre, le critère d'arrêt et le test. Il s'applique aux **paris détectés à partir du
16/11/2026 à 00 h (Paris)**. Les résultats d'avant ne comptent pas : ils ont seulement servi à calculer le nombre de
paris.

Le protocole est écrit dans [`cotes/protocole_registre.json`](../cotes/protocole_registre.json), appliqué par
`cotes/protocole.py` à chaque construction du site, et verrouillé par `tests/test_protocole.py`.
Scellé du registre au gel : `94faa228f06db04aaf16e855c0a9f604ad5dc594617497357672883fdad94651`.

## En bref

| | Règle, la même pour les 70 stratégies |
|---|---|
| Hypothèse | La CLV moyenne contre la clôture Pinnacle est positive |
| Paris comptés | Détectés depuis le 16/11/2026, cote ≤ 5, réglés, clôture Pinnacle connue (« paris mesurés ») |
| Nombre à atteindre | Propre à chaque stratégie, de 300 à 1 680 paris mesurés (tableau du registre) |
| Lectures | Deux seulement : à la moitié du nombre, puis au nombre entier. Aucun verdict entre les deux |
| Succès | À la lecture finale : CLV moyenne > 0 avec p < 0,025 %, clôture connue pour au moins la moitié des réglés, au moins 50 matchs, rendement pas nettement sous la CLV |
| Échec | Lecture finale sans succès ; CLV moyenne ≤ 0 à mi-parcours ; échéance du 16/11/2027 sans volume ; mise en pause |
| Test | Student unilatéral sur la CLV moyenne par pari, le match comme unité de hasard |
| Règle modifiée | Le protocole de la stratégie est rompu. La nouvelle version repart de zéro, sur une nouvelle place |

## 1. Hypothèse

- **À rejeter** : la CLV moyenne de la stratégie contre la clôture Pinnacle sans marge est nulle ou négative.
- **À prouver** : elle est positive.

La mesure est la CLV et non le ROI, pour deux raisons mesurées dans avantage-reel.md :

- le ROI ne tranche pas : à +1 % d'avantage il faut 375 000 paris, dix ans au rythme actuel ;
- à cote ≤ 5, la CLV contre la clôture Pinnacle prédit le rendement pari par pari (un point de CLV vaut 1,23 point
  de rendement [0,55 ; 1,89]). La clôture des autres références ne le prédit pas : elle ne sert pas ici.

Le ROI reste un garde-fou : une stratégie dont le rendement est nettement sous sa CLV n'est pas validée (§ 5).

## 2. Règles figées

**Règles de chaque stratégie.** Chacune a une empreinte dans le registre. L'empreinte est calculée en rejouant ses
règles sur un jeu de paris témoin figé (`tests/fixtures/protocole_temoin.json.gz` : les 6 506 paris détectés
jusqu'au 15/11/2026 à 04 h 38 UTC, sans résultats ni décisions déjà prises) : ce sont ses paramètres déclarés et
la liste exacte des paris qu'elle y prend.

- Réécrire le code sans changer la règle ne change pas l'empreinte.
- Changer un seuil, un filtre, un plafond ou un départage qui déplace un seul pari du témoin la change.
- Le témoin ne contient ni statut, ni gain, ni CLV : une sélection ne peut pas dépendre d'un résultat.

Si l'empreinte change : le test `tests/test_protocole.py` échoue, donc rien ne se fusionne ; et le site affiche
« Protocole rompu » pour la stratégie, définitivement (les paris pris entre-temps ne sont plus ceux de la règle
inscrite). Pour changer une règle, il faut changer la version de la stratégie et l'inscrire de nouveau : son ancien
protocole est clos (« remplacée »), le nouveau repart de zéro à la date d'inscription et prend une place de plus.

**Règles du protocole.** Les règles communes et les 70 inscriptions sont couvertes par le scellé (SHA-256). Le test
vérifie le scellé de chaque état passé du registre : on peut ajouter une inscription, pas en modifier une. Changer
un nombre de paris, un seuil ou une date fait échouer le test, et se voit dans le journal Git de deux fichiers.

**Ce qui reste permis**, parce que cela ne change ni les paris pris ni la façon de les juger : corriger un bug qui ne
déplace aucun pari du témoin, améliorer l'affichage, enregistrer la clôture Pinnacle de plus de paris (c'est une
mesure, pas une règle).

**Ce qui est interdit** : changer le nombre de paris, le seuil ou l'échéance ; retirer des paris, des jours ou des
bookmakers après coup ; lire le test avant les deux lectures prévues ; relire une lecture déjà faite.

Les règles de chaque stratégie sont décrites dans leur document (`docs/strategie-*.md`,
[variantes-prudentes.md](variantes-prudentes.md), [protocole-comparaison.md](protocole-comparaison.md) pour les 24
règles du laboratoire). Le registre en fige la version et l'empreinte.

## 3. Paris comptés

Un pari compte pour une stratégie s'il remplit tout ceci :

1. il fait partie de sa sélection officielle (décision figée à la prise, `cotes/decisions.py`) ;
2. il est détecté à partir du début du protocole de la stratégie (16/11/2026 à 00 h, Paris) ;
3. sa cote est ≤ 5, comme dans tous les bilans du site ;
4. il est réglé ;
5. sa CLV contre la clôture Pinnacle est connue : clôture lue dans les 30 minutes avant le début, celle du pari si
   Pinnacle est sa référence, sinon celle du même pari (même bookmaker, match, marché, issue) repéré aussi par
   Pinnacle. C'est la mesure de avantage-reel.md, § 3.

Les paris sont rangés par début de match, puis détection, puis identifiant. Une lecture à N paris porte sur les N
premiers de cet ordre. Mise fixe de 10 € : le mode de mise du site ne change rien au protocole.

## 4. Nombre de paris à atteindre

N = ((3,481 + 0,842) × σ / 2 %)², arrondi à la dizaine supérieure, avec un minimum de 300.

- **2 %** : l'avantage que le protocole doit pouvoir prouver. Viser deux fois moins demande quatre fois plus de
  paris (1 100 à 6 700 pour 1 %).
- **3,481** : seuil unilatéral de 0,025 %, soit 5 % partagés entre 200 places (Bonferroni). 70 places sont prises ;
  130 restent pour les nouvelles stratégies et les nouvelles versions. Le seuil ne dépend donc pas du nombre de
  stratégies ajoutées plus tard. À 200 inscriptions, plus aucune n'est acceptée.
- **0,842** : puissance de 80 %. Une stratégie dont la vraie CLV vaut 2 % est validée 4 fois sur 5.
- **σ** : écart-type de la CLV par pari de la stratégie, paris d'un même match groupés, mesuré sur ses paris d'avant
  le gel. Moins de 50 mesures : 12 % par défaut (27 stratégies).

Lecture du tableau du registre (en bas) : σ va de 7,7 % à 19,0 %, donc N de 300 à 1 680. Les stratégies à gros écart
(Défi) ont une CLV deux fois plus dispersée et demandent quatre fois plus de paris.

**Durée attendue**, au rythme des 14 jours d'avant le gel : 11 stratégies finissent en 60 jours ou moins, 21 entre 61
et 180 jours, 15 entre 181 et 365 jours, et **23 n'atteignent pas leur nombre avant l'échéance**.

## 5. Lectures et critère d'arrêt

Deux lectures par stratégie, déclenchées par le nombre de paris mesurés, jamais par une date choisie ni par un
résultat. Entre les deux, le site montre l'avancement (paris mesurés sur N), pas de verdict.

**Mi-parcours (N / 2 paris mesurés)** : échec anticipé seulement, jamais de succès.

- Échec si la CLV moyenne est ≤ 0.
- Échec si le rendement est nettement sous la CLV (même règle qu'à la lecture finale).
- Sinon le protocole continue. Une stratégie dont la vraie CLV vaut 2 % est arrêtée à tort ici 1 fois sur 1 000.

**Lecture finale (N paris mesurés)** : succès si les quatre conditions sont réunies.

1. Au moins 50 matchs différents.
2. Clôture Pinnacle connue pour au moins la moitié des paris réglés du protocole (sinon la CLV ne décrit qu'un
   sous-ensemble : avantage-reel.md, § 3).
3. CLV moyenne > 0 avec p < 0,025 % (§ 6).
4. Rendement pas nettement sous la CLV : sur les paris mesurés, l'écart moyen (rendement − CLV) n'est pas négatif
   au seuil unilatéral de 2,5 %. C'est le cas des stratégies à forte CLV qui perdent quand même (Claude Défi 5 :
   CLV +8,4 %, ROI −37,9 %).

**Échec** dans tous les autres cas :

| Motif | Quand |
|---|---|
| CLV négative à mi-parcours | CLV moyenne ≤ 0 sur les N / 2 premiers paris mesurés |
| CLV non prouvée | Lecture finale : p ≥ 0,025 % ou CLV moyenne ≤ 0 |
| Rendement sous la CLV | Mi-parcours ou lecture finale : condition 4 non remplie |
| Clôture Pinnacle trop rare | Lecture finale : connue pour moins de la moitié des réglés |
| Trop peu de matchs | Lecture finale : moins de 50 matchs |
| Volume insuffisant | Échéance (365 jours après le début) atteinte avant la mi-parcours |
| Pause | La stratégie est mise en pause automatique (`cotes/pauses.py`) : elle ne prend plus de paris |
| Remplacée | Une nouvelle version de la stratégie est inscrite |

**Échéance** : 365 jours après le début, soit le 16/11/2027 pour les 70 stratégies inscrites au gel. Si la
mi-parcours est passée mais pas N, la lecture finale se fait ce jour-là sur les paris mesurés disponibles, avec les
mêmes conditions. La date est fixée d'avance : elle ne dépend d'aucun résultat.

Un verdict est définitif. Une lecture est écrite une seule fois dans `protocole.json` (branche `donnees`) et n'est
jamais recalculée, même si un règlement est corrigé plus tard.

## 6. Test statistique

- **Statistique** : t = CLV moyenne par pari / erreur type. L'erreur type est calculée par match (les paris d'un
  même match varient ensemble), avec l'estimateur de `scripts/avantage_reel.py`.
- **Loi** : Student à (matchs − 1) degrés de liberté, test unilatéral.
- **Seuil** : p < 0,025 % (t > 3,5 environ). Un seul test par stratégie, à la lecture finale.
- **Correction** : Bonferroni sur 200 places, fixée d'avance. Les stratégies partagent des paris : Bonferroni reste
  valable dans ce cas.
- **Garde-fou du rendement** : même test, sur l'écart (rendement − CLV) par pari, côté négatif, seuil de 2,5 %.

Pourquoi Student et non le bootstrap de avantage-reel.md : le test est refait à chaque construction du site, sans
numpy, et doit donner le même résultat à la main. La CLV est bien moins asymétrique que les gains.

**Contrôle par simulation** (`scripts/protocole.py --simuler`, graine fixe) : pour chacune des 23 stratégies
d'au moins 100 CLV mesurées avant le gel, 200 000 échantillons de la taille de son protocole sont tirés par matchs
entiers dans ses propres CLV.

- Sans avantage (CLV recentrées sur zéro) : faux succès de 0,011 % à 0,042 % selon la stratégie, médiane 0,027 %,
  pour 0,025 % visé. Le seuil est tenu en moyenne, dépassé au pire d'un facteur 1,7.
- Avec une CLV de 2 % : succès de 78 % à 84 %, médiane 80 %. Le nombre de paris donne bien la puissance prévue.
- Risque d'au moins un faux succès sur les 70 stratégies : 3 % au plus, au taux le plus défavorable mesuré.

## 7. Suivi automatique

À chaque construction du site (`scripts/site_web.py` › `suivi_protocole`), pour chaque stratégie :

1. les empreintes des règles sont recalculées sur le témoin et comparées au registre ;
2. les paris du protocole sont comptés ;
3. si un seuil de lecture vient d'être franchi, la lecture est faite et écrite dans `protocole.json` ;
4. l'état est publié dans les données du site (`D.protocole`).

Dans le site, onglet Bilan › Stratégies :

- **dans la ligne de chaque stratégie**, une étiquette : « Protocole 37 % » (avancement), « Validée », « Non
  validée », « Protocole rompu » ou « Hors protocole » ;
- **dans sa fiche**, le panneau « Protocole de validation » : paris mesurés sur N, mi-parcours, lecture finale,
  échéance, date de fin au rythme actuel, et les chiffres de chaque lecture faite ;
- **sous les recommandées**, la liste « Protocole de validation » : toutes les stratégies par état.

Une stratégie affichée « Hors protocole » n'est pas inscrite : aucune conclusion n'est permise sur elle. C'est le cas
d'une fusion automatique (Fusion 2, 3…) tant qu'elle n'est pas inscrite.

## 8. Ce que le protocole ne dit pas

- **« Validée » veut dire : ces paris battent la clôture Pinnacle, au seuil annoncé.** Ce n'est pas un gain garanti :
  le lien entre CLV et rendement est mesuré sur 40 jours.
- **« Non validée » ne veut pas dire « perd ».** Cela veut dire : un avantage d'au moins 2 % n'est pas démontré. Une
  stratégie dont la vraie CLV vaut 1 % échoue 9 fois sur 10, et 6 fois sur 10 si elle vaut 1,5 %.
- **18 stratégies échoueront sur la clôture, quel que soit leur résultat**, si rien ne change : Grok 1, 4, 5, 8 et
  10, Claude Défi 6 et les 12 règles Polymarket ont une clôture Pinnacle connue pour moins de la moitié de leurs
  paris (14 % à 43 %). Pour les juger, il faut enregistrer la clôture Pinnacle de chaque pari, quelle que soit sa
  référence (avantage-reel.md, décision 2). Ce n'est pas fait.
- **23 stratégies n'atteignent pas leur nombre en un an** au rythme actuel : ces 18, et Qwen, Grok 3, Gemini
  Défi 3, Claude Défi 3 et Pinnacle · 1.3–2 · ≥ 5 % · ≤ 12 h.
- **Les recommandées, les notes sur 100 et les avis d'analyste ne changent pas** : ils décrivent le passé avec leurs
  propres règles. Seul le protocole permet d'écrire qu'un avantage est prouvé.
- **La pause automatique** juge tout l'historique, pas seulement les paris du protocole. Elle ne peut produire qu'un
  échec, jamais un succès.

## Inscrire une nouvelle stratégie ou une nouvelle version

Avant son premier pari compté. La commande ajoute une ligne au registre (nombre de paris, empreinte) et donne le
scellé à ajouter dans `tests/test_protocole.py`. Sans `--debut`, le protocole commence à l'instant de la commande.

```bash
bash scripts/cloner_donnees.sh https://github.com/Matttgic/cotes-value donnees
```

```bash
python scripts/protocole.py --inscrire CLE --donnees donnees
```

## Vérifier et reproduire

Empreintes du code contre le registre (c'est aussi ce que fait le test) :

```bash
python scripts/protocole.py --verifier
```

État du suivi sur les données du jour, sans rien écrire :

```bash
python scripts/protocole.py --etat --donnees donnees
```

Tableau ci-dessous (les colonnes de rythme se recalculent sur les 14 jours d'avant le gel) :

```bash
python scripts/protocole.py --tableau --donnees donnees
```

Simulation du test (numpy, 40 secondes) :

```bash
python scripts/protocole.py --simuler --donnees donnees
```

Gel fait sur le commit `1d117bf` de `donnees` (15/11/2026, 04:54 UTC).

## Registre au gel : les 70 stratégies

« Écart-type par pari » : celui de la CLV Pinnacle, matchs groupés, avant le gel. « Mesurés par jour » et « Clôture
Pinnacle connue » : sur les 14 jours d'avant le gel (ou depuis le lancement, pour les stratégies plus récentes).
« Durée à ce rythme » : paris à atteindre / mesurés par jour. Début : 16/11/2026. Échéance : 16/11/2027.

| Stratégie | Version | Écart-type par pari | Paris mesurés à atteindre | Mi-parcours | Mesurés par jour | Clôture Pinnacle connue | Durée à ce rythme | Empreinte des règles |
|---|---|---|---|---|---|---|---|---|
| Claude | 1 | 12,4 % | 730 | 365 | 21,5 | 62 % | 34 jours | `fefddeb9814524e4` |
| ChatGPT v1 | 1 | 7,7 % | 300 | 150 | 1,7 | 80 % | 175 jours | `a03ab66599e6f5de` |
| Gemini Argon v1 | 2 | 9,2 % | 400 | 200 | 3,9 | 68 % | 102 jours | `0f90d918f78960fd` |
| JULES EDGE v1 | 1 | 9,2 % | 400 | 200 | 2,9 | 84 % | 137 jours | `33e01173cfa35260` |
| JULES EDGE v2 | 2-reconstruite | 10,0 % | 480 | 240 | 3,6 | 64 % | 132 jours | `b6f42c5704edc299` |
| Eden | 1 | 9,9 % | 460 | 230 | 8,8 | 76 % | 52 jours | `f653e21bd05f7b35` |
| M3 | 1 | 18,4 % | 1590 | 795 | 8,2 | 51 % | 194 jours | `e96606042d01c5eb` |
| Convergence ≥ 2 | 1 | 12,4 % | 720 | 360 | 10,6 | 62 % | 68 jours | `0740e3e5c8a8553c` |
| Claude 1/match · max 10/j | 1 | 8,5 % | 340 | 170 | 6,6 | 75 % | 52 jours | `bc423f9235430559` |
| Convergence ≥ 3 hors M3 | 1 | 8,7 % | 360 | 180 | 2,2 | 65 % | 163 jours | `3953687fd54d7c51` |
| M3 · Max 3/match | 1 | 13,9 % | 910 | 455 | 3,9 | 59 % | 236 jours | `3a26edd28ec51ce1` |
| Qwen | 1 | 12,0 % (par défaut) | 680 | 340 | 0,2 | 75 % | **plus d'un an** | `845165d812e0a0b1` |
| Cœur value | 1 | 9,0 % | 390 | 195 | 2,1 | 94 % | 188 jours | `807b162a0238f2b4` |
| Liquidité sûre | 1 | 10,0 % | 470 | 235 | 7,9 | 94 % | 59 jours | `ab2b45e4bc8f0e05` |
| Grok 1 · Polymarket mid | 1 | 12,0 % (par défaut) | 680 | 340 | 0,9 | 31 % | **plus d'un an** | `6bef4adb5256efb0` |
| Grok 2 · Pinnacle low | 2 | 10,8 % | 550 | 275 | 4,3 | 88 % | 128 jours | `f9a1e3568feff09b` |
| Grok 3 · Consensus mid | 2 | 12,0 % (par défaut) | 680 | 340 | 1,7 | 75 % | **plus d'un an** | `094bbca3f16067d2` |
| Grok 4 · Polymarket low-odds | 1 | 12,0 % (par défaut) | 680 | 340 | 1,1 | 34 % | **plus d'un an** | `7d1e30a2d3dfddaa` |
| Grok 5 · Multi-sharp low | 1 | 12,0 % (par défaut) | 680 | 340 | 1,5 | 38 % | **plus d'un an** | `2f8ce176be7db015` |
| Grok 6 · Pinnacle hors foot | 1 | 9,8 % | 450 | 225 | 5,6 | 89 % | 81 jours | `27a4a582333f94bf` |
| Grok 7 · Pinnacle cote moyenne | 1 | 11,4 % | 620 | 310 | 4,1 | 90 % | 152 jours | `367448e39c9edc23` |
| Grok 8 · Polymarket hors foot | 1 | 12,0 % (par défaut) | 680 | 340 | 0,4 | 17 % | **plus d'un an** | `0d40c1d2c82a9ef6` |
| Grok 9 · Valeur Pinnacle | 2 | 17,6 % | 1460 | 730 | 11,3 | 84 % | 129 jours | `4ecfcc814ac1bc06` |
| Grok 10 · Valeur Polymarket | 2 | 12,0 % (par défaut) | 680 | 340 | 1,1 | 20 % | **plus d'un an** | `5b9662b1ae1c5f57` |
| Conseil · bookmaker en retard (hors foot) | 1 | 10,1 % | 490 | 245 | 3,3 | 63 % | 149 jours | `c0286e6c6aa4c5aa` |
| Défi 1 · Écart fort, match proche | 1 | 18,0 % | 1530 | 765 | 5,4 | 60 % | 286 jours | `8181a1a1ec8ba9d6` |
| Défi 4 · Pinnacle très gros écart | 1 | 18,6 % | 1620 | 810 | 4,6 | 76 % | 349 jours | `630e8374baa526e4` |
| Gemini Défi 1 · Indoor & Glace | 1 | 19,0 % | 1680 | 840 | 6,9 | 62 % | 245 jours | `d6914526dce4e42a` |
| Gemini Défi 3 · Sniper principaux | 1 | 18,0 % | 1520 | 760 | 3,1 | 72 % | **plus d'un an** | `3ca04da76a4f15b3` |
| Gemini Défi 4 · Lignes asiatiques | 1 | 17,7 % | 1470 | 735 | 5,1 | 55 % | 286 jours | `6a3bb18b4f559eef` |
| Claude Défi 1 · Gros écart 12 h | 1 | 18,3 % | 1570 | 785 | 6,3 | 62 % | 250 jours | `a27b1d39af501f1e` |
| Claude Défi 2 · Handicaps | 1 | 12,0 % (par défaut) | 680 | 340 | 2,9 | 55 % | 235 jours | `806438114e4d43f3` |
| Claude Défi 3 · Books lents 2–12 h | 1 | 18,0 % | 1510 | 755 | 4,0 | 58 % | **plus d'un an** | `c9f569cbdb9af15f` |
| Claude Défi 4 · Gros écart hors Winamax | 1 | 12,0 % (par défaut) | 680 | 340 | 3,0 | 57 % | 228 jours | `004ae274cc8b8015` |
| Claude Défi 5 · Books lents, cotes courtes | 1 | 15,1 % | 1060 | 530 | 5,1 | 61 % | 207 jours | `a8ba8f80e6030fc9` |
| Claude Défi 6 · Polymarket tôt | 1 | 12,0 % (par défaut) | 680 | 340 | 1,7 | 20 % | **plus d'un an** | `93b5cb50a5708949` |
| Claude Fusion · Défi 4 + Défi 5 | 1 | 17,7 % | 1460 | 730 | 6,4 | 61 % | 230 jours | `fbe72604727f5ed5` |
| Claude Opus · Valeur solide | 1 | 14,6 % | 1000 | 500 | 8,3 | 64 % | 120 jours | `c00794c3423b4938` |
| Claude Opus · Favoris réguliers | 1 | 9,7 % | 440 | 220 | 5,6 | 69 % | 79 jours | `10a20a5157ed7248` |
| Claude Opus · Hors football | 1 | 12,3 % | 710 | 355 | 5,4 | 60 % | 131 jours | `ea902e0627a624d7` |
| Claude Opus · Handicaps | 1 | 12,0 % (par défaut) | 680 | 340 | 2,3 | 58 % | 295 jours | `1f557fd22ac3c085` |
| Claude Signal · Double avis | 1 | 12,0 % (par défaut) | 680 | 340 | 6,2 | 78 % | 109 jours | `2f422c4bdef2006b` |
| Claude Signal · Prix frais | 1 | 12,8 % | 770 | 385 | 35,0 | 79 % | 22 jours | `5a1676b6598d3f9f` |
| Claude · Méthode humaine | 1 | 12,0 % (par défaut) | 680 | 340 | 7,7 | 68 % | 88 jours | `884ef0974b575b68` |
| Claude · PMU régulier | 1 | 12,0 % (par défaut) | 680 | 340 | 18,6 | 66 % | 37 jours | `340eb1238e054604` |
| Fusion 1 · recommandées du 8/11 | 1 | 9,6 % | 440 | 220 | 11,4 | 72 % | 39 jours | `5ccf67c5ad1d254a` |
| Pinnacle · 1.3–2 · ≥ 2 % · ≤ 12 h | 1 | 8,0 % | 300 | 150 | 6,7 | 88 % | 45 jours | `9ac803cbd9992aea` |
| Pinnacle · 1.3–2 · ≥ 2 % · ≤ 36 h | 1 | 8,4 % | 330 | 165 | 10,8 | 90 % | 31 jours | `e97ed46e7d630bdd` |
| Pinnacle · 1.3–2 · ≥ 5 % · ≤ 12 h | 1 | 12,0 % (par défaut) | 680 | 340 | 1,6 | 85 % | **plus d'un an** | `c1608ab29d5754e6` |
| Pinnacle · 1.3–2 · ≥ 5 % · ≤ 36 h | 1 | 9,0 % | 380 | 190 | 3,1 | 91 % | 124 jours | `a16e563b612c54bf` |
| Pinnacle · 1.5–3 · ≥ 2 % · ≤ 12 h | 1 | 9,0 % | 380 | 190 | 7,6 | 86 % | 50 jours | `3d02fe8dbb09963c` |
| Pinnacle · 1.5–3 · ≥ 2 % · ≤ 36 h | 1 | 9,7 % | 450 | 225 | 12,3 | 87 % | 37 jours | `41d9240ae33267d4` |
| Pinnacle · 1.5–3 · ≥ 5 % · ≤ 12 h | 1 | 10,5 % | 520 | 260 | 2,5 | 88 % | 208 jours | `dd563d809f573d9c` |
| Pinnacle · 1.5–3 · ≥ 5 % · ≤ 36 h | 1 | 10,3 % | 500 | 250 | 4,6 | 93 % | 109 jours | `a59a3b29a98bbb2f` |
| Pinnacle · 2–5 · ≥ 2 % · ≤ 12 h | 1 | 9,4 % | 420 | 210 | 4,4 | 87 % | 96 jours | `553c9f905a1e6e56` |
| Pinnacle · 2–5 · ≥ 2 % · ≤ 36 h | 1 | 11,8 % | 650 | 325 | 7,8 | 85 % | 83 jours | `1eb6af559d9cf4da` |
| Pinnacle · 2–5 · ≥ 5 % · ≤ 12 h | 1 | 11,0 % | 570 | 285 | 1,7 | 89 % | 332 jours | `c222c6b4b9bb557c` |
| Pinnacle · 2–5 · ≥ 5 % · ≤ 36 h | 1 | 11,1 % | 580 | 290 | 3,3 | 90 % | 177 jours | `0eaab9c33f60609d` |
| Polymarket · 1.3–2 · ≥ 2 % · ≤ 12 h | 1 | 12,0 % (par défaut) | 680 | 340 | 0,7 | 34 % | **plus d'un an** | `6e7e1bd0cebadcab` |
| Polymarket · 1.3–2 · ≥ 2 % · ≤ 36 h | 1 | 12,0 % (par défaut) | 680 | 340 | 1,4 | 38 % | **plus d'un an** | `d22bae8e4ced404d` |
| Polymarket · 1.3–2 · ≥ 5 % · ≤ 12 h | 1 | 12,0 % (par défaut) | 680 | 340 | 0,1 | 14 % | **plus d'un an** | `2c8dbae0942293e7` |
| Polymarket · 1.3–2 · ≥ 5 % · ≤ 36 h | 1 | 12,0 % (par défaut) | 680 | 340 | 0,4 | 36 % | **plus d'un an** | `23b33d6139fc176e` |
| Polymarket · 1.5–3 · ≥ 2 % · ≤ 12 h | 1 | 12,0 % (par défaut) | 680 | 340 | 0,9 | 30 % | **plus d'un an** | `6cf591558831aac9` |
| Polymarket · 1.5–3 · ≥ 2 % · ≤ 36 h | 1 | 12,0 % (par défaut) | 680 | 340 | 1,6 | 31 % | **plus d'un an** | `50b0078f37d1d288` |
| Polymarket · 1.5–3 · ≥ 5 % · ≤ 12 h | 1 | 12,0 % (par défaut) | 680 | 340 | 0,2 | 25 % | **plus d'un an** | `23e881ee10f5c60c` |
| Polymarket · 1.5–3 · ≥ 5 % · ≤ 36 h | 1 | 12,0 % (par défaut) | 680 | 340 | 0,4 | 29 % | **plus d'un an** | `3afbce6818f451f8` |
| Polymarket · 2–5 · ≥ 2 % · ≤ 12 h | 1 | 12,0 % (par défaut) | 680 | 340 | 0,7 | 24 % | **plus d'un an** | `327c9496b7d0c2eb` |
| Polymarket · 2–5 · ≥ 2 % · ≤ 36 h | 1 | 12,0 % (par défaut) | 680 | 340 | 1,1 | 22 % | **plus d'un an** | `4469cb9802fac9bf` |
| Polymarket · 2–5 · ≥ 5 % · ≤ 12 h | 1 | 12,0 % (par défaut) | 680 | 340 | 0,4 | 43 % | **plus d'un an** | `69c3b3d62a0cb8c1` |
| Polymarket · 2–5 · ≥ 5 % · ≤ 36 h | 1 | 12,0 % (par défaut) | 680 | 340 | 0,6 | 35 % | **plus d'un an** | `63a24775dc46fcc2` |
