import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createECDH} from 'node:crypto';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {ORIGIN,createHandler,validSubscription,validAlert,alertsFor,validClaims,hash} from '../supabase/functions/cv-notifications/core.mjs';

const now=Date.parse('2026-10-15T15:00:00Z');
const iso=ms=>new Date(ms).toISOString();
const alert={id:'a'.repeat(64),strategies:['strategie','gemini'],labels:['Claude','Gemini'],
  validations:{strategie:iso(now-60000),gemini:iso(now-30000)},detecte:iso(now-30000),debut:iso(now+3600000),
  cote:2,match:'Paris – Madrid',pari:'Paris vainqueur',bookmaker:'PMU'};
const id='12345678-1234-4234-8234-123456789abc', token='b'.repeat(64);
const device={id,strategies:['strategie'],since_at:iso(now-120000),updated_at:iso(now),subscription:{}};
function sub() {
  const ec=createECDH('prime256v1');ec.generateKeys();
  return {endpoint:'https://fcm.googleapis.com/fcm/send/test-only-unregistered-endpoint',
    keys:{p256dh:ec.getPublicKey().toString('base64url'),auth:Buffer.alloc(16,1).toString('base64url')}};
}
const req=(action,body,origin=ORIGIN)=>new Request('https://example.test/cv-notifications/'+action,{
  method:body===undefined?'GET':'POST',headers:{Origin:origin,'Content-Type':'application/json'},
  body:body===undefined?undefined:JSON.stringify(body)});
function app(options={}) {
  return createHandler({db:async()=>[],config:async()=>({publicKey:'public',privateKey:'private'}),
    authorize:async()=>false,send:async()=>201,clock:()=>now,...options});
}

test('les abonnements ne peuvent pas faire des requêtes vers un serveur arbitraire',()=>{
  assert.ok(validSubscription(sub()));
  for(const endpoint of ['http://fcm.googleapis.com/fcm/send/x','https://127.0.0.1/private',
    'https://fcm.googleapis.com.evil.test/fcm/send/x','https://fcm.googleapis.com:444/fcm/send/x',
    'https://user:pass@fcm.googleapis.com/fcm/send/x']) assert.equal(validSubscription({...sub(),endpoint}),false);
  assert.equal(validSubscription({...sub(),keys:{p256dh:'bad',auth:'bad'}}),false);
});
test('les dates et votes propres à chaque stratégie empêchent les alertes rétroactives',()=>{
  assert.ok(validAlert(alert,now));
  assert.equal(alertsFor(device,[alert],now).length,1);
  assert.equal(alertsFor({...device,strategies:['strategie'],since_at:iso(now-45000)},[alert],now).length,0);
  assert.equal(alertsFor({...device,strategies:['gemini'],since_at:iso(now-45000)},[alert],now).length,1);
  for(const change of [{debut:iso(now-1)},{detecte:iso(now-16*60000)},
    {cote:NaN},{strategies:['Inconnue !']},{strategies:['labo:x']},{strategies:Array(65).fill('strategie')},{labels:undefined},{validations:{}}]) assert.equal(validAlert({...alert,...change},now),false);
});
test('seul le workflow de collecte du dépôt et de la branche autorisés est accepté',()=>{
  const p={repository_id:'1404917041',repository_owner_id:'183744829',repository:'Matttgic/cotes-value',
    ref:'refs/heads/ccr-148b8ccc-phitmr',workflow_ref:'Matttgic/cotes-value/.github/workflows/collecte.yml@refs/heads/ccr-148b8ccc-phitmr',event_name:'workflow_dispatch'};
  assert.ok(validClaims(p));
  for(const change of [{repository_id:'2'},{repository_owner_id:'2'},{repository_owner_id:undefined},{ref:'refs/heads/other'},{workflow_ref:'other'},{event_name:'pull_request'}]) assert.equal(validClaims({...p,...change}),false);
});
test('CORS, authentification des envois et clé privée protégée',async()=>{
  const handler=app();
  assert.equal((await handler(req('dispatch',{alertes:[]}))).status,401);
  assert.equal((await handler(req('subscribe',{id,token},'https://evil.test'))).status,403);
  const config=await (await handler(req('config'))).json();
  assert.equal(config.publicKey,'public');assert.equal(config.privateKey,undefined);
});
test('inscription valide, jeton haché et choix de stratégies contrôlés',async()=>{
  let saved;
  const handler=app({db:async(path,method,body)=>{saved={path,method,body};return true;}});
  const r=await handler(req('subscribe',{id,token,strategies:['claude_prudent'],subscription:sub()}));
  assert.equal(r.status,200);assert.equal(saved.body.p_token,await hash(token));
  assert.notEqual(saved.body.p_token,token);
  assert.equal((await handler(req('subscribe',{id,token,strategies:[],subscription:sub()}))).status,400);
});
test('un même pari éligible à plusieurs stratégies produit une seule livraison',async()=>{
  const claims=new Set();let sent=0;
  const handler=app({authorize:async()=>true,send:async()=>{sent++;return 201;},
    db:async(path,method,body)=>{
      if(path.startsWith('cv_push_devices?enabled')) return [device];
      if(path==='rpc/cv_push_claim') {if(claims.has(body.p_alert)) return false;claims.add(body.p_alert);return true;}
      return [];
    }});
  const feed={generated_at:iso(now),alertes:[alert,alert]};
  assert.equal((await (await handler(req('dispatch',feed))).json()).sent,1);
  await handler(req('dispatch',feed));assert.equal(sent,1);
  assert.equal((await handler(req('dispatch',{...feed,generated_at:iso(now-11*60000)}))).status,400);
});
test('abonnement expiré supprimé sans réessayer les autres paris du même appareil',async()=>{
  let removed=0,sent=0;
  const handler=app({authorize:async()=>true,send:async()=>{sent++;return 410;},
    db:async(path,method)=>{
      if(path.startsWith('cv_push_devices?enabled')) return [device];
      if(path==='rpc/cv_push_claim') return true;
      if(path.startsWith('cv_push_devices?') && method==='DELETE') removed++;
      return [];
    }});
  const r=await handler(req('dispatch',{generated_at:iso(now),alertes:[alert,{...alert,id:'c'.repeat(64)}]}));
  assert.equal(r.status,200);assert.equal(removed,1);assert.equal(sent,1);
});
test('le service worker refuse les doublons et les notifications périmées',async()=>{
  const handlers={},seen=new Set(),shown=[];
  const ctx={Date,self:{addEventListener:(type,fn)=>{handlers[type]=fn;},
    registration:{showNotification:async(...a)=>shown.push(a)}}};
  vm.createContext(ctx);vm.runInContext(readFileSync(new URL('../web/sw.js',import.meta.url),'utf8'),ctx);
  ctx.claim=async id=>{if(seen.has(id)) return false;seen.add(id);return true;};
  async function push(data) {let work;handlers.push({data:{json:()=>data},waitUntil:p=>{work=p;}});await work;}
  const packet={id:'a'.repeat(64),title:'PMU 2,00',body:'Test',debut:iso(Date.now()+3600000),expires_at:iso(Date.now()+300000)};
  await push(packet);await push(packet);assert.equal(shown.length,1);
  await push({...packet,id:'b'.repeat(64),expires_at:iso(Date.now()-1)});assert.equal(shown.length,1);
  await push({...packet,id:'c'.repeat(64),debut:'invalide'});assert.equal(shown.length,1);
});

