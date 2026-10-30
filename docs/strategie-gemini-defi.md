# Stratégies Gemini Défi

Famille proposée par **Gemini Argon** (une IA externe), le 29 octobre 2026, sur le modèle de la
[famille Défi](strategie-defi.md). Elle est distincte des Grok, des Défi et de la stratégie Gemini
Argon V1 ([strategie-gemini.md](strategie-gemini.md)) : module `cotes/strategie_gemini_defi.py`,
clés `gemini_defi_1`, `gemini_defi_3`, `gemini_defi_4` et `gemini_defi_5`, libellé « Gemini Défi »
sur le site. Aucune stratégie figée existante n'est modifiée. Les règles suivent la section 3 de la
réponse finale de Gemini (« Récapitulatif final — audit, validation & spécifications »).

**Gemini Défi 2 (consensus multi-sharps, `convergence ≥ 2`) a été abandonnée par Gemini** après avoir
vu la validation : sa CLV tombe de +5,16 % en construction à +1,1 % en validation (IC traversant zéro),
une fois le flux Betfair éteint après le 18/10. Elle n'a ni clé, ni sélecteur, et n'est pas suivie.
Ses chiffres de rejeu restent ci-dessous pour mémoire.

Comme les Défi, chaque stratégie :

- est figée au lancement (`@figer_selecteur`) : une prise déjà décidée ne reçoit jamais la clé après coup ;
- n'est suivie qu'à partir de sa mise en service, le **30 octobre 2026 à 01:00 UTC** (02:00 à Paris),
  sans rejeu sur l'historique ;
- simule une mise fictive de **10 €** (le Kelly du site reste le même affichage que pour les autres comparateurs) ;
- ne lit jamais le résultat, le gain, la CLV ni la cote de clôture pour choisir ses paris.

## Tronc commun

- Référence Pinnacle, Betfair ou Polymarket (jamais Smarkets, Kalshi, Matchbook, le Consensus ni un book français) ;
  Gemini Défi 5 : Pinnacle seul.
- `equipes_inversees` différent de `True` : `False` et vide sont acceptés.
- Une seule mise par cote française (`cle_cote_fr` = match du bookmaker | marché | période | ligne | issue | joueur) :
  la première détection qui passe la règle. Deux books français sur le même choix restent deux mises ;
  deux références sur la même cote n'en font qu'une. Une détection refusée ne consomme pas la cote.
- Bornes incluses. Délai : `0 < delai_min ≤ borne` (Gemini Défi 5 : `15 ≤ delai_min ≤ 720`).

## Règles exactes

| Stratégie | Périmètre | Cote française | Écart | Délai (min) | Âge réf. (s) | Correspondance |
|---|---|---|---|---|---|---|
| **Gemini Défi 1 · Indoor & Glace** | basket, hockey, handball, volley | 1,15 – 6,00 | 4 – 25 % | ≤ 720 | ≤ 180 | — |
| **Gemini Défi 3 · Sniper principaux** | groupe principal | 1,25 – 10,00 | 6 – 20 % | ≤ 1 440 | ≤ 150 | ≥ 0,75 |
| **Gemini Défi 4 · Lignes asiatiques** | football, basket, handball, rugby, hockey, football américain ; `HANDICAP`, `TOTAL`, `TOTAL_DOM`, `TOTAL_EXT` | 1,35 – 3,50 | 4 – 12 % | ≤ 720 | ≤ 140 | ≥ 0,85 |
| **Gemini Défi 5 · Exotiques foot** | Pinnacle seul ; football ; `CORRECT_SCORE`, `HALF_TIME_FULL_TIME` ; au plus 2 cotes par match ; au plus 10 mises par jour UTC | 12 – 75 | 8 – 35 % | 15 – 720 | ≤ 140 | ≥ 0,85 |

