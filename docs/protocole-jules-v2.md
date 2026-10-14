# Protocole Jules v2 reconstruite — figé avant recalcul

But : réaliser l'intention de Jules (commit `b3e8e8c`), sans rechercher des seuils
qui maximisent artificiellement les résultats déjà vus. Aucun rendement futur garanti.

## Règle unique à évaluer

Pinnacle, Betfair et Polymarket ; Winamax, Betclic, Unibet et PMU ; sports existants
du moteur. Cotes 1,30–2,80, edge 2,5–12 %, référence de 5 minutes au maximum,
détection de 15 minutes à 18 heures avant le début. Cote juste et edge cohérents,
preuve conforme, identifiant de référence et ressemblance >= 0,85 obligatoires.
Marchés 1N2, vainqueur, total et handicap ; match ou temps réglementaire explicite.
Tennis/volley : vainqueur du match seulement ; lignes entières ou demi-points.

Première opportunité admissible par événement identifiable. En simultané : edge
décroissant, cote décroissante, bookmaker et identifiant pour départager. Une mise
fictive de 10 €, huit sélections au plus par jour civil de Paris. Aucun résultat,
gain ou CLV finale n'entre dans la sélection. Aucune sélection passée remplacée.

## Identité des événements

Les identifiants de référence sont séparés par fournisseur : « Pinnacle 123 » et
« Polymarket 123 » ne désignent pas automatiquement la même rencontre. Relier
progressivement identifiants bookmaker, identifiants de référence et équipes
normalisées à la même heure UTC. Conserver les marqueurs femmes/jeunes/réserves.
Utiliser aussi les noms de la rencontre de référence quand ils sont présents.

Mémoriser les liens sur les correspondances conformes, même si la cote ou l'edge
ne permet pas une prise. Traiter les détections dans leur ordre réel ; ne jamais
préconstruire le graphe avec des correspondances découvertes plus tard. Un lien
tardif entre deux événements déjà joués doit être signalé, sans réécrire le passé.
Des alias sans aucun lien observable restent une limite d'identification.

## Évaluation fixée

Rejeu principal sur le même relevé du 14/10 à 12:09:28 Paris et la même fenêtre
de matchs 7–13 octobre que les comparateurs existants (données `56bed648…`).
Comparer v1, v2 livrée par Jules, v2 reconstruite, Claude, ChatGPT, Gemini et M3.
Même mise de 10 €, mêmes coupures de connaissance des règlements et même contrôle
de CLV. Afficher exposition, résultat, ROI, CLV/couverture et baisse maximale du cumul.
Fournir les IDs, l'empreinte et le commit des données, ainsi qu'un script reproductible.

Un bootstrap groupé par jour donne une incertitude descriptive tenant compte des
rencontres corrélées d'une même journée. Quelques jours ne constituent pas une
validation indépendante. Publier aussi le résultat sans le meilleur pari et avec
des cotes dégradées de 1 %. Aucun changement de seuil après lecture de ces résultats.

Tout historique déjà consulté reste exploratoire, même découpé chronologiquement.
Seul le suivi après publication sera prospectif : **15/10/2026 à 00:30 Paris**
(`2026-10-14T22:30:00Z`), si la publication précède cette heure ; sinon le lancement
sera repoussé. La v1 et les autres stratégies ne sont pas modifiées.
