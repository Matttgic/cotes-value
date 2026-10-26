# Conseil des stratégies — 26 octobre 2026

**Règle déployée : « Conseil retard » (`conseil_retard`, version 1), suivi prospectif à partir du
26 octobre 2026 à 5 h (Paris), `2026-10-26T04:00:00Z`.** Les prises antérieures ne sont pas comptées. Le rejeu
sur le passé est optimiste et ne prouve rien : seul le suivi fait foi.

## Méthode

Méthode du « LLM Council » : cinq conseillers indépendants, une relecture anonyme et une synthèse. Elle est
adaptée ici pour éviter le sur-ajustement.

1. **Instantané figé** : commit `15c5efc` de la branche `donnees`, `paris.json` (sha256 `99f97851…`).
2. **Trois fenêtres**, selon le début du match à Paris :
   - construction avant le 19/10 ;
   - validation du 19 au 21/10 ;
   - **test du 22 au 25/10**, jamais montré aux conseillers ni aux relecteurs.
3. **Cinq conseillers en parallèle**, chacun avec un angle : contrarien, premiers principes, expansionniste,
   outsider et exécutant. Ils ont le même outil de mesure et ne voient que la construction et la validation.
   Chacun propose une ou deux règles, soit 9 règles en tout.
4. **Cinq relecteurs** voient les réponses sous les lettres A à E. Ils relancent les mesures et désignent la
   réponse la plus forte, le plus gros angle mort et ce que tout le monde a raté.
5. **Le président** garde au plus 4 règles et fixe **avant le test** un critère de réussite pour chacune. Les
   règles sont figées (empreintes ci-dessous) avant un seul passage sur la fenêtre de test.

Le moteur commun (`cotes/strategie_conseil.py`) ne lit que ce qui est connu à la détection. Il ne consulte
jamais le statut, le gain, la CLV ni la cote de clôture.

## Les 9 propositions (construction / validation)

Base à battre : ROI +13,6 % / +14,9 %, CLV +1,2 % / +4,44 %, 378 / 72 paris réglés.

| Conseiller | Règle | Réglés | ROI | CLV |
|---|---|---|---|---|
| Outsider | A1 : cote 1,5 à 5, rien d'autre | 320 / 59 | +12,1 % / +21,6 % | +1,37 % / +4,53 % |
| Outsider | A2 : A1 avec au moins 2 bookmakers sur le même écart | 56 / 12 | +32,3 % / +62,6 % | −1,14 % / −1,9 % |
| Exécutant | B1 : 4 grands bookmakers, cote 1,4 à 3, détection 1 h à 36 h avant, 5 par jour | 54 / 13 | +11,0 % / +41,9 % | +3,69 % / +2,85 % |
| Exécutant | B2 : B1 sans les totaux | 51 / 10 | +17,8 % / +80,3 % | +1,30 % / +7,24 % |
| Expansionniste | C1 : tous sports sauf le football | 160 / 48 | +20,8 % / +35,9 % | +2,01 % / +6,37 % |
| Expansionniste | C2 : tous sports, au moins 2 bookmakers sur le même écart | 66 / 12 | +30,0 % / +62,6 % | −1,0 % / −1,9 % |
| Premiers principes | **D1 : bookmaker en retard, hors football** | 62 / 19 | +39,4 % / +55,6 % | +5,09 % / +7,25 % |
| Premiers principes | D2 : D1 tous sports, sans Winamax | 93 / 20 | +13,7 % / +44,5 % | +3,01 % / +4,37 % |
| Contrarien | E1 : Pinnacle seul, cote 1,3 à 2,5, sans Winamax ni Unibet | 142 / 11 | +10,0 % / +37,6 % | +1,35 % / +2,37 % |

Les conseillers ont essayé environ 126 variantes au total.

## Ce que la relecture a montré

- **Réponse la plus forte : D**, pour trois relecteurs sur cinq. C'est la seule qui part d'un mécanisme
  mesuré. Un écart ne tient que si le bookmaker est en retard sur la ligne de Pinnacle, ce que montre la
  « rétention », c'est-à-dire la CLV divisée par l'écart à la détection.
  - En football, la rétention vaut 0,07 : l'écart est du bruit.
  - En basket et en hockey, elle vaut environ 0,8.
- **Accords**
  - Écarter A2 et C2 : leur CLV est négative, et ce sont les 12 mêmes paris.
  - Retirer le football.
  - La validation, courte et déjà regardée, ne départage rien : l'erreur-type du ROI est de ±17 à ±33 points.
