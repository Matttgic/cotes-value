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
