# Liquidité sûre — version 1

**Lancement prospectif : 25 octobre 2026 à 17 h 30 (Paris), `2026-10-25T16:30:00Z`.**
Les prises antérieures ne sont pas comptées. Comparateur supplémentaire : il ne vote dans aucune convergence.

## Hypothèse

Les écarts repérés sur des marchés **liquides** chez Pinnacle (marge faible) et à **cote ≤ 10** sont plus fiables
que les autres : la cote juste y est plus solide.

## Règle figée

- Référence Pinnacle (sans marge) ; bookmakers Winamax, Betclic, Unibet, PMU.
- Marchés : 1N2, vainqueur, remboursé si nul, total, handicap (lignes entières ou demi), temps réglementaire. Tennis et volley : vainqueur uniquement.
- **Marge de Pinnacle ≤ 8 %**, mesurée à la prise (`marge_pinnacle`). Un pari sans cette mesure est refusé.
- Cote 1,30 à 10 ; écart de 2 % à 12 %.
- Référence lue à moins de 15 min ; correspondance prouvée (score ≥ 0,85, contrôle conforme) ; match à au moins 15 min.
- Une seule première prise par match (tous bookmakers), 10 prises au maximum par jour civil de Paris.
- Mise fictive de 10 € (le Bilan affiche aussi la mise Kelly ¼ sur les mêmes paris). Simulation uniquement.

## Limites

- Les seuils viennent du bilan du 5 au 25/10 : au-delà de 8 % de marge, CLV −1,8 % contre +3 % ; cotes > 10 : ROI −35 % à mise fixe.
  Le rejeu est donc optimiste et n'est pas publié comme preuve. **Seul le suivi prospectif fait foi.**
- À comparer avec « Cœur value » et la stratégie de base : si le CLV et le ROI ne battent pas ces témoins après quelques centaines de paris, l'hypothèse tombe.
- Le TRJ, la limite de mise Pinnacle et le mouvement de cote ne servent pas ici : ils se mesurent à part, dans « Essais en cours » du Bilan.
- Un bookmaker peut limiter un compte gagnant.
