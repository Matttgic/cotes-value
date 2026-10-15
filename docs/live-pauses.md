# Audit et moteur de recherche : value pendant les pauses

État du 15 octobre 2026. **Recherche hors production**, aucun branchement au
cycle, aux simulations historiques, au site ou aux notifications. Aucun pari
automatique. `cotes/live_pauses.py` ne fait ni requête réseau ni écriture disque.

## 1. Ce que le dépôt voit aujourd'hui

| Source | Chemin et comportement actuels | Live accessible ? | Ce qui manque pour une pause exploitable |
| --- | --- | --- | --- |
| Pinnacle guest | `cotes/pinnacle.py`, `/sports/{id}/matchups` et `/markets/straight` ; rejet explicite de `isLive` | **Oui observé**, voir la sonde ci-dessous | Normaliser `state`/`periods`, règles de règlement, heure de mise à jour du prix et score associé ; le traducteur jette ces états |
| Winamax, Betclic, Unibet FR, PMU via PulseScore | `Client.matchs()` lit `/{book}/{sport}/events`, exige `not live`, `not suspended`, début futur | `/api/{book}/live-events` **documenté et observé HTTP 200** sur les 4 bookmakers | Adaptateur dédié et pagination live ; ne pas seulement changer le filtre de début |
| Betfair via Orbit/PulseScore | Même client pré-match ; actuellement **football et tennis seulement** dans `SPORTS_BETFAIR` | Live observé sur 7 catégories dans la première page, dont tennis/basket/hockey/baseball | Score/pause, carnet back/lay à jour, liquidité, format et règles ; aucune garantie de couverture exhaustive |
| Polymarket Gamma | Événements actifs non clos ; fenêtre `endDate` et `gameStartTime`, midpoint bid/ask | Certains événements en cours peuvent être retournés | Aucun état de pause ni score normalisé ; prix Gamma horodaté à la collecte, pas preuve d'âge du carnet. Pas de référence L1 V1 |
| Kalshi | Événements ouverts ; début **estimé** à partir de la clôture moins une durée par sport | Chevauchement possible avec le live | Pas de chronomètre/pause fiable ; heure estimée insuffisante. Exclu L1/L2 V1 |
| Résultats PulseScore | `/{book}/results`, `resultats.lire()` rejette les résultats non terminés | Les résultats historiques contiennent parfois des scores intermédiaires | Ce n'est pas un flux de détection de pause ; certains scores tennis Betfair/PMU sont connus comme figés |
| ESPN | Scoreboards football, ATP/WTA, NBA/WNBA, NHL, NFL/NCAAF, MLB | Le flux brut peut contenir des états en cours | `_espn_match()` ne conserve ni état de pause ni horloge ; `a_venir` signifie ici « non final », pas une preuve de pré-match. Pas de handball/volley/rugby dans `ESPN_LIGUES` |
| NHL officielle | Calendrier puis `/gamecenter/{id}/landing`, uniquement après 6 h et états `OFF`/`FINAL` | Le calendrier peut exposer horloge/période, adaptateur live à faire | Ne pas réutiliser le validateur final en le faisant passer pour du live multisports |
| The Odds API | Secours résultats ; `_capture()` exige `completed`, cache par ligue | Scores en cours possibles côté fournisseur | Aucun état inter-période conservé ; clés gratuites destinées au règlement, pas à un polling live massif |
| PropLine | Secours résultats ; `status=final`, `live != true`, période vide, attente 6 h | `/scores` gratuit documenté et observé HTTP 200 pour NHL | Le connecteur rejette volontairement le live. Aucun exemple de pause validé. Le paramètre `period` des **marchés** n'est pas une preuve de pause actuelle |
| API-Sports | Secours scores finaux uniquement ; clé retirée par l'utilisateur | Non utilisable actuellement dans ce projet | Ne pas bâtir le live dessus sans rétablir une source opérationnelle |

### Sonde effectivement exécutée

Le 15/10 à **19:41 UTC (21:41 Paris)**, 5 GET publics, sans réessai :

- Pinnacle football : HTTP 200 sur les deux chemins existants ; 579 **lignes
  matchups** marquées `isLive` (racines, enfants et spéciaux confondus), 1 953
  marchés liés. **Ce ne sont pas 579 matchs uniques**, ni 1 953 signaux valides.
