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

// Champ 3D : une grille de points qui ondule comme un marché ; les crêtes s'allument à l'orange de la value.
function champValue(hote) {
  if(!hote || hote.querySelector('.cv-champ')) return;
  const toile=document.createElement('canvas');toile.className='cv-champ';toile.setAttribute('aria-hidden','true');
  const gl=toile.getContext('webgl',{premultipliedAlpha:true,antialias:false,alpha:true});
  if(!gl) return;
  hote.prepend(toile);
  const vs=`attribute vec2 p;uniform float t,asp,dpr;uniform vec2 inc;varying float h,d;
void main(){float x=p.x*1.9,z=p.y*1.9;
float y=.17*sin(x*2.1+t*.8)+.13*sin(z*2.9-t*.6)+.09*sin((x+z)*4.2+t*1.25)+.05*sin(length(vec2(x,z))*6.-t*1.6);
h=y;float a=.5+inc.x*.35+t*.03;float c=cos(a),s=sin(a);vec3 v=vec3(x*c-z*s,y,x*s+z*c);
float b=.62+inc.y*.18;float cb=cos(b),sb=sin(b);v=vec3(v.x,v.y*cb-v.z*sb,v.y*sb+v.z*cb);v.z+=2.5;d=v.z;
gl_Position=vec4(v.x*2.3/asp,v.y*2.3+.05,0.,v.z);gl_PointSize=dpr*(1.6+6.*smoothstep(.2,.38,y))*2.6/v.z;}`;
  const fs=`precision mediump float;uniform vec3 encre,signal;varying float h,d;
void main(){vec2 c=gl_PointCoord-.5;float r=length(c);if(r>.5)discard;float pic=smoothstep(.2,.36,h);
float a=(1.-smoothstep(.15,.5,r))*mix(.5,1.,pic)*clamp(1.9-(d-1.8)*.8,0.,1.);gl_FragColor=vec4(mix(encre,signal,pic)*a,a);}`;
  const shader=(type,src)=>{const s=gl.createShader(type);gl.shaderSource(s,src);gl.compileShader(s);return s;};
  const prog=gl.createProgram();
  gl.attachShader(prog,shader(gl.VERTEX_SHADER,vs));gl.attachShader(prog,shader(gl.FRAGMENT_SHADER,fs));gl.linkProgram(prog);
  if(!gl.getProgramParameter(prog,gl.LINK_STATUS)) {toile.remove();return;}
  gl.useProgram(prog);
  const N=96,M=64,pts=new Float32Array(N*M*2);
  for(let i=0;i<N;i++) for(let j=0;j<M;j++){pts[(i*M+j)*2]=i/(N-1)*2-1;pts[(i*M+j)*2+1]=j/(M-1)*2-1;}
  gl.bindBuffer(gl.ARRAY_BUFFER,gl.createBuffer());gl.bufferData(gl.ARRAY_BUFFER,pts,gl.STATIC_DRAW);
  const loc=gl.getAttribLocation(prog,'p');gl.enableVertexAttribArray(loc);gl.vertexAttribPointer(loc,2,gl.FLOAT,false,0,0);
  const u=n=>gl.getUniformLocation(prog,n);
  gl.enable(gl.BLEND);gl.blendFunc(gl.ONE,gl.ONE_MINUS_SRC_ALPHA);
  const rgb=v=>{const m=getComputedStyle(document.documentElement).getPropertyValue(v).trim().match(/^#?([\da-f]{6})$/i);
    const n=parseInt(m ? m[1] : 'ECE9E1',16);return [(n>>16&255)/255,(n>>8&255)/255,(n&255)/255];};
  let couleurs=0,visible=false,boucle=0;const dpr=Math.min(2,devicePixelRatio || 1);
  const taille=()=>{toile.width=Math.round(toile.clientWidth*dpr);toile.height=Math.round(toile.clientHeight*dpr);};
  new ResizeObserver(()=>{taille();if(!animationsPermises()) dessiner(4000);}).observe(toile);
  function dessiner(ms){
    if(couleurs++%90===0){gl.uniform3fv(u('encre'),rgb('--texte'));gl.uniform3fv(u('signal'),rgb('--signal'));}
    gl.viewport(0,0,toile.width,toile.height);gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT);
    gl.uniform1f(u('t'),ms/1000);gl.uniform1f(u('asp'),toile.width/Math.max(1,toile.height));gl.uniform1f(u('dpr'),dpr);
    gl.uniform2f(u('inc'),cvIncl.x,cvIncl.y);gl.drawArrays(gl.POINTS,0,N*M);
  }
  const tourner=ms=>{if(!visible || document.hidden){boucle=0;return;}dessiner(ms);boucle=requestAnimationFrame(tourner);};
  const relancer=()=>{if(animationsPermises()){if(!boucle && visible && !document.hidden) boucle=requestAnimationFrame(tourner);}else dessiner(4000);};
  new IntersectionObserver(([e])=>{visible=e.isIntersecting;relancer();}).observe(toile);
  document.addEventListener('visibilitychange',relancer);
  toile.classList.add('cv-champ-pret');
}
champValue(document.querySelector('#o-accueil .une-tete'));
