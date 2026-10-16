// Lecture des données existantes uniquement. Aucune sélection ni aucun règlement modifié.
const ETATS_ANALYSE=['gagne','demi_gagne','perdu','demi_perdu','rembourse'];
const COULEURS_ANALYSE=['var(--accent)','#b24a76','#b27b24','#64748b','#8472bd'];
const HEURE_SUIVI_ANALYSE=Date.parse('2026-10-14T14:00:00+02:00');
function instantAnalyse(s) {const t=Date.parse(s);return Number.isFinite(t)?t:null;}
function jourAnalyse(s) {return instantAnalyse(s)==null?'':new Intl.DateTimeFormat('fr-CA',{timeZone:'Europe/Paris',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(s));}
function courtAnalyse(s) {const [a,m,j]=String(s).split('-');return j?j+'/'+m:s;}
function gainAnalyse(p) {
  if(!ETATS_ANALYSE.includes(p.statut)) return null;
  if(Number.isFinite(p.gain)) return p.gain;
  const mise=Number.isFinite(p.mise)?p.mise:10,c=Number(p.cote);
  if(!(c>1)) return null;
  return Math.round(100*(p.statut==='gagne'?mise*(c-1):p.statut==='demi_gagne'?mise*(c-1)/2:p.statut==='perdu'?-mise:p.statut==='demi_perdu'?-mise/2:0))/100;
}
function lignesAnalyse(d, toutes, filtre) {
  const periode=filtre.periode || 'futur', nav=d.laboratoire?.navigation;
  let rows;
  if(filtre.selection && filtre.selection!=='uniques') {
    const ids=nav?.selections?.[filtre.selection] || {};
    const liste=periode==='tout'?[...new Set([...(ids.ensemble || []),...(ids.futur || [])])]:ids[periode] || [];
    const index=new Map(toutes.map(p=>[p.id,p]));
    rows=liste.map(id=>index.get(id) || nav?.paris?.[id]).filter(Boolean);
  } else {
    rows=toutes.filter(p=>p.unique_bilan===true);
    if(periode==='futur') rows=rows.filter(p=>(instantAnalyse(p.detecte)??-Infinity)>=HEURE_SUIVI_ANALYSE);
    if(periode==='ensemble') {
      const debut=Date.parse('2026-10-07T00:00:00+02:00'),fin=Date.parse('2026-10-14T00:00:00+02:00');
      const cutoff=instantAnalyse(d.laboratoire?.releve);
      rows=rows.filter(p=>instantAnalyse(p.debut)>=debut && instantAnalyse(p.debut)<fin && cutoff!=null && instantAnalyse(p.detecte)!=null && instantAnalyse(p.detecte)<=cutoff);
    }
  }
  if(periode==='ensemble') {
    const cutoff=instantAnalyse(d.laboratoire?.releve);
    rows=rows.map(p=>{
      const t=instantAnalyse(p.regle_le),detecte=instantAnalyse(p.detecte);
      return cutoff!=null && t!=null && detecte!=null && detecte<=t && t<cutoff?p:{...p,statut:'en_cours',gain:null,clv:null};
    });
  }
  return rows.filter(p=>(!filtre.sport || p.sport===filtre.sport) && (!filtre.book || p.bookmaker===filtre.book));
}
function statsAnalyse(rows) {
  const regles=rows.filter(p=>ETATS_ANALYSE.includes(p.statut));
  const connus=regles.filter(p=>gainAnalyse(p)!=null), cs=regles.filter(p=>Number.isFinite(p.clv));
  const mises=connus.reduce((n,p)=>n+(Number.isFinite(p.mise)?p.mise:10),0);
  const gain=connus.reduce((n,p)=>n+gainAnalyse(p),0);
  const ordre=[...connus].sort((a,b)=>(instantAnalyse(a.regle_le || a.debut || a.detecte)??0)-(instantAnalyse(b.regle_le || b.debut || b.detecte)??0) || String(a.id).localeCompare(String(b.id)));
  let cumul=0,sommet=0,drawdown=0;
  const courbe=[],replis=[];
  for(const p of ordre) {
    cumul+=gainAnalyse(p);sommet=Math.max(sommet,cumul);drawdown=Math.max(drawdown,sommet-cumul);
    const t=instantAnalyse(p.regle_le || p.debut || p.detecte);
    if(t!=null) {courbe.push([t,cumul]);replis.push([t,cumul-sommet]);}
  }
  return {n:rows.length,regles:regles.length,attente:rows.length-regles.length,connus:connus.length,mises,
    gain:connus.length?gain:null,roi:mises?gain/mises:null,
    reussite:regles.length?regles.filter(p=>['gagne','demi_gagne'].includes(p.statut)).length/regles.length:null,
    clv:cs.length?cs.reduce((n,p)=>n+p.clv,0)/cs.length:null,clv_n:cs.length,
    drawdown:connus.length?drawdown:null,courbe,replis};
}
function groupesAnalyse(rows,champ) {
  const groupes=new Map();
  for(const p of rows) {const k=p[champ] || 'Non renseigné';if(!groupes.has(k)) groupes.set(k,[]);groupes.get(k).push(p);}
  return [...groupes].map(([nom,lignes])=>({nom,...statsAnalyse(lignes)}));
}
function argentAnalyse(v) {return v==null?'—':new Intl.NumberFormat('fr-FR',{style:'currency',currency:'EUR',maximumFractionDigits:2,minimumFractionDigits:0,signDisplay:'exceptZero'}).format(Math.abs(v)<.000001?0:v);}
function tauxAnalyse(v) {return v==null?'—':new Intl.NumberFormat('fr-FR',{style:'percent',maximumFractionDigits:1,signDisplay:'exceptZero'}).format(v);}
function entierAnalyse(v) {return Number(v).toLocaleString('fr-FR');}
function videAnalyse(texte='Aucune donnée sur cette sélection.') {return `<p class="analyse-absence">${e(texte)}</p>`;}
function cadreAnalyse(titre,sousTitre,contenu,large=false) {
  return `<figure class="analyse-figure ${large?'analyse-large':''}"><figcaption><h3>${e(titre)}</h3><p>${e(sousTitre)}</p></figcaption>${contenu}<output class="analyse-survol" aria-live="polite"></output></figure>`;
}
function anneauAnalyse(items,libelle) {
  const positifs=items.filter(x=>x.n>0),total=positifs.reduce((n,x)=>n+x.n,0);
  if(!total) return videAnalyse();
  const r=45,c=2*Math.PI*r;let offset=0;
  const parts=positifs.map((x,i)=>{
    const longueur=c*x.n/total,texte=`${x.nom} : ${x.n} (${(100*x.n/total).toFixed(1).replace('.',',')} %)`;
    const svg=`<circle class="analyse-marque" tabindex="0" data-aide="${e(texte)}" aria-label="${e(texte)}" cx="65" cy="65" r="${r}" fill="none" stroke="${x.couleur || COULEURS_ANALYSE[i%5]}" stroke-width="17" stroke-dasharray="${longueur} ${c-longueur}" stroke-dashoffset="${-offset}" transform="rotate(-90 65 65)"><title>${e(texte)}</title></circle>`;
    offset+=longueur;return svg;
  }).join('');
  return `<div class="analyse-anneau"><svg viewBox="0 0 130 130" role="img" aria-label="${e(libelle)} · ${total} prises">${parts}<text x="65" y="64" text-anchor="middle" class="anneau-total">${total}</text><text x="65" y="79" text-anchor="middle" class="anneau-unite">prises</text></svg><ul class="analyse-legende">${positifs.map((x,i)=>`<li><i style="background:${x.couleur || COULEURS_ANALYSE[i%5]}"></i><span>${e(x.nom)}</span><b>${x.n}</b><small>${Math.round(100*x.n/total)} %</small></li>`).join('')}</ul></div>`;
}
function barresAnalyse(items,champ,format) {
  if(!items.length) return videAnalyse();
  const max=Math.max(...items.map(x=>Math.abs(x[champ] || 0)),0.0001);
  return `<div class="analyse-barres">${items.map(x=>{
    const val=x[champ],largeur=Number.isFinite(val)?Math.abs(val)/max*50:0;
    const contexte=champ==='clv'?`${x.clv_n}/${x.regles} CLV mesurées`:`${x.regles} réglés · ROI ${tauxAnalyse(x.roi)}`;
    const aide=`${x.nom} : ${format(val)} · ${contexte}`;
    return `<div class="analyse-barre" tabindex="0" data-aide="${e(aide)}"><div class="analyse-barre-tete"><span>${e(nomsSports[x.nom] || x.nom)}</span><b class="${val<0?'neg':''}">${e(format(val))}</b></div><div class="analyse-piste"><i style="left:${val<0?50-largeur:50}%;width:${largeur}%;background:${val<0?'var(--graph-neg)':'var(--accent)'}"></i></div><small>${e(contexte)}</small></div>`;
  }).join('')}</div>`;
}
function ligneGraphiqueAnalyse(points,libelle) {
  if(!points.length) return videAnalyse('Le graphique apparaîtra après les premiers règlements datés.');
  const W=380,H=210,g=60,d=12,h=12,b=30;
  const t0=points[0][0],t1=points.at(-1)[0],valeurs=points.map(p=>p[1]);
  let lo=Math.min(0,...valeurs),hi=Math.max(0,...valeurs);
  if(lo===hi) {lo-=10;hi+=10;}
  const step=pas(hi-lo);lo=Math.floor(lo/step)*step;hi=Math.ceil(hi/step)*step;
  const x=t=>g+(t-t0)/(t1-t0 || 1)*(W-g-d),y=v=>h+(hi-v)/(hi-lo)*(H-h-b);
  let path=`M ${g} ${y(0)}`;for(const [t,v] of points) path+=` H ${x(t)} V ${y(v)}`;
  let axes='';for(let v=lo;v<=hi+step/10;v+=step) axes+=`<line x1="${g}" x2="${W-d}" y1="${y(v)}" y2="${y(v)}" stroke="var(--ligne)"/><text x="${g-6}" y="${y(v)+4}" text-anchor="end">${e(argentAnalyse(v))}</text>`;
  const date=t=>new Intl.DateTimeFormat('fr-FR',{timeZone:'Europe/Paris',day:'2-digit',month:'2-digit',...(t1-t0<48*3600000?{hour:'2-digit'}:{})}).format(new Date(t)).replace(' h','h');
  const rep=[t0,t0+(t1-t0)/2,t1].filter((t,i,a)=>a.findIndex(v=>date(v)===date(t))===i);
  axes+=rep.map((t,i)=>`<text x="${x(t)}" y="${H-7}" text-anchor="${i===0?'start':i===rep.length-1?'end':'middle'}">${e(date(t))}</text>`).join('');
  const last=points.at(-1);
  return `<div class="analyse-graph-valeur">${e(argentAnalyse(last[1]))}<small>${e(libelle)}</small></div><svg class="analyse-courbe" viewBox="0 0 ${W} ${H}" role="img" aria-label="${e(libelle)} : ${e(argentAnalyse(last[1]))}, ${points.length} règlements"><title>${e(libelle)} · ${points.length} règlements</title>${axes}<path d="${path}" fill="none" stroke="var(--accent)" stroke-width="2"/><circle cx="${x(last[0])}" cy="${y(last[1])}" r="3" fill="var(--accent)"/></svg>`;
}
function colonnesAnalyse(items,format,libelle) {
  if(!items.length) return videAnalyse();
  const W=380,H=205,g=60,d=10,h=14,b=40,max=Math.max(...items.map(x=>Math.abs(x.valeur)),1),neg=items.some(x=>x.valeur<0);
  const lo=neg?-max:0,hi=max,y=v=>h+(hi-v)/(hi-lo)*(H-h-b),largeur=(W-g-d)/items.length;
  const ticks=neg?[-max,0,max]:[0,max/2,max];
  const axes=ticks.map(v=>`<line x1="${g}" x2="${W-d}" y1="${y(v)}" y2="${y(v)}" stroke="var(--ligne)"/><text x="${g-6}" y="${y(v)+4}" text-anchor="end">${e(format(v))}</text>`).join('');
  const barres=items.map((x,i)=>{
    const px=g+i*largeur+largeur*.12,aide=`${x.nom} : ${format(x.valeur)}${x.detail?' · '+x.detail:''}`;
    const etiquette=items.length<=8 || i===0 || i===items.length-1 || i%Math.ceil(items.length/5)===0;
    return `<g class="analyse-marque" tabindex="0" data-aide="${e(aide)}" aria-label="${e(aide)}"><title>${e(aide)}</title><rect x="${px}" y="${Math.min(y(x.valeur),y(0))}" width="${largeur*.76}" height="${Math.max(1,Math.abs(y(x.valeur)-y(0)))}" fill="${x.valeur<0?'var(--graph-neg)':'var(--accent)'}"/>${etiquette?`<text x="${px+largeur*.38}" y="${H-19}" text-anchor="middle">${e(x.court || x.nom)}</text>`:''}</g>`;
  }).join('');
  return `<svg class="analyse-courbe" viewBox="0 0 ${W} ${H}" role="img" aria-label="${e(libelle)}">${axes}${barres}</svg><details class="analyse-valeurs"><summary>Valeurs exactes</summary><ul>${items.map(x=>`<li><span>${e(x.nom)}</span><b>${e(format(x.valeur))}</b>${x.detail?`<small>${e(x.detail)}</small>`:''}</li>`).join('')}</ul></details>`;
}
function seriesQuotidiennesAnalyse(rows) {
  const jours=new Map();
  for(const p of rows) {
    const g=gainAnalyse(p),j=jourAnalyse(p.regle_le || p.debut || p.detecte);if(g==null || !j) continue;
    const avant=jours.get(j) || {valeur:0,n:0};avant.valeur+=g;avant.n++;jours.set(j,avant);
  }
  const liste=[...jours].sort(([a],[b])=>a.localeCompare(b));
  // Les jours sans règlement apparaissent à zéro, sans inventer de paris.
  if(!liste.length) return [];
  const debut=new Date(liste[0][0]+'T12:00:00Z'),fin=new Date(liste.at(-1)[0]+'T12:00:00Z');
  const nombre=Math.round((fin-debut)/86400000)+1;
  if(nombre<=28) {
    const out=[];
    for(let t=+debut;t<=+fin;t+=86400000) {const j=new Date(t).toISOString().slice(0,10),v=jours.get(j) || {valeur:0,n:0};out.push({nom:j,court:courtAnalyse(j),valeur:v.valeur,detail:v.n+' règlements'});}
    return out;
  }
  const mois=new Map();for(const [j,v] of liste) {const k=j.slice(0,7),a=mois.get(k) || {valeur:0,n:0};a.valeur+=v.valeur;a.n+=v.n;mois.set(k,a);}
  return [...mois].map(([nom,v])=>({nom,court:nom.slice(5)+'/'+nom.slice(2,4),valeur:v.valeur,detail:v.n+' règlements · agrégat mensuel'}));
}
function rendreAnalyses() {
  const zone=document.getElementById('analyse-graphiques');if(!zone) return;
  const filtre={selection:document.getElementById('analyse-selection').value,periode:document.getElementById('analyse-periode').value,sport:document.getElementById('analyse-sport').value,book:document.getElementById('analyse-book').value};
  const rows=lignesAnalyse(D,fiches,filtre),s=statsAnalyse(rows);
  const affiner=document.getElementById('analyse-affiner-titre');
  if(affiner) affiner.textContent=[nomsSports[filtre.sport] || filtre.sport,filtre.book].filter(Boolean).join(' · ') || 'Sport et bookmaker';
  document.getElementById('analyse-periode-badge').textContent=filtre.periode==='futur'?'Suivi prospectif':filtre.periode==='ensemble'?'Historique figé':'Historique actualisé';
  document.getElementById('analyse-periode-badge').classList.toggle('historique',filtre.periode!=='futur');
  document.getElementById('analyse-contexte').textContent=`${entierAnalyse(s.n)} prises · ${s.regles} réglées · ${s.attente} en attente. `+(filtre.periode==='futur'?'Depuis le 14/10 à 14 h (Paris), ou le lancement propre à la stratégie.':filtre.periode==='ensemble'?`Matchs du 7 au 13/10 · règlements figés au ${quand(D.laboratoire?.releve)}.`:(filtre.selection==='uniques'?'Règlements actuels, archives comprises.':'Sélections historiques et prospectives disponibles, règlements actualisés.'))+(s.connus<s.regles?` ${s.regles-s.connus} gains indisponibles exclus du gain et du ROI.`:'');
  document.getElementById('analyse-vide').hidden=rows.length>0;zone.hidden=!rows.length;
  const kpis=[['Gain net',argentAnalyse(s.gain),`${argentAnalyse(s.mises).replace(/^\+/, '')} de mises réglées`],['ROI',tauxAnalyse(s.roi),'Gain / mises réglées'],['Paris réglés',entierAnalyse(s.regles),`${s.attente} en attente`],['CLV moyenne',tauxAnalyse(s.clv),`${s.clv_n}/${s.regles} clôtures mesurées`],['Réussite',s.reussite==null?'—':(s.reussite*100).toFixed(1).replace('.',',')+' %','Gagnés et demi-gagnés / réglés'],['Repli maximal',argentAnalyse(s.drawdown==null?null:-s.drawdown),'Baisse depuis un sommet des gains']];
  document.getElementById('analyse-kpis').innerHTML=kpis.map(([nom,val,detail])=>`<div><span>${e(nom)}</span><strong>${e(val)}</strong><small>${e(detail)}</small></div>`).join('');
  if(!rows.length) {zone.innerHTML='';return;}
  const resultats=[['gagne','Gagnés'],['demi_gagne','Demi-gagnés'],['perdu','Perdus'],['demi_perdu','Demi-perdus'],['rembourse','Remboursés']].map(([statut,nom])=>({nom,n:rows.filter(p=>p.statut===statut).length,couleur:({gagne:'var(--accent)',demi_gagne:'#8472bd',perdu:'var(--graph-neg)',demi_perdu:'#b27b24',rembourse:'#64748b'})[statut]}));
  resultats.push({nom:'En attente',n:s.attente,couleur:'var(--ligne)'});
  const sports=groupesAnalyse(rows,'sport').sort((a,b)=>b.n-a.n),books=groupesAnalyse(rows,'bookmaker').sort((a,b)=>(b.gain??-Infinity)-(a.gain??-Infinity));
  const partsSport=sports.slice(0,4).map(x=>({nom:nomsSports[x.nom] || x.nom,n:x.n}));if(sports.length>4) partsSport.push({nom:'Autres sports',n:sports.slice(4).reduce((a,x)=>a+x.n,0)});
  const refs=groupesAnalyse(rows,'reference').sort((a,b)=>(b.clv??-Infinity)-(a.clv??-Infinity));
  const bornes=[1.5,2,3,5,10,Infinity],noms=['≤ 1,50','1,51–2','2,01–3','3,01–5','5,01–10','> 10'];
  const cotes=bornes.map((b,i)=>({nom:noms[i],valeur:rows.filter(p=>Number.isFinite(p.cote) && p.cote>1 && p.cote<=(b) && (i===0 || p.cote>bornes[i-1])).length}));
  const inconnues=rows.filter(p=>!Number.isFinite(p.cote) || p.cote<=1).length;if(inconnues)cotes.push({nom:'Inconnue',valeur:inconnues});
  const quotidien=seriesQuotidiennesAnalyse(rows);
  zone.innerHTML=[
    cadreAnalyse('Évolution des gains',`${s.connus} règlements · date de règlement, à défaut début du match · €`,ligneGraphiqueAnalyse(s.courbe,'Gain cumulé'),true),
    cadreAnalyse('Résultats des paris',`${s.n} prises, y compris ${s.attente} en attente`,anneauAnalyse(resultats,'Répartition des résultats')),
    cadreAnalyse('Volume par sport','Nombre de prises, réglées et en attente',anneauAnalyse(partsSport,'Répartition des sports')),
    cadreAnalyse('Gain par bookmaker','Gains nets sur les paris réglés · axe commun en €',barresAnalyse(books,'gain',argentAnalyse)),
    cadreAnalyse('CLV par référence','Moyenne sur les clôtures validées · couverture sous chaque barre',barresAnalyse(refs,'clv',tauxAnalyse)),
    cadreAnalyse('Distribution des cotes',`${s.n} prises · nombre de paris par tranche`,colonnesAnalyse(cotes,v=>Number.isInteger(v)?entierAnalyse(v):String(v).replace('.',','),'Volume par tranche de cote')),
    cadreAnalyse(quotidien.some(x=>x.nom.length===7)?'Gains par mois':'Gains par jour','Date de règlement, à défaut début du match · heure de Paris',colonnesAnalyse(quotidien,argentAnalyse,'Gains au fil des règlements')),
    cadreAnalyse('Replis depuis les sommets',`Repli maximal observé : ${argentAnalyse(s.drawdown==null?null:-s.drawdown)} · €`,ligneGraphiqueAnalyse(s.replis,'Repli en cours'),true)
  ].join('');
}
function initialiserAnalyses() {
  const selection=document.getElementById('analyse-selection');
  for(const [id] of Object.entries(D.laboratoire?.navigation?.selections || {})) {
    const option=document.createElement('option');option.value=id;
    const regle=D.laboratoire.resultats?.find(r=>r.regle.id===id)?.regle;
    option.textContent=D.variantes?.[id]?.nom || (regle?`${regle.reference} · ${id}`:id.replace(' (rejeu)',''));selection.append(option);
  }
  for(const [id,champ] of [['analyse-sport','sport'],['analyse-book','bookmaker']]) {
    const sel=document.getElementById(id);for(const val of [...new Set(fiches.filter(p=>p.reference!=='Pinnacle brut').map(p=>p[champ]).filter(Boolean))].sort()) {const o=document.createElement('option');o.value=val;o.textContent=nomsSports[val] || val;sel.append(o);}
  }
  for(const id of ['analyse-selection','analyse-periode','analyse-sport','analyse-book']) document.getElementById(id).onchange=rendreAnalyses;
  const graph=document.getElementById('analyse-graphiques');
  for(const type of ['pointerover','focusin','click']) graph.addEventListener(type,ev=>{
    const cible=ev.target.closest('[data-aide]');if(cible)cible.closest('figure').querySelector('output').textContent=cible.dataset.aide;
  });
  rendreAnalyses();
}
