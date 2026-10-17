export const ORIGIN = 'https://matttgic.github.io';
export const SITE = ORIGIN + '/cotes-value/';
export const STRATEGIES = ['strategie','chatgpt','gemini','jules','jules_v2','m3','convergence','claude_prudent','convergence_3','m3_structure'];
export const hash = async s => [...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(s)))].map(x=>x.toString(16).padStart(2,'0')).join('');
const date = x => typeof x==='string' ? Date.parse(x) : NaN;
export function validSubscription(s) {
  try {
    const u = new URL(s.endpoint);
    if (u.protocol!=='https:' || u.port || u.username || u.password ||
      !['fcm.googleapis.com','updates.push.services.mozilla.com','web.push.apple.com'].includes(u.hostname) || u.pathname.length<10) return false;
    return [['p256dh',65],['auth',16]].every(([k,n])=>{
      const v=s.keys[k];
      if (typeof v!=='string' || !/^[A-Za-z0-9_-]+={0,2}$/.test(v)) return false;
      const b=atob(v.replace(/-/g,'+').replace(/_/g,'/'));
      return b.length===n && (k!=='p256dh' || b.charCodeAt(0)===4);
    });
  } catch { return false; }
}
export function validAlert(a,now=Date.now()) {
  return a && /^[a-f0-9]{64}$/.test(a.id) && Array.isArray(a.strategies) &&
    a.strategies.length>0 && a.strategies.every(s=>STRATEGIES.includes(s)) &&
    Array.isArray(a.labels) && a.labels.length<=STRATEGIES.length && a.labels.every(s=>typeof s==='string' && s.length<=80) &&
    a.validations && a.strategies.every(s=>Number.isFinite(date(a.validations[s]))) &&
    Number.isFinite(a.cote) && a.cote>1 && a.cote<=100 &&
    ['match','pari','bookmaker'].every(k=>typeof a[k]==='string' && a[k].length>0 && a[k].length<=250) &&
    date(a.debut)>now+60000 && date(a.detecte)<=now+60000 && date(a.detecte)>=now-15*60000;
}
export function alertsFor(device,alerts,now=Date.now()) {
  return alerts.filter(a=>validAlert(a,now) && a.strategies.some(s=>device.strategies.includes(s) &&
    date(a.validations[s])>=date(device.since_at) && date(a.validations[s])>=now-15*60000 && date(a.validations[s])<=now+60000));
}
export function validClaims(p) {
  return p.repository_id==='1404917041' && p.repository_owner_id &&
    p.repository==='Matttgic/cotes-value' && p.ref==='refs/heads/ccr-148b8ccc-phitmr' &&
    p.workflow_ref==='Matttgic/cotes-value/.github/workflows/collecte.yml@refs/heads/ccr-148b8ccc-phitmr' &&
    ['push','schedule','workflow_dispatch'].includes(p.event_name);
}
export function createHandler({db,config,authorize,send,clock=Date.now}) {
  return async req => {
    const origin=req.headers.get('Origin');
    const headers={'Content-Type':'application/json','Cache-Control':'no-store','Vary':'Origin'};
    if(origin===ORIGIN) Object.assign(headers,{'Access-Control-Allow-Origin':ORIGIN,
      'Access-Control-Allow-Headers':'content-type,authorization','Access-Control-Allow-Methods':'GET,POST,OPTIONS'});
    const reply=(obj,status=200)=>new Response(JSON.stringify(obj),{status,headers});
    if(origin && origin!==ORIGIN) return reply({error:'Origine refusée'},403);
    if(req.method==='OPTIONS') return new Response(null,{status:204,headers});
    const action=new URL(req.url).pathname.split('/').pop();
    try {
      if(req.method==='GET' && action==='config') {
        const c=await config(); return reply({publicKey:c.publicKey,strategies:STRATEGIES});
      }
      if(req.method!=='POST') return reply({error:'Méthode refusée'},405);
      if(action==='dispatch') {
        if(!await authorize(req.headers.get('Authorization')||'')) return reply({error:'Accès refusé'},401);
      } else if(origin!==ORIGIN) return reply({error:'Origine requise'},403);
      if(Number(req.headers.get('Content-Length')||0)>200000) return reply({error:'Requête trop grande'},413);
      const raw=await req.text();
      if(raw.length>200000) return reply({error:'Requête trop grande'},413);
      let body; try {body=JSON.parse(raw);} catch {return reply({error:'JSON invalide'},400);}
      if(!body || typeof body!=='object' || Array.isArray(body)) return reply({error:'Requête invalide'},400);
      const now=clock();
      if(action==='dispatch') {
        if(!Array.isArray(body.alertes) || body.alertes.length>100 ||
          !Number.isFinite(date(body.generated_at)) || Math.abs(now-date(body.generated_at))>10*60000)
          return reply({error:'Relevé périmé ou invalide'},400);
        let sent=0,expired=0,failed=0;
        const devices=await db('cv_push_devices?enabled=eq.true&select=*');
        for(const d of devices) {
          if(now-date(d.updated_at)>90*86400000) {await db(`cv_push_devices?id=eq.${d.id}`,'DELETE');continue;}
          for(const a of alertsFor(d,body.alertes,now)) {
            if(!await db('rpc/cv_push_claim','POST',{p_device:d.id,p_alert:a.id})) continue;
            const ttl=Math.max(1,Math.min(300,Math.floor((date(a.debut)-now)/1000)));
            const result=await send(d.subscription,{
              id:a.id,title:`${a.bookmaker} · ${a.cote.toFixed(2).replace('.',',')}`,
              body:`${a.match}\n${a.pari}\n${a.labels.join(' · ')}`.slice(0,500),
              debut:a.debut,expires_at:new Date(now+ttl*1000).toISOString()
            },ttl);
            if(result>=200 && result<300) {
              await db(`cv_push_deliveries?device_id=eq.${d.id}&alert_id=eq.${a.id}`,'PATCH',{sent_at:new Date(now).toISOString()});sent++;
            } else if(result===404 || result===410) {await db(`cv_push_devices?id=eq.${d.id}`,'DELETE');expired++;break;}
            else failed++;
          }
        }
        await db(`cv_push_deliveries?claimed_at=lt.${encodeURIComponent(new Date(now-8*86400000).toISOString())}`,'DELETE');
        return reply({ok:failed===0,sent,expired,failed,devices:devices.length});
      }
      if(!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(body.id||'') || !/^[0-9a-f]{64}$/.test(body.token||''))
        return reply({error:'Identité appareil invalide'},400);
      const token=await hash(body.token);
      if(action==='subscribe') {
        if(!validSubscription(body.subscription) || !Array.isArray(body.strategies) ||
          body.strategies.length<1 || body.strategies.length>STRATEGIES.length || body.strategies.some(s=>!STRATEGIES.includes(s)))
          return reply({error:'Abonnement ou stratégies invalides'},400);
        const ok=await db('rpc/cv_push_register','POST',{p_id:body.id,p_token:token,
          p_endpoint:await hash(body.subscription.endpoint),p_subscription:body.subscription,p_strategies:[...new Set(body.strategies)]});
        return reply(ok?{ok:true}:{error:'Appareil refusé ou limite atteinte'},ok?200:409);
      }
      const rows=await db(`cv_push_devices?id=eq.${body.id}&token_hash=eq.${token}&select=*`);
      const d=rows[0]; if(!d) return reply({error:'Abonnement introuvable'},404);
      if(action==='status') return reply({enabled:d.enabled,strategies:d.strategies,since:d.since_at});
      if(action==='unsubscribe') {await db(`cv_push_devices?id=eq.${d.id}`,'DELETE');return reply({ok:true});}
      if(action==='test') {
        if(d.test_at && now-date(d.test_at)<30000) return reply({error:'Attends 30 secondes entre deux tests'},429);
        const claimed=await db(`cv_push_devices?id=eq.${d.id}&or=(test_at.is.null,test_at.lt.${encodeURIComponent(new Date(now-30000).toISOString())})`,'PATCH',{test_at:new Date(now).toISOString()});
        if(!claimed.length) return reply({error:'Attends 30 secondes entre deux tests'},429);
        const result=await send(d.subscription,{id:await hash('test|'+d.id+'|'+now),
          title:'Test Cotes Value',body:'Notifications Chrome actives sur cet appareil.',
          debut:new Date(now+3600000).toISOString(),expires_at:new Date(now+300000).toISOString()},300);
        if(result===404 || result===410) await db(`cv_push_devices?id=eq.${d.id}`,'DELETE');
        return reply(result>=200&&result<300?{ok:true}:{error:'Envoi impossible : réactive les notifications'},result>=200&&result<300?200:502);
      }
      return reply({error:'Action inconnue'},404);
    } catch {return reply({error:'Service temporairement indisponible'},503);}
  };
}
