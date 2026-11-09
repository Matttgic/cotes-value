# Protocole d'évaluation des stratégies

Adapté du protocole commun aux trois dépôts du propriétaire (cotes-value, cotes-boostees, Autonome), débat
« statisticien sceptique » du 9/11/2026. Il dit **quand un résultat compte** ; il ne change aucune règle de
sélection ni aucune stratégie figée. Paris fictifs (10 € fixes), détection seulement.

## P0. Pré-enregistrement

Avant chaque période d'évaluation, un fichier `docs/prereg/AAAA-MM-JJ.md` commité et daté fixe : les règles de
sélection (version du moteur `VERSION` de `cotes/__init__.py` et commit du code), la métrique principale, le nombre
de matchs N visé, la règle d'arrêt et la liste des stratégies évaluées. Chaque pari porte déjà la version du moteur
(`preuve_prise.version`, `2026-11-09-justesse` depuis le lot « justesse »). Les données d'avant le gel servent à
explorer ; elles ne valident rien (exemples : rejeux de Jules, M3, Claude Opus dans le README).

## P1. Unité et grappes

Unité d'analyse : le **match** (événement). Tous les intervalles de confiance et p-valeurs se calculent par match
(gains et mises additionnés par match, ou bootstrap par match) ; par jour si l'on veut être prudent (environ
+15 % d'écart type). Dans le dépôt : `cotes/notation.py` (note /100) et `icRoi` de `web/modele.html` (Bilan,
depuis le 9/11/2026) le font ; la métrique principale garde un pari par match (le premier détecté).

## P2. Métrique principale

- **CLV** = cote prise / cote juste de clôture − 1, la clôture étant lue au plus `CLOTURE_MAX_MIN` (30 min) avant
  le coup d'envoi (`simulation.clv_finale`) ; viser 10 min et publier la sensibilité à 30 min. Préférer une
  clôture lue sur une autre référence que celle de la détection quand elle existe. Couverture déclarée : au moins
  80 % des paris réglés avec une CLV, sinon comparer les paris avec et sans clôture.
- Secondaires : ROI à mise plate (pas Kelly), gagnés contre attendus (Σ des probabilités justes), capture de la
  cote (prix relu 5 min après la prise).
- Jamais un ROI en vert sans son intervalle de confiance.

## P3. Taille d'échantillon

n = ((z₁₋α + z₁₋β) · σ / δ)², σ mesurée sur les données d'exploration (pas supposée).

- CLV, δ = 1 %, σ ≈ 0,09 à 0,10 par match, puissance 80 % : environ 460 à 660 matchs pour une stratégie, 650 à 900
  pour trois, 860 à 1 200 pour dix. Au rythme mesuré (environ 290 matchs par semaine), 2 à 4 semaines.
- ROI, δ = 3 % : environ 8 100 paris (plus de 10 semaines). Avant N, le ROI ne sert qu'à vérifier qu'il ne
  contredit pas la CLV. Afficher « n = x / N ».

## P4. Règle d'arrêt

Un seul regard final à N matchs, fixé à l'avance. Regards intermédiaires seulement pour un arrêt « nocif » (borne
haute de l'IC de la CLV < 0 après au moins 200 matchs), avec une dépense d'α de type O'Brien-Fleming ; aucun arrêt
« pour succès » avant N. Le SPRT de Wald sert à surveiller une dégradation (CUSUM de la CLV hebdomadaire), jamais
à valider : rejoué sur nos données, il disait « validé » après 8 matchs puis l'inverse 100 matchs plus tard.
La mise en pause automatique des stratégies (`cotes/pauses.py`) est un arrêt « nocif » de ce type.

## P5. Tests multiples

- Une seule stratégie primaire par période : test unilatéral à α = 5 %, sans correction.
- Au plus trois stratégies pré-enregistrées en plus : correction de Holm.
- Tout le reste (les dizaines de stratégies et variantes du site) est **exploratoire** : Benjamini-Hochberg à
  q = 10 % sur les p-valeurs par match de la CLV, étiqueté « exploratoire », jamais « recommandée ». Une stratégie
  repérée en exploration s'évalue sur la période suivante seule (hors échantillon) : la meilleure de 70 est
  biaisée à la hausse.

## P6. Critère « recommandée »

Les trois à la fois, sur des données hors échantillon : (i) CLV > 0 avec p < α corrigé à N ; (ii) borne basse de
l'IC du ROI (par match) > −5 points ; (iii) signe positif sur les deux moitiés de la période. Déclassement dès que
(ii) échoue. Les critères actuels des « Recommandées » (`docs/recommandees.md`) restent en place tant que le
propriétaire n'a pas validé ce changement.

## P7. Hygiène des données

Exclure de la métrique principale, et publier la part exclue : références suspectes (écart > 30 %, Polymarket figé
à 50/50 : champ `reference_suspecte`), listes d'issues Pinnacle incomplètes (score exact, mi-temps/fin, jamais
pariées depuis le 9/11/2026), règlements non vérifiables ou faits à la main (étiquetés à part), paris sans cote de
référence valide, appariements douteux. Au-delà d'une cote de 5, la cote juste Pinnacle surestime la probabilité de
gain d'environ 1,8 fois : analyser ces paris à part.

## P8. Affichage honnête

Toujours : n matchs, IC à 95 % par match, date de gel, étiquette « exploration » ou « hors échantillon », CLV et
ROI côte à côte, écart annoncé à côté de la CLV réalisée (l'écart annoncé surestime la valeur). Couleur verte
réservée au critère P6 rempli.
