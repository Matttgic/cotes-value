import webpush from 'npm:web-push@3.6.7';
import {createRemoteJWKSet,jwtVerify} from 'npm:jose@6.1.0';
import {createHandler,validClaims,SITE} from './core.mjs';

const base=Deno.env.get('SUPABASE_URL')+'/rest/v1/';
const secret=Deno.env.get('SUPABASE_SERVICE_ROLE_KEY');
async function db(path,method='GET',body) {
  const r=await fetch(base+path,{method,headers:{apikey:secret,Authorization:`Bearer ${secret}`,
    'Content-Type':'application/json',Prefer:'return=representation,resolution=ignore-duplicates'},
    body:body===undefined?undefined:JSON.stringify(body)});
  if(!r.ok) throw new Error('database');
  const s=await r.text();return s?JSON.parse(s):null;
}
let cached;
async function config() {
  if(cached) return cached;
  let rows=await db('cv_push_config?id=eq.true');
  if(!rows.length) {
    await db('cv_push_config','POST',{id:true,value:webpush.generateVAPIDKeys()});
    rows=await db('cv_push_config?id=eq.true');
  }
  const value=rows[0].value;
  // Vérifie aussi la compatibilité du chiffrement Web Push avec ce runtime,
  // sans émettre de requête vers un service de notification.
  const browser=webpush.generateVAPIDKeys();
  webpush.generateRequestDetails({endpoint:'https://fcm.googleapis.com/fcm/send/crypto-self-test',
    keys:{p256dh:browser.publicKey,auth:btoa(String.fromCharCode(...crypto.getRandomValues(new Uint8Array(16))))}},
    JSON.stringify({test:true}),{vapidDetails:{subject:SITE,publicKey:value.publicKey,privateKey:value.privateKey},TTL:30});
  cached=value;return cached;
}
const jwks=createRemoteJWKSet(new URL('https://token.actions.githubusercontent.com/.well-known/jwks'));
async function authorize(header) {
  if(!header.startsWith('Bearer ')) return false;
  try {
    const {payload}=await jwtVerify(header.slice(7),jwks,{issuer:'https://token.actions.githubusercontent.com',
      audience:'cotes-value-notifications',algorithms:['RS256'],maxTokenAge:'10m'});
    return validClaims(payload);
  } catch {return false;}
}
async function send(subscription,payload,ttl) {
  try {
    const c=await config();
    const r=webpush.generateRequestDetails(subscription,JSON.stringify(payload),{
      vapidDetails:{subject:SITE,publicKey:c.publicKey,privateKey:c.privateKey},TTL:ttl,urgency:'high'});
    const response=await fetch(r.endpoint,{method:'POST',headers:r.headers,body:r.body,redirect:'error',signal:AbortSignal.timeout(10000)});
    return response.status;
  } catch {return 503;}
}
Deno.serve(createHandler({db,config,authorize,send}));
