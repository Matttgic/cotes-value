# Consignes pour Claude

- **Fusion** : ne demande jamais « je fusionne ? ». Quand les tests en ligne sont verts et que la PR est sans
  conflit, fusionne-la toi-même (méthode « merge »), puis dis-le. Si les tests échouent, corrige d'abord.
- Réponds en français. N'invente jamais de résultats, de cotes ni d'URL.
- **Coût** : à la fin de chaque tâche, une seule phrase courte, sans détail : le coût de la tâche et le total de la
  session, mesurés par `get_session` (serveur claude-code-remote, sans `session_id` ; `external_metadata.usage.cost_usd`,
  relevé au début et à la fin). Jamais d'estimation inventée : sans mesure, le dire dans cette phrase.
