# Prompts de l'audit complet du 26/11/2026

Six sous-agents lancés en parallèle, chacun dans son propre worktree, avec un périmètre de fichiers séparé pour éviter
les conflits. L'intégrateur fusionne les branches, relance les deux suites de tests, pousse et ouvre la PR.
Résultats : `docs/audit-26-11-*.md`.

## Comment s'en servir

- Une session principale lance les six agents (`Agent`, `isolation: worktree`, en arrière-plan).
- Données réelles : clone partiel de la branche `donnees` dans le scratchpad, en lecture seule (voir « Données »).
- Chaque agent commite dans son worktree, sans pousser ; l'intégrateur fusionne.
- En cas de coupure (quota), relancer chaque agent par `SendMessage` : son travail non commité reste dans son
  worktree. Demander aux agents de commiter au fur et à mesure.
- Économie : sorties filtrées (`tail`, `grep`), pas de relecture inutile.

## Préambule commun (à mettre en tête de chaque prompt)

```markdown
Dépôt `cotes-value` (Python 3.12 + site statique JS, GitHub Actions). Il compare les cotes des bookmakers français
à la cote juste de références sharp, simule des paris value à 10 €, les règle, publie un site GitHub Pages. Tout est en
français. Lis CLAUDE.md et seulement la partie utile du README ; docs/ contient les audits passés : ne refais pas ce
qui y est fait.

Données réelles (LECTURE SEULE) : clone partiel de la branche `donnees` dans <SCRATCHPAD>/donnees. Fichier journalier
non extrait : `git -C <clone> show HEAD:<chemin> > <ton dossier>/x`.

Règles :
- Reste dans ton PÉRIMÈTRE : d'autres agents modifient le reste en même temps. Hors périmètre : note-le.
- Chaque correction de bug : un test qui échoue sur l'ancien code, dans un NOUVEAU fichier tests/test_audit_<date>_<thème>.py.
- N'invente aucun chiffre : tout chiffre vient d'un calcul sur les données, avec la date de mesure.
- Ne touche pas README.md. Rapport dans docs/audit-<date>-<thème>.md (court, verdict d'abord, tableaux).
- Avant de finir : `python -m pytest -q tests 2>&1 | tail -3` et `node --test tests/*.test.mjs 2>&1 | tail -5` verts.
- Commits en français, petits et thématiques. Ne pousse rien, ne crée pas de PR.
- Rapport final (≤ 40 lignes) : branche + SHA, corrections chiffrées, recommandations non faites, état des tests.
```

## 1. Code cœur

Périmètre : comparaison, correspondance, marches, pulsescore, simulation, reglement, resultats*, sources_resultats,
decision(s), mises, notation, analyste, controle, convergence, mouvement, marge, euria, surebets, temps, pipeline/.

```markdown
Chasse aux bugs de correction, validée sur les vraies données :
1. Rejoue le règlement des paris réglés de paris.json avec le code actuel ; liste les désaccords et incohérences
   (gain faux, CLV aberrante, cote juste < 1, doublons, période fausse, dates UTC/Paris, réglé avant le coup d'envoi).
2. Cherche dans le code : divisions par zéro, arrondis, fuseaux, handicaps asiatiques en quart, remboursements,
   prolongations, abandons au tennis, Kelly, cas limites du consensus.
3. resultats_a_saisir.json : quels paris restent à la main et pourquoi ; automatise un type fréquent s'il est sûr.
4. Confirme chaque soupçon sur l'exemple réel avant de corriger. Chiffre l'effet (paris, € à 10 €).
```

## 2. Fiabilité, CI, sécurité

Périmètre : direct/ (sauf boosts_sites), pinnacle*, polymarket*, smarkets, sources de résultats, sources/,
surveillance, derive, fraicheur, echecs, protection, securite, connexion, reprise, delai, alertes/, notifications,
.github/, scripts/ (sauf site et boosts), serveur/, supabase/, requirements*.

```markdown
1. Santé réelle (sante_historique, sante_incidents, controle, etat) : taux d'échec par source, 403/429, budgets,
   durée des cycles ; trouve la cause dans le code et corrige ce qui est confirmé.
2. Workflows : concurrence sur `donnees`, timeouts, permissions, injection `${{ github.event.* }}`, actions épinglées,
   échecs masqués.
3. Sécurité : secrets, fonctions Edge (auth, CORS), systemd, dépendances (pip-audit).
4. Alertes Pushover : doublons ou pertes.
```

## 3. Design et UX

Périmètre : web/ (sauf boosts.js), cotes/site/, scripts/site_web.py, scripts/empreinte_site.py, tests du site.

```markdown
1. Construis le site avec les vraies données, sers-le et regarde-le avec Playwright (Chromium préinstallé) en mobile
   390×844 et bureau 1440×900, chaque onglet, clair et sombre ; relève les erreurs console.
2. Corrige : débordements sur mobile, tableaux illisibles, hiérarchie (ce qu'il faut jouer saute aux yeux), contraste
   WCAG AA, cibles ≥ 44 px, focus clavier, ARIA, états vides, poids de la page, service worker, vitrine.
3. Mesure avant/après (Ko, erreurs console, débordements, contrastes). Aucun chiffre ni calcul ne change.
```

## 4. Stratégie et rentabilité

Périmètre : docs/audit-<date>-strategie.md, etudes/audit_<date>.py, ajout de filtres observés seulement. Aucune
stratégie retirée ni modifiée : recommandations.

```markdown
Analyste quantitatif sceptique :
1. ROI et CLV par stratégie, référence, bookmaker, sport, marché, tranche d'écart, cote, délai, âge du prix, heure,
   mois ; IC par bootstrap groupé par match ; nombre de paris ET de matchs.
2. La CLV prédit-elle le ROI ?
3. Tests multiples (Benjamini-Hochberg, Holm) : qu'est-ce qui garde un avantage hors échantillon ?
4. Puissance : paris et jours nécessaires pour conclure sur +3 % de ROI.
5. Verdict : quoi jouer, quoi arrêter, mise conseillée, protocole des prochaines idées.
```

## 5. Boosts

Périmètre : cotes/boosts.py, direct/boosts_sites.py, scripts/regler_boosts.py, scripts/sonde_boosts.py, web/boosts.js,
docs/boosts.md, tests des boosts.

```markdown
1. Traduction : part traduite par bookmaker et sport ; ajoute les traductions sûres des libellés réels fréquents.
2. Valeur et calibration (gagnés contre attendus) par type.
3. Règlement : mal réglés, jamais réglés, en double.
4. Boosts couverts et surebets : mises de couverture sur cas réels.
5. Onglet : « à jouer » en tête avec mise conseillée et gain attendu, le reste replié.
6. Conclusion : quels boosts jouer, lesquels ignorer.
```

## 6. Dette technique et performance

Périmètre : strategie_*, strategies/, strategies_prudentes, stockage, depot/, memo, memoire, config, etudes/,
notebooks/, tests lents.

```markdown
1. Code mort (vulture ou grep), branches de sources arrêtées : supprime ce qui est prouvé mort.
2. Duplication entre strategie_* : factorise seulement si le rejeu est identique octet pour octet.
3. Performance : cProfile des bilans et du stockage sur les vraies données ; optimise à sortie identique.
4. Tests : `--durations=25`, accélère sans perte de couverture ; mesure avant/après.
```
