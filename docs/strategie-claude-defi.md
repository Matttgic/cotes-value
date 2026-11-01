# Stratégies Claude Défi

Famille proposée par **Claude** le 1er novembre 2026, sur le modèle de la [famille Défi](strategie-defi.md) et des
[Gemini Défi](strategie-gemini-defi.md). Elle est distincte des Grok, des Défi, des Gemini Défi et de la stratégie
« Claude (rejeu) » : module `cotes/strategie_claude_defi.py`, clés `claude_defi_1` à `claude_defi_5` et
`claude_fusion`, libellés « Claude Défi » et « Claude Fusion » sur le site. Aucune stratégie figée existante n'est modifiée.

Chaque stratégie :

- est figée au lancement (`@figer_selecteur`) : une prise déjà décidée ne reçoit jamais la clé après coup ;
- n'est suivie qu'à partir de sa mise en service, le **2 novembre 2026 à 01:00 UTC** (02:00 à Paris), sans rejeu
  sur l'historique ;
- simule une mise fictive de **10 €** (le Kelly du site reste le même affichage que pour les autres comparateurs) ;
- ne lit jamais le résultat, le gain, la CLV ni la cote de clôture pour choisir ses paris.

## Tronc commun

- Référence Pinnacle, Betfair ou Polymarket (jamais Smarkets, Kalshi, Matchbook, le Consensus ni un book français).
- `equipes_inversees` différent de `True` : `False` et vide sont acceptés.
- Référence lue depuis **180 s au plus** (`detecte − lu_reference`, signé : une référence relue quelques secondes
  après la cote française passe).
- Aucun score de correspondance minimal : sur la construction, les associations à 0,64–0,71 (acceptées par le
  matcher seulement à heure identique) avaient la même CLV que les autres.
- Une seule mise par cote française (`cle_cote_fr` = match du bookmaker | marché | période | ligne | issue | joueur) :
  la première détection qui passe la règle. Une détection refusée ne consomme pas la cote. Deux books français sur
  le même choix restent deux mises ; deux références sur la même cote n'en font qu'une.
- Aucun plafond par match ni par jour. Bornes incluses, sauf le délai : `0 < délai ≤ 720 min`.

## Règles exactes

| Stratégie | Périmètre | Cote française | Écart | Délai (min) |
|---|---|---|---|---|
| **Claude Défi 1 · Gros écart 12 h** | tous sports et marchés | 1,30 – 10 | 6 – 30 % | 0 < délai ≤ 720 |
| **Claude Défi 2 · Handicaps** | `HANDICAP`, `HANDICAP_3`, `SETS_HANDICAP`, `JEUX_HANDICAP` | 1,30 – 4 | 5 – 30 % | 0 < délai ≤ 720 |
| **Claude Défi 3 · Books lents 2–12 h** | Betclic et PMU seulement | 1,30 – 10 | 5 – 30 % | 120 < délai ≤ 720 |

Logique de marché :

- **Défi 1** : un écart d'au moins 6 % face à un book sharp, à moins de 12 h du match, signale une cote française en
  retard, que le book corrige ensuite vers la cote sharp avant la clôture. Au-delà de 12 h, la cote sharp elle-même
  bouge encore trop.
- **Défi 2** : les books français recopient les lignes de handicap avec retard quand la ligne sharp bouge.
- **Défi 3** : hypothèse que Betclic et PMU mettent leurs cotes à jour plus lentement que Winamax et Unibet, entre
  2 h et 12 h du match. **Non confirmée en validation** (voir ci-dessous).

## Rejeu sur l'historique (optimiste)

