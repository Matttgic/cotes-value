// Effets de présentation, style journal financier : bandeau boursier de l'Accueil, courbes qui se tracent,
// transitions entre onglets (View Transitions) et petite vibration au changement d'onglet.
// Rien ne bouge si l'appareil demande moins de mouvement.

// Changement d'onglet : fondu enchaîné natif quand le navigateur le permet, et une vibration de 8 ms sur Android.
function basculer(action) {
  try{navigator.vibrate?.(8);}catch{}
  if(document.startViewTransition && animationsPermises()) document.startViewTransition(action);
  else action();
}

// Bandeau boursier de l'Accueil, façon cotation de Wall Street : chiffres clés, paris à jouer (▲ vert), derniers
// résultats (▲ gain, ▼ perte). Les éléments sont doublés pour que le défilement boucle sans saut.
function bandeauBoursier(elements) {
  const une=document.querySelector('#o-accueil .une-tete');if(!une) return;
  let bandeau=une.querySelector('.cv-bandeau');
  if(!elements.length){bandeau?.remove();return;}
  if(!bandeau){
    bandeau=document.createElement('div');bandeau.className='cv-bandeau';bandeau.setAttribute('role','marquee');
    bandeau.setAttribute('aria-label','Cotation du jour');une.prepend(bandeau);
  }
  const fleche=c=>c==='pos'?'▲':c==='neg'?'▼':'';
  const html=elements.map(([nom,valeur,variation,classe])=>`<span class="cv-cote"><span class="cv-sym">${e(nom)}</span> <b>${e(valeur)}</b>${variation||classe?` <i class="${classe||''}">${fleche(classe)}${variation?' '+e(variation):''}</i>`:''}</span>`).join('');
  bandeau.innerHTML=`<div class="cv-piste">${html}<span aria-hidden="true" class="cv-double">${html}</span></div>`;
  const piste=bandeau.firstElementChild;
  requestAnimationFrame(()=>piste.style.setProperty('--cv-duree',`${Math.max(20,piste.scrollWidth/2/40)}s`));
}

// Courbe qui se trace : à la première ouverture d'une stratégie (et à la première vue du gain cumulé de l'Accueil),
// la ligne part du début et le point avance jusqu'au gain d'aujourd'hui.
const courbesTracees=new Set();
function tracerCourbe(svg) {
  if(!svg || !animationsPermises()) return;
  const chemins=[...svg.querySelectorAll(':scope>path')],ligne=chemins.at(-1),point=svg.querySelector(':scope>circle');
  if(!ligne || !ligne.getTotalLength) return;
  const long=ligne.getTotalLength(),duree=1700,debut=performance.now(),fin=point?[point.getAttribute('cx'),point.getAttribute('cy')]:null;
  const autres=chemins.slice(0,-1);
  ligne.style.strokeDasharray=`${long} ${long}`;ligne.style.strokeDashoffset=long;
  autres.forEach(c=>{c.style.opacity=0;c.style.transition='opacity .6s ease .9s';});
  requestAnimationFrame(()=>autres.forEach(c=>c.style.opacity=''));
  const pas=t=>{
    const p=Math.min(1,(t-debut)/duree),lisse=p<.5?4*p*p*p:1-Math.pow(-2*p+2,3)/2;
    ligne.style.strokeDashoffset=long*(1-lisse);
    if(point){const q=ligne.getPointAtLength(long*lisse);point.setAttribute('cx',q.x);point.setAttribute('cy',q.y);}
    if(p<1) requestAnimationFrame(pas);
    else {ligne.style.strokeDasharray=ligne.style.strokeDashoffset='';if(point){point.setAttribute('cx',fin[0]);point.setAttribute('cy',fin[1]);point.classList.add('cv-arrivee');}}
  };
  requestAnimationFrame(pas);
}
document.addEventListener('toggle',e=>{
  const d=e.target;
  if(!(d instanceof HTMLDetailsElement) || !d.open || !d.classList.contains('ligne-strategie')) return;
  const cle=d.id || d.querySelector('summary')?.textContent;
  if(courbesTracees.has(cle)) return;
  courbesTracees.add(cle);
  tracerCourbe(d.querySelector('.grande-courbe'));
},true);
const zoneCourbeAccueil=document.getElementById('acc-courbe');
if(zoneCourbeAccueil) new IntersectionObserver((entrees,obs)=>{
  if(!entrees[0].isIntersecting) return;
  const svg=zoneCourbeAccueil.querySelector('.grande-courbe');if(!svg) return;
  obs.disconnect();tracerCourbe(svg);
},{threshold:.4}).observe(zoneCourbeAccueil);
