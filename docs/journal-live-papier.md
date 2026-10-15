# Journal papier Live et suivi des variantes

## Dates des stratégies

Les deux variantes existent déjà depuis le **15/10/2026 à 06 h Paris**. Leur
date et les bilans historiques sont conservés. `suivis_prudents()` est l'export
commun du site et de `scripts/comparer_strategies.py` : sélections officielles,
IDs et statistiques au relevé. Une reconstitution séparée depuis le 14/10 à
14 h est explicitement exploratoire : on ne peut pas antidater un protocole
créé après cette date. Les tableaux/courbes/filtres/badges officiels gardent les
sélections causales existantes, avec un vote par famille Jules et sans M3.

## Déroulement d'un cycle Live

1. Si `LIVE_PAPIER=oui`, avec clé PulseScore et mode complet, une rafale dédiée
   interroge **Winamax, Betclic et Orbit live**, ainsi que les marchés/matchups
   Pinnacle football, hockey, basket et handball. Les sept tâches sont lancées
   en parallèle : **11 requêtes**, sans réessai, timeout réseau 8 s par lecture.
2. Cette rafale précède les collectes pré-match et donc les lectures lentes de
   Polymarket/Kalshi. Les filtres et l'ordre relatif des collectes pré-match
   restent ceux de l'existant ; aucun ancien pari n'est recalculé ou modifié.
3. L'intervalle total entre premier départ et dernière réception est enregistré.
   **S'il atteint 20 s, aucun signal de cette rafale n'est retenu.** On ne promet
   pas que les fournisseurs répondront en moins de 20 s. Les gardes plus strictes
   du moteur L1 restent appliquées (état 15 s, prix 30 s, décalage 10 s).
4. Au plus six prix sur des pauses explicitement reconnues sont observés par
   cycle. Une horloge arrêtée, un score stable ou un nom de période ne suffisent
   pas. Football/basket/handball : mi-temps ; hockey : intermissions P1/P2.
5. Les deux relevés +15/+30 s se font en arrière-plan **pendant** la collecte
   pré-match. Chaque relevé relit au plus deux bookmakers, soit **4 appels
   supplémentaires maximum**. Aucune page suivante ni aucun réessai automatique.
   Le délai réel est publié ; écart de plus de 5 s à la cible = hors fenêtre.
6. Avant la sauvegarde du cycle, les résultats sont ajoutés atomiquement à
   **`docs/live_papier.json` sur la branche `donnees`**. Le fichier homonyme
   de la branche code est seulement un modèle vide, jamais l'historique réel.
   Une erreur live est signalée sans bloquer le scanner pré-match.

Chaque prise papier garde : date réelle, contrat, score, pause, bookmaker, cote
vue, décisions L1 et L2, edge/cote juste quand calculables, raisons de refus,
observations de prix suivantes et délai réel. Aucun prix manquant n'est inventé.
L1 est de la value relative, pas une couverture garantissant un bénéfice.

Les requêtes PulseScore du journal sont ajoutées au compteur mensuel existant.
Sur 288 cycles/jour : 864 à 2 016 appels PulseScore supplémentaires/jour selon
les pauses (3 à 7/cycle), plus 2 304 lectures publiques Pinnacle (8/cycle).
L'offre gratuite PulseScore ne suffit pas ; le compte PRO existant est utilisé.
L'infrastructure garde son rythme d'environ 5 min, adapté seulement à un premier
observatoire des pauses longues. Pas de couverture exhaustive ni temps réel garanti.

Le fichier conserve les **500 dernières observations**, les 500 derniers signaux
et 100 cycles de diagnostic. Déduplication des observations par ID, des signaux
par événement/pause/score/contrat/bookmaker ; un premier signal n'est jamais
remplacé par une meilleure cote observée plus tard. Pas de bilan financier live,
pas de classement rentable à partir de simples mouvements de prix.

## Abstentions attendues

- L'appariement des événements exige des noms normalisés et horaires exactement
  identiques, dans le même ordre, avec marqueurs féminin/jeunes préservés.
  C'est volontairement plus restrictif que le rapprochement pré-match. Une
  inversion ou un nom incertain n'est pas utilisé pour créer un signal.
- La traduction des marchés existante est réutilisée, mais activité du marché
  **et** de la sélection doivent être explicitement vraies. Les scopes ambiguës,
  sous-périodes et marchés non modélisés sont exclus.
- Pas de transformation de l'heure HTTP, de `version` Pinnacle ou de `cutoffAt`
  en heure de dernière confirmation du prix/score. Si les timestamps source
  manquent, une observation est publiée mais **aucun signal vérifié**.
- La sonde précédente a confirmé des scores incohérents et des champs de pause
  incomplets. Unibet/PMU ne sont pas activés dans cette première version live.
- L2 ne déduit jamais les intensités ou écarts-types d'une cote isolée de
  `paris.json`. Sans clôture complète pré-match, profil versionné, règles
  compatibles et contexte live vérifié, il reste refusé. **Zéro signal est une
  sortie valide**, et non une raison de relâcher les gardes.

## Entrées L2

Le point d'entrée optionnel `donnees/docs/live_clotures.json` associe un ID
canonique du journal à un modèle vérifié. Structure : `type` (`poisson` ou
`gaussian`), `closing` (champs de `ClosingContext` avec dates ISO UTC) et
`parameters` (champs de `PoissonModel`/`GaussianModel`, hors `closing`). Les
constructeurs et `evaluate_l2()` valident dates, règles, sport et contexte.
Les paramètres doivent venir des calibrations `fit_poisson` / `fit_gaussian`
sur **tous les marchés nécessaires** et un profil explicite. Aucun fichier de
paramètres fictifs n'est ajouté par cette livraison. Le connecteur ne déclare
le contexte complet que si cette preuve existe ; le champ reste faux par défaut.

## Affichage et isolation

Stratégies contient les cartes des variantes, une reconstitution du 14 distincte
et un bloc repliable **Journal papier Live** : dernier cycle, délai de rafale,
compteurs, lectures partielles et prix vus. Le JSON complet se télécharge depuis
le site. Aucun de ces enregistrements n'entre dans `paris.json`, les courbes
pré-match ou les notifications Chrome. Les mises et l'acceptation réelles sont
inconnues : une cote encore affichée à +30 s ne mesure pas une liquidité exécutable.

Arrêt du journal seulement : retirer `LIVE_PAPIER=oui` du workflow collecte.
Tests : `pytest tests/test_live_papier.py tests/test_strategies_prudentes.py`.
