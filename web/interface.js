// Présentation uniquement : aucune règle de sélection ou statistique n'est recalculée.
const menuPlus = document.getElementById('nav-plus-toggle');
function fermerMenu() {
  document.getElementById('onglets').classList.remove('menu-ouvert');
  menuPlus.setAttribute('aria-expanded','false');
}
menuPlus.onclick = () => {
  const ouvert=document.getElementById('onglets').classList.toggle('menu-ouvert');
  menuPlus.setAttribute('aria-expanded',String(ouvert));
};
document.addEventListener('click', ev => {if (!ev.target.closest('#onglets')) fermerMenu();});
document.addEventListener('keydown', ev => {if (ev.key==='Escape') {fermerMenu();menuPlus.focus();}});

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
        if(['liste-bilan','bilan-books','bilan-tranches'].includes(table.id)) {
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
    for (const conteneur of document.querySelectorAll('#ctl-liste, #gemini-picks-list, #jules-picks-list, #jules-v2-picks-list, #m3-picks-list, #prudentes-picks, .seg-paris')) {
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
  const debut=D.etat?.dernier_cycle?.debut, age=minutes(debut);
  const info=document.getElementById('fraicheur');
  info.textContent=age==null ? 'En attente d’un relevé' : age<1 ? 'Relevé à l’instant' : `Relevé il y a ${age} min`;
  info.classList.toggle('ancien',age!=null && age>15);
  document.getElementById('jouer-quand').textContent=debut ?
    `Relevé à ${hm(debut)} · ${age<1 ? 'à l’instant' : 'il y a '+age+' min'}. Vérifie la cote avant de jouer.` : 'Aucune collecte disponible pour le moment.';
}
let sportJouer=lire('cv-sport-jouer') || '';
function rendreResumeJouer(liste) {
  const validees=liste.filter(o=>o.strategies.length>0).length;
  const sports=[...new Set(liste.map(o=>o.sport).filter(Boolean))].sort();
  document.getElementById('jouer-resume').innerHTML=`<div class="resume-cotes">
    <svg viewBox="0 0 64 64" aria-hidden="true"><circle cx="32" cy="32" r="27" fill="none" stroke="var(--ligne)" stroke-width="4"/>
    <circle cx="32" cy="32" r="27" fill="none" stroke="var(--accent)" stroke-width="4" pathLength="100" stroke-dasharray="${liste.length?100*validees/liste.length:0} 100" transform="rotate(-90 32 32)"/>
    <text x="32" y="36" text-anchor="middle">${liste.length}</text></svg>
    <div><b>${validees} validée${validees>1?'s':''} par stratégie</b><span>${liste.length} cotes · ${sports.length} sports · ${new Set(liste.map(o=>o.bookmaker)).size} bookmakers</span></div></div>`;
  const choisi=sportJouer;
  document.getElementById('jouer-sports').innerHTML=[['','Tous les sports'],...sports.map(s=>[s,nomsSports[s] || s])].map(([s,nom])=>
    `<button data-sport="${e(s)}" class="sport-puce ${choisi===s?'actif':''}" aria-pressed="${choisi===s}">${s?iconeSport(s):''}<span>${e(nom)}</span>${s?`<b>${liste.filter(o=>o.sport===s).length}</b>`:''}</button>`).join('');
  for(const b of document.querySelectorAll('#jouer-sports button')) b.onclick=()=>{sportJouer=b.dataset.sport;ecrire('cv-sport-jouer',sportJouer);rendreJouer();};
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
    ['filtres-jouer','#jouer-sports, #jouer-filtres','Filtrer les opportunités'],
    ['filtres-bilan','#puces-ref','Choisir la référence ou la stratégie'],
    ['filtres-paris','.grille-filtres','Filtres des paris']
  ]) {
    const elements=[...document.querySelectorAll(selecteur)];if(!elements.length) continue;
    const d=document.createElement('details'),summary=document.createElement('summary'),corps=document.createElement('div');
    d.id=id;d.className='mode-emploi filtres-depliables';summary.textContent=titre;
    elements[0].before(d);for(const el of elements) corps.append(el);d.append(summary,corps);
  }
}
function initialiserPalette() {
  const sel=document.getElementById('palette-site');
  const choix=lire('cv-palette-v1');sel.value=['bleu','violet','graphite'].includes(choix)?choix:'bleu';
  document.documentElement.dataset.palette=sel.value;
  sel.onchange=()=>{document.documentElement.dataset.palette=sel.value;ecrire('cv-palette-v1',sel.value);};
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
// Appelé à la fin du rendu : les utilitaires du modèle sont alors initialisés.
function initialiserInterface() {
  initialiserPalette();initialiserTheme();compacterFiltres();adapterTableaux();actualiserFraicheur();setInterval(actualiserFraicheur,60000);
  // Rapidité des alertes : délai d'envoi et trous entre relevés, puis les dernières alertes envoyées.
  const r=D.rapidite || {}, min=x=>x==null?'—':x<10?x.toFixed(1).replace('.',',')+' min':Math.round(x)+' min';
  document.getElementById('notif-rapidite').innerHTML=[
    ['Envoi après lecture du prix',r.envoi_median_s==null?'—':r.envoi_median_s<90?'≈ '+Math.round(r.envoi_median_s)+' s':min(r.envoi_median_s/60),r.envoi_median_s==null?'':'pos'],
    ['Écart habituel entre deux relevés',min(r.ecart_median_min),''],
    ['Relevés espacés de plus de 8 min',r.releves?`${r.ecarts_plus_8_min} sur ${r.releves}`:'—',r.ecarts_plus_8_min?'neg':''],
    ['Plus long trou',min(r.plus_long_trou_min),r.plus_long_trou_min>15?'neg':'']
  ].map(([t,v,c])=>`<div class="notif-mesure"><span>${t}</span><b class="${c}">${e(v)}</b></div>`).join('');
  document.getElementById('notif-dernieres').innerHTML=(r.dernieres || []).length?r.dernieres.map(a=>
    `<div class="notif-alerte"><span><b>${e(a.match)}</b><small>${e(a.pari)}</small></span><span><b>${cote(a.cote)}</b><small>${e(a.bookmaker)} · ${hm(a.envoi)}</small></span></div>`).join('')
    :'<p class="aide notif-vide">Aucune alerte envoyée récemment.</p>';
  const diagnostics=D.diagnostic_alertes || [];
  document.getElementById('notif-diagnostic').innerHTML=diagnostics.length?diagnostics.slice().reverse().map(c=>
    `<p>Demande ${quand(c.envoi_demande_le)} · ${(c.alertes || []).length} signal(s) préparé(s) · ${c.resultat?.sent || 0} notification(s) acceptée(s) par le service Push${c.resultat?.ok===false?' · envoi en erreur':''}.</p>`).join(''):'<p>Aucun diagnostic d’envoi disponible pour les anciennes alertes.</p>';
  setInterval(()=>{
    actualiserHoraires();
    const actif=document.querySelector('.onglet.actif')?.id;
    const prefixe=actif==='o-jouer'?'jouer':actif==='o-paris'?'paris':null;
    if(!prefixe || (prefixe!=='jouer' && !document.getElementById(prefixe+'-horaire').value)) return;
    const conteneur=document.getElementById('liste-'+prefixe);
    const ouverts=new Set([...conteneur.querySelectorAll('details[open]')].map(d=>d.id));
    if(prefixe==='jouer') rendreJouer();else rendreParis();
    for(const d of conteneur.querySelectorAll('details')) d.open=ouverts.has(d.id);
  },60000);
  document.getElementById('bilan-evolution').ontoggle=()=>{if(document.getElementById('bilan-evolution').open) rendreCourbe();};
  choisirVueStrategies(lire('cv-vue-strategies-lignes')==='graphiques'?'graphiques':'liste');
  for(const b of document.querySelectorAll('[data-vue-strategies]')) b.onclick=()=>{
    choisirVueStrategies(b.dataset.vueStrategies);
    requestAnimationFrame(()=>rendreStrategies());
  };
}
