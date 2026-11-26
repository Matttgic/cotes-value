// Décision : trois questions seulement, et chaque réponse renvoie au chiffre mesuré qui la justifie (« Les chiffres »,
// en bas de la page). Lecture seule de données déjà publiées : D.decision (cotes/decision.py : ROI et CLV contre la
// clôture Pinnacle par bookmaker et par référence), D.protocole (seul à pouvoir dire « prouvé », docs/protocole.md),
// D.pauses, D.doublons et les fiches des paris. Aucun test du protocole n'est lu avant ses deux lectures prévues.
// Fonctions seulement (pas de « const » au premier niveau) : la page ouvre son onglet de départ avant ce fichier.
function decPct(x, d = 2) { return x == null ? '—' : (x > 0 ? '+' : '') + Number(x).toFixed(d).replace('.', ',') + ' %'; }
function decIc(v, d = 2) { return v ? ` [${decPct(v[0], d).replace(' %', '')} ; ${decPct(v[1], d).replace(' %', '')}]` : ''; }
function decNb(n) { return Number(n || 0).toLocaleString('fr-FR'); }
function decJour(d) { return d ? d.slice(8, 10) + '/' + d.slice(5, 7) + '/' + d.slice(0, 4) : '—'; }
function decP(p) { return p == null ? '' : p < 1e-4 ? 'p < 0,01 %' : 'p = ' + (100 * p).toFixed(p < 0.01 ? 2 : 1).replace('.', ',') + ' %'; }
function decPluriel(n, mot, pluriel = mot + 's') { return `${decNb(n)} ${n > 1 ? pluriel : mot}`; }
function decEtat(decision) { return {jouer: 'Jouable', couper: 'À couper', surveiller: 'À surveiller', attendre: 'Non tranché'}[decision] || decision; }
function decAncre(id) { return 'chiffre-' + String(id).replace(/[^a-zA-Z0-9]+/g, '-'); }
// Chiffres d'une ligne mesurée, tels qu'ils sont écrits dans les réponses et dans le tableau.
function decClv(l) {
  return l.clv == null ? 'CLV Pinnacle non mesurée' : `CLV Pinnacle ${decPct(l.clv)}${decIc(l.clv_ic)} · ${decPluriel(l.clv_n, 'mesuré')}`;
}
function decRoi(l) { return l.roi == null ? 'aucun pari réglé' : `ROI ${decPct(l.roi, 1)}${decIc(l.roi_ic, 1)} · ${decPluriel(l.regles, 'réglé')}`; }
// Bouton « preuve » : le chiffre lui-même, qui mène à sa ligne dans « Les chiffres ».
function decPreuve(id, texte) {
  return `<button type="button" class="dec-preuve" data-chiffre="${e(id)}">${e(texte)} <span aria-hidden="true">↓</span></button>`;
}

// Règle principale (cotes/regle_principale.py) : la seule règle jugée, figée le 14/11, sur les paris d'après le gel.
function decHtmlPrincipale(P) {
  if (!P || !P.regle) return '';
  const verdict = P.prouve ? '<b class="pos">Avantage mesuré</b>' : '<b>Pas encore prouvé</b>';
  const clv = P.clv == null ? 'CLV Pinnacle non mesurée'
    : `CLV Pinnacle ${decPct(P.clv)}${decIc(P.clv_ic)} · ${decPluriel(P.clv_n, 'mesuré')}${P.clv_p == null ? '' : ' · ' + decP(P.clv_p)}`;
  const roi = P.roi == null ? 'aucun pari réglé' : `ROI ${decPct(P.roi, 1)}${decIc(P.roi_ic, 1)} · ${decPluriel(P.regles, 'réglé')}`;
  return `<li><span class="badge ${P.prouve ? 'gagne' : 'en_cours'}">Règle principale</span> ${verdict} : ${e(P.regle.nom)}, seule règle jugée,
sur les paris détectés depuis le ${decJour(P.regle.gel)}. <span class="dec-chiffre">${e(clv)} · ${e(roi)}</span>
<span class="aide">${e(P.regle.texte)}. Un seul test : CLV &gt; 0, seuil ${decPct(100 * P.alpha, 0).replace('+', '')}.</span></li>`;
}

