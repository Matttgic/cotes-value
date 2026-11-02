# Consignes pour Claude

- **Fusion** : ne demande jamais « je fusionne ? ». Quand les tests en ligne sont verts et que la PR est sans
  conflit, fusionne-la toi-même (méthode « merge »), puis dis-le. Si les tests échouent, corrige d'abord.
- Réponds en français. N'invente jamais de résultats, de cotes ni d'URL.
- **Coût** : à la fin de chaque tâche, indique le coût d'utilisation mesuré. Appelle `get_session` (serveur
  claude-code-remote, sans `session_id`) et rapporte `external_metadata.usage` : `cost_usd` cumulé de la session,
  l'écart depuis le début de la tâche (relève la valeur en commençant), et les jetons (sortie, cache). Jamais
  d'estimation inventée : si aucune mesure n'est disponible, dis-le.
