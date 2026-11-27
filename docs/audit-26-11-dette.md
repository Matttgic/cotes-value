# Audit du 26/11/2026 — dette et performance

## Verdict

Peu de dette dans le périmètre (stratégies, registre, variantes prudentes, stockage, dépôt, mémo, configuration,
études). Code mort quasi nul : une fonction d'étude jamais appelée et quatre imports. Deux copies de moteur réunies.
Le mémo et le dédoublonnage par match des variantes prudentes étaient les deux points chauds du périmètre : la
construction du site passe de **21,1 s à 18,7 s** (−11 %) sur les vraies données, la suite Python de **144,7 s à
119,7 s** (−17 %). Aucun comportement changé : site et rejeu des stratégies identiques octet pour octet.

Les trois plus gros gains restants sont hors périmètre (section « Hors périmètre ») : le premier, un cache sur
`decision.quantile_student`, retirerait environ 2,2 s par construction sans rien changer à la sortie.

## Mesures

Données réelles du 26/11/2026 (branche `donnees`, 7 279 paris dont 3 513 archivés), heure figée
`2026-11-26T23:30:00+00:00`, sans profileur, même machine (4 cœurs).

| Mesure | Avant | Après |
|---|---|---|
| Construction du site complète | 21,1 s | 18,7 s |
| Mémo des sélections : `_identifiants` + `_rendre` | 1,64 s | 0,43 s |
| `selection_unique` (65 appels par construction) | 1,40 s | 0,85 s |
| Empreintes du protocole sur le témoin (à chaque construction) | 2,20 s | 1,53 s |
| `selection_unique`, un appel sur les 7 279 paris (portée match) | 80 ms | 59 ms |
| Lecture `paris.json` + archives + fusion | 0,24 s | inchangé (pas un point chaud) |
| Suite Python, un seul processus | 144,7 s | 119,7 s |
| … dont empreintes du protocole (31 tests qui construisent le site) | 75,3 s | 62,1 s |
| Suite Python avec `pytest -n 4` (pytest-xdist) | arrêt une fois sur deux (collecte instable) | 45 s, 2 054 réussis (3 lancements de suite) |

## Changements (6 commits)

| Commit | Contenu | Preuve |
|---|---|---|
| Mémo | Identifiants d'une liste gardés pour les deux dernières listes vues, réutilisés seulement si la liste contient les mêmes objets aux mêmes identifiants ; tuples de valeurs immuables et dictionnaires `id → valeur` rendus sans reconstruction | site, rejeu, 3 tests neufs verts avant et après |
| Variantes prudentes (1) | Les deux portées de `selection_unique` (« match », « sélection ») partagent `_cycles` : union des alias écrite une fois au lieu de deux ; heure et clés lues une fois par pari | 280 appels comparés à l'ancienne version (vrais paris, témoin, éligibles au hasard, 4 débuts, plafonds), site, rejeu |
| Variantes prudentes (2) | `_observations` (paris triés, heures, clés de match) mémorisée : calculée une fois par liste pendant la construction du site, au lieu d'une fois par stratégie | idem |
| Eden et Gemini | `paris_eden` recopiait le dédoublonnage de `paris_gemini` : un seul moteur, `strategie_gemini.une_par_book_et_match` (plafond facultatif), 27 lignes de moins | 16 appels comparés (Eden 342 prises, Gemini 261), site, rejeu |
| Code mort | `etudes/cote_juste.divergence` (aucun appel), 4 imports et une variable de boucle inutilisés (`ruff` F401, B007) | tests |
| Tests | `tests/conftest.py` : identifiant stable pour un gzip passé en paramètre (son en-tête porte l'heure) ; la collecte change d'un lancement à l'autre et `pytest -n 4` s'arrêtait | même collecte (2 054 tests) d'un lancement à l'autre |

Contrôles après chaque commit : `scripts/empreinte_site.py --comparer` (20 fichiers identiques) et un rejeu de
toutes les stratégies (registre sans mémo, deux passes avec mémo plus une copie des paris, motifs de refus de chaque
module pour chaque pari) : même sha256 `395194fa…` avant et après.

## Non retenu

- **Factoriser dans `strategie_commune.py`** : fichier figé (docs/architecture-cible.md, 2.1, empreinte de
  `scripts/verifier_strategie_jules_v2.py`).
- **Motifs de refus Claude Défi, Gemini Défi, Opus, Signal, Méthode humaine** : blocs proches, mais bornes
  différentes (`<` ou `≤` sur le délai) et l'ordre des tests fixe le motif affiché ; il faudrait des drapeaux.
- **Sélecteurs appelés seulement par les tests** (`paris_grok_6` à `_10`, `paris_defi_1`, `_4`, alias Claude et
  Gemini Défi) : interface publique testée, pas du code mort.
- **Betfair et Kalshi dans les stratégies** : ce sont des paramètres figés des règles (références admises), pas des
  branches de sources arrêtées ; les retirer changerait les définitions du protocole.
- **Cache des empreintes du protocole dans `conftest.py`** : elles dépendent d'entrées cachées (`recommandees.json`,
  pauses, remplacements faits par les tests) ; un cache de session ferait perdre de la couverture.

## Hors périmètre (mesuré, non modifié)

| Point chaud | Mesure | Correction proposée |
|---|---|---|
| `cotes/decision.py`, `quantile_student` | 1 665 appels par construction pour 401 valeurs distinctes, 2,9 s | `@lru_cache` (fonction pure) : environ −2,2 s, sortie identique |
| `cotes/protocole.py` `empreintes_actuelles`, appelé par `site/construction.suivi_protocole` | 1,5 s par construction ; 62 s de la suite (31 tests) | ne recalculer que si le témoin, le code des stratégies ou les fusions actives changent (clé : sha256 du témoin + des sources + `recommandees.json`) |
| `cotes/analyste.py`, `_tirages` | 1,7 s, 1,26 million d'appels à `random.choices` | tirer tout d'un coup changerait la suite aléatoire, donc les chiffres publiés : à décider |
| CI | suite en 120 s sur un processus | `pytest-xdist` dans `requirements-dev.in` et `-n auto` dans le workflow des tests : environ 45 s sur 4 cœurs |
| `tests/test_audit_stockage.py` | identifiants dépendant de l'heure | `gzip.compress(..., mtime=0)` rendrait le crochet de `conftest.py` inutile |
