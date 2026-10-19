# Ordres de pari (ordres.json)

Le site publie `ordres.json` à côté de `notifications.json` : un ordre par alerte encore valable, pour parier à la main ou par une IA avec ordinateur (Grok Bot, etc.). Le module `cotes/ordres.py` ne place aucun pari et ne contient aucun identifiant de compte.

Champs d'un ordre : `id` (unique, un seul pari par id), `bookmaker`, `domicile`, `exterieur`, `ligue`, `debut`, `marche`, `issue`, `ligne`, `pari`, `libelle_bookmaker`, `cote_relevee`, `cote_min` (3 % sous la cote relevée), `mise` (10 € par défaut, `MISE_EUR`), `expire_le` (10 minutes après le relevé, et au plus tard 3 minutes avant le match), `lien` (adresse du match chez le bookmaker, ou `null`), `recherche` (noms exacts pour retrouver le match), `strategies`. Le champ `regles` rappelle les garde-fous.

Notification : toucher une alerte ouvre le site sur `?alerte=<id>`, avec un bandeau « Ouvrir chez … » (lien, cote minimale, mise, heure limite). Sans lien connu (OlyBet, NetBet), le bandeau donne les noms à chercher.

Limite : les adresses de base des liens (Winamax, Betclic, PMU, Unibet) ne sont pas vérifiées en ligne, les sites refusent les requêtes automatiques. Un lien qui ne mène pas au match se remplace par la recherche.
