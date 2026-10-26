# Maquettes de design — à l'attention de Claude Code

Ce dossier contient des maquettes statiques (HTML + captures PNG). Il ne fait pas partie du site en production.

## Contenu
- `vitrine/` : la **page d'accueil publique** (vitrine) à intégrer au site. `vitrine.html` = la maquette, les `vitrine-*-ecran-*.png` = rendus desktop/mobile, `vitrine-desktop-page.png` = la page entière.
- `interface/` : l'**interface connectée actuelle (version A)** habillée de la même direction artistique (DA). `accueil.html`, `strategies.html`, `da.css` + captures `interface-*-ecran-*.png` et `comparatif-avant-apres.png`. **À appliquer sans changer la structure, les onglets ni les sections** : seul l'habillage change.
- `polices/` : polices sous licence libre OFL (Instrument Serif, Familjen Grotesk, Geist Mono), référencées en relatif (`../polices/`).
- Les scripts `rendu.py`, `build.py`, `comparatif.py` sont des outils de génération des captures ; ils contiennent des chemins absolus de la machine de design (`/workspace/design/...`) et ne sont pas à exécuter tels quels.

## Direction artistique
- Titres : **Instrument Serif** ; texte : **Familjen Grotesk** ; chiffres : **Geist Mono**.
- Papier `#ECE9E1`, encre `#12120F`.
- Accent orange `#F2541B` **réservé à l'écart / la value**.
- Perte : rouge brique `#9C3B2E`.
- Filets fins ; **pas** de cartes arrondies, **pas** d'icônes, **pas** de dégradés.

## Points de vigilance sur les chiffres
- Seuls **+631 €** et **+1 198 €** sont des résultats en **Kelly ¼** ; tous les autres montants sont en **mise fixe de 10 €**.
- L'exemple **Struff–Griekspoor** suppose que la cote **1,85** est celle de **Pinnacle** : à vérifier avant publication.

## Intégration
- Le site réel est généré par `scripts/site_web.py` + `web/`. C'est là qu'il faut intégrer.
- **Ne pas toucher** aux stratégies (`@figer_selecteur`), à la collecte, ni aux données.
- Travailler sur une branche et ouvrir une PR vers `ccr-148b8ccc-phitmr`, **sans merger**.
