// Accueil : chiffres du moment, paris en cours, classement des stratégies par la note /100, gain cumulé, derniers résultats.
// Lecture seule des données déjà chargées : aucune sélection, aucun règlement n'est modifié.
function ligneAccueilPari(p) {
  const ref=(typeof REF_COURTE!=='undefined' && REF_COURTE[p.reference]!==undefined ? REF_COURTE[p.reference] : (p.reference || '')+' ');
  return `<article class="acc-pari"><div class="acc-pari-texte"><span class="acc-meta">${e(nomSport(p.sport))}${p.ligue ? ' · '+e(p.ligue) : ''}</span>
<b>${e(p.domicile)} – ${e(p.exterieur)}</b><span>${e(p.pari)}</span><span class="pari-debut">Match ${horairePari(p)}</span></div>
<div class="acc-pari-prix"><span class="acc-book">${e(p.bookmaker)}${heureEnvoi(p) ? ' · '+heureEnvoi(p) : ''}</span>
<b class="acc-cote">${cote(p.cote)}</b><small class="acc-ref">${e(ref)}${cote(p.cote_juste)}</small><i class="acc-ecart">${pct(p.ecart)}</i>${boutonBookmaker(p,true)}</div></article>`;
}
function rangTexte(n) {return `${n}<sup>${n===1 ? 'er' : 'e'}</sup>`;}
// Bilan des paris uniques réglés dans une mise donnée, quel que soit le mode affiché : même règle qu'appliquerMise
// (mise Kelly ¼ quand le pari en a une, sinon la mise fixe d'origine).
function bilanEnMise(ps, kelly) {
  let mises = 0, net = 0;
  for (const p of ps) {
    if (kelly && p.mise_kelly && p.mise_fixe) { mises += p.mise_kelly; net += p.gain_fixe * p.mise_kelly / p.mise_fixe; }
    else { mises += p.mise_fixe ?? p.mise ?? 0; net += p.gain_fixe ?? p.gain ?? 0; }
  }
  return {net: Math.round(net * 100) / 100, roi: mises ? net / mises : null};
}
function nomMiseAccueil(mode) { return typeof nomMise === 'function' ? nomMise(mode) : mode === 'fixe' ? '10 € fixes' : 'Kelly ¼'; }
function rendreAccueil() {
  const cible=document.getElementById('acc-kpis');if(!cible) return;
  const heure=Number(new Intl.DateTimeFormat('fr-FR',{timeZone:'Europe/Paris',hour:'2-digit',hourCycle:'h23'}).format(new Date()));
  document.getElementById('acc-titre').textContent=(heure>=5 && heure<18 ? 'Bonjour' : 'Bonsoir')+' Matthieu';
  const mise=nomMiseAccueil(miseMode);
  // Premier chiffre : les cotes de 10 au plus. Au-delà, c'est de la loterie (quelques gains sur des centaines de
  // paris) qui masquait tout le reste ; le total toutes cotes reste écrit dessous.
  const toutes=fiches.filter(p=>p.unique_bilan && p.gain!=null),sToutes=statsBU(toutes);
  const reglees=toutes.filter(p=>!(p.cote>10)),s=statsBU(reglees);
  const enCours=fiches.filter(p=>p.statut==='en_cours' && !p.a_regler);
  // L'autre mise reste visible : en 10 € fixes, les grosses cotes perdantes pèsent autant que les petites ;
  // en Kelly ¼, la mise suit l'écart et la cote. Les deux lectures se complètent.
  // Repère affiché à côté : les mises fixes, ou Kelly ¼ quand on regarde déjà les mises fixes.
  const autreKelly=miseMode==='fixe', autre=bilanEnMise(reglees,autreKelly), nomAutre=nomMiseAccueil(autreKelly ? 'kelly' : 'fixe');
  cible.innerHTML=[
    [`Gain net · cotes ≤ 10 · ${mise}`,eurC(s.net),signe(s.net),`${s.n} paris uniques réglés · en ${nomAutre} : ${eurC(autre.net)} · toutes cotes : ${eurC(sToutes.net)}`],
    ['ROI · cotes ≤ 10',pct(s.roi),signe(s.net),`Gain net / mises réglées · en ${nomAutre} : ${pct(autre.roi)} · toutes cotes : ${pct(sToutes.roi)}`],
    ['Réussite',pctEntier(s.reussite),'','Gagnés et demi-gagnés / réglés'],
    ['En cours',String(enCours.length),'','Paris pas encore réglés']
  ].map(([t,v,c,d])=>`<div class="acc-kpi"><p>${e(t)}</p><strong class="${c}">${e(v)}</strong><span>${e(d)}</span></div>`).join('');
  // Values du moment : les cinq dernières prises encore en cours.
  document.getElementById('acc-values-n').textContent=`${enCours.length} en cours`;
  document.getElementById('acc-values').innerHTML=enCours.length ? enCours.slice(0,5).map(ligneAccueilPari).join('')
    : '<p class="aide">Aucun pari en cours pour le moment.</p>';
  // Classement par la note /100 déjà publiée (classerParNote) : meilleure d'abord, sans note en dernier.
  // À égalité : plus de paris réglés, puis le nom. Les pastilles restent les meilleurs critères (50 réglés).
  const rows=lignesStrategies('futur');attribuerMedailles(rows);
  const top=classerParNote(rows).slice(0,5);
  document.getElementById('acc-top5-mise').textContent=`note /100 · ${mise}`;
  document.getElementById('acc-top5').innerHTML=top.length ? top.map((r,i)=>{
    const note=r.stats&&r.stats.note&&typeof r.stats.note.total==='number'?r.stats.note.total:null;
    const ton=note==null?'':note>=70?'pos':note<40?'neg':'';
    return `<div class="acc-rang"><span class="acc-num">${i+1}.</span>
<span class="acc-rang-nom"><b>${e(r.nomCourt || r.nom)}</b>${pastillesMedailles(r.medailles)}<small class="acc-rang-detail"><span class="${ton}">${note==null?'Sans note':'Note '+note+'/100'}</span> · ${r.stats.regles} réglés · <span class="${signe(r.stats.roi)}">ROI ${pct(r.stats.roi/100)}</span></small></span>
<span class="acc-rang-gain ${ton}">${note==null?'—':String(note)}</span></div>`;
  }).join('')
    : '<p class="aide">Pas encore de stratégie à classer.</p>';
  // Gain cumulé des paris uniques (même courbe que le Bilan, tracée en marches), avec la ligne témoin : gain attendu
  // cumulé et marge du hasard (variance cumulée de chaque pari, 5e colonne).
  let total=0,attendu=0,variance=0;
  const points=((D.courbes || {}).Uniques || []).map(p=>[p[0]*60,total=Math.round((total+p[1])*100)/100,
    attendu=Math.round((attendu+(p[3] || 0))*100)/100,Math.sqrt(variance+=Number.isFinite(p[4])?p[4]:0)]);
  document.getElementById('acc-courbe').innerHTML=grandeCourbe(points);
  document.getElementById('acc-courbe-mise').textContent=`paris uniques · ${mise}`;
  // Derniers résultats : les cinq derniers paris uniques réglés.
  const derniers=fiches.filter(p=>p.unique_bilan && p.gain!=null && p.regle_le).sort((a,b)=>Date.parse(b.regle_le)-Date.parse(a.regle_le)).slice(0,5);
  document.getElementById('acc-derniers').innerHTML=derniers.length ? derniers.map(p=>`<div class="acc-resultat"><span><b>${e(p.domicile)} – ${e(p.exterieur)}</b>
<small>${e(p.pari)} · ${e(p.bookmaker)} ${cote(p.cote)}</small></span><b class="${signe(p.gain)}">${eur(p.gain)}</b></div>`).join('')
    : '<p class="aide">Aucun résultat récent.</p>';
}
