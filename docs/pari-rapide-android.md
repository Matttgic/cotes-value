# Pari rapide sur Android : notification → page du match → mise collée

But : passer de l'alerte au pari en quelques secondes, sans recopier le match ni le montant, et sans robot qui
clique à ta place.

## Ce qui existe déjà

- **Lien direct vers le match** : chaque pari a son lien (`cotes/liens.py`) chez Winamax, Betclic, Unibet,
  PMU, NetBet et OlyBet. Les paris du 1er et du 2/11 en ont tous un. Pushover l'affiche en bouton « Ouvrir le
  match chez … ». Quand seule la page du sport est connue, le bouton le dit (« match à chercher »).
- **La mise** : la notification donne la mise Kelly ¼ et la cote minimale en dessous de laquelle ne pas jouer.

## Ce qui a été ajouté

Une ligne lisible par une machine, juste avant la liste des stratégies :

```
STAKE:7.5|MIN:1.85|URL:https://www.betclic.fr/…-m1262412406730753
```

- `STAKE` : mise Kelly ¼ ramenée à ta bankroll, arrondie à 0,50 € (point décimal).
- `MIN` : cote minimale. En dessous, ne pas jouer : le prix a bougé.
- `URL` : page du match. Pas de ligne si le lien ne mène qu'à la page du sport.

Réglages (GitHub → Settings → Secrets and variables → Actions → **Variables**) :

- `PUSHOVER_BANKROLL` : ta bankroll en euros (défaut 1 000, celle des bilans). La mise affichée suit.
- `PUSHOVER_LIGNE_MACRO` : `non` pour retirer la ligne.

## Recette MacroDroid (option recommandée)

Les noms d'actions peuvent varier légèrement selon la version de MacroDroid.

1. **Déclencheur** : *Notification reçue* → application **Pushover**, le texte contient `STAKE:`.
2. **Action** : *Manipulation de texte* → extraire de `[notification]` avec l'expression régulière
   `STAKE:([0-9.]+)` → variable `mise`.
3. **Action** : même extraction avec `URL:(\S+)` → variable `lien`.
4. **Action** : *Définir le presse-papiers* → `{v=mise}`.
5. **Action** : *Ouvrir une page web* → `{v=lien}`, dans le navigateur de ton choix (Firefox, Brave, Chrome).

Ensuite, à la main : tu vérifies que la cote est encore au moins égale à `MIN`, tu touches la cote, tu colles
la mise depuis la suggestion du clavier et tu valides. Comptez quelques secondes. Le pari reste le tien, posé
comme n'importe quel pari manuel.

## L'option B (MacroDroid qui clique dans la page) : non

La proposition de Jiminy va plus loin : MacroDroid touche la cote et remplit la mise à ta place, avec des délais
aléatoires pour ne pas avoir l'air d'un robot. Je ne l'ai pas mise en place.

- Les conditions des bookmakers agréés ANJ interdisent les paris automatisés. Les délais aléatoires servent
  justement à contourner leurs contrôles. Le risque est la fermeture du compte et l'annulation des gains.
- Le gain de temps est faible : une ou deux secondes de plus que l'option recommandée.
- Elle est fragile : une page plus lente ou une maquette modifiée, et le clic tombe à côté. Une erreur de mise
  coûte plus que le temps gagné.

Ce qui fait limiter un compte, ce n'est pas l'outil sur le téléphone : c'est un profil de parieur qui bat
régulièrement la cote de clôture. Ce risque existe avec ou sans automatisation.

## Navigateur ou application du bookmaker ?

Les deux fonctionnent avec la recette. Le navigateur a deux avantages pratiques : le lien s'ouvre directement
sur la page du match, et rien ne dépend d'une mise à jour de l'application. Si l'application du bookmaker est
installée, Android peut ouvrir le lien dedans. Le choix du navigateur dans l'action 5 l'évite.

## Limites

- Entre l'alerte et ton clic, la cote peut avoir baissé : `MIN` est là pour ça.
- Les alertes suivent les cycles (environ toutes les 5 minutes). Le délai entre la cote vue et la notification
  est affiché dans la page Notifications.
- Jeu responsable : Joueurs Info Service, 09 74 75 13 13.

## Récapitulatif « encore jouables » (11 h)

Chaque jour à 11 h (heure de Paris), une notification Pushover reprend les alertes envoyées depuis le récapitulatif
précédent dont la cote, revérifiée dans l'historique des cotes, est encore au moins la cote minimale, et dont le
match commence dans plus de 10 minutes. Une ligne par pari : match, cote actuelle, cote minimale, mise, lien.
Pour les alertes de la nuit ou des heures de travail (`cotes/recap_jouables.py`).

- `PUSHOVER_RECAP_HEURE` : heure du récapitulatif (0–23, défaut 11) ; `non` pour le couper.
- Les mises (alertes et récapitulatif) sont arrondies à l'euro supérieur (8,74 € → 9 €) : sur l'historique, le ROI
  ne change pas (+2,95 % → +3,01 % sur les paris uniques, mises +3,6 %).