// Filtres observés (cotes/filtres_observes.py) : sous-ensembles de la règle suivis depuis le 26/11, jamais joués.
function decHtmlObserves(O) {
  if (!O || !(O.filtres || []).length) return '';
  const ligne = F => {
    const clv = F.clv == null ? 'CLV non mesurée' : `CLV Pinnacle ${decPct(F.clv)}${decIc(F.clv_ic)} · ${decPluriel(F.clv_n, 'mesuré')}${F.clv_p == null ? '' : ' · ' + decP(F.clv_p)}`;
    const roi = F.roi == null ? 'aucun pari réglé' : `ROI ${decPct(F.roi, 1)}${decIc(F.roi_ic, 1)} · ${decPluriel(F.regles, 'réglé')}`;
    const badge = F.principal ? `<span class="badge ${F.prouve ? 'gagne' : 'en_cours'}">${F.prouve ? 'Avantage mesuré' : 'Testé'}</span> ` : '';
    return `<li>${badge}<b>${e(F.nom)}</b> : ${decPluriel(F.paris, 'pari')}. <span class="dec-chiffre">${e(clv)} · ${e(roi)}</span></li>`;
  };
  return `<li><span class="badge">Filtres observés</span> suivis depuis le ${decJour(O.gel)} sur les paris de la règle principale, sans être joués.
<span class="aide">Un seul test, sur le filtre marqué : CLV &gt; 0, seuil ${decPct(100 * O.alpha, 0).replace('+', '')}, à partir de ${O.min_clv} CLV. À relire le ${decJour(O.revoir_le)}.</span>
<ul>${O.filtres.map(ligne).join('')}</ul></li>`;
}

// 1. L'avantage est-il prouvé ? Seul le protocole fixé à l'avance peut le dire : une stratégie « validée ».
function decisionAvantage(P, maintenant = Date.now()) {
  const R = (P && P.regles) || {}, lignes = Object.values((P && P.lignes) || {}).filter(l => l.statut !== 'hors_protocole');
  const par = statut => lignes.filter(l => l.statut === statut);
  // Prochaine lecture : parmi les stratégies qui ont déjà des paris mesurés, celle à qui il en manque le moins.
  const prochaine = par('en_cours').filter(l => l.mesures > 0).map(l => {
    const cible = l.mi_parcours ? l.n : l.mi;
    return {...l, cible, lecture: l.mi_parcours ? 'lecture finale' : 'mi-parcours', manque: Math.max(0, cible - l.mesures)};
  }).sort((a, b) => a.manque - b.manque || String(a.nom).localeCompare(String(b.nom)))[0] || null;
  const validees = par('succes');
  return {prouve: validees.length > 0, validees, echecs: par('echec'), rompues: par('rompu'), enCours: par('en_cours'),
    inscrites: lignes.length, commence: !!R.debut && Date.parse(R.debut) <= maintenant, prochaine, regles: R};
}

// Un pari appartient-il à la stratégie ``cle`` du protocole ? (règles du laboratoire : « labo:<id> »)
function decDansStrategie(p, cle) {
  return cle === 'convergence' ? !!p.convergence
    : cle.startsWith('labo:') ? (p.regles || []).includes(cle.slice(5)) : (p.strategies || []).includes(cle);
}

// 2. Quoi jouer aujourd'hui ? Les paris uniques encore ouverts (match pas commencé) :
// - « prouvé » : pris par une stratégie validée par le protocole ;
// - « probable » : le bookmaker ET la référence du pari battent la clôture Pinnacle de façon établie (décision « jouer »).
// Un pari dont le bookmaker ou la référence est « à couper » n'est jamais retenu.
function decisionParis(fiches, DEC, P, maintenant = Date.now()) {
  const lignes = new Map(((DEC && DEC.lignes) || []).map(l => [l.id, l]));
  const validees = Object.values((P && P.lignes) || {}).filter(l => l.statut === 'succes');
  const ouverts = fiches.filter(p => p.unique_bilan && p.statut === 'en_cours' && !p.a_regler && Date.parse(p.debut) > maintenant);
  const jouer = [], coupes = [], attente = [];
  for (const p of ouverts) {
    const b = lignes.get('bookmaker:' + p.bookmaker), r = lignes.get('reference:' + p.reference);
    const coupe = [b, r].find(l => l && l.decision === 'couper');
    const strategies = validees.filter(l => decDansStrategie(p, l.cle));
    if (coupe) coupes.push({p, ligne: coupe});
    else if (strategies.length) jouer.push({p, niveau: 'prouve', strategies, preuves: [b, r].filter(Boolean)});
    else if (b && r && b.decision === 'jouer' && r.decision === 'jouer') jouer.push({p, niveau: 'probable', strategies: [], preuves: [b, r]});
    else attente.push({p, ligne: b && b.decision !== 'jouer' ? b : r && r.decision !== 'jouer' ? r : b || r || null});
  }
  jouer.sort((x, y) => (x.niveau === 'prouve' ? 0 : 1) - (y.niveau === 'prouve' ? 0 : 1) || Date.parse(x.p.debut) - Date.parse(y.p.debut));
  return {ouverts: ouverts.length, jouer, coupes, attente};
}

