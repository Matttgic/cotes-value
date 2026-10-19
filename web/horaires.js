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
function texteCollecte(p, maintenant=Date.now()) {
  const valeur=p.collecte_recue || p.detecte, t=valeur?new Date(valeur):null;
  if(!t || !Number.isFinite(t.getTime())) return {texte:'Collecte non renseignée',ancien:false};
  const age=Math.max(0,Math.floor((maintenant-t.getTime())/60000)),h=Math.floor(age/60),m=age%60;
  const delai=age<1?'à l’instant':h?(h+'h'+String(m).padStart(2,'0')):age+' min';
  const date=t.toLocaleString('fr-FR',{timeZone:fuseauMatch,day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit'});
  return {texte:'Cote relevée '+date+' · '+(age<1?delai:'il y a '+delai),ancien:age>5 && (!p.statut || p.statut==='en_cours')};
}
function collectePari(p, maintenant=Date.now()) {
  const c=texteCollecte(p,maintenant);
  const precision=p.collecte_recue?'Réception de la réponse API ; mise à jour interne du fournisseur non vérifiée.':'Ancienne prise : heure enregistrée du lot, réception exacte inconnue.';
  let suite='';
  if(Number.isFinite(p.prix_revu) && p.prix_revu_le && p.prix_revu!==p.cote) {
    const delta=p.prix_revu-p.cote;
    suite=`<span class="prix-revu ${delta<0?'neg':'pos'}">Relue ${new Date(p.prix_revu_le).toLocaleString('fr-FR',{timeZone:fuseauMatch,day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit'})} : ${cote(p.prix_revu)} (${delta>0?'+':''}${cote(delta)})</span>`;
  } else if(Number.isFinite(p.prix_revu) && p.prix_revu_le && p.prix_revu_le!==(p.collecte_recue || p.detecte)) {
    suite=`<span>Prix confirmé dans l’API ${new Date(p.prix_revu_le).toLocaleString('fr-FR',{timeZone:fuseauMatch,day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit'})}</span>`;
  }
  if(p.alerte_demande_le) {
    const demande=new Date(p.alerte_demande_le),recue=new Date(p.collecte_recue || p.detecte);
    if(Number.isFinite(demande.getTime()) && Number.isFinite(recue.getTime())) {
      const secondes=Math.max(0,Math.round((demande-recue)/1000));
      suite+=`<span>Envoi demandé ${demande.toLocaleTimeString('fr-FR',{timeZone:fuseauMatch,hour:'2-digit',minute:'2-digit',second:'2-digit'})} · délai ${secondes<60?secondes+' s':Math.floor(secondes/60)+' min '+secondes%60+' s'}</span>`;
    }
  }
  return `<span class="pari-collecte${c.ancien?' collecte-ancienne':''}" title="${e(precision)}" data-collecte="${e(p.collecte_recue || p.detecte || '')}" data-precision="${p.collecte_recue?'api':'lot'}" data-statut="${e(p.statut || '')}"><span class="collecte-date">${e(c.texte)}</span>${suite}</span>`;
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
function actualiserHoraires() {
  for(const el of document.querySelectorAll('time[data-horaire]')) {
    const h=infoHoraire({debut:el.dataset.horaire,reporte_au:el.dataset.reporte==='oui'?el.dataset.horaire:null,statut:'en_cours'});
    if(el.textContent!==h.texte) el.textContent=h.texte;
    el.className='pari-horaire '+h.classe;
  }
  for(const el of document.querySelectorAll('[data-collecte]')) {
    const p={detecte:el.dataset.collecte,statut:el.dataset.statut},c=texteCollecte(p);
    const label=el.querySelector('.collecte-date');
    if(label && label.textContent!==c.texte) label.textContent=c.texte;
    el.classList.toggle('collecte-ancienne',c.ancien);
  }
}
