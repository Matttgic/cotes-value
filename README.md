# Cotes Value

Compare **toutes les cotes** des bookmakers français (Winamax, Betclic, Unibet, PMU, OlyBet) à la
**cote juste** de plusieurs références « sharp », et simule les paris qu'on prendrait à chaque erreur
de cote : 10 € par pari, plusieurs seuils, pour savoir lesquels gagnent vraiment.

⚠️ Simulation uniquement. Les paris sportifs comportent un risque de perte.
Jeu responsable : Joueurs Info Service, 09 74 75 13 13.

## Sources

Toutes les cotes sont lues **directement**, sans abonnement : PulseScore (et Betfair, qui n'existait que
par lui) est arrêté depuis le 18/10/2026. `cotes/pulsescore.py` ne fait plus d'appel réseau : il garde le
**traducteur** (`traduire`) qui met les marchés de tous les lecteurs directs dans un vocabulaire commun.

| Source | Rôle | Accès | Coût |
|---|---|---|---|
| Pinnacle | Référence | API publique du site (`cotes/pinnacle.py`) | Gratuit |
| Polymarket | Référence | API officielle gamma (`cotes/polymarket.py`) | Gratuit |
| Matchbook | Référence | API publique edge, sans compte ni clé (`cotes/direct/matchbook.py`) | Gratuit |
| Smarkets | Affiché, hors décision | API publique v3, sans compte (`cotes/smarkets.py`) | Gratuit |
| Winamax | Cotes à comparer | Socket (`cotes/direct/winamax.py`) | Gratuit |
| Betclic | Cotes à comparer | API gRPC-web (`cotes/direct/betclic.py`) | Gratuit |
| Unibet | Cotes à comparer | API LVS (`cotes/direct/unibet.py`) | Gratuit |
| PMU | Cotes à comparer | Kambi (`cotes/direct/pmu.py`) | Gratuit |
| OlyBet | Cotes à comparer | Swarm BetConstruct (`cotes/direct/olybet.py`) | Gratuit |
| NetBet | Cotes à comparer | État Nuxt de netbet.fr (`cotes/direct/netbet.py`) | Gratuit |
| FanDuel | Référence props NBA/NHL | API publique du site (`cotes/direct/fanduel.py`) | Gratuit |
| DraftKings | Référence matchs NBA, NHL, NFL, MLB et props NBA/NHL | API publique du site (`cotes/direct/draftkings.py`) | Gratuit |

Les paris déjà pris contre Betfair ou Kalshi restent dans les bilans ; ces sources ne sont plus interrogées.

Pinnacle a un **secours** facultatif (pinnodds, clé gratuite) quand sa lecture directe échoue ou n'a que des
cotes trop vieilles (cache de 15 min chez Pinnacle depuis le 19/10/2026) : voir
[docs/pinnacle-secours.md](docs/pinnacle-secours.md).

OlyBet et NetBet peuvent être coupés (`SOURCE_OLYBET` ou `SOURCE_NETBET` = `off`).
FanDuel ne sert que de référence pour les props NBA/NHL (`SOURCE_FANDUEL` = `direct`
dans la collecte, `off` sinon) : aucun pari, la stratégie Props FanDuel reste éteinte.
DraftKings joue le même rôle (`SOURCE_DRAFTKINGS`), avec en plus les lignes de match NBA, NHL, NFL et MLB : sa
comparaison à Pinnacle est publiée dans Bilan › Props. Betfair répond 403 depuis GitHub.
[Relevés, Betfair et reverse-api-engineer](docs/sources-us.md).
Betclic « L'équipe possède X buts (points) d'avance ou gagne » (`AVANCE_OU_GAGNE`) est gagné dès que l'équipe gagne :
il est comparé à la cote juste de la **victoire** (1N2 ou vainqueur, même période). L'écart est donc un **minimum**
(`ecart_minimum` sur le pari). Règlement : gagné si l'équipe gagne ou menait de X à la mi-temps, perdu si elle finit
sous X buts, sinon à la main.
Les marchés de hockey et de basket dont le libellé ne dit pas si la prolongation
compte restent en période `MATCH?` et ne sont pas comparés.

