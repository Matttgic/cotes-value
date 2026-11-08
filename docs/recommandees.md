# Stratégies recommandées

En haut de la page Stratégies, deux blocs distincts :

- **Recommandées** : une liste **stable** de stratégies existantes (au plus trois). Chaque carte porte le nom de la
  stratégie et sa date d'entrée (« Recommandée depuis le 8/11 »), avec son résultat depuis cette date. La liste
  n'est revue que tous les 7 jours.
- **Fusion 1** : une stratégie à part, qui réunit les trois recommandées du 8/11/2026 avec un seul pari par match.
  Ses membres sont figés : elle ne suit pas la liste des recommandées.

Code : `cotes/recommandations.py` (critères et révision), `cotes/strategie_recommandee.py` (Fusion 1),
`scripts/site_web.py` (calcul à chaque construction du site), `web/modele.html` (`rendreRecommandees`). État de la
liste : `recommandees.json` dans la branche `donnees`.

## Exemple pour lire les deux blocs

Le 8/11, les recommandées sont Polymarket 1,5–3, Pinnacle 1,3–2 et Polymarket 2–5 ; Fusion 1 les réunit.
Si, à la révision du 15/11, Grok 8 dépasse Pinnacle 1,3–2 d'au moins 5 points :
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

## Critères

Sur le suivi depuis le lancement de chaque stratégie, en mise fixe, une stratégie est **candidate** si :

| Critère | Seuil | Pourquoi |
|---|---|---|
| Matchs réglés | ≥ 50 (note non provisoire) | Assez de matchs pour que le hasard pèse peu |
| Borne basse à 80 % du ROI, par match | > 0 | Rentable même dans un scénario prudent |
| ROI sans les meilleurs matchs (5 %, au moins un) | > 0 | Le gain ne tient pas à quelques matchs chanceux |
| Part du meilleur match dans les gains | ≤ 25 % | Pas de dépendance à un seul match |
| CLV moyenne par match | > 0 | Les cotes prises battent la clôture : avantage réel, pas seulement de la chance |

Les candidates sont classées par note /100 (docs/notation-strategies.md, version 2). Une candidate qui partage plus
de 60 % de ses paris avec une recommandée est écartée comme doublon (paris communs / paris de la plus petite des
deux). Trois recommandées au plus. Les bases du Bilan (tous les paris d'une référence) ne sont pas candidates. Le
choix se fait en mise fixe.

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
