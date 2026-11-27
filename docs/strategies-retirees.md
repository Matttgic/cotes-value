# Stratégies retirées

Une stratégie retirée ne prend plus aucun nouveau pari et n'envoie plus d'alerte. Elle n'apparaît plus dans Notifs ni
dans les recommandées. Sur la page Stratégies, elle est masquée : « Afficher › Retirées » montre son historique, avec
l'étiquette « Retirée ». La liste est dans `cotes/pauses.py` (`RETIREES`).

Pourquoi garder cette page : ne pas refaire une stratégie déjà essayée et perdante.

## 27/11/2026 à 18 h UTC : quatre stratégies sous la règle, Claude Défi 4 réactivée

Jugées sur la **CLV** et non plus sur le ROI ([audit du 26/11](audit-26-11-strategie.md) : aucun ROI ne tient après
correction pour tests multiples, la CLV si). Critère : au moins 50 CLV mesurées et borne haute à 95 % de la CLV
(bootstrap par match) **sous celle de la règle principale** (+3,4 %). Elles font donc moins bien que la règle seule,
même au mieux. Relevé du 26/11 à 23 h 05 UTC, 10 € fixes.

| Stratégie | Réglés (matchs) | ROI | CLV [IC 95 %] | CLV mesurées |
|---|---|---|---|---|
| ChatGPT v1 (rejeu) | 90 (90) | −8,7 % | +0,7 % [−1,5 ; +2,5] | 73 |
| Grok 2 · Pinnacle low | 95 (95) | −3,9 % | +0,2 % [−1,6 ; +2,0] | 84 |
| Claude Opus · Favoris réguliers | 170 (111) | +7,6 % | +0,5 % [−1,5 ; +2,2] | 137 |
| Cœur value | 63 (63) | −4,6 % | −1,3 % [−4,0 ; +1,0] | 54 |

ChatGPT v1 vote dans Convergence ≥ 2 : sa sélection continue en coulisse (`votes`), comme les autres bases.

**Gardées, trop tôt pour juger** (moins de 50 CLV, lancées les 18 et 20/11) : Claude · Drop Pinnacle (40 CLV,
−0,5 % [−4,9 ; +3,0]), Claude · Drop z-score (31, −1,0 % [−6,6 ; +3,0]), Néon 1 · Socle sharp (34, +0,6 %
[−3,5 ; +4,0]).

**Claude Défi 4 · Gros écart hors Winamax réactivée** : retirée le 27/11 à 0 h sur son ROI (−9,5 %), c'est pourtant la
seule stratégie confirmée hors échantillon : CLV +10,4 % [+5,7 ; +15,0] sur 67 mesurées, +10,1 % sur les 42 paris
réglés après le gel du 15/11. Ses paris depuis le 27/11 à 0 h réapparaissent (la sélection est recalculée à chaque
cycle) ; aucune alerte n'a été envoyée pour eux.

## 27/11/2026 : dix-huit stratégies

Chiffres du suivi depuis le lancement de chaque stratégie, 10 € fixes, relevé du 26/11/2026 au soir. « Au mieux » :
borne haute à 95 % du ROI par match. Le code et les règles restent ; seules la prise, les alertes et l'affichage
s'arrêtent le 27/11/2026 à 0 h UTC.

**Perdantes avec assez de recul** : ROI négatif et au moins 100 paris réglés (sous ce seuil, l'analyste dit « Trop tôt
pour juger »). Aucune n'est prouvée perdante (le meilleur cas reste au-dessus de zéro) : elles sont retirées parce
qu'elles ne gagnent pas après plusieurs semaines, à la demande de l'utilisateur.

| Stratégie | Réglés (matchs) | ROI | Au mieux | CLV par match |
|---|---|---|---|---|
| Convergence ≥ 3 hors M3 | 106 (105) | −11,8 % | +3,2 % | +1,3 % |
| Claude Défi 4 · Gros écart hors Winamax (réactivée le 27/11 à 18 h) | 103 (60) | −9,5 % | +20,3 % | +5,9 % |
| JULES EDGE v2 (rejeu) | 170 (170) | −8,3 % | +4,0 % | +2,0 % |
| JULES EDGE v1 (rejeu) | 133 (133) | −6,6 % | +6,8 % | +0,6 % |
| Défi 1 · Écart fort, match proche | 207 (109) | −3,9 % | +15,6 % | +4,1 % |
| Claude (rejeu) | 654 (412) | −1,9 % | +6,1 % | +2,5 % |
| Conseil · bookmaker en retard (hors foot) | 114 (114) | −1,8 % | +15,3 % | +0,6 % |
| Gemini Défi 1 · Indoor & Glace | 244 (128) | −1,8 % | +14,4 % | +0,9 % |
| Gemini Argon v1 (rejeu) | 188 (181) | −1,6 % | +8,6 % | +2,6 % |
| Claude 1/match · max 10/j | 198 (196) | −1,5 % | +9,3 % | +2,7 % |
| Grok 6 · Pinnacle hors foot | 124 (124) | −0,9 % | +14,7 % | +0,5 % |
| Grok 10 · Valeur Polymarket | 114 (64) | −0,3 % | +25,9 % | +2,2 % |
| Gemini Défi 4 · Lignes asiatiques | 181 (92) | −0,2 % | +18,2 % | +1,9 % |
| Liquidité sûre | 118 (118) | −0,1 % | +17,9 % | +0,5 % |