test('M3 Max 3 est un choix distinct, sans abonnement automatique',()=>{
  const a={...alert,strategies:['m3_structure'],labels:['M3 Max 3'],validations:{m3_structure:iso(now-30000)}};
  assert.ok(validAlert(a,now));
  assert.equal(alertsFor({...device,strategies:['m3']},[a],now).length,0);
  assert.equal(alertsFor({...device,strategies:['m3_structure']},[a],now).length,1);
});


test('Eden et les règles du laboratoire (Pinnacle 2…) sont acceptées sans liste figée',async()=>{
  const a={...alert,strategies:['eden','labo:PIN-1.3-2-e2-h36'],labels:['Eden','Pinnacle 2'],
    validations:{eden:iso(now-30000),'labo:PIN-1.3-2-e2-h36':iso(now-30000)}};
  assert.ok(validAlert(a,now));
  assert.equal(alertsFor({...device,strategies:['labo:PIN-1.3-2-e2-h36']},[a],now).length,1);
  assert.equal(alertsFor({...device,strategies:['labo:PIN-1.3-2-e2-h12']},[a],now).length,0);
  let saved;
  const handler=app({db:async(path,method,body)=>{saved=body;return true;}});
  const r=await handler(req('subscribe',{id,token,strategies:['labo:POL-2-5-e5-h36','eden'],subscription:sub()}));
  assert.equal(r.status,200);assert.deepEqual(saved.p_strategies,['labo:POL-2-5-e5-h36','eden']);
  assert.equal((await handler(req('subscribe',{id,token,strategies:['labo:../x'],subscription:sub()}))).status,400);
});

test('le corps est limité en octets avant lecture complète, même avec une taille mensongère',async()=>{
  for(const contentLength of [undefined,'0']) {
    let pulls=0,cancelled=false,calls=0;
    const stream=new ReadableStream({
      pull(controller) {pulls++;controller.enqueue(new TextEncoder().encode('é'.repeat(60000)));},
      cancel() {cancelled=true;}
    });
    const headers={Origin:ORIGIN};if(contentLength!==undefined) headers['Content-Length']=contentLength;
    const request=new Request('https://example.test/cv-notifications/subscribe',{
      method:'POST',headers,body:stream,duplex:'half'});
    const handler=app({db:async()=>{calls++;return [];}});
    const result=await handler(request);
    assert.equal(result.status,413);assert.ok(cancelled);assert.ok(pulls<=3);
    assert.equal(calls,0);assert.equal(result.headers.get('Cache-Control'),'no-store');
    assert.equal(result.headers.get('X-Content-Type-Options'),'nosniff');
  }
});

