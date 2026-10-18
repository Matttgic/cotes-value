# Cotes Value

Compare **toutes les cotes** des bookmakers français (Winamax, Betclic, Unibet, PMU, OlyBet) à la
**cote juste** de plusieurs références « sharp », et simule les paris qu'on prendrait à chaque erreur
de cote : 10 € par pari, plusieurs seuils, pour savoir lesquels gagnent vraiment.

⚠️ Simulation uniquement. Les paris sportifs comportent un risque de perte.
Jeu responsable : Joueurs Info Service, 09 74 75 13 13.

## Sources

| Source | Rôle | Accès | Coût |
|---|---|---|---|
| Pinnacle | Référence | API publique du site (`cotes/pinnacle.py`) | Gratuit |
| Polymarket | Référence | API officielle gamma (`cotes/polymarket.py`) | Gratuit |
| Betfair Exchange | Référence | PulseScore, via Orbit Exchange | Offre PulseScore |
| Winamax, Betclic, Unibet | Cotes à comparer | PulseScore (`cotes/pulsescore.py`) | Offre PulseScore |
| PMU | Cotes à comparer | Kambi en parallèle de PulseScore (`cotes/direct/pmu.py`) | Gratuit |
| OlyBet | Cotes à comparer | Swarm BetConstruct (`cotes/direct/olybet.py`) | Gratuit |

NetBet n'est pas suivi : le flux « netbet » de PulseScore est celui du site international (netbet.com), pas
de netbet.fr (intitulés anglais, corners, handicaps asiatiques en quart, compétitions hors liste ANJ).

Vérifications faites (workflow « Vérifications des sources ») :
- Pinnacle lu directement = PS3838 de PulseScore : 98 % des 4 161 cotes à moins de 1 % d'écart ;
- Polymarket lu directement = PulseScore : 87 % des marchés strictement identiques
  (les écarts restants : marchés sans échanges, écartés par le comparateur).

PMU peut être lu sur l'API Kambi (`SOURCE_PMU`, défaut `shadow`). En `shadow`, PulseScore
reste la source des paris et un rapport `pmu_comparaison.json` compare les deux flux.
`auto` prend Kambi et revient à PulseScore si la lecture échoue. `direct` ne lit plus PMU
chez PulseScore. `pulsescore` désactive Kambi. Le rapport est prêt à basculer à partir de
95 % des matchs retrouvés et 99 % des cotes communes à ±0,01. Les paris déjà pris contre
Kalshi restent affichés ; Kalshi n'est plus interrogé.

OlyBet est lu en direct (`SOURCE_OLYBET`, défaut `direct`). `off` coupe cette lecture.
Les marchés de hockey et de basket dont le libellé ne dit pas si la prolongation
compte restent en période `MATCH?` et ne sont pas comparés.

## Comment ça marche

Toutes les 5 minutes (`scripts/cycle.py`) ; le règlement des paris, une fois par heure :

1. **Collecte** des références, puis des bookmakers français et de Betfair sur les 36 prochaines heures,
   seulement pour les sports où une référence a des matchs.
2. **Traduction** des marchés dans un vocabulaire commun (`cotes/marches.py`) : résultat, vainqueur,
   remboursé si nul, double chance, handicaps (asiatique et à 3 issues), totaux, totaux par équipe,
   corners, jeux et sets au tennis, les deux équipes marquent, score exact, mi-temps/fin de match ;
   par période (mi-temps, périodes, quart-temps, sets). Les cas ambigus sont écartés plutôt que devinés.
3. **Association des matchs** entre sources (`cotes/correspondance.py`) : heure, noms d'équipes
   (pays et villes en français, initiales, noms tronqués, U21, féminin).
4. **Comparaison** (`cotes/comparaison.py`) : écart = cote française × probabilité juste − 1, pour
   chaque référence fiable lue à moins de 15 minutes d'intervalle ; plus un **consensus** (moyenne
   des références disponibles).
5. **Paris simulés** (`cotes/simulation.py`) : 10 € à la première détection, un pari par référence,
   bookmaker et sélection, rangé dans la tranche de son écart : **A** 2 à 3 %, **B** 3 à 4 %, **C** 4 à 5 %,
   **D** 5 à 7 %, **E** 7 % et plus (cotes ≤ 10), **X** cotes > 10 (≥ 3 %). La cote juste est suivie jusqu'au coup d'envoi (**CLV**). Référence témoin
   **Pinnacle brut** : la cote affichée par Pinnacle, marge comprise, pour mesurer ce que change le retrait
   de la marge.