- Pinnacle hockey : HTTP 200, 1 ligne live, aucun marché lié dans cette réponse.
- Matchups live : champs `state`, `periods`, `status`, `version`, `liveMode`
  présents dans le schéma observé. Marchés : `version`, `cutoffAt`, `status`,
  `prices` ; aucun horodatage de prix déjà normalisé par notre code.
- Deux lectures ciblées supplémentaires du même endpoint football ont distingué
  472 lignes `special` et 107 `matchup`. Les parents peuvent eux-mêmes avoir un
  `parentId` : compter seulement les lignes sans parent serait faux. Des parents
  observés portent `status="started"` et `state={minutes: 37 ou 38, state: 1}`.
  Ce code numérique **n'est pas interprété comme une pause** ; les `state` des
  spéciaux sont parfois vides. `version` n'est pas assimilé à un timestamp et
  `cutoffAt` est une échéance de marché, pas sa dernière mise à jour.
- Calendrier NHL du jour : HTTP 200, 11 matchs `FUT`. Cette sonde ne permet pas
  de valider un exemple de pause NHL.
- PulseScore et PropLine : non sondés, leurs secrets ne sont pas exposés dans
  l'environnement local. Aucun secret n'a été demandé ni récupéré.

Une source accessible ne signifie pas qu'une paire de prix exécutable pendant
une pause a été vérifiée. Il manque encore cette validation **de bout en bout**.

### Vérification authentifiée dans GitHub Actions

La sonde ponctuelle a ensuite été exécutée avec les secrets existants, **11 GET
environ 11 secondes**, sans écriture sur la branche de données ni notification.
[Run réussi du 15/10 à 19:47 UTC / 21:47 Paris](https://github.com/Matttgic/cotes-value/actions/runs/38796746483).

| Flux | HTTP | Événements sur la page | Sports effectivement observés | État disponible |
| --- | --- | --- | --- | --- |
| Winamax | 200 | 29/29 | 18 foot, 5 basket, 3 handball, 2 hockey, 1 volley | score, horloge et scores par période sur 29 |
| Betclic | 200 | 29/29 | mêmes volumes par sport | score et horloge sur 29 ; pas de `periodScores` |
| Unibet FR | 200 | 29/29 | mêmes volumes par sport | score et horloge sur 29 ; `periodScores` sur 1 |
| PMU | 200 | 29/29 | mêmes volumes par sport | score et horloge sur 29 ; pas de `periodScores` |
| Orbit/Betfair | 200 | 30/52, page suivante non lue | tennis 7, foot 10, basket 5, hockey 1, baseball 1, cricket 4, esport 2 | score sur 21, horloge sur 14 ; carnets back/lay et `updatedAt` dans les champs de marché |
| PropLine NHL | 200 | 78 lignes | NHL seulement, aucun autre sport sondé | `live`, `status`, `period` ; les 5 premiers exemples sont `upcoming`, période nulle |

L'absence de tennis/rugby dans les 29 événements FR à cet instant **ne prouve
pas leur absence de couverture**. Cricket/esport retournés par Orbit restent
hors des 9 sports de ce moteur.

Points bloquants constatés :

- Aucun des champs événement `updatedAt`, `lastUpdated`, `last_update` sur ces
  pages PulseScore. Le `updatedAt` de marché existe chez Orbit ; les marchés
  FR observés n'en exposent pas dans leurs champs. Heure de réception HTTP et
  fraîcheur de confirmation chez le bookmaker ne sont pas interchangeables.
- Unibet hockey : un exemple donne `score=1–0` et `info="OR 1:1"`, un autre
  `score=0–0` et `info="OR 2:0"`. Basket : `score=23–29`, `info="OR 53:70"`.
  Il faut identifier le score de match avant de comparer, pas choisir un champ
  parce qu'il s'appelle `score`.
- PMU volley : `score=9–9`, horloge sans numéro de set dans l'exemple. Winamax
  expose un score en sets et les points de chaque set. **Ne pas les confondre**.
- Unibet et PMU : `running=false` sur des libellés de troisième quart/tiers ;
  cela ne prouve ni une pause réglementaire ni la fin de la période.
- Orbit tennis : des exemples n'ont pas de `matchClock` et donnent des chaînes
  telles que `Set 3-5 (0-0)` ou `Set 5-5 (30-15)`. Impossible d'en déduire une
  pause entre sets sans une règle provider vérifiée.

**Verdict** : les flux live existent réellement avec les accès du dépôt. Les
contrats normalisés et leur fraîcheur ne sont pas encore assez vérifiés pour
brancher automatiquement L1/L2. Le module livré refuse justement ces états
ambigus au lieu de produire de faux edges.

### Fréquence, durée et budgets

`collecte.yml` vise un cycle toutes les 5 min par relance, avec une tâche horaire
de secours. Les jobs partagent une file pour protéger les données ; démarrage,
préparation, collecte et publication ajoutent du délai.

Mesure sur les 50 dernières entrées d'`etat.json` consultées (dernier cycle
15/10 19:35:10 UTC) : intervalle médian **280 s**, minimum **238 s**, maximum
**539 s**. Dernier cycle : 63 appels PulseScore ; séquences Pinnacle 42,7 s,
Polymarket 13,8 s, Kalshi 76,6 s puis PulseScore 29,5 s. Le timestamp
`collecte` de certaines lignes est pris **avant** une série de requêtes.
« Même cycle » ne signifie donc pas « mêmes dix secondes ».

