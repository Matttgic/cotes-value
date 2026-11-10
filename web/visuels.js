// Petits visuels locaux : uniquement les valeurs observées, jamais une projection.
const nomsSports={football:'Football',basket:'Basket',tennis:'Tennis',hockey:'Hockey',volley:'Volley',handball:'Handball',rugby:'Rugby',football_americain:'Foot US',baseball:'Baseball'};
// Pastilles « meilleur » d'une stratégie : ROI (étoile), gain net (euro), réussite (trèfle), CLV (cible).
// Une seule gagnante par critère, parmi les stratégies d'au moins 50 paris réglés sur la période affichée.
const MEDAILLES_MIN_PARIS=50;
const MEDAILLES=[
  {cle:'roi',nom:'Meilleur ROI',valeur:r=>r.stats.roi,
    dessin:'<path d="M8 1.4l1.9 4.2 4.5.5-3.4 3 1 4.5L8 11.4l-4 2.2 1-4.5-3.4-3 4.5-.5z" fill="currentColor"/>'},
  {cle:'gain',nom:'Meilleur gain net',valeur:r=>r.stats.gain,
    dessin:'<circle cx="8" cy="8" r="6.4" fill="none" stroke="currentColor" stroke-width="1.4"/><text x="8" y="11.2" text-anchor="middle" font-size="9" font-weight="700" fill="currentColor">€</text>'},
  {cle:'reussite',nom:'Meilleure réussite',valeur:r=>r.reussite,
    dessin:'<g fill="currentColor"><circle cx="8" cy="4.3" r="2.9"/><circle cx="4.3" cy="8" r="2.9"/><circle cx="11.7" cy="8" r="2.9"/><circle cx="8" cy="11.7" r="2.9"/></g><path d="M8 11.5c0 2-.8 3-2.4 3.6" fill="none" stroke="currentColor" stroke-width="1.4"/>'},
  {cle:'clv',nom:'Meilleure CLV',valeur:r=>r.stats.clv,
    dessin:'<g fill="none" stroke="currentColor" stroke-width="1.4"><circle cx="8" cy="8" r="6.4"/><circle cx="8" cy="8" r="3.2"/></g><circle cx="8" cy="8" r="1" fill="currentColor"/>'}
];
function attribuerMedailles(rows) {
  for(const r of rows) r.medailles=[];
  const eligibles=rows.filter(r=>r.stats && r.stats.regles>=MEDAILLES_MIN_PARIS);
  for(const m of MEDAILLES) {
    let meilleure=null,max=-Infinity;
    for(const r of eligibles) {const v=m.valeur(r);if(Number.isFinite(v) && v>max){max=v;meilleure=r;}}
    if(meilleure) meilleure.medailles.push(m.cle);
  }
}
// Score « valeur » : réunit ROI et CLV. Rang moyen d'une stratégie au ROI et à la CLV (1 = meilleure), parmi celles
// qui ont au moins VALEUR_MIN_REGLES paris réglés et VALEUR_MIN_CLV CLV mesurées. Le ROI dit ce qui a été gagné,
// la CLV si les cotes prises battaient la clôture (moins sensible à la chance) : une stratégie n'est en tête que si
// elle est bonne sur les deux. r.valeur = rang moyen (plus petit = meilleur), null si la stratégie n'est pas classée.
const VALEUR_MIN_REGLES=30, VALEUR_MIN_CLV=20;
function attribuerValeur(rows) {
  for(const r of rows) r.valeur=null;
  const ok=rows.filter(r=>r.stats && r.stats.regles>=VALEUR_MIN_REGLES && (r.stats.clv_n||0)>=VALEUR_MIN_CLV
    && Number.isFinite(r.stats.roi) && Number.isFinite(r.stats.clv));
  const rang=cle=>{
    const tries=[...ok].sort((a,b)=>b.stats[cle]-a.stats[cle]);
    const out=new Map();
    tries.forEach((r,i)=>{                       // ex aequo : même rang
      const precedent=i && tries[i-1].stats[cle]===r.stats[cle] ? out.get(tries[i-1]) : i+1;
      out.set(r,precedent);
    });
    return out;
  };
  const roi=rang('roi'),clv=rang('clv');
  for(const r of ok) {r.rang_roi=roi.get(r);r.rang_clv=clv.get(r);r.valeur=(r.rang_roi+r.rang_clv)/2;}
  return ok;
}
function classerParValeur(rows) {
  return rows.filter(r=>r.valeur!=null).sort((a,b)=>a.valeur-b.valeur || b.stats.clv-a.stats.clv || b.stats.roi-a.stats.roi);
}
// Classement par la note /100 déjà calculée (cotes/notation.py). Sans note : en dernier.
// À égalité : plus de paris réglés, puis le nom, puis l'ordre d'origine (tri stable).
function noteStrategie(r) {
  const n=r && r.stats && r.stats.note && r.stats.note.total;
  return typeof n==='number' && Number.isFinite(n) ? n : null;
}
function classerParNote(rows) {
  return rows.map((r,i)=>({r,i})).sort((a,b)=>{
    const na=noteStrategie(a.r), nb=noteStrategie(b.r);
    if(na==null && nb!=null) return 1;
    if(na!=null && nb==null) return -1;
    if(na!=null && nb!=null && na!==nb) return nb-na;
    const dr=(Number(b.r.stats&&b.r.stats.regles)||0)-(Number(a.r.stats&&a.r.stats.regles)||0);
    if(dr) return dr;
    const cn=(a.r.nom||'').toLocaleLowerCase('fr').localeCompare((b.r.nom||'').toLocaleLowerCase('fr'),'fr');
    return cn || a.i-b.i;
  }).map(x=>x.r);
}
function panneauAnalyste(r) {
  const avis=r && r.stats && r.stats.avis;
  if(!avis || !avis.verdict) {
    if(r && r.avisSuivi) return '<aside class="avis-analyste" aria-label="Avis d\'analyste"><p class="avis-kicker">Avis d\'analyste</p><p class="aide">Calculé sur tout le suivi, pas sur les dates affichées.</p></aside>';
    return '';
  }
  const d=avis.details||{}, ton=avis.verdict==='Fiable'?'pos':avis.verdict==='Chance ou yo-yo'?'neg':avis.verdict==='Trop tôt pour juger'?'doux':'';
  const nb=x=>x==null||!Number.isFinite(Number(x))?'—':String(x).replace('.',',');
  const ratio=x=>x==null||!Number.isFinite(Number(x))?'—':(100*x).toFixed(1).replace('.',',')+' %';
  const pVal=p=>{if(p==null||!Number.isFinite(Number(p))) return '—'; if(p>0 && p<0.001) return '< 0,001'; return Number(p).toFixed(3).replace('.',',');};
  const dec=x=>x==null||!Number.isFinite(Number(x))?'—':Number(x).toFixed(2).replace('.',',');
  const retour=d.drawdown_recupere===false?'pas encore rattrapé'
    :(d.drawdown_paris==null?'—':d.drawdown_paris+' paris'+(d.drawdown_jours==null?'':' · '+nb(d.drawdown_jours)+' jours'));
  const lignes=[
    ['Paris réglés', nb(d.paris_regles)],
    ['Gain net', d.gain==null?'—':eur(d.gain)],
    ['ROI', pct(d.roi)],
    ['Probabilité que le profit soit du hasard', ratio(d.proba_chance)],
    ['Tirages bootstrap', (d.tirages??'—')+' · graine '+(d.graine??'—')],
    ['CLV moyenne', pct(d.clv_moyenne)],
    ['CLV mesurées', nb(d.clv_n)],
    ['p du t-test (CLV > 0)', pVal(d.pvalue_clv)],
    ['Repli maximal', d.drawdown_max==null?'—':eur(-Math.abs(d.drawdown_max))],
    ['Retour au plus haut', retour],
    ['Régularité (R²)', dec(d.r2)],
    ['Moyenne / écart-type par pari', dec(d.sharpe)],
    ['ROI première moitié', pct(d.roi_premiere)],
    ['ROI seconde moitié', pct(d.roi_seconde)],
    ['Même signe sur les deux moitiés', d.memes_signe==null?'—':(d.memes_signe?'oui':'non')],
    ['ROI sans le top 5 % des cotes gagnantes', pct(d.roi_sans_cotes)],
    ['ROI sans les 3 plus gros gains', pct(d.roi_sans_gains)],
    ['Dépend de quelques grosses cotes', d.depend_grosses_cotes?'oui':'non']
  ];
  const raisons=(avis.raisons||[]).slice(0,3).map(t=>'<li>'+e(t)+'</li>').join('');
  return '<aside class="avis-analyste" aria-label="Avis d\'analyste"><p class="avis-kicker">Avis d\'analyste</p>'
    +'<p class="avis-verdict '+ton+'">'+e(avis.verdict)+'</p><ul class="avis-raisons">'+raisons+'</ul>'
    +'<details class="avis-details"><summary>Détails</summary><dl class="avis-nombres">'
    +lignes.map(([k,v])=>'<dt>'+e(k)+'</dt><dd>'+e(v)+'</dd>').join('')+'</dl></details></aside>';
}
function pastillesMedailles(cles) {
  const pastilles=MEDAILLES.filter(m=>(cles || []).includes(m.cle)).map(m=>{
    const titre=`${m.nom} (${MEDAILLES_MIN_PARIS} paris réglés minimum)`;
    return `<span class="medaille" role="img" aria-label="${titre}" title="${titre}"><svg viewBox="0 0 16 16" aria-hidden="true">${m.dessin}</svg></span>`;
  });
  return pastilles.length ? `<span class="medailles">${pastilles.join('')}</span>` : '';
}
// Ligne témoin des courbes : le gain attendu si les cotes justes sont exactes (mise × (cote / cote juste − 1), cumulé),
// et autour, la marge du hasard (80 % des cas : ± 1,28 écart type). Points : [instant (s), réel, attendu, écart type].
const Z_TEMOIN=1.2816;
const avecTemoin=pts=>pts.length>0 && pts.every(p=>Number.isFinite(p[2]));
const margeTemoin=p=>Number.isFinite(p[3])?Z_TEMOIN*p[3]:0;
// Points d'une liste de paris réglés (fiches du site) : même calcul que le serveur (cotes/laboratoire.py, courbe).
// `poids(p)` : nombre de mises du pari (1 par défaut).
function pointsDepuisParis(liste, poids=()=>1) {
  const regles=(liste || []).filter(p=>Number.isFinite(p.gain) && p.regle_le && Number.isFinite(Date.parse(p.regle_le)))
    .sort((a,b)=>Date.parse(a.regle_le)-Date.parse(b.regle_le));
  let reel=0,attendu=0,variance=0;
  return regles.map(p=>{
    const w=poids(p),mise=Number.isFinite(p.mise)&&p.mise>0?p.mise:10,c=p.cote,j=p.cote_juste;
    reel+=w*p.gain;
    if(Number.isFinite(c) && c>1) {
      const ok=Number.isFinite(j) && j>1,q=ok?1/j:1/c;
      if(ok) attendu+=w*mise*(c/j-1);
      variance+=w*w*(mise*c)**2*q*(1-q);
    }
    return [Math.floor(Date.parse(p.regle_le)/1000),Math.round(reel*100)/100,Math.round(attendu*100)/100,Math.round(Math.sqrt(variance)*100)/100];
  });
}
// Verdict lisible sous un graphique : réel, attendu et sa marge, puis conforme / au-dessus / en dessous.
function verdictTemoin(points) {
  const pts=(points || []).filter(p=>Number.isFinite(p[1]));
  if(!avecTemoin(pts)) return '';
  const d=pts.at(-1),ecart=d[1]-d[2],marge=margeTemoin(d);
  const euros=v=>(v>0?'+':'')+Math.round(v)+' €',classe=v=>v>0?'pos':v<0?'neg':'';
  const [mot,c]=Math.abs(ecart)<=marge?['Conforme à l’attendu','']:ecart>0?['Au-dessus de l’attendu','pos']:['En dessous de l’attendu','neg'];
  return `<p class="temoin"><span><i class="temoin-reel"></i>Réel <b class="${classe(d[1])}">${euros(d[1])}</b></span>`+
    `<span><i class="temoin-attendu"></i>Attendu <b>${euros(d[2])}</b> <small>± ${Math.round(marge)} € de hasard</small></span>`+
    `<b class="temoin-mot ${c}">${mot}</b></p>`;
}
function miniCourbe(points, couleur='var(--accent)') {
  const pts=(points || []).filter(p=>Number.isFinite(p[0]) && Number.isFinite(p[1]));
  if (!pts.length) return '<span class="courbe-absente">Courbe indisponible</span>';
  const W=150,H=52,m=4,temoin=avecTemoin(pts);
  const t0=pts[0][0],t1=pts.at(-1)[0],x=t=>m+(t-t0)/(t1-t0 || 1)*(W-2*m);
  const vals=pts.flatMap(p=>temoin?[p[1],p[2]]:[p[1]]);
  const lo=Math.min(0,...vals),hi=Math.max(0,...vals);
  const y=g=>H-m-(g-lo)/(hi-lo || 1)*(H-2*m);
  let path=`M ${m} ${y(0)}`;
  for(const [t,g] of pts) path+=` H ${x(t)} V ${y(g)}`;
  const attendu=temoin?`<path d="M ${m} ${y(0)} ${pts.map(p=>`L ${x(p[0])} ${y(p[2])}`).join(' ')}" fill="none" stroke="var(--attendu)" stroke-width="1.5" stroke-dasharray="4 3" vector-effect="non-scaling-stroke"/>`:'';
  return `<svg class="mini-courbe" viewBox="0 0 ${W} ${H}" role="img" aria-label="Gain cumulé : ${pts.length} règlements, échelle propre à la stratégie${temoin?', pointillés : attendu':''}">
    <line x1="${m}" x2="${W-m}" y1="${y(0)}" y2="${y(0)}" stroke="var(--ligne)" stroke-dasharray="3 3"/>${attendu}
    <path d="${path}" fill="none" stroke="${e(couleur)}" stroke-width="2" vector-effect="non-scaling-stroke"/>
    <circle cx="${x(pts.at(-1)[0])}" cy="${y(pts.at(-1)[1])}" r="2.5" fill="${e(couleur)}"/>
    <title>Gain cumulé observé · échelle propre · ${pts.length} règlements${temoin?' · pointillés : gain attendu':''}</title></svg>`;
}
// Courbe lisible d'une stratégie : gain cumulé en euros, avec zéro, extrêmes et dates ; ligne témoin (attendu, en
// pointillés) et marge du hasard (zone grisée) quand les points les portent, puis le verdict.
function grandeCourbe(points, couleur='var(--accent)') {
  const pts=(points || []).filter(p=>Number.isFinite(p[0]) && Number.isFinite(p[1]));
  if (pts.length<2) return '<span class="courbe-absente">Courbe disponible après deux règlements</span>';
  const temoin=avecTemoin(pts);
  const vals=pts.flatMap(p=>temoin?[p[1],p[2]+margeTemoin(p),p[2]-margeTemoin(p)]:[p[1]]);
  const lo=Math.min(0,...vals),hi=Math.max(0,...vals);
  const euros=v=>(v>0?'+':'')+Math.round(v)+' €';
  // Marge gauche à la taille des montants (« +4949 € » n'est plus coupé).
  const W=320,H=150,g=Math.max(44,Math.ceil(8+6.2*Math.max(...[hi,lo].map(v=>euros(v).length)))),d=8,h=10,b=20;
  const t0=pts[0][0],t1=pts.at(-1)[0],x=t=>g+(t-t0)/(t1-t0 || 1)*(W-g-d);
  const y=v=>H-b-(v-lo)/(hi-lo || 1)*(H-b-h);
  let path=`M ${g} ${y(0)}`;
  for(const [t,v] of pts) path+=` H ${x(t).toFixed(1)} V ${y(v).toFixed(1)}`;
  const jour=t=>new Date(t*1000).toLocaleDateString('fr-FR',{timeZone:'Europe/Paris',day:'numeric',month:'short'});
  const graduations=[...new Set([hi,0,lo])].map(v=>`<line x1="${g}" x2="${W-d}" y1="${y(v)}" y2="${y(v)}" stroke="var(--ligne)"${v?'':' stroke-dasharray="3 3"'}/>
    <text x="${g-4}" y="${y(v)+3}" text-anchor="end">${euros(v)}</text>`).join('');
  const ligne=f=>pts.map(p=>`L ${x(p[0]).toFixed(1)} ${y(f(p)).toFixed(1)}`).join(' ');
  const bande=temoin?`<path class="temoin-bande" d="M ${g} ${y(0)} ${ligne(p=>p[2]+margeTemoin(p))} ${[...pts].reverse().map(p=>`L ${x(p[0]).toFixed(1)} ${y(p[2]-margeTemoin(p)).toFixed(1)}`).join(' ')} Z" fill="var(--attendu)" fill-opacity=".16" stroke="none"/>`:'';
  const attendu=temoin?`<path d="M ${g} ${y(0)} ${ligne(p=>p[2])}" fill="none" stroke="var(--attendu)" stroke-width="1.6" stroke-dasharray="5 4"/>`:'';
  return `<svg class="grande-courbe" viewBox="0 0 ${W} ${H}" role="img" aria-label="Gain cumulé : ${euros(pts.at(-1)[1])} après ${pts.length} règlements${temoin?`, attendu ${euros(pts.at(-1)[2])}`:''}">
    ${graduations}${bande}${attendu}<path d="${path}" fill="none" stroke="${e(couleur)}" stroke-width="2"/>
    <circle cx="${x(pts.at(-1)[0])}" cy="${y(pts.at(-1)[1])}" r="3.5" fill="${e(couleur)}"/>
    <text x="${g}" y="${H-4}">${jour(t0)}</text><text x="${W-d}" y="${H-4}" text-anchor="end">${jour(t1)}</text></svg>${verdictTemoin(pts)}`;
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
// Mise moyenne par pari réglé : montrée seulement en mise Kelly ¼ (en 10 € fixes, chaque pari vaut 10 €).
function miseMoyenne(s) {
  if(typeof miseMode==='undefined' || miseMode!=='kelly' || !s.regles || !Number.isFinite(s.mise)) return '';
  const moyenne=(s.mise/s.regles).toLocaleString('fr-FR',{minimumFractionDigits:2,maximumFractionDigits:2});
  return `<div class="mise-moyenne"><dt>Mise moyenne</dt><dd>${moyenne} €</dd><small>Kelly ¼ · sur ${s.regles} réglés</small></div>`;
}
function carteStrategieVisuelle(r, points, couleur='var(--accent)') {
  const s=r.stats,pp=x=>pct(x==null?null:x/100);
  return `<details class="ligne-detail ligne-strategie" id="strategie-${e(encodeURIComponent(r.id))}"><summary>
    <span class="ligne-nom" title="${e(r.nom+' · '+r.detail)}">${e(r.nomCourt || r.nom)}${s.note?` <b class="note-mini" title="Note /100">${s.note.total}</b>`:''}</span>${pastillesMedailles(r.medailles)}${(typeof D!=='undefined'&&(D.pauses?.liste||{})[r.id])?' <small class="badge-pause neg">⏸</small>':''}<span class="ligne-volume" aria-label="${s.regles} paris réglés, ${s.evenements_regles ?? "inconnu"} matchs">${s.regles}<small>${s.evenements_regles ?? "—"} matchs</small></span>
    <span class="ligne-roi ${signe(s.roi)}">${pp(s.roi)}</span><b class="ligne-valeur ${signe(s.gain)}">${s.regles?eur(s.gain):'—'}</b></summary>
    <div class="ligne-corps"><article class="strategie-ligne strategie-visuelle" style="--identite:${e(couleur)}">
    <div class="strategie-entete"><div class="strategie-identite"><h3>${e(r.nom)}</h3></div>
    <button class="btn secondaire" data-strategie="${e(r.id)}" aria-label="Voir les paris de ${e(r.nom)}">Les paris <span aria-hidden="true">↗</span></button></div>
    <p class="strategie-regle">${e(r.detail)}</p>${typeof etiquettesStrategie==='function'?etiquettesStrategie(r):''}
    <div class="strategie-apercu"><div><span class="libelle-gain">Gain net simulé</span><strong class="${signe(s.gain)}">${s.regles?eur(s.gain):'—'}</strong></div>${s.note?`<div><span class="libelle-gain">Note</span><strong class="${s.note.total>=70?'pos':s.note.total<40?'neg':''}">${s.note.total}/100</strong><small>${s.note.provisoire?'provisoire · ':''}${typeof sousNotes==='function'?sousNotes(s.note):''}</small>${typeof evolutionNote==='function'?evolutionNote(r.id,s.note.total):''}</div>`:''}</div>
    <div class="strategie-lecture"><div class="strategie-trajectoire">${grandeCourbe(points,couleur)}<span>Gain cumulé par date de règlement · pointillés : gain attendu si les cotes justes sont exactes · zone grisée : marge du hasard (8 fois sur 10)</span></div>${panneauAnalyste(r)}</div>
    <dl class="strat-chiffres">
      <div><dt>ROI</dt><dd class="${signe(s.roi)}">${pp(s.roi)}</dd><small>${r.reussite==null?'—':r.reussite.toFixed(1).replace('.',',')+' %'} de réussite</small></div>
      <div><dt>CLV moyenne</dt><dd class="${signe(s.clv)}">${pp(s.clv)}</dd>${couvertureCLV(s)}<small>Par match <b class="${signe(s.clv_evenement)}">${pp(s.clv_evenement)}</b> · ${s.clv_evenements_n ?? 0}/${s.evenements_regles ?? "—"} mesurés</small></div>
      <div><dt>Paris réglés</dt><dd>${s.regles} <small>(${s.evenements_regles ?? "—"} matchs)</small></dd><small>${s.paris} prises · ${s.attente} en attente</small></div>
      ${miseMoyenne(s)}
    </dl>${repartitionResultats(s)}
    <details><summary>Règles et détail des résultats</summary><p>${e(r.detail)}</p>
      <div class="strat-secondaires"><span>Gains bruts<b class="pos">${s.regles?eur(s.gains_bruts):'—'}</b></span>
      <span>Pertes<b class="neg">${s.regles?eur(-s.pertes_brutes):'—'}</b></span></div></details></article></div></details>`;
}
