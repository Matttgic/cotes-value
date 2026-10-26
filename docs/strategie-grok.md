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

## Grok 2 — Pinnacle low (v2)
- Référence : Pinnacle (v1 : Smarkets, abandonné ; Betfair n'est plus collecté)
- Cotes : 1,30 – 2,00
- Edge : 3 % – 15 %
- Max 6 paris/jour

## Grok 3 — Consensus mid
- Référence : Consensus
- Cotes : 1,40 – 2,30
- Edge : 2 % – 10 %
- Sports : football, basket, hockey
- Max 8 paris/jour
- v2 : le Consensus n'a pas de score de ressemblance propre. La preuve exigée est celle de chaque
  composante (`preuve_prise.preuves_composantes`, score ≥ 0,85 et match associé), avec au moins
  deux composantes, toutes parmi Pinnacle, Betfair et Polymarket. Un Consensus incluant Smarkets
  ou Kalshi est refusé. Les paris enregistrés avant ce champ n'ont pas cette preuve et restent refusés.

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

## Grok 9 et 10 — Valeur (lancées le 26/10/2026 à 20:00 UTC, sans rejeu)

Même règle, une référence chacune. Inspirée d'une stratégie « Valeur » (marge retirée, edge ≥ 4 %,
cote 1,50–4,50, Kelly au quart plafonné à 2 %, plancher 0,25 %), adaptée aux références déjà
collectées. Jamais un bookmaker français contre un autre, jamais un consensus de bookmakers
français. Smarkets, Kalshi, Betfair et le Consensus sont hors périmètre.

La probabilité juste est celle déjà écrite sur le pari (`cote_juste`) : dévig power pour Pinnacle,
milieu achat/vente renormalisé pour Polymarket. L'edge exigé est `cote × proba_juste − 1`.

| Stratégie | Règle |
|---|---|
| Grok 9 | Pinnacle seul · tous sports suivis · cote 1,50–4,50 · edge ≥ 4 % · plusieurs paris par match · pas de limite par jour · jusqu'au coup d'envoi |
| Grok 10 | Polymarket seul · tous sports suivis · cote 1,50–4,50 · edge ≥ 4 % · plusieurs paris par match · pas de limite par jour · jusqu'au coup d'envoi |

Version 2, le soir du lancement. La stratégie « Valeur » n'a ni un seul pari par match, ni un
plafond de 10 paris par jour, ni l'interdiction de jouer dans les 15 dernières minutes. Plusieurs
marchés ou issues du même match sont donc retenus. On ne dédoublonne que la sélection exacte
(même match, même marché, même issue), pour ne pas compter deux fois le même pari revu à un
passage suivant. On peut parier jusqu'au coup d'envoi, jamais après le début du match. La
référence doit toujours dater de moins de 15 minutes, et la preuve de correspondance reste exigée.

Mise fictive 10 €, comme les autres Grok. Le Kelly ¼ du site (bankroll 1 000 €, plafond 2 %)
reste le calcul commun : dans cette bande, la plus petite mise est ≈ 2,86 € (cote 4,50, edge 4 %),
au-dessus du plancher 0,25 % (2,50 €). Le plancher n'est donc pas ajouté au calcul global, qui
sert aussi aux stratégies déjà lancées. Grok 1 à 8 gardent leur règle d'un pari par match, leur
plafond journalier et leurs 15 minutes avant le coup d'envoi.
