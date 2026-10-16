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
function rendreResumeJouer(liste) {
  document.getElementById('jouer-resume').innerHTML=[
    [liste.length,'cotes repérées'],[new Set(liste.map(o=>o.sport).filter(Boolean)).size,'sports'],
    [new Set(liste.map(o=>o.bookmaker)).size,'bookmakers']
  ].map(([n,nom])=>`<span><b>${n}</b> ${nom}</span>`).join('');
}
function connexion() {document.getElementById('hors-ligne').hidden=navigator.onLine!==false;}
window.addEventListener('online',connexion);window.addEventListener('offline',connexion);connexion();
// Appelé à la fin du rendu : les utilitaires du modèle sont alors initialisés.
function initialiserInterface() {adapterTableaux();actualiserFraicheur();setInterval(actualiserFraicheur,60000);}
