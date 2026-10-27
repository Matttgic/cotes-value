// Accueil : chiffres du moment, paris en cours, Top 5 des stratégies, gain cumulé, derniers résultats.
// Lecture seule des données déjà chargées : aucune sélection, aucun règlement n'est modifié.
function ligneAccueilPari(p) {
  const ref=(typeof REF_COURTE!=='undefined' && REF_COURTE[p.reference]!==undefined ? REF_COURTE[p.reference] : (p.reference || '')+' ');
  return `<article class="acc-pari"><div class="acc-pari-texte"><span class="acc-meta">${e(nomSport(p.sport))}${p.ligue ? ' · '+e(p.ligue) : ''}</span>
<b>${e(p.domicile)} – ${e(p.exterieur)}</b><span>${e(p.pari)}</span><span class="pari-debut">Match ${horairePari(p)}</span></div>
<div class="acc-pari-prix"><span class="acc-book">${e(p.bookmaker)}${heureEnvoi(p) ? ' · '+heureEnvoi(p) : ''}</span>
<b class="acc-cote">${cote(p.cote)}</b><small class="acc-ref">${e(ref)}${cote(p.cote_juste)}</small><i class="acc-ecart">${pct(p.ecart)}</i>${boutonBookmaker(p,true)}</div></article>`;
}
function rendreAccueil() {
  const cible=document.getElementById('acc-kpis');if(!cible) return;
  const heure=Number(new Intl.DateTimeFormat('fr-FR',{timeZone:'Europe/Paris',hour:'2-digit',hourCycle:'h23'}).format(new Date()));
  document.getElementById('acc-titre').textContent=(heure>=5 && heure<18 ? 'Bonjour' : 'Bonsoir')+' Matthieu';
  const mise=miseMode==='kelly' ? 'Kelly ¼' : '10 € fixes';
  const reglees=fiches.filter(p=>p.unique_bilan && p.gain!=null),s=statsBU(reglees);
  const enCours=fiches.filter(p=>p.statut==='en_cours' && !p.a_regler);
  cible.innerHTML=[
    [`Gain net · paris uniques · ${mise}`,eurC(s.net),signe(s.net),`${s.n} réglés · mise ${Math.round(s.mises).toLocaleString('fr-FR')} €`],
    ['ROI',pct(s.roi),signe(s.net),'Gain net / mises réglées'],
    ['Réussite',pctEntier(s.reussite),'','Gagnés et demi-gagnés / réglés'],
    ['En cours',String(enCours.length),'','Paris pas encore réglés']
  ].map(([t,v,c,d])=>`<div class="acc-kpi"><p>${e(t)}</p><strong class="${c}">${e(v)}</strong><span>${e(d)}</span></div>`).join('');
  // Values du moment : les cinq dernières prises encore en cours.
  document.getElementById('acc-values-n').textContent=`${enCours.length} en cours`;
  document.getElementById('acc-values').innerHTML=enCours.length ? enCours.slice(0,5).map(ligneAccueilPari).join('')
    : '<p class="aide">Aucun pari en cours pour le moment.</p>';
  // Top 5 : gain net depuis le lancement ; les pastilles désignent les meilleurs critères (50 paris réglés minimum).
  const rows=lignesStrategies('futur');attribuerMedailles(rows);
  const top=rows.filter(r=>r.stats.regles>0).sort((a,b)=>(b.stats.gain ?? -Infinity)-(a.stats.gain ?? -Infinity)).slice(0,5);
  document.getElementById('acc-top5-mise').textContent=`gain net · ${mise}`;
  document.getElementById('acc-top5').innerHTML=top.length ? top.map((r,i)=>`<div class="acc-rang"><span class="acc-num">${i+1}.</span>
<span class="acc-rang-nom"><b>${e(r.nomCourt || r.nom)}</b>${pastillesMedailles(r.medailles)}</span>
<span class="acc-rang-gain ${signe(r.stats.gain)}">${eurC(r.stats.gain)}</span><small class="${signe(r.stats.roi)}">${pct(r.stats.roi==null ? null : r.stats.roi/100)}</small></div>`).join('')
    : '<p class="aide">Pas encore de stratégie avec des paris réglés.</p>';
  // Gain cumulé des paris uniques (même courbe que le Bilan, tracée en marches).
  let total=0;
  const points=((D.courbes || {}).Uniques || []).map(p=>[p[0]*60,total=Math.round((total+p[1])*100)/100]);
  document.getElementById('acc-courbe').innerHTML=grandeCourbe(points);
  document.getElementById('acc-courbe-mise').textContent=`paris uniques · ${mise}`;
  // Derniers résultats : les cinq derniers paris uniques réglés.
  const derniers=fiches.filter(p=>p.unique_bilan && p.gain!=null && p.regle_le).sort((a,b)=>Date.parse(b.regle_le)-Date.parse(a.regle_le)).slice(0,5);
  document.getElementById('acc-derniers').innerHTML=derniers.length ? derniers.map(p=>`<div class="acc-resultat"><span><b>${e(p.domicile)} – ${e(p.exterieur)}</b>
<small>${e(p.pari)} · ${e(p.bookmaker)} ${cote(p.cote)}</small></span><b class="${signe(p.gain)}">${eur(p.gain)}</b></div>`).join('')
    : '<p class="aide">Aucun résultat récent.</p>';
}
