# Simplification de `cotes/`

Fait le 14/11/2026. But : moins de modules qui se recoupent, sans perdre de données ni de fonction utilisée.

## Résultat

| | Avant | Après |
|---|---|---|
| Modules dans `cotes/` (hors `direct/` et `analyse_marche/`) | 81 | 75 |
| Lignes dans ces modules | 16 170 | 16 036 |
| Tests Python | 1 653 réussis | 1 653 réussis |
| Tests JavaScript | 77 réussis | 77 réussis |

Rien ne change dans la branche `donnees` : mêmes noms de fichiers, mêmes formats, mêmes clés du journal
(`historique_cotes`, `historique_references`, `pannes_strategies`…). Aucune règle de stratégie n'est modifiée.

## Contrôle après chaque étape

1. `python scripts/verifier_secrets.py`, `python -m pytest -q tests`, `node --test tests/*.test.mjs`.
2. Empreinte du site : `scripts/site_web.py` construit le site sur une copie des données réelles du 14/11/2026
   (`paris.json`, archives, fichiers d'état), heure figée. Les 40 fichiers produits (pages, `notifications.json`,
   `ordres.json`, `mises/*.json`, états réécrits dans `donnees`) sont comparés octet par octet avec la version
   d'avant. Identiques à chaque étape. Seule exception voulue : étape 4, un commentaire corrigé dans
   `web/modele.html` change `index.html` et `version.json`, rien d'autre.
3. Étape 8 : chaque fonction de date retirée a été comparée à sa remplaçante sur 17 324 valeurs (toutes les dates de
   `paris.json` et `etat.json`, plus des valeurs invalides). Aucun écart.

Limite : l'empreinte ne couvre pas le cycle de collecte (il faut le réseau). Les étapes 3 et 8 qui le touchent
reposent sur les tests.

## Étapes faites

| N° | Changement | Modules en moins |
|---|---|---|
| 1 | Code jamais appelé retiré : `protection.proteger`, `direct/horizon.PRES_H`, alias `paris_claude_pmu` | 0 |
| 2 | `historique_notes.py` fusionné dans `notation.py` (la note et son historique quotidien) | 1 |
| 3 | `historique_cotes.py`, `historique_references.py` et `ecriture.py` réunis dans `historiques.py` | 2 |
| 4 | `pannes.py` fusionné dans `protection.py` ; un seul envoi Pushover d'exploitation, `echecs.alerter_pushover` (il existait en double dans `pannes.py` et `derive.py`) | 1 |
| 5 | `strategie_claude_pmu.py` dans `strategie_claude_signal.py` (même moteur) ; `strategie_m3_structure.py` dans `strategie_m3.py` | 2 |
| 6 | Un seul moteur « une mise par cote française » (`premieres_par_cote`, `selecteur_sans_rejeu` dans `strategie_gemini_defi.py`) : il était copié dans Claude Défi, Opus et Signal | 0 |
| 7 | `strategies_prudentes.selections_prudentes` : 9 boucles répétées remplacées par 2 | 0 |
| 8 | Sept lectures de dates copiées (`netbet`, `pauses`, `reprise`, `resultats`, `stockage`, `strategie_eden`, `strategie_gemini`) remplacées par `temps.instant` / `temps.instant_utc` | 0 |

Un commit par étape (« Simplification 1 » à « Simplification 8 »).

## Noms qui ont changé

À connaître pour un script ou un carnet écrit hors du dépôt. Le dépôt lui-même est à jour.

| Avant | Après |
|---|---|
| `historique_notes.mettre_a_jour`, `.FICHIER` | `notation.historiser`, `notation.FICHIER_HISTORIQUE` |
| `historique_notes.notes_du_laboratoire`, `.reperes` | `notation.notes_du_laboratoire`, `notation.reperes` |
| `historique_cotes.index`, `.changements`, `.ajouter` | `historiques.index_cotes`, `.changements_cotes`, `.ajouter_cotes` |
| `historique_cotes.fraiche`, `.texte_cle` | `historiques.fraiche`, `historiques.texte_cle` |
| `historique_references.changements` | `historiques.changements_references` |
| `historique_references.enregistrer`, `.releve`, `.ajouter_references`, `.ajouter_correspondances` | mêmes noms dans `historiques` |
| `ecriture.ajouter_gzip` | `historiques.ajouter_gzip` |
| `pannes.suivre`, `.envoyer`, `.mettre_a_jour` | `protection.suivre_pannes`, `.alerter_pannes`, `.mettre_a_jour_pannes` |
| `pannes.FICHIER`, `.SEUIL`, `.URL` | `protection.FICHIER_PANNES`, `protection.SEUIL_PANNES`, `echecs.PUSHOVER_URL` |
| `strategie_claude_pmu.CLAUDE_PMU`, `.DEBUT`, `.SELECTEURS` | `strategie_claude_signal.CLAUDE_PMU`, `.DEBUT_PMU`, `.paris_claude_pmu` |
| `strategie_m3_structure.M3_STRUCTURE`, `.paris_m3_structure` | mêmes noms dans `strategie_m3` |

