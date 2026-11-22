// Habillage « marché boursier » : tableau de cotation façon terminal, séance ouverte ou close, chiffres qui
// clignotent depuis la dernière visite, tendance 30 jours des stratégies, carte de chaleur sport × bookmaker et
// séances hebdomadaires en chandeliers. Lecture seule des données déjà chargées : rien n'est calculé côté serveur.

// Symbole boursier d'un match : trois lettres par équipe, sans accents (« OLOMOUC – LIBEREC » → « OLO-LIB »).
function symboleMatch(p) {
  const trois=t=>String(t || '?').normalize('NFD').replace(/[̀-ͯ]/g,'').replace(/[^A-Za-z0-9]/g,'').slice(0,3).toUpperCase() || '?';
  return `${trois(p.domicile)}-${trois(p.exterieur)}`;
}

// Tableau de cotation : les paris en cours triés par écart de value, les paris « à jouer » marqués ●.
function tableauCotation(enCours, jouer) {
  const zone=document.getElementById('acc-cotation');if(!zone) return;
  const aJouer=new Set(jouer.map(x=>x.p.id));
  const lignes=[...enCours].filter(p=>Number.isFinite(p.ecart)).sort((a,b)=>b.ecart-a.ecart).slice(0,10);
  if(!lignes.length){zone.innerHTML='';zone.hidden=true;return;}
  zone.hidden=false;
  const heure=new Intl.DateTimeFormat('fr-FR',{timeZone:'Europe/Paris',hour:'2-digit',minute:'2-digit'}).format(new Date());
  zone.innerHTML=`<div class="cv-terminal-tete"><b>Cotes en cours</b><span>${enCours.length} en cours · ● à jouer · ${heure}</span></div>
<div class="cv-terminal-ligne cv-terminal-entete" aria-hidden="true"><span>Match</span><span>Pari</span><span>Book</span><span>Cote</span><span>Juste</span><span>Écart</span></div>
${lignes.map(p=>{const j=aJouer.has(p.id),c=p.ecart>0?'pos':p.ecart<0?'neg':'';
  return `<div class="cv-terminal-ligne${j?' cv-a-jouer':''}" title="${e(p.domicile)} – ${e(p.exterieur)} · ${e(p.pari)}"><span class="cv-symb">${j?'● ':''}${e(symboleMatch(p))}</span>`
  +`<span class="cv-pari">${e(p.pari)}</span><span class="cv-book">${e(String(p.bookmaker || '').slice(0,3).toUpperCase())}</span>`
  +`<b>${cote(p.cote)}</b><span>${cote(p.cote_juste)}</span><i class="${c}">${p.ecart>0?'▲':p.ecart<0?'▼':''} ${pct(p.ecart)}</i></div>`;}).join('')}`;
}

// Séance ouverte tant qu'un pari en cours n'a pas commencé ; clôture sinon.
function etatSeance(enCours, maintenant=Date.now()) {
  const avenir=enCours.filter(p=>Date.parse(p.debut)>maintenant).length;
  return avenir ? {ouverte:true,texte:`Séance ouverte · ${avenir} match${avenir>1?'s':''} à venir`} : {ouverte:false,texte:'Clôture · aucun match à venir'};
}
function afficherSeance(enCours) {
  const date=document.getElementById('une-date');if(!date) return;
  const s=etatSeance(enCours);
  let b=document.getElementById('une-seance');
  if(!b){b=document.createElement('span');b.id='une-seance';date.after(b);}
  b.className='cv-seance'+(s.ouverte?' ouverte':'');b.textContent=s.texte;
}

// Chiffres clés comparés à ceux de la visite précédente sur cet appareil (même mise, même bankroll) : flèche et
// clignotement vert ou rouge s'ils ont bougé. La mémoire est lue une seule fois, à l'ouverture de la page.
const CLE_VUS='cv-chiffres-vus-v1';
const chiffresVisitePrecedente=(()=>{try{return JSON.parse(localStorage.getItem(CLE_VUS) || '{}');}catch{return {};}})();
function comparerChiffres(cle, valeurs) {
  const avant=chiffresVisitePrecedente[cle] || {}, vus={...chiffresVisitePrecedente};
  vus[cle]=valeurs;
  try{localStorage.setItem(CLE_VUS,JSON.stringify(vus));}catch{}
  const out={};
  for(const [k,v] of Object.entries(valeurs)) if(Number.isFinite(v) && Number.isFinite(avant[k]) && Math.abs(v-avant[k])>1e-9) out[k]=v-avant[k];
  return out;
}

