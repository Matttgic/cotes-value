# Optimisée 19/11 (et sa variante + Polymarket)

Code : `cotes/strategie_optimisee.py`. Suivie dès le **19/11/2026 à 18 h (Paris)**, sans rejeu, inscrite au
protocole (`docs/protocole.md`). Origine : [analyse-paris-19-11.md](analyse-paris-19-11.md).

## Règle

**Optimisée 19/11** : la stratégie figée du 14/11 ([strategie-mises.md](strategie-mises.md)), moins deux segments
sans CLV.

- Toutes les références, cote ≤ 5, écart annoncé ≥ 3 %.
- Tous les bookmakers sauf Winamax et OlyBet.
- Ni volley, ni total au basket (le total d'une équipe reste).
- Détecté au plus 24 h avant le début, match pas commencé, équipes non inversées.
- Une mise par cote française : la première détection qui passe la règle.

**Optimisée 19/11 + Polymarket** : même règle, référence Pinnacle seulement, et Polymarket voit aussi un écart
≥ 5 % (`ecart_polymarket`). Piste à confirmer : 231 paris et 49 clôtures mesurées au 19/11. À juger vers le 5/12.

## Pourquoi

Sur 4 589 paris réglés à cote ≤ 5 (05/10 au 19/11) :

| Ensemble | Paris | CLV Pinnacle [IC 95 %] |
|---|---|---|
| Règle figée du 14/11, depuis le 15/11 (paris neufs) | 126 | +6,1 % [+1,5 ; +12,8] |
| Paris qu'elle écarte | 2 942 | −0,2 % [−0,8 ; +0,5] |
| Règle figée sans volley | 1 575 | +4,0 % [+3,0 ; +5,1] |
| Confirmation Polymarket ≥ 5 % | 231 | +9,3 % [+4,9 ; +13,9] |

Volley : ROI −15,8 % [−27 ; −3], négatif sur les trois périodes. Total au basket : CLV −1,5 %.

## Mise conseillée dans les notifications

Depuis le 19/11, la mise des notifications (Pushover, ntfy, récapitulatif « Encore jouables ») est un **Kelly au 1/8
sur l'avantage « compté »** de l'étude du 14/11 (`mise_conseillee`), avec un garde-fou à 5 % de la bankroll. Le même
jour, le 1/16 (trop petit en euros) puis le ¼ plafonné à 2 % (trop risqué) ont été essayés et remplacés.

    mise = bankroll de mise × 1/8 × avantage compté / (cote − 1), au plus 5 % de la bankroll de mise

| Écart annoncé | < 3 % | 3 % | 4 % | 5 % | 7 % | ≥ 10 % |
|---|---|---|---|---|---|---|
| Avantage compté | 0 | +0,18 % | +1,01 % | +2,19 % | +4,64 % | +8,15 % |

Entre deux points, interpolation linéaire. Exemples pour 1 000 € : cote 2,00 à 4 %, 1,26 € ; à 7 %, 5,80 € ; cote
1,50 à 10 %, 20,38 €. La mise affichée est arrondie à l'euro supérieur, 1 € au moins.

**Pourquoi 1/8 sans plafond serré.** Simulation sur 3 mois (2 894 paris tirés par match parmi les 1 447 gardés,
2 000 tirages, 1 000 € réels, bankroll mise à jour pari après pari) :

| Mise | Gain médian | Perdre la moitié, avantage réel | Perdre la moitié, sans avantage |
|---|---|---|---|
| Kelly ¼, plafond 2 % | +1 738 € | 10 % | 43 % |
| Kelly ¼, sans plafond | +2 236 € | 10 % | 41 % |
| Bankroll déclarée × 2 (Kelly ½) | +5 351 € | 74 % | 96 % |
| Bankroll déclarée × 3 | +9 659 € | 99 % | 100 % |
| **Kelly 1/8** | +862 € | **0,1 %** | **3 %** |

« Perdre la moitié » : la bankroll passe un jour sous la moitié de son plus haut. Relever le plafond ne coûte rien en
risque ; gonfler la bankroll déclarée mène à la ruine. Plusieurs paris d'un même match se cumulent, d'où des baisses
plus fortes que Kelly ne le laisse croire. Script : `sim_mises.py` (hors dépôt), mêmes données que l'analyse du 19/11.

## Bankroll automatique

`cotes/alertes/bankroll.py`, état dans `bankroll.json` (branche « donnees »). Le système ne voit pas les comptes chez
les bookmakers : il suppose que **chaque alerte Pushover envoyée est jouée à la mise affichée**.

1. Départ : `PUSHOVER_BANKROLL` (variable GitHub, 1 000 € par défaut).
2. Chaque alerte envoyée est notée avec sa mise ; quand le pari est réglé, son gain (ramené à cette mise) s'ajoute à
   la bankroll calculée. Une alerte dont le pari reste introuvable 10 jours est retirée sans gain.
3. **Bankroll de mise** (celle des mises) : elle baisse tout de suite quand la bankroll calculée passe 10 % sous elle,
   et monte par paliers de +20 % (1 000 → 1 200 → 1 440…).
4. **Recaler** sur la réalité : changer `PUSHOVER_BANKROLL` (le calcul repart de ce chiffre). À faire si tu ne joues
   pas une alerte, ou à une autre cote. `PUSHOVER_BANKROLL_AUTO=non` coupe le calcul.

Ne change pas : les bilans du site gardent leur mode Kelly ¼ sur l'écart brut (`simulation.mise_kelly`), déjà publié.
La mise ne retire pas ce qui est déjà misé sur le même match : à faire à la main si plusieurs paris tombent sur un
match.

## Règle appliquée à tout le site (comme le plafond de cote du 11/11)

Depuis le 19/11/2026, la même règle (`simulation.motif_hors_regle`) s'applique **à la prise et à tous les bilans** :

- `placer` ne prend plus de pari hors règle : cote > 5, écart < 3 %, Winamax, OlyBet, volley, total au basket, plus
  de 24 h avant le match. Une cote vue à plus de 24 h est prise à sa première détection dans les 24 h, si elle est
  encore là.
- Le site retire les anciens paris hors règle de tous les bilans (Bilan, Paris, stratégies), sans les supprimer des
  données : ils sont dans `hors_plafond.json`, avec leur nombre par motif sous le Bilan.

Effet sur les paris uniques réglés au 19/11 : **1 447 gardés, +519 €, ROI +3,6 %** ; 4 112 exclus, −3 563 €,
ROI −8,7 %. Motifs, sur tous les paris enregistrés (écart < 3 % : 2 501 ; cote > 5 : 1 095 ; plus de 24 h : 609 ; Winamax : 428 ; OlyBet : 212 ; total au
basket : 158 ; volley : 75 ; un pari peut avoir plusieurs motifs, seul le premier est compté).

Conséquence : les stratégies qui prenaient ces paris les perdent aussi, dans leurs bilans et à l'avenir (règles à
écart ≥ 2 %, Fusion 1, Liquidité sûre, bookmakers Winamax…), comme les cotes > 5 le 11/11. Le protocole
(`scripts/protocole.py`) garde sa propre mesure, figée le 15/11. La stratégie « Optimisée 19/11 » fait désormais
presque doublon avec le Bilan ; elle reste suivie (inscrite au protocole).

## Limites

Choisie sur l'historique : seul le suivi depuis le 19/11 compte. Les intervalles sont larges (un mois et demi de
données). Rejeu indicatif du 15/11 au 19/11 : 121 paris pour la règle, 11 pour la variante + Polymarket.
