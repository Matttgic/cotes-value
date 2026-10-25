import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {webcrypto} from 'node:crypto';

const SOURCE=readFileSync(new URL('../web/pushover.js',import.meta.url),'utf8');
const NOMS={eden:'Eden','labo:PIN-1.3-2-e2-h12':'Pinnacle 1','labo:PIN-1.3-2-e2-h36':'Pinnacle 2','labo:POL-1.3-2-e2-h12':'Polymarket 1'};

// Page minimale : les éléments dont le script a besoin, et quelques cases cochables.
function page({serveur,stockage={}}) {
  const el=id=>({id,value:'',textContent:'',disabled:false,innerHTML:'',classList:{toggle(){}}});
  const elements=Object.fromEntries(['pushover-strategies','pushover-message','pushover-sauver','pushover-code','pushover-etat'].map(id=>[id,el(id)]));
  let cochees=new Set();
  elements['pushover-strategies'].querySelectorAll=()=>[...cochees].map(value=>({value}));
  const appels=[];
  const ctx={
    document:{getElementById:id=>elements[id]||null},
    D:{notifications:{api:'https://f.test/cv',strategies:NOMS,details:{}}},
    e:s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])),
    lire:k=>stockage[k]??null,ecrire:(k,v)=>{stockage[k]=v;},
    crypto:webcrypto,TextEncoder,AbortSignal,Set,JSON,Error,Promise,
    fetch:async(url,opts)=>{
      const action=url.split('/').pop(), corps=JSON.parse(opts.body);
      appels.push([action,corps]);
      const [status,json]=serveur(action,corps);
      return {ok:status<400,status,json:async()=>json};
    }};
  vm.createContext(ctx);
  const demarrer=async()=>{vm.runInContext(SOURCE,ctx);await new Promise(r=>setTimeout(r,20));};
  return {elements,appels,stockage,demarrer,cocher:(...cles)=>{cochees=new Set(cles);}};
}

test('premier enregistrement : le code est exigé, haché, mémorisé, et jamais envoyé en clair',async()=>{
  const p=page({serveur:(action)=>action==='pushover-lire'?[200,{defini:false,strategies:[]}]:[200,{ok:true}]});
  await p.demarrer();
  assert.match(p.elements['pushover-etat'].textContent,/Aucun choix enregistré/);
  assert.ok(p.elements['pushover-strategies'].innerHTML.includes('Pinnacle 1'));
  p.cocher('eden','labo:PIN-1.3-2-e2-h12');
  await p.elements['pushover-sauver'].onclick();
  assert.equal(p.appels.filter(a=>a[0]==='pushover-ecrire').length,0);                  // pas de code : rien d'envoyé
  assert.match(p.elements['pushover-message'].textContent,/au moins 8 caractères/);
  p.elements['pushover-code'].value='  mon-code-secret ';
  await p.elements['pushover-sauver'].onclick();
  const envoi=p.appels.find(a=>a[0]==='pushover-ecrire')[1];
  assert.deepEqual(envoi.strategies,['eden','labo:PIN-1.3-2-e2-h12']);
  assert.match(envoi.token,/^[0-9a-f]{64}$/);assert.ok(!JSON.stringify(envoi).includes('mon-code-secret'));
  assert.equal(p.stockage['cv-pushover-v1'],envoi.token);                                // mémorisé : pas à retaper
  assert.equal(p.elements['pushover-code'].value,'');
  assert.match(p.elements['pushover-message'].textContent,/Enregistré/);
  assert.match(p.elements['pushover-etat'].textContent,/2 stratégies/);
});

test('code mémorisé : on enregistre sans le retaper ; code refusé : il est oublié et signalé',async()=>{
  const jeton='a'.repeat(64);
  let accepte=true;
  const p=page({stockage:{'cv-pushover-v1':jeton},serveur:(action)=>action==='pushover-lire'?
    [200,{defini:true,strategies:['eden']}]:(accepte?[200,{ok:true}]:[403,{error:'Code personnel refusé'}])});
  await p.demarrer();
  assert.match(p.elements['pushover-etat'].textContent,/1 stratégie\./);
  assert.ok(p.elements['pushover-strategies'].innerHTML.includes('checked'));          // la case enregistrée est cochée
  p.cocher('eden','labo:PIN-1.3-2-e2-h36');
  await p.elements['pushover-sauver'].onclick();
  assert.equal(p.appels.find(a=>a[0]==='pushover-ecrire')[1].token,jeton);
  accepte=false;
  await p.elements['pushover-sauver'].onclick();
  assert.match(p.elements['pushover-message'].textContent,/Code personnel refusé/);
  assert.equal(p.stockage['cv-pushover-v1'],'');                                       // le mauvais code mémorisé est effacé
  assert.equal(p.elements['pushover-sauver'].disabled,false);
});

test('tout décocher est un choix valide, et un serveur muet laisse la page utilisable',async()=>{
  const p=page({stockage:{'cv-pushover-v1':'b'.repeat(64)},serveur:(action)=>action==='pushover-lire'?[200,{defini:true,strategies:['eden']}]:[200,{ok:true}]});
  await p.demarrer();
  p.cocher();
  await p.elements['pushover-sauver'].onclick();
  assert.deepEqual(p.appels.find(a=>a[0]==='pushover-ecrire')[1].strategies,[]);
  assert.match(p.elements['pushover-message'].textContent,/aucune alerte Pushover/);
  const panne=page({serveur:()=>[503,{error:'Service temporairement indisponible'}]});
  await panne.demarrer();
  assert.match(panne.elements['pushover-etat'].textContent,/indisponible/);
  assert.equal(panne.elements['pushover-sauver'].disabled,true);
});
