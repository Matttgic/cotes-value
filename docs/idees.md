# Idées et suggestions (11/11/2026)

Ce qui est déjà fait dans le code est marqué **fait**. Le reste est classé par ce que ça rapporterait, avec ce
qu'il faut pour le faire.

## Idées que le projet n'exploitait pas

| Idée | État | Ce que disent les données | Suite |
|---|---|---|---|
| **Second avis indépendant** : ne parier que si deux références sharp voient la valeur chacune de leur côté | **Fait** : stratégie Claude Signal · Double avis | CLV par match +3,1 % contre +0,3 % sans le signal (docs/strategie-claude-signal.md) | Suivi depuis le 12/11 |
| **Âge réel du prix** de la référence, pas l'heure de notre lecture | **Fait** : Claude Signal · Prix frais | Prix de plus de 400 s : CLV négative sur les deux périodes | Suivi depuis le 12/11 |
| **Durée de vie d'une value** : combien de temps pour jouer, par bookmaker | **Fait** : `scripts/etude_duree_values.py` | 80 % encore jouables après 15 min ; Betclic corrige en 14 min, PMU en 65 (docs/duree-values.md) | Afficher « encore jouable ~X min » dans l'alerte |
| **CLV maison** : le bookmaker a-t-il baissé sa propre cote après la détection ? Mesure sans référence | **Fait** (étude) | Cote montée ensuite par le bookmaker : ROI −27,5 %, CLV −10,3 % ; baissée : +4,7 % | La publier à côté de la CLV dans chaque fiche |
| **Origine de la value** : le bookmaker a monté sa cote, ou la référence a bougé sans lui ? | **Fait** (étude) | Référence qui bouge seule : CLV +3,2 % ; bookmaker qui monte sa cote : −1,2 % | L'enregistrer à la prise, comme filtre à tester |
| **Contrôle croisé des règlements** : le même match réglé chez deux bookmakers doit avoir le même score | **Fait** : `resultats.incoherences_freres` | 4 désaccords sur 700 paires, dont un règlement faux | Corriger le pari signalé |
| **Rappel avant le match** : relire la value 30 min avant le coup d'envoi et prévenir si elle existe encore | À faire | 28 % des values tiennent jusqu'au match | Une alerte « toujours là » : la liquidité est meilleure, les compositions sont connues |
| **Alerte d'annulation** : le bookmaker vient de monter la cote d'un pari que tu as joué | À faire | Voir CLV maison : c'est le signe le plus net d'une fausse value | Possible avec l'historique des cotes, sans appel de plus |
| **Mise arrondie** : proposer la mise Kelly arrondie à 5 € | À faire | — | Des mises rondes ressemblent à celles d'un joueur ordinaire ; les bookmakers limitent les comptes aux mises « calculées » |
| **Kelly par match** : plusieurs sélections du même match se partagent une seule mise | À faire | Les paris d'un même match sont corrélés (la note /100 le compte déjà par match) | Plafond de 2 % par match au lieu de par pari |
| **Calibration des cotes justes** : corriger la probabilité juste par ce qui a été observé à cette cote | À faire | Au-delà de la cote 5, les cotes justes surestiment de moitié (docs/etude-longues-cotes.md) | Un écart « corrigé » remplacerait le plafond de cote |
| **Journal réel** : noter la mise et la cote vraiment obtenues, à côté du pari simulé | À faire | — | Mesure le glissement entre l'alerte et le pari, et le vrai bilan |
| **Cotes boostées** : lire les promotions des bookmakers français | À faire | — | Souvent la plus grosse valeur du jour ; demande un lecteur par bookmaker |

## Interface : ce qui a changé

- **Mise des bilans** : un menu (Kelly ¼ par défaut, Kelly ⅛, Kelly ½, Kelly ¼ plafonné à 1 %, gain constant,
  fixe 1 %) et une **bankroll de départ** modifiable. Tous les montants suivent ; ROI, CLV, notes et avis ne
  changent pas.
- **Périodes** du Bilan (Paris uniques, Stratégies) : des menus déroulants, comme « Afficher » et « Classer par ».
- **Avis d'analyste** : six questions cochées, ce qu'il faut faire du verdict (« À suivre », « À surveiller »,
  « À éviter pour l'instant », « Attendre »), et le seuil de chaque preuve manquante.
- **Props** : la comparaison DraftKings – Pinnacle sous celle de FanDuel.

## Interface : suggestions

1. **Accueil** : le premier chiffre est le bilan de tous les paris uniques, tiré vers le bas par les cotes de plus
   de 10 (767 paris, −3 400 € en mises fixes). Montrer plutôt le bilan des stratégies recommandées, ou des cotes
   de 10 au plus, et garder l'ensemble en second.
2. **Fait** : le verdict de l'analyste en un mot (« Fiable », « Prometteur », « Chance », « Trop tôt ») à
   côté de la note dans la liste des stratégies, sans ouvrir la fiche.
3. **Bilan trop long** : « Essais en cours » (18 méthodes de mise, combinaisons) devrait être replié par défaut ou
   déplacé dans un sous-onglet « Laboratoire ». Les tableaux par écart, cote, sport et référence suffisent en
   première lecture.
4. **Stratégies** : 77 lignes. Un filtre « Fiable ou prometteur » coché par défaut réduirait la liste à ce qui
   mérite d'être lu ; le reste à la demande.
5. **Fiche d'un pari** : afficher « encore jouable ~X min chez ce bookmaker » et l'âge du prix de référence, les
   deux informations qui décident s'il faut jouer.
6. **Mobile** : la ligne d'explication sous le menu des mises prend une ligne entière ; la passer en infobulle une
   fois le mode choisi.
7. **Santé** : y afficher les règlements incohérents (`resultats_a_saisir.json` › `incoherences`), pas seulement
   dans le fichier.
