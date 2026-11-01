# Stratégies Claude Défi

Famille proposée par **Claude** le 1er novembre 2026, sur le modèle de la [famille Défi](strategie-defi.md) et des
[Gemini Défi](strategie-gemini-defi.md). Elle est distincte des Grok, des Défi, des Gemini Défi et de la stratégie
« Claude (rejeu) » : module `cotes/strategie_claude_defi.py`, clés `claude_defi_1`, `claude_defi_2` et
`claude_defi_3`, libellé « Claude Défi » sur le site. Aucune stratégie figée existante n'est modifiée.

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
