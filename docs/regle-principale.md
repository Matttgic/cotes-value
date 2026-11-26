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
- **Winamax à part** (depuis le 26/11/2026) : collecté normalement mais hors règle (CLV Pinnacle négative). Ses values
  du dernier relevé qui passeraient la règle sans cette exclusion sont listées sur l'Accueil, pour information :
  aucun pari pris, rien dans les bilans (`winamax_a_part`, `cotes/site/construction.py`).
  Ces values sont aussi notées sans pari (`donnees/winamax_suivi.json`, `cotes/winamax_suivi.py`) : CLV contre la
  clôture Pinnacle (30 min avant le match), une par cote, moyenne et IC 95 % par match, affichées sur l'Accueil.
  L'exclusion de Winamax est à revoir le 5/12/2026 sur cette mesure.
- **Règlement manuel** : un statut saisi sous l'identifiant d'un pari exige une source et un score (ou un motif) ;
  une saisie par match exige une source. Revue des 87 statuts sans preuve : [manuels-sans-preuve.md](manuels-sans-preuve.md).

## Filtres observés (26/11/2026)

Sous-ensembles de la règle suivis sur les paris détectés depuis le 26/11/2026, sans être joués ni changer la règle
(`cotes/filtres_observes.py`, page Décision) : cote repérée par 2 références ou plus, écart ≥ 5, 8 et 10 %. Constat
du 26/11 sur les paris du 05/10 au 25/11 (optimiste, choisi sur ces données) :

| 2 sources ou plus, écart | Paris | ROI (10 € fixes) | CLV [IC 95 %] |
|---|---|---|---|
| ≥ 3 % | 252 | +18,7 % | +7,8 % [+5,2 ; +10,3] |
| ≥ 5 % | 117 | +25,4 % | +9,5 % [+6,3 ; +13,1] |
| ≥ 8 % | 57 | +56,3 % | +10,6 % [+4,7 ; +16,2] |
| ≥ 10 % | 34 | +91,0 % | +14,6 % [+5,6 ; +22,2] |

Pas d'optimum net : la CLV monte avec le seuil, le gain net reste à peu près stable. Un seul test, sur ≥ 8 % : CLV
Pinnacle > 0, Student unilatéral par match, seuil 5 %, à partir de 30 CLV. Lecture le 5/12, puis chaque mois.
Limite : les sources d'une cote comptent les références qui l'ont repérée à tout moment, pas seulement avant la
première détection.