6. **Règlement** (`cotes/reglement.py`) avec les résultats PulseScore du bookmaker du pari, selon son
   règlement officiel (prolongations, tirs au but, abandon au tennis : voir `docs/reglements.md`) ;
   sinon « à régler à la main » sur le site (bouton « Copier » → coller la liste à Claude).
7. **Site** (`scripts/site_web.py`) publié sur GitHub Pages, en onglets : À jouer, Bilan, Paris, À régler.

### Deux stratégies suivies séparément

**Bilan → Stratégie** conserve la stratégie de Claude du 11/10.
**Bilan → ChatGPT** suit une stratégie expérimentale indépendante à compter du
14/10/2026 à 05:15 (Paris) : Pinnacle sans marge, cotes 1,50–3,00, edge 3–12 %,
première détection entre 15 min et 6 h du match, une mise fictive de 10 € par match,
cinq nouvelles mises maximum par jour. Le bouton « Voir les paris ChatGPT » donne
ses sélections. Aucun appel API supplémentaire.

[Règles, audit historique défavorable et limites](docs/strategie-chatgpt.md).
Le backtest de conception est exclu du bilan prospectif : rentabilité non démontrée.

### JULES EDGE v1

**Bilan → JULES EDGE** et **Stratégies → JULES EDGE V1** suivent les nouvelles
détections depuis la première publication du code de Jules, le **14/10/2026 à
23:04:13 (Paris)**. Pinnacle, cotes 1,30–2,50, edge 3–12 %, 15 min à 12 h avant
le match, référence de 5 min maximum, une sélection par match et six par jour.
Mise fictive de 10 € ; les lignes du tableau ouvrent les paris sélectionnés.

Le rejeu complet au relevé du 14/10 à 23:03:59 compte **26 sélections, 21 réglées,
+27,90 € et +13,29 % de ROI**. Ce passé est exclu du suivi après lancement.
Les anciens chiffres annoncés par Jules ne correspondent pas au code livré.
Voir [audit et limites](docs/strategie-jules.md), [rapport figé](docs/strategie-jules.json)
et `scripts/verifier_strategie_jules.py`. Aucune rentabilité future démontrée.

### Jules v2 reconstruite

**Bilan → JULES EDGE v2** et **Stratégies → JULES EDGE V2** reprennent l'intention
de Jules avec une identité des matchs reliée entre Pinnacle, Betfair et Polymarket.
Cotes 1,30–2,80, edge 2,5–12 %, 15 min à 18 h avant le match, référence de 5 min
maximum, une mise par événement identifiable et huit par jour au plus.
Mise fictive de 10 €. Suivi à partir du **15/10/2026 à 00:30 (Paris)**.

Sur le relevé commun 7–13 octobre : **34 sélections, 30 réglées, +38,30 €,
ROI +12,77 %**, contre +13,50 % pour Claude. Résultat exploratoire, sans
supériorité démontrée ; le suivi exclut ces gains passés. La v1 reste inchangée.
[Protocole](docs/protocole-jules-v2.md), [audit et limites](docs/strategie-jules-v2.md),
[rapport reproductible](docs/strategie-jules-v2.json).

### M3 MultiSport Value (analyse historique)

**Stratégies → M3 · MultiSport** présente un nouveau comparateur expérimental :
basket, baseball et handball ; Pinnacle/Betfair/Polymarket ; vainqueur,
handicap, total du match et total équipe extérieure ; cotes 1,30–3,00,
edge 2–12 %, contrôle conforme et référence fraîche. Sur le relevé figé
du 7 au 13/10, **69 paris réglés, +310,70 € à 10 € fictifs** (ROI +45,03 %),
contre +214,70 € pour le rejeu Claude. **Les règles M3 ont été choisies
après avoir vu les résultats : ce n'est pas une validation indépendante.**
Plusieurs sélections du même match sont corrélées ; aucune rentabilité future
ne peut être déduite de ce chiffre.

Les nouvelles sélections M3 sont suivies uniquement à partir du **15/10/2026**
sur le site, avec un panneau qui affiche les matchs et les paris sélectionnés.
Voir [règles et limites](docs/strategie-m3.md) et
[rapport chiffré](docs/strategie-m3.json).

### Laboratoire de comparaison

