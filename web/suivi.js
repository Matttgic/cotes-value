// « Mes stratégies » : bilan des paris des stratégies cochées dans Notifications, depuis la date de chaque coche,
// et filtre de période du Bilan. Tout est calculé dans le navigateur à partir du catalogue des prises ;
// l'historique des coches reste sur cet appareil (localStorage).
const CLE_SUIVI = 'cv-suivi-strategies-v1', CLE_PERIODE = 'cv-periode-bilan-v1';
const REGLES_SUIVI = new Set(['gagne', 'perdu', 'rembourse', 'demi_gagne', 'demi_perdu']);

// {cle: [[debutMs, finMs|null], ...]} -> même forme, après une coche/décoche enregistrée.
function suiviSynchroniser(etat, cochees, maintenant, depuis) {
  const out = {};
  for (const [k, l] of Object.entries(etat || {})) out[k] = l.map(x => x.slice());
  const actives = new Set(cochees);
  for (const k of actives) {
    const l = out[k] ||= [];
    if (!l.length || l[l.length - 1][1] != null) l.push([Number.isFinite(depuis) ? depuis : maintenant, null]);
  }
  for (const [k, l] of Object.entries(out)) {
    const dernier = l[l.length - 1];
    if (!actives.has(k) && dernier && dernier[1] == null) dernier[1] = maintenant;
  }
  return out;
}
// La prise détectée à `t` compte pour la stratégie si elle l'était alors.
const suiviCompte = (intervalles, t) => (intervalles || []).some(([a, b]) => t >= a && (b == null || t < b));
const suiviNombre = x => typeof x === 'number' && Number.isFinite(x) ? x : null;

function suiviObjets(catalogue) {
  const champs = catalogue?.champs || [];
  return (catalogue?.lignes || []).map(l => Object.fromEntries(champs.map((c, i) => [c, l[i]])));
}
// Prises détectées dans la période. `etat` non nul : seulement celles des stratégies suivies à ce moment-là,
// avec la liste de ces stratégies (`suivies`). `unique` : une prise par pari, comme le Bilan (sans doublon de référence).
function suiviPrises(prises, {depuis, jusqua, etat, unique} = {}) {
  const out = [];
  for (const p of prises) {
    const t = Date.parse(p.detecte);
    if (!Number.isFinite(t) || (depuis != null && t < depuis) || (jusqua != null && t >= jusqua)) continue;
    if (unique && !p.unique_bilan) continue;
    if (etat) {
      const cles = [...(p.strategies || []), ...(p.regles || []), ...(p.convergence ? ['convergence'] : [])].filter(k => suiviCompte(etat[k], t));
      if (!cles.length) continue;
      out.push({...p, suivies: cles});
    } else out.push(p);
  }
  return out;
}
function suiviBilan(prises) {
  const b = {paris: prises.length, regles: 0, gagnes: 0, en_cours: 0, mises: 0, gains: 0};
  for (const p of prises) {
    if (!REGLES_SUIVI.has(p.statut)) {b.en_cours++; continue;}
    const mise = suiviNombre(p.mise) ?? 10;
    const g = suiviNombre(p.gain) ?? (p.statut === 'gagne' ? mise * (p.cote - 1) : p.statut === 'perdu' ? -mise : 0);
    b.regles++; b.mises += mise; b.gains += g;
    if (g > 0) b.gagnes++;
  }
  b.roi = b.mises ? b.gains / b.mises : null;
  return b;
}
// Bornes en ms depuis deux dates AAAA-MM-JJ (jour civil de Paris ; `jusqua` inclus).
function suiviBornes(depuis, jusqua) {
  const jour = (s, plus) => {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(s || '')) return null;
    const [a, m, j] = s.split('-').map(Number);
    let t = Date.UTC(a, m - 1, j + plus);
    for (let i = 0; i < 2; i++) {                       // recale sur minuit à Paris (heure d'été ou d'hiver)
      const p = new Intl.DateTimeFormat('en-GB', {timeZone: 'Europe/Paris', hourCycle: 'h23', hour: '2-digit', minute: '2-digit'}).formatToParts(new Date(t));
      const h = Number(p.find(x => x.type === 'hour').value), mn = Number(p.find(x => x.type === 'minute').value);
      t -= ((h + (h > 12 ? -24 : 0)) * 60 + mn) * 60000;
    }
    return t;
  };
  return {depuis: jour(depuis, 0), jusqua: jour(jusqua, 1)};
}
const suiviJourParis = (t = Date.now()) => new Intl.DateTimeFormat('en-CA', {timeZone: 'Europe/Paris'}).format(new Date(t));
const suiviLire = () => { try { return JSON.parse(lire(CLE_SUIVI) || '{}') || {}; } catch { return {}; } };
const suiviPeriode = () => { try { return JSON.parse(lire(CLE_PERIODE) || '{}') || {}; } catch { return {}; } };

