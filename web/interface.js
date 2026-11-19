// Présentation uniquement : aucune règle de sélection ou statistique n'est recalculée.
// Les cellules originales sont déplacées,
// sans clonage des contrôles, pour conserver leurs identifiants et événements.
const tableauxCompactes=new WeakMap();
function textePrincipal(el) {
  return [...el.childNodes].filter(n=>!['SMALL','SELECT'].includes(n.nodeName)).map(n=>n.textContent).join(' ').trim() || el.textContent.trim();
}
function adapterTableaux() {
  observationInterface.disconnect();
  try {
    for (const [index,table] of [...document.querySelectorAll('main table:not(.strategies-table)')].entries()) {
      const avant=tableauxCompactes.get(table);
      if (avant?.source===table.firstChild) continue;
      const entete=table.querySelector('tr');
      if (!entete?.querySelector('th')) {avant?.host.remove();tableauxCompactes.delete(table);continue;}
      const noms=[...entete.querySelectorAll('th')].map(th=>[...th.childNodes].map(n=>n.textContent.trim()).filter(Boolean).join(' / '));
      const host=document.createElement('div');host.className='lignes-bilan';
      const ouverts=new Set([...(avant?.host.querySelectorAll('details[open]') || [])].map(d=>d.id));
      for (const [i,tr] of [...table.querySelectorAll('tr')].entries()) {
        const cellules=[...tr.querySelectorAll('td')];if (!cellules.length) continue;
        const d=document.createElement('details');d.className='ligne-detail ligne-bilan';
        d.id=`bilan-${table.id || index}-${i}`;d.open=ouverts.has(d.id);
        const titre=textePrincipal(cellules[0]);
        const resume=document.createElement('summary');
        const nom=document.createElement('span');nom.className='ligne-nom';nom.textContent=titre;nom.title=titre;resume.append(nom);
        if(['liste-bilan','bilan-tranches'].includes(table.id)) {
          const volume=cellules.find((td,j)=>/^Paris/i.test(noms[j] || ''));
          if(volume) {
            const matchs=[...volume.querySelectorAll('small')].find(el=>/matchs$/.test(el.textContent.trim()));
            const exposition=document.createElement('small');exposition.className='bilan-exposition';
            exposition.textContent=textePrincipal(volume)+' tickets'+(matchs?' · '+matchs.textContent:'');
            nom.append(exposition);
          }
        }
        // Les deux mesures prioritaires du tableau, avec leurs libellés.
        const mesures=cellules.map((td,j)=>({td,j})).filter(({j})=>j>0);
        const prioritaires=mesures.filter(({j})=>/gain|net|roi|clv|réel|espéré/i.test(noms[j] || '')).slice(0,2);
        for (const {td,j} of (prioritaires.length?prioritaires:mesures.slice(0,2))) {
          const valeur=document.createElement('span');valeur.className='ligne-mesure '+td.className;
          valeur.textContent=(noms[j]?.split(' / ')[0] || 'Valeur')+' '+textePrincipal(td);
          valeur.title=valeur.textContent;resume.append(valeur);
        }
        const corps=document.createElement('div');corps.className='ligne-corps bilan-champs';
        cellules.forEach((td,j)=>{
          const champ=document.createElement('div'),label=document.createElement('span'),valeur=document.createElement('div');
          label.className='champ-libelle';label.textContent=noms[j] || 'Sélection';
          while(td.firstChild) valeur.append(td.firstChild);
          champ.append(label,valeur);corps.append(champ);
        });
        d.append(resume,corps);host.append(d);
      }
      table.hidden=true;avant?.host.remove();table.after(host);
      tableauxCompactes.set(table,{source:table.firstChild,host});
    }
    // Listes secondaires : mêmes lignes dépliables, sans modifier leurs données.
    for (const conteneur of document.querySelectorAll('#ctl-liste, .seg-paris')) {
      for (const [i,carte] of [...conteneur.querySelectorAll('article, .sp')].entries()) {
        if(carte.closest('.ligne-detail')) {
          if(!carte.classList.contains('sp')) continue;
          if(carte.parentElement.classList.contains('ligne-corps')) continue;
        }
        const d=document.createElement('details');d.className='ligne-detail ligne-secondaire';
        d.id=`detail-${conteneur.id || conteneur.closest('[id]')?.id || 'segment'}-${i}`;
        const summary=document.createElement('summary'),nom=document.createElement('span');nom.className='ligne-nom';
        nom.textContent=carte.querySelector('.match,b,h3')?.textContent || carte.textContent.trim();nom.title=nom.textContent;
        const valeur=document.createElement('span');valeur.className='ligne-valeur';
        valeur.textContent=carte.querySelector('.badge,.pos,.neg')?.textContent || 'Détails';
        const corps=document.createElement('div');corps.className='ligne-corps';summary.append(nom,valeur);
        if(conteneur.id!=='ctl-liste') {
          const texte=(carte.querySelector('.l3 > span') || carte.querySelector(':scope > div'))?.textContent?.trim();
          if(texte) {const pari=document.createElement('span');pari.className='pari-selection';pari.textContent=texte;summary.append(pari);d.classList.add('secondaire-pari');}
          const horaire=carte.querySelector('time.pari-horaire');
          if(horaire) summary.append(horaire.cloneNode(true));
          const collecte=carte.querySelector('.pari-collecte');
          if(collecte) summary.append(collecte.cloneNode(true));
        }
        carte.before(d);corps.append(carte);d.append(summary,corps);
      }
    }
  } finally {observationInterface.observe(document.querySelector('main'),{childList:true,subtree:true});}
}
let adaptationPrevue=false;
const observationInterface=new MutationObserver(() => {
  if(adaptationPrevue) return;
  adaptationPrevue=true;
  queueMicrotask(()=>{adaptationPrevue=false;adapterTableaux();});
});
observationInterface.observe(document.querySelector('main'),{childList:true,subtree:true});

