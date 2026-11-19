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
// « Repartir de zéro » : seules les stratégies encore cochées restent, suivies à partir de `maintenant`.
// Avec `cle` : cette seule stratégie recommence (si elle est encore cochée) ; les autres gardent leur historique.
function suiviRepartir(etat, maintenant, cle) {
  const out = {};
  for (const [k, l] of Object.entries(etat || {})) {
    const d = l[l.length - 1], active = d && d[1] == null;
    if (cle != null && !(k === cle && active)) out[k] = l.map(x => x.slice());
    else if (active) out[k] = [[maintenant, null]];
  }
  return out;
}
// « Retirer » : efface une stratégie arrêtée et son historique (une stratégie encore cochée reste).
function suiviRetirer(etat, cle) {
  const out = {...(etat || {})}, l = out[cle], d = l && l[l.length - 1];
  if (d && d[1] != null) delete out[cle];
  return out;
}
// La prise détectée à `t` compte pour la stratégie si elle l'était alors.
const suiviCompte = (intervalles, t) => (intervalles || []).some(([a, b]) => t >= a && (b == null || t < b));
const suiviNombre = x => typeof x === 'number' && Number.isFinite(x) ? x : null;
// Bases du Bilan cochées dans Notifications (cotes/notifications.py, selections_bases) : déduites de la référence et du
// drapeau « pari unique » de chaque prise, sans colonne de plus dans le catalogue.
const suiviBases = p => [...(p.reference ? ['base_' + String(p.reference).toLowerCase()] : []), ...(p.unique_bilan ? ['base_uniques'] : [])];

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
      const cles = [...(p.strategies || []), ...(p.regles || []), ...suiviBases(p), ...(p.convergence ? ['convergence'] : [])].filter(k => suiviCompte(etat[k], t));
      if (!cles.length) continue;
      out.push({...p, suivies: cles});
    } else out.push(p);
  }
  return out;
}
// `poids(p)` : nombre de mises du pari. Dans « Toutes », chaque stratégie suivie qui l'a pris mise 10 € ;
// la vue d'une seule stratégie compte une mise.
function suiviBilan(prises, poids = () => 1) {
  const b = {paris: 0, regles: 0, gagnes: 0, en_cours: 0, mises: 0, gains: 0};
  for (const p of prises) {
    const w = poids(p);
    b.paris += w;
    if (!REGLES_SUIVI.has(p.statut)) {b.en_cours += w; continue;}
    const mise = suiviNombre(p.mise) ?? 10;
    const g = suiviNombre(p.gain) ?? (p.statut === 'gagne' ? mise * (p.cote - 1) : p.statut === 'perdu' ? -mise : 0);
    b.regles += w; b.mises += mise * w; b.gains += g * w;
    if (g > 0) b.gagnes += w;
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
// Les stratégies choisies pour Pushover comptent aussi : elles sont gardées à part (CLE_SUIVI_PUSHOVER) et réunies à
// celles de l'abonnement Chrome, pour qu'une coche ou un arrêt de l'un n'arrête pas le suivi de l'autre.
const CLE_SUIVI_PUSHOVER = 'cv-suivi-pushover-v1';
const DEBUT_PUSHOVER_SITE = Date.parse('2026-10-25T12:44:00Z');       // choix Pushover lu depuis le site
const suiviPushoverLire = () => { try { const l = JSON.parse(lire(CLE_SUIVI_PUSHOVER) || '[]'); return Array.isArray(l) ? l : []; } catch { return []; } };
function suiviEnregistrer(cochees, depuis) {
  const etat = suiviLire();
  const toutes = [...new Set([...cochees, ...suiviPushoverLire()])];
  ecrire(CLE_SUIVI, JSON.stringify(suiviSynchroniser(etat, toutes, Date.now(), depuis)));
}
function suiviPushover(choisies) {
  ecrire(CLE_SUIVI_PUSHOVER, JSON.stringify([...choisies]));
  let chrome = [];
  try { const d = JSON.parse(lire('cv-notifications-v1') || 'null'); if (d?.enabled && Array.isArray(d.strategies)) chrome = d.strategies; } catch {}
  suiviEnregistrer(chrome, DEBUT_PUSHOVER_SITE);
}
function suiviAmorcer(cochees, since) {                  // appareil déjà abonné avant cette fonction : on part de l'abonnement
  if (Object.keys(suiviLire()).length || !cochees.length) return;
  const t = Date.parse(since);
  suiviEnregistrer(cochees, Number.isFinite(t) ? t : Date.now());
}

// --- affichage
function suiviBankroll(x) { return typeof enBankroll === 'function' ? enBankroll(x) : x; }      // montants pour la bankroll choisie
const eur2 = x => { if (x == null) return '—'; x = suiviBankroll(x); return (x > 0 ? '+' : '') + x.toFixed(2).replace('.', ',') + ' €'; };
const nomStrategie = k => (D.notifications?.strategies || {})[k] || (D.strategies_badges || {})[k] || k;
let suiviFiltre = '', suiviLimite = 50;
let prisesCache = [null, [], false];
// Copie des prises propre à cet onglet, refaite quand la mise des bilans change (fixe, Kelly ¼ ou un autre mode).
const prisesSuivi = () => {
  const mode = typeof miseMode !== 'undefined' ? miseMode : 'fixe';
  if (prisesCache[0] !== D.catalogue || prisesCache[2] !== mode) {
    let objets = suiviObjets(D.catalogue);
    // Kelly ¼ : la mise est dans le catalogue ; autre mode : dans son bloc chargé (mises_paris, par identifiant).
    const autres = mode !== 'fixe' && mode !== 'kelly' && typeof blocMise === 'function' ? (blocMise(mode)?.mises_paris || {}) : null;
    const miseDe = p => mode === 'kelly' ? p.mise_kelly : autres ? autres[p.id] : null;
    if (mode !== 'fixe') objets = objets.map(p => { const m = miseDe(p); return m && p.mise ? {...p, mise: m,
      gain: p.gain == null ? p.gain : Math.round(100 * p.gain * m / p.mise) / 100} : p; });
    prisesCache = [D.catalogue, objets, mode];
  }
  return prisesCache[1];
};

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
  <div class="l1"><span><b class="${signe(b.gains)}">${eur2(b.regles ? b.gains : null)}</b> <small class="roi ${signe(b.roi)}">ROI ${b.roi == null ? '—' : pctC(b.roi)}</small> <small>· ${typeof miseMode !== 'undefined' && miseMode !== 'fixe' ? 'mise ' + (typeof nomMise === 'function' ? nomMise() : 'Kelly ¼') + ' par stratégie et par pari' : (typeof eurosNets === 'function' ? eurosNets(10) : '10') + ' € par stratégie et par pari'}</small></span></div></div>`;
// Bilan « Paris uniques » : deux dates au choix en plus des périodes rapides.
function rendreDatesBilan() {
  const zone = document.getElementById('bu-dates');
  if (!zone) return;
  if (!zone.dataset.pret) { zone.innerHTML = '<details class="mode-emploi bu-dates-perso"><summary>Dates personnalisées</summary>' + datesHtml() + '<p class="aide">Dates de règlement des paris. Choisir des dates remplace la période rapide.</p></details>'; zone.dataset.pret = '1'; lierDates(zone, false); }
  else zone.querySelectorAll('input[data-p]').forEach(i => i.value = suiviPeriode()[i.dataset.p] || '');
}

// Heures des notifications : paris pris par les stratégies `cles` sur les `jours` derniers jours (tout l'historique
// publié, pas seulement depuis la coche), un par pari (même match, marché, ligne et issue), heure de Paris.
function suiviHeures(prises, cles, maintenant = Date.now(), jours = 30) {
  const debut = maintenant - jours * 86400000, vus = new Set(), heures = Array(24).fill(0);
  const heureParis = new Intl.DateTimeFormat('en-GB', {timeZone: 'Europe/Paris', hour: '2-digit', hourCycle: 'h23'});
  let n = 0, premier = maintenant;
  for (const p of prises) {
    const t = Date.parse(p.detecte);
    if (!Number.isFinite(t) || t < debut || t > maintenant) continue;
    const k = [...(p.strategies || []), ...(p.regles || []), ...suiviBases(p), ...(p.convergence ? ['convergence'] : [])];
    if (!k.some(x => cles.includes(x))) continue;
    const u = [p.match_id, p.marche, p.periode, p.ligne, p.issue, p.joueur].join('|');
    if (vus.has(u)) continue;
    vus.add(u);
    heures[Number(heureParis.formatToParts(new Date(t)).find(x => x.type === 'hour').value) % 24]++;
    n++; premier = Math.min(premier, t);
  }
  return {heures, n, jours: n ? Math.max(1, Math.min(jours, Math.round((maintenant - premier) / 86400000))) : 0};
}
const TRANCHES_HEURES = [['La nuit', 0, 8], ['Le matin', 8, 12], ["L'après-midi", 12, 18], ['Le soir', 18, 24]];
function heuresHtml(r) {
  if (!r.n) return '<div class="carte mes-heures"><h3 class="bu-titre">Quand arrivent les notifications ?</h3><p class="aide">Pas encore de paris pour ces stratégies sur les 30 derniers jours.</p></div>';
  const h = r.heures, max = Math.max(...h), pc = v => Math.round(100 * v / r.n) + ' %';
  let fort = 0, debut = 0;
  for (let i = 0; i < 24; i++) { const t = h[i] + h[(i + 1) % 24] + h[(i + 2) % 24]; if (t > fort) { fort = t; debut = i; } }
  const parJour = (r.n / r.jours).toLocaleString('fr-FR', {maximumFractionDigits: 1});
  const tranches = TRANCHES_HEURES.map(([nom, a, b]) => { const v = h.slice(a, b).reduce((x, y) => x + y, 0);
    return `<span><b>${pc(v)}</b> ${e(nom)} <small>(${a} h–${b} h)</small></span>`; }).join('');
  const barres = h.map((v, i) => `<i title="${i} h : ${v} pari${v > 1 ? 's' : ''}" class="${(i - debut + 24) % 24 < 3 ? 'fort' : ''}" style="height:${Math.max(2, Math.round(100 * v / max))}%"></i>`).join('');
  return `<div class="carte mes-heures"><h3 class="bu-titre">Quand arrivent les notifications ?</h3>
  <p class="explication"><b>Environ ${parJour} par jour.</b> Le plus souvent entre <b>${debut} h et ${(debut + 3) % 24} h</b> (${pc(fort)} des notifications).
  <b>Exemple</b> : si tu regardes ton téléphone vers ${(debut + 1) % 24} h, c'est là que tu en auras le plus.</p>
  <div class="heures-tranches">${tranches}</div>
  <div class="heures-barres" role="img" aria-label="Notifications par heure">${barres}</div>
  <div class="heures-axe"><small>0 h</small><small>6 h</small><small>12 h</small><small>18 h</small><small>23 h</small></div>
  <p class="aide">${r.n} paris sur les ${r.jours} derniers jours, heure de Paris. Calculé sur tout l'historique ${r.cles > 1 ? 'de tes ' + r.cles + ' stratégies cochées, même avant que tu les coches' : 'de cette stratégie, même avant que tu la coches'}.</p></div>`;
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
      <span class="sante-mot sante-mot-${actif ? 'ok' : 'alerte'}">${actif ? '✓ Active' : 'Arrêtée'}</span>${actif ? ` <button type="button" class="btn secondaire" data-zero-un="${e(k)}">Repartir de zéro</button>` : ` <button type="button" class="btn secondaire" data-retirer="${e(k)}">Retirer</button>`}</div>`;
  }).join('');
  const puce = (k, nom, n) => `<button type="button" data-suivi="${e(k)}" class="${suiviFiltre === k ? 'actif' : ''}">${e(nom)} <small>${n}</small></button>`;
  sortie.innerHTML = `<div class="puces" aria-label="Filtrer par stratégie">${puce('', 'Toutes', toutes.length)}${cles.map(k => puce(k, nomStrategie(k), nb[k])).join('')}</div>`
    + resumeHtml(suiviBilan(vues, suiviFiltre ? () => 1 : p => p.suivies.length))
    // Gain cumulé des paris suivis, avec la ligne témoin (attendu) et la marge du hasard (visuels.js).
    + (() => { const ks = suiviFiltre ? [suiviFiltre] : cles.filter(k => { const l = etat[k]; return l.length && l[l.length - 1][1] == null; });
      return ks.length ? heuresHtml({...suiviHeures(prisesSuivi(), ks), cles: ks.length}) : ''; })()
    + (typeof grandeCourbe === 'function' ? `<div class="carte mes-courbe">${grandeCourbe(pointsDepuisParis(vues, suiviFiltre ? () => 1 : p => p.suivies.length))}</div>` : '')
    + `<div id="mes-liste">${vues.slice(0, suiviLimite).map(p => carteSuivi(p, suiviFiltre ? 1 : p.suivies.length)).join('') || '<p class="vide">Aucun pari sur cette période.</p>'}</div>`
    + (vues.length > suiviLimite ? '<p><button type="button" class="btn secondaire" id="mes-plus">Voir plus</button></p>' : '')
    + `<details class="mode-emploi"><summary>Stratégies suivies</summary><div class="carte">${lignesSuivi}</div>
       <p class="aide">Seuls comptent les paris détectés pendant que la stratégie était cochée. Une décoche enregistrée arrête l’ajout de ses nouveaux paris, l’historique déjà suivi reste : « Retirer » l’efface. Ce suivi est enregistré sur cet appareil.</p>
       <p><button type="button" class="btn secondaire" id="mes-zero">Tout repartir de zéro</button></p>
       <p class="aide">Le bouton de chaque stratégie ne remet à zéro que celle-ci. « Tout repartir de zéro » : toutes les stratégies cochées recommencent maintenant ; les stratégies arrêtées sont effacées. Les paris eux-mêmes ne changent pas.</p></details>`;
  sortie.querySelectorAll('[data-suivi]').forEach(b => b.onclick = () => { suiviFiltre = b.dataset.suivi; suiviLimite = 50; rendreMesStrategies(); });
  const plus = document.getElementById('mes-plus');
  if (plus) plus.onclick = () => { suiviLimite += 50; rendreMesStrategies(); };
  sortie.querySelectorAll('[data-retirer]').forEach(b => b.onclick = () => {
    if (!confirm(`Retirer « ${nomStrategie(b.dataset.retirer)} » et son historique de Mes stratégies ?`)) return;
    ecrire(CLE_SUIVI, JSON.stringify(suiviRetirer(suiviLire(), b.dataset.retirer))); rendreMesStrategies();
  });
  sortie.querySelectorAll('[data-zero-un]').forEach(b => b.onclick = () => {
    const k = b.dataset.zeroUn;
    if (!confirm(`Repartir de zéro pour « ${nomStrategie(k)} » seulement ? Ses statistiques recommencent maintenant ; les autres stratégies ne changent pas.`)) return;
    ecrire(CLE_SUIVI, JSON.stringify(suiviRepartir(suiviLire(), Date.now(), k)));
    if (suiviFiltre === k) suiviFiltre = '';
    rendreMesStrategies();
  });
  const zero = document.getElementById('mes-zero');
  if (zero) zero.onclick = () => {
    if (!confirm('Repartir de zéro ? Les statistiques des stratégies cochées recommencent maintenant ; les stratégies arrêtées sont effacées.')) return;
    ecrire(CLE_SUIVI, JSON.stringify(suiviRepartir(suiviLire(), Date.now()))); suiviFiltre = ''; rendreMesStrategies();
  };
}
// Même ligne colorée que l'onglet Paris : vert gagné, rouge perdu ; les stratégies qui l'ont pris sont listées dessous.
const LIGNE_SUIVI = {gagne: ['gagne', '✓ Gagné'], demi_gagne: ['gagne', '✓ ½ gagné'], perdu: ['perdu', '✗ Perdu'],
  demi_perdu: ['perdu', '✗ ½ perdu'], rembourse: ['rembourse', 'Remboursé']};
const REF_SUIVI = {Pinnacle: '', Polymarket: 'Poly ', Consensus: 'Cons. ', Smarkets: 'Sm. '};
// Bouton « Parier chez … » de liens.js (absent quand ce fichier est testé seul).
const boutonSuivi = (p, court = false) => typeof boutonBookmaker === 'function' ? boutonBookmaker(p, court) : '';
// Affichage seul : un pari pris par plusieurs stratégies suivies montre la mise totale (unitaire × nombre),
// le détail reste en petit et en infobulle. Mise inconnue : 10 €, comme dans suiviBilan.
const montantSuivi = x => suiviBankroll(x).toLocaleString('fr-FR', {minimumFractionDigits: 2, maximumFractionDigits: 2}) + ' €';
function texteMiseSuivi(mise, mises = 1) {
  const m = suiviNombre(mise);
  if (!(mises > 1)) return m != null ? ` · mise ${montantSuivi(m)}` : '';
  const u = m ?? 10, detail = `${mises} × ${montantSuivi(u)}`;
  return ` · mise totale ${montantSuivi(u * mises)} <small class="mise-detail" title="${mises} mises de ${montantSuivi(u)}">(${detail})</small>`;
}
const carteSuivi = (p, mises = 1) => {
  const [etat, libelle] = LIGNE_SUIVI[p.statut] || ['cours', 'En cours'];
  const quand = new Date(p.detecte).toLocaleString('fr-FR', {timeZone: 'Europe/Paris', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit'});
  const valeur = suiviNombre(p.gain) != null ? eur2(p.gain * mises) : '';
  const miseTexte = texteMiseSuivi(p.mise, mises);
  return `<details class="ligne-detail ligne-pari pari-ligne etat-${etat}"><summary>
<span class="pari-gauche"><span class="pari-tete"><span class="puce-sport">${e((typeof nomsSports !== 'undefined' && nomsSports[p.sport]) || p.sport || 'Sport')}</span><span class="pari-ligue">${e(p.ligue || '')}</span></span>
<span class="ligne-nom pari-match">${e(p.domicile)} – ${e(p.exterieur)}</span><span class="pari-selection">${e(p.pari)}</span>${typeof horairePari === 'function' ? `<span class="pari-debut">Match ${horairePari(p)}</span>` : ''}</span>
<span class="pari-milieu"><span class="pari-bookmaker">${e(p.bookmaker)} · ${quand}</span>
<span><b class="ligne-cote">${cote(p.cote)}</b> <span class="pari-ref">(${e(REF_SUIVI[p.reference] ?? (p.reference || '') + ' ')}${cote(p.cote_juste)})</span></span></span>
<span class="pari-droite"><b class="ligne-valeur">${valeur}</b><span class="pari-etat">${libelle}${miseTexte}</span>${boutonSuivi(p, true)}</span></summary>
<div class="ligne-corps"><div class="carte">${boutonSuivi(p) ? `<div class="l1">${boutonSuivi(p)}</div>` : ''}<div class="l4">${p.suivies.map(k => `<span class="badge">${e(nomStrategie(k))}</span>`).join('')}</div></div></div></details>`;
};
