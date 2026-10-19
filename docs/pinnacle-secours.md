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
| `PINNODDS_LIMITE_JOUR` | 90 | requêtes par jour (l'offre gratuite en permet 100) |
| `PINNODDS_PAUSE_MIN` | 30 | minutes entre deux lectures de secours (0 : à chaque cycle) |
| `PINNODDS_HANDICAPS` | non | `oui` reprend aussi handicaps et totaux par équipe |

Abonnement (Pro, 10 requêtes par seconde sans plafond) : mettre `PINNODDS_LIMITE_JOUR` très haut et
`PINNODDS_PAUSE_MIN` à 0.

## Comportement

- Seuls les sports en **erreur HTTP** chez Pinnacle sont relus (tous si la lecture directe ne rend rien).
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
