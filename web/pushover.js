// Choix des stratégies envoyées par Pushover : enregistrés sur le serveur avec un code personnel, sans abonnement Chrome.
// Le job GitHub lit ce choix à chaque cycle (action « strategies » de la fonction cv-notifications).
(async function pushover() {
  const zone=document.getElementById('pushover-strategies'), message=document.getElementById('pushover-message');
  const sauver=document.getElementById('pushover-sauver'), code=document.getElementById('pushover-code');
  const etat=document.getElementById('pushover-etat');
  if(!zone) return;
  const api=D.notifications.api, cleCode='cv-pushover-v1';
  const noms=D.notifications.strategies, details=D.notifications.details||{};
  const say=(s,bad=false)=>{message.textContent=s;message.classList.toggle('neg',bad);};
  const empreinte=async s=>[...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode('cotes-value-pushover:'+s)))]
    .map(x=>x.toString(16).padStart(2,'0')).join('');
  async function appeler(action,corps) {
    const r=await fetch(api+'/'+action,{method:'POST',cache:'no-store',credentials:'omit',referrerPolicy:'no-referrer',
      headers:{'Content-Type':'application/json'},body:JSON.stringify(corps),signal:AbortSignal.timeout(15000)});
    const d=await r.json().catch(()=>({}));
    if(!r.ok) {const erreur=Error(d.error||'Service indisponible');erreur.status=r.status;throw erreur;}
    return d;
  }
  let memorise=null;
  try {memorise=lire(cleCode)||null;} catch {}
  let choisies=new Set(), defini=false;
  function dessiner() {
    const ligne=([k,v])=>`<label class="notif-choix"><span>${e(v)}${details[k]?`<small>${e(details[k])}</small>`:''}</span><input type="checkbox" role="switch" class="interrupteur" value="${e(k)}" ${choisies.has(k)?'checked':''}></label>`;
    const groupes=[['Comparateurs',k=>!k.startsWith('labo:')],['Règles Pinnacle',k=>k.startsWith('labo:PIN-')],['Règles Polymarket',k=>k.startsWith('labo:POL-')]]
      .map(([titre,f])=>[titre,Object.entries(noms).filter(([k])=>f(k))]).filter(([,l])=>l.length);
    zone.innerHTML='<legend>Stratégies envoyées sur Pushover</legend>'+groupes.map(([titre,l],i)=>{
      const n=l.filter(([k])=>choisies.has(k)).length;
      return `<details class="notif-groupe"${i===0||n?' open':''}><summary>${e(titre)} <small>${n?n+' suivie'+(n>1?'s':''):l.length+' au choix'}</small></summary>${l.map(ligne).join('')}</details>`;
    }).join('');
    code.placeholder=memorise?'Code mémorisé sur cet appareil':'Choisis un code personnel (8 caractères au moins)';
  }
  try {
    const d=await appeler('pushover-lire',{});
    defini=!!d.defini;choisies=new Set(d.strategies||[]);
    etat.textContent=defini?`Choix enregistré : ${choisies.size} stratégie${choisies.size>1?'s':''}.`:
      'Aucun choix enregistré : Pushover suit pour l’instant les cases de l’abonnement Chrome, s’il existe.';
  } catch {etat.textContent='Choix indisponible pour le moment. Recharge la page pour réessayer.';sauver.disabled=true;}
  dessiner();
  sauver.onclick=async()=>{
    sauver.disabled=true;say('');
    try {
      const strategies=[...zone.querySelectorAll('input:checked')].map(x=>x.value);
      const saisi=code.value.trim();
      if(!memorise && saisi.length<8) throw Error(defini?'Saisis ton code personnel.':'Choisis un code personnel d’au moins 8 caractères.');
      const token=saisi?await empreinte(saisi):memorise;
      await appeler('pushover-ecrire',{token,strategies});
      memorise=token;try {ecrire(cleCode,token);} catch {}
      code.value='';choisies=new Set(strategies);defini=true;dessiner();
      etat.textContent=`Choix enregistré : ${strategies.length} stratégie${strategies.length>1?'s':''}.`;
      say(strategies.length?'Enregistré. Les alertes de ces stratégies arrivent sur Pushover dès le prochain relevé.':'Enregistré : aucune alerte Pushover.');
    } catch(erreur) {
      if(erreur.status===403) {memorise=null;try {ecrire(cleCode,'');} catch {} dessiner();}
      say(erreur.status===403?'Code personnel refusé. Saisis le code choisi lors du premier enregistrement.':erreur.message||'Enregistrement impossible. Réessaie.',true);
    } finally {sauver.disabled=false;}
  };
})().catch(()=>{const z=document.getElementById('pushover-etat');if(z) z.textContent='Choix Pushover momentanément indisponible. Recharge la page.';});
