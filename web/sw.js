// Pas de cache HTML ni d'interception réseau : les bilans restent servis à jour.
self.addEventListener('install',event=>event.waitUntil(self.skipWaiting()));
self.addEventListener('activate',event=>event.waitUntil(self.clients.claim()));
function openedDB() {
  return new Promise((resolve,reject)=>{
    const r=indexedDB.open('cotes-value-notifications',1);
    r.onupgradeneeded=()=>r.result.createObjectStore('seen',{keyPath:'id'});
    r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);
  });
}
async function claim(id) {
  const db=await openedDB();
  return new Promise((resolve,reject)=>{
    const tx=db.transaction('seen','readwrite'), store=tx.objectStore('seen');
    let duplicate=false;
    const r=store.add({id,at:Date.now()});
    r.onerror=e=>{if(r.error.name==='ConstraintError'){duplicate=true;e.preventDefault();e.stopPropagation();}};
    // Une semaine de dédoublonnage, sans accumuler indéfiniment sur le téléphone.
    const cursor=store.openCursor();cursor.onsuccess=()=>{const c=cursor.result;if(c){if(c.value.at<Date.now()-8*86400000)c.delete();c.continue();}};
    tx.oncomplete=()=>{db.close();resolve(!duplicate);};tx.onerror=()=>{db.close();reject(tx.error);};
  });
}
async function forget(id) {
  const db=await openedDB();const tx=db.transaction('seen','readwrite');tx.objectStore('seen').delete(id);
  await new Promise(r=>{tx.oncomplete=r;tx.onerror=r;});db.close();
}
self.addEventListener('push',event=>event.waitUntil((async()=>{
  let data;try{data=event.data.json();}catch{return;}
  if(!/^[a-f0-9]{64}$/.test(data.id||'') || Date.parse(data.expires_at)<=Date.now() ||
    !Number.isFinite(Date.parse(data.expires_at)) || !Number.isFinite(Date.parse(data.debut)) || Date.parse(data.debut)<=Date.now()) return;
  if(!await claim(data.id)) return;
  try {
    await self.registration.showNotification(String(data.title||'Cotes Value').slice(0,120),{
      body:String(data.body||'Nouvelle sélection').slice(0,500),tag:'cv-'+data.id,renotify:false,
      data:{id:data.id},timestamp:Date.now()
    });
  } catch {await forget(data.id);}
})()));
self.addEventListener('notificationclick',event=>{
  event.notification.close();
  event.waitUntil((async()=>{
    const url=new URL('./',self.registration.scope);url.searchParams.set('alerte',event.notification.data?.id||'');url.hash='jouer';
    for(const c of await self.clients.matchAll({type:'window',includeUncontrolled:true})) {
      if(c.url.startsWith(self.registration.scope) && 'focus' in c) {await c.navigate(url.href);return c.focus();}
    }
    return self.clients.openWindow(url.href);
  })());
});
