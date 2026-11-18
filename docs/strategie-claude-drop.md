# Claude · Drop Pinnacle

Stratégie « dropping odds » conçue par Claude le 18/11/2026, suivie dès le **18/11/2026 à 06 h (Paris)**, figée au
lancement (`cotes/strategie_claude_drop.py`, clé `claude_drop`, version 1). Inscrite au protocole de validation le
même jour (`cotes/protocole_registre.json`, 680 paris mesurés à atteindre).

## Idée

Quand la cote de Pinnacle chute sur une issue, le marché sharp a reçu de l'argent informé. Les bookmakers français
suivent avec retard : pendant ce délai, leur cote est trop haute. Les autres stratégies se déclenchent sur l'écart à
la cote juste ; celle-ci exige en plus que l'écart vienne d'une **chute de Pinnacle**.

La chute est le mouvement déjà mesuré à chaque prise par `cotes/mouvement.py` (`mouvement_pinnacle`) : probabilité
juste de Pinnacle comparée à son ancre, lue 10 à 60 minutes plus tôt. +3 % de probabilité juste correspond à une cote
juste qui baisse d'environ 3 %.

## Règle

- Référence Pinnacle seule.
- Probabilité juste de Pinnacle en hausse d'au moins 3 % sur 10 à 60 minutes (cote en chute).
- Cote française 1,40–4,00, écart 2–10 %.
- Ni score exact ni mi-temps/fin, équipes non inversées, match pas commencé.
- Tous les bookmakers sauf OlyBet.
- Une mise fictive de 10 € par cote française : la première détection qui passe la règle. Aucun plafond.

La sélection ne lit jamais statut, gain, CLV ni cote de clôture. Pas de rejeu : seul le suivi depuis le lancement
compte.

## Origine

[duree-values.md](duree-values.md), § 3 (11/11/2026) : les values où la référence a bougé sans le bookmaker
(311 paris réglés) avaient un ROI de +6,9 % et une CLV de +3,2 %, contre −1,2 % de CLV quand le bookmaker venait de
monter sa cote. Douze jours de données : une tendance, pas une preuve. Les seuils (3 %, 2–10 %, 1,40–4,00) ont été
posés à la main avant le suivi, sans les régler sur ces chiffres.

## Limites

- **Retard de Pinnacle** : la lecture passe par un cache Cloudflare d'environ 15 minutes
  ([pinnacle-secours.md](pinnacle-secours.md)). La chute est vue de 0 à 15 minutes après qu'elle a eu lieu. D'après
  duree-values.md, 93 % des values PMU tiennent encore 15 minutes, 60 % seulement chez Betclic : le bilan par
  bookmaker dira où la stratégie tient.
- **Fenêtre de mesure** : le mouvement porte sur 10 à 60 minutes (ancre renouvelée chaque heure). Une chute plus
  ancienne n'est pas vue.
- **Bookmaker stable** : l'étude d'origine distinguait aussi les cas où le bookmaker n'avait pas bougé depuis une
  heure. Cette mesure n'est pas enregistrée à la prise : elle n'est pas dans la règle.
- Aucun avantage n'est démontré. Seul le protocole de validation (docs/protocole.md) permettra de conclure.

## Variante z-score (Claude · Drop z-score, suivie dès le 18/11/2026 à 8 h, heure de Paris)

Idée reprise du dépôt public [kaykyif/pinnacle-odds-radar](https://github.com/kaykyif/pinnacle-odds-radar)
(`src/volatility.py`, `src/episodes.py`) : une chute de 3 % est banale sur un marché nerveux et rare sur un marché
calme.

- **Mesure** (`cotes/mouvement.py`) : pour chaque marché (type + période), moyenne et variance des mouvements non nuls
  de toutes les cotes Pinnacle suivies, pondérées sur environ 5 000 mesures. `mouvement_z` = (mouvement − moyenne) /
  écart-type, avec les statistiques d'avant le cycle. Pas de z sous 200 mesures. Les statistiques vivent dans le cache
  (`reprise/stats_mouvement.json.gz`).
- **Règle** : celle de Drop Pinnacle, plus `mouvement_z` ≥ 2. Même mise (10 € de base, puis le mode du menu « Mise des
  bilans »), une mise par cote française.
- **Épisode** : `mouvement_lignes` compte les lignes alternatives du même match, marché, période et issue qui ont chuté
  d'au moins 3 % au même cycle. Enregistré dans chaque pari, **hors règle** : à étudier dans les bilans avant d'en
  faire une variante.
- **Comparaison** : Drop z-score est un sous-ensemble de Drop Pinnacle. Si le z apporte quelque chose, son ROI et sa CLV
  doivent dépasser ceux de Drop sur la même période.