## Qui fait quoi maintenant

Les groupes dont les noms se ressemblent, après simplification.

| Module | Rôle |
|---|---|
| `historiques.py` | Tout ce que le cycle écrit en ajout seul dans `donnees` : `cotes/`, `references/`, `releves/`, `correspondances/`, et l'ajout gzip sûr utilisé aussi pour `opportunites/` |
| `notation.py` | Note /100 des stratégies et son historique quotidien (`notes_historique.json`) |
| `recommandations.py` | Choix des stratégies recommandées, révisé tous les 7 jours (`recommandees.json`) |
| `stockage.py` | `paris.json` et ses archives mensuelles |
| `memoire.py` | Fichiers de travail du cycle gardés hors de `donnees` (cache GitHub Actions) |
| `reprise.py` | Dernier bon état de Pinnacle et Polymarket, repris quand la source tombe |
| `memo.py` | Mémo en mémoire vive des sélections pendant une construction du site (rien sur disque) |
| `protection.py` | Stratégie en erreur pendant la construction du site : isolée, comptée, alerte après 6 échecs de suite |
| `echecs.py` | Erreurs non bloquantes rendues visibles (annotation, `etat.json`) et envoi Pushover d'exploitation |
| `derive.py`, `surveillance.py` | Source qui dérive ; journal des incidents de la page Santé |
| `strategies_prudentes.py` | Registre des variantes et règle « un pari par match » |
| `strategie_commune.py` | Validations partagées par les sélecteurs |
| `strategie_*.py` | Une famille de règles par fichier, même nom que `docs/strategie-*.md` et `tests/test_strategie_*.py` |

## Non retenu, et pourquoi

- **Fusionner les stratégies de base** (`chatgpt`, `gemini`, `jules`, `jules_v2`, `eden`, `m3`) : règles figées.
  `scripts/verifier_strategie_jules_v2.py` enregistre l'empreinte de `strategie_jules_v2.py`, `strategie_commune.py`,
  `strategie_jules.py`, `correspondance.py` et `decisions.py`. Ces cinq fichiers n'ont pas été touchés.
- **Fusionner `strategie_coeur.py` et `strategie_liquidite.py`** : deux règles figées de 70 lignes, proches mais avec
  des seuils et des bornes différents. Les réunir obligerait à réécrire leurs règles de refus. Gain : un fichier.
- **Fusionner `memo.py`, `memoire.py`, `reprise.py`, `stockage.py`** : les noms se ressemblent, les rôles non (tableau
  ci-dessus). Aucun code commun à retirer.
- **Une seule fonction d'écriture atomique JSON** : une douzaine de copies de 3 lignes, avec des formats différents (indentation,
  gzip niveau 5 ou 6, ASCII ou non). Gain d'environ 15 lignes pour un risque sur les fichiers de `donnees`.
- **Fusionner les stratégies Claude** (`claude_defi`, `claude_opus`, `claude_signal`, `claude_humain`) : chaque fichier
  a ses constantes `DEBUT` et `SELECTEURS`, lues par ses tests. Le code commun est déjà réuni (étape 6).

## Suite possible

Une seule étape reste proposée, à décider : déplacer les 19 `strategie_*.py` dans un dossier `cotes/strategies/`.
`cotes/` passerait de 75 à 56 modules. Coût : environ 70 fichiers d'imports à modifier, les chemins de
`.github/workflows/site.yml` et de `scripts/verifier_strategie_jules_v2.py`, et les empreintes des cinq fichiers
figés changeraient. Aucun code en moins : c'est du rangement.