// Tendance des 30 derniers jours d'une stratégie : petite courbe verte si elle monte, rouge si elle baisse.
function tendance30(points, maintenant=Date.now()) {
  const pts=(points || []).filter(p=>Number.isFinite(p[0]) && Number.isFinite(p[1]));
  if(pts.length<2) return '';
  const debut=maintenant/1000-30*86400, avant=pts.filter(p=>p[0]<debut).at(-1), dans=pts.filter(p=>p[0]>=debut);
  if(!dans.length) return '';
  const serie=[[debut,avant?avant[1]:0],...dans.map(p=>[p[0],p[1]])];
  const W=56,H=16,lo=Math.min(...serie.map(p=>p[1])),hi=Math.max(...serie.map(p=>p[1]));
  const x=t=>1+(t-debut)/(maintenant/1000-debut || 1)*(W-2), y=v=>H-1-(v-lo)/(hi-lo || 1)*(H-2);
  const delta=serie.at(-1)[1]-serie[0][1], c=delta>0?'pos':delta<0?'neg':'';
  return `<svg class="cv-tendance ${c}" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="30 jours : ${eur(delta)}"><polyline fill="none" stroke="currentColor" stroke-width="1.3" vector-effect="non-scaling-stroke" points="${serie.map(p=>`${x(p[0]).toFixed(1)},${y(p[1]).toFixed(1)}`).join(' ')}"/></svg>`;
}

// Carte de chaleur : ROI par sport (lignes) et bookmaker (colonnes). Moins de 20 paris : case grisée, sans couleur.
function carteChaleur(L) {
  const zone=document.getElementById('bu-chaleur');if(!zone) return;
  const compte=(cle)=>{const m=new Map();for(const p of L){const k=cle(p);m.set(k,(m.get(k) || 0)+1);}return [...m].sort((a,b)=>b[1]-a[1]).map(x=>x[0]);};
  const sports=compte(p=>p.sport).slice(0,6), books=compte(p=>p.bookmaker).slice(0,6);
  if(!sports.length || !books.length){zone.innerHTML='<p class="aide">Aucun pari réglé sur cette période.</p>';return;}
  const cases=sports.map(sp=>books.map(b=>statsBU(L.filter(p=>p.sport===sp && p.bookmaker===b))));
  const fond=s=>{
    if(s.n<20 || !Number.isFinite(s.roi)) return '';
    const force=Math.round(12+Math.min(1,Math.abs(s.roi)/0.2)*48);
    return ` style="background:color-mix(in srgb, var(${s.roi>=0?'--vert':'--rouge'}) ${force}%, transparent)"`;
  };
  zone.style.setProperty('--cv-colonnes',books.length);
  zone.innerHTML=`<div class="cv-chaleur" role="table" aria-label="ROI par sport et bookmaker"><span class="cv-chaleur-coin" role="columnheader"></span>${
    books.map(b=>`<span class="cv-chaleur-tete" role="columnheader">${e(String(b).slice(0,7))}</span>`).join('')}${
    sports.map((sp,i)=>`<span class="cv-chaleur-sport" role="rowheader">${e(nomSport(sp))}</span>${cases[i].map((s,j)=>
      `<span class="cv-case${s.n<20?' cv-peu':''}" role="cell"${fond(s)} title="${e(nomSport(sp))} · ${e(books[j])} : ${s.n} paris${s.n?', ROI '+pct(s.roi)+', '+eurC(s.net):''}">${
        s.n<20?'<small>'+(s.n || '·')+'</small>':`<b>${pct(s.roi)}</b><small>${s.n}</small>`}</span>`).join('')}`).join('')}</div>
<p class="aide">Couleur : ROI, plus foncé jusqu'à ±20 %. Grisé : moins de 20 paris, trop peu pour juger. Chiffre du bas : nombre de paris.</p>`;
}

