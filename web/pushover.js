// Choix des stratégies envoyées par Pushover : enregistrés sur le serveur avec un code personnel, sans abonnement Chrome.
// Le job GitHub lit ce choix à chaque cycle (action « strategies » de la fonction cv-notifications).
(async function pushover() {
  const zone=document.getElementById('pushover-strategies'), message=document.getElementById('pushover-message');
  const sauver=document.getElementById('pushover-sauver'), code=document.getElementById('pushover-code');
  const etat=document.getElementById('pushover-etat');
  if(!zone) return;
  const api=D.notifications.api, cleCode='cv-pushover-v1';
  const noms=D.notifications.strategies, details=D.notifications.details||{};
  // Bilan prospectif de chaque règle du laboratoire (mises de 10 €), comme sur la page Stratégies.
  const futur=new Map((D.laboratoire?.futur||[]).map(r=>['labo:'+r.id,r]));
  for(const [k,nom] of Object.entries(D.notifications.comparateurs||{})) {
    const r=D.laboratoire?.comparateurs_futur?.[nom];
    if(r) futur.set(k,r);
  }
  const fr=(x,d)=>x.toFixed(d).replace('.',',');
  const signe=(x,d)=>(x>0?'+':'')+fr(x,d);
  const classe=x=>x>0?'pos':x<0?'neg':'';
  function bilan(k) {
    const r=futur.get(k);
    if(!r) return '';
    if(!r.regles) return `<span class="notif-bilan">Aucun pari réglé depuis le 14/10${r.attente?` · ${r.attente} en attente`:''}</span>`;
    const roi=Number.isFinite(r.roi)?r.roi:0, gain=Number.isFinite(r.gain)?r.gain:0;
    return `<span class="notif-bilan"><span>Réussite <b>${Math.round(100*r.gagnes/r.regles)} %</b> (${r.gagnes}/${r.regles})</span>`+
      `<span>Gain <b class="${classe(gain)}">${signe(gain,2)} €</b></span><span>ROI <b class="${classe(roi)}">${signe(roi,1)} %</b></span>`+
      `${r.jours?`<span><b>${fr(r.paris/r.jours,1)}</b> paris/jour</span><span><b class="${classe(gain)}">${signe(gain/r.jours*30.44,0)} €</b>/mois</span>`:''}`+
      `${r.attente?`<span>${r.attente} en attente</span>`:''}</span>`;
  };
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
    const ligne=([k,v])=>`<label class="notif-choix"><span>${e(v)}${details[k]?`<small>${e(details[k])}</small>`:''}${bilan(k)}</span><input type="checkbox" role="switch" class="interrupteur" value="${e(k)}" ${choisies.has(k)?'checked':''}></label>`;
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
    if(defini && typeof suiviPushover==='function') {suiviPushover(choisies);if(typeof rendreMesStrategies==='function') rendreMesStrategies();}
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
      if(typeof suiviPushover==='function') {suiviPushover(choisies);if(typeof rendreMesStrategies==='function') rendreMesStrategies();}
      etat.textContent=`Choix enregistré : ${strategies.length} stratégie${strategies.length>1?'s':''}.`;
      say(strategies.length?'Enregistré. Les alertes de ces stratégies arrivent sur Pushover dès le prochain relevé.':'Enregistré : aucune alerte Pushover.');
    } catch(erreur) {
      if(erreur.status===403) {memorise=null;try {ecrire(cleCode,'');} catch {} dessiner();}
      say(erreur.status===403?'Code personnel refusé. Saisis le code choisi lors du premier enregistrement.':erreur.message||'Enregistrement impossible. Réessaie.',true);
    } finally {sauver.disabled=false;}
  };
})().catch(()=>{const z=document.getElementById('pushover-etat');if(z) z.textContent='Choix Pushover momentanément indisponible. Recharge la page.';});