// 3. Quoi couper ? Ce qui est mesuré comme perdant (« couper »), ce qui est déjà arrêté (pauses, protocole), et ce qui
// penche du mauvais côté sans être tranché (« surveiller »). Sans rien à couper : la ligne la plus proche d'une coupe.
function decisionCoupes(D) {
  const lignes = (D.decision && D.decision.lignes) || [], P = D.protocole || {};
  const pauses = Object.entries((D.pauses && D.pauses.liste) || {}).map(([id, p]) => ({id, ...p}));
  const enPause = new Set(pauses.map(p => p.cle));
  const protocole = Object.values(P.lignes || {});
  const partMin = 100 * ((P.regles && P.regles.couverture_min) || 0.5);
  const negatives = lignes.filter(l => l.roi_ic && l.roi < 0 && l.decision !== 'couper' && l.decision !== 'surveiller')
    .sort((a, b) => a.roi_ic[1] - b.roi_ic[1]);
  return {
    couper: lignes.filter(l => l.decision === 'couper'),
    pauses,
    // Une pause automatique clôt aussi le protocole de la stratégie : elle n'est listée qu'une fois, comme pause.
    echecs: protocole.filter(l => l.statut === 'echec' && !enPause.has(l.cle)),
    rompues: protocole.filter(l => l.statut === 'rompu'),
    surveiller: lignes.filter(l => l.decision === 'surveiller'),
    // Protocole en cours mais clôture Pinnacle trop rare : la lecture finale échouera si rien ne change (§ 8).
    sansCloture: protocole.filter(l => l.statut === 'en_cours' && l.regles >= 30 && l.couverture != null && l.couverture < partMin),
    plusProche: negatives[0] || null,
    doublons: D.doublons || []};
}

function decHtmlPari(x) {
  return typeof ligneAccueilPari === 'function' ? ligneAccueilPari(x.p)
    : `<article class="acc-pari"><b>${e(x.p.domicile)} – ${e(x.p.exterieur)}</b> ${e(x.p.pari)} · ${e(x.p.bookmaker)}</article>`;
}
// Paris à jouer, regroupés par justification : les chiffres sont écrits une fois par groupe, pas à chaque pari.
function decHtmlJouer(jouer, visibles = 6) {
  const groupes = new Map();
  for (const x of jouer) {
    const cle = [x.niveau, ...x.strategies.map(s => s.cle), ...x.preuves.map(l => l.id)].join('|');
    if (!groupes.has(cle)) groupes.set(cle, {...x, paris: []});
    groupes.get(cle).paris.push(x);
  }
  return [...groupes.values()].map(g => {
    const preuves = g.strategies.map(s => decPreuve('protocole:' + s.cle, `Validée : ${s.nom}`))
      .concat(g.preuves.map(l => decPreuve(l.id, `${l.nom} · ${decClv(l)}`)));
    const titre = g.strategies.map(s => s.nom).concat(g.preuves.map(l => l.nom)).join(' × ');
    const suite = g.paris.slice(visibles);
    return `<div class="dec-groupe"><p class="dec-groupe-tete"><span class="badge ${g.niveau === 'prouve' ? 'gagne' : 'en_cours'}">${g.niveau === 'prouve' ? 'Avantage prouvé' : 'Avantage probable'}</span>
<b>${decPluriel(g.paris.length, 'pari')}</b> · ${e(titre)}</p><p class="dec-preuves">${preuves.join('')}</p>
${g.paris.slice(0, visibles).map(decHtmlPari).join('')}${suite.length ? `<details class="mode-emploi"><summary>Les ${suite.length} suivants, par heure de match</summary>${suite.map(decHtmlPari).join('')}</details>` : ''}</div>`;
  }).join('');
}
// Paris ouverts non retenus, regroupés par la ligne qui les écarte.
function decHtmlEcartes(liste, raison) {
  const groupes = new Map();
  for (const x of liste) {
    const cle = x.ligne ? x.ligne.id : '';
    groupes.set(cle, {ligne: x.ligne, n: (groupes.get(cle) || {n: 0}).n + 1});
  }
  return [...groupes.values()].sort((a, b) => b.n - a.n).map(g => `<li>${decPluriel(g.n, 'pari')} ${g.ligne
    ? `· <b>${e(g.ligne.nom)}</b> : ${e(raison(g.ligne))} ${decPreuve(g.ligne.id, g.ligne.clv_ic ? decClv(g.ligne) : decRoi(g.ligne))}`
    : '· bookmaker ou référence sans mesure'}</li>`).join('');
}
function decNomStrategie(id, noms) { return (noms && noms.get(id)) || id; }

