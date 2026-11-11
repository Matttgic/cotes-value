# Claude Signal : Double avis et Prix frais

Deux stratégies conçues le 11/11/2026 par Claude. Suivies à partir du **12/11/2026 à 00:00 UTC** (01:00 à Paris),
figées au lancement, sans rejeu : seules les nouvelles détections comptent. Code : `cotes/strategie_claude_signal.py`,
clés `claude_signal_double` et `claude_signal_frais`.

## Idée

Les stratégies déjà suivies filtrent la cote, l'écart, le délai, le bookmaker. Ces deux-ci lisent des mesures
enregistrées à la prise depuis fin octobre, que personne n'utilisait pour choisir :

| Stratégie | Règle propre | Raison |
|---|---|---|
| **Double avis** | Pinnacle et Polymarket donnent chacun, séparément, au moins 2 % de valeur sur la même cote française (`ecart_polymarket` pour un pari Pinnacle, `ecart_pinnacle` pour un pari Polymarket) | Deux sources sharp indépendantes se trompent rarement ensemble ; une seule peut être en retard ou mal associée |
| **Prix frais** | Pinnacle, prix de moins de 400 s (`age_prix_pinnacle_s`, âge réel du cache, pas l'heure de notre lecture), et cote juste Pinnacle pas en hausse de plus de 0,5 % sur 10 à 60 min (`mouvement_pinnacle`) | Un écart contre un prix de dix minutes est souvent un retard de notre référence, pas une erreur du bookmaker |

Communs aux deux : cote 1,30–5,00, écart 2–15 %, ni score exact ni mi-temps/fin, équipes non inversées, tous les
bookmakers sauf OlyBet, match pas commencé, une mise fictive de 10 € par cote française (la première détection qui
passe la règle), aucun plafond.

## Ce que disent les données

Rejeu des sélecteurs du code sur les paris enregistrés (branche `donnees` du 10/11/2026 à 21 h UTC). CLV de clôture
(≤ 30 min avant le coup d'envoi), une moyenne par match, intervalle à 95 % par rééchantillonnage des matchs
(3 000 tirages, graine 11).

| | Période | Paris réglés | Matchs | Gain (10 €) | ROI | Réussite | CLV par match [IC 95 %] |
|---|---|---|---|---|---|---|---|
| **Double avis** | 18–24/10 | 21 | 18 | +19,8 € | +9,4 % | 48 % | +2,34 % [−1,0 ; +5,8] |
| | 25/10–2/11 | 47 | 37 | +78,6 € | +16,7 % | 57 % | +3,10 % [+0,2 ; +5,9] |
| | 3–10/11 | 67 | 41 | +164,2 € | +24,5 % | 60 % | +3,30 % [+1,1 ; +5,7] |
| | Ensemble | 135 | 96 | +262,6 € | +19,5 % | 57 % | +3,06 % [+1,4 ; +4,7] |
| **Prix frais** | 25/10–2/11 | 75 | 37 | +213,3 € | +28,4 % | 60 % | +2,34 % [−1,5 ; +6,7] |
| | 3–10/11 | 314 | 192 | +132,0 € | +4,2 % | 50 % | +1,94 % [+0,8 ; +3,0] |
| | Ensemble | 389 | 228 | +345,3 € | +8,9 % | 52 % | +1,99 % [+0,8 ; +3,1] |
| Témoin : Pinnacle, mêmes filtres communs, sans signal | Ensemble | 1 417 | 819 | −42,5 € | −0,3 % | 49 % | +0,33 % [−0,3 ; +1,0] |

Lecture : les mêmes paris sans le signal ne battent pas la clôture (+0,33 %, intervalle à cheval sur zéro). Avec le
second avis, la CLV par match passe à +3 % et son intervalle est au-dessus de zéro ; avec un prix frais, à +2 %.
37 paris sont communs aux deux stratégies.

Mesures brutes derrière les seuils (paris uniques réglés, cote ≤ 5, du 25/10 au 10/11) :

- Pari Pinnacle, Polymarket à ≥ 2 % : CLV +5,6 % puis +6,4 % sur les deux périodes ; Polymarket contre (écart < 0) :
  −0,9 % puis −3,1 %.
- Prix Pinnacle de plus de 400 s : CLV −5,3 % puis −3,0 % ; de moins de 400 s : positive sur les deux périodes.
- Cote juste Pinnacle en hausse de plus de 0,5 % (Pinnacle s'éloigne de la sélection) : CLV −10,3 % puis −8,1 %
  (17 puis 10 mesures).
- OlyBet : CLV −4,4 % puis −3,5 %.

## Limites

- **Ce n'est pas une validation indépendante.** Les seuils ont été fixés en regardant les périodes du 25/10 au
  10/11. Seule la semaine du 18 au 24/10 n'avait pas été regardée pour Double avis : elle va dans le même sens,
  sur 21 paris seulement. Prix frais n'a aucune période non regardée (la mesure existe depuis le 1/11).
- Peu de matchs : 96 pour Double avis. Le ROI peut encore n'être qu'une bonne série ; la CLV est le chiffre à suivre.
- Double avis dépend de Polymarket : sans prix Polymarket sur le marché, pas de pari (1 591 détections sans
  second avis sur la période).
- Les deux stratégies se recoupent avec les stratégies Pinnacle et Polymarket existantes : leurs mises ne
  s'additionnent pas.
- Aucune rentabilité future n'est démontrée. Le suivi depuis le 12/11 fait foi.
