// Journal réel (audit du 20/11/2026, priorité 12) : ce qui a vraiment été joué, en un geste depuis l'alerte Pushover.
// Chaque alerte porte quatre liens « #notifications?journal=<pari>&r=joue|refuse|plafonne|disparu&cote=<cote> »
// (cotes/alertes/pushover.py › liens_journal). La réponse est gardée sur cet appareil (localStorage), puis comparée
// au résultat du pari simulé (fiches) : bilan réel, cote obtenue, bookmaker qui limite.
// Fonctions seulement (pas de « const » au premier niveau) : le fichier est inséré au milieu du script de la page.
function journalLire() {
  try { const j = JSON.parse(localStorage.getItem('cv-journal-v1') || '{}'); return j && typeof j === 'object' ? j : {}; }
  catch { return {}; }
}
function journalEcrire(j) { try { localStorage.setItem('cv-journal-v1', JSON.stringify(j)); } catch {} }
function journalReponses() { return {joue: 'Joué', refuse: 'Refusé', plafonne: 'Plafonné', disparu: 'Disparu'}; }
// Lien d'une alerte : note la réponse, rend un message de confirmation (ou '' si l'ancre n'est pas une réponse).
function journalNoterDepuisAncre(hash = location.hash, maintenant = new Date()) {
  const brut = String(hash || '').replace(/^#/, ''), i = brut.indexOf('?');
  if (i < 0) return '';
  const q = new URLSearchParams(brut.slice(i + 1)), id = q.get('journal') || '', r = q.get('r') || '';
  if (!/^[a-z0-9]{1,40}$/i.test(id) || !(r in journalReponses())) return '';
  const cote = Number(q.get('cote'));
  const j = journalLire();
  j[id] = {r, cote: Number.isFinite(cote) && cote > 1 ? cote : null, le: maintenant.toISOString()};
  journalEcrire(j);
  return `Noté : ${journalReponses()[r]}.`;
}
// Bilan : réponses par type, gain réel des paris joués (cote obtenue, mise de la fiche), bookmakers qui limitent.
function journalBilan(j, fiches) {
  const parId = new Map(fiches.map(f => [f.id, f]));
  const comptes = {joue: 0, refuse: 0, plafonne: 0, disparu: 0};
  let mises = 0, gain = 0, regles = 0;
  const parBook = {};
  for (const [id, x] of Object.entries(j)) {
    if (!(x.r in comptes)) continue;
    comptes[x.r]++;
    const f = parId.get(id);
    const book = f && f.bookmaker || '—';
    const b = parBook[book] = parBook[book] || {reponses: 0, plafonne: 0};
    b.reponses++; if (x.r === 'plafonne') b.plafonne++;
    if (x.r !== 'joue' || !f || f.gain == null) continue;
    const mise = 10, cote = x.cote || f.cote;
    const part = {gagne: cote - 1, demi_gagne: (cote - 1) / 2, rembourse: 0, demi_perdu: -0.5, perdu: -1}[f.statut];
    if (part == null) continue;
    regles++; mises += mise; gain += mise * part;
  }
  const limites = Object.entries(parBook).filter(([, b]) => b.plafonne >= 3 && b.plafonne / b.reponses >= 0.3).map(([k]) => k);
  return {comptes, regles, gain: Math.round(gain * 100) / 100, roi: mises ? gain / mises : null, limites, parBook};
}
function rendreJournal(message = '') {
  const zone = document.getElementById('journal-reel'); if (!zone) return;
  const j = journalLire(), B = journalBilan(j, typeof fiches !== 'undefined' ? fiches : []), R = journalReponses();
  const total = Object.values(B.comptes).reduce((a, b) => a + b, 0);
  const pct = x => x == null ? '—' : (x > 0 ? '+' : '') + (100 * x).toFixed(1).replace('.', ',') + ' %';
  zone.innerHTML = `${message ? `<p class="aide" role="status">${e(message)}</p>` : ''}
<p class="aide">Touche « Joué », « Refusé », « Plafonné » ou « Disparu » sous chaque alerte Pushover : la réponse est gardée sur cet appareil.</p>
<div class="bu-kpis">${Object.entries(R).map(([k, nom]) => `<div><p>${e(nom)}</p><strong>${B.comptes[k]}</strong></div>`).join('')}</div>
<p>${total ? `Gain réel des paris joués et réglés (10 € par pari, cote obtenue) : <b class="${B.gain >= 0 ? 'pos' : 'neg'}">${B.gain >= 0 ? '+' : '−'}${Math.abs(B.gain).toFixed(2).replace('.', ',')} €</b> sur ${B.regles} réglé${B.regles > 1 ? 's' : ''} · ROI ${pct(B.roi)}`
    : 'Aucune réponse notée sur cet appareil.'}</p>
${B.limites.length ? `<p class="aide"><b>Limitation probable</b> : ${B.limites.map(e).join(', ')} (au moins 3 mises plafonnées, 30 % des réponses ou plus).</p>` : ''}
${total ? '<p><button type="button" class="btn secondaire" id="journal-effacer">Effacer le journal de cet appareil</button></p>' : ''}`;
  const effacer = document.getElementById('journal-effacer');
  if (effacer) effacer.onclick = () => { journalEcrire({}); rendreJournal('Journal effacé.'); };
}
// L'ouverture d'un onglet réécrit l'ancre (history.replaceState) : on lit celle d'arrivée (ANCRE_DEPART, notée au
// début du script de la page) puis l'URL donnée par chaque hashchange.
function initialiserJournal() {
  const depart = typeof ANCRE_DEPART === 'string' ? ANCRE_DEPART : location.hash;
  rendreJournal(journalNoterDepuisAncre(depart));
  window.addEventListener('hashchange', ev => {
    const url = String(ev.newURL || ''), i = url.indexOf('#');
    const m = journalNoterDepuisAncre(i < 0 ? '' : url.slice(i));
    if (m) rendreJournal(m);
  });
}