// Séances hebdomadaires : un chandelier par semaine (lundi–dimanche, heure de Paris) sur le gain cumulé.
// Ouverture = gain cumulé à la fin de la semaine précédente, clôture = fin de semaine, mèches = plus haut et plus bas.
function bougiesHebdo(points, largeur=0) {
  const pts=(points || []).filter(p=>Number.isFinite(p[0]) && Number.isFinite(p[1]));
  if(pts.length<2) return '<span class="courbe-absente">Chandeliers disponibles après deux règlements</span>';
  const lundi=t=>{const d=new Date(new Date(t*1000).toLocaleString('en-US',{timeZone:'Europe/Paris'}));d.setHours(0,0,0,0);d.setDate(d.getDate()-((d.getDay()+6)%7));return d.getTime();};
  const semaines=[];let precedent=0;
  for(const [t,v] of pts){
    const k=lundi(t);let s=semaines.at(-1);
    if(!s || s.k!==k){s={k,o:precedent,h:precedent,l:precedent,c:precedent};semaines.push(s);}
    s.c=v;s.h=Math.max(s.h,v);s.l=Math.min(s.l,v);precedent=v;
  }
  const S=semaines.slice(-16),lo=Math.min(0,...S.map(s=>s.l)),hi=Math.max(0,...S.map(s=>s.h));
  const euros=v=>{v=visuelBankroll(v);return (v>0?'+':'')+Math.round(v)+' €';};
  const {W,H}=dimensionsCourbe(largeur),g=Math.max(48,Math.ceil(8+6.6*Math.max(euros(hi).length,euros(lo).length))),d=8,h=12,b=24;
  const pas=(W-g-d)/S.length,larg=Math.max(3,Math.min(14,pas*.6));
  const y=v=>H-b-(v-lo)/(hi-lo || 1)*(H-b-h);
  const jour=k=>new Date(k).toLocaleDateString('fr-FR',{day:'numeric',month:'short'});
  const corps=S.map((s,i)=>{
    const x=g+pas*(i+.5),c=s.c>=s.o?'pos':'neg',top=y(Math.max(s.o,s.c)),haut=Math.max(1,Math.abs(y(s.o)-y(s.c)));
    return `<g class="cv-bougie ${c}"><title>Semaine du ${jour(s.k)} : ${euros(s.c-s.o)} (ouverture ${euros(s.o)}, clôture ${euros(s.c)})</title>`
      +`<line x1="${x.toFixed(1)}" x2="${x.toFixed(1)}" y1="${y(s.h).toFixed(1)}" y2="${y(s.l).toFixed(1)}"/>`
      +`<rect x="${(x-larg/2).toFixed(1)}" y="${top.toFixed(1)}" width="${larg.toFixed(1)}" height="${haut.toFixed(1)}"/></g>`;
  }).join('');
  const hausse=S.filter(s=>s.c>=s.o).length;
  return `<svg class="grande-courbe cv-bougies" viewBox="0 0 ${W} ${H}" style="max-width:${W}px" role="img" aria-label="${S.length} semaines : ${hausse} en hausse, ${S.length-hausse} en baisse">
    <line x1="${g}" x2="${W-d}" y1="${y(0)}" y2="${y(0)}" stroke="var(--ligne)" stroke-dasharray="3 3"/>
    <text x="${g-4}" y="${y(hi)+3}" text-anchor="end">${euros(hi)}</text>${Math.abs(y(lo)-y(hi))>=12 && lo!==hi?`<text x="${g-4}" y="${y(lo)+3}" text-anchor="end">${euros(lo)}</text>`:''}
    ${corps}<text x="${g}" y="${H-6}">${jour(S[0].k)}</text><text x="${W-d}" y="${H-6}" text-anchor="end">${jour(S.at(-1).k)}</text></svg>
<p class="temoin"><span><b class="pos">${hausse}</b> semaine${hausse>1?'s':''} en hausse</span><span><b class="neg">${S.length-hausse}</b> en baisse</span></p>`;
}