// Appelées par Notifications (coche enregistrée, arrêt) ; `since` : début de l'abonnement connu du serveur.
function suiviEnregistrer(cochees, depuis) {
  const etat = suiviLire();
  ecrire(CLE_SUIVI, JSON.stringify(suiviSynchroniser(etat, cochees, Date.now(), depuis)));
}
function suiviAmorcer(cochees, since) {                  // appareil déjà abonné avant cette fonction : on part de l'abonnement
  if (Object.keys(suiviLire()).length || !cochees.length) return;
  const t = Date.parse(since);
  suiviEnregistrer(cochees, Number.isFinite(t) ? t : Date.now());
}

// --- affichage
const eur2 = x => x == null ? '—' : (x > 0 ? '+' : '') + x.toFixed(2).replace('.', ',') + ' €';
const nomStrategie = k => (D.notifications?.strategies || {})[k] || (D.strategies_badges || {})[k] || k;
let suiviFiltre = '', suiviLimite = 50;
let prisesCache = [null, []];
const prisesSuivi = () => prisesCache[0] === D.catalogue ? prisesCache[1] : (prisesCache = [D.catalogue, suiviObjets(D.catalogue)])[1];

function datesHtml() {
  const pr = suiviPeriode(), auj = suiviJourParis();
  return `<div class="filtres periode-bilan"><div class="champ"><label>Du</label><input type="date" data-p="depuis" value="${e(pr.depuis || '')}" max="${auj}"></div>
  <div class="champ"><label>Au</label><input type="date" data-p="jusqua" value="${e(pr.jusqua || '')}" max="${auj}"></div></div>`;
}
function lierDates(racine, rapides) {
  const maj = v => { ecrire(CLE_PERIODE, JSON.stringify(v)); rendreBilanUniques(); rendreMesStrategies(); };
  racine.querySelectorAll('input[data-p]').forEach(i => i.onchange = () => maj({...suiviPeriode(), [i.dataset.p]: i.value || ''}));
  if (rapides) racine.querySelectorAll('[data-rapide]').forEach(b => b.onclick = () => {
    const r = b.dataset.rapide;
    maj(r === 'tout' ? {} : {depuis: suiviJourParis(Date.now() - (r === 'aujourdhui' ? 0 : Number(r)) * 86400000), jusqua: suiviJourParis()});
  });
}
const bornesActuelles = () => { const p = suiviPeriode(); return suiviBornes(p.depuis, p.jusqua); };
const resumeHtml = b => `<div class="carte resume-suivi"><div class="l1"><span><b>${b.regles}</b> réglé${b.regles > 1 ? 's' : ''} · ${b.gagnes} gagné${b.gagnes > 1 ? 's' : ''}${b.regles ? ' (' + Math.round(100 * b.gagnes / b.regles) + ' %)' : ''}${b.en_cours ? ' · ' + b.en_cours + ' en cours' : ''}</span></div>
  <div class="l1"><span><b class="${signe(b.gains)}">${eur2(b.regles ? b.gains : null)}</b> <small class="roi ${signe(b.roi)}">ROI ${b.roi == null ? '—' : pctC(b.roi)}</small> <small>· 10 € par prise</small></span></div></div>`;
// Bilan « Paris uniques » : deux dates au choix en plus des périodes rapides.
function rendreDatesBilan() {
  const zone = document.getElementById('bu-dates');
  if (!zone) return;
  if (!zone.dataset.pret) { zone.innerHTML = datesHtml() + '<p class="aide">Dates de règlement des paris. Choisir des dates remplace la période rapide.</p>'; zone.dataset.pret = '1'; lierDates(zone, false); }
  else zone.querySelectorAll('input[data-p]').forEach(i => i.value = suiviPeriode()[i.dataset.p] || '');
}

