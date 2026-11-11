# Claude · Méthode humaine

**La stratégie de Claude : ce qu'il jouerait lui-même s'il était humain, pour gagner.** Demandée le 11/11/2026 :
« si tu devais parier, tu ferais quoi pour être le plus optimal possible, et le plus humainement possible ? ».
Une quinzaine de paris par jour au plus, choisis pour leur CLV.

## Règle (figée au lancement, 12/11/2026 00:00 UTC, sans rejeu)

- Écart d'au moins 5 % (au plus 25 %) contre Pinnacle, Polymarket, Betfair ou Matchbook.
- Cote entre 1,50 et 3,00.
- Betclic, PMU ou Unibet seulement.
- Pas de mi-temps (MT1, MT2), ni score exact ni mi-temps/fin ; équipes non inversées ; match pas commencé.
- Un pari par match, 20 par jour au plus (heure de Paris), première détection qui passe la règle.
- Mise fictive 10 €.

## Pourquoi (3 801 paris uniques réglés à cote ≤ 5, 38 jours)

| Critère | Garde | Écarte |
|---|---|---|
| Écart | ≥ 5 % : CLV +1 à +10 % | 2–3 % : CLV +0,1 % (40 % du volume) |
| Bookmaker | Betclic, PMU (CLV +2,2 %), Unibet (+0,7 %) | OlyBet (−2,5 %), Winamax (−1,0 %), NetBet (−1,1 %) |
| Référence | Polymarket (+3,6 %), Betfair (+3,8 %), Pinnacle (+1,3 %) | Kalshi (−10 %), Smarkets (−3 %) |

Sur l'historique : 578 paris, ~15 par jour, CLV +5,8 %, ROI +4,7 % ± 4,2. Les filtres ont été choisis sur ces
mêmes données : le chiffre est flatteur, seul le suivi depuis le lancement compte.

## Comment Claude la jouerait

1. Alerte Pushover sur cette seule stratégie ; parier dans les minutes qui suivent.
2. Revérifier la cote avant de valider : si l'écart est tombé sous 3 %, passer.
3. Mise fixe de 1 % de la bankroll (ou Kelly ¼ plafonné à 2 %).
4. Suivre la CLV chaque semaine ; si elle passe sous 0 sur 200 paris, arrêter et revoir.
5. Répartir entre les trois bookmakers, montants ronds, jamais la mise maximale.
