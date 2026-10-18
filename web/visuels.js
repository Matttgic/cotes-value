// Petits SVG locaux : uniquement les valeurs observées, jamais une projection.
function iconeSport(sport) {
  const chemins={
    football:'<circle cx="12" cy="12" r="9"/><path d="m12 7 5 4-2 6H9l-2-6 5-4Zm0-4v4M3 10l4 1m10 0 4-1M7 20l2-3m6 0 2 3"/>',
    basket:'<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3v18M6 5c8 5 8 9 12 14M18 5C10 10 10 14 6 19"/>',
    tennis:'<ellipse cx="14" cy="9" rx="6" ry="8" transform="rotate(40 14 9)"/><path d="m9 15-6 7m8-15 7 6m-8-2 7-7"/>',
    hockey:'<path d="m5 3 9 16h6v3h-8L3 5M15 6l-5 8"/><ellipse cx="19" cy="16" rx="3" ry="1.5"/>',
    volley:'<circle cx="12" cy="12" r="9"/><path d="m12 12 1-9m-1 9 8 4m-8-4-7 6M13 6l7 7M7 5l-1 9m4 6 8-3"/>',
    handball:'<circle cx="12" cy="12" r="9"/><path d="m12 7 5 4-2 6H9l-2-6 5-4ZM12 3v4M3 10l4 1m10 0 4-1"/>',
    rugby:'<ellipse cx="12" cy="12" rx="7" ry="11" transform="rotate(40 12 12)"/><path d="m8 16 8-8M9 11l4 4m-1-7 4 4"/>',
    football_americain:'<ellipse cx="12" cy="12" rx="7" ry="11" transform="rotate(40 12 12)"/><path d="m8 16 8-8M9 11l4 4m-1-7 4 4"/>',
    baseball:'<circle cx="12" cy="12" r="9"/><path d="M6 5c7 3 7 11 0 14M18 5c-7 3-7 11 0 14M7 8l3-1m-3 5h3m-3 4 3 1m7-9-3-1m3 5h-3m3 4-3 1"/>'
  };
  return `<svg class="sport-icone" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${chemins[sport] || '<circle cx="12" cy="12" r="8"/><path d="M8 12h8m-4-4v8"/>'}</svg>`;
}
const nomsSports={football:'Football',basket:'Basket',tennis:'Tennis',hockey:'Hockey',volley:'Volley',handball:'Handball',rugby:'Rugby',football_americain:'Foot US',baseball:'Baseball'};
function monogrammeBookmaker(nom) {
  const codes={Winamax:'w',Betclic:'b',Unibet:'u',PMU:'p',OlyBet:'o'};
  return `<span class="book-monogramme book-${codes[nom] || 'autre'}" aria-hidden="true">${e(String(nom || '?').slice(0,1))}</span>`;
}
function miniCourbe(points, couleur='var(--accent)') {
  const pts=(points || []).filter(p=>Number.isFinite(p[0]) && Number.isFinite(p[1]));
  if (!pts.length) return '<span class="courbe-absente">Courbe indisponible</span>';
  const W=150,H=52,m=4;
  const t0=pts[0][0],t1=pts.at(-1)[0],x=t=>m+(t-t0)/(t1-t0 || 1)*(W-2*m);
  const lo=Math.min(0,...pts.map(p=>p[1])),hi=Math.max(0,...pts.map(p=>p[1]));
  const y=g=>H-m-(g-lo)/(hi-lo || 1)*(H-2*m);
  let path=`M ${m} ${y(0)}`;
  for(const [t,g] of pts) path+=` H ${x(t)} V ${y(g)}`;
  return `<svg class="mini-courbe" viewBox="0 0 ${W} ${H}" role="img" aria-label="Gain cumulé : ${pts.length} règlements, échelle propre à la stratégie">
    <line x1="${m}" x2="${W-m}" y1="${y(0)}" y2="${y(0)}" stroke="var(--ligne)" stroke-dasharray="3 3"/>
    <path d="${path}" fill="none" stroke="${e(couleur)}" stroke-width="2" vector-effect="non-scaling-stroke"/>
    <circle cx="${x(pts.at(-1)[0])}" cy="${y(pts.at(-1)[1])}" r="2.5" fill="${e(couleur)}"/>
    <title>Gain cumulé observé · échelle propre · ${pts.length} règlements</title></svg>`;
}
function repartitionResultats(s) {
  const n=s.regles || 0;
  if (!n) return '<div class="resultats-vides">Aucun pari réglé sur cette période</div>';
  const autres=Math.max(0,n-s.gagnes-s.perdus);
  const libelleAutres=autres===1?'autre réglé':'autres réglés';
  const parts=[[s.gagnes,'gagnants'],[s.perdus,'perdants'],[autres,'autres']];
  return `<div class="resultats-repartition" role="img" aria-label="${s.gagnes} gagnés, ${s.perdus} perdus, ${autres} ${libelleAutres}">${parts.filter(([n])=>n>0).map(([v,c])=>`<span class="${c}" style="width:${100*v/n}%"></span>`).join('')}</div>
    <div class="resultats-legende"><span><i class="point-gagne"></i>${s.gagnes} gagnés</span><span><i class="point-perdu"></i>${s.perdus} perdus</span>${autres ? `<span>${autres} ${libelleAutres}</span>` : ''}</div>`;
}
function couvertureCLV(s) {
  const n=s.clv_n || 0,total=s.regles || 0,largeur=total?Math.min(100,100*n/total):0;
  return `<span class="couverture-clv" aria-hidden="true"><i style="width:${largeur}%"></i></span><small>${n}/${total} mesurés</small>`;
}
function carteStrategieVisuelle(r, points, couleur='var(--accent)') {
  const s=r.stats,pp=x=>pct(x==null?null:x/100);
  const code=r.nom.startsWith('Convergence')?'CV':r.nom.startsWith('Claude')?'CL':r.nom.startsWith('Gemini')?'GA':r.nom.startsWith('JULES')?'JL':r.nom.startsWith('M3')?'M3':r.nom.startsWith('ChatGPT')?'GP':'RF';
  return `<details class="ligne-detail ligne-strategie" id="strategie-${e(encodeURIComponent(r.id))}"><summary>
    <span class="ligne-nom" title="${e(r.nom+' · '+r.detail)}">${e(r.nomCourt || r.nom)}</span><span class="ligne-volume" aria-label="${s.regles} paris réglés, ${s.evenements_regles ?? "inconnu"} matchs">${s.regles}<small>${s.evenements_regles ?? "—"} matchs</small></span>
    <span class="ligne-roi ${signe(s.roi)}">${pp(s.roi)}</span><b class="ligne-valeur ${signe(s.gain)}">${s.regles?eur(s.gain):'—'}</b></summary>
    <div class="ligne-corps"><article class="strategie-ligne strategie-visuelle" style="--identite:${e(couleur)}">
    <div class="strategie-entete"><div class="strategie-identite"><span class="strategie-avatar" aria-hidden="true">${code}</span><h3>${e(r.nom)}</h3></div>
    <button class="btn secondaire" data-strategie="${e(r.id)}" aria-label="Voir les paris de ${e(r.nom)}">Les paris <span aria-hidden="true">↗</span></button></div>
    <div class="strategie-apercu"><div><span class="libelle-gain">Gain net simulé</span><strong class="${signe(s.gain)}">${s.regles?eur(s.gain):'—'}</strong></div>
    <div class="strategie-trajectoire">${miniCourbe(points,couleur)}<span>Trajectoire · échelle propre</span></div></div>
    <dl class="strat-chiffres">
      <div><dt>ROI</dt><dd class="${signe(s.roi)}">${pp(s.roi)}</dd><small>${r.reussite==null?'—':r.reussite.toFixed(1).replace('.',',')+' %'} de réussite</small></div>
      <div><dt>CLV moyenne</dt><dd class="${signe(s.clv)}">${pp(s.clv)}</dd>${couvertureCLV(s)}<small>Par match <b class="${signe(s.clv_evenement)}">${pp(s.clv_evenement)}</b> · ${s.clv_evenements_n ?? 0}/${s.evenements_regles ?? "—"} mesurés</small></div>
      <div><dt>Paris réglés</dt><dd>${s.regles} <small>(${s.evenements_regles ?? "—"} matchs)</small></dd><small>${s.paris} prises · ${s.attente} en attente</small></div>
    </dl>${repartitionResultats(s)}
    <details><summary>Règles et détail des résultats</summary><p>${e(r.detail)}</p>
      <div class="strat-secondaires"><span>Gains bruts<b class="pos">${s.regles?eur(s.gains_bruts):'—'}</b></span>
      <span>Pertes<b class="neg">${s.regles?eur(-s.pertes_brutes):'—'}</b></span></div></details></article></div></details>`;
}
