// Présentation des horaires uniquement. Les dates des prises restent inchangées.
const fuseauMatch = 'Europe/Paris';
function jourParis(date) {
  return new Intl.DateTimeFormat('en-CA',{timeZone:fuseauMatch,year:'numeric',month:'2-digit',day:'2-digit'}).format(date);
}
function heureMatch(p) {
  const valeur=p.reporte_au && p.statut==='en_cours' ? p.reporte_au : p.debut;
  const date=valeur ? new Date(valeur) : null;
  return date && Number.isFinite(date.getTime()) ? date : null;
}
function infoHoraire(p, maintenant=Date.now()) {
  const date=heureMatch(p);
  if(!date) return {texte:'Horaire non communiqué',classe:'inconnu',date:null};
  const now=new Date(maintenant), delta=date.getTime()-now.getTime();
  // Midi civil à Paris : ajouter un jour calendaire reste correct aux changements d'heure.
  const jour=jourParis(now), demain=new Date(jour+'T12:00:00Z');
  demain.setUTCDate(demain.getUTCDate()+1);
  const cible=jourParis(date), hm=date.toLocaleTimeString('fr-FR',{timeZone:fuseauMatch,hour:'2-digit',minute:'2-digit'});
  let texte=cible===jour ? 'Auj. '+hm : cible===jourParis(demain) ? 'Demain '+hm :
    date.toLocaleDateString('fr-FR',{timeZone:fuseauMatch,weekday:'short',day:'2-digit',month:'2-digit'})+' · '+hm;
  const imminent=delta>0 && delta<=2*3600000;
  if(imminent) {
    const minutes=Math.ceil(delta/60000), h=Math.floor(minutes/60), m=minutes%60;
    texte+=' (dans '+(h ? h+'h'+(m?String(m).padStart(2,'0'):'') : minutes+' min')+')';
  }
  if(p.reporte_au && p.statut==='en_cours') texte='Reporté · '+texte;
  return {texte,classe:imminent?'imminent':delta<=0?'passe':cible===jourParis(demain)?'lointain':'',date};
}
function horairePari(p, maintenant=Date.now()) {
  const h=infoHoraire(p,maintenant);
  return `<time class="pari-horaire ${h.classe}"${h.date?` datetime="${h.date.toISOString()}"`:''} data-horaire="${e(h.date?.toISOString() || '')}" data-reporte="${p.reporte_au && p.statut==='en_cours'?'oui':''}" title="Heure de Paris">${e(h.texte)}</time>`;
}
function accepteHoraire(p, filtre, maintenant=Date.now()) {
  if(!filtre) return true;
  const date=heureMatch(p);if(!date) return false;
  if(filtre==='imminent') return date.getTime()>maintenant && date.getTime()<=maintenant+2*3600000;
  const jour=jourParis(new Date(maintenant)), demain=new Date(jour+'T12:00:00Z');
  demain.setUTCDate(demain.getUTCDate()+1);
  return jourParis(date)===(filtre==='demain'?jourParis(demain):jour);
}
function trierHoraires(liste, ordre) {
  if(!ordre) return liste;
  return [...liste].sort((a,b)=>{
    const x=heureMatch(a)?.getTime(),y=heureMatch(b)?.getTime();
    if(x==null) return y==null?0:1;if(y==null) return -1;
    return ordre==='recent'?y-x:x-y;
  });
}
function groupesMatchs(liste) {
  const groupes=new Map();
  for(const p of liste) {
    // Regroupement visuel prudent : ni rapprochement flou, ni fusion de catégories d'équipes.
    const nom=s=>String(s||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().trim().replace(/\s+/g,' ');
    const date=heureMatch(p);
    const cle=JSON.stringify([p.sport,date?.toISOString(),nom(p.domicile),nom(p.exterieur),
      !date||!p.domicile||!p.exterieur ? p.match_id : '']);
    if(!groupes.has(cle)) groupes.set(cle,[]);
    groupes.get(cle).push(p);
  }
  return [...groupes.values()];
}
function rendreGroupesJouer(liste) {
  return groupesMatchs(liste).map(paris=>{
    const tries=[...paris].sort((a,b)=>b.ecart-a.ecart),p=tries[0];
    return `<section class="groupe-match" aria-label="${e(p.domicile)} – ${e(p.exterieur)}">
      <header><div class="groupe-sport">${iconeSport(p.sport)}${e(nomsSports[p.sport]||p.sport||'Sport')}${p.ligue?' · '+e(p.ligue):''}</div>
      <h3>${e(p.domicile)} – ${e(p.exterieur)}</h3><div class="groupe-horaire">${horairePari(p)}<span>${paris.length} offre${paris.length>1?'s':''}</span></div></header>
      ${tries.map((o,i)=>`<div class="offre-match${i===0 && tries.length>1?' meilleur-edge':''}">${i===0 && tries.length>1?'<span class="meilleur-libelle">Edge le plus élevé</span>':''}${carteActuelle(o)}</div>`).join('')}</section>`;
  }).join('');
}
function actualiserHoraires() {
  for(const el of document.querySelectorAll('time[data-horaire]')) {
    const h=infoHoraire({debut:el.dataset.horaire,reporte_au:el.dataset.reporte==='oui'?el.dataset.horaire:null,statut:'en_cours'});
    if(el.textContent!==h.texte) el.textContent=h.texte;
    el.className='pari-horaire '+h.classe;
  }
}
