# Règlements : diagnostic du 15 octobre 2026

Au relevé `421c459` (12:27 UTC), 372 lignes brutes sont `a_regler`, dont
304 témoins Pinnacle brut et 68 lignes avec référence calculée. Le compteur du
site déduplique plusieurs simulations/références : il ne compte ni les lignes
brutes ni les événements sportifs uniques.

Les quatre clés The Odds API sont reconnues. Le dernier cycle n'a aucun pari
éligible à ce secours : EuroCup/Euroligue féminines, KHL, volley, coupes de
football et périodes ne bénéficient pas de sa couverture actuelle. Augmenter
les crédits ne résout pas ce manque. API-Sports renvoie explicitement
`Your account is suspended` ; seul le titulaire peut rétablir cet accès.

Le statut `a_regler` démarre après 12 heures, mais une source unique ordinaire
n'est validée qu'après 24 heures. Le statut n'arrête pas les tentatives horaires.
Le site explique désormais cette attente, affiche le diagnostic, la prochaine
validation possible et la panne API-Sports, et regroupe les sélections par
sport/équipes/date. Le compteur conserve tous les tickets en attente, témoins
compris ; aucun pari n'est effacé ou considéré comme perdu faute de résultat.

La source NHL officielle, sans clé, complète les tiers, prolongation et tirs
au but. Seuls les matchs explicitement terminés et les décomptes cohérents sont
acceptés. Une confirmation NHL + ESPN/DraftKings distingue un final de scores à
60 minutes improprement publiés comme finaux. Les autres désaccords restent
bloquants. Une source finale ne vaut jamais preuve d'une mi-temps.

Le rattrapage documenté est enregistré dans `resultats_manuels.json` sur la
branche de données, avec les URL officielles et, lorsqu'il est disponible,
le détail PulseScore cohérent avec le final corroboré. Pour Santarém–Gil
Vicente : 0-0 à la pause et 2-2 à 90 minutes ; le 2-3 après prolongation est
exclu. Les règles de validation des sources isolées n'ont pas été assouplies.
Les corrections finales seules peuvent ensuite recevoir un détail automatique
concordant, sans dépasser l'autorisation des paris couverts par la source.
