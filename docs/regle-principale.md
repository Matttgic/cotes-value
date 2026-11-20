# Règle principale — gel du 20 novembre 2026

Suite de l'audit du 20/11/2026 : 97 stratégies testées en parallèle, aucune ne survit à la correction pour tests
multiples, et les règles récentes ont été choisies sur les données qui les jugent. Une seule règle est désormais
jugée, et le registre des stratégies est gelé.

| | |
| --- | --- |
| Règle | Cote ≤ 5 · écart ≥ 3 % · hors Winamax et OlyBet · au plus 24 h avant le match · une mise par cote française |
| Origine | [strategie-mises.md](strategie-mises.md), choisie sur les matchs du 05/10 au 25/10 |
| Paris jugés | Détectés depuis le 15/11/2026 (après le gel) |
| Test | Un seul : CLV moyenne contre la clôture Pinnacle > 0, Student unilatéral par match, seuil 5 % |
| ROI | Affiché, sans verdict (≈ 49 000 paris pour prouver +2 %) |
| Code | `cotes/regle_principale.py`, publié dans la page Décision (`D.decision.principale`) |

Conséquences :

- **Prise** : la règle de prise redevient celle du 14/11. Les exclusions du 19/11 (volley, total au basket) sont
  retirées : elles empêcheraient de juger la règle figée sur tous ses paris.
- **Fraîcheur** : chaque lecture (cote française et références) a au plus 5 minutes à la décision, contre 15 avant.
  Au-delà de 5 minutes, un prix Pinnacle donnait une CLV de −1,82 % [−3,50 ; −0,02] contre +3,09 % en deçà.
- **Registre gelé** : 97 stratégies, 77 inscriptions au protocole. `tests/test_regle_principale.py` échoue si l'une
  ou l'autre grandit. Le protocole continue de tourner pour les stratégies inscrites, sans nouvelle place.
- **Règlement manuel** : un statut saisi sous l'identifiant d'un pari exige une source et un score (ou un motif) ;
  une saisie par match exige une source. Revue des 87 statuts sans preuve : [manuels-sans-preuve.md](manuels-sans-preuve.md).