- **Angles morts**
  - Un même groupe de paris Polymarket sur le tennis porte presque toutes les validations : 26 sur 48 pour
    C1, 12 sur 19 pour D1.
  - 27 de ces paris de tennis sont des « remboursé » saisis à la main.
  - Le 18/10, le régime a changé (arrêt de PulseScore, Winamax privé de handicap et de total pendant une
    semaine).
  - Les mesures ne corrigent pas les tests multiples.

## Verdict du président et critères fixés avant le test

Le président a retenu 4 règles. La CLV est le critère, avec t = CLV / erreur-type.

| Règle | Minimum | Confirmée si | Infirmée si |
|---|---|---|---|
| Hors foot · Pinnacle (candidate principale) | 25 réglés | CLV > 0 avec t ≥ 2, et ROI sans le meilleur > 0 | CLV ≤ 0, ou ROI sans le meilleur < −25 % |
| D1 · bookmaker en retard | 15 réglés | CLV de la partie Pinnacle > 0, et CLV totale ≥ celle de la principale | CLV de la partie Pinnacle ≤ 0 |
| C1 · hors foot avec Polymarket (témoin) | 10 vraies issues Polymarket | CLV > 0 et ROI > 0 sur la partie Polymarket | sinon, Polymarket retiré partout |
| E1 · Pinnacle propre (témoin football) | 15 réglés | CLV > 0 et CLV football > 0 | CLV football ≤ 0 : exclusion du football confirmée |

Empreintes sha256 des règles figées avant le test :

```
024b1694a0a2876907c299b0ce361445dc0412ae15256401bb4360744c3fc655  conseil_bookmaker_en_retard.json
506a53234a48db1f06a9aba221ea8a3dc423665006c017cdd904e1f7f43fcb45  conseil_hors_foot_avec_polymarket.json
95f1f8942ed077ac6dc4f50137cbae52b106f648098efaa6d2e8a1dcd5268d31  conseil_hors_foot_pinnacle.json
f4186d3e16a58f3d96455cf5fb4910163fb6fcf89d78ca16e39e9e9e496c8478  conseil_pinnacle_propre.json
```

## Résultat du test unique (matchs du 22 au 25/10)

| Règle | Réglés | ROI | ROI sans le meilleur | CLV (n) | t | Verdict |
|---|---|---|---|---|---|---|
| Base | 169 | −6,9 % | −9,6 % | +0,16 % (148) | 0,16 | — |
| Hors foot · Pinnacle | 77 | −7,3 % | −13,5 % | −0,22 % (63) | −0,15 | **infirmée** |
| **D1 · bookmaker en retard** | 25 | +4,3 % | −3,0 % | +3,4 % (22) | 1,1 | **confirmée, signal faible** (partie Pinnacle +3,47 %, 21 paris) |
| C1 · partie Polymarket | 8 | −12,2 % | — | +7,77 % (7) | — | **non concluant** (8 vraies issues sur 10 requises) |
| E1 · Pinnacle propre | 58 | −3,2 % | −5,8 % | −0,19 % (48) | −0,11 | **infirmée** (football : CLV −1,37 %, ROI −18 %, 22 paris) |

## Ce qui est déployé, et pourquoi seulement ça

- **D1 est déployée** sous le nom de « Conseil retard ». Elle est cochable dans Pushover et suivie sur le site
  avec les autres stratégies. C'est la seule à avoir passé son critère.
  - Réglages : références Pinnacle et Polymarket ; tous sports sauf le football ; 1N2, vainqueur, double
    chance et handicap ; cote de 1,30 à 5 ; écart de 3 à 15 % ; référence lue il y a 5 min au plus.
  - Détection de 15 min à 36 h avant le match ; une prise par match ; 10 au plus par jour ; mise fictive de 10 €.
- **La candidate principale et E1 sont infirmées**, et elles ne sont pas déployées. E1 confirme que le
  football doit rester exclu.
- **C1 n'est pas conclusive.** Polymarket est gardé dans D1 comme le prévoyait la règle figée, mais sa part
  est à surveiller à part.

## Limites connues

- **Le signal est faible** : t = 1,1 sur 25 paris. Le ROI sans le meilleur pari reste négatif (−3,0 %).
  **Pas d'argent réel avant 150 paris réglés en suivi prospectif.**
- **La référence Consensus ne passe jamais** la preuve de correspondance du moteur, faute de score propre.
  Aucune règle du conseil ne peut donc la retenir.
- **Remboursés saisis à la main** : des paris Polymarket de tennis en validation ont le statut « remboursé »
  saisi à la main. Ils sont exclus des minimums, mais ils ont pesé sur le choix des filtres.
- **Changement de régime le 18/10** : la construction mélange deux régimes de collecte.
- Un bookmaker peut limiter un compte gagnant. La cote peut bouger entre l'alerte et la prise.
