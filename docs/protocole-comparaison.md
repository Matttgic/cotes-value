# Protocole figé avant les calculs comparatifs — 14 octobre 2026

## Décision et source

Chercher la candidate la mieux étayée parmi une famille limitée de règles de
value betting. Ne pas prétendre découvrir « la meilleure stratégie possible ».
Comparaison à mise fixe de 10 € fictifs, jamais de placement réel.

Source de référence : branche `donnees`, commit
`56bed648894f383f04fb42f677ee9223d29c2abe`, cycle du 14/10/2026 à 10:09:28 UTC.
SHA256 de `paris.json` : `5d1a044eb1a5fbaf7261e2a149eaef2937731af42a7cbd22977bcceb8797ce31`.
La branche contient les premières détections, pas une possibilité de reprendre
chaque ancien pari à une cote ultérieure. Aucun résultat n'est modifié.

## Famille de 36 règles

Produit cartésien, sans recherche additionnelle après lecture des résultats :

- Référence : **Pinnacle sans marge / Betfair / Polymarket**.
- Cotes : **1,30–2,00 / 1,50–3,00 / 2,00–5,00**.
- Edge minimum : **2 % / 5 %**, avec maximum commun de 12 %.
- Anticipation maximum : **12 h / 36 h**. Détection strictement avant le match.

Qualité commune : bookmaker Winamax, Betclic, Unibet ou PMU ; contrôle conforme
enregistré à la prise, ressemblance des noms ≥ 0,85, identifiant de match de la
référence présent, cote de référence âgée de 0 à 15 min, edge cohérent avec les
cotes à l'arrondi près. Pas de sélection a posteriori selon la présence de CLV.

Marchés : 1N2, vainqueur, double chance, remboursé si nul, total du match,
handicap ; match entier ou temps réglementaire. Pas de quarts de ligne.
Tennis et volley : vainqueur seulement, à cause des ambiguïtés jeux/sets/points
des marchés génériques. Aucun filtre de sport, sexe, ligue ou bookmaker fondé
sur son profit observé. Aucun filtre cartons/corners/BTTS/score exact.

Une seule mise par match et par candidate, grâce à l'identifiant de la référence,
tous bookmakers et marchés confondus. Première détection admissible ; si deux
détections ont exactement la même heure : edge décroissant, cote décroissante,
bookmaker, identifiant. Pas de choix du meilleur prix vu plus tard. Aucun plafond
journalier arbitraire dans cette famille ; l'exposition est publiée séparément.

Kalshi et Consensus ne sont pas dans la famille : ils ne doivent pas être
ajoutés après observation d'un résultat. L'étude porte sur les trois références
déjà utilisées par la stratégie de Claude, avec un identifiant d'événement direct.

## Découpage chronologique (Europe/Paris)

Les intervalles sont fermés à gauche et ouverts à droite, classés par début du
match. Un événement ne peut pas se retrouver à cheval sur deux périodes.

1. **Construction : 7/10 00:00 → 11/10 00:00.** Scores réglés avant la fin de
   cette période uniquement pour choisir les finalistes.
2. **Validation : 11/10 00:00 → 13/10 00:00.** Scores réglés avant la fin de
   cette période uniquement pour choisir une candidate parmi les finalistes.
3. **Test final : 13/10 00:00 → 14/10 00:00.** Règlements disponibles au moment
   du relevé ; les matchs non réglés restent visibles, pas implicitement perdus.

Détections à partir du 7/10 seulement, date où la preuve de prise existe. Les
détections après le début d'une période restent évidemment possibles pour ses
matchs, mais aucune donnée de résultat de la période suivante n'entre dans le
classement précédent. Les corrections tardives d'un ancien règlement ne sont
pas entièrement reconstructibles : le relevé disponible représente l'état actuel.

Ces périodes ont déjà été regardées sous forme agrégée. **Test rétrospectif
chronologique ne signifie donc pas test aveugle indépendant.** Seuls de nouveaux
paris sélectionnés après publication des règles offrent cette indépendance.

## Choix annoncé avant les résultats

- Construction : garder au plus trois finalistes ayant **≥ 20 paris réglés**, un
  ROI positif, une CLV moyenne positive et une couverture de CLV ≥ 50 %.
- Classement : borne basse de l'intervalle bootstrap à 95 % du ROI, puis nombre
  de réglés, puis identifiant. 5 000 tirages par événements, graine fixe 20261014.
- Validation : retenir parmi ces finalistes ceux qui ont **≥ 10 réglés**, ROI
  positif, CLV moyenne positive et couverture de CLV ≥ 50 % ; appliquer le même
  classement. S'il n'y en a aucun, **ne désigner aucune gagnante**.
- Test final : la candidate choisie sur la validation ne sera jamais remplacée
  par une autre parce qu'elle échoue sur le test. Un lancement v2 expérimental
  nécessite ≥ 10 réglés, ROI positif, CLV positive et couverture ≥ 50 % sur ce test.
- Même dans ce cas, parler de **candidate expérimentale**, jamais de rentabilité
  acquise. Une borne basse négative, un échantillon faible, les essais multiples
  et la courte période interdisent de traiter le ROI historique comme une prévision.

La V1 ChatGPT et Claude sont des comparateurs descriptifs, non des finalistes.
Leurs règles historiques sont préservées ; les rejeux avant leur date de lancement
sont explicitement marqués hypothétiques. Le bilan réel depuis lancement reste
séparé. Si aucune candidate ne passe, intégrer le laboratoire et suivre la famille
en simulation future, sans fabriquer de gagnante ni retoucher les seuils.

## Mesures, sensibilité et audit

Pour chaque candidate et période : sélections, réglés/non réglés, matchs uniques,
gagnés/perdus/remboursés, profit net, ROI sur mises réglées, IC bootstrap 95 %,
CLV et couverture, baisse maximale du cumul dans l'ordre des règlements,
meilleur gain, profit sans ce gain, jours positifs/actifs, mises maximum par jour.

Tests de sensibilité annoncés : retrait du meilleur gain ; baisse relative de
1 % de chaque cote jouée (mêmes sélections et résultats) ; bornes pessimiste et
optimiste si les paris non réglés perdent ou gagnent tous. La sensibilité au prix
ne prouve pas qu'une cote était effectivement exécutable à la prise.

Audit : unicité des IDs, données manquantes, événements corrélés, statut/gain/mise,
dates, règlement automatique ou manuel et accord des résultats du même pari entre
références. Les résultats suspects sont signalés, jamais corrigés par supposition.
Les intervalles par match ignorent encore les dépendances entre matchs d'une même
journée ; présenter aussi les profits journaliers pour exposer cette limite.

Fournir code, relevé JSON, notebook exécuté et tableau lisible dans Bilan. Aucune
recherche massive de milliers de seuils ni modèle ML sur quelques jours de données.
