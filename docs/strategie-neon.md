# Stratégies Néon 1, 2 et 3

Code : `cotes/strategie_neon.py`. Suivies dès le **20/11/2026 à 1 h (Paris)**, sans rejeu, inscrites au protocole
(`cotes/protocole_registre.json`). Mise fictive 10 € par pari.

## D'où elles viennent

Néon (IA externe) a reçu l'export `paris_cotes_value.csv` (7 005 paris du 5/10 au 19/11/2026). Elle a choisi ses seuils sur
les paris détectés **avant le 5/11/2026** (construction), sans regarder les suivants. Les chiffres de **validation**
(paris détectés à partir du 5/11) ont été calculés ici, une seule fois, sans retoucher les seuils.

## Règles communes

- Bookmakers : PMU, Betclic ou Unibet.
- Ni volley, ni total au basket ; ni score exact, ni mi-temps/fin de match, ni handicap à 3 issues.
- Match entier ou temps réglementaire seulement.
- Match pas commencé ; équipes non inversées.
- Une même sélection (match, marché, période, ligne, issue) au plus une fois, tous bookmakers confondus : la première
  détection ; à la même seconde, la plus haute cote puis le plus gros écart.
- Un seul pari par match : la première détection ; à la même seconde, le plus gros écart puis la plus haute cote.
- Jamais de filtre sur le résultat, la CLV, la cote de clôture ni le nombre de références.

## Règles propres

| Stratégie | Références | Cote | Écart | Délai avant le match |
|---|---|---|---|---|
| Néon 1 · Socle sharp | Pinnacle, Betfair ou Matchbook, première à voir la cote | 1,15–4 | 4–25 % | ≤ 24 h |
| Néon 2 · Sniper écart | Pinnacle, Betfair ou Matchbook, première à voir la cote | 1,20–3,5 | 6–25 % | ≤ 12 h |
| Néon 3 · Consensus multi | Consensus, même s'il voit la cote après une autre référence | 1,15–4 | 2,5–25 % | ≤ 24 h |

« Première à voir la cote » : si une autre référence (Polymarket, Kalshi…) a repéré cette cote française avant, le pari
est écarté.

## Chiffres (un pari par match, paris réglés)

| Stratégie | Construction (30 j) | Validation (15 j) |
|---|---|---|
| Néon 1 · Socle sharp | 294 matchs · ROI +5,1 % · CLV +4,5 % | 96 matchs · ROI +10,7 % · CLV +4,7 % |
| Néon 2 · Sniper écart | 103 matchs · ROI +24,5 % · CLV +6,3 % | 36 matchs · **ROI −24,6 %** · CLV +6,2 % |
| Néon 3 · Consensus multi | 101 matchs · ROI +10,7 % · CLV +3,5 % | 40 matchs · ROI +16,5 % · CLV +5,2 % |

CLV moyenne hors paris remboursés. Le code ajoute une sécurité absente du CSV (équipes inversées) : il retrouve
exactement les chiffres ci-dessus pour Néon 2 et 3, et 4 matchs de moins pour Néon 1 (290 et 95).

Aucun de ces ROI n'est prouvé : sur si peu de matchs, le meilleur cas plausible reste loin du pire. Le protocole
tranchera sur les paris neufs.

## Avertissement : Néon 2 ressemble à une stratégie retirée

Néon 2 · Sniper écart mise sur les gros écarts (6 % et plus) à moins de 12 h du match, comme **Claude Défi 1**, retirée le
19/11 ([strategies-retirees.md](strategies-retirees.md)). Même profil en validation : CLV élevée, ROI très négatif. Elle
est suivie pour en avoir le cœur net, mais **elle n'est pas à notifier** tant que le protocole ne l'a pas validée.

## Ce qui pourrait les rendre fausses (d'après Néon)

- Cotes déjà bougées au moment de miser : à moins de 12 h et sur un gros écart, la cote disparaît vite.
- Limitation des comptes gagnants chez les bookmakers français.
- Consensus : sa composition peut changer, et son volume a baissé fin octobre.