function actualiserFraicheur() {
  const cycle=D.etat?.dernier_cycle;
  const instant=cycle?.fin || cycle?.debut;
  const age=minutes(instant);
  const info=document.getElementById('fraicheur');
  if(!info) return;
  info.textContent=age==null ? 'En attente d’un relevé' : age<1 ? 'Relevé à l’instant' : `Relevé il y a ${age} min`;
  info.classList.toggle('ancien',age!=null && age>15);
}
function choisirVueStrategies(vue) {
  const graphiques=vue==='graphiques';
  document.getElementById('strategies-vue-liste').hidden=graphiques;
  document.getElementById('strategies-vue-graphiques').hidden=!graphiques;
  for(const b of document.querySelectorAll('[data-vue-strategies]')) b.setAttribute('aria-pressed',String(b.dataset.vueStrategies===vue));
  ecrire('cv-vue-strategies-lignes',graphiques?'graphiques':'liste');
}
function compacterFiltres() {
  for(const [id,selecteur,titre] of [
    ['filtres-bilan','#puces-ref','Choisir la référence ou la stratégie'],
    ['filtres-paris','.outils-horaires, .grille-filtres, .outils-paris, #paris-ref-aide','Filtres et export']
  ]) {
    const elements=[...document.querySelectorAll(selecteur)];if(!elements.length) continue;
    const d=document.createElement('details'),summary=document.createElement('summary'),corps=document.createElement('div');
    d.id=id;d.className='mode-emploi filtres-depliables';summary.textContent=titre;
    elements[0].before(d);for(const el of elements) corps.append(el);d.append(summary,corps);
  }
}
// Mode nuit : automatique (réglage du téléphone), ou forcé jour / nuit.
function initialiserTheme() {
  const sel=document.getElementById('theme-site');
  if(!sel) return;
  const appliquer=v=>{if(v==='auto') delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme=v==='jour'?'light':'dark';};
  const choix=lire('cv-theme-v1');sel.value=['nuit','jour'].includes(choix)?choix:'auto';
  appliquer(sel.value);
  sel.onchange=()=>{appliquer(sel.value);ecrire('cv-theme-v1',sel.value);};
}
function connexion() {document.getElementById('hors-ligne').hidden=navigator.onLine!==false;}
window.addEventListener('online',connexion);window.addEventListener('offline',connexion);connexion();
// Toucher une notification ouvre le site avec ?alerte=<id> : bandeau « Parier chez … » avec le lien du bookmaker.
async function bandeauAlerte() {
  const id=new URLSearchParams(location.search).get('alerte');
  if(!id) return;
  const place=document.getElementById('o-paris');if(!place) return;
  let html='<b>Alerte expirée</b><small>Le prix n’est plus valable ou l’alerte est trop ancienne.</small>';
  try {
    const o=((await (await fetch('ordres.json',{cache:'no-store'})).json()).ordres||[]).find(x=>x.id===id);
    if(o) {
      const lien=o.lien?`<a class="btn" href="${e(o.lien)}" target="_blank" rel="noopener noreferrer">${o.lien_repli?'Page du sport chez '+e(o.bookmaker)+' › (match à chercher)':'Ouvrir le match chez '+e(o.bookmaker)+' ›'}</a>`:'';
      html=`<b>${e(o.domicile)} – ${e(o.exterieur)}</b><span>${e(o.pari)} · cote ${cote(o.cote_relevee)} chez ${e(o.bookmaker)}</span><small>Jouer seulement si la cote reste ≥ ${cote(o.cote_min)} · ${hm(o.envoi_le)} · ${e(o.bookmaker)}.</small>${lien}`;
    }
  } catch {html='<b>Alerte indisponible</b><small>Réessayez dans un instant.</small>';}
  const div=document.createElement('div');div.className='bandeau-alerte';div.innerHTML=html;place.prepend(div);
}
// Appelé à la fin du rendu : les utilitaires du modèle sont alors initialisés.
function initialiserInterface() {
  initialiserTheme();bandeauAlerte();compacterFiltres();adapterTableaux();actualiserFraicheur();setInterval(actualiserFraicheur,60000);
  // Rapidité des alertes : délai d'envoi et trous entre relevés, puis les dernières alertes envoyées.
  const r=D.rapidite || {}, min=x=>x==null?'—':x<10?x.toFixed(1).replace('.',',')+' min':Math.round(x)+' min';
  document.getElementById('notif-rapidite').innerHTML=[
    ['Envoi après lecture du prix',r.envoi_median_s==null?'—':r.envoi_median_s<90?'≈ '+Math.round(r.envoi_median_s)+' s':min(r.envoi_median_s/60),r.envoi_median_s==null?'':'pos'],
    ['Écart habituel entre deux relevés',min(r.ecart_median_min),'' ],
    ['Relevés espacés de plus de 8 min',r.releves?`${r.ecarts_plus_8_min} sur ${r.releves}`:'—',r.ecarts_plus_8_min?'neg':'' ],
    ['Plus long trou',min(r.plus_long_trou_min),r.plus_long_trou_min>15?'neg':'']
  ].map(([t,v,c])=>`<div class="notif-mesure"><span>${t}</span><b class="${c}">${e(v)}</b></div>`).join('');
  document.getElementById('notif-dernieres').innerHTML=(r.dernieres || []).length?r.dernieres.map(a=>
    `<div class="notif-alerte"><span><b>${e(a.match)}</b><small>${e(a.pari)}</small></span><span><b>${cote(a.cote)}</b><small>${e(a.bookmaker)} · ${hm(a.envoi)}</small></span></div>`).join('')
    :'<p class="aide notif-vide">Aucune alerte envoyée récemment.</p>';
  const diagnostics=D.diagnostic_alertes || [];
  document.getElementById('notif-diagnostic').innerHTML=diagnostics.length?diagnostics.slice().reverse().map(c=>
    `<p>Demande ${quand(c.envoi_demande_le)} · ${(c.alertes || []).length} signal(s) préparé(s) · ${c.resultat?.sent || 0} notification(s) acceptée(s) par le service Push${c.resultat?.ok===false?' · en erreur':''}</p>`).join('')
    :'<p class="aide">Aucune alerte enregistrée.</p>';
  setInterval(()=>{
    actualiserHoraires();
    if(document.querySelector('.onglet.actif')?.id!=='o-paris' || !document.getElementById('paris-horaire').value) return;
    const conteneur=document.getElementById('liste-paris');
    const ouverts=new Set([...conteneur.querySelectorAll('details[open]')].map(d=>d.id));
    rendreParis();
    for(const d of conteneur.querySelectorAll('details')) d.open=ouverts.has(d.id);
  },60000);
  document.getElementById('bilan-evolution').ontoggle=()=>{if(document.getElementById('bilan-evolution').open) rendreCourbe();};
  choisirVueStrategies(lire('cv-vue-strategies-lignes')==='graphiques'?'graphiques':'liste');
  for(const b of document.querySelectorAll('[data-vue-strategies]')) b.onclick=()=>{
    choisirVueStrategies(b.dataset.vueStrategies);
    requestAnimationFrame(()=>rendreStrategies());
  };
}

