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
const eur2 = x => x == null ? '—' : (x > 0 ? '+' : '') + x.toFixed(2).replace('.', ',') + ' €';
const nomStrategie = k => (D.notifications?.strategies || {})[k] || (D.strategies_badges || {})[k] || k;
let suiviFiltre = '', suiviLimite = 50;
let prisesCache = [null, [], false];
// Copie des prises propre à cet onglet, refaite quand la mise des bilans change (fixe 10 € ou Kelly ¼).
const prisesSuivi = () => {
  const kelly = typeof miseMode !== 'undefined' && miseMode === 'kelly';
  if (prisesCache[0] !== D.catalogue || prisesCache[2] !== kelly) {
    let objets = suiviObjets(D.catalogue);
    if (kelly) objets = objets.map(p => p.mise_kelly && p.mise ? {...p, mise: p.mise_kelly,
      gain: p.gain == null ? p.gain : Math.round(100 * p.gain * p.mise_kelly / p.mise) / 100} : p);
    prisesCache = [D.catalogue, objets, kelly];
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
  <div class="l1"><span><b class="${signe(b.gains)}">${eur2(b.regles ? b.gains : null)}</b> <small class="roi ${signe(b.roi)}">ROI ${b.roi == null ? '—' : pctC(b.roi)}</small> <small>· ${typeof miseMode !== 'undefined' && miseMode === 'kelly' ? 'mise Kelly ¼ par stratégie et par pari' : '10 € par stratégie et par pari'}</small></span></div></div>`;
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
    + resumeHtml(suiviBilan(vues, suiviFiltre ? () => 1 : p => p.suivies.length))
    + `<div id="mes-liste">${vues.slice(0, suiviLimite).map(p => carteSuivi(p, suiviFiltre ? 1 : p.suivies.length)).join('') || '<p class="vide">Aucun pari sur cette période.</p>'}</div>`
    + (vues.length > suiviLimite ? '<p><button type="button" class="btn secondaire" id="mes-plus">Voir plus</button></p>' : '')
    + `<details class="mode-emploi"><summary>Stratégies suivies</summary><div class="carte">${lignesSuivi}</div>
       <p class="aide">Seuls comptent les paris détectés pendant que la stratégie était cochée. Une décoche enregistrée arrête l’ajout de ses nouveaux paris, l’historique déjà suivi reste. Ce suivi est enregistré sur cet appareil.</p></details>`;
  sortie.querySelectorAll('[data-suivi]').forEach(b => b.onclick = () => { suiviFiltre = b.dataset.suivi; suiviLimite = 50; rendreMesStrategies(); });
  const plus = document.getElementById('mes-plus');
  if (plus) plus.onclick = () => { suiviLimite += 50; rendreMesStrategies(); };
}
// Même ligne colorée que l'onglet Paris : vert gagné, rouge perdu ; les stratégies qui l'ont pris sont listées dessous.
const LIGNE_SUIVI = {gagne: ['gagne', '✓ Gagné'], demi_gagne: ['gagne', '✓ ½ gagné'], perdu: ['perdu', '✗ Perdu'],
  demi_perdu: ['perdu', '✗ ½ perdu'], rembourse: ['rembourse', 'Remboursé']};
const REF_SUIVI = {Pinnacle: '', Polymarket: 'Poly ', Consensus: 'Cons. ', Smarkets: 'Sm. '};
// Bouton « Parier chez … » de liens.js (absent quand ce fichier est testé seul).
const boutonSuivi = (p, court = false) => typeof boutonBookmaker === 'function' ? boutonBookmaker(p, court) : '';
const carteSuivi = (p, mises = 1) => {
  const [etat, libelle] = LIGNE_SUIVI[p.statut] || ['cours', 'En cours'];
  const quand = new Date(p.detecte).toLocaleString('fr-FR', {timeZone: 'Europe/Paris', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit'});
  const valeur = suiviNombre(p.gain) != null ? eur2(p.gain * mises) : '';
  const miseTexte = suiviNombre(p.mise) != null ? ` · mise ${p.mise.toLocaleString('fr-FR', {minimumFractionDigits: 2, maximumFractionDigits: 2})} €` : '';
  return `<details class="ligne-detail ligne-pari pari-ligne etat-${etat}"><summary>
<span class="pari-gauche"><span class="pari-tete"><span class="puce-sport">${e((typeof nomsSports !== 'undefined' && nomsSports[p.sport]) || p.sport || 'Sport')}</span><span class="pari-ligue">${e(p.ligue || '')}</span></span>
<span class="ligne-nom pari-match">${e(p.domicile)} – ${e(p.exterieur)}</span><span class="pari-selection">${e(p.pari)}</span>${typeof horairePari === 'function' ? `<span class="pari-debut">Match ${horairePari(p)}</span>` : ''}</span>
<span class="pari-milieu"><span class="pari-bookmaker">${e(p.bookmaker)} · ${quand}</span>
<span><b class="ligne-cote">${cote(p.cote)}</b> <span class="pari-ref">(${e(REF_SUIVI[p.reference] ?? (p.reference || '') + ' ')}${cote(p.cote_juste)})</span></span></span>
<span class="pari-droite"><b class="ligne-valeur">${valeur}</b><span class="pari-etat">${libelle}${miseTexte}${mises > 1 ? ` · ${mises} mises` : ''}</span>${boutonSuivi(p, true)}</span></summary>
<div class="ligne-corps"><div class="carte">${boutonSuivi(p) ? `<div class="l1">${boutonSuivi(p)}</div>` : ''}<div class="l4">${p.suivies.map(k => `<span class="badge">${e(nomStrategie(k))}</span>`).join('')}</div></div></div></details>`;
};