// La règle « Quoi jouer » a-t-elle marché ? Bilan rejoué sans regard vers l'avenir (cotes/decision.py, ``rejouer``).
function decVerdictRejeu(b) {
  return !b || !b.roi_ic ? {cls: 'attendre', mot: 'Non tranché'} : b.roi_ic[0] > 0 ? {cls: 'jouer', mot: 'Gagnante'}
    : b.roi_ic[1] < 0 ? {cls: 'couper', mot: 'Perdante'} : {cls: 'attendre', mot: 'Non tranché'};
}
function decLignesRejeu(R) {
  if (!R || !R.retenus || !R.retenus.regles) return [];
  return [{id: 'rejeu:retenus', nom: 'Règle « Quoi jouer », rejouée', raison: `paris retenus · ${decPluriel(R.jours, 'jour')} depuis le ${decJour(R.debut)}`, ...R.retenus},
    {id: 'rejeu:ecartes', nom: 'Paris uniques écartés, mêmes jours', raison: 'pour comparer', ...R.ecartes}];
}
function decHtmlRejeu(R) {
  const [r, x] = decLignesRejeu(R);
  if (!r) return `<p class="aide"><b>A-t-elle marché ?</b> Jamais appliquée : aucun jour n'a encore eu un bookmaker et une référence jouables avec les seuls paris réglés avant lui.</p>`;
  const v = decVerdictRejeu(r);
  const titre = {jouer: 'Oui, elle a gagné.', couper: 'Non, elle a perdu.', attendre: 'Pas encore tranché.'}[v.cls];
  const roi = v.cls === 'jouer' ? "L'intervalle du ROI est au-dessus de zéro."
    : v.cls === 'couper' ? "L'intervalle du ROI est sous zéro."
    : "L'intervalle du ROI contient zéro : trop peu de paris pour savoir si elle rapporte.";
  const clv = !r.clv_ic ? '' : r.clv_ic[0] > 0 ? ' Ses paris battent bien la clôture Pinnacle.'
    : r.clv_ic[1] < 0 ? ' Ses paris perdent contre la clôture Pinnacle.' : ' Sa CLV Pinnacle ne se distingue pas de zéro.';
  const preuves = l => decPreuve(l.id, decRoi(l)) + (l.clv != null ? ' ' + decPreuve(l.id, decClv(l)) : '');
  return `<div class="dec-bilan"><p class="dec-reponse"><strong class="${v.cls === 'jouer' ? 'pos' : v.cls === 'couper' ? 'neg' : ''}">A-t-elle marché ? ${titre}</strong>
Rejouée chaque jour depuis le ${decJour(R.debut)}, avec les seuls paris réglés avant ce jour : ${decPluriel(r.regles, 'pari retenu', 'paris retenus')}, ${decPluriel(R.jours, 'jour')}.
${roi}${clv}</p><p class="dec-preuves">${preuves(r)}</p>
<p class="aide">Pour comparer, les ${decPluriel(x.regles, 'autre pari unique', 'autres paris uniques')} des mêmes jours : ${preuves(x)}</p></div>`;
}

