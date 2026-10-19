// Intégré dans l'unique script de la page. Aucun suivi des prix en arrière-plan :
// le serveur envoie les nouvelles prises issues des scans GitHub Actions.
(async function notifications() {
  const ui=document.getElementById('notif-etat'), message=document.getElementById('notif-message');
  const activer=document.getElementById('notif-activer'), arreter=document.getElementById('notif-arreter');
  const sauver=document.getElementById('notif-sauver'), tester=document.getElementById('notif-test');
  const key='cv-notifications-v1', api=D.notifications.api;
  let device;
  try {device=JSON.parse(lire(key)||'null');} catch {}
  const supported=isSecureContext && 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
  const noms=D.notifications.strategies;
  const selected=new Set(device?.strategies || ['claude_prudent']);
  document.getElementById('notif-strategies').innerHTML='<legend>Stratégies à suivre</legend>'+Object.entries(noms).map(([k,v])=>
    `<label class="notif-choix"><span>${e(v)}${k==='claude_prudent'?'<small>1 pari par match, 10 par jour au plus</small>':''}${k==='m3'?'<small>Exploratoire</small>':''}</span><input type="checkbox" role="switch" class="interrupteur" value="${e(k)}" ${selected.has(k)?'checked':''}></label>`).join('');
  const choices=()=>[...document.querySelectorAll('#notif-strategies input:checked')].map(x=>x.value);
  const say=(s,bad=false)=>{message.textContent=s;message.classList.toggle('neg',bad);};
  function render() {
    const active=!!device?.enabled && Notification.permission==='granted';
    ui.textContent=!supported?'Notifications indisponibles ici. Ouvre le site dans Chrome sur Android.':
      Notification.permission==='denied'?'Notifications bloquées. Autorise-les dans les paramètres du site de Chrome.':
      active?'Notifications activées sur cet appareil.':'Notifications désactivées sur cet appareil.';
    activer.disabled=!supported || Notification.permission==='denied';
    activer.hidden=active; arreter.hidden=!device?.enabled;
    sauver.disabled=!active; tester.disabled=!active;
  }
  function persist() {
    const s=JSON.stringify(device);ecrire(key,s);
    if(lire(key)!==s) throw Error('Autorise le stockage du site pour enregistrer cet appareil.');
  }
  async function request(action,extra={}) {
    const r=await fetch(api+'/'+action,{method:'POST',cache:'no-store',credentials:'omit',referrerPolicy:'no-referrer',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({id:device?.id,token:device?.token,...extra}),signal:AbortSignal.timeout(15000)});
    const d=await r.json();if(!r.ok) {const error=Error(d.error||'Service indisponible');error.status=r.status;throw error;}return d;
  }
  const bytes=s=>Uint8Array.from(atob(s.replace(/-/g,'+').replace(/_/g,'/')),c=>c.charCodeAt(0));
  let registration;
  async function worker() {
    registration ||= await navigator.serviceWorker.register('./sw.js',{scope:'./',updateViaCache:'none'});
    await navigator.serviceWorker.ready;return registration;
  }
  async function save() {
    const strategies=choices();if(!strategies.length) throw Error('Choisis au moins une stratégie.');
    const reg=await worker(), subscription=await reg.pushManager.getSubscription();
    if(!subscription) throw Error('Réactive les notifications sur cet appareil.');
    await request('subscribe',{strategies,subscription:subscription.toJSON()});
    device.strategies=strategies;device.enabled=true;persist();render();
  }
  async function busy(button,fn) {
    button.disabled=true;say('');
    try {await fn();} catch(err) {say(err.message||'Service indisponible. Réessaie.',true);}
    finally {render();}
  }
  activer.onclick=()=>busy(activer,async()=>{
    if(!choices().length) throw Error('Choisis au moins une stratégie.');
    // Permission demandée directement après le clic, avant tout appel réseau.
    const permission=await Notification.requestPermission();
    if(permission!=='granted') throw Error('Autorisation non accordée. Tu peux réessayer depuis les paramètres Chrome.');
    const fresh=!device;
    if(fresh) {
      device={id:crypto.randomUUID(),token:[...crypto.getRandomValues(new Uint8Array(32))].map(x=>x.toString(16).padStart(2,'0')).join(''),enabled:false,strategies:choices()};
      persist();
    }
    const r=await fetch(api+'/config',{cache:'no-store',signal:AbortSignal.timeout(15000)});
    if(!r.ok) throw Error('Service de notification indisponible. Réessaie.');
    const config=await r.json(), reg=await worker();
    let sub=await reg.pushManager.getSubscription();
    if(sub && (fresh || (sub.options.applicationServerKey &&
      String(new Uint8Array(sub.options.applicationServerKey))!==String(bytes(config.publicKey))))) {
      await sub.unsubscribe();sub=null;
    }
    if(!sub) await reg.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:bytes(config.publicKey)});
    await save();say('Activé. Tu recevras les nouvelles sélections de tes stratégies à partir des prochains scans.');
  });
  sauver.onclick=()=>busy(sauver,async()=>{await save();say('Stratégies enregistrées. Les alertes commencent à partir de maintenant.');});
  tester.onclick=()=>busy(tester,async()=>{await request('test');say('Test envoyé. Vérifie la notification Chrome sur ton téléphone.');});
  arreter.onclick=()=>busy(arreter,async()=>{
    let error;
    try {await request('unsubscribe');} catch(err) {error=err;}
    const reg=await worker(), sub=await reg.pushManager.getSubscription();
    if(sub && !await sub.unsubscribe()) throw Error('Désactivation impossible. Réessaie.');
    device.enabled=false;persist();
    say(error?'Arrêté sur cet appareil. Le serveur n’a pas confirmé la suppression.':'Notifications désactivées.');
  });
  if(!supported) {activer.disabled=true;sauver.disabled=true;tester.disabled=true;ui.textContent='Notifications indisponibles ici. Ouvre le site dans Chrome sur Android.';return;}
  render();
  if(device?.enabled && Notification.permission==='granted') {
    try {
      const status=await request('status'), sub=await (await worker()).pushManager.getSubscription();
      if(!status.enabled || !sub) {device.enabled=false;persist();render();}
    } catch(error) {
      if(error.status===404) {device.enabled=false;persist();render();say('Abonnement expiré : clique sur Activer pour le rétablir.',true);}
      else say('Vérification du serveur indisponible. Tes réglages locaux sont conservés ; réessaie plus tard.',true);
    }
  }
})().catch(()=>{document.getElementById('notif-etat').textContent='Notifications momentanément indisponibles. Recharge la page pour réessayer.';});
