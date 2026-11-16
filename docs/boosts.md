# Cotes boostées

Ajouté le 16/11/2026. Code : `cotes/direct/winamax.py` (`lire_boosts`, `boosts_depuis`), `cotes/direct/boosts_sites.py`
(Unibet, NetBet, OlyBet, `lire_tous`), `cotes/boosts.py`
(traduction des intitulés, value, suivi), `cotes/pipeline/analyse.py` (`boosts_du_cycle`), `web/boosts.js` (onglet
**Boosts**), `cotes/alertes/promos.py` (Pushover). Sonde : `scripts/sonde_boosts.py` (Actions → « Sonde cotes
boostées »).

## Où sont les boosts (sondes du 16/11/2026)

Les lecteurs Unibet, NetBet et OlyBet viennent du dépôt **cotes-boostees** (fork du 16/11), qui les lisait par un
proxy français payant. Depuis GitHub, sans proxy (`scripts/sonde_boosts.py`) :

| Bookmaker | Accès sans proxy | Lecture (`cotes/direct/boosts_sites.py`, `cotes/direct/winamax.py`) |
|---|---|---|
| Winamax | oui | route `sport:100000` du socket : cote d'avant (`previousOdd`) et mise max (« mise max 20 € ») |
| Unibet | oui (page 200) | page /cotes-boostees (état « serverApp-state ») et page de chaque paquet ; « (2,50 -> 2,75 / Mise max 25€) » |
| NetBet | oui (page 200) | page /super-cotes (état Nuxt, même lecteur que la collecte) ; cote d'avant non publiée, mise max 10 € |
| OlyBet | oui (API swarm) | `get_boosted_selections` puis `get` ; cote d'avant non publiée, gain net plafonné à 25 € |
| Genybet, Betsson | **non** (403, IP non française) | non lus |
| Betclic, PMU | — | aucun boost dans ce que la collecte lit (PMU : boosts visibles seulement connecté) |

Les paris de saison (« 26/27 », « playoffs »…) sont gardés mais pas évalués (« pari à long terme »).

Exemples : Winamax « Carlos Alcaraz gagne par au moins 6 jeux d'écart » 2,80 (au lieu de 2,50) ; Unibet « Montauban
gagne et Johnny Matthews marque au moins 1 essai » 2,75 (2,50) ; NetBet « Lille (vs Arsenal) marque au moins 1 but »
2,10 ; OlyBet « Paris SG gagne et les 2 équipes marquent » 4,50.

## Ce que l'historique de cotes-boostees a déjà mesuré

`analyses/conseil-initial.json` du dépôt cotes-boostees (8/11/2026) : **979 boosts réglés** (Winamax, Unibet,
OlyBet, Genybet, NetBet, Betsson, du 10/10 au 8/11) : 305 gagnés pour 322 attendus d'après leurs cotes, **ROI −6,6 %**
en les jouant tous. Seule sélection positive, jugée à l'aveugle (chaque boost avec les seuls résultats antérieurs) :
« prendre » les types de pari qui ont réussi au moins 5 % au-dessus de leur cote sur 30 boosts réglés, +13,9 % sur
140 paris (−4,8 % pour « éviter », −15,9 % pour « neutre »). Un boost n'est donc pas rentable par nature : c'est la
value contre la cote juste qui compte.

## Value d'un boost

1. **Match** : le match du même bookmaker aux mêmes équipes, sinon celui d'un autre (ordre des équipes indifférent),
   début à 90 minutes près.
