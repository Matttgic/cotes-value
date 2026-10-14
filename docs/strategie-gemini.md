# Gemini Argon V1

Simulation depuis le **14 octobre 2026 à 20 h, heure de Paris**. Aucun pari réel.

- Références : Pinnacle, Betfair, Polymarket.
- Cotes : 1,30–2,15 sur Pinnacle ; 1,30–2,60 sur Betfair et Polymarket.
- Edge : 2,5–12 % ; détection de 30 minutes à 24 h avant match.
- Référence âgée de 10 minutes maximum ; correspondance ≥ 0,85 et contrôle conforme.
- Hommes seniors ; match entier ou temps réglementaire. Tennis/volley : vainqueur.
- Marchés : 1N2, vainqueur, double chance, remboursé si nul, total et handicap.
- Lignes entières ou demi-points, pas de quarts. Mise fictive 10 €, 8 prises par jour Paris.

Les premiers prix admissibles sont retenus dans l’ordre des détections. À heure
égale : edge décroissant, cote croissante, bookmaker puis ID. Ni les résultats
ni la CLV ne servent à choisir un pari. Les seuils et la date initiale sont
conservés lors du correctif du 14 octobre au soir.

## Audit de l’intégration

- Les bilans par simulation, bookmaker et cote comptent désormais la sélection
  Gemini, comme le graphique et les fiches de Paris. Le simple ajout d’un bouton
  de Bilan ne suffisait pas à alimenter ces totaux.
- Les alias de matchs connus à la détection sont reliés entre références et
  bookmakers, même quand la ligne est écartée car le match est déjà joué.
  Les mêmes équipes normalisées au même instant apportent un lien supplémentaire.
  Un nouveau bookmaker ne doit pas reprendre un événement déjà identifié comme joué.
- Le plafond journalier des rejeux tient compte de toutes les prises admissibles,
  même des matchs hors période affichée. Filtrer la période avant la sélection
  aurait libéré des places et modifié les paris affichés.
- Le site calcule chaque sélection une seule fois pour la navigation, puis
  réutilise ses IDs. Le recalcul pour chaque fiche créait une charge quadratique.
- Les boutons Bilan → Paris réinitialisent le contexte d’une précédente stratégie.

L’identité d’événement dépend des identifiants et associations disponibles au
moment de la prise. Des alias divergents sans lien connu peuvent encore être
manqués ; ce mécanisme ne prouve pas une indépendance statistique parfaite.
Il ne fusionne pas les paris après coup en utilisant un résultat futur.

Le rejeu historique est hypothétique et a été conçu après consultation des données.
La rentabilité de Gemini n’est pas démontrée ; son objectif d’exposition et ses
seuils ne constituent pas un modèle de probabilité calibré. La CLV sert au diagnostic.

Accès : **Bilan → Gemini Argon** ; **Stratégies → Gemini Argon V1** ;
**Paris → Simulations → Gemini Argon**. Cliquer une ligne de Stratégies ouvre ses
sélections exactes pour la période affichée. Les paris d’avant 20 h ne sont pas
réintégrés dans le bilan prospectif.

Validation : tests de dates, plafonds Paris, invariance aux résultats, ponts entre
références/bookmakers, comptabilité commune des bilans/courbes/fiches et nombre
constant de calculs de sélection pour la navigation.
