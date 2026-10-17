# Revue contradictoire — Simulation et décisions, 17 octobre 2026

## Verdict

L’audit identifie deux protections utiles : valider les nouvelles prises indépendamment du comparateur et vérifier les identifiants avant de figer les décisions. Le diagnostic statistique est trop favorable : un seuil de 30 tickets ne suffit pas à rendre le sigma interprétable, et un registre prospectif ne couvre pas rétroactivement toutes les prises anciennes.

Cette passe ne change aucun critère des stratégies, aucune mise historique ni aucun règlement. Elle durcit les nouvelles prises et décrit plus honnêtement les limites des segments.

## Décisions sur les sept recommandations

| Point | Décision et justification |
| --- | --- |
| `tranche()` avec une cote invalide | Retour explicite `cote invalide`, sans casser la génération du bilan. `None` provoquait une `TypeError`, plutôt qu’une `StopIteration` ; les deux risques sont traités. Les valeurs non numériques, booléennes, non finies et ≤ 1 sont invalides. |
| Bornes A–E / X | Seuils conservés et testés : 10 entre dans A–E ; 10,0001 peut entrer dans X. La petite bande `(10 ; 10,0001)` reste hors sélection, conformément aux constantes existantes ; aucun élargissement de critère n’est introduit. |
| Fraîcheur dans `placer()` | Validation des dates obligatoires, de leur écart et de leur âge lors de la décision. Deux lectures anciennes mais contemporaines sont refusées. |
| Sigma des segments | Seuil d’affichage maintenu à 10 ; ajout des événements distincts, d’un indicateur de conditions minimales et de ses limites. Un simple `n >= 30` est insuffisant. |
| ROI et paris ouverts | Calcul conservé : les mises `en_cours` et `a_regler` ne sont pas dans le dénominateur. Test ajouté, avec CLV provisoire exclue. Un ROI stocké à `1.2` signifie +120 %. |
| Identifiants dans le registre | Validation préalable de tout le lot : identifiant persistant, unicité, appartenance au registre par le même objet et date de décision exploitable. |
| Imports locaux | Choix conservé et documenté : évite les imports circulaires entre décisions, convergence, stratégies et laboratoire. |

## Prises : protection supplémentaire

Pour une nouvelle prise, les dates de la cote française (`detecte`) et de la référence (`lu_reference`) doivent :

- être présentes, lisibles et munies d’un fuseau ;
- être espacées d’au plus 15 minutes ;
- dater d’au plus 15 minutes au moment réel de la décision ;
- précéder le coup d’envoi, avec la marge de prise de 30 secondes déjà existante.

La tolérance d’horloge existante de 60 secondes est conservée pour les lectures légèrement futures, sans autoriser une lecture après le début du match. Si `collecte_recue` est renseignée, elle doit aussi passer les contrôles ; elle ne remplace jamais une détection absente ou ancienne.

Le pseudo-code de l’audit aurait laissé passer des dates absentes et deux lectures vieilles d’une heure, tant qu’elles sont proches entre elles. Le nouveau contrôle refuse ces cas. Les nombres invalides sont écartés avant le tri : un import défectueux ne doit pas bloquer les autres opportunités du lot.

### Cas particulier du consensus

Le consensus utilisait comme date synthétique celle de la cote française. Vérifier uniquement ce champ ne prouve pas l’âge de chacune de ses références.

`comparer()` transmet désormais `lectures_references`, contenant les horodatages de ses composantes. `placer()` vérifie chaque date et les conserve dans la preuve de prise. Une nouvelle opportunité Consensus importée sans au moins deux dates de composantes n’est pas prise. Les anciennes prises et leurs preuves restent intactes ; aucun champ n’est rempli rétroactivement.

La moyenne des probabilités, les prix et les seuils de détection ne changent pas. Une réception HTTP récente ne prouve toujours pas que le fournisseur n’a pas servi un prix mis en cache : cet horodatage est une preuve de lecture, pas une garantie de fraîcheur du marché à la seconde.

## Registre : `id()` n’est pas un identifiant persistant

`id(p)` reste adapté pour relier les sélections aux mêmes objets pendant une exécution. Il n’est jamais enregistré comme identifiant durable. Après sauvegarde et rechargement, `selections_figees` rétablit les acceptations et les refus sur les nouveaux objets.

