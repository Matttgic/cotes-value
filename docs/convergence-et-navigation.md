# Convergence et navigation des paris

Version publiée le 15 octobre 2026 (heure de Paris). Les stratégies existantes,
leurs règles et leurs mises fictives restent inchangées.

## Définition de la convergence

Début du suivi prospectif : **15 octobre 2026 à 01 h à Paris**
(`2026-10-14T23:00:00Z`). Aucun pari antérieur n'est ajouté à ce suivi.

Un pari est retenu lorsque deux familles au moins sélectionnent **la même
sélection chez le même bookmaker, au même prix et au même instant de détection**.
L'instant est comparé en UTC, indépendamment du format du fuseau dans les données.
Les références peuvent différer. Marché, période, ligne, issue et joueur doivent
coïncider. Il s'agit des sélections effectives des moteurs, après leurs plafonds
journaliers et leurs dédoublonnages, pas d'un simple respect des seuils.

Les familles sont Claude, ChatGPT, Gemini Argon, Jules et M3. Jules v1 et v2
peuvent chacune apparaître dans les badges et les courbes mais ne donnent
**qu'un vote Jules**. L'accord des stratégies ne signifie pas que leurs sources
ou leurs erreurs sont indépendantes.

Une seule mise fictive de 10 € est comptée par sélection convergente, à la
première convergence observée. Un signal reçu plus tard ne valide pas
rétroactivement une ancienne prise. En cas de références simultanées, leur ordre
habituel détermine la prise représentative, sans consulter le résultat.
La convergence ne crée pas de mises réelles et n'ajoute pas de plafond propre :
elle conserve les plafonds des moteurs dont elle regroupe les sélections.

L'historique du 7 au 13 octobre réapplique les règles à partir du début de
l'étude, avec les données détectées avant le relevé figé. C'est un **rejeu
exploratoire a posteriori**, pas une validation indépendante de rentabilité.
Les sous-périodes utilisent les coupures de règlement du protocole existant.
Le rapport M3 archivé était descriptif au relevé final pour toutes ses
sous-périodes ; le tableau et les courbes du site harmonisent désormais ces
coupures avec les autres comparateurs. Son total historique reste inchangé.

## À jouer et Paris

Les badges d'une opportunité indiquent les sélections déjà enregistrées pour
cette sélection et ce prix, et affichent leur date. Ils ne promettent pas une
nouvelle place dans un plafond déjà rempli. Si le prix change, la sélection
précédente n'est pas transférée automatiquement à la nouvelle cote.

La recherche et l'export portent sur toutes les prises enregistrées, archives
comprises. Une ligne correspond à une prise par référence ; plusieurs références
peuvent donc signaler la même sélection. Les filtres d'une stratégie ou de la
convergence utilisent ses prises exactes. Toucher une ligne du tableau Stratégies
ouvre ses paris pour la période correspondante, avec les badges du rejeu lorsque
la période est historique.

Le CSV contient tous les résultats des filtres et de la recherche, même si seules
50 cartes sont rendues. Encodage UTF-8 avec BOM, séparateur point-virgule,
guillemets échappés, cellules texte susceptibles de devenir des formules
neutralisées par une apostrophe. Les valeurs numériques restent numériques ;
`ecart` et `clv` sont des ratios (0,03 = 3 %). La CLV est celle de clôture validée,
et reste vide si sa mesure manque. Le gain est celui enregistré dans la simulation.

## Courbes et segments

Les courbes reprennent la mise fixe de 10 €, les statuts et les coupures de
connaissance des tableaux. Elles avancent par date de règlement. Le nombre de
points et le dernier gain cumulé doivent égaler le nombre de réglés et le gain
de la ligne correspondante. La légende masque ou affiche chaque comparateur.

Les segments couvrent les 15 croisements non vides entre tranche de cote,
bookmaker, sport et référence. Ils gardent un minimum de dix paris réglés et
suppriment les sous-ensembles identiques. La référence attribuée à un pari unique
est celle de sa première détection, selon le dédoublonnage existant : un même pari
ne devient pas plusieurs mises. Le dépliage applique ces mêmes dimensions aux
paris réglés et aux paris à venir. Ces segments sont exploratoires : multiplier
les croisements augmente le risque d'observer des réussites dues au hasard.