Groupes de marché (comme l'export) : principal = `RESULTAT_1N2`, `VAINQUEUR`, `DRAW_NO_BET`, `DOUBLE_CHANCE` ;
handicap = `HANDICAP`, `HANDICAP_3`, `SETS_HANDICAP`, `JEUX_HANDICAP` ; total = `TOTAL`, `TOTAL_DOM`,
`TOTAL_EXT`, `JEUX_TOTAL`, `SETS_TOTAL` ; tout le reste est exotique.

### Correspondance entre l'export et les champs du code

| Export (`paris_regles_sharp_defi.csv`) | Champ interne |
|---|---|
| `cote_fr` | `cote` |
| `ecart_pct` | `100 × ecart`, arrondi à 4 décimales comme l'export |
| `delai_min` | `debut − detecte`, en minutes |
| `age_reference_s` | `detecte − lu_reference`, en secondes, **signé** (une référence relue quelques secondes après la cote française passe, comme dans l'export) |
| `marche_type` / `groupe_marche` | `marche` / table ci-dessus |
| `equipes_inversees` | `preuve_prise.equipes_inversees` |
| `score_association_journal` | `preuve_prise.ressemblance_noms` (même score lu dans le journal des opportunités) |
| `evenement` | match relié entre books (`cotes.evenements.identites`) |

### Gemini Défi 5 : plafonds dans l'ordre d'arrivée

Règle temps réel de Gemini (section 2.2 et 3 de sa réponse finale), appliquée telle quelle :

1. au plus **2 mises par match** (`evenement`), les premières détections valides dans l'ordre d'arrivée ;
2. au plus **10 mises par jour UTC** (`detecte_utc[:10]`), les premières détections valides de la journée ;
3. si plusieurs détections ont **exactement le même horodatage** pour la dernière place d'un match ou d'une
   journée, on les départage par **écart décroissant**. Ce départage ne joue qu'à égalité de seconde : une
   détection arrivée plus tôt garde sa place, même avec un écart plus faible.

Une cote écartée par un plafond est perdue : sa détection suivante ne la rattrape pas. La première version de
Gemini classait toute la journée par écart décroissant avant de garder les 10 premières, ce qui n'est pas
faisable en direct ; Gemini l'a remplacée par cette règle. Gemini Défi 1, 3 et 4 n'ont pas de plafond.

### Écarts de lecture avec le script de Gemini (section 6)

Sans effet sur les règles :

- à la même seconde, deux références sur la même cote française (Défi 1, 3, 4) : le code garde l'ordre du
  registre ; le script de Gemini laisse pandas choisir (`sort_values` non stable). Sur l'export, cela remplace
  2 paris de Défi 3 et 1 pari de Défi 4, sans changer les N ;
- le script de Gemini dédoublonne bloc par bloc : une cote déjà prise en construction peut être reprise en
  validation (Défi 3 : 37 paris de validation au lieu des 35 annoncés en section 3). Le code applique la règle
  écrite, une seule mise par cote française sur toute la période, et retrouve les 35 de la section 3.

## Rejeu sur l'historique (optimiste)

Export de la recherche Défi : 2 845 détections réglées, sharp seulement, du 5 au 26 octobre 2026.
Découpe chronologique : construction avant le 18/10/2026 à 02:29:01 UTC, validation après.
Gemini a choisi ses seuils sur la construction, puis a regardé la validation pour retenir 4 stratégies sur 5.
CLV de clôture (lecture ≤ 30 min avant le coup d'envoi), intervalle à 95 % **clusterisé par match**
(erreur-type sandwich regroupée par `evenement`). ROI = somme des gains / (10 € × N).
Source : `rejeu_gemini.py` / `rejeu_resultats.json` (rejeu de référence) pour Gemini Défi 1, 3 et 4, dont les
sélecteurs du code retrouvent exactement les mêmes paris sur le même export (`tests/fixtures/gemini_defi_rejeu.csv`,
`tests/test_strategie_gemini_defi.py`). Gemini Défi 5 : statistiques recalculées (même méthode) sur les paris
retenus par le sélecteur du code, qui sont exactement ceux du script de Gemini (section 6 de sa réponse finale).

| Stratégie | N constr. | avec CLV | matchs | CLV [IC 95 %] | ROI | N valid. | avec CLV | matchs | CLV [IC 95 %] | ROI |
|---|---|---|---|---|---|---|---|---|---|---|
| Gemini Défi 1 | 175 | 135 | 86 | +6,37 % [+3,97 ; +8,77] | +23,9 % | 45 | 33 | 25 | +6,77 % [+0,36 ; +13,17] | −29,5 % |
| Gemini Défi 3 | 59 | 52 | 43 | +11,00 % [+4,31 ; +17,68] | +33,5 % | 35 | 28 | 20 | +4,84 % [−0,36 ; +10,04] | +0,6 % |
| Gemini Défi 4 | 72 | 57 | 35 | +7,74 % [+4,52 ; +10,96] | +28,2 % | 43 | 28 | 25 | +9,33 % [+4,70 ; +13,96] | −31,4 % |
| Gemini Défi 5 (suivie : ordre d'arrivée, même seconde par écart décroissant) | 59 | 36 | 29 | +14,46 % [+11,93 ; +16,99] | +3,4 % | 23 | 17 | 16 | +12,25 % [+5,21 ; +19,29] | −100,0 % |

Variantes du même rejeu, pour information :

| Variante | N constr. | avec CLV | matchs | CLV [IC 95 %] | ROI | N valid. | avec CLV | matchs | CLV [IC 95 %] | ROI |
|---|---|---|---|---|---|---|---|---|---|---|
| Gemini Défi 4 · HANDICAP + TOTAL_DOM | 52 | 40 | 22 | +9,58 % [+5,53 ; +13,63] | +38,7 % | 11 | 11 | 9 | +15,86 % [+8,07 ; +23,65] | −62,7 % |
| Gemini Défi 4 · TOTAL + TOTAL_EXT | 20 | 17 | 16 | +3,43 % [+0,11 ; +6,74] | +1,0 % | 32 | 17 | 16 | +5,11 % [+2,54 ; +7,67] | −20,6 % |
| Gemini Défi 2 · consensus multi-sharps (abandonnée par Gemini, non suivie) | 91 | 78 | 58 | +5,16 % [+2,61 ; +7,70] | +7,7 % | 35 | 27 | 25 | +1,09 % [−2,33 ; +4,51] | +22,5 % |
| Gemini Défi 5 · ordre d'arrivée, même seconde dans l'ordre du registre (version précédente, non suivie) | 59 | 36 | 29 | +13,97 % [+11,50 ; +16,43] | +3,4 % | 23 | 17 | 16 | +12,25 % [+5,21 ; +19,29] | −100,0 % |
| Gemini Défi 5 · plafond trié par écart sur la journée (1re règle de Gemini, non suivie) | 59 | 33 | 27 | +15,31 % [+12,85 ; +17,78] | +1,7 % | 23 | 17 | 16 | +12,25 % [+5,21 ; +19,29] | −100,0 % |
| Gemini Défi 5 · sans plafonds | 80 | 44 | 32 | +13,80 % [+11,62 ; +15,99] | −23,8 % | 23 | 17 | 16 | +12,25 % [+5,21 ; +19,29] | −100,0 % |

Chiffres de la réponse finale de Gemini (section 3), pour comparaison : construction / validation,
Défi 1 175 / 45 paris, Défi 3 59 / 35, Défi 4 72 / 43, Défi 5 59 / 23. Les N, les CLV moyennes et les ROI sont
ceux du rejeu ci-dessus, sauf la CLV de construction de Défi 5 (Gemini annonce +13,97 %, le chiffre de la version
sans départage par écart ; sa propre règle donne +14,46 % : 4 paris remplacés par d'autres détectés à la même
seconde, le 10 et le 11/10). Ses IC de validation diffèrent légèrement (méthode non précisée). Les chiffres de sa première réponse
(Défi 1 182 paris, Défi 3 136, Défi 4 212 + 162, Défi 5 159) venaient de filtres exploratoires plus larges.

## Avertissements

- **Les N de la réponse finale de Gemini se reproduisent** pour les quatre stratégies suivies (voir ci-dessus).
  Ceux de sa première réponse ne se reproduisaient pas : ils venaient de filtres exploratoires plus larges.
- **Les échantillons de validation sont petits** : 23 à 45 paris, 16 à 25 matchs. Les intervalles sont larges et
  le ROI sur trois semaines est très bruité (Gemini Défi 1 et 4 ont une CLV positive en validation mais un ROI
  de −30 %).
- **Gemini Défi 5 a perdu ses 23 paris de validation** (ROI −100 %), à des cotes de la plage 12–75 (cotes jouées
  de 25 à 68), malgré une CLV mesurée de +12,25 %. À ces cotes, 23 paris ne disent presque rien, dans un sens
  comme dans l'autre.
- **31 lignes de l'export avaient une CLV fictive** à cause d'un bug du matcher sur les derbies d'une même ville
  (domicile et extérieur inversés face à la référence, `equipes_inversees = True`), corrigé dans une PR séparée.
  Le filtre `equipes_inversees ≠ True` du tronc commun les écarte ; sans ce filtre, le rejeu donne 175 / 60 / 73 paris
  de construction pour Gemini Défi 1, 3 et 4.
- Le rejeu reste optimiste : les seuils ont été choisis après coup sur la construction, et la validation a été
  regardée avant le lancement. Seul le suivi à partir du 30/10/2026 à 01:00 UTC compte.
