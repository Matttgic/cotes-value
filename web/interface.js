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

// Des libellés explicites permettent de lire chaque ligne des petits tableaux sur mobile.
function adapterTableaux() {
  for (const table of document.querySelectorAll('main table:not(.strategies-table)')) {
    table.setAttribute('role','table');
    const entete=table.querySelector('tr');
    if (!entete?.querySelector('th')) continue;
    entete.classList.add('entete-table');
    const noms=[...entete.querySelectorAll('th')].map(th => {
      th.setAttribute('scope','col');
      th.setAttribute('role','columnheader');
      return [...th.childNodes].map(n=>n.textContent.trim()).filter(Boolean).join(' · ');
    });
    for (const tr of table.querySelectorAll('tr')) {
      tr.setAttribute('role','row');
      [...tr.querySelectorAll('td')].forEach((td,i) => {td.dataset.label=noms[i] || 'Détail';td.setAttribute('role','cell');});
    }
  }
}
let adaptationPrevue=false;
new MutationObserver(() => {
  if (adaptationPrevue) return;
  adaptationPrevue=true;
  queueMicrotask(() => {adaptationPrevue=false;adapterTableaux();});
}).observe(document.querySelector('main'),{childList:true,subtree:true});

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
  ecrire('cv-vue-strategies',graphiques?'graphiques':'liste');
}
function connexion() {document.getElementById('hors-ligne').hidden=navigator.onLine!==false;}
window.addEventListener('online',connexion);window.addEventListener('offline',connexion);connexion();
// Appelé à la fin du rendu : les utilitaires du modèle sont alors initialisés.
function initialiserInterface() {
  adapterTableaux();actualiserFraicheur();setInterval(actualiserFraicheur,60000);
  choisirVueStrategies(lire('cv-vue-strategies')==='graphiques'?'graphiques':'liste');
  for(const b of document.querySelectorAll('[data-vue-strategies]')) b.onclick=()=>{
    choisirVueStrategies(b.dataset.vueStrategies);
    requestAnimationFrame(()=>rendreStrategies());
  };
}