// Page entière. ``noms`` : identifiant de stratégie → nom affiché (classement du Bilan), pour les pauses et les doublons.
function htmlDecision(D, fiches, maintenant = Date.now(), noms = null) {
  const DEC = D.decision || {}, lignes = DEC.lignes || [], R = DEC.regles || {};
  if (!lignes.length) return '<div class="vide">Chiffres de décision indisponibles à cette construction du site.</div>';
  const A = decisionAvantage(D.protocole, maintenant), J = decisionParis(fiches, DEC, D.protocole, maintenant), C = decisionCoupes(D);
  const ensemble = lignes.find(l => l.id === 'ensemble');
  const seuil = A.regles.alpha == null ? '' : ` · seuil p < ${String(Math.round(1e6 * A.regles.alpha) / 1e4).replace('.', ',')} %`;
  const compte = `${decPluriel(A.validees.length, 'validée')} sur ${decPluriel(A.inscrites, 'inscrite')}`;
  const nCoupes = C.couper.length + C.pauses.length + C.echecs.length + C.rompues.length;
  const nSurveiller = C.surveiller.length + C.sansCloture.length;
  const kpis = [
    ['Avantage prouvé ?', A.prouve ? 'Oui' : 'Non', A.prouve ? 'pos' : '', compte + ' au protocole'],
    ['À jouer maintenant', String(J.jouer.length), '', `sur ${decPluriel(J.ouverts, 'pari ouvert', 'paris ouverts')}`],
    ['À couper', String(nCoupes), nCoupes ? 'neg' : '', `${nSurveiller} à surveiller`]
  ].map(([t, v, c, d]) => `<div class="acc-kpi"><p>${e(t)}</p><strong class="${c}">${e(v)}</strong><span>${e(d)}</span></div>`).join('');

  // --- 1. L'avantage est-il prouvé ?
  const lecture = l => l.finale && l.finale.clv != null
    ? `CLV Pinnacle ${decPct(l.finale.clv)} · ${decP(l.finale.p)} · ${decPluriel(l.finale.n, 'pari mesuré', 'paris mesurés')}` : (l.motif || '');
  const etabli = !ensemble ? '' : ensemble.decision === 'jouer' || (ensemble.clv_ic && ensemble.clv_ic[0] > 0)
    ? `<li><b>Établi</b> : les paris uniques battent la clôture Pinnacle. ${decPreuve('ensemble', decClv(ensemble))}</li>`
    : `<li><b>Non établi</b> : la CLV des paris uniques ne se distingue pas de zéro. ${decPreuve('ensemble', decClv(ensemble))}</li>`;
  const gain = !ensemble || !ensemble.roi_ic ? '' : ensemble.roi_ic[0] > 0
    ? `<li><b>Gain</b> : le ROI des paris uniques est au-dessus de zéro, hors protocole. ${decPreuve('ensemble', decRoi(ensemble))}</li>`
    : `<li><b>Pas établi</b> : que cela rapporte. L'intervalle du ROI ${ensemble.roi_ic[1] < 0 ? 'est sous zéro' : 'contient zéro'}. ${decPreuve('ensemble', decRoi(ensemble))}</li>`;
  const suite = !A.commence ? `<li>Le protocole commence le ${decJour(A.regles.debut)} : aucun pari n'est encore compté.</li>`
    : A.prochaine ? `<li>Prochaine lecture : <b>${e(A.prochaine.nom)}</b>, ${A.prochaine.lecture} à ${decNb(A.prochaine.cible)} paris mesurés (${decNb(A.prochaine.mesures)} aujourd'hui). ${decPreuve('protocole', compte)}</li>`
    : `<li>Aucune stratégie n'a encore de pari mesuré dans le protocole.</li>`;
  const q1 = `<section class="dec-question" aria-labelledby="dec-q1"><h3 class="bu-titre" id="dec-q1"><small>1</small> L'avantage est-il prouvé ?</h3>
<p class="dec-reponse"><strong class="${A.prouve ? 'pos' : ''}">${A.prouve ? `Oui, pour ${decPluriel(A.validees.length, 'stratégie')}.` : 'Non.'}</strong>
${A.prouve ? 'Elles battent la clôture Pinnacle au seuil fixé avant les paris.' : "Aucune stratégie n'a passé le protocole fixé avant les paris, seul à pouvoir le dire."}
${decPreuve('protocole', compte + seuil)}</p>
<ul class="dec-liste">${decHtmlPrincipale(DEC.principale)}${decHtmlObserves(DEC.observes)}${A.validees.map(l => `<li><b>${e(l.nom)}</b> : validée. ${decPreuve('protocole:' + l.cle, lecture(l))}</li>`).join('')}${etabli}${gain}${suite}</ul></section>`;

  // --- 2. Quoi jouer aujourd'hui ?
  const jouables = lignes.filter(l => l.decision === 'jouer' && l.famille !== 'ensemble');
  const q2 = `<section class="dec-question" aria-labelledby="dec-q2"><h3 class="bu-titre" id="dec-q2"><small>2</small> Quoi jouer aujourd'hui ?</h3>
<p class="dec-reponse"><strong>${J.jouer.length ? decPluriel(J.jouer.length, 'pari') + '.' : 'Rien pour l’instant.'}</strong>
${J.jouer.length ? `Sur ${decPluriel(J.ouverts, 'pari ouvert', 'paris ouverts')}, ceux dont le bookmaker et la référence battent tous deux la clôture Pinnacle.`
    : J.ouverts ? `Aucun des ${decPluriel(J.ouverts, 'pari ouvert', 'paris ouverts')} n'a un bookmaker et une référence qui battent tous deux la clôture Pinnacle.`
    : 'Aucun pari ouvert dont le match n’a pas commencé.'}</p>