- Football/handball/rugby à la mi-temps, hockey entre tiers et basket à la
  mi-temps : pauses plus longues, mais le cycle courant n'offre aucune garantie
  de détection ni d'envoi avant la reprise.
- Tennis : repos entre sets normalement 120 s (ITF, règle 29).
- Volley : intervalle normalement 3 min (FIVB, règle 18.1).
- Quart-temps basket : notamment 2 min en FIBA ; distinguer NBA/FIBA/NCAA.
- Baseball : pauses entre demi-manches et NFL entre périodes, pas de nouvelle
  « mi-temps universelle ». L1 peut les représenter si les flux le prouvent.

Les pauses courtes nécessitent un worker persistant / WebSocket ou un polling
sélectif bien plus fréquent, **pas** une modification du cron global à 30 s.

Documentation PulseScore consultée : PRO illimité, 1 req/s/bookmaker et 1
WebSocket/bookmaker ; STARTER 30 000/mois, 1 req/min/bookmaker. Le code utilise
1,1 s entre pages par client. Ce sont des limites documentées, pas une
vérification du contrat courant ni une réservation de débit pour le live.
Pré-match et live devront partager un même limiteur par bookmaker.

PropLine Free : 1 000 requêtes/jour documentées ; le secours actuel réserve un
budget local de 800/jour. Une ligue interrogée toutes les 30 s consommerait déjà
2 880 appels/jour sur 24 h (960 sur 8 h), sans compter les résultats existants.
Quatre clés The Odds API Free ne créent ni endpoint de pause ni débit suffisant
pour un système multisports permanent. Les quotas exacts des comptes ne sont
pas supposés connus.

## 2. Architecture proposée

1. **Adaptateurs live distincts** : préserver réponse native, identifiant,
   score, unité, période terminée, statut de pause explicite, état des marchés,
   heure de réception, heure SOURCE, versions, carnet et règles. Aucun changement
   aux adaptateurs pré-match. La sonde n'est pas un adaptateur de production.
2. **Rapprochement canonique vérifié** : sport, compétition, sexe/catégorie,
   équipes/joueurs, format et heure ; orientation DOM/EXT et identifiants natifs.
   Ne pas déduire l'identité du seul score ou de noms approximatifs en live.
3. **Machine d'état** : `unknown → playing → pause_confirmed → playing/final`.
   Une suspension de marché, un score inchangé, « P2 » ou `live=true` ne prouvent
   jamais une pause. Refuser si horloge/statut inconnus ou divergents.
4. **Clôtures complètes distinctes** : figer un snapshot par match/marché avant
   le premier événement live, avec toutes les issues, lignes, timestamps source
   et règles. Ne jamais recalibrer L2 avec des données postérieures au début.
5. **Moteur pur** `cotes/live_pauses.py` : contrats ci-dessous, L1 et L2
   indépendants, refus explicites et résultats papier. Pas d'API ni de secret.
6. **Journal prospectif séparé** : observations, refus, paramètres/version,
   score, prix, délai, prix encore disponible à +15/+30/+60 s et règlement.
   Dédupliquer par match/pause/marché/ligne/issue/bookmaker ; limiter l'exposition
   par match. Aucun mélange avec `paris.json` ou les bilans pré-match.
