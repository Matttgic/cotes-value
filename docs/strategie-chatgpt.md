# ChatGPT v1 — stratégie expérimentale

Règles figées le **14 octobre 2026**. Bilan prospectif à partir de **05:15, heure
de Paris (03:15 UTC)**, dans **Bilan → ChatGPT**. La stratégie de Claude reste
dans **Bilan → Stratégie**, avec ses règles et sa date de départ inchangées.

## Règles

| Élément | Règle v1 |
|---|---|
| Référence | Pinnacle **sans marge**, pas « Pinnacle brut » |
| Bookmakers | Winamax, Betclic, Unibet, PMU |
| Cote | De 1,50 à 3,00, bornes incluses |
| Edge estimé | De 3 à 12 %, bornes incluses : cote française / cote juste − 1 |
| Moment | Première détection enregistrée entre 15 minutes et 6 heures avant le match |
| Fraîcheur | Référence lue au plus 5 minutes avant la détection |
| Qualité | Contrôle conforme, correspondance des noms ≥ 0,85 et identifiant Pinnacle présent |
| Marchés | 1N2, vainqueur, total du match, handicap ; match entier ou temps réglementaire |
| Lignes | Entières ou demi-points, aucun quart de ligne |
| Tennis et volley | Vainqueur seulement : éviter les ambiguïtés jeux/sets/points des marchés génériques |
| Sélection | Un seul pari par match Pinnacle, tous bookmakers et marchés confondus |
| Priorité | Première détection admissible ; en cas d'égalité temporelle, edge le plus élevé, puis cote, bookmaker et ID |
| Volume | Les 5 premières sélections admissibles par jour de détection, fuseau Europe/Paris |
| Mise | **10 € fictifs** par pari, donc au plus 50 € de nouvelles mises fictives par jour |

Pas de combiné, pas de martingale, pas d'augmentation de mise après une perte.
Le plafond journalier ne limite pas l'encours cumulé si des matchs sont reportés.
Pas de sélection sur le résultat, la CLV future, le sexe des participants ou le
ROI historique d'un championnat. Les corners, cartons, BTTS, scores exacts et
marchés de période ne font pas partie de cette version.

## Pourquoi cette construction

Les cotes intermédiaires limitent la dépendance à quelques gains très rares.
La borne d'edge évite de courir après les écarts extrêmes, plus exposés aux erreurs
de rapprochement. Une référence unique évite de choisir après coup celle qui a
eu raison. La déduplication par **identifiant de match Pinnacle** limite les mises
corrélées : un match présent chez quatre bookmakers ne devient pas quatre paris.

Les bornes, la fenêtre et le plafond sont des choix de conception, **pas des
seuils optimaux démontrés**. Le ROI positif d'une sous-population plus large ne
se transmet pas automatiquement à une stratégie plus filtrée.

## Audit de conception — résultat défavorable publié

Source : branche `donnees`, commit
[`2503f8b3d245cf20a329f9b3bdbefb02c73b7d95`](https://github.com/Matttgic/cotes-value/commit/2503f8b3d245cf20a329f9b3bdbefb02c73b7d95),
cycle du 14/10 à 03:03:25 UTC. **8 761 lignes** depuis le 5/10, dont **7 413**
pour le témoin « Pinnacle brut ». Ces lignes ne sont pas des paris indépendants.

| Population | Réglés | Gain simulé | ROI | CLV moyenne | CLV mesurées |
|---|---:|---:|---:|---:|---:|
| Paris uniques du site | 1 033 | −430,50 € | −4,17 % | +3,07 % | 721 |
| Claude depuis son lancement du 11/10 | 43 | −28,60 € | −6,65 % | +0,43 % | 42 |
| Pinnacle, cotes 1,50–3,00, edge 3–12 %, avant les autres filtres | 224 | +198,20 € | +8,85 % | +3,90 % | 165 |
| **Rejeu exact ChatGPT v1 avant lancement** | **13** | **−16,30 €** | **−12,54 %** | **−3,60 %** | **12** |

Le rejeu ChatGPT sélectionne 14 paris, dont un non réglé dans ce relevé ; baisse
maximale du gain cumulé : 30 €. **Ce résultat ne valide pas la stratégie**, et
aucune supériorité sur Claude n'est établie. Les fenêtres et populations diffèrent :
ce tableau n'est pas un classement équitable entre stratégies.

Ce petit échantillon sert uniquement à diagnostiquer la mécanique. On ne change
pas les seuils jusqu'à faire artificiellement apparaître un backtest gagnant.
Tous les chiffres rétrospectifs restent **hors du bilan ChatGPT du site**.

Reproduction, depuis le dépôt de code :

```bash
git worktree add --detach ../donnees-audit 2503f8b3d245cf20a329f9b3bdbefb02c73b7d95
python scripts/analyse_chatgpt.py --donnees ../donnees-audit
```

Le commit doit être disponible localement (`git fetch origin donnees` au besoin).
Sur une autre révision des données, les corrections de résultats peuvent modifier
les chiffres. Le script exclut les détections et règlements après le lancement.

## Suivi et limites

- **Bilan → ChatGPT** : gains nets, ROI, CLV avec son nombre de mesures, courbe,
  répartitions par bookmaker et cote. **Voir les paris ChatGPT** ouvre ses fiches.
- Les mises restent celles de la simulation existante ; aucune mise réelle n'est
  effectuée. Aucun nouvel appel API n'est nécessaire.
- Le moteur enregistre une première détection par référence et sélection. Un pari
  repéré initialement hors fenêtre n'est pas repris automatiquement lorsqu'il entre
  dans les 6 heures ; il faudrait un moteur d'entrée dédié pour cette autre stratégie.
- Le flux des quatre bookmakers sert de périmètre français. Il ne constitue pas
  une vérification juridique indépendante de chaque compétition/marché autorisé.
- L'edge dépend de la qualité de Pinnacle et de la correspondance des règlements.
  La CLV reste un indicateur de prix, pas une garantie de profit. Les erreurs de
  source ou de règlement peuvent affecter le suivi.
- La baisse maximale du diagnostic dépend de l'ordre de règlement ; elle ne
  mesure pas un capital minimal ni le risque futur maximal.

Premier examen prévu méthodologiquement après **100 matchs réglés**, sans
optimisation automatique ni rappel programmé : ROI, CLV, couverture de CLV,
remboursements, baisse maximale et stabilité dans le temps. Même 300 paris ne
prouvent pas à eux seuls la rentabilité. Toute modification créera une **v2 avec
une nouvelle date**, sans réécrire le bilan v1. Pour comparer Claude et ChatGPT,
utiliser ensuite la même période à partir du 14/10 à 05:15 Paris.
