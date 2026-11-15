# Convergence ≥ 2

Stratégie de vote, sans règle propre : un pari est pris quand **au moins deux familles** parmi les sept bases
(Claude, ChatGPT, Gemini, Jules, Eden, M3 ; Jules v1 et v2 comptent pour une seule famille) ont retenu la même
sélection. Code : `cotes/convergence.py` (`paris_convergence`), clé `convergence`.

- **Même prise** : même cote française, même prix et même instant de détection (UTC), même si les références
  diffèrent. Une sélection plus tardive ne réécrit pas le passé.
- **Une prise par sélection** : la première convergence l'emporte ; à instant égal, la référence la mieux classée
  (`simulation.REFERENCES`) puis l'identifiant du pari départagent.
- **Début du suivi** : `CONVERGENCE["debut"]` (14/10/2026, 23:00 UTC). Les prises sont figées à la décision
  (`cotes/decisions.py`).

Les variantes (`strategies_prudentes.VARIANTES`, dont « Convergence ≥ 3 hors M3 ») ne votent pas : elles ne changent ni
les votes ni la prise représentative.
