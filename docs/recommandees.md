# Stratégies recommandées

En haut de la page Stratégies, deux blocs distincts :

- **Recommandées** : une liste **stable** de stratégies existantes (au plus trois), celles qui battent le plus
  sûrement la clôture Pinnacle. Chaque carte porte le nom de la stratégie et sa date d'entrée, avec son résultat
  depuis cette date. La liste n'est revue que tous les 7 jours.
- **Fusion 1** : une stratégie à part, qui réunit les trois recommandées du 8/11/2026 avec un seul pari par match.
  Ses membres sont figés : elle ne suit pas la liste des recommandées.

Code : `cotes/recommandations.py` (critères et révision), `cotes/strategie_recommandee.py` (Fusion 1),
`scripts/site_web.py` (calcul à chaque construction du site), `web/modele.html` (`rendreRecommandees`). État de la
liste : `recommandees.json` dans la branche `donnees`.

## Exemple pour lire les deux blocs

Le 8/11, les recommandées sont Polymarket 1,5–3, Pinnacle 1,3–2 et Polymarket 2–5 ; Fusion 1 les réunit.
Si, à la révision du 15/11, Grok 8 dépasse Pinnacle 1,3–2 d'au moins 0,5 point (borne basse de la CLV Pinnacle) :
- la liste devient Polymarket 1,5–3, Polymarket 2–5, Grok 8 (« recommandée depuis le 15/11 ») ; Pinnacle 1,3–2
  passe dans « Anciennes recommandées » avec ses dates et la raison ;
- Fusion 1 ne change pas : elle garde Pinnacle 1,3–2, marqué « plus recommandée depuis le 15/11 » ;
- **Fusion 2 est créée automatiquement** le 15/11 avec Polymarket 1,5–3, Polymarket 2–5 et Grok 8, suivie à
  partir de l'instant de la révision. Fusion 1 et Fusion 2 continuent chacune leur suivi.

## Révision tous les 7 jours

Entre deux révisions, la liste ne bouge pas, même si les notes changent. À une révision :

1. une recommandée **sort** seulement si elle ne remplit plus un des critères ci-dessous ;
2. une place libre est prise par la meilleure candidate (note la plus haute) qui n'est pas un doublon ;
3. si les trois places sont prises, une candidate **remplace** la plus faible seulement si sa note la dépasse
   d'au moins 5 points.

Chaque sortie est gardée (dates, raison, résultat pendant la période recommandée).

## Fusions automatiques

