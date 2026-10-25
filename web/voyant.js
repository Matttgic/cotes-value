// Voyant Pushover, en bas de chaque page : confirme que les stratégies cochées sur le site sont bien celles que le job
// de collecte notifie. Compare le choix enregistré (lu en direct) au dernier cycle du journal des alertes.
const VOYANT_AGE_MAX_MIN = 20;       // un cycle dure ~5 min : au-delà, la collecte est en retard
function etatVoyant(cycles, choix, maintenant) {
  const liste = Array.isArray(cycles) ? cycles.filter(c => c && c.pushover) : [];
  const dernier = liste[liste.length - 1];
  if (!dernier) return {niveau: 'attention', texte: 'Pushover : aucun relevé du serveur pour le moment.'};
  const p = dernier.pushover, t = Date.parse(dernier.prepare_le);
  const age = Number.isFinite(t) ? Math.round((maintenant - t) / 60000) : null;
  const heure = Number.isFinite(t) ? new Date(t).toLocaleTimeString('fr-FR', {timeZone: 'Europe/Paris', hour: '2-digit', minute: '2-digit'}) : '?';
  const nombre = x => Array.isArray(x) ? x.length : (Number.isFinite(x) ? x : 0);
  const envoyees = liste.reduce((n, c) => n + nombre(c.pushover.envoyees), 0);
  const echecs = nombre(p.echecs), erreurs = Array.isArray(p.erreurs) ? p.erreurs : [];
  if (!p.actif) return {niveau: 'erreur', texte: 'Pushover inactif : clés absentes ou aucune stratégie cochée. Rien n’est envoyé.'};
  if (echecs || erreurs.length) return {niveau: 'erreur', texte: `Pushover : ${echecs || erreurs.length} échec d’envoi au dernier cycle (${heure}).${erreurs.length ? ' ' + erreurs[0] : ''}`};
  if (age !== null && age > VOYANT_AGE_MAX_MIN) return {niveau: 'attention', texte: `Pushover : dernier cycle il y a ${age} min (${heure}), la collecte est en retard.`};
  const suivies = nombre(p.strategies);
  const coches = choix && Array.isArray(choix.strategies) ? choix.strategies.length : null;
  const detail = `dernier cycle ${heure} · ${envoyees} alerte${envoyees > 1 ? 's' : ''} envoyée${envoyees > 1 ? 's' : ''} sur les ${liste.length} derniers cycles`;
  if (coches !== null && coches !== suivies)
    return {niveau: 'attention', texte: `Pushover : tu as coché ${coches} stratégie${coches > 1 ? 's' : ''}, le serveur en suit ${suivies}. À jour au prochain cycle (${detail}).`};
  if (p.source && p.source !== 'site')
    return {niveau: 'attention', texte: `Pushover : les ${suivies} stratégies viennent de la variable du dépôt, pas de tes cases du site (${detail}).`};
  return {niveau: 'ok', texte: `Pushover actif : ${suivies} stratégie${suivies > 1 ? 's' : ''} cochée${suivies > 1 ? 's' : ''} notifiée${suivies > 1 ? 's' : ''} (${detail}).`};
}
async function afficherVoyant() {
  const zone = document.getElementById('voyant-pushover');
  if (!zone) return;
  let choix = null;
  try {
    const r = await fetch(D.notifications.api + '/pushover-lire', {method: 'POST', cache: 'no-store', credentials: 'omit',
      referrerPolicy: 'no-referrer', headers: {'Content-Type': 'application/json'}, body: '{}', signal: AbortSignal.timeout(10000)});
    if (r.ok) { const d = await r.json(); if (d && d.defini) choix = d; }
  } catch {}
  const v = etatVoyant(D.diagnostic_alertes, choix, Date.now());
  const noms = choix ? choix.strategies.map(k => (D.notifications.strategies || {})[k] || k) : [];
  zone.className = 'voyant voyant-' + v.niveau;
  zone.innerHTML = `<span class="voyant-point" aria-hidden="true"></span><span class="voyant-texte">${e(v.texte)}${noms.length ? `<small>${e(noms.join(' · '))}</small>` : ''}</span>`;
}
afficherVoyant();
document.addEventListener('visibilitychange', () => { if (!document.hidden) afficherVoyant(); });