7. **Notifications live ultérieures** : seulement après validation des
   adaptateurs et de la latence de bout en bout, avec expiration courte et
   revalidation au moment de l'envoi. Aucun branchement réalisé ici.

### Contrats du module livré

- `PauseState` : identifiant commun + identifiant natif + source, cycle,
  `phase="pause"`, frontière `HT`, `P1/P2`, `QT1/QT3`, `SET1…SET4` ou
  `TOPn/BOTTOMn`, score et son unité, horodatages. `context_complete` vaut faux
  par défaut pour L2. Les incidents connus empêchent les projections baselines.
- `Market` : même événement, sport, marché, issue, ligne, unité, scope
  (`REGULATION`, `INCLUDING_OT`, `SETS`) et identifiant de règles. Le contrat
  porte sur la **fin du match entier**, jamais « reste du match ».
- `LiveQuote` : offre explicitement active, identifiant de prix, heure source
  et heure de réception. Aucune heure source inventée à partir de la collecte.
- `fair_reference()` : toutes les issues d'un marché Pinnacle (méthode power,
  marge max 12 %) ou toutes les issues du carnet Betfair back/lay, avec liquidité
  minimale 20 et écart maximal 3 points de probabilité. Marché incomplet refusé.
- `evaluate_l1()` : prix max 30 s, état max 15 s, désynchronisation max 10 s par
  défaut ; âge des prix jamais au-delà de 180 s. Même pause, score, cycle,
  orientation et contrat. Le score/temps source est exigé des deux côtés.
  Betfair utilise une borne prudente de probabilité, pas simplement son midpoint.
- `ClosingContext` : référence Pinnacle/Betfair, snapshot avant début et dans
  les 15 dernières minutes, composants espacés d'au plus 30 s, règles et version.
  Les modèles ne lisent **pas** automatiquement `paris.json` : les preuves
  complètes nécessaires ne sont pas stockées aujourd'hui.
- `evaluate_l2()` : même garde sur l'offre live, contexte non exceptionnel et
  complet ; résultat `experimental_candidate`, toujours `mode="paper"`.
- `Outcome(win, push, loss)` : cote d'équilibre `1 + loss/win` et edge par euro
  `win × (cote − 1) − loss`. Pas de formule `cote × proba − 1` quand un push
  est possible. En L1 une ligne entière est refusée si la probabilité de
  remboursement n'est pas fournie ; les deux cotes seules ne l'identifient pas.

Les paramètres de fraîcheur/edge sont des gardes de recherche, **pas des seuils
de rentabilité validés**. Le module n'établit pas la conformité ANJ d'un marché :
le futur adaptateur devra vérifier la liste des compétitions/types de paris
autorisés et rester sur les bookmakers français couverts.

## 3. Modèles L2 et corrections du prompt

| Sports | Calcul livré | Domaine / abstention |
| --- | --- | --- |
| Football | Poisson indépendant, score acquis + intensités restantes ; calibration 1N2 et total demi-entier | À HT, part de buts de seconde période explicitement fournie ; 0,55 n'est pas une constante universelle. Incidents inconnus/rouge : pas de signal |
| Hockey | Poisson réglementaire, 2/3 après P1, 1/3 après P2 | Pas d'invention d'une proba OT/tirs au but. Baseline insuffisante pour avantage numérique, gardien retiré, évolution du rythme |
| Basket/handball | Différence et total gaussiens résiduels, correction de continuité, masse du nul/push | Sigmas **distincts**, fournis et versionnés ; pas de 11,5/4,5 universels. Réglementaire seulement, pas de traitement OT implicite |
| Tennis/volley | Inversion de `P_match`, récursion sur les sets restant à gagner en format 2 ou 3 sets gagnants | Hypothèse de sets indépendants/stationnaires ; pas de déduction du service, fatigue ou blessure. Format spécial/super tie-break refusé ; proba du set décisif paramétrable |
| Rugby, NFL, baseball | **L1 seulement** | L2 refusé : rugby/NFL demandent notamment un modèle de marques composées/possessions ; baseball un état manches/retraits/coureurs. Un Poisson de buts ou un simple temps restant serait trompeur |

Calibrations :

- `fit_poisson()` inverse d'abord le total sans marge, ajuste la répartition
  DOM/EXT sur le 1N2 et rejette un marché incompatible avec l'hypothèse
  d'indépendance (erreur max 2,5 points par issue par défaut).
