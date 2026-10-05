# Cotes Value

Compare **toutes les cotes** des bookmakers français (Winamax, Betclic, Unibet, PMU, NetBet) à la
**cote juste** de plusieurs références « sharp », et simule les paris qu'on prendrait à chaque erreur
de cote : 10 € par pari, plusieurs seuils, pour savoir lesquels gagnent vraiment.

⚠️ Simulation uniquement. Les paris sportifs comportent un risque de perte.
Jeu responsable : Joueurs Info Service, 09 74 75 13 13.

## Sources

| Source | Rôle | Accès | Coût |
|---|---|---|---|
| Pinnacle | Référence | API publique du site (`cotes/pinnacle.py`) | Gratuit |
| Polymarket | Référence | API officielle gamma (`cotes/polymarket.py`) | Gratuit |
| Kalshi | Référence (vainqueur) | API officielle (`cotes/kalshi.py`) | Gratuit |
| Betfair Exchange | Référence | PulseScore, via Orbit Exchange | Offre PulseScore |
| Winamax, Betclic, Unibet, PMU, NetBet | Cotes à comparer | PulseScore (`cotes/pulsescore.py`) | Offre PulseScore |

Vérifications faites (workflow « Vérifications des sources ») :
- Pinnacle lu directement = PS3838 de PulseScore : 98 % des 4 161 cotes à moins de 1 % d'écart ;
- Polymarket et Kalshi lus directement = PulseScore : 87 % et 99 % des marchés strictement identiques
  (les écarts restants : marchés sans échanges, écartés par le comparateur).

## Comment ça marche

Toutes les 15 minutes (`scripts/cycle.py`) :

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
5. **Paris simulés** (`cotes/simulation.py`) : 10 € à la première détection, par simulation et par
   référence. **A** ≥ 2 %, **B** ≥ 3 %, **C** ≥ 4 %, **D** ≥ 5 %, **E** ≥ 7 % (cotes ≤ 10),
   **X** cotes > 10 (≥ 3 %). La cote juste est suivie jusqu'au coup d'envoi (**CLV**).
6. **Règlement** (`cotes/reglement.py`) avec les résultats PulseScore du bookmaker du pari ;
   sinon « à régler à la main » sur le site (bouton « Copier » → coller la liste à Claude).
7. **Site** (`scripts/site_web.py`) publié sur GitHub Pages.

## Mise en route

1. Secret `PULSESCORE_KEY` (Settings → Secrets and variables → Actions → Secrets).
2. Settings → Pages → Source : **GitHub Actions**.
3. Test : Actions → « Collecte et comparaison » → Run workflow → mode `test` (≈ 4 requêtes).
4. Collecte automatique (avec PulseScore PRO) : variable de dépôt `COLLECTE_AUTO` = `oui`
   (et `MODE_COLLECTE` = `complet`, valeur par défaut).

Coût en requêtes : `python scripts/simulation_appels.py` (≈ 415 000/mois pour les 5 bookmakers +
Betfair toutes les 15 min : offre PRO nécessaire ; l'offre gratuite ne sert qu'aux tests).

## Données (branche `donnees`)

- `paris.json` : tous les paris simulés (statut, gain, CLV) ;
- `opportunites/AAAA-MM-JJ.jsonl.gz` : toutes les erreurs de cote détectées ;
- `etat.json` : dernier cycle, requêtes PulseScore par mois ;
- `resultats_manuels.json` : règlements à la main, par exemple
  `{"winamax|72036146": {"score": [2, 1], "mi_temps": [1, 0], "corners": [7, 3]}}`.

## Développement

```bash
pip install -r requirements-dev.txt
python -m pytest -q tests
python scripts/cycle.py --mode test     # nécessite PULSESCORE_KEY ; sans clé : références seules
```
