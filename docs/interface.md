# Interface du site

Le générateur `scripts/site_web.py` incorpore `web/interface.css` et
`web/interface.js` dans l'unique document HTML. Aucun chargement de bibliothèque,
police distante ou service supplémentaire n'est nécessaire.

- À 760 px et moins : navigation inférieure avec quatre destinations principales
  et un menu Plus ; stratégies présentées en lignes de métriques avec détails
  dépliables. Les petits tableaux conservent toutes leurs cellules, étiquetées.
- Sur ordinateur : tableau de comparaison complet, avec CLV et couverture dans
  une colonne distincte ; opportunités sur deux colonnes.
- Le thème suit les préférences système. Les couleurs des courbes sont adaptées
  au thème sombre. Les fragments d'onglets ne correspondent à aucune ancre
  interne, pour éviter de sauter les titres ou filtres à l'ouverture.
- Le filtre initial des stratégies affiche les comparateurs et variantes ;
  « Toutes » permet toujours d'afficher aussi les 36 règles du laboratoire.
- Recherche, CSV, notifications et actualisation automatique restent branchés
  aux données existantes. Les sélections, gains, périodes et critères ne sont
  pas modifiés par la présentation.

`verification-responsive.html`, produit avec le site, affiche la vraie page dans
une fenêtre de 360, 390, 430 ou 1200 px. Il permet de vérifier les deux thèmes et
les interactions sans changer les préférences du téléphone. Ce cadre ne simule
pas les permissions de notification ou le comportement de Chrome Android.