<p class="aide">Retenu : une mise par cote, match pas commencé, ${A.prouve ? 'pris par une stratégie validée, ou ' : ''}bookmaker et référence « jouables » dans Les chiffres${jouables.length
    ? ` (${jouables.map(l => e(l.nom)).join(', ')})` : ' (aucune ligne aujourd’hui)'}. ${A.prouve ? '' : 'Avantage probable, pas prouvé : '}la CLV contre la clôture Pinnacle est le seul chiffre qui prédit le rendement.</p>
${decHtmlRejeu(DEC.rejeu)}
<div class="dec-paris">${decHtmlJouer(J.jouer)}</div>
${J.coupes.length + J.attente.length ? `<details class="mode-emploi"><summary>Non retenus (${J.coupes.length + J.attente.length})</summary><ul class="dec-liste">
${decHtmlEcartes(J.coupes, () => 'à couper')}${decHtmlEcartes(J.attente, l => l.raison || 'non tranché')}</ul></details>` : ''}</section>`;

  // --- 3. Quoi couper ?
  const vers = `<button type="button" class="acc-lien" data-vers="strategies">Stratégies →</button>`;
  const quoi = l => l.famille === 'bookmaker' ? `Ne plus prendre de paris chez <b>${e(l.nom)}</b>`
    : l.famille === 'reference' ? `Ne plus suivre la <b>${e(l.nom.replace('Référence', 'référence'))}</b>` : `<b>${e(l.nom)}</b>`;
  const chiffres = l => decPreuve(l.id, decRoi(l)) + (l.clv != null ? ' ' + decPreuve(l.id, decClv(l)) : '');
  const virgule = x => String(x).replace('.', ',');
  const items = [
    ...C.couper.map(l => `<li><span class="badge perdu">À couper</span> ${quoi(l)} : ${e(l.raison)}. ${chiffres(l)}</li>`),
    ...C.pauses.map(p => `<li><span class="badge perdu">Déjà coupée</span> <b>${e(decNomStrategie(p.id, noms))}</b> : ${p.retiree ? `retirée le ${decJour(p.depuis)} : ${e(p.motif || 'elle perd même dans le meilleur cas')}` : `en pause automatique depuis le ${decJour(p.depuis)}, elle perd contre la clôture.
<span class="dec-chiffre">CLV par pari ${virgule(p.clv)} % (au mieux ${virgule(p.clv_haute)} %) · par match ${virgule(p.clv_match)} % · ${decPluriel(p.regles, 'réglé')}</span>`} ${p.retiree ? `<span class="dec-chiffre">${p.roi != null ? `ROI ${virgule(p.roi)} % (au mieux ${virgule(p.roi_haut)} %) sur ${p.matchs} matchs` : `${decPluriel(p.regles, 'réglé')}, dernier pari le ${decJour(p.dernier)}`}</span>` : ''} ${vers}</li>`),
    ...C.echecs.map(l => `<li><span class="badge perdu">Non validée</span> <b>${e(l.nom)}</b> : ${e(l.motif || 'protocole non réussi')}. ${decPreuve('protocole:' + l.cle, lecture(l))}</li>`),
    ...C.rompues.map(l => `<li><span class="badge perdu">Protocole rompu</span> <b>${e(l.nom)}</b> : ${e(l.motif || 'règles modifiées')} ; aucune conclusion possible sans nouvelle inscription. ${decPreuve('protocole:' + l.cle, 'Protocole rompu')}</li>`),
    ...C.surveiller.map(l => `<li><span class="badge a_regler">À surveiller</span> <b>${e(l.nom)}</b> : ${e(l.raison)}. ${chiffres(l)}</li>`),
    ...C.sansCloture.map(l => `<li><span class="badge a_regler">À surveiller</span> <b>${e(l.nom)}</b> : clôture Pinnacle trop rare, sa lecture finale échouera si rien ne change.
