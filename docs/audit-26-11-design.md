# Audit design et UX du site (26-27/11/2026)

**Verdict** : le site tenait déjà bien sur téléphone (aucun débordement horizontal, focus clavier visible partout,
service worker sans cache). Il avait en revanche 412 erreurs d'accessibilité (axe, WCAG 2.1 AA) sur 44 vues, des
cibles tactiles trop petites et un sous-onglet tronqué. Après correction : 4 erreurs, toutes dans `web/boosts.js`
(hors de ce lot), et plus aucune cible sous 44 px sur téléphone. Aucun chiffre ni calcul affiché n'a changé.

Mesure : site construit avec les vraies données (branche `donnees` du 26/11, 23 h 05 UTC), servi en local et ouvert
avec Playwright/Chromium. 11 vues (Accueil, Décision, Paris, Boosts, Bilan, Stratégies, Mes stratégies, Bilan Boosts,
Notifs, Santé, vitrine) × mobile 390×844 et bureau 1440×900 × thèmes jour et nuit. axe-core 4.10, règles WCAG 2.0/2.1 A et AA.

## Avant / après (44 vues)

| Mesure | Avant | Après |
|---|---|---|
| Erreurs axe (WCAG A/AA) | 412 | 4 (`#bb-texte`, boosts.js) |
| dont contrastes en échec | 194 | 0 |
| Éléments qui débordent | 0 | 0 |
| Cibles < 44 px (mobile, 22 vues) | 164 | 0 |
| Cibles < 24 px (bureau, 22 vues) | 78 | 0 |
| Textes < 12 px (mobile, 22 vues) | 1 040 | 890 |
| Erreurs console | 160 | 160 (*) |
| `index.html` | 2 109 Ko (399 Ko gzip) | 2 115 Ko (401 Ko gzip) |
| CSS / scripts / données embarquées | 120 / 324 / 1 625 Ko | 124 / 326 / 1 625 Ko |
| Rendu Accueil, processeur ×4 (FCP, prêt) | 260-316 ms, 2,3-2,5 s | pareil (écart dans le bruit) |

(*) 4 par page : les 2 appels `pushover-lire` vers l'API Pushover, bloqués par le réseau du bac à sable. Pas une
erreur du site ; la vitrine n'en a aucune.

## Problème → correction

| Problème | Correction |
|---|---|
| Lien « Parier chez … » dans le `summary` des lignes de paris : contrôle imbriqué (60 erreurs) | Copie du summary en `<span data-lien>` ouverte au doigt (`ouvrirLienResume`, hôte revérifié) ; le vrai lien reste dans le détail (`web/liens.js`, `modele.html`, `suivi.js`) |
| Carte de chaleur du Bilan : cellules sans rangées ARIA (144 erreurs), petit texte à 1,9-2,8:1 (60) | `role="row"` en `display:contents` ; texte des cases colorées en encre pleine ; intensité max 60 → 48 % |
| Vitrine : gris 3,85:1, orange des grands titres 2,85:1 (134 erreurs sur 4 vues) | Gris `#625F57` (5,3:1) ; orange `#E04A12` sur papier (3,4:1, grands textes), l'orange d'origine reste sur fond encre |
| Dates « Du / Au » sans nom accessible ; bandeau défilant inatteignable au clavier | `aria-label` ; bandeau `tabindex=0` |
| Sous-onglets du Bilan : « Mes stratégi… » tronqué, pas de flèches clavier | Largeur au texte ; flèches, Début, Fin et tabulation itinérante (motif ARIA « tabs ») ; panneau Props sans référence morte |
| Boutons de filtre (références, segments, Santé) : état choisi seulement en couleur | `aria-pressed` |
| Cibles trop petites : menu du thème 46×15, Réglages 26 px, replis 18-36 px, preuves de la Décision 25 px, liens « Stratégies → » 18 px, puces 36 px | 44 px sur téléphone (zone agrandie par `::after` quand la mise en page ne doit pas bouger), 24 px au moins au bureau |
| Accueil : « En cours » seul sur sa ligne sous le gain net | ROI, réussite et en cours sur une ligne de trois (110 px de moins à faire défiler) |
| Accueil : le bouton du pari à jouer avait le même poids qu'un lien secondaire | Bouton « Parier chez … » plein pour les paris et boosts à jouer (Winamax, hors règle, reste au trait) |
| Notifs : « Joué » sur toute la largeur, « Disparu » seul | Grille 2 × 2 |
| Textes d'aide et libellés de commandes en 11 px sur téléphone | 12 px (aides, bouton court du bookmaker), 13 px (replis « mode d'emploi ») |
| Chargement différé invisible pour un lecteur d'écran | `aria-busy` sur le contenu pendant le chargement |
| Boosts (nouveau `boosts.js`) : `.bo-resume`, `.bo-conseil` sans style | Résumé encadré en tête ; conseil en ligne compacte sous chaque carte |

Tests : `tests/design_26_11.test.mjs` (lien du summary, carte de chaleur, dates, aria-busy).

## Non fait, à décider

1. **`#bb-texte`** (texte à copier du Bilan Boosts) sans libellé : dans `web/boosts.js`, ajouter
   `aria-label="Boosts à régler, texte à copier"`.
2. **Poids** : 77 % de `index.html` est le bloc de données, dont le catalogue (1 218 Ko, 2 411 lignes × 44 champs).
   Le charger après l'affichage, comme `mises/*.json`, allégerait le premier chargement d'environ 60 %.
   `decide_le` et `registre_version` (70 Ko bruts) ne sont pas lus par le JavaScript, mais font partie de l'export.
3. **Deux appels `pushover-lire`** à chaque ouverture (`voyant.js` et `pushover.js`) : les faire partager une seule requête.
4. **Textes de 11 px** encore nombreux dans les tableaux denses (Stratégies : médailles, volumes, valeurs). Les
   grossir est un arbitrage entre lisibilité et densité, à faire avec l'utilisateur.
5. **Décision, « Quoi couper ? »** : 22 lignes « Déjà coupée » toutes ouvertes ; les replier sous « Déjà coupées (22) »
   laisserait en vue ce qui reste à décider.
6. **`interface.css`** (124 Ko) empile une dizaine de refontes et beaucoup de `!important` : à consolider (dette).
7. Service worker : aucun cache (pas de gestionnaire `fetch`), mis à jour sans cache HTTP. Rien de périmé, rien à changer.
