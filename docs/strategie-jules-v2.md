# JULES EDGE v2 reconstruite

Reconstruction de l'intention de Jules, à partir de son commit `b3e8e8c`.
Le [protocole](protocole-jules-v2.md) et le sélecteur ont été enregistrés avant
le recalcul ci-dessous. Aucun seuil n'a été choisi pour améliorer ce bilan.
La v1 corrigée et les autres stratégies restent inchangées.

## Idée et décisions prises

Chercher une cote française supérieure à la cote juste donnée par **Pinnacle,
Betfair ou Polymarket**, avec des cotes modérées et une exposition limitée.
Une référence suffit : il ne s'agit pas d'un consensus de trois probabilités.
Les références utilisent la cote juste et les ajustements déjà calculés par le moteur.

Les seuils numériques de Jules sont conservés : cotes **1,30–2,80**, edge
**2,5–12 %**, détection **15 minutes à 18 heures** avant le match, référence
de **5 minutes maximum**, correspondance >= **0,85**, marché contrôlé conforme.
Winamax, Betclic, Unibet, PMU et sports déjà couverts par le moteur.
Marchés 1N2, vainqueur, total et handicap sur le match ou le temps réglementaire
explicitement identifié. Tennis et volley : vainqueur du match seulement.
Les quarts de ligne sont exclus. Mise fixe fictive de **10 €**, au plus **8/jour**
selon le calendrier de Paris. Les femmes et les catégories d'âge ne sont pas
exclues arbitrairement : elles doivent être identifiées distinctement.

### Correction de l'identité et du risque

La version livrée par Jules confondait identifiant de référence et événement
physique : un match Pinnacle et le même match Polymarket pouvaient être joués
deux fois. Le nouveau moteur relie progressivement :

- les identifiants de référence, séparés par fournisseur ;
- les identifiants des bookmakers ;
- les noms normalisés des équipes, ceux de la référence et la même heure UTC,
  en conservant les marqueurs féminin/jeunes/réserves.

Un lien conforme reste mémorisé même sur une cote refusée. Chaque lien n'est
utilisé qu'à partir de sa détection, sans préconstruire le graphe avec le futur.
La première opportunité admissible est prise ; un meilleur prix plus tard ne la
remplace pas. En simultané : edge décroissant, cote décroissante, puis ordre stable.

Cela vise une mise par **événement identifiable au moment de la décision**.
Des alias inconnus sans lien commun peuvent encore échapper au rapprochement.
Si un lien tardif révèle deux mises déjà prises, le moteur le signale sans
réécrire l'historique. **Aucune fusion tardive sur le relevé étudié.**

## Résultats recalculés sur le même relevé

Source : branche `donnees`, commit
`56bed648894f383f04fb42f677ee9223d29c2abe`, **9 307 lignes**, archives incluses.
Matchs du **7 au 13 octobre 2026**, relevé du **14/10 à 12:09:28 Paris**.
Les sélections prennent aussi en compte les places journalières consommées par
des matchs hors fenêtre. Les règlements inconnus à chaque coupure restent en attente.

| Stratégie | Sélections | Réglés | Mises réglées | Gain net | ROI | CLV exploitable | Baisse max. observée |
|---|---:|---:|---:|---:|---:|---:|---:|
| Jules v1 | 20 | 18 | 180 € | +20,60 € | +11,44 % | +0,40 % | 20,00 € |
| **Jules v2 reconstruite** | **34** | **30** | **300 €** | **+38,30 €** | **+12,77 %** | **+2,50 %** | **30,20 €** |
| Claude | 162 | 159 | 1 590 € | +214,70 € | +13,50 % | +3,33 % | 98,60 € |
| ChatGPT v1 | 14 | 13 | 130 € | −16,30 € | −12,54 % | −3,60 % | 30,00 € |
| Gemini Argon v1 | 29 | 29 | 290 € | +22,00 € | +7,59 % | +3,59 % | 46,00 € |
| M3 | 83 | 69 | 690 € | +310,70 € | +45,03 % | −0,40 % | 31,30 € |

La v2 compte **18 gagnés, 12 perdus et 4 en attente** ; réussite sur réglés :
**60 %**. CLV exploitable : **24/30**, soit 80 %. Le contrôle de clôture existant
écarte les CLV absentes ou mesurées hors de la fenêtre valide avant match.

La v2 livrée non corrigée donne, sur ces mêmes données, 35 sélections,
32 réglées et +71,10 €. Ce chiffre comprend des répétitions de rencontres ;
il ne décrit pas la règle « une mise par match ». Après déduplication, les
places libérées peuvent aussi changer les sélections suivantes sous le plafond.

### Périodes et fragilité

| Période | Réglés | En attente | Gain | ROI |
|---|---:|---:|---:|---:|
| Construction 7–10 oct. | 13 | 0 | +23,20 € | +17,85 % |
| Validation 11–12 oct. | 13 | 1 | −1,90 € | −1,46 % |
| Test 13 oct. | 4 | 3 | +17,00 € | +42,50 % |

Ces noms désignent des tranches descriptives : la stratégie est construite
après ces dates. Le test n'est donc pas une validation indépendante.
L'ensemble inclut les règlements tardifs connus au relevé ; il n'est pas la
somme des évaluations intermédiaires effectuées à leurs coupures respectives.

- Retirer le meilleur pari laisse **+20,30 €** de gain.
- Dégrader toutes les cotes prises de 1 % donne un ROI de **+11,64 %**.
- L'intervalle descriptif à 95 % du ROI, par rééchantillonnage de journées,
  est **[−18,00 % ; +35,84 %]**, sur seulement six jours avec des règlements.
- Une nouvelle mise au maximum de huit par jour représente **80 € fictifs/jour**.
  La baisse observée n'est pas une limite garantie pour l'avenir.

**Ce relevé ne montre pas une supériorité sur Claude** : le ROI est légèrement
inférieur, sur beaucoup moins de paris. Le profit de M3 résulte d'une optimisation
après observation du passé ; son intervalle descriptif ne corrige pas ce biais.
La CLV positive et le gain de Jules sont intéressants, mais trente résultats
et quelques journées ne démontrent pas une rentabilité durable.

## Reproduction et lancement

[Rapport JSON](strategie-jules-v2.json) : métriques par période, identifiants des
sélections, diagnostic, commit et empreinte des données, empreintes du sélecteur,
du protocole et du code brut de Jules. Aucun résultat n'est inventé.

```bash
git fetch origin 56bed648894f383f04fb42f677ee9223d29c2abe b3e8e8c927b51747170e21892815f0903653a52c
git worktree add --detach ../donnees-jules-v2 56bed648894f383f04fb42f677ee9223d29c2abe
python scripts/verifier_strategie_jules_v2.py --donnees ../donnees-jules-v2 --sortie rapport-jules-v2.json
```

**Suivi après publication : 15/10/2026 à 00:30 Paris**, sans reprise des gains
historiques. Visible dans **Bilan → JULES EDGE v2** et **Stratégies → JULES EDGE V2**,
avec courbe et liens vers les prix exacts des paris. La v1 est conservée séparément.
Les données avant ce lancement servent au rejeu et aux correspondances déjà
connues ; elles ne créent pas de mises dans le suivi. Aucun pari réel n'est placé.
