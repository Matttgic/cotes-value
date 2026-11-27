# Audit du code cœur : règlement, comparaison, simulation

Fait le 26/11/2026 sur la branche `donnees` (cycle du 26/11 à 23:05 UTC) : 7 279 paris (3 766 dans `paris.json`,
3 513 dans `archives/paris-2026-10.json.gz`), dont 7 226 réglés. Tests : `tests/test_audit_26_11_code.py`.

## Verdict

1. **Le règlement est juste.** 6 903 paris réglés rejoués avec le code actuel, à partir des scores gardés dans leur
   preuve : 3 désaccords, les 3 « vainqueur » de hockey déjà listés dans `docs/audit-bilans.md`. Aucun gain faux.
2. **Un bug corrigé : le volley « points du 1er set » ne se réglait jamais tout seul.** 3 paris depuis le 22/11
   (2 « à régler », 1 en cours). Les 2 en attente seraient gagnés : +16,40 € à 10 €.
3. **Aucune incohérence de données** : ni cote juste ≤ 1, ni CLV ou écart mal calculés, ni pari réglé avant son
   coup d'envoi, ni date hors UTC.
4. **À décider : les matchs reportés.** 105 paris réglés après un report d'au moins 24 h (−220,5 €). La règle des
   bookmakers n'est pas écrite dans `docs/reglements.md`.

## Bug corrigé

| Bug | Exemple réel | Effet | Correction |
|---|---|---|---|
| Volley, handicap en points d'un set (`POINTS_HANDICAP`, ajouté le 22/11) : le consensus jetait les points par set (il comparait leur somme au score en sets), et le règlement ignorait le préfixe `POINTS_`. Même une saisie avec les sets ne réglait rien | `19fc8e2c46bb24be`, PMU, Onikisubat – Ziraat Bankasi 24/11 : Flashscore 0-3 (19-25, 20-25, 16-25), « score validé, détail manquant » | 3 paris ; 2 gagnés en attente (+7,40 €, +9,00 €) | `resultats._periodes_coherentes` : au volley, les sets gagnés doivent se déduire des points. `reglement.scores_par_periode` : `SET1`… et `POINTS`. `reglement._regler` : préfixe `POINTS_` |
| Libellé « POINTS_HANDICAP EXT 4.5 » : la ligne est celle du domicile, l'extérieur est donc à −4,5 | même pari | Affichage | `comparaison.libelle_pari` : « Ziraat Bankasi Ankara -4,5 points (1er set) » |

Le handicap du match reste en sets. Un détail des points qui ne redonne pas le score en sets n'est pas utilisé.

## Contrôles sans anomalie

| Contrôle | Résultat |
|---|---|
| Gain = mise × (cote − 1), −mise ou 0 | 0 écart sur 7 226 |
| Scores par période recalculés depuis score + périodes enregistrés | 0 statut changé (37 paris de handball et rugby gagneraient MT1/MT2, sans effet) |
| Lignes en quart (±0,25, ±0,75) | 0 pari ; code vérifié par les tests existants |
| Lignes entières (push) | 109 paris, 30 remboursés, tous conformes au rejeu |
| CLV au-delà de ±50 % | 116 paris, dont 66 à cote > 5. Cas vérifié : Grenade – Saint-Kitts 13/11, Pinnacle passe de 5,15 à 14,6 avant le coup d'envoi (20:00), mouvement réel |
| Doublons même match, bookmaker, sélection | 573 groupes, 788 paris en plus : tous d'une autre référence (un pari par référence, voulu) |
| Kelly, mise négative, bankroll nulle | `mises.py` et `simulation.mise_conseillee` rendent 0 ; les méthodes évolutives s'arrêtent à solde nul |

## Paris encore à régler à la main

`resultats_a_saisir.json` du 26/11 à 22:46 : 26 matchs, 38 paris.

| Raison | Matchs | Paris | Pourquoi |
|---|---|---|---|
| Aucune source | 21 | 27 | Ligues absentes des sources gratuites : volley (7), snooker (6), handball (5), basket (3), MMA (2), tennis (2), football (2) |
| Pas assez de sources | 2 | 8 | Béthune – Nancy (7 paris) : LiveScore seul, rapproché par une seule équipe ; un secours seul ne règle pas (voulu) |
| Score validé, détail manquant | 3 | 3 | 2 volley : **corrigé**. 1 NBA « avance ou gagne de 18 points » : indécidable sans le déroulé |

Aucun autre type fréquent ne peut être réglé automatiquement sans risque.

## Recommandations non faites

- **Reports.** 210 paris ont été reportés ; 105 réglés après au moins 24 h de report (−220,5 €), 14 après 48 h.
  Le code attend jusqu'à 7 jours (`resultats.REPORT_MAX_J`). Les règles de report des bookmakers (remboursement
  au-delà d'un délai ?) n'ont pas été relues : à vérifier avant tout changement.
  **Décision du 27/11 : rien de changé.** Recherche faite : aucune page officielle de Winamax, Betclic ou Unibet
  trouvée ; seuls des sites tiers parlent d'un délai de 48 h (96 h au tennis chez Unibet), et se contredisent sur le
  report annoncé avant le match. Changer le règlement sur ces seules sources fausserait le bilan autant que le garder.
  À reprendre avec le règlement officiel de chaque bookmaker (rubrique « Règlement » de chaque site, homologué par
  l'ANJ) : un délai par bookmaker dans `resultats.REPORT_MAX_J`, et les 14 paris réglés après 48 h à revoir.
- **Hockey, 3 « vainqueur » remboursés à tort** (`docs/audit-bilans.md`) : paris d'octobre, déjà archivés
  (`archives/paris-2026-10.json.gz`), effet ±0,08 point sur le ROI. **Décision du 27/11 : non corrigés.** Recherche
  faite : Grizzlys Wolfsbourg – Krefeld Pinguine du 15/10 donné 2-1 aux tirs au but par une seule source (sportschau.de),
  ce qui ferait perdre le pari sur Krefeld (`b603d0cd9c7293e8`, −10 €) ; Colorado Eagles – Abbotsford Canucks du
  10/10 introuvable. Le règlement exige plusieurs sources : à corriger dans l'archive seulement si un second score
  confirme.