- `fit_gaussian()` utilise une ligne handicap et une ligne total demi-entières
  avec leurs probabilités sans marge, ainsi que deux sigmas fournis par profil.
  Une cote vainqueur isolée ne permet pas de retrouver différence, total et
  variances. L'écart-type résiduel est `sigma × sqrt(r)` ; la **variance** est
  `r × sigma²`.
- `fit_sets()` inverse une fonction monotone : en best-of-3 IID,
  `P_match = 3p² − 2p³`. Après perte du premier set, `P_restant = p²` **seulement
  en deux sets gagnants, sous cette hypothèse**. Le modèle général recalcule
  l'état en best-of-5 et peut distinguer un set décisif. Le filtre de rebond L2
  se limite au favori initial ≥ 68 %, ayant perdu SET1, sur son vainqueur match,
  avec edge ≥ 6 %. Ces seuils viennent du prompt, pas d'une validation.

Le résultat du premier set apporte de l'information : réutiliser les forces
pré-match sans les mettre à jour est une baseline, pas une « vraie cote ».
Même problème avec rythme, fautes, composition, score et cartons dans les autres
sports. Les marchés live peuvent intégrer cette information mieux que L2.

Enfin **L1 est de la value relative, pas un arbitrage garanti** : une référence
sans marge n'est pas la probabilité vraie. Une couverture sur un exchange
demanderait prix réellement disponibles, commission, profondeur et exécution.
Pendant une pause les prix peuvent bouger et un bookmaker peut suspendre,
refuser ou retarder un pari. Betfair documente des délais live de 1 à 12 s.

## 4. Validation et prochaine étape concrète

Exécuter les tests sans appeler les fournisseurs :

```sh
python -m pytest -q tests/test_live_pauses.py tests/test_sonde_live_pauses.py
```

Sonde **ponctuelle**, sans cron ni modification des données :

```sh
python scripts/sonde_live_pauses.py --sortie /tmp/audit-live.json
```

Elle lit les clés dans l'environnement si elles existent (jamais en argument),
fait au plus **11 GET** sans réessai, décrit schémas et états, ne révèle pas les
clés et ne produit aucun signal. Une première page n'établit pas la couverture
complète d'un bookmaker. Le script ne change pas le mode des clients existants.

Le workflow `sonde-live.yml` permet la même lecture avec les secrets déjà
configurés dans Actions : lancement manuel ou lors d'une modification de ce
workflow, **aucun cron**. Permissions dépôt en lecture seule, délai max 5 min,
rapport sans secrets conservé comme artefact pendant 7 jours.

Avant tout live opérationnel : compléter la sonde des 4 bookmakers + Orbit par
des pauses/reprises réelles et des exemples par sport,
établir les horodatages source et règles par marché, puis bâtir l'adaptateur
et un petit journal papier **football HT/hockey d'abord**. Mesurer ensuite
fraîcheur, fausses pauses, disponibilité des prix, calibration (Brier/log loss)
et rendement hors échantillon avec regroupement par match. Pas de ROI live
reconstitué à partir des seuls paris pré-match existants.

## Sources primaires consultées

- [PulseScore REST/WebSocket, live-events et limites](https://pulsescore.net/docs)
- [PulseScore : champs live facultatifs](https://pulsescore.net/)
- [PropLine : scores, marchés par période et quotas](https://prop-line.com/docs)
- [Betfair : délais sur marchés live](https://support.developer.betfair.com/hc/en-us/articles/360002825652-Why-do-you-have-a-delay-on-placing-bets-on-a-market-that-is-in-play)
- [ITF : règles 2026, règle 29](https://www.itftennis.com/media/7221/2026-rules-of-tennis-english.pdf)
- [FIVB : règles 2025–2028, règle 18.1](https://www.fivb.com/wp-content/uploads/2025/01/FIVB-Volleyball_Rules2025_2028-EN-v05.pdf)
- [FIBA : règles officielles 2024](https://refereeing.fiba.basketball/en/rule-zone/official-basketball-rules-2024)
- [Dixon et Robinson, 1998 : modèle de buts dépendant du temps/score](https://doi.org/10.1111/1467-9884.00152)
- [Barnett et Clarke, 2005 : modèle tennis à partir des statistiques de service](https://doi.org/10.1093/imaman/dpi001)
