import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';

const source=readFileSync(new URL('../web/actualisation.js',import.meta.url),'utf8');
const A='a'.repeat(64), B='b'.repeat(64);
const attendre=()=>new Promise(resolve=>setImmediate(resolve));
function page({stockage=new Map(), version=A, reponse=async()=>({ok:true,json:async()=>({version})}), href='https://example.test/cotes-value/#paris', bloque=false}={}) {
  const events={}, appels=[], navigations=[], restaurations=[];
  let temps=1000000, interv, protection=false;
  const document={visibilityState:'visible',addEventListener(n,fn){events[n]=fn;}};
  const ctx=vm.createContext({document,window:{addEventListener(n,fn){events[n]=fn;}},URL,AbortSignal,
    Date:{now:()=>temps},sessionStorage:{getItem:k=>{if(bloque)throw Error();return stockage.get(k);},setItem:(k,v)=>{if(bloque)throw Error();stockage.set(k,v);}},
    history:{replaceState(){}},location:{href,replace:url=>navigations.push(url)},
    setInterval(fn,ms){assert.equal(ms,60000);interv=fn;},
    fetch:async(url,opts)=>{appels.push({url,opts});return reponse();},
    config:{version,capturer:()=>({recherche:'Lyon',onglet:'paris'}),restaurer:s=>restaurations.push(s),protegee:()=>protection}});
  vm.runInContext(source+'\ninstallerActualisation(config);',ctx);
  return {events,appels,navigations,restaurations,stockage,document,tic(ms=60000){temps+=ms;return interv();},proteger(v){protection=v;}};
}
test('version identique : contrôle léger, événements groupés, aucun rechargement',async()=>{
  const p=page(); await attendre();
  p.events.focus();p.events.pageshow(); await attendre();
  assert.equal(p.appels.length,1);assert.equal(p.navigations.length,0);
  assert.equal(p.appels[0].opts.cache,'no-store');
  assert.equal(p.appels[0].url.pathname,'/cotes-value/version.json');
  p.document.visibilityState='hidden';await p.tic();assert.equal(p.appels.length,1);
  p.document.visibilityState='visible';await p.events.visibilitychange();assert.equal(p.appels.length,2);
});
test('nouvelle publication : cache contourné, adresse et état conservés puis restaurés une fois',async()=>{
  const p=page({reponse:async()=>({ok:true,json:async()=>({version:B})}),href:'https://example.test/cotes-value/?autre=1#paris'});
  await attendre();assert.equal(p.navigations.length,1);
  const url=new URL(p.navigations[0]);assert.equal(url.searchParams.get('_cv'),B);
  assert.equal(url.searchParams.get('autre'),'1');assert.equal(url.hash,'#paris');
  await p.tic();assert.equal(p.navigations.length,1);
  const q=page({stockage:p.stockage,version:B,href:url.href});await attendre();
  assert.equal(q.restaurations[0].recherche,'Lyon');assert.equal(q.navigations.length,0);
  const r=page({stockage:p.stockage,version:B});await attendre();assert.equal(r.restaurations.length,0);
});
test('hors ligne, HTTP en erreur et manifeste invalide : page conservée, reprise au retour réseau',async()=>{
  let etape=0;
  const p=page({reponse:async()=>{etape++;if(etape===1)throw Error('offline');return etape===2 ? {ok:false} : {ok:true,json:async()=>({version:etape===3?'invalide':B})};}});
  await attendre();await p.tic();await p.tic();assert.equal(p.navigations.length,0);
  await p.events.online();assert.equal(p.navigations.length,1);
});
test('pas de rechargement pendant les réglages, la saisie ou une requête déjà en cours',async()=>{
  let terminer;
  const p=page({reponse:()=>new Promise(r=>{terminer=r;})});
  await p.tic();assert.equal(p.appels.length,1);
  p.proteger(true);terminer({ok:true,json:async()=>({version:B})});await attendre();assert.equal(p.navigations.length,0);
  // Requête suivante résolue immédiatement, mais une saisie vient de commencer.
  p.proteger(false);const t=p.tic();p.events.input();terminer({ok:true,json:async()=>({version:B})});await t;
  assert.equal(p.navigations.length,0);
  const u=p.tic();terminer({ok:true,json:async()=>({version:B})});await u;assert.equal(p.navigations.length,1);
});
test('HTML encore ancien : garde-fou CDN même sans stockage disponible',async()=>{
  for(const bloque of [false,true]) {
    const p=page({bloque,href:'https://example.test/cotes-value/?_cv='+B,reponse:async()=>({ok:true,json:async()=>({version:B})})});
    await attendre();await p.tic();assert.equal(p.navigations.length,0);
    await p.tic(300000);assert.equal(p.navigations.length,1);
  }
});
