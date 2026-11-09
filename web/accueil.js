// Accueil, dans l'ordre : santé, paris à jouer maintenant, chiffres clés, Top 5 des stratégies, gain cumulé, derniers
// résultats.
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
// (mise Kelly quand le pari en a une, sinon la mise fixe d'origine).
function bilanEnMise(ps, kelly) {
  let mises = 0, net = 0;
  for (const p of ps) {
    if (kelly && p.mise_kelly && p.mise_fixe) { mises += p.mise_kelly; net += p.gain_fixe * p.mise_kelly / p.mise_fixe; }
    else { mises += p.mise_fixe ?? p.mise ?? 0; net += p.gain_fixe ?? p.gain ?? 0; }
  }
  return {net: Math.round(net * 100) / 100, roi: mises ? net / mises : null};
}
function rendreAccueil() {
  const cible=document.getElementById('acc-kpis');if(!cible) return;
  const heure=Number(new Intl.DateTimeFormat('fr-FR',{timeZone:'Europe/Paris',hour:'2-digit',hourCycle:'h23'}).format(new Date()));
  document.getElementById('acc-titre').textContent=(heure>=5 && heure<18 ? 'Bonjour' : 'Bonsoir')+' Matthieu';
  const mise=miseMode==='kelly' ? 'Kelly ¼' : '10 € fixes';
  const reglees=fiches.filter(p=>p.unique_bilan && p.gain!=null),s=statsBU(reglees);
  const enCours=fiches.filter(p=>p.statut==='en_cours' && !p.a_regler);
  // Santé d'abord : une source en panne se voit avant de parier (même diagnostic que l'onglet Paris).
  const sante=document.getElementById('acc-sante');
  if(sante && typeof diagnosticSante==='function') {
    const {niveau,texte}=diagnosticSante();
    sante.className='paris-sante sante-'+niveau;
    sante.innerHTML=`<span class="sante-point" aria-hidden="true"></span><span class="sante-texte">${e(texte)}</span><span class="sante-suite">Détails ›</span>`;
    sante.onclick=()=>{ouvrir('controle');window.scrollTo(0,0);};
  }
  // L'autre mise reste visible : en 10 € fixes, les grosses cotes perdantes pèsent autant que les petites ;
  // en Kelly ¼, la mise suit l'écart et la cote. Les deux lectures se complètent.
  const autreKelly=miseMode!=='kelly', autre=bilanEnMise(reglees,autreKelly), nomAutre=autreKelly ? 'Kelly ¼' : '10 € fixes';
  cible.innerHTML=[
    [`Gain net · paris uniques · ${mise}`,eurC(s.net),signe(s.net),`${s.n} réglés · en ${nomAutre} : ${eurC(autre.net)}`],
    ['ROI',pct(s.roi),signe(s.net),`Gain net / mises réglées · en ${nomAutre} : ${pct(autre.roi)}`],
    ['Réussite',pctEntier(s.reussite),'','Gagnés et demi-gagnés / réglés'],
    ['En cours',String(enCours.length),'','Paris pas encore réglés']
  ].map(([t,v,c,d])=>`<div class="acc-kpi"><p>${e(t)}</p><strong class="${c}">${e(v)}</strong><span>${e(d)}</span></div>`).join('');
  // À jouer maintenant : paris uniques en cours dont le match n'a pas commencé (le plus proche d'abord), hors
  // référence suspecte. Rien à jouer est un état normal.
  const jouables=aJouer();
  document.getElementById('acc-values-n').textContent=`${jouables.length} jouable${jouables.length>1?'s':''} · ${enCours.length} en cours`;
  document.getElementById('acc-values').innerHTML=jouables.length ? jouables.slice(0,5).map(ligneAccueilPari).join('')
    : '<p class="aide">Rien à jouer pour le moment : aucun pari en cours sur un match à venir.</p>';
  // Top 5 valeur : rang moyen au ROI et à la CLV depuis le lancement (attribuerValeur) ; les pastilles désignent
  // les meilleurs critères (50 paris réglés minimum).
  const rows=lignesStrategies('futur');attribuerMedailles(rows);attribuerValeur(rows);
  const top=classerParValeur(rows).slice(0,5);
  document.getElementById('acc-top5-mise').textContent=`ROI + CLV · ${mise}`;
  document.getElementById('acc-top5').innerHTML=top.length ? top.map((r,i)=>`<div class="acc-rang"><span class="acc-num">${i+1}.</span>
<span class="acc-rang-nom"><b>${e(r.nomCourt || r.nom)}</b>${pastillesMedailles(r.medailles)}<small class="acc-rang-detail"><span class="${signe(r.stats.roi)}">ROI ${pct(r.stats.roi/100)}</span> (${rangTexte(r.rang_roi)}) · <span class="${signe(r.stats.clv)}">CLV ${pct(r.stats.clv/100)}</span> (${rangTexte(r.rang_clv)}) · ${r.stats.regles} réglés</small></span>
<span class="acc-rang-gain ${signe(r.stats.gain)}">${eurC(r.stats.gain)}</span></div>`).join('')
    : '<p class="aide">Pas encore de stratégie classée (30 paris réglés et 20 CLV mesurées au moins).</p>';
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