// Animations de présentation : apparition des sections, chiffres qui défilent, signal des chiffres qui ont bougé depuis
// la dernière visite. Rien n'est animé si l'appareil demande moins de mouvement.
const animationsPermises=()=>!matchMedia('(prefers-reduced-motion: reduce)').matches;
function animerApparition(section) {
  if(!animationsPermises()) return;
  [...section.children].filter(el=>el.offsetParent!==null).slice(0,14).forEach((el,i)=>{
    el.classList.remove('cv-apparait');void el.offsetWidth;
    el.style.setProperty('--cv-delai',`${i*35}ms`);el.classList.add('cv-apparait');
    el.addEventListener('animationend',()=>el.classList.remove('cv-apparait'),{once:true});
  });
}
const nombreAffiche=texte=>{
  const m=texte.match(/-?\d+(?:[\s  ]\d{3})*(?:,\d+)?/);if(!m) return null;
  const valeur=Number(m[0].replace(/[\s  ]/g,'').replace(',','.'));
  return Number.isFinite(valeur) ? {brut:m[0],valeur,decimales:(m[0].split(',')[1] || '').length} : null;
};
function defilerChiffre(el) {
  const texte=el.textContent,n=nombreAffiche(texte);
  if(!n || n.valeur===0 || !animationsPermises()) return;
  const [avant,apres]=[texte.slice(0,texte.indexOf(n.brut)),texte.slice(texte.indexOf(n.brut)+n.brut.length)];
  const format=v=>v.toLocaleString('fr-FR',{minimumFractionDigits:n.decimales,maximumFractionDigits:n.decimales});
  const debut=performance.now(),duree=650;
  el.classList.add('cv-defile');
  const etape=t=>{
    const p=Math.min(1,(t-debut)/duree),lisse=1-Math.pow(1-p,3);
    if(!el.isConnected) return;
    if(p<1) {el.textContent=avant+format(n.valeur*lisse)+apres;requestAnimationFrame(etape);}
    else {el.textContent=texte;el.classList.remove('cv-defile');}
  };
  requestAnimationFrame(etape);
}
const kpisAffiches=new Map(),kpisChanges=new Map();let kpisCompares=false;
function animerKpis() {
  const cible=document.getElementById('acc-kpis');if(!cible) return;
  const mode=document.getElementById('mode-mise')?.value || '';
  let memoire={};try{memoire=JSON.parse(localStorage.getItem('cv-kpis-v1') || '{}');}catch{}
  for(const kpi of cible.querySelectorAll('.acc-kpi')) {
    const titre=kpi.querySelector('p')?.textContent || '',fort=kpi.querySelector('strong');if(!fort) continue;
    const texte=fort.textContent,cle=`${mode}|${titre}`,valeur=nombreAffiche(texte)?.valeur;
    if(kpisAffiches.get(cle)!==texte) defilerChiffre(fort);
    kpisAffiches.set(cle,texte);
    if(!kpisCompares && valeur!=null && memoire[cle]!=null && memoire[cle]!==valeur)
      kpisChanges.set(cle,titre==='En cours' ? 'neutre' : valeur>memoire[cle] ? 'hausse' : 'baisse');
    const sens=kpisChanges.get(cle);
    if(sens) {
      kpi.classList.add(`cv-${sens}`);kpi.title='A changé depuis ta dernière visite';
      if(performance.now()<6000) kpi.classList.add('cv-flash');
    }
    if(valeur!=null) memoire[cle]=valeur;
  }
  kpisCompares=true;
  try{localStorage.setItem('cv-kpis-v1',JSON.stringify(memoire));}catch{}
}
new MutationObserver(mutations=>{
  for(const m of mutations) if(m.target.classList.contains('onglet') && m.target.classList.contains('actif') && !(m.oldValue || '').split(' ').includes('actif')) animerApparition(m.target);
}).observe(document.querySelector('main'),{subtree:true,attributes:true,attributeFilter:['class'],attributeOldValue:true});
const kpisCible=document.getElementById('acc-kpis');
if(kpisCible) new MutationObserver(animerKpis).observe(kpisCible,{childList:true});
