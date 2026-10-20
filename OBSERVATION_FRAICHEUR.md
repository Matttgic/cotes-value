# Observation manuelle de la collecte

Le script `scripts/observer_collecte.py` reutilise une seule fois `scripts.cycle.collecter_prematch`. Il ne lance ni les simulations, ni les reglements, ni les notifications, ni la publication. Le workflow de production reste inchange.

Le workflow `diagnostic-fraicheur.yml` est manuel uniquement, avec permission `contents: read`. Son lancement effectue de vrais appels reseau, consomme des minutes GitHub Actions et, si configure, des invocations du rechauffeur existant. L'ajout des fichiers ne lance aucun essai. Les secours Pinnacle sont desactives : aucune cle PINNODDS/PINBOOK n'est utilisee, aucun de leurs quotas n'est consomme. OlyBet et NetBet sont aussi desactives pour cet essai.

La reserve existante est copiee dans un repertoire temporaire ; l'original et les donnees de production ne sont pas modifies. Le rapport agrege separe Pinnacle direct des origines inattendues et signale les sources sans ligne. Il ne contient pas les prix bruts, les noms d'equipes ou les erreurs brutes du journal. Les journaux des collecteurs existants restent soumis a leurs propres protections.

## Tests

```bash
python -m unittest discover -s tests -p test_diagnostic_fraicheur.py -v
python -m unittest discover -s tests -p test_observation_fraicheur.py -v
```

Les 7 nouveaux tests ont reussi hors ligne avec une fausse collecte. Le diagnostic importe pendant ces tests a le meme SHA de blob que celui du depot. Aucun test reseau ni suite complete du depot n'a ete execute.

## Essai local, apres autorisation des acces reseau

```bash
python scripts/observer_collecte.py --mode test --reserve donnees/horizon_direct.json --sortie observation-unique
```

Le dossier de sortie doit etre nouveau. Adapter le chemin a une copie locale reelle. Sans reserve, les collecteurs demarrent avec un cache vide. Ne pas lancer l'ancien workflow de production pour cet essai. La disponibilite du nouveau workflow manuel depuis une branche non par defaut reste a verifier ; aucune fusion n'est effectuee ici.

## Limites

Un seul essai ne prouve ni la disponibilite continue ni l'exhaustivite. Les sports et horizons restent ceux du cycle existant, y compris en mode test. Les horodatages ne prouvent pas l'age du prix en amont ; les anciennes lignes gardent leur date. Les secours ne sont pas testes. Le delai jusqu'au navigateur n'est pas mesure. Le cycle automatique de production n'est pas encore instrumente : son raccordement necessitera une modification distincte apres validation.