Polymarket : la cote juste est le milieu achat/vente quand le carnet est serré (écart ≤ 5 points). Depuis le
8/11/2026, un carnet plus large (jusqu'à 10 points) d'un marché à deux issues est lu au **prix d'achat** : l'écart
obtenu est un minimum, la ligne reste hors du consensus (`prix_prudent` dans la trace). Sont aussi lus depuis cette
date : handicaps de 1re mi-temps et des quarts-temps 1 à 3, totaux par équipe (NFL, NBA…), total de jeux, total de
sets, handicap de sets et vainqueur du 1er set au tennis. Mesure du 8/11 à 3 h (PMU et Winamax) : 15 450 cotes
françaises ont une cote juste Polymarket, contre 14 307 avec l'ancienne lecture (+8 %).

Sur le serveur en direct, le meilleur achat / vente Polymarket vient du **websocket** des carnets quand il est plus
récent que gamma (`cotes/polymarket_flux.py`, voir [docs/serveur-direct.md](docs/serveur-direct.md)).

Smarkets est lu sur son API publique, sans compte. La cote juste est le milieu
achat/vente : le spread est dans le milieu, aucune commission
n'est retirée en plus. Le bilan a une table Smarkets, comme Polymarket :
10 € fictifs quand un bookmaker français bat cette cote juste,
réglés à part. L'écart affiché (écart vs Smarkets) reste à côté.
`SMARKETS_DANS_DECISION` vaut `non` par défaut : Smarkets n'entre pas dans le
consensus partagé. `oui` l'y ajoute, sans changer les autres tables.

Matchbook est une bourse lue sans compte (`SOURCE_MATCHBOOK` = `direct` par
défaut, `shadow` pour lire sans prendre de pari, `off` pour couper). Les paris
value utilisent les mêmes seuils que Pinnacle (2 %, 3 %, 5 %…). Matchbook a sa
colonne dans le bilan et dans le filtre par référence. Il ne rejoint pas le
consensus, et aucune stratégie (Grok, Défi, Gemini Défi, Claude Défi, sélecteurs figés) ne le prend.

## Comment ça marche

Toutes les 5 minutes (`scripts/cycle.py`) ; le règlement des paris, une fois par heure :

1. **Collecte** des références, puis des bookmakers français sur les 36 prochaines heures,
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
   **D** 5 à 7 %, **E** 7 % et plus (cotes ≤ 10), **X** cotes > 10 (≥ 3 %). La cote juste est suivie jusqu'au coup d'envoi (**CLV**).
6. **Règlement** (`cotes/reglement.py`) avec les scores validés par plusieurs sources gratuites (voir
   « Règlement » plus bas), selon le
   règlement officiel (prolongations, tirs au but, abandon au tennis : voir `docs/reglements.md`) ;
   sinon « à régler à la main » sur le site (bouton « Copier » → coller la liste à Claude).
7. **Site** (`scripts/site_web.py`, gabarit `web/modele.html`) publié sur GitHub Pages, en quatre onglets : Paris, Bilan, Notifications, Santé.
   Polices OFL en WOFF2 dans `web/polices/`. La vitrine
   publique (`web/vitrine.html`, deux chiffres Kelly ¼ recalculés à chaque publication) est publiée à part, en
   `vitrine.html`, sans lien depuis l'interface ni bouton de connexion : l'interface reste la page d'accueil.
   La page Santé garde un journal des incidents des dernières 24 heures (`sante_incidents.json`, écrit à chaque cycle par `cotes/surveillance.py`) : pannes, lectures dégradées et refus 403/429 qui durent au moins 3 cycles, avec début, durée et nombre de cycles. Le dépassement de budget n'en fait pas partie.

### Deux stratégies suivies séparément

**Bilan → Stratégie** conserve la stratégie de Claude du 11/10.
**Bilan → ChatGPT** suit une stratégie expérimentale indépendante à compter du
14/10/2026 à 05:15 (Paris) : Pinnacle sans marge, cotes 1,50–3,00, edge 3–12 %,
première détection entre 15 min et 6 h du match, une mise fictive de 10 € par match,
cinq nouvelles mises maximum par jour. « Les paris » de sa fiche (Bilan › Stratégies) donne
ses sélections. Aucun appel API supplémentaire.

[Règles, audit historique défavorable et limites](docs/strategie-chatgpt.md).

**Qwen** (`qwen_persistence`, depuis le 20/10/2026) : Pinnacle, cotes 1,45–3,20, edge ≥ 3,5 %, Winamax et Betclic,
15 min à 2 h avant le match, validée après deux cycles consécutifs, 3 paris par jour au plus.
[Règles et limites](docs/strategie-qwen.md).
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

### Filtres à tester et mise Kelly (Bilan)

Mesures prises à l'enregistrement du pari, **descriptives, jamais appliquées** : TRJ du marché chez le bookmaker
français (`comparaison.taux_retour`), limite de mise de Pinnacle (liquidité du marché sharp) et mouvement de la cote
juste de Pinnacle sur 10 à 60 minutes (`cotes/mouvement.py`, ancres gardées dans le cache Actions à côté de la
reprise). Le pari garde aussi l'âge réel du prix Pinnacle (`age_prix_pinnacle_s`, en-tête `Age` du cache Cloudflare) :
`lu_reference` n'est que l'heure de notre lecture. Seul le mouvement sert aussi de **garde-fou** : une cote Pinnacle de
référence strictement inchangée depuis 10 minutes ou plus (copie de cache figée) rend l'opportunité suspecte
(« cote Pinnacle figée »), pour Pinnacle et pour le Consensus qui la contient. Le Bilan compare le ROI et la CLV par tranche (`simulation.bilan_filtres`). Les anciens paris n'ont pas ces
mesures : les tranches se remplissent au fil des nouveaux paris. Le Bilan montre aussi une mise **Kelly ¼** (bankroll
fictive 1 000 €, 2 % maximum) calculée sur les mêmes paris, à côté des 10 € fixes, ainsi que la part des paris qui
battent la clôture et le profil horaire des détections par bookmaker. Il montre enfin le ROI avec une **mise plafonnée par match** (10, 20 et 30 €, `simulation.bilan_plafond`) : plusieurs paris d'un même match sont corrélés, et un ROI qui ne tient que sans plafond repose sur quelques matchs chargés.

### Claude Opus · Valeur solide (et trois déclinaisons)

Stratégies de Claude, suivies dès le **3/11/2026 à 00:00 UTC**, figées au lancement. Valeur solide : références sharp lues depuis
≤ 180 s, Betclic, Unibet, PMU ou NetBet, cote 1,60–3,50, écart 4–15 %, match dans les 12 h, ni score exact ni
mi-temps/fin. Choisie sur la construction (7–22/10), validée une seule fois (23/10–2/11 : 136 paris, ROI +2,9 %,
CLV +4,2 %). Déclinaisons plus ciblées : Favoris réguliers (cote 1,60–2,20), Hors football, Handicaps.
[Méthode, candidates et limites](docs/strategie-claude-opus.md).

### Claude Signal · Double avis et Prix frais

Deux stratégies de Claude, suivies dès le **12/11/2026 à 00:00 UTC**, figées au lancement. Double avis : Pinnacle et
Polymarket donnent chacun au moins 2 % sur la même cote française. Prix frais : prix Pinnacle de moins de 400 s, sans
mouvement contraire. Cote 1,30–5,00, écart 2–15 %, tous les bookmakers sauf OlyBet. Rejeu du 18/10 au 10/11 : CLV par
match +3,1 % (96 matchs) et +2,0 % (228 matchs), contre +0,3 % sans le signal. Seuils fixés en regardant ces
périodes : pas une validation indépendante. [Mesures et limites](docs/strategie-claude-signal.md).

### Claude · PMU régulier
Stratégie de Claude, suivie dès le **13/11/2026 à 02:00 UTC**, figée au lancement : PMU, référence Pinnacle ou
Polymarket, cote 1,50–3,00, écart 2–7 %, ni score exact ni mi-temps/fin. PMU est le seul bookmaker dont la CLV par
match reste positive sur les trois tiers du 10/10 au 12/11 (+0,7 %, 756 matchs). Choisie parmi 102 sous-ensembles :
pas une validation. [Mesures et limites](docs/strategie-claude-pmu.md).
### Avis d'analyste

Chaque fiche de stratégie porte un verdict (« Fiable », « Prometteur mais pas prouvé », « Chance ou yo-yo », « Trop
tôt pour juger »), ce qu'il faut en faire, et six questions cochées : assez de recul, gain, gain qui ne tient pas à
la chance, cotes qui battent la clôture, régularité, indépendance des grosses cotes (`cotes/analyste.py`). « Fiable »
= six oui. La probabilité que le gain soit un hasard est calculée sans tirage à partir de 30 matchs (point-selle,
même résultat que 10 000 rééchantillons à 0,25 point près) : la construction du site est passée de 54 s à 10 s.

### Note des stratégies sur 100

**Stratégies → Classer par « Note /100 »** (tri par défaut). Version 2 (8/11/2026) : calculée **par match**
(plusieurs paris sur un même match comptent pour un seul match) : rentabilité prudente /25, robustesse /20 (ROI sans
les meilleurs matchs, part du meilleur match), valeur (CLV par match) /25, régularité /15, solidité /15.
[Formule et lecture](docs/notation-strategies.md).

### Stratégies recommandées

En haut de **Stratégies** : les **Recommandées**, liste stable revue tous les 7 jours (≥ 50 matchs, borne basse du
ROI positive, ROI positif sans les meilleurs matchs, aucun match au-delà de 25 % du gain, CLV par match positive, pas
de doublon ; une recommandée ne sort que si elle échoue un critère ou est dépassée de 5 points), chacune avec sa date
d'entrée et son résultat depuis. Puis les **Fusions**, stratégies à part aux membres figés : Fusion 1 réunit les trois
recommandées du 8/11/2026 (un pari par match, suivie depuis le 8/11/2026 à 9 h) ; à chaque révision qui change la
liste, une nouvelle fusion (Fusion 2, 3…) est créée automatiquement avec les recommandées du jour. [Critères, choix et limites](docs/recommandees.md).

### Fiabilité des cotes justes selon la cote

[Étude de calibration](docs/etude-longues-cotes.md) (2/11/2026, 3 689 paris uniques réglés) : jusqu'à une cote de 5,
les cotes justes sont exactes à quelques pour cent près ; au-delà, elles surestiment la probabilité de gain
d'environ moitié (score exact, mi-temps/fin et cotes classiques de 5 à 10).

### Mise des bilans et bankroll (tous les bilans)

Le menu « Mise des bilans » (en haut du site) recalcule **tous** les gains, ROI, CLV pondérés, courbes, segments et
tableaux des stratégies dans le mode choisi : **Kelly ¼** par défaut (plafond 2 %, `simulation.mise_kelly`), Kelly ⅛,
Kelly ½, Kelly ¼ plafonné à 1 %, gain constant, ou mise fixe de 1 % (`cotes/mises.py`, `MODES_BILAN`). Kelly ¼ et la
mise fixe sont dans la page ; les autres modes sont publiés à part (`site/mises/<mode>.json`) et chargés quand on
les choisit. La **bankroll de départ** (1 000 € par défaut) se modifie à côté du menu : la mise de chaque mode ne
dépend que du pari, donc tous les montants sont multipliés par bankroll / 1 000, sans rien recalculer ; ROI, CLV,
notes et avis ne changent pas. Les deux choix restent sur l'appareil. Mêmes paris, seule la mise change : le serveur calcule les deux versions
(`site_web.paris_en_mise_kelly` rejoue les mêmes fonctions sur des copies misées en Kelly) et le navigateur échange
les blocs. Le choix est mémorisé. Seule l'étude figée du 14/10 (règles du laboratoire, `docs/comparaison-strategies.json`)
reste en mises fixes.

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

## Serveur en direct (option)

Un petit serveur (environ 6 €/mois) fait tourner la collecte en continu : cycle toutes les minutes environ,
alertes Pushover en 1 à 2 minutes (les notifications Chrome restent réservées à GitHub Actions). GitHub reste
la roue de secours et reprend tout seul si le serveur s'arrête.
[Commander, installer, vérifier](docs/serveur-direct.md).

## Mise en route

Pinnacle cherche sa clé guest dans cet ordre, sans jamais l'écrire dans les diagnostics :
le champ `api.haywire.apiKey` de `https://www.pinnacle.com/config/app.json` (délai court, mis en
cache pour le cycle), puis le secret GitHub Actions ou la variable `PINNACLE_API_KEY`, puis la
valeur guest historique du code si les deux échouent. Ce secours n'est pas une suppression de la valeur dans le dépôt
ou son historique.
`PINNACLE_AGE_MAX_MIN` (défaut 10) est l'âge maximum, en minutes, du cache Cloudflare pour un match
qui commence dans les 2 heures ; `PINNACLE_AGE_MAX_LOIN_MIN` (défaut 16) celui des autres matchs. Le cache
dure 905 s et d'autres clients le rechargent dès son expiration : un seuil unique de 10 min écartait un
tiers des lectures. Les deux à 16 : plus aucune lecture écartée, références jusqu'à 15 min.
Le délai depuis le réchauffeur ne compte que s'il a renouvelé l'entrée (`fresh`, statut
`MISS`, `EXPIRED` ou `DYNAMIC`). Sinon l'âge est l'en-tête `Age` de la lecture, ou à défaut
l'âge vu à Paris (`age_s`). Au-delà, ou si aucune mesure n'existe, la cote est périmée et ne
déclenche pas de pari. Les corners, les cartons et les paris pair/impair ne sont pas comparés
aux books français (périmètre ANJ).

**Reprise des références** (`cotes/reprise.py`). Un sport que Pinnacle ou Polymarket n'a pas rendu au
cycle (refus 403, panne, budget), même après le secours Pinnacle, reprend les lignes de son dernier passage
réussi, marquées `reprise`. Elles gardent leur heure de lecture d'origine et vieillissent pour de vrai :
âge du cache Pinnacle plus le temps écoulé, ou temps écoulé depuis la lecture pour Polymarket, avec les
mêmes seuils (`PINNACLE_AGE_MAX_MIN`, `PINNACLE_AGE_MAX_LOIN_MIN`). Au-delà, la ligne est oubliée. Les
cotes françaises ne sont jamais reprises : un pari se prend sur un prix lu au cycle même. Un pari pris
contre une référence reprise porte `reference_reprise` dans `preuve_prise`. La panne reste notée dans
l'étape (`ok`, `erreurs`) avec le nombre de lignes reprises (`reprise`). Le fichier
(`reprise/derniere_lecture.json.gz`, environ 2 Mo) vit dans le cache GitHub Actions, pas dans la
branche « donnees ». `REPRISE_CHEMIN` vide : aucune reprise.

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

1. Settings → Pages → Source : **GitHub Actions**.
2. Test : Actions → « Collecte et comparaison » → Run workflow → mode `test`.
3. Collecte automatique : variable de dépôt `COLLECTE_AUTO` = `oui`
   (et `MODE_COLLECTE` = `complet`, valeur par défaut), puis lancer un cycle à la main une fois.
   Chaque cycle relance le suivant 5 minutes après son début (GitHub saute trop souvent les tâches
   planifiées) ; la tâche planifiée horaire redémarre la chaîne si elle s'arrête. Pour arrêter :
   `COLLECTE_AUTO` ≠ `oui`.


Le workflow horaire **Règlement des paris** utilise aussi les secrets optionnels
`THE_ODDS_API_KEY_1` à `THE_ODDS_API_KEY_4` pour les scores manquants, après LiveScore,
ESPN, Flashscore et la source NHL officielle. Chaque compte est vérifié par `/sports` (gratuit), puis les scores
sont lus uniquement pour les compétitions identifiées et les paris compatibles.
Cache partagé `theodds.json`, lecture au plus toutes les 3 heures par compétition,
16 crédits/jour et 500/mois par compte, au plus 4 appels scores par cycle.
Un appel scores coûte 2 crédits et retourne les résultats des 3 derniers jours.
Les doublons de clés n'augmentent pas le quota et les comptes restent une seule source.
[Couverture, règles et diagnostic](docs/theodds.md).

Depuis le 15/10, les comptes API-Sports sont suspendus ; leur lecteur a été retiré du code le 2/11.
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
- `cotes/AAAA-MM-JJ.jsonl.gz` (depuis le 30/10/2026) : historique des cotes PMU, Unibet, Betclic et NetBet,
  en ajout seul : seules les cotes nouvelles ou changées d'un cycle à l'autre, champs réduits
  (`t` heure de lecture, `b` bookmaker, `m` match, `k` marché|période|ligne|issue[|joueur], `c` cote), plus une
  ligne de description (équipes, ligue, début) à la première apparition d'un match (cotes/historique_cotes.py) ;
- `controle.json` : contrôle des intitulés, JSON compact publié au plus une fois par heure (champ `publie`) ;
  la version de chaque cycle reste dans la mémoire de travail.

Mémoire de travail, hors de la branche (gzip, cache GitHub Actions `memoire-`, comme `reprise/`) :
`horizon_direct`, `pinnacle_secours_cache`, `smarkets_cache` et `controle` (cotes/memoire.py). Absente (premier
cycle, cache évincé) : démarrage à froid, le cycle relit tout. Un seul commit et un seul push par cycle.
- `etat.json` : dernier cycle, dernier règlement et historique des 200 derniers relevés ;
- `theodds.json` : scores de secours en cache et compteurs de crédits, sans clés API ;
- `resultats_manuels.json` : règlements à la main, par exemple
  `{"winamax|72036146": {"score": [2, 1], "mi_temps": [1, 0], "corners": [7, 3]}}` ; `periodes` donne le
  score de chaque période (manches de baseball pour les marchés « 5 manches »).

## Études et idées

[Durée de vie des values, CLV maison, origine de la value](docs/duree-values.md)
(`python scripts/etude_duree_values.py --donnees donnees`) · [Idées et suggestions d'interface](docs/idees.md).

## Développement

```bash
pip install -r requirements-dev.txt
python -m pytest -q tests
python scripts/cycle.py --mode test     # cycle réduit, sans clé
```

### Gemini Argon

[Critères et audit de Gemini Argon V1](docs/strategie-gemini.md), suivie depuis
le 14 octobre à 20 h (Paris), dans Bilan, Stratégies et Paris. Rentabilité non démontrée.

### Eden

**Bilan → Eden** et **Stratégies → Eden** suivent les nouvelles détections depuis
le **19 octobre 2026 à 20 h (Paris)**. Pinnacle et Polymarket, cotes 1,30–2,00,
edge 2–12 %, 30 minutes à 24 heures avant le match, une mise fictive de 10 €
par bookmaker français et par match. Le rejeu est positif sur la validation et
sur le test du 17–19 octobre. Cela ne démontre pas une rentabilité future.
[Règles et limites](docs/strategie-eden.md).

## Sécurité et audit

[Configuration, secrets et publication](SECURITY.md).
[Audit de la justesse des bilans](docs/audit-bilans.md) (13/11/2026) : biais, règlement, chiffres refaits par
`scripts/audit_bilans.py`.
[Cote juste](docs/cote-juste.md) (14/11/2026) : méthodes de retrait de la marge et pondérations du consensus
mesurées par `scripts/cote_juste.py` ; aucun changement retenu.
Le retrait complet de la valeur guest Pinnacle reste conditionné à une configuration de remplacement validée. La revue détaillée de cinq moteurs de sélection reste ouverte ; les rapports ne certifient pas une rentabilité future.

## Règlement

Les scores viennent de plusieurs sources gratuites, rapprochées par noms d'équipes et heure (`cotes/resultats.py`) :

| Sport | Sources | Contrôle |
|---|---|---|
| Football | LiveScore, ESPN, Flashscore (secours) | 99,8 % d'accord sur 2 041 matchs déjà réglés |
| Basket | LiveScore, ESPN, Flashscore (secours), 365Scores (deuxième avis) | ~97 % |
| Hockey | LiveScore, NHL officiel, ESPN, Flashscore (secours) | 93,6 % (les écarts sont d'anciens scores du temps réglementaire) |
| Tennis | LiveScore, ESPN, Flashscore (secours) | 96 % |
| Baseball, football américain | ESPN, Flashscore (secours) | baseball 32/32 |
| Handball | Flashscore, 365Scores (deuxième avis) | 56/58 (mesuré avec API-Sports, retiré) |
| Volley | Flashscore, 365Scores (deuxième avis) | 18/18 retrouvés (3 absents) |
| Rugby | Flashscore, 365Scores (deuxième avis) | 11/13 |

**365Scores** (`cotes/scores365.py`, `SCORES_365` = `non` pour couper) donne un deuxième avis au basket, au volley,
au handball et au rugby, où Flashscore était seul : deux sources d'accord règlent tout de suite, un désaccord attend
la saisie à la main.

Une source seule ne règle qu'après 24 h (6 h pour LiveScore, ESPN, NHL, et pour Flashscore au basket, volley,
handball, rugby, snooker et baseball, où il est d'habitude la seule source et ne garde que les matchs terminés).
**Match frère** : un pari sans résultat est réglé par le même match déjà validé chez un autre bookmaker (même
sport, même heure à 15 min, deux équipes à 0,9 ; `resultats.par_freres`). **Report** : une affiche rejouée quelques
jours plus tard n'est un report que si aucune source ne donne de score à la date d'origine. **Correction** : écrire
le bon statut sous l'identifiant d'un pari déjà réglé dans `resultats_manuels.json` le corrige, sans changer sa date
de règlement. **Cohérence** : `resultats_a_saisir.json` liste aussi (`incoherences`) les matchs réglés avec deux
scores différents chez deux bookmakers. `donnees/resultats_a_saisir.json`
liste les matchs qu'aucune source ne règle (un match vu par plusieurs bookmakers n'y figure qu'une fois, avec toutes
ses clés dans `match_ids`), avec le modèle de saisie de `resultats_manuels.json`. Le journal du
cycle indique quelles sources ont réglé les paris (`sources_reglement`). LiveScore et Flashscore sont des flux non
officiels : ils peuvent changer sans préavis.
La page Santé liste aussi les **marchés non reconnus** par bookmaker (`cotes/inconnus.py`,
`donnees/marches_inconnus.json`) : libellés ignorés faute de traduction, chiffres remplacés par #, et ceux apparus
depuis moins de 24 h (souvent un libellé qui a changé).
La page Santé suit la part des paris des 7 derniers jours réglés à la main ou encore à régler, contre les 7 jours
d'avant (`reglement.taux_manuel`) ; au-delà de 5 %, elle passe en alerte : une source de scores décroche.

TheSportsDB (`cotes/thesportsdb.py`, clé publique gratuite ou `THESPORTSDB_API_KEY`) sert de secours pour les paris
restés sans résultat : recherche match par match (20 appels au plus par cycle, cache `donnees/thesportsdb.json`),
score final seulement (pas de tennis, ni de score par période). Seule, elle ne règle qu'après 24 h et jamais au hockey.
