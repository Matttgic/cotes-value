# Audit fiabilité du 26/11/2026

## Verdict

La collecte tient : 2 086 cycles en 7 jours, un cycle toutes les 4,8 min (médiane), aucun 429. Les pertes réelles
viennent surtout de deux refus isolés, propres au runner GitHub : l'accueil Unibet (3,8 % des cycles) et le socket
Winamax (3,1 %). Des reprises dans le même cycle n'y changent rien. La page Santé affichait aussi de fausses alertes
longues : 162 cycles Pinnacle « réseau indisponible » alors que la lecture était normale, et 163 cycles où une
erreur bénigne masquait la vraie cause. Ces deux défauts sont corrigés. Workflows, secrets et dépendances sont sains,
avec deux durcissements.

Mesures faites le 26-27/11/2026 sur la branche `donnees` au commit `2737020` (26/11 23:05 UTC), du 20/11 au 26/11
inclus. Sources : `sante_historique.json`, `sante_incidents.json`, `etat.json`, `releves/` (2 086 relevés),
`pushover_envoyes.json` et `notifications_diagnostic.json`.

## Santé par source (20-26/11)

| Source | Panne ou refus (cycles) | Cycles sans lecture fraîche | Cause |
|---|---|---|---|
| Pinnacle | 557 refus 403 (125 incidents) ; 169 « réseau indisponible », dont 162 d'affilée | 9 / 2 086 | 403 aléatoires, déjà repris. Le 25/11, l'erreur restait notée après une reprise réussie (**corrigé**) |
| Unibet | 79 « accueil HTTP 403 » (76 incidents d'un cycle) | 79 (3,8 %) | DataDome refuse l'IP du runner. Le second tour ajouté le 25/11 n'a rien changé : 11 incidents le 25/11, 22 le 26/11 |
| Winamax | 63 « CurlError 22 » (61 incidents d'un cycle) | 64 (3,1 %) | Socket refusé pendant les 5 ouvertures (1 à 8 s) : refus par IP, non par délai |
| Betclic | 80 « trame incomplète », dont 73 d'affilée le 22/11 | 10 | Une réponse gRPC tronquée par cycle, sans reprise. Le volume restait normal (≈ 24 000 lignes) |
| PMU | 6 « HTTP 410 » | 6 | Ponctuel |
| Polymarket | 3 « HTTP 422 » | 3 | Ponctuel |
| Matchbook, FanDuel, DraftKings | 4, 6, 1 | 4, 0, 0 | Ponctuel |
| Smarkets | 0 | 1 562 (75 %) | Cache de 15 min réutilisé, hors décision (`smarkets_dans_decision: false`) : voulu |

Autres mesures :

- **429** : aucun sur les 1 803 incidents archivés depuis le 25/10.
- **Budget** : 1 coupure dure en 7 jours (Pinnacle « budget dépassé »). Les lectures partielles « budget » ne sont
  pas archivées : seul le dernier cycle les montre (Winamax : 76,2 s sur 80).
- **Cadence** : le 26/11 de 07:09 à 23:03, 201 cycles, écart de 2,9 à 5,3 min. Le dernier cycle a duré 106 s.
- **Cycles en incident** : 1 642 sur 2 086 (79 %), surtout la dérive et les refus Pinnacle.
- **Dérive** : 244 cycles du 23/11 03 h au 25/11 03 h, puis 111 cycles jusqu'au 27/11 (correctif du 25/11).
  3 incidents sur 59 reprennent moins de 11 min après le précédent, ce qui donne une nouvelle alerte.

## Corrections

| Correctif | Mesure qui le justifie | Test |
|---|---|---|
| `pinnacle._get` : une erreur réseau, 408 ou 5xx n'est notée que si la requête échoue au final. Un 5xx repris ne déclenche plus le secours pinnodds | 162 cycles d'alerte du 25/11 14:15 au 26/11 03:14, avec ≈ 107 000 lignes et 1 400 matchs Pinnacle par cycle | 4 tests |
| `surveillance.problemes` : le détail d'une alerte est la première erreur non bénigne | 163 cycles d'alerte affichés « sport N matchups : HTTP 403 » | 2 tests |
| `securite.verifier_public` : Pushover (×2), réchauffeur, webhook, Healthchecks, `GITHUB_TOKEN` et `GH_TOKEN` sont comparés à l'identique avant publication | 7 secrets présents dans l'environnement qui construit le site, sans forme que `detections` reconnaisse | 8 tests |
| `tests.yml` : `timeout-minutes: 20` | C'était la seule tâche sans limite sur 10 workflows (6 h par défaut). La suite prend ~2 min 30 | 1 test |
| Service systemd durci : `NoNewPrivileges`, `PrivateTmp`, `ProtectSystem=full`, protection du noyau et des cgroups | Le service n'avait aucune directive de durcissement | 1 test |

Tous ces tests sont dans `tests/test_audit_26_11_fiabilite.py`. Sur l'ancien code, 12 échouent et 4 vérifient la
non-régression.

## Points vérifiés sans défaut

- **Workflows** : actions épinglées par SHA et `permissions: {}` par défaut. Aucun `${{ github.event.* }}` ni
  `inputs.*` libre dans `run:` (seulement dans `env`, ou des constantes). Aucun `|| true`. Collecte, règlement et
  archivage partagent le groupe `donnees`, et le push reprend 3 fois après un rebase. Healthchecks ne reçoit un
  signal qu'après un cycle et un push réussis.
- **Fonctions Supabase** : OIDC limité au dépôt, à la branche et à `collecte.yml`. CORS limité à une origine,
  corps borné à 200 ko, liens limités aux sites des bookmakers.
- **Dépendances** : `pip-audit` ne trouve aucune vulnérabilité dans `requirements.txt` ni dans
  `requirements-dev.txt`. Toutes les versions sont à jour sauf certifi (2026.10.23 → 2026.11.20), que Dependabot
  met à jour chaque semaine.
- **Pushover** : 162 ids envoyés du 24/11 au 26/11 (101 alertes, 59 relances de statut). Sur 100 cycles du 26/11,
  20 envois, 0 échec, 0 erreur. Aucun doublon n'est visible : le fichier est indexé par id.

## Recommandations non faites

| Sujet | Pourquoi pas ici |
|---|---|
| Refus Unibet et Winamax liés à l'IP du runner | Aucune reprise dans le cycle n'y change rien. Seule une IP fixe règlerait le problème (serveur en direct, `docs/serveur-direct.md`) |
| Délai de 10 s des matchups Pinnacle : le 25/11, le premier essai échouait à chaque cycle, ce qui coûte jusqu'à 12 s sur 45 | Non confirmé, car la durée de chaque essai n'est pas journalisée. Ajouter un compteur `reprise_reseau` dans `choix_prix` |
| Même défaut que Pinnacle dans `polymarket._get` | Aucun effet sur les alertes : Polymarket n'est pas dans `SURVEILLEES_DEGRADE` |
| Betclic « trame incomplète » sans reprise | Il faut d'abord savoir quelle requête est tronquée (73 cycles d'affilée, probablement une même réponse volumineuse) |
| Flashscore « format inattendu » (snooker, rugby, dernier règlement) | Cause invérifiable sans réseau |
| `journal["surveillance"]` est écrit après `etat.json`, donc une erreur de surveillance n'est jamais conservée | Hors périmètre (`cotes/pipeline/sauvegarde.py`) |
| Dérive : l'alerte est oubliée après un seul cycle sans constat (3 nouvelles alertes en 7 jours) | Effet faible |
| `serveur/env.exemple` ne contient pas `THE_ODDS_API_KEY_1` | Peut-être voulu (clé 1 réservée à GitHub) : à confirmer |
