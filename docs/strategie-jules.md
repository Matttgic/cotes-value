# JULES EDGE v1 : règles et audit

Stratégie créée par Jules, première publication du code le **14/10/2026 à
23:04:13 (Europe/Paris)**, commit `5f4c2c74ef50bc6d930dd9acaa488cf0ed7663da`.
Cette date est le début du suivi après lancement. Le 5 octobre est uniquement
le début du rejeu historique et ne doit pas alimenter le bilan de suivi.

## Règles conservées

- Référence Pinnacle sans marge ; Winamax, Betclic, Unibet et PMU.
- Cotes 1,30–2,50 ; edge 3–12 %, cohérent avec la cote juste.
- Détection entre 15 minutes et 12 heures avant le match ; référence de 5 minutes maximum.
- Preuve de correspondance >= 0,85, identifiant de match Pinnacle et contrôle conforme.
- Marchés 1N2, vainqueur, total et handicap ; match entier ou temps réglementaire explicite.
- Tennis et volley : vainqueur seulement. Pas de lignes en quart.
- Première opportunité admissible par match Pinnacle, tous bookmakers et marchés
  confondus ; six nouvelles sélections maximum par jour civil de Paris.
- À détection égale : edge décroissant, puis cote décroissante, bookmaker et identifiant.
- Mise fixe fictive de 10 €. Aucun pari réel n'est placé.

La correction d'intégration ne change aucun seuil ni ordre de sélection de Jules.
Le filtre ne lit ni résultat, ni gain, ni CLV. Cela permet une décision causale,
mais ne prouve pas que les seuils aient été choisis sans regarder l'historique.

## Audit historique reproductible

Rejeu depuis le **5 octobre à 02:00 (Paris)**, sur les détections disponibles au
**14 octobre à 23:03:59 (Paris)**. Source : branche `donnees`, commit
`fa0b85b964f17015a8b16576fd5145e2177aed04`, paris actifs et archives inclus.
Le rapport [strategie-jules.json](strategie-jules.json) contient les identifiants
des sélections, l'empreinte des données et les statistiques.

| Indicateur | Résultat recalculé |
|---|---:|
| Sélections | 26 |
| Paris réglés | 21 |
| En attente | 5 |
| Gagnés / perdus / remboursés | 13 / 8 / 0 |
| Réussite sur paris réglés | 61,90 % |
| Mises réglées | 210 € |
| Gains nets des gagnants | 107,90 € |
| Pertes | 80,00 € |
| Gain net | +27,90 € |
| ROI sur mises réglées | +13,29 % |
| CLV exploitable moyenne | +0,91 % sur 16/21 paris réglés |
| Baisse maximale du cumul observée | 20,00 € |

La CLV suit le contrôle existant : clôture lue avant le match et dans les
30 dernières minutes. Les cinq autres CLV ne sont pas retenues dans cette moyenne.
Les cinq paris en attente ne sont comptés ni comme perdus ni comme gagnés.

Les anciens chiffres « 256 paris, +499 €, +19,5 % de ROI, +4,9 % de CLV »
ne sont pas reproductibles avec le code livré et sont retirés. Un plafond de
six sélections par jour permet au maximum 60 sélections sur ces dix jours.

Pour reproduire le rapport, utiliser une copie de la branche de données au commit
indiqué, puis lancer depuis la racine du code :

```bash
python scripts/verifier_strategie_jules.py --donnees chemin/vers/donnees --releve 2026-10-14T21:03:59+00:00 --sortie rapport-jules.json
```

## Lecture sur le site et limites

- **Bilan → JULES EDGE** : détections depuis le lancement du 14/10 à 23:04:13.
- **Voir les paris JULES EDGE** : sélections exactes de ce suivi, avec leur prix à la prise.
- **Stratégies → JULES EDGE V1** : ligne cliquable, statistiques et graphique.
- **Stratégies → Historique 7–13 oct.** : rejeu sur la même fenêtre et le même
  relevé figé que les autres comparateurs. Cette fenêtre plus courte n'est pas
  le rapport complet 5–14 octobre ci-dessus.

Tout le passé présenté ici est un **rejeu descriptif a posteriori**. Les noms des
périodes « construction », « validation » et « test » dans le comparateur ne
constituent pas une validation indépendante d'une stratégie créée après ces dates.
21 résultats sont insuffisants pour conclure à une rentabilité durable ou à une
supériorité sur Claude. Aucun taux de réussite futur ni rendement n'est garanti.
