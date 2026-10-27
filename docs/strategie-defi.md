# Stratégies Défi

Famille distincte des Grok, lancée le 27 octobre 2026 à 01:00 UTC. Les règles viennent d'une recherche sur l'historique des paris simulés : CLV de clôture, références sharp seulement, **une seule mise par cote française** (la première détection qui respecte la règle).

Le rejeu sur cet historique est optimiste : les seuils ont été choisis après coup. Seul le suivi à partir du 27/10/2026 à 01:00 UTC compte. Les prises déjà figées ne reçoivent pas ces clés. Défi 2, Défi 3 et Défi 5 ne sont pas lancés.

Mise fictive 10 €. Le Kelly du site (bankroll 1 000 €, fraction ¼, plafond 2 %) est le même affichage que pour les autres comparateurs. Pas de plafond journalier. La sélection ne lit jamais le résultat, le gain ou la CLV.

La cote française est le couple bookmaker + match + marché (type, période, ligne, joueur) + issue. Deux books français sur le même choix restent deux mises. Deux références de la même cote n'en font qu'une.

## Défi 1 · Écart fort, match proche

Référence Pinnacle, Betfair ou Polymarket. Jamais un bookmaker français, jamais Smarkets, Kalshi ou le Consensus. Écart ≥ 6 %, sans plafond. Cote française de 1 à 10. Détection à moins de 12 h du coup d'envoi, et avant le coup d'envoi (l'instant du début est accepté, jamais après).

CLV historique, période entière : **232 paris réglés, CLV +9,4 %** (intervalle à 95 % [+6,7 % ; +12,1 %]).

## Défi 4 · Pinnacle très gros écart

Pinnacle seul. Écart ≥ 8 %, sans plafond. Cote française de 1 à 10. N'importe quand avant le coup d'envoi, jamais après. Pas de fenêtre de 12 h.

CLV historique, période entière : **181 paris réglés, CLV +7,9 %** (intervalle à 95 % [+5,2 % ; +10,5 %]).

## Contrôles ajoutés pour le suivi

Les deux exigent une preuve de correspondance ≥ 0,85 et une référence lue depuis moins de 15 minutes (15 minutes pile sont acceptées, comme pour Grok 9 et 10). L'écart stocké doit coller à `cote / cote_juste − 1` (tolérance 0,002, cote juste > 1) : une cote de 1 ne peut pas porter un écart positif cohérent. Une ligne signalée suspecte est écartée.

Le crible historique « délai < 12 h » gardait aussi des détections déjà après le coup d'envoi. Le suivi les refuse. Il ne filtre ni le sport ni le marché : le crible ne le faisait pas non plus. Grok 1 à 10 ne changent pas.
