# Règlements des bookmakers français : ce que le code applique

Lus le 05/10/2026. Pour chaque bookmaker : la règle officielle, ce que le code en fait, et ce qui reste à
vérifier. Le code concerné est dans `cotes/pulsescore.py` (`REGLE_PAR_DEFAUT`, `PROLONGATION_VERIFIEE`,
`periode_match`) pour la comparaison, et dans `cotes/reglement.py` (`scores_par_periode`, `_regler_abandon`)
pour le règlement.

Principe : quand on ne sait pas si une prolongation compte, le marché **n'est pas comparé** (période
`MATCH?`). On préfère rater une erreur de cote que parier sur un marché différent de celui de la référence.

## Sources

| Bookmaker | Document | Accès |
|---|---|---|
| Winamax | Règlement des paris sportifs, <https://www.winamax.fr/cgu-paris-sportifs> | Lu en entier |
| Unibet | Règlement des paris sportifs FDJ Online (Unibet est dans le groupe FDJ United), applicable au 29/09/2026 | Lu en entier (PDF) |
| NetBet | Règlement des paris sportifs et règles BetBuilder, netbet.fr | Lu en entier |
| PMU | Règlement des paris sportifs, version du 05/07/2022 | Lu en entier (PDF), mais ancien : PMU a changé de plateforme depuis |
| Betclic | Règlement des paris sportifs | **Inaccessible** (le site bloque toute lecture automatique). Règles déduites des libellés des marchés |

## Prolongations : hockey, basket, football américain, baseball

Pinnacle cote ces sports dans deux versions : temps réglementaire et prolongation incluse. Il faut donc
savoir laquelle le bookmaker français propose.

Au football, au handball et au rugby, tous les bookmakers règlent sur le temps réglementaire, comme
Pinnacle : pas de différence.

Les marchés où le nul existe (1N2, double chance, remboursé si nul, handicap à 3 issues, mi-temps/fin de
match) portent toujours sur le temps réglementaire.

### Hockey sur glace

