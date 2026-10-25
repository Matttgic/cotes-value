# Stratégies Grok

Salve de stratégies créées le 25 octobre 2026 à partir de l'analyse de l'historique de paris simulés (branche `donnees`, `paris.json`).

Les filtres ont été choisis en observant les sous-ensembles historiques avec ROI et CLV positifs (Polymarket, Smarkets, Consensus, cotes basses/moyennes, certains sports). **Le rejeu sur l'historique est optimiste** car les seuils ont été sélectionnés après coup. Seul le suivi prospectif à partir du 25/10/2026 compte.

Toutes les stratégies :
- Mise fictive 10 €
- 1 seul pari par match
- Limite journalière
- Contrôles de qualité standard (preuve de correspondance ≥0,85, fraîcheur, cohérence edge, etc.)
- Ne lisent jamais le résultat, le gain ou la CLV pour la sélection

## Grok 1 — Polymarket mid
- Référence : Polymarket
- Cotes : 1,40 – 2,20
- Edge : 2,5 % – 12 %
- Sports : football, tennis, hockey, basket
- Max 8 paris/jour

## Grok 2 — Smarkets low
- Référence : Smarkets
- Cotes : 1,30 – 2,00
- Edge : ≥ 3 %
- Max 6 paris/jour

## Grok 3 — Consensus mid
- Référence : Consensus
- Cotes : 1,40 – 2,30
- Edge : 2 % – 10 %
- Sports : football, basket, hockey
- Max 8 paris/jour

## Grok 4 — Polymarket low-odds
- Référence : Polymarket
- Cotes : 1,30 – 1,75
- Edge : 2 % – 8 %
- Max 10 paris/jour

## Grok 5 — Multi-sharp low
- Références : Polymarket, Smarkets ou Consensus
- Cotes : 1,30 – 1,80
- Edge : 2 % – 8 %
- Max 12 paris/jour

Ces stratégies sont intégrées dans le système de décisions figées pour un suivi prospectif. Aucune n'est automatiquement promue ; elles sont là pour être testées en simulation.

## Grok 6 à 8 (lancées le 25/10/2026 à 01:00 UTC, sans rejeu)

Construites sur les paris **réglés** du 07 au 17/10/2026 (apprentissage) et vérifiées sur ceux du
18 au 24/10/2026 (validation hors échantillon), 1 pari par match, mise plate 1 u. Référence
de valeur : Pinnacle ou Polymarket uniquement (jamais un bookmaker français contre un autre,
Smarkets et Kalshi exclus). Garde-fous communs identiques à Grok 1–5.

| Stratégie | Règle | Apprentissage | Validation |
|---|---|---|---|
| Grok 6 | Pinnacle · basket/hockey/tennis (vainqueur)/handball/baseball · cote 1,50–3,50 · écart 3–15 % · max 10/j | n 52 · ROI +29 % · CLV +3,5 % | n 31 · ROI +40 % · CLV +2,0 % |
| Grok 7 | Pinnacle · tous sports suivis · cote 1,80–2,50 · écart 4–15 % · max 8/j | n 38 · ROI +16 % · CLV +2,9 % | n 23 · ROI +12 % · CLV +4,2 % |
| Grok 8 | Polymarket · mêmes sports que Grok 6 · cote 1,50–3,50 · écart 3–15 % · max 8/j | n 9 · ROI +29 % · CLV +2,6 % | n 17 · ROI +75 % · CLV +5,1 % |

Échantillons courts (≈ 2 semaines) : ces chiffres sont indicatifs. Grok 8 est exploratoire
(peu de paris Polymarket hors football avant le 18/10). Seul le suivi depuis le lancement compte.