2. **Pari standard** (`traduire`) : victoire, match nul, double chance, handicap (« gagne par au moins N jeux / buts /
   points d'écart » = handicap −(N − 0,5)), mi-temps/fin, total, total d'une équipe, les deux équipes marquent, but ou
   total de points d'un joueur. Combinés (« … et … ») et intitulés inconnus : pas de traduction.
3. **Période** : quand plusieurs sont possibles (hockey : temps réglementaire par défaut chez Winamax), celle dont la
   cote habituelle du bookmaker vaut la cote d'avant le boost (« vérifié »), à 8 % près ; un pari qui existe chez lui à
   une tout autre cote n'est pas retenu. Sans cote d'avant : la première période qui a une cote juste.
4. **Cote juste** : celle de la référence du match (Pinnacle d'abord), lue au même moment, même association que la
   comparaison :

       value = cote boostée × probabilité juste − 1

Sans cote juste : la **hausse** (cote boostée / cote d'avant − 1) et la **marge seuil** (1 − cote d'avant / cote
boostée : le boost est rentable si la marge du bookmaker sur la cote d'avant était plus petite). Un repère, pas une
mesure.

## Boosts couverts (gain garanti)

Ajouté le 16/11/2026 (`couverts` dans `cotes/boosts.py`). Un boost traduit en pari d'un marché que les surebets savent
couvrir sans remboursement possible (1N2, vainqueur, double chance, les deux équipes marquent, handicaps et totaux à
demi-ligne) est joué à sa **mise maximale** (10 € si inconnue) ; chaque autre issue est couverte à la meilleure cote
française du cycle pour le même retour. Pour un boost 1N2, la couverture est soit le nul et l'autre équipe, soit la
double chance qui les réunit, la moins chère des deux. Si

    1/cote boostée + Σ 1/cote de couverture < 1

le gain est le même quel que soit le résultat : mise du boost × cote boostée × (1 − cette somme), aux arrondis près
(couvertures arrondies aux 10 centimes, au mieux pour le pire résultat). Exemple des tests : Lens boosté de 1,95 à
2,30 chez Winamax, nul à 3,60 chez Betclic, Lille à 4,50 chez Unibet : 10 € + 6,40 € + 5,10 €, **+1,45 € quoi qu'il
arrive**. Les cotes habituelles du même bookmaker peuvent couvrir son propre boost.

Couvertures : mêmes cotes et mêmes garde-fous que les surebets (`surebets.candidates` : lues depuis moins de 10 min,
pas plus de 15 % au-dessus de leur cote juste, intitulés contrôlés, match bien associé). **Vérifié** : le boost et
chaque couverture ont une cote juste chez la référence et ces probabilités font 1 à 3 % près ; si toutes en ont une et
qu'elles ne font pas 1, la couverture est écartée (pas le même marché). **Suspect** (affiché à part, ni suivi ni
envoyé) : rendement au-delà de 50 %, ou de 5 % sans vérification.

Garanti sur le papier seulement : la couverture peut bouger avant d'être jouée. Mise d'abord le boost (il peut
disparaître), puis la couverture tout de suite.

## Suivi, fichiers et alertes

`donnees/boosts.json` (JSON compact, réécrit à chaque cycle complet ; le journal donne le nombre lu par bookmaker, le
nombre de boosts couverts et les erreurs) : boosts du cycle évalués, épisodes des 30
derniers jours (première et dernière lecture, cote et value à la première lecture). Bilan sur 7 et 30 jours : nombre,
part évaluée, part en value, value médiane, **gain espéré** (mise maximale × value des boosts en value).
Boosts couverts : `couverts` (ceux du cycle) et `episodes_couverts` (un par boost et couverture : rendement, gain et
mise à la première lecture). Bilan : nombre, vérifiés, **gain garanti s'ils avaient tous été pris**, mise engagée.

Case **Cotes boostées** du bloc « Alertes Pushover » : un message par boost dont la value atteint
`BOOST_SEUIL_ALERTE` (3 % par défaut). Un boost couvert dont le rendement atteint `SUREBET_SEUIL_ALERTE` (1 %) part une
fois, si la case Surebets ou Cotes boostées est cochée, avec les mises de chaque jambe ; il remplace l'alerte de value
du même boost. `SOURCE_BOOSTS=off` coupe la lecture.

## Limites et suite

- Les boosts ne sont pas encore **réglés** : le gain espéré est une espérance, pas un résultat. Suite : régler les boosts
  traduits avec les scores déjà récupérés pour les paris (`cotes/reglement.py`).
- Les boosts sur des joueurs n'ont une cote juste que si la référence cote le même joueur (props NBA/NHL de Pinnacle).
- Genybet et Betsson : il faudrait une IP française (proxy payant, comme cotes-boostees) ; non lus.
- Combinés d'un même match (« X gagne et les deux équipes marquent ») : pas de cote juste. cotes-boostees les évalue
  avec Matchbook (« résultat + total ») ; à reprendre si utile.
