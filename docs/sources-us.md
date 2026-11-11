# DraftKings, Betfair, 365Scores et reverse-api-engineer : ce qui a été mesuré

Relevés du 10/11/2026 depuis GitHub Actions (sortie aux États-Unis), avec `scripts/sonde_sources_us.py`
(Actions → « Sonde des sources US » → Run workflow). Aucune clé, aucun compte.

| Source | Réponse depuis GitHub | Suite donnée |
|---|---|---|
| DraftKings, matchs NBA, NHL, NFL | HTTP 200 en 0,1 à 0,3 s : Moneyline, Spread ou Puck Line, Total | Lecteur `cotes/direct/draftkings.py` |
| DraftKings, MLB | HTTP 200, hors saison : un seul pari de long terme | Lu avec les mêmes noms de marché à la reprise ; le handicap (« Run Line ») n'a pas été observé et n'est pas traduit |
| DraftKings, props NBA (points, rebonds, passes, tirs à 3 points) et NHL (tirs, points, passes) | HTTP 200, un marché plus/moins par joueur | Même lecteur |
| Betfair Exchange | **HTTP 403**, page « Betfair » en HTML | Pas lisible depuis GitHub : voir plus bas |
| 365Scores (scores) | HTTP 200, liste `games` par sport et par jour | Lecteur `cotes/scores365.py` (règlement) |
| Sofascore (scores) | HTTP 403 | Écarté |

## DraftKings

Référence seule, comme FanDuel : Matthieu ne peut pas y parier, aucune stratégie ne s'en sert. Onze appels par
cycle (quatre ligues, sept sous-catégories de props). La marge est retirée par la même méthode que pour Pinnacle.
Chaque cycle compare à Pinnacle et publie sur la page **Bilan › Props** :

- props NBA et NHL : lignes rapprochées (même joueur, même statistique, même ligne, même rencontre), écart moyen de
  probabilité juste, part des lignes où les deux désignent le même favori ;
- matchs NBA, NHL, NFL, MLB : même chose pour le vainqueur, le handicap et le total, par sport.

`SOURCE_DRAFTKINGS` vaut `direct` dans la collecte GitHub (variable de dépôt `SOURCE_DRAFTKINGS` = `off` pour couper)
et `off` partout ailleurs (tests, serveur hors des États-Unis). DraftKings abrège les villes (« MIL Bucks ») : le
lecteur garde le surnom (« Bucks »), qui se rapproche mieux du nom complet des autres sources.

Pas encore fait : afficher l'écart contre DraftKings sur chaque pari (comme Polymarket et Smarkets), et s'en servir
comme second avis pour les props. À décider après quelques jours de comparaison publiée : si l'accord avec Pinnacle
est faible, DraftKings n'apporte rien comme référence.

## Betfair

Le lecteur existe (`cotes/direct/betfair.py`, football et tennis) mais Betfair refuse la France, l'Allemagne et les
États-Unis. Depuis GitHub : HTTP 403 mesuré. Trois voies, de la plus simple à la plus lourde :

1. **Le serveur en direct** (docs/serveur-direct.md), s'il sort par un pays accepté : c'est le cas prévu par le
   code (`SERVEUR_DIRECT=oui`). Rien à écrire. Le dernier cycle publié venait de GitHub : Betfair y était éteint.
2. **Un relais Supabase** dans une région acceptée (Londres, Dublin ou Stockholm), sur le modèle de
   `pinnacle-rechauffe` qui force déjà Paris par l'en-tête `x-region`. Gratuit, sans serveur. Pas écrit : rien ne
   permet de vérifier d'ici que Betfair accepte les adresses de ces centres de données.
3. **The Odds API** (clés déjà utilisées pour les scores) : donne Betfair et DraftKings, mais 500 crédits par mois et
   par compte, soit deux ou trois relevés par jour pour quatre ligues. Trop peu pour détecter des écarts.

Pour les sports américains, le lecteur Betfair ne connaît que le football et le tennis. Les types de marché du
basket, du hockey, du football américain et du baseball n'ont pas pu être relevés (403) : ils ne sont pas devinés.

## reverse-api-engineer

`kalil0321/reverse-api-engineer` est un outil en ligne de commande : il ouvre un navigateur (piloté à la main ou par
un agent), enregistre le trafic réseau du site dans un fichier HAR, puis fait écrire un client d'API par un modèle
de langage. Ce qu'il change pour ce projet :

- il **accélère la découverte** des adresses d'un bookmaker pas encore lu (ParionsSport, Bwin, Vbet, ZEbet, ou les
  props de Betclic) : une session de navigation donne les appels à reproduire ;
- il **ne contourne rien** : ni le blocage par pays (il faut naviguer depuis un pays accepté), ni les protections
  anti-robot (son README le dit : « sites with aggressive bot detection may block capture »), ni les connexions
  WebSocket ou gRPC que Winamax et Betclic utilisent et que le projet lit déjà à la main ;
- le client généré n'a ni les budgets de temps, ni la traduction des marchés, ni les tests du projet : c'est un
  brouillon à réécrire dans `cotes/direct/`.

Usage conseillé : sur ton ordinateur, en France, une capture par bookmaker à ajouter, puis l'écriture du lecteur à
partir du HAR. Pas d'intégration dans le cycle. Pour les sources américaines, la sonde de ce dépôt fait le même
travail depuis GitHub sans navigateur.