Après chaque révision, si la liste des recommandées n'est plus celle de la dernière fusion (et qu'il reste au moins
deux recommandées), une nouvelle fusion est créée : Fusion 2, puis Fusion 3… Même règle que Fusion 1 : la réunion des
recommandées du jour, un seul pari par match (la première prise d'un des membres), membres figés, suivie depuis sa
création, sans rejeu. Les fusions ne sont jamais candidates aux recommandées.

- Les fusions créées sont notées dans `recommandees.json` (« fusions ») ; vingt places sont prévues (Fusion 2 à
  Fusion 21, `FUSIONS_AUTO` dans `cotes/strategie_recommandee.py`). Une place libre n'apparaît nulle part.
- Une fusion active apparaît dans la page Stratégies (bloc « Fusions », et parmi les comparateurs) et peut être
  cochée dans Notifications.
- Ses prises sont recalculées à partir des prises figées de ses membres (`cotes/decisions.py`) : elles ne dépendent
  d'aucun résultat.

## Critères (version 2, depuis le 16/11/2026)

Sur le suivi depuis le lancement de chaque stratégie (mise fixe, cote ≤ plafond), mesuré comme une ligne de la page
Décision (`cotes/decision.py` › `mesurer` : CLV contre la clôture Pinnacle sans marge, le match comme unité de hasard,
Student), une stratégie est **candidate** si :

| Critère | Seuil | Pourquoi |
|---|---|---|
| Matchs réglés | ≥ 50 | Assez de matchs pour mesurer |
| Clôture Pinnacle connue | ≥ 50 % des paris réglés, ≥ 30 mesures | Sinon la CLV ne décrit qu'une partie des paris |
| CLV Pinnacle positive | p de Holm < 5 %, sur toutes les stratégies testées | La CLV prédit le rendement à cote ≤ 5 (avantage-reel.md, point 6) ; la correction empêche le nombre de stratégies comparées de fabriquer des gagnantes |
| Rendement pas nettement sous la CLV | écart (rendement − CLV) : borne haute à 95 % ≥ 0 | Écarte les stratégies qui battent la clôture mais perdent quand même (Claude Défi 5) |
| ROI | > 0 | Garde-fou, comme « jouer » dans la page Décision |

Classement : **borne basse à 95 % de la CLV Pinnacle** (le cas prudent). Une candidate remplace la plus faible si sa
borne basse la dépasse d'au moins 0,5 point. Une candidate qui partage plus de 60 % de ses paris avec une recommandée
est écartée comme doublon (paris communs / paris de la plus petite des deux). Trois recommandées au plus. Les bases du
Bilan (tous les paris d'une référence) et les fusions ne sont pas candidates. Mesures publiées pour chaque stratégie
dans `stats.preuve` (`cotes/recommandations.py` › `mesurer_preuves`).

**Pourquoi la version 1 a été remplacée.** Elle demandait une borne basse du ROI à 80 % positive, sans correction,
et classait par note /100 (fondée sur le ROI). Avec une centaine de lignes comparées, environ une stratégie sans
avantage sur dix passait par hasard ; à 50 matchs, le ROI varie de ±25 points. Le 13/11, la meilleure recommandée
(Polymarket 2–5) avait une p corrigée de 0,50. La version 2 juge sur la CLV, mesure qui tranche bien plus vite.

**Changement de version** : il déclenche une révision immédiate (`CRITERES` dans `cotes/recommandations.py`). Les
recommandées qui ne remplissent pas les nouveaux critères sortent, avec la raison « (critères version 2) ».

**Différence avec le protocole de validation** (docs/protocole.md) : les recommandées sont relues chaque semaine sur
tout l'historique, y compris les paris qui ont servi à les choisir ; c'est une sélection, pas une preuve. Le protocole
fixe tout à l'avance, ne compte que les paris d'après le 16/11/2026, demande un seuil bien plus strict (p < 0,025 %)
et rend un verdict définitif. Seul le protocole peut dire qu'un avantage est prouvé.

### Révision du 16/11/2026 (passage à la version 2)

Sur les données du 16/11 à 0 h 45 (Paris), 50 stratégies testées :

| Stratégie | Matchs | Clôture connue | CLV Pinnacle [IC 95 %] | p corrigée | ROI |
|---|---|---|---|---|---|
| Défi 4 · Pinnacle très gros écart | 73 | 75 % | +9,51 % [+5,56 ; +13,46] | 0,0003 | +13,0 % |
| Pinnacle · 2–5 · ≥ 5 % · ≤ 36 h | 140 | 79 % | +4,55 % [+2,41 ; +6,69] | 0,0012 | +13,4 % |
| Pinnacle · 1,5–3 · ≥ 5 % · ≤ 36 h | 166 | 83 % | +4,16 % [+2,34 ; +5,98] | 0,0003 | +9,8 % |

Sorties : Polymarket 1,5–3 et Polymarket 2–5 (clôture Pinnacle connue pour moins de la moitié des paris),
Pinnacle 1,3–2 · ≥ 2 % (CLV non prouvée après correction). Fusion 2 est créée avec les trois entrantes. Écartée :
Claude Défi 5 (CLV +7,8 % mais ROI −35,9 % : rendement nettement sous la CLV).

## Première liste (8/11/2026)

| | Stratégie | Matchs | ROI | Borne basse | ROI sans les meilleurs | Meilleur match | CLV par match | Note |
|---|---|---|---|---|---|---|---|---|
| 1 | Polymarket · cotes 1,5–3 · écart ≥ 2 % · ≤ 36 h | 109 | +22,3 % | +8,8 % | +12,5 % (6 retirés) | 2,9 % | +2,1 % | 88 |
| 2 | Pinnacle · cotes 1,3–2 · écart ≥ 2 % · ≤ 36 h | 284 | +8,9 % | +2,7 % | +4,0 % (15 retirés) | 0,8 % | +0,9 % | 85 |
| 3 | Polymarket · cotes 2–5 · écart ≥ 2 % · ≤ 36 h | 142 | +28,9 % | +12,6 % | +11,2 % (8 retirés) | 3,3 % | +1,3 % | 84 |

Écartées comme doublons : Pinnacle · 1,5–3 (71 % de paris communs avec la n° 2) et Polymarket · 1,3–2 (67 % avec la
n° 1). Aucune stratégie de la famille des comparateurs (Claude, Grok, Défi…) ne remplit tous les critères ce
jour-là : Grok 8 en est la plus proche, mais n'a que 40 matchs réglés.

## Fusion 1

Nom sur le site : « Fusion 1 · recommandées du 8/11 ». Réunion des trois recommandées du 8/11/2026, **membres
figés** : un pari est pris quand l'une des trois le prend,
si le match n'a encore aucun pari de la fusion (la première prise l'emporte ; à la même seconde, le plus gros
écart). Équivaut à : Pinnacle 1,3–2 ou Polymarket 1,5–5, écart ≥ 2 %, ≤ 36 h avant le match, un pari par match.

- Pourquoi une fusion : la règle Pinnacle et les règles Polymarket ne partagent aucun pari (les deux règles
  Polymarket se recoupent sur les cotes 2–3 : 59 % des paris de la plus petite). Réunies, elles donnent plus de
  matchs, donc un résultat moins dépendant du hasard, et le « un pari par match » supprime la concentration sur un
  match.
- Suivi : depuis le 8/11/2026 à 9 h (Paris). Décisions figées à la prise comme les autres stratégies
  (`cotes/decisions.py`) ; la fusion apparaît aussi parmi les comparateurs et peut être cochée dans Notifications.
- Rejeu indicatif depuis le 14/10 : 430 matchs, ROI +15,2 %, +651,50 €, note 87/100. **Optimiste** : les membres
  ont été choisis après avoir vu ces résultats. Seul le suivi depuis le 8/11 compte.
- Les membres ne changent pas quand la liste des recommandées change : la page indique pour chacun s'il est encore
  recommandé. Une nouvelle combinaison serait Fusion 2, avec sa propre date de départ.

## Limites

Recommandation descriptive, sur un passé court (environ 3 semaines et demie de suivi) : aucun gain futur garanti.
Les trois règles viennent d'une famille de 24 règles du laboratoire ; choisir les meilleures d'une famille
surestime leur avenir (sélection après coup), d'où les critères prudents ci-dessus et la fusion suivie
uniquement en prospectif.