test('une requête UTF-8 découpée en milieu de caractère reste valide',async()=>{
  const bytes=new TextEncoder().encode(JSON.stringify({id,token,strategies:['strategie'],subscription:sub(),note:'équipe'}));
  const position=bytes.indexOf(0xc3)+1;
  const stream=new ReadableStream({start(c){c.enqueue(bytes.slice(0,position));c.enqueue(bytes.slice(position));c.close();}});
  const request=new Request('https://example.test/cv-notifications/subscribe',{
    method:'POST',headers:{Origin:ORIGIN},body:stream,duplex:'half'});
  const r=await app({db:async()=>true})(request);
  assert.equal(r.status,200);
});

test('le service worker ne crée aucun cache réseau et les requêtes privées évitent le cache',()=>{
  const handlers={};const ctx={self:{addEventListener:(type,fn)=>{handlers[type]=fn;}}};
  vm.createContext(ctx);vm.runInContext(readFileSync(new URL('../web/sw.js',import.meta.url),'utf8'),ctx);
  assert.equal(handlers.fetch,undefined);
  const code=readFileSync(new URL('../web/notifications.js',import.meta.url),'utf8');
  assert.ok(code.includes("method:'POST',cache:'no-store',credentials:'omit'"));
});

test('le lien du match n\'est transmis que s\'il est sûr',async()=>{
  const {lienSur}=await import('../supabase/functions/cv-notifications/core.mjs');
  assert.equal(lienSur('https://www.winamax.fr/paris-sportifs/match/68932762'),'https://www.winamax.fr/paris-sportifs/match/68932762');
  assert.ok(lienSur('https://www.betclic.fr/football-s1/ligue-1-c4/lens-lille-m123').startsWith('https://www.betclic.fr/'));
  assert.ok(lienSur('https://www.google.com/search?q=site%3Awww.betclic.fr+Lens+Lille'));
  for(const mauvais of [null,undefined,42,'','http://www.winamax.fr/x','javascript:alert(1)','https://evil.example/winamax.fr',
    'https://winamax.fr.evil.example/x','https://user:mdp@www.winamax.fr/x','https://www.winamax.fr:8443/x',
    'https://www.google.com/url?q=https://evil.example','https://notwinamax.fr/x','https://www.winamax.fr/'+'a'.repeat(700)])
    assert.equal(lienSur(mauvais),null,String(mauvais).slice(0,60));
});

test('la notification envoyée porte l\'adresse du match, ou rien',async()=>{
  const sentPackets=[];
  const run=async lien=>{
    const handler=createHandler({db:async path=>path.startsWith('cv_push_devices?enabled')?[device]:path==='rpc/cv_push_claim'?true:[],
      config:async()=>({publicKey:'x'}),authorize:async()=>true,send:async(sub,packet)=>{sentPackets.push(packet);return 201;},clock:()=>now});
    await handler(req('dispatch',{generated_at:iso(now),alertes:[{...alert,...(lien===undefined?{}:{lien})}]}));
    return sentPackets.at(-1);
  };
  assert.equal((await run('https://www.winamax.fr/paris-sportifs/match/1')).url,'https://www.winamax.fr/paris-sportifs/match/1');
  assert.equal('url' in await run('http://www.winamax.fr/x'),false);
  assert.equal('url' in await run(undefined),false);
});

test('toucher la notification ouvre le match chez le bookmaker, le bouton ouvre le site',async()=>{
  const handlers={},ouvertes=[];
  const ctx={URL,Date,self:{addEventListener:(type,fn)=>{handlers[type]=fn;},
    registration:{scope:'https://matttgic.github.io/cotes-value/',showNotification:async(...a)=>ouvertes.push(['montree',...a])},
    clients:{matchAll:async()=>[],openWindow:async u=>{ouvertes.push(['ouverte',u]);},claim:async()=>{}}}};
  vm.createContext(ctx);vm.runInContext(readFileSync(new URL('../web/sw.js',import.meta.url),'utf8'),ctx);
  const clic=async(action,url)=>{let work;handlers.notificationclick({action,notification:{close(){},data:{id:'a'.repeat(64),url}},waitUntil:p=>{work=p;}});await work;};
  await clic('', 'https://www.betclic.fr/football-s1/x-c1/y-m2');
  await clic('site','https://www.betclic.fr/football-s1/x-c1/y-m2');
  await clic('', 'https://evil.example/x');
  await clic('', null);
  assert.deepEqual(ouvertes.map(o=>o[1]),['https://www.betclic.fr/football-s1/x-c1/y-m2',
    'https://matttgic.github.io/cotes-value/?alerte='+'a'.repeat(64)+'#paris',
    'https://matttgic.github.io/cotes-value/?alerte='+'a'.repeat(64)+'#paris',
    'https://matttgic.github.io/cotes-value/?alerte='+'a'.repeat(64)+'#paris']);
});