// Mes stratégies actives.
function rendreMesStrategies() {
  const zone = document.getElementById('mes-strategies');
  if (!zone) return;
  const etat = suiviLire(), cles = Object.keys(etat);
  if (!zone.dataset.pret) {
    zone.innerHTML = '<div id="mes-periode">' + datesHtml() + `<div class="puces" aria-label="Périodes rapides"><button type="button" data-rapide="aujourdhui">Aujourd’hui</button><button type="button" data-rapide="7">7 jours</button><button type="button" data-rapide="30">30 jours</button><button type="button" data-rapide="tout">Tout</button></div><p class="aide">Dates de détection des paris.</p></div><div id="mes-contenu"></div>`;
    zone.dataset.pret = '1'; lierDates(document.getElementById('mes-periode'), true);
  }
  else document.querySelectorAll('#mes-periode input[data-p]').forEach(i => i.value = suiviPeriode()[i.dataset.p] || '');
  const sortie = document.getElementById('mes-contenu');
  if (!cles.length) {
    sortie.innerHTML = '<p class="vide">Aucune stratégie suivie. Coche tes stratégies dans <button type="button" class="btn secondaire" data-aller="notifications">Notifications</button> puis « Enregistrer mes choix » : leurs paris s’ajoutent ici à partir de ce moment.</p>';
    sortie.querySelector('[data-aller]').onclick = () => { ouvrir('notifications'); window.scrollTo(0, 0); };
    return;
  }
  if (suiviFiltre && !cles.includes(suiviFiltre)) suiviFiltre = '';
  const toutes = suiviPrises(prisesSuivi(), {...bornesActuelles(), etat});
  const nb = Object.fromEntries(cles.map(k => [k, toutes.filter(p => p.suivies.includes(k)).length]));
  const vues = suiviFiltre ? toutes.filter(p => p.suivies.includes(suiviFiltre)) : toutes;
  const maintenant = Date.now();
  const lignesSuivi = cles.map(k => {
    const l = etat[k], d = l[l.length - 1], actif = d && d[1] == null;
    const debut = new Date(l[0][0]).toLocaleString('fr-FR', {timeZone: 'Europe/Paris', day: 'numeric', month: 'numeric', hour: '2-digit', minute: '2-digit'});
    return `<div class="sante-ligne"><div><b>${e(nomStrategie(k))}</b><small>Suivie depuis le ${debut}${actif ? '' : ' · arrêtée le ' + new Date(d[1]).toLocaleString('fr-FR', {timeZone: 'Europe/Paris', day: 'numeric', month: 'numeric', hour: '2-digit', minute: '2-digit'})}</small></div>
      <span class="sante-mot sante-mot-${actif ? 'ok' : 'alerte'}">${actif ? '✓ Active' : 'Arrêtée'}</span></div>`;
  }).join('');
  const puce = (k, nom, n) => `<button type="button" data-suivi="${e(k)}" class="${suiviFiltre === k ? 'actif' : ''}">${e(nom)} <small>${n}</small></button>`;
  sortie.innerHTML = `<div class="puces" aria-label="Filtrer par stratégie">${puce('', 'Toutes', toutes.length)}${cles.map(k => puce(k, nomStrategie(k), nb[k])).join('')}</div>`
    + resumeHtml(suiviBilan(vues))
    + `<div id="mes-liste">${vues.slice(0, suiviLimite).map(carteSuivi).join('') || '<p class="vide">Aucun pari sur cette période.</p>'}</div>`
    + (vues.length > suiviLimite ? '<p><button type="button" class="btn secondaire" id="mes-plus">Voir plus</button></p>' : '')
    + `<details class="mode-emploi"><summary>Stratégies suivies</summary><div class="carte">${lignesSuivi}</div>
       <p class="aide">Seuls comptent les paris détectés pendant que la stratégie était cochée. Une décoche enregistrée arrête l’ajout de ses nouveaux paris, l’historique déjà suivi reste. Ce suivi est enregistré sur cet appareil.</p></details>`;
  sortie.querySelectorAll('[data-suivi]').forEach(b => b.onclick = () => { suiviFiltre = b.dataset.suivi; suiviLimite = 50; rendreMesStrategies(); });
  const plus = document.getElementById('mes-plus');
  if (plus) plus.onclick = () => { suiviLimite += 50; rendreMesStrategies(); };
}
const carteSuivi = p => `<article class="carte"><div class="l1"><span class="match">${e(p.domicile)} – ${e(p.exterieur)}</span></div>
  <div class="l2">${e(p.pari)}</div>
  <div class="l3"><span><b>${e(p.bookmaker)} ${cote(p.cote)}</b></span><span>${new Date(p.detecte).toLocaleString('fr-FR', {timeZone: 'Europe/Paris', day: 'numeric', month: 'numeric', hour: '2-digit', minute: '2-digit'})}</span></div>
  <div class="l4"><span class="badge ${e(p.statut)}">${e(STATUTS[p.statut] || p.statut)}</span>${p.suivies.map(k => `<span class="badge">${e(nomStrategie(k))}</span>`).join('')}
  ${suiviNombre(p.gain) != null ? `<b class="${signe(p.gain)}">${eur2(p.gain)}</b>` : ''}</div></article>`;