${decPreuve('protocole:' + l.cle, `Clôture connue pour ${virgule(l.couverture)} % des ${decNb(l.regles)} réglés`)}</li>`)];
  const proche = !C.couper.length && C.plusProche ? `<li>Le plus proche d'une coupe : <b>${e(C.plusProche.nom)}</b>, non tranché (${e(C.plusProche.raison)}). ${chiffres(C.plusProche)}</li>` : '';
  const d0 = C.doublons[0];
  const doublons = d0 ? `<li>Doublons : <b>${e(decNomStrategie(d0.a, noms))}</b> et <b>${e(decNomStrategie(d0.b, noms))}</b> partagent ${virgule(d0.part)} % de leurs paris
(${decNb(d0.communs)} en commun)${C.doublons.length > 1 ? `, et ${C.doublons.length - 1} autres paires à 80 % ou plus` : ''}. L'une des deux n'apporte presque rien. ${vers}</li>` : '';
  const q3 = `<section class="dec-question" aria-labelledby="dec-q3"><h3 class="bu-titre" id="dec-q3"><small>3</small> Quoi couper ?</h3>
<p class="dec-reponse"><strong class="${nCoupes ? 'neg' : ''}">${nCoupes ? decPluriel(nCoupes, 'ligne') + '.' : 'Rien aujourd’hui.'}</strong>
${nCoupes ? 'Mesurées comme perdantes, ou déjà arrêtées par leurs propres règles.' : 'Aucun bookmaker, aucune référence, aucune stratégie n’est mesuré comme perdant après correction.'}</p>
<ul class="dec-liste">${items.join('')}${proche}${doublons}</ul></section>`;

  // --- Les chiffres : une ligne par mesure citée plus haut.
  const etat = l => l.verdict ? `<span class="dec-etat ${l.verdict.cls}">${e(l.verdict.mot)}</span>`
    : `<span class="dec-etat ${l.decision}">${e(decEtat(l.decision))}</span>`;
  const rejeu = decLignesRejeu(DEC.rejeu).map((l, i) => ({...l, verdict: i ? {cls: '', mot: '—'} : decVerdictRejeu(l)}));
  const mesurees = [...lignes, ...rejeu].map(l => `<div class="dec-ligne" id="${decAncre(l.id)}" tabindex="-1"><span>${e(l.nom)}<small>${e(l.raison || '')}</small></span>
<span data-t="Réglés">${decNb(l.regles)}</span>
<span data-t="ROI" class="${signe(l.roi)}">${decPct(l.roi, 1)}<small>${l.roi_ic ? decIc(l.roi_ic, 1) : 'non testé'}</small></span>
<span data-t="CLV Pinnacle" class="${signe(l.clv)}">${decPct(l.clv)}<small>${l.clv_ic ? decIc(l.clv_ic) : l.clv == null ? '' : 'non testée'}</small></span>
<span data-t="Mesurés">${decNb(l.clv_n)}<small>${l.couverture == null ? '' : virgule(l.couverture) + ' %'}</small></span>${etat(l)}</div>`).join('');
  const Pn = (D.protocole && D.protocole.resume) || {};
  const suivies = [...A.validees, ...C.echecs, ...C.rompues, ...C.sansCloture].map(l => `<div class="dec-ligne dec-ligne-texte" id="${decAncre('protocole:' + l.cle)}" tabindex="-1">
<span>${e(l.nom)}<small>${e(l.statut === 'succes' ? 'validée' : l.motif || 'en cours')}</small></span><span class="dec-chiffre">${decNb(Math.min(l.mesures || 0, l.n || 0))} / ${decNb(l.n)} paris mesurés${l.couverture == null ? '' : ` · clôture connue ${virgule(l.couverture)} %`}${l.finale && l.finale.clv != null ? ' · ' + e(lecture(l)) : ''}</span></div>`).join('');
  const chiffresProtocole = `<div class="dec-ligne dec-ligne-texte" id="${decAncre('protocole')}" tabindex="-1"><span>Protocole de validation<small>docs/protocole.md</small></span>
<span class="dec-chiffre">${decPluriel(A.inscrites, 'inscrite')} · ${Pn.en_cours || 0} en cours · ${decPluriel(Pn.succes || 0, 'validée')} · ${decPluriel(Pn.echec || 0, 'non validée', 'non validées')} · ${decPluriel(Pn.rompu || 0, 'rompue')}${seuil} · début ${decJour(A.regles.debut)}${A.regles.scelle ? ' · scellé ' + e(A.regles.scelle) : ''}</span></div>`;
  return `<div class="acc-kpis dec-kpis">${kpis}</div>${q1}${q2}${q3}
<section class="dec-question" aria-labelledby="dec-chiffres"><h3 class="bu-titre" id="dec-chiffres">Les chiffres <small>calculés le ${e(quand(DEC.calcule_le))}</small></h3>
<div class="dec-table">${chiffresProtocole}${suivies}
<div class="dec-ligne bu-entete"><span>Ligne mesurée</span><span>Réglés</span><span>ROI · IC 95 %</span><span>CLV Pinnacle · IC 95 %</span><span>Mesurés</span><span>Décision</span></div>${mesurees}</div>
<p class="aide">Paris des bilans (cote ≤ 5, mise fixe), tout l'historique ; bookmakers sur les paris uniques, références sur tous leurs paris. Intervalles à 95 % par match.
<b>Jouable</b> : ROI positif et CLV Pinnacle positive après correction de Holm, mesurée sur au moins ${Math.round(100 * (R.part_pinnacle_min ?? .5))} % des paris réglés, rendement compatible avec la CLV.
<b>À couper</b> : ROI négatif, avec le ROI ou la CLV Pinnacle sous zéro après correction de Benjamini-Hochberg. <b>À surveiller</b> : intervalle du ROI sous zéro, ou CLV négative, sans les deux.
<b>Règle rejouée</b> : chaque jour, les décisions sont refaites avec les seuls paris réglés avant minuit (UTC), puis appliquées aux paris uniques détectés ce jour-là ; elle n'est pas corrigée, c'est un seul test.
Correction sur ${R.tests_roi ?? '—'} tests pour le ROI et ${R.tests_clv ?? '—'} pour la CLV (chaque ligne, dans les deux sens). Règles : docs/avantage-reel.md ; « prouvé » : docs/protocole.md.</p></section>`;
}

function rendreDecision() {
  const zone = document.getElementById('dec-contenu'); if (!zone) return;
  const noms = typeof lignesStrategies === 'function' ? new Map(lignesStrategies().map(r => [r.id, r.nom + (r.detail && r.reference !== 'comparateurs' && r.reference !== 'bases' ? ' · ' + r.detail : '')])) : null;
  zone.innerHTML = htmlDecision(D, fiches, Date.now(), noms);
  zone.onclick = ev => {
    const preuve = ev.target.closest('[data-chiffre]'), lien = ev.target.closest('[data-vers]');
    if (lien) { ouvrir(lien.dataset.vers); window.scrollTo(0, 0); return; }
    const cible = preuve && document.getElementById(decAncre(preuve.dataset.chiffre));
    if (!cible) return;
    zone.querySelectorAll('.dec-vise').forEach(x => x.classList.remove('dec-vise'));
    cible.classList.add('dec-vise');
    cible.scrollIntoView({behavior: 'smooth', block: 'center'});
    cible.focus({preventScroll: true});
  };
}