Export de la recherche Défi : 2 845 détections réglées, sharp seulement, du 5 au 26 octobre 2026
(`tests/fixtures/gemini_defi_rejeu.csv`, complété par la CLV, le statut et le gain de `paris.json`).
Découpe chronologique : construction avant le 18/10/2026 à 02:29:01 UTC, validation après.
Les règles ont été choisies sur la construction seule, écrites et figées, puis la validation a été évaluée **une
seule fois**, sans retouche. CLV de clôture (lecture ≤ 30 min avant le coup d'envoi), moyenne sur les paris dont la
CLV est mesurée ; intervalle à 95 % par **bootstrap regroupé par match** (`evenement`, 4 000 tirages,
graine 20261101). ROI = somme des gains / (10 € × N). Réussite = gagnés / (gagnés + perdus).

| Stratégie | N constr. | avec CLV | CLV [IC 95 %] | ROI | Réussite | N valid. | avec CLV | CLV [IC 95 %] | ROI | Réussite |
|---|---|---|---|---|---|---|---|---|---|---|
| Claude Défi 1 | 161 | 124 | +9,44 % [+6,06 ; +13,15] | +16,5 % | 52,5 % | 63 | 48 | +9,20 % [+5,18 ; +13,26] | −14,9 % | 33,3 % |
| Claude Défi 2 | 90 | 69 | +8,45 % [+5,45 ; +11,47] | +25,0 % | 62,9 % | 18 | 16 | +13,55 % [+3,04 ; +21,04] | −68,3 % | 12,5 % |
| Claude Défi 3 | 76 | 58 | +12,40 % [+6,94 ; +16,89] | +34,8 % | 59,2 % | 32 | 22 | +5,04 % [−3,75 ; +13,52] | −8,9 % | 41,9 % |

Le test `tests/test_strategie_claude_defi.py` rejoue les trois sélecteurs du code sur l'export et retrouve ces N.

La quatrième règle étudiée (« Dernière demi-heure » : écart 4–30 %, délai ≤ 30 min, cote 1,30–10 ; validation
26 paris, CLV +7,76 % [+5,73 ; +9,61]) n'est pas suivie.

## Avertissements

- **Claude Défi 3 n'a pas tenu en validation** : sa CLV passe de +12,4 % à +5,0 %, avec un intervalle qui traverse
  zéro. Elle est suivie à la demande, pour vérifier l'hypothèse des books lents sur des données neuves.
- **Claude Défi 2 n'a que 18 paris de validation** (13 matchs) : sa CLV de +13,6 % est très incertaine.
- **Le ROI de validation est négatif pour les trois**, comme pour les Gemini Défi : sur 18 à 63 paris en 8 jours,
  il est très bruité. Seule la CLV est interprétable sur cet horizon.
- Le flux Betfair s'est arrêté après le 18/10 : la validation ne contient que Pinnacle et Polymarket.
- Le rejeu reste optimiste : les seuils ont été choisis après coup sur la construction. Seul le suivi à partir du
  2/11/2026 à 01:00 UTC compte.

## Deuxième salve : Claude Défi 4, Claude Défi 5 et Claude Fusion

Ajoutées le 1er novembre 2026 au soir, même lancement (**2/11/2026 01:00 UTC**), mêmes protections (gel, une mise
par cote française, 10 € fictifs, pas de rejeu, aucune lecture du résultat). Elles acceptent aussi le **Consensus**
(moyenne Pinnacle + Polymarket) comme référence. En amont, le garde-fou « cote Pinnacle figée » (`cotes/mouvement.py`)
écarte déjà les opportunités dont la cote Pinnacle n'a pas bougé depuis 10 minutes.

| Stratégie | Books | Cote française | Écart | Délai (min) |
|---|---|---|---|---|
| **Claude Défi 4 · Gros écart hors Winamax** | Betclic, PMU, Unibet, OlyBet, NetBet | 1,30 – 30 | 8 – 30 % | 0 < délai ≤ 720 |
| **Claude Défi 5 · Books lents, cotes courtes** | Betclic, PMU | 1,30 – 3 | 6 – 30 % | 0 < délai ≤ 1 440 |
| **Claude Fusion · Défi 4 + Défi 5** | passe Défi 4 **ou** Défi 5 | — | — | — |

Tronc commun : Pinnacle, Betfair, Polymarket ou Consensus · référence lue depuis ≤ 180 s · équipes non inversées ·
tous sports et marchés · pas de score minimal ni de plafond.

Logique de marché :

- **Défi 4** : un écart d'au moins 8 % à moins de 12 h du match est une cote française en retard. Winamax est exclu :
  c'est le book français qui suit les sharps le plus vite, ses écarts sont plus souvent un retard de notre référence
  qu'une vraie erreur (CLV −12,5 % du 26 au 31/10 pour Winamax à écart ≥ 6 %).
- **Défi 5** : Betclic et PMU mettent leurs cotes à jour plus lentement ; sur des cotes courtes (≤ 3), le ROI suit la
  CLV avec peu de variance.
- **Fusion** : réunit les deux sans doubler une mise sur la même cote.

### Méthode

Tout l'historique (`paris.json`, 3 851 paris réglés du 5/10 au 31/10, l'archive `archive-donnees-2026-10-30` ne
contenant aucun pari de plus) découpé en trois périodes : **P1** jusqu'au 18/10 02:29 UTC, **P2** jusqu'au 26/10 16:15,
**P3** ensuite. Une grille de règles simples (référence, books, écart, délai, cote ; 1 920 combinaisons) a été classée
par **la plus faible CLV entre P1 et P2** (au moins 25 CLV mesurées dans chacune), puis P3 regardée. CLV de clôture
(≤ 30 min avant le coup d'envoi), intervalle à 95 % par bootstrap regroupé par match (3 000 tirages, graine 11).
Chiffres obtenus en rejouant les sélecteurs du code sur `paris.json` (`selection_claude_defi`, depuis le 5/10).

| Stratégie | Période | N | avec CLV | CLV [IC 95 %] | Gain (10 €) | ROI [IC 95 %] | Réussite |
|---|---|---|---|---|---|---|---|
| Claude Défi 4 | P1 | 80 | 55 | +11,23 % [+7,10 ; +16,16] | +96,6 € | +12,1 % [−28 ; +53] | 46 % |
| | P2 | 43 | 32 | +11,39 % [+6,88 ; +15,66] | −185,5 € | −43,1 % [−71 ; −12] | 20 % |
| | P3 | 44 | 36 | +10,63 % [+6,74 ; +14,15] | +120,6 € | +27,4 % [−55 ; +168] | 33 % |
| | **total** | **167** | 123 | **+11,10 % [+8,58 ; +13,67]** | **+31,7 €** | +1,9 % [−30 ; +41] | 37 % |
| Claude Défi 5 | P1 | 99 | 76 | +9,45 % [+6,53 ; +12,75] | +356,1 € | +36,0 % [+8 ; +61] | 65 % |
| | P2 | 43 | 33 | +9,45 % [+4,33 ; +14,46] | −66,9 € | −15,6 % [−49 ; +25] | 38 % |
| | P3 | 47 | 42 | +6,29 % [+3,20 ; +8,44] | +186,8 € | +39,7 % [+5 ; +73] | 65 % |
| | **total** | **189** | 151 | **+8,57 % [+6,49 ; +10,75]** | **+476,0 €** | **+25,2 % [+5 ; +44]** | 60 % |
| Claude Fusion | P1 | 143 | 104 | +9,97 % [+6,83 ; +13,52] | +248,1 € | +17,3 % [−10 ; +45] | 52 % |
| | P2 | 65 | 49 | +9,64 % [+5,78 ; +13,43] | −172,4 € | −26,5 % [−53 ; +3] | 31 % |
| | P3 | 69 | 58 | +7,92 % [+4,91 ; +10,73] | +248,9 € | +36,1 % [−20 ; +129] | 48 % |
| | **total** | **277** | 211 | **+9,33 % [+7,36 ; +11,37]** | **+324,6 €** | +11,7 % [−10 ; +40] | 47 % |

Sur l'export du défi (`tests/fixtures/gemini_defi_rejeu.csv`), les sélecteurs retrouvent les N de P1 et P2 :
Défi 4 80 / 43, Défi 5 99 / 43, Fusion 143 / 65 (`tests/test_strategie_claude_defi.py`).

### Avertissements (deuxième salve)

- **Rejeu optimiste** : les règles ont été choisies sur P1 et P2, et P3 avait déjà été regardée pour d'autres règles
  le même jour. Aucune période n'est vraiment vierge : seul le suivi à partir du 2/11/2026 compte.
- **Le ROI reste du bruit à cet horizon** : à CLV quasi constante (+11 %), Défi 4 gagne +12 % en P1, perd −43 % en
  P2, regagne +27 % en P3. Défi 5 est la seule règle dont l'intervalle du ROI reste au-dessus de zéro sur tout
  l'historique, mais 189 paris ne suffisent pas à garantir un ROI futur.
- **Plusieurs paris d'un même match** sont corrélés ; l'intervalle regroupé par match en tient compte, pas le gain.
- **Cotes Pinnacle figées** : avant le 25/10, le mouvement n'était pas mesuré. Une partie des paris historiques
  aurait été écartée par le garde-fou ; la CLV de ces paris est elle-même mesurée sur le même flux.