Avant toute mutation du lot, `figer_nouveaux()` refuse :

- un identifiant absent, vide ou qui n’est pas une chaîne ;
- un nouvel identifiant absent ou dupliqué dans le registre ;
- un candidat fourni comme copie d’un objet du registre ;
- une date `decide_le` absente, invalide ou sans fuseau.

Le cycle transmet déjà les objets renvoyés par `placer()`, avec leur identifiant déterministe `_id()`. Un test vérifie ce chemin complet puis un aller-retour JSON : les votes et refus figés survivent au changement d’identités Python. Les écritures répétées ne réévaluent pas les décisions déjà enregistrées.

Sur le relevé de contrôle : **12 712 identifiants présents et uniques**, aucune cote de prise invalide détectée. Ce constat décrit ce fichier de contrôle, pas tous les futurs imports. Les paris anciens sans registre restent reconstruits par les sélecteurs : ils ne deviennent pas des décisions prospectives figées par cette passe.

## Segments : ce que le sigma permet réellement de dire

La formule `somme(q × (1−q))` est la variance d’une somme de Bernoulli indépendantes, avec des probabilités potentiellement différentes. C’est un modèle de Poisson-binomial, pas une validation automatique des performances.

Trois limites supplémentaires comptent ici :

1. Des marchés différents du même match restent corrélés, même après déduplication d’une sélection entre références.
2. Un remboursement ou demi-règlement ne se résume pas à une Bernoulli gagné/perdu avec probabilité `1 / cote_juste`.
3. Chercher les meilleurs parmi de nombreux segments crée une sélection a posteriori, sans correction des essais multiples.

Les chiffres existants, dont `ecart_sigma`, restent inchangés pour préserver les bilans. Les nouvelles métadonnées indiquent les situations où leur lecture est fragile :

| Champ | Rôle |
| --- | --- |
| `evenements` | Nombre d’événements reliés dans les tickets du segment. |
| `sigma_limites` | Moins de 30 paris, tickets d’un même événement, règlements non binaires, ou moins de 5 succès/échecs attendus. |
| `sigma_fiable` | Vrai uniquement si aucune de ces limites n’est détectée. Conditions minimales descriptives, jamais certificat d’indépendance ni de rentabilité. |

Sur les **258 segments** du relevé disponible :

- **230** contiennent plusieurs tickets d’un événement ;
- **131** ont moins de 30 paris ;
- **104** comprennent au moins un demi-règlement ou remboursement ;
- **59** ont des effectifs attendus extrêmes ;
- **aucun** ne satisfait toutes les conditions minimales simultanément.

Les catégories se recoupent. Ce constat ne démontre pas l’absence d’edge ; il interdit seulement de présenter ces sigmas comme une preuve statistique de solidité. Le regroupement d’événements reste dépendant des alias disponibles ; des dépendances entre matchs peuvent également subsister.

Dans le site, le badge « Solide » est remplacé par « À confirmer ». Les détails montrent les matchs distincts et les limites détectées. Les anciens objets sans ces champs restent affichables, sans verdict favorable inventé. Le texte n’affirme plus qu’un sigma inférieur à 2 prouve le hasard ou qu’une CLV manquante équivaut à une CLV négative.

## Validation

- **545 tests Python et 36 tests JavaScript passent**, soit **581 tests**.
- Cas couverts : bornes d’écart/cote, valeurs non finies, données manquantes, deux lectures simultanément anciennes, limites de 15 minutes, décalages de fuseau, consensus avec une composante périmée, doublons et copies dans le registre, atomicité des validations, persistance après JSON, ROI des paris ouverts et interprétation des segments.
- Comparaison avant/après sur 12 712 paris : sélections des comparateurs existants et indicateurs financiers identiques.
- Comparaison des 258 segments : tous les champs numériques antérieurs sont identiques ; seules les métadonnées et leur présentation sont ajoutées.
- Génération du site et vérification du JavaScript embarqué réussies ; pas d’appel à une API de paris ni de modification du fichier de données de production.

Cette simulation reste un suivi à mise fixe : elle ne démontre ni l’acceptation réelle des cotes, ni une gestion complète du capital, ni un rendement futur. L’étape suivante peut examiner la persistance, la déduplication inter-archives et les risques de surcomptage, sans confondre un ticket, un signal et un événement indépendant.