| Bookmaker | Règle officielle | Dans le code |
|---|---|---|
| Winamax | « Les paris sur le hockey sur glace sont proposés par défaut sur la base du temps règlementaire. Dans certains cas, les prolongations sont comptabilisées : le cas échéant, Winamax le précisera dans l'intitulé ou l'aide du pari. » | Temps réglementaire par défaut. **Exception** : « Nombre de buts » (totaux, totaux par équipe) et vainqueur à 2 issues = prolongation incluse, vérifié par toi sur le site |
| Unibet | « A défaut d'être précisée, la période à prendre en compte est le temps réglementaire. » ; pour les face-à-face et handicaps, « pour certains sports, il sera tenu compte des éventuelles prolongations ». **Vérifié dans l'appli** : « temps réglementaire » est écrit dans l'intitulé quand il s'applique | Temps réglementaire si l'intitulé le dit, sinon prolongation incluse |
| NetBet | « Dans tous les sports qui adoptent un certain temps de jeu, le résultat qui fait foi est celui qui est établi après le temps de jeu normal (ou temps réglementaire) […]. Les prolongations ou séance de tirs au but n'auront aucune influence sur l'issue des paris sauf dans les cas contraires mentionnés sur le site. » | Temps réglementaire, sauf libellé contraire. (Les règles BetBuilder, prolongation incluse, ne concernent que les paris BetBuilder, qu'on ne simule pas) |
| PMU | Règlement de 2022 : prolongation incluse en NHL et AHL, temps réglementaire ailleurs. **Vérifié dans l'appli** : la mention « Prol. et t.a.b. inc. » est écrite quand la prolongation compte | Temps réglementaire, sauf « Prol. et t.a.b. inc. » |
| Betclic | Règlement inaccessible. **Vérifié dans l'appli** : sans mention entre parenthèses, la prolongation compte (vainqueur, totaux) ; « (tps rég.) » = temps réglementaire | Prolongation incluse, sauf « tps rég. » |

**Handicaps à ±1,5, ±2,5…** : la prolongation (but en or) ou les tirs au but partent d'une égalité et
donnent toujours 1 but d'écart. Un handicap -1,5 est donc perdu et un +1,5 gagné avec ou sans
prolongation : ces handicaps sont comparés à Pinnacle chez tous les bookmakers. Les handicaps à ±0,5 ou
±1, eux, changent avec la prolongation et suivent la règle du bookmaker.

**Tirs au but** (Winamax, NetBet, PMU) : le vainqueur de la séance reçoit un but de plus. Exemple NetBet :
« France - Allemagne 2-2 à la fin des prolongations. La France remporte la séance de tirs aux buts. Le
score final sera donc de 3-2 pour la France. Le nombre de buts marqués dans le match après prolongations et
tirs aux buts sera de 5. » Winamax : « La victoire lors d'une séance de tirs au but est considérée comme un
but supplémentaire marqué par l'équipe victorieuse. » C'est aussi la règle de Pinnacle. Le code compte ce
but pour tous les marchés « prolongation incluse ».

### Basket

| Bookmaker | Règle officielle | Dans le code |
|---|---|---|
| Winamax | « Les paris sur le basket sont proposés sur la base du temps total du match (temps règlementaire et prolongations éventuelles). Dans certains cas, les prolongations ne sont pas comptabilisées : le cas échéant, Winamax le précisera dans l'intitulé ou l'aide du pari. » | Prolongation incluse, sauf libellé contraire |
| Unibet | Temps réglementaire à défaut de précision (règle générale ci-dessus). Pour les « face à face », « pour certains sports, il sera tenu compte des éventuelles prolongations ». **Vérifié dans l'appli** : « temps réglementaire » est écrit dans l'intitulé quand il s'applique | Temps réglementaire si l'intitulé le dit (non comparé : Pinnacle ne cote le basket que prolongation incluse), sinon prolongation incluse |
| NetBet | Temps réglementaire (règle générale 4.2) ; « En cas d'égalité sur le résultat d'un pari et si cette option n'a pas été proposée par NETBET, tous les paris seront considérés comme nuls. » **Vérifié dans l'appli** : « prolongations incluses » est écrit dans l'intitulé quand elles comptent | Prolongation incluse si l'intitulé le dit (comparé), sinon temps réglementaire (non comparé) |
| PMU (2022) | « tous les paris […] sont sur la base du temps réglementaire de 40 minutes […] ainsi que des prolongations le cas échéant » (idem 48 minutes en NBA) | Prolongation incluse |
| Betclic | **Vérifié dans l'appli** : sans mention entre parenthèses, la prolongation compte (vainqueur, total de points) | Prolongation incluse |

Deuxième mi-temps et 4e quart-temps : selon les bookmakers, la prolongation y est ajoutée ou non. Ces
marchés ne sont pas comparés.

### Football américain et baseball

| Bookmaker | Règle officielle | Dans le code |
|---|---|---|
| NetBet | Football américain : « les paris portent sur le résultat final prolongations incluses, sauf mention contraire dans l'intitulé du pari. » Baseball : « En pré-match, Qui va gagner le match ?, concerne les neuf premières manches réglementaires. » | Football américain : prolongation incluse. Baseball : 9 manches |
| Autres | Pas de règle par défaut claire, ou règlement inaccessible | **Non comparé** sans précision dans le libellé |

## Tennis

### Tie-break et super tie-break

| Bookmaker | Règle officielle |
|---|---|
| Winamax | « Les éventuels tie-breaks joués au cours d'un match sont considérés comme un jeu. Les éventuels super tie-breaks joués au cours d'un match sont considérés à la fois comme un jeu et comme un set. » |
| NetBet | « Si un match se termine par un Super Tie-Break, le match sera considéré comme ayant été joué en 3 sets. Tout Tie-Break ou Super Tie-Break sera considéré comme un jeu seulement dans le total de jeu du match. » |
| PMU (2022) | « un jeu décisif (tie-break) est considéré comme un jeu. Dans l'éventualité d'un jeu décisif pour le gain de la partie (super tie-break), cela sera considéré comme un set à part entière. » |

Dans le code : un dernier set à 10 points ou plus est un super tie-break, compté comme 1 jeu et 1 set.

### Abandon

| Bookmaker | Règle officielle |
|---|---|
| Winamax | « Sauf mention contraire, tous les paris concernant une phase de jeu en cours au moment de l'abandon ou la disqualification (notamment le vainqueur du match, le score du match en sets...) sont annulés. Ainsi, les paris sur le nombre de jeux […] seront annulés si la valeur seuil proposée par Winamax n'est pas dépassée au moment de l'abandon […]. Par exception, les paris sur le nombre de sets […] sont validés dès lors que le résultat est sûr d'être atteint à la fin d'un set. » |
| Unibet | « tous les paris, portant sur une période de jeu (point, jeu, set) totalement terminée et/ou si la valeur seuil proposée dans le pari est atteinte ou dépassée au moment de l'abandon ou de la disqualification, sont promulgués » |
| NetBet | « seuls les paris dont le résultat est déjà définitivement acquis au moment de l'interruption seront validés […]. Par exemple, pour un pari sur le nombre total de sets (plus ou moins 2.5 sets) : si un joueur abandonne au cours du troisième set, le pari sera annulé (remboursé) » |
| PMU (2022) | « Si un match ayant débuté ne va pas à son terme ou s'il se termine sur un abandon ou une disqualification d'un joueur, les paris seront annulés, sauf si leur résultat est déjà entériné sans équivoque (par exemple le nombre de jeux du 1er set si le 1er set a été joué en totalité). » |

Dans le code (`_regler_abandon`) :
- vainqueur du match, handicaps, score exact : remboursés ;
- sets terminés (vainqueur du 1er set…) : maintenus ;
- totaux de jeux : gagnés ou perdus si le seuil est déjà dépassé, sinon remboursés ;
- nombre total de sets : réglé sur « sets terminés + 1 » quand c'est certain, sauf chez NetBet, où il est
  remboursé.

## Vérifications faites dans les applis

Betclic, PMU, Unibet (hockey et basket), NetBet (basket) et Winamax (totaux et handicaps au hockey) : vérifiés par l'utilisateur,
reportés dans les tableaux ci-dessus. Toute nouvelle vérification se traduit par une ligne dans
`REGLE_PAR_DEFAUT` ou `PROLONGATION_VERIFIEE` (`cotes/pulsescore.py`).
