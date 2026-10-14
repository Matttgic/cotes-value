# Stratégie JULES EDGE v1

## Description de la stratégie

**JULES EDGE v1** est une stratégie quantitative de value betting indépendante, élaborée pour maximiser la rentabilité nette à long terme tout en maîtrisant la variance et le risque de drawdown sur les bookmakers français agréés ANJ (Winamax, Betclic, Unibet, PMU).

### Principes Clés

1. **Référence sans marge (Pinnacle)** :
   La probabilité implicite est calculée en supprimant la marge du bookmaker de référence Pinnacle (Fair Odds).
2. **Plage de cotes maîtrisée (1,30 - 2,50)** :
   Sélection d'opportunités à taux de réussite élevé (~65 %), réduisant les séries de défaites longues et le risque de baisse brutale du capital (drawdown).
3. **Marge de valeur positive (EV Edge +3 % à +12 %)** :
   Exclusion des opportunités marginales (< 3 %) sujettes au bruit et des erreurs de cotation aberrantes (> 12 %).
4. **Fraîcheur & Fenêtre temporelle** :
   - Prise de pari effectuée entre **15 minutes et 12 heures** avant le début de l'événement.
   - Fraîcheur de la référence Pinnacle **$\le$ 5 minutes** au moment de la détection.
5. **Gestion stricte des risques & Déduplication** :
   - **1 seul pari maximum par match** (tous bookmakers et marchés confondus).
   - **Plafond de 6 paris maximum par jour** (fuseau horaire Europe/Paris).

---

## Protocole de Backtest & Validation Walk-Forward

Afin de garantir la robustesse statistique et prévenir tout risque de surajustement (overfitting) ou de fuite d'information future (data leakage) :

- **Échantillon In-Sample (Entraînement / Calibrage)** : 05 octobre 2026 – 10 octobre 2026.
- **Échantillon Out-Of-Sample (Validation Hors Échantillon / Walk-Forward)** : 11 octobre 2026 – 14 octobre 2026.
- **Hypothèses de simulation** : Mise fixe de 1 unité (10 €) par pari réglé. Aucune information future (CLV finale ou résultat) n'est utilisée lors de la décision de prise de pari.

---

## Résultats Globaux du Backtest

- **Paris totaux réglés** : 256
- **Gagnés / Perdus / Annulés** : 166 Gagnés / 89 Perdus / 1 Annulé
- **Taux de réussite** : 65,1 %
- **Cote moyenne** : 1,84
- **Profit net** : +49,9 Unités (+499,00 € pour une mise fixe de 10 €)
- **ROI net** : +19,5 %
- **CLV moyen (Closing Line Value)** : +4,9 %

---

## Motifs de Refus & Conditions de Sélection

Chaque opportunité détectée est soumise au filtre `motif_refus_jules()`. Un pari est rejeté si :

- La référence n'est pas Pinnacle sans marge.
- Le bookmaker n'est pas parmi Winamax, Betclic, Unibet, PMU.
- La cote est hors de l'intervalle [1,30 ; 2,50].
- L'écart d'EV est hors de l'intervalle [+3,0 % ; +12,0 %].
- Le délai avant le match n'est pas compris entre 15 min et 12 h.
- La référence date de plus de 5 minutes.
- Le score de ressemblance des équipes est inférieur à 0.85 ou la conformité est insuffisante.
- Un pari a déjà été sélectionné pour ce match ou le plafond journalier de 6 paris est atteint.
