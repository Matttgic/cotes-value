// Effets de présentation : champ 3D de l'Accueil (WebGL, sans librairie), reflet des cartes guidé par le gyroscope
// ou la souris, transitions entre onglets (View Transitions) et petite vibration au changement d'onglet.
// Tout s'arrête si l'appareil demande moins de mouvement ; rien ne tourne quand l'Accueil n'est pas visible.

// Inclinaison commune (-1…1), lissée : gyroscope sur téléphone, souris sur ordinateur.
const cvIncl={x:0,y:0,cx:0,cy:0};
addEventListener('pointermove',e=>{
  if(e.pointerType!=='mouse') return;
  cvIncl.cx=e.clientX/innerWidth*2-1;cvIncl.cy=e.clientY/innerHeight*2-1;
},{passive:true});
addEventListener('deviceorientation',e=>{
  if(e.gamma==null || e.beta==null) return;
  cvIncl.cx=Math.max(-1,Math.min(1,e.gamma/30));cvIncl.cy=Math.max(-1,Math.min(1,(e.beta-45)/30));
},{passive:true});
(function suivreInclinaison(){
  cvIncl.x+=(cvIncl.cx-cvIncl.x)*.08;cvIncl.y+=(cvIncl.cy-cvIncl.y)*.08;
  const r=document.documentElement.style;
  r.setProperty('--cv-gx',`${(50+cvIncl.x*45).toFixed(1)}%`);r.setProperty('--cv-gy',`${(30+cvIncl.y*40).toFixed(1)}%`);
  if(animationsPermises()) requestAnimationFrame(suivreInclinaison);
})();

// Changement d'onglet : fondu enchaîné natif quand le navigateur le permet, et une vibration de 8 ms sur Android.
function basculer(action) {
  try{navigator.vibrate?.(8);}catch{}
  if(document.startViewTransition && animationsPermises()) document.startViewTransition(action);
  else action();
}

