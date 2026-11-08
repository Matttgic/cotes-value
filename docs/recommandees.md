# Stratégies recommandées

En haut de la page Stratégies : « Recommandée 1, 2, 3 », puis « Recommandée 4 · Fusion ».
Code : `cotes/recommandations.py` (choix), `cotes/strategie_recommandee.py` (fusion), `scripts/site_web.py`
(calcul à chaque construction du site), `web/modele.html` (`rendreRecommandees`).

## Recommandées 1 à 3 : choix

Sur le suivi depuis le lancement de chaque stratégie, en mise fixe, une stratégie est **candidate** si :

| Critère | Seuil | Pourquoi |
|---|---|---|
| Matchs réglés | ≥ 50 (note non provisoire) | Assez de matchs pour que le hasard pèse peu |
| Borne basse à 80 % du ROI, par match | > 0 | Rentable même dans un scénario prudent |
| ROI sans les meilleurs matchs (5 %, au moins un) | > 0 | Le gain ne tient pas à quelques matchs chanceux |
| Part du meilleur match dans les gains | ≤ 25 % | Pas de dépendance à un seul match |
| CLV moyenne par match | > 0 | Les cotes prises battent la clôture : avantage réel, pas seulement de la chance |

Les candidates sont classées par note /100 (docs/notation-strategies.md, version 2). Une candidate qui partage plus
de 60 % de ses paris avec une recommandée mieux notée est écartée comme doublon (paris communs / paris de la plus
petite des deux). Trois recommandées au plus. Les bases du Bilan (tous les paris d'une référence) ne sont pas
candidates.

Le choix est recalculé à chaque mise à jour du site : une stratégie qui faiblit sort de la liste. Les chiffres
affichés suivent la mise choisie (fixe ou Kelly) ; le choix, lui, se fait toujours en mise fixe.

## Choix du 8/11/2026

| Rang | Stratégie | Matchs | ROI | Borne basse | ROI sans les meilleurs | Meilleur match | CLV par match | Note |
|---|---|---|---|---|---|---|---|---|
| 1 | Polymarket · cotes 1,5–3 · écart ≥ 2 % · ≤ 36 h | 109 | +22,3 % | +8,8 % | +12,5 % (6 retirés) | 2,9 % | +2,1 % | 88 |
| 2 | Pinnacle · cotes 1,3–2 · écart ≥ 2 % · ≤ 36 h | 284 | +8,9 % | +2,7 % | +4,0 % (15 retirés) | 0,8 % | +0,9 % | 85 |
| 3 | Polymarket · cotes 2–5 · écart ≥ 2 % · ≤ 36 h | 142 | +28,9 % | +12,6 % | +11,2 % (8 retirés) | 3,3 % | +1,3 % | 84 |

Écartées comme doublons : Pinnacle · 1,5–3 (71 % de paris communs avec la n° 2) et Polymarket · 1,3–2 (67 % avec la
n° 1). Aucune stratégie de la famille des comparateurs (Claude, Grok, Défi…) ne remplit tous les critères ce
jour-là : Grok 8 en est la plus proche, mais n'a que 40 matchs réglés.

## Recommandée 4 · Fusion

Réunion des trois recommandées du 8/11/2026, **membres figés** : un pari est pris quand l'une des trois le prend,
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
- Les membres ne changent pas quand le classement change : une nouvelle fusion serait une nouvelle stratégie,
  avec sa propre date de départ.

## Limites

Recommandation descriptive, sur un passé court (environ 3 semaines et demie de suivi) : aucun gain futur garanti.
Les trois règles viennent d'une famille de 24 règles du laboratoire ; choisir les meilleures d'une famille
surestime leur avenir (sélection après coup), d'où les critères prudents ci-dessus et la fusion suivie
uniquement en prospectif.
