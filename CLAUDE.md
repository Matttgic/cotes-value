# Consignes pour Claude

- **Fusion** : ne demande jamais « je fusionne ? ». Quand les tests en ligne sont verts et que la PR est sans
  conflit, fusionne-la toi-même (méthode « merge »), puis dis-le. Si les tests échouent, corrige d'abord.
- Réponds en français. N'invente jamais de résultats, de cotes ni d'URL.
- **Coût** : à la fin de chaque tâche, une seule phrase courte, sans détail : le coût de la tâche et le total de la
  session, mesurés par `get_session` (serveur claude-code-remote, sans `session_id` ; `external_metadata.usage.cost_usd`,
  relevé au début et à la fin). Jamais d'estimation inventée : sans mesure, le dire dans cette phrase.
- **Économie** : lis seulement les fichiers utiles ; filtre les journaux et sorties de tests (`grep`, `tail`) au lieu de
  tout afficher. Termine chaque réponse par une parenthèse : action conseillée (`/clear`, `/compact`, `/effort`,
  modèle, passation) ou « rien à changer ».

# Compact instructions

Garde uniquement : l'objectif en cours, les fichiers modifiés, les décisions validées, les erreurs de tests non
résolues et la prochaine étape. Supprime les sorties complètes, les essais abandonnés et les explications.

# Erreurs à ne plus faire

- Depuis une session cloud Claude : imiter l'empreinte TLS d'un navigateur (curl_cffi…), sonder les API internes
  des bookmakers ou exécuter le JS de leurs pages est refusé : ne pas réessayer. Winamax et Betclic répondent 403
  depuis GitHub ; Betclic se lit par son API publique gRPC-web.
- Une source qui répond 403/429 se met en pause (`cotes/pauses_sources.py` : 30 min, doublée jusqu'à 6 h) : ne
  jamais insister (Unibet relu 1 703 cycles en 403 en 7 jours ; NetBet a fini par bloquer Autonome).
- Écart > 30 % = erreur de référence ou de marché, pas une value (77 paris : 1 gagné, −540 €) ; Polymarket tennis
  figé à 0,49/0,50 = forfait réglé 50/50. Les deux sont « référence suspecte » : jamais alertés.
- Score exact et mi-temps/fin Pinnacle : liste d'issues incomplète, marge mal retirée (399 paris score exact :
  3 gagnés pour 10,7 attendus). Jamais pariables.
- Au-delà d'une cote de 5, la cote juste Pinnacle surestime la probabilité de gain d'environ 1,8 fois (hors score
  exact et mi-temps/fin : 18 gagnés pour 32,3 attendus). Ne pas lire un écart sur longue cote comme une value.
- Appariement : « Paris FC » ≠ « Paris SG », « Inter » ≠ « Inter Miami », « Arsenal W » ≠ « Arsenal »,
  « Venus » ≠ « Serena Williams » : garder les pièges de `tests/test_justesse.py`. Ne pas changer
  `ressemblance`, `normaliser` ni `avec_marqueurs_ligue` à la légère : le règlement et les stratégies figées s'en
  servent (les règles strictes vivent dans `ressemblance_appariement`).
- Tout changement de détection incrémente `VERSION` (`cotes/__init__.py`), noté dans la trace de chaque pari.
- Code copié d'un autre dépôt du propriétaire (Autonome, cotes-boostees) : en-tête « Copié de <dépôt>/<chemin>
  @ <commit> le <date> — écarts : … », sinon les copies divergent en silence (cas de `boosts/marge.py`).
- Intervalles de confiance et p-valeurs : par match (grappe), jamais par pari ; protocole dans `docs/PROTOCOLE.md`.