**Stratégies** affiche les 36 règles, Claude et ChatGPT V1 dans un tableau triable
avec effectifs, réussite, ROI, gains, pertes, gain net et graphique comparatif.
Le laboratoire détaillé reste accessible sous ce tableau. Il compare 36 règles avec un découpage chronologique et
suit leurs nouvelles sélections à partir du 14/10/2026 à 14 h (Paris).
Aucune candidate ne satisfait le protocole initial : aucune rentabilité future
n'est annoncée. La V1 reste un témoin expérimental, pas une stratégie validée.
Les simulations se recoupent et leurs mises ne s'additionnent pas.

[Résultats et limites](docs/comparaison-strategies.md) ·
[Protocole figé](docs/protocole-comparaison.md) ·
[Notebook exécuté](notebooks/comparaison-strategies.ipynb).

## Mise en route

Pinnacle cherche sa clé guest dans cet ordre, sans jamais l'écrire dans les diagnostics :
le champ `api.haywire.apiKey` de `https://www.pinnacle.com/config/app.json` (délai court, mis en
cache pour le cycle), puis le secret GitHub Actions ou la variable `PINNACLE_API_KEY`, puis la
valeur guest historique du code si les deux échouent. Les sondes et le journal papier utilisent
le même constructeur d'en-têtes. Ce secours n'est pas une suppression de la valeur dans le dépôt
ou son historique.
`PINNACLE_AGE_MAX_MIN` (défaut 10) est l'âge maximum, en minutes, du cache Cloudflare.
Le délai depuis le réchauffeur ne compte que s'il a renouvelé l'entrée (`fresh`, statut
`MISS`, `EXPIRED` ou `DYNAMIC`). Sinon l'âge est l'en-tête `Age` de la lecture, ou à défaut
l'âge vu à Paris (`age_s`). Au-delà, ou si aucune mesure n'existe, la cote est périmée et ne
déclenche pas de pari. Les corners, les cartons et les paris pair/impair ne sont pas comparés
aux books français (périmètre ANJ).

