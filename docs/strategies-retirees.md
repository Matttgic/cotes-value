# Stratégies retirées

Une stratégie retirée ne prend plus aucun nouveau pari. Son historique reste visible dans le Bilan, avec l'étiquette
« Retirée ». Elle n'apparaît plus dans Notifs. La liste est dans `cotes/pauses.py` (`RETIREES`).

Pourquoi garder cette page : ne pas refaire une stratégie déjà essayée et perdante.

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
- **Les handicaps et les « books lents »** (Betclic, PMU) avec un gros écart ont donné les pires résultats.
