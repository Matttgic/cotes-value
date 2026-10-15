# Deux nouvelles variantes de simulation — version 1

Protocole figé le 15 octobre 2026 après l'audit statistique du dépôt.
**Lancement prospectif : 15 octobre 2026 à 06 h Europe/Paris
(`2026-10-15T04:00:00Z`).** Les prises antérieures restent exclues du suivi.
Les comparateurs existants ne sont ni remplacés ni modifiés.

## Claude 1/match · max 10/j

- Tous les critères existants de Claude, avec la date de départ de cette variante.
- Une seule première prise par événement, tous bookmakers et références confondus.
- Edge maximal uniquement pour départager des prises détectées au même instant.
- Dix nouvelles prises au maximum par jour civil à Paris, ordre chronologique.
  Un événement écarté au plafond ne reçoit pas de seconde chance sur une prise
  ultérieure ou le lendemain.
- Mise fictive uniforme de 10 €. Aucun ajustement selon les gains ou les votes.
- Le plafond est un maximum de risque, pas un objectif de volume quotidien.

## Convergence ≥ 3 hors M3

- Au moins trois familles parmi Claude, ChatGPT v1, Gemini Argon v1 et Jules.
- Jules v1 et v2 donnent un seul vote Jules, même si les deux versions sélectionnent.
- Même bookmaker, sélection, période, ligne, issue, joueur, prix et instant UTC.
- Votes des sélections effectives des moteurs, avec leurs propres dates, plafonds
  et dédoublonnages. M3 et les deux nouvelles variantes ne votent pas.
- Une seule première prise par match, tous bookmakers confondus.
- Mise fictive uniforme de 10 €, sans majoration pour quatre familles.

## Identité, causalité et limites

Le regroupement apprend les IDs bookmakers et les alias avec score de
correspondance ≥0,85 au moment où ils sont observés. Les IDs fournisseurs
exigent en plus un contrôle conforme ; un marché refusé peut apprendre un alias. Les noms
normalisés préservent les marqueurs féminin, jeunes/réserves et le début du match.
Sans preuve exploitable, seul l'ID bookmaker est utilisé : un alias inconnu peut
empêcher de reconnaître un doublon entre bookmakers. Les observations écartées
et antérieures au lancement peuvent apprendre des alias, sans consommer de mise.
Une fusion tardive ne supprime jamais rétroactivement une prise déjà sélectionnée.
Les diagnostics de fusion sont disponibles dans `selection_unique`.

Les plafonds se calculent sur toutes les prises observées, avant de filtrer la
période des matchs. Le résultat, le gain, la CLV et la date de règlement ne sont
jamais des critères de sélection. Les anciennes prises ne sont pas réinventées
quand une cote persiste : ces suivis portent sur les premières prises enregistrées.

## Rejeu et évaluation

Le rejeu du 7–13 octobre est exploratoire, car les règles sont proposées après
lecture de cet historique. Il remplace explicitement les dates de début par le
début de l'étude ; il n'est jamais ajouté au suivi prospectif. Les coupures de
règlement sont celles des comparateurs existants. Les tableaux et courbes sont
calculés dynamiquement depuis les prises, sans nouveau résultat préfabriqué.

Conserver ces règles pendant une période nouvelle avant toute révision ; suivre
volume, CLV et couverture, gains, drawdown et concentration par événement.
Aucune rentabilité future ni fréquence quotidienne n'est démontrée.
