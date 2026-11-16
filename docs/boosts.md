# Cotes boostées

Ajouté le 16/11/2026. Code : `cotes/direct/winamax.py` (`lire_boosts`, `boosts_depuis`), `cotes/boosts.py`
(traduction des intitulés, value, suivi), `cotes/pipeline/analyse.py` (`boosts_du_cycle`), `web/boosts.js` (onglet
**Boosts**), `cotes/alertes/promos.py` (Pushover). Sonde : `scripts/sonde_boosts.py` (Actions → « Sonde cotes
boostées »).

## Où sont les boosts (sonde du 16/11/2026)

| Bookmaker | Constat |
|---|---|
| Winamax | Route `sport:100000` du socket : un faux match par boost (« Cote Boostée : A - B »), un pari « Cote boostée (mise max 20 €) » avec `previousOdd` (cote d'avant), une issue au libellé libre. **Lu à chaque cycle complet.** |
| Unibet | Une rubrique « Cotes Boostées » existe (chemins `p58245556`…), vide dans les pages de sports lues par la collecte ; les `promos` des pages sont des combinés boostés. Non lu. |
| Betclic, PMU, NetBet, OlyBet | Aucun boost dans ce que la collecte lit (trames gRPC Betclic, offre Kambi de PMU, pages NetBet, Swarm OlyBet). |

Exemples relevés le 16/11 : « Carlos Alcaraz gagne par au moins 6 jeux d'écart » 2,80 (au lieu de 2,50),
« Allemagne gagne à la mi-temps et à la fin du match » 2,70 (2,45), « États-Unis (F) gagne par au moins 3 buts
d'écart » 2,75 (2,50), « Jack Eichel marque au moins un but » 2,60 (2,40). Mise maximale : 20 €.

## Value d'un boost

1. **Match** : le match Winamax habituel aux mêmes équipes, début à 90 minutes près.
2. **Pari standard** (`traduire`) : victoire, match nul, double chance, handicap (« gagne par au moins N jeux / buts /
   points d'écart » = handicap −(N − 0,5)), mi-temps/fin, total, total d'une équipe, les deux équipes marquent, but ou
   total de points d'un joueur. Combinés (« … et … ») et intitulés inconnus : pas de traduction.
3. **Période** : quand plusieurs sont possibles (hockey : temps réglementaire par défaut chez Winamax), celle dont la
   cote Winamax habituelle vaut la cote d'avant le boost (« vérifié »), à 8 % près. Un pari qui existe chez Winamax à une
   tout autre cote n'est pas retenu.
4. **Cote juste** : celle de la référence du match (Pinnacle d'abord), lue au même moment, même association que la
   comparaison :

       value = cote boostée × probabilité juste − 1

Sans cote juste : la **hausse** (cote boostée / cote d'avant − 1) et la **marge seuil** (1 − cote d'avant / cote
boostée : le boost est rentable si la marge de Winamax sur la cote d'avant était plus petite). Un repère, pas une
mesure.

## Suivi, fichiers et alertes

`donnees/boosts.json` (JSON compact, réécrit à chaque cycle complet) : boosts du cycle évalués, épisodes des 30
derniers jours (première et dernière lecture, cote et value à la première lecture). Bilan sur 7 et 30 jours : nombre,
part évaluée, part en value, value médiane, **gain espéré** (mise maximale × value des boosts en value).

Case **Cotes boostées** du bloc « Alertes Pushover » : un message par boost dont la value atteint
`BOOST_SEUIL_ALERTE` (3 % par défaut). `SOURCE_BOOSTS=off` coupe la lecture.

## Limites et suite

- Les boosts ne sont pas encore **réglés** : le gain espéré est une espérance, pas un résultat. Suite : régler les boosts
  traduits avec les scores déjà récupérés pour les paris (`cotes/reglement.py`).
- Les boosts sur des joueurs n'ont une cote juste que si la référence cote le même joueur (props NBA/NHL de Pinnacle).
- Unibet : à lire sur sa page « cotes boostées » quand un boost y est publié (relancer la sonde à une heure de forte
  offre, en soirée).