Les runners GitHub sont aux États-Unis : Pinnacle ne répond 200 que si le cache Cloudflare
est déjà rempli (jusqu'à 900 s). La fonction `supabase/functions/pinnacle-rechauffe/index.ts`
(nom `pinnacle-rechauffe`) relit les mêmes URL depuis Paris et renvoie seulement le chemin
retenu. `verify_jwt` est désactivé dans `supabase/config.toml` ; la fonction exige l'en-tête
`x-secret`, égal au secret de fonction `RECHAUFFEUR_SECRET`.

Déploiement sur le projet **EdgeScope** (ref `tapotyftgyacbnjmeovn`), exécution forcée à Paris :

```bash
supabase secrets set RECHAUFFEUR_SECRET=… --project-ref tapotyftgyacbnjmeovn
supabase functions deploy pinnacle-rechauffe --project-ref tapotyftgyacbnjmeovn
```

Le client envoie `x-region: eu-west-3`. Secrets GitHub Actions à créer :
`PINNACLE_RECHAUFFEUR_URL` =
`https://tapotyftgyacbnjmeovn.supabase.co/functions/v1/pinnacle-rechauffe`
et `PINNACLE_RECHAUFFEUR_SECRET` (la même valeur que `RECHAUFFEUR_SECRET`).
Les deux vides : pas d'appel, la collecte continue. `PINNACLE_PROXY_URL` est un secours
facultatif qui remplace l'hôte de l'API guest.
`.env.example` ne contient aucune clé et les fichiers `.env` sont ignorés. Python ne les charge pas
automatiquement : exporter les variables avant l'exécution. Les diagnostics n'affichent jamais les clés.

1. Secret `PULSESCORE_KEY` (Settings → Secrets and variables → Actions → Secrets).
2. Settings → Pages → Source : **GitHub Actions**.
3. Test : Actions → « Collecte et comparaison » → Run workflow → mode `test` (≈ 4 requêtes).
4. Collecte automatique (avec PulseScore PRO) : variable de dépôt `COLLECTE_AUTO` = `oui`
   (et `MODE_COLLECTE` = `complet`, valeur par défaut), puis lancer un cycle à la main une fois.
   Chaque cycle relance le suivant 5 minutes après son début (GitHub saute trop souvent les tâches
   planifiées) ; la tâche planifiée horaire redémarre la chaîne si elle s'arrête. Pour arrêter :
   `COLLECTE_AUTO` ≠ `oui`.

Coût en requêtes : `python scripts/simulation_appels.py` (≈ 337 000/mois pour les 4 bookmakers +
Betfair toutes les 5 min : offre PRO nécessaire ; l'offre gratuite ne sert qu'aux tests).

Le workflow horaire **Règlement des paris** utilise aussi les secrets optionnels
`THE_ODDS_API_KEY_1` à `THE_ODDS_API_KEY_4` pour les scores manquants, après PulseScore,
ESPN et la source NHL officielle. Chaque compte est vérifié par `/sports` (gratuit), puis les scores
sont lus uniquement pour les compétitions identifiées et les paris compatibles.
Cache partagé `theodds.json`, lecture au plus toutes les 3 heures par compétition,
16 crédits/jour et 500/mois par compte, au plus 4 appels scores par cycle.
Un appel scores coûte 2 crédits et retourne les résultats des 3 derniers jours.
Les doublons de clés n'augmentent pas le quota et les comptes restent une seule source.
[Couverture, règles et diagnostic](docs/theodds.md).

Depuis le 15/10, les workflows n'utilisent plus les comptes API-Sports suspendus.
Le secret optionnel **`PROPLINE_API_KEY`** active un secours supplémentaire :
scores gratuits Prop-Line, uniquement pour les marchés et compétitions compatibles.
Cache `propline.json`, une lecture par compétition au plus chaque heure,
24 appels maximum par cycle, plafond local de 800/jour et réserve de 100 appels
sur le quota communiqué par l'API. Aucun endpoint payant n'est appelé.
[Configuration, limites et diagnostic Prop-Line](docs/propline.md).

## Données (branche `donnees`)

L'onglet **Notifications** permet de choisir ses stratégies et de recevoir leurs
nouvelles sélections via Chrome sur Android, même lorsque l'onglet est fermé.
Activer depuis le téléphone puis utiliser **Envoyer un test**. Les alertes
suivent les scans et ne garantissent pas que la cote reste disponible.
[Fonctionnement, confidentialité et vérifications](docs/notifications.md).

- `paris.json` : tous les paris simulés (statut, gain, CLV), avec leur trace depuis le 7/10/2026 :
  `preuve_prise` (match de référence, équipes inversées ou non, références d'un consensus, état du contrôle
  de l'intitulé, version du moteur) et `preuve_reglement` (score retenu, ses sources ou la saisie manuelle,
  scores par période comparés à la ligne) ;
- `opportunites/AAAA-MM-JJ.jsonl.gz` : toutes les erreurs de cote détectées ;
- `etat.json` : dernier cycle, requêtes PulseScore par mois ;
- `theodds.json` : scores de secours en cache et compteurs de crédits, sans clés API ;
- `resultats_manuels.json` : règlements à la main, par exemple
  `{"winamax|72036146": {"score": [2, 1], "mi_temps": [1, 0], "corners": [7, 3]}}` ; `periodes` donne le
  score de chaque période (manches de baseball pour les marchés « 5 manches »).

## Développement

```bash
pip install -r requirements-dev.txt
python -m pytest -q tests
python scripts/cycle.py --mode test     # nécessite PULSESCORE_KEY ; sans clé : références seules
```

### Gemini Argon

[Critères et audit de Gemini Argon V1](docs/strategie-gemini.md), suivie depuis
le 14 octobre à 20 h (Paris), dans Bilan, Stratégies et Paris. Rentabilité non démontrée.

### Recherche live pendant les pauses

L’audit des flux et l’architecture sont décrits dans [docs/live-pauses.md](docs/live-pauses.md).
Le module `cotes/live_pauses.py` calcule L1/L2 uniquement sur des observations vérifiées, en mode papier.
Il n’est relié ni au cycle de production, ni aux mises, ni aux notifications.
Une sonde ponctuelle est disponible dans `scripts/sonde_live_pauses.py`.

Le [journal papier Live](docs/journal-live-papier.md) observe les pauses longues
dans un fichier isolé de la branche données, avec délais réels et prix revus à
+15/+30 s. Les données non vérifiées restent des observations refusées.

## Sécurité et audit

[Configuration, secrets et publication](SECURITY.md) · [Audit consolidé du 17 octobre 2026](docs/audit-final-consolide-2026-10-17.md).
Le retrait complet de la valeur guest Pinnacle reste conditionné à une configuration de remplacement validée. La revue détaillée de cinq moteurs de sélection reste ouverte ; les rapports ne certifient pas une rentabilité future.
