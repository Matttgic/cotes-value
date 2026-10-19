# Secours Pinnacle (pinnodds)

La lecture directe de Pinnacle (`cotes/pinnacle.py`, API publique du site) reste la source normale.
Quand elle échoue (maintenance, refus 403), le secours lit les mêmes cotes chez **pinnodds**, un revendeur
du flux de Pinnacle. Il n'aide pas si Pinnacle lui-même est à l'arrêt : pinnodds retient alors sa grille
(`X-Data-Status: stale`) et le secours ne renvoie rien, jamais de vieilles cotes.

## Activation

1. Créer une clé gratuite sur <https://pinnodds.com> (sans carte ni compte Pinnacle).
2. GitHub → Settings → Secrets and variables → Actions → Secrets : `PINNODDS_API_KEY`.
   Sans ce secret, rien ne change : le secours est éteint.

Variables de dépôt facultatives (Actions → Variables) :

| Variable | Défaut | Rôle |
|---|---|---|
| `PINNACLE_SECOURS_PERIME` | football | sports relus quand Pinnacle est en retard (noms séparés par des virgules, `non` pour couper) |
| `PINNODDS_LIMITE_JOUR` | 90 | requêtes par jour (l'offre gratuite en permet 100) |
| `PINNODDS_PAUSE_MIN` | 30 | minutes entre deux lectures de secours (0 : à chaque cycle) |
| `PINNODDS_HANDICAPS` | non | `oui` reprend aussi handicaps et totaux par équipe |

Abonnement (Pro, 10 requêtes par seconde sans plafond) : mettre `PINNODDS_LIMITE_JOUR` très haut et
`PINNODDS_PAUSE_MIN` à 0.

## Comportement

- Sont relus les sports en **erreur HTTP** chez Pinnacle (tous si la lecture directe ne rend rien), et ceux de
  `PINNACLE_SECOURS_PERIME` dont toutes les cotes directes sont **périmées** (plus de `PINNACLE_AGE_MAX_MIN` minutes).
- Marchés repris par défaut : résultat, vainqueur et totaux, aux périodes de `pinnacle.PERIODES`.
  Tennis : vainqueur seulement (handicaps et totaux y sont en sets ou en jeux).
- Les lignes ont le format de `pinnacle.collecter`, avec `origine: "pinnodds"` et leur probabilité juste.
- Le journal du cycle (`pinnacle_secours`) et la page Santé indiquent quand le secours a servi.
- Le budget du jour est gardé dans `pinnacle_secours.json` (branche `donnees`).

## Valider avant de s'y fier

Quand Pinnacle répond de nouveau, comparer les deux lectures :

```bash
PINNODDS_API_KEY=... PINNODDS_HANDICAPS=oui python scripts/comparer_secours_pinnacle.py football basket
```

La couverture et la part de cotes à ±1 % doivent être très élevées. Tant que ce n'est pas vérifié,
laisser `PINNODDS_HANDICAPS` à `non` : le signe du handicap et les périodes de pinnodds n'ont pas été
confrontés à la lecture directe.

## Entre deux lectures

Le secours ne lit que toutes les 30 minutes (offre gratuite). Entre deux lectures, le dernier passage est rejoué depuis `pinnacle_secours_cache.json` avec son âge réel : une ligne plus vieille que `PINNACLE_AGE_MAX_MIN` (10 minutes par défaut) reste marquée périmée et ne sert pas de référence, un match commencé est retiré, et le cache est ignoré au-delà de 3 heures. Limite : avec 90 requêtes par jour, l'offre gratuite ne donne une référence fraîche que quelques dizaines de minutes par jour.

## Second secours : PinBook (offre gratuite)

`PINBOOK_API_KEY` (secret GitHub, clé de l'offre gratuite « PinBook Odds » sur RapidAPI : 550 requêtes par mois) ajoute PinBook **derrière** pinnodds. Il ne sert que pour les sports restés sans ligne fraîche (ni lecture, ni cache de moins de 10 minutes), parmi `PINBOOK_SPORTS` (football, tennis, basket par défaut), au plus `PINBOOK_LIMITE_JOUR` requêtes par jour (16) et `PINBOOK_PAUSE_MIN` minutes entre deux lectures (60). La fraîcheur vient de `last_call` : une réponse plus vieille que `PINNACLE_AGE_MAX_MIN` donne des lignes marquées périmées. Les lignes portent `origine: pinbook`.

Essai manuel : workflow « Essai PinBook » (3 requêtes, aucune écriture), qui affiche couverture, fraîcheur et quota restant. Mesures du 19/10/2026 pendant la maintenance de l'API invitée de Pinnacle : football 360 matchs à moins de 36 h, tennis 156, basket 79, données vieilles de quelques secondes.

## Pinnacle en retard (cache de 15 minutes)

Depuis la fin de la maintenance du 19/10/2026 (vers 13 h 20 UTC), toute l'API invitée de Pinnacle répond
`Cache-Control: public, max-age=905` : chaque URL est une copie Cloudflare renouvelée toutes les 15 minutes,
aussitôt reprise par d'autres lecteurs. Mesuré le 19/10 : les orthographes des prix du football, les URL par
ligue et les autres sports vieillissent ensemble, à quelques dizaines de secondes près. Une URL absente du cache
part chez Pinnacle, qui refuse (403) ou répond vide (204) : on ne peut ni choisir une copie plus jeune ni en
créer une. Le réchauffeur de Paris ne sert plus à rien dans ce cas : il relit la même copie (HIT).

Conséquence : chaque cycle lit des cotes de 0 à 15 minutes et, environ un cycle sur trois, toutes dépassent
10 minutes et sont écartées. Le secours pinnodds (cotes d'âge 0) comble alors le football : au plus une
requête toutes les 30 minutes, 48 par jour, soit environ un trou sur deux. Ajouter tennis et basket à
`PINNACLE_SECOURS_PERIME` triple la dépense : le quota gratuit (90) serait vide en fin d'après-midi, heure de
Paris. La page Santé affiche la ligne « Pinnacle · fraîcheur ».