Claude (rejeu), JULES EDGE v1 et v2 et Gemini Argon v1 sont des stratégies de base : leurs votes font tourner
Convergence ≥ 2 (ROI +1,2 %, gardée). Leur sélection continue donc en coulisse (`votes` dans `RETIREES`) ; seuls
l'affichage et les alertes s'arrêtent. Les arrêter vraiment changerait une règle déjà lancée.

**Mortes** : plus de paris depuis la règle de prise du 19/11 (Winamax exclu, cote ≤ 5…), ou presque.

| Stratégie | Réglés | Dernier pari |
|---|---|---|
| Grok 4 · Polymarket low-odds | 13 | 18/11 |
| Grok 5 · Multi-sharp low | 16 | 18/11 |
| Optimisée 19/11 + Polymarket | 2 | 22/11 |
| Qwen | 12 | 24/11 |

Gardées malgré un ROI négatif, faute de recul (moins de 100 réglés) : ChatGPT v1 (90, −8,7 %), Grok 2 (95, −3,9 %),
Fusion 1 (95, −2,3 %), Cœur value (63, −4,6 %), Claude Opus · Handicaps (69, −5,6 %), Néon 2 (13, −14,4 %).
À revoir quand elles passent 100 réglés.

## 19/11/2026 : quatre stratégies Claude Défi

**Comment on les a jugées.** Les paris sont pris depuis le 14/10/2026, avec une mise fixe de 10 €, et comptés par
match, parce que les paris d'un même match gagnent ou perdent ensemble. La « borne haute » est le ROI du meilleur cas
plausible (95 %, unilatéral). Si même ce meilleur cas est sous zéro, la stratégie perd pour de bon.

| Stratégie | Règles | Paris (matchs) | ROI | Meilleur cas | CLV |
|---|---|---|---|---|---|
| Claude Défi 5 · Books lents, cotes courtes | Betclic et PMU seulement · cote 1,30–3 · écart 6–30 % · 0 < délai ≤ 24 h · Pinnacle, Betfair, Polymarket ou Consensus | 116 (73) | −26,6 % | −4,0 % | +9,7 % |
| Claude Fusion · Défi 4 + Défi 5 | passe Défi 4 (tous books sauf Winamax · cote 1,30–30 · écart 8–30 % · délai ≤ 12 h) ou Défi 5 | 143 (93) | −25,8 % | −2,9 % | +9,0 % |
| Claude Défi 2 · Handicaps | handicaps (asiatique, à 3 issues, sets, jeux) · cote 1,30–4 · écart 5–30 % · délai ≤ 12 h · Pinnacle, Betfair ou Polymarket | 55 (26) | −31,0 % | −2,6 % | +9,4 % |
| Claude Défi 1 · Gros écart 12 h | tous sports et marchés · cote 1,30–10 · écart 6–30 % · délai ≤ 12 h · Pinnacle, Betfair ou Polymarket | 136 (85) | −22,1 % | +2,4 % | +9,7 % |

Toutes ces règles ont en commun : la référence est lue depuis 180 s au plus, les équipes ne sont pas inversées, et
une seule mise est prise par cote française. Le détail complet est dans `docs/strategie-claude-defi.md`.

Claude Défi 1 n'est pas encore prouvée perdante : son meilleur cas reste juste au-dessus de zéro. Elle a été retirée
avec les autres à la demande de l'utilisateur, parce qu'elle suit le même chemin.

## Leçons à retenir

- **Un gros écart (6 % et plus) n'est pas un bon signe.** Le plus souvent, c'est une cote de référence périmée ou
  mal associée, pas un vrai avantage. Les quatre stratégies misaient sur les gros écarts.
- **Une CLV élevée ne suffit pas.** Ces stratégies affichaient +9 à +10 % de CLV et perdaient pourtant 22 à 31 %. Sur
  ces paris, la cote de clôture était mal mesurée. Il faut toujours vérifier que le ROI va dans le même sens.
- **La pause automatique ne voit que la CLV** (`cotes/pauses.py`). Une stratégie qui perd de l'argent avec une CLV
  positive doit être retirée à la main.
- **Exemple de rechute** : « Néon 2 · Sniper écart » (20/11, [strategie-neon.md](strategie-neon.md)) reprend
  le gros écart à moins de 12 h. En validation : CLV +6,2 %, ROI −24,6 %. Suivie, pas notifiée.
- **Les handicaps et les « books lents »** (Betclic, PMU) avec un gros écart ont donné les pires résultats.