// Fond de l'Accueil : un terrain vu en 3D, d'où montent des cotes ; celles en value (dont celles du jour) sont en vert.
// Canvas 2D et projection perspective faite main ; l'inclinaison du téléphone fait tourner la caméra.
function terrainDesCotes(hote) {
  if(!hote || hote.querySelector('.cv-champ')) return;
  const toile=document.createElement('canvas');toile.className='cv-champ';toile.setAttribute('aria-hidden','true');
  const ctx=toile.getContext('2d');if(!ctx) return;
  hote.prepend(toile);
  const dpr=Math.min(2,devicePixelRatio || 1),L=52.5,l=34;
  // Lignes du terrain (mètres) : contour, médiane, rond central, surfaces de réparation et de but.
  const lignes=[[[-L,-l],[L,-l],[L,l],[-L,l],[-L,-l]],[[0,-l],[0,l]],
    Array.from({length:49},(_,i)=>[9.15*Math.cos(i/48*2*Math.PI),9.15*Math.sin(i/48*2*Math.PI)])];
  for(const s of [-1,1]) lignes.push([[s*L,-20.16],[s*(L-16.5),-20.16],[s*(L-16.5),20.16],[s*L,20.16]],
    [[s*L,-9.16],[s*(L-5.5),-9.16],[s*(L-5.5),9.16],[s*L,9.16]],[[s*L,-3.66],[s*(L+1.8),-3.66],[s*(L+1.8),3.66],[s*L,3.66]]);
  // Cotes du jour lues sur la page (cote + écart), complétées par des cotes tirées au hasard.
  const duJour=()=>[...document.querySelectorAll('#acc-values .acc-pari')].map(c=>c.querySelector('.acc-cote')?.textContent.trim()).filter(Boolean);
  let reelles=[];
  const nouvelle=(age=0)=>{
    if(!reelles.length) reelles=duJour();
    const value=Math.random()<.3,txt=value && reelles.length && Math.random()<.7 ? reelles[Math.floor(Math.random()*reelles.length)]
      : (1.3+Math.random()*3.4).toFixed(2).replace('.',',');
    return {x:(Math.random()*2-1)*(L-6),z:(Math.random()*2-1)*(l-4),age,duree:5+Math.random()*4,txt,value};
  };
  const cotes=Array.from({length:14},()=>nouvelle(Math.random()*6));
  let couleurs={},visible=false,boucle=0,avant=0;
  const lireCouleurs=()=>{const c=getComputedStyle(document.documentElement);
    couleurs={encre:c.getPropertyValue('--texte').trim() || '#ECE9E1',vert:c.getPropertyValue('--vert').trim() || '#7FC496'};};
  const taille=()=>{toile.width=Math.round(toile.clientWidth*dpr);toile.height=Math.round(toile.clientHeight*dpr);};
  function dessiner(ms,dt){
    const W=toile.width,H=toile.height,t=ms/1000;if(!W || !H) return;
    if(!couleurs.encre || Math.random()<.01) lireCouleurs();
    const a=-.42+cvIncl.x*.35+Math.sin(t*.07)*.12,b=.52+cvIncl.y*.12,ca=Math.cos(a),sa=Math.sin(a),cb=Math.cos(b),sb=Math.sin(b);
    const f=W*.95,cx=W/2,cy=H*.34,D=128;
    const proj=(x,y,z)=>{const X=x*ca-z*sa,Z=x*sa+z*ca,Yv=y*cb+Z*sb,Zv=-y*sb+Z*cb+D;return [cx+X*f/Zv,cy-Yv*f/Zv,Zv];};
    ctx.clearRect(0,0,W,H);
    // Bandes de pelouse.
    ctx.fillStyle=couleurs.encre;
    for(let i=0;i<10;i+=2){
      const x0=-L+i*L/5,x1=x0+L/5,q=[proj(x0,0,-l),proj(x1,0,-l),proj(x1,0,l),proj(x0,0,l)];
      ctx.globalAlpha=.035;ctx.beginPath();q.forEach(([u,v],k)=>k?ctx.lineTo(u,v):ctx.moveTo(u,v));ctx.fill();
    }
    ctx.globalAlpha=.32;ctx.strokeStyle=couleurs.encre;ctx.lineWidth=1.2*dpr;
    for(const pl of lignes){ctx.beginPath();pl.forEach(([x,z],k)=>{const [u,v]=proj(x,0,z);k?ctx.lineTo(u,v):ctx.moveTo(u,v);});ctx.stroke();}
    // Cotes qui s'élèvent : les plus proches devant.
    for(const c of cotes){c.age+=dt;if(c.age>c.duree) Object.assign(c,nouvelle());}
    const vues=cotes.map(c=>{const p=c.age/c.duree,y=1+p*16;return {c,p,base:proj(c.x,0,c.z),haut:proj(c.x,y,c.z)};}).sort((u,v)=>v.haut[2]-u.haut[2]);
    for(const {c,p,base,haut} of vues){
      const alpha=Math.min(1,p*5,(1-p)*3),echelle=f/haut[2];
      const couleur=c.value?couleurs.vert:couleurs.encre;
      if(c.value){ // onde au sol à l'endroit où la value apparaît
        ctx.globalAlpha=alpha*.5*(1-p);ctx.strokeStyle=couleur;ctx.lineWidth=1.4*dpr;ctx.beginPath();
        ctx.ellipse(base[0],base[1],(2+p*10)*f/base[2],(2+p*10)*f/base[2]*sb,0,0,2*Math.PI);ctx.stroke();
      }
      ctx.globalAlpha=alpha*(c.value?.95:.38);ctx.strokeStyle=couleur;ctx.lineWidth=dpr;
      ctx.beginPath();ctx.moveTo(base[0],base[1]);ctx.lineTo(haut[0],haut[1]+2*dpr);ctx.stroke();
      ctx.fillStyle=couleur;ctx.font=`${c.value?600:400} ${Math.max(10*dpr,3.4*echelle)}px "Geist Mono",ui-monospace,monospace`;
      ctx.textAlign='center';ctx.fillText(c.txt,haut[0],haut[1]);
    }
    ctx.globalAlpha=1;
  }
  const tourner=ms=>{if(!visible || document.hidden){boucle=0;avant=0;return;}
    dessiner(ms,avant?Math.min(.05,(ms-avant)/1000):0);avant=ms;boucle=requestAnimationFrame(tourner);};
  const relancer=()=>{if(animationsPermises()){if(!boucle && visible && !document.hidden) boucle=requestAnimationFrame(tourner);}else dessiner(0,0);};
  new ResizeObserver(()=>{taille();relancer();if(!animationsPermises()) dessiner(0,0);}).observe(toile);
  new IntersectionObserver(([e])=>{visible=e.isIntersecting;relancer();}).observe(toile);
  document.addEventListener('visibilitychange',relancer);
  toile.classList.add('cv-champ-pret');
}
terrainDesCotes(document.querySelector('#o-accueil .une-tete'));

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
