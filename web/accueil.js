// Accueil, façon Une de journal : la date, un titre (combien de paris à jouer), un exemple concret, les chiffres,
// les paris à jouer (règle de la page Décision), les recommandées, le gain cumulé et les derniers résultats.
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
// Le chapô : un exemple chiffré plutôt qu'une explication.
function chapoAccueil(jouer, enCours) {
  const x=jouer[0] && jouer[0].p;
  if(!x) return `${enCours} paris en cours, aucun ne passe la règle du jour : leur bookmaker ou leur référence ne bat pas encore la clôture Pinnacle.`;
  return `Exemple : ${e(x.bookmaker)} paie <b>${cote(x.cote)}</b> sur « ${e(x.pari)} » (${e(x.domicile)} – ${e(x.exterieur)}). `
    +`${e(x.reference)} estime le juste prix à <b>${cote(x.cote_juste)}</b> : on est payé ${pct(x.ecart)} de plus que ce que le pari vaut.`;
}
function carteRecommandee(x, i, noms) {
  const P=typeof preuveDe==='function' ? preuveDe(x.id) : null, d=x.depuis_entree || {};
  const clv=P && P.clv!=null ? `<span class="${signe(P.clv)}">CLV Pinnacle ${pct(P.clv/100)}</span> · ${P.matchs} matchs` : 'pas encore mesurée';
  const depuis=d.regles ? `depuis le ${x.depuis.slice(8,10)}/${x.depuis.slice(5,7)} : ${d.regles} réglés, <span class="${signe(d.gain)}">${eur(d.gain)}</span>`
    : `depuis le ${x.depuis.slice(8,10)}/${x.depuis.slice(5,7)} : rien de réglé`;
  return `<div class="acc-rang"><span class="acc-num">${i+1}.</span><span class="acc-rang-nom"><b>${e(noms.get(x.id) || x.id)}</b>
<small class="acc-rang-detail">${clv}<br>${depuis}</small></span></div>`;
}
function rendreAccueil() {
  const cible=document.getElementById('acc-kpis');if(!cible) return;
  const maintenant=new Date();
  const jour=new Intl.DateTimeFormat('fr-FR',{timeZone:'Europe/Paris',weekday:'long',day:'numeric',month:'long',year:'numeric'}).format(maintenant);
  const heure=new Intl.DateTimeFormat('fr-FR',{timeZone:'Europe/Paris',hour:'2-digit',minute:'2-digit'}).format(maintenant).replace(':',' h ');
  document.getElementById('une-date').textContent=`${jour} · édition de ${heure}`;
  const mise=nomMiseAccueil(miseMode);
  // Premier chiffre : les cotes de 10 au plus. Au-delà, c'est de la loterie (quelques gains sur des centaines de
  // paris) qui masquait tout le reste.
  const reglees=fiches.filter(p=>p.unique_bilan && p.gain!=null && !(p.cote>10)),s=statsBU(reglees);
  const enCours=fiches.filter(p=>p.statut==='en_cours' && !p.a_regler);
  const autreKelly=miseMode==='fixe', autre=bilanEnMise(reglees,autreKelly), nomAutre=nomMiseAccueil(autreKelly ? 'kelly' : 'fixe');
  cible.innerHTML=[
    ['Gain net',eurC(s.net),signe(s.net),`${s.n} paris réglés · ${mise}`],
    ['ROI',pct(s.roi),signe(s.net),`en ${nomAutre} : ${pct(autre.roi)}`],
    ['Réussite',pctEntier(s.reussite),'','paris gagnés'],
    ['En cours',String(enCours.length),'','pas encore réglés']
  ].map(([t,v,c,d])=>`<div class="acc-kpi"><p>${e(t)}</p><strong class="${c}">${e(v)}</strong><span>${e(d)}</span></div>`).join('');
  // À jouer : la règle de la page Décision (bookmaker ET référence qui battent la clôture Pinnacle).
  const jouer=typeof decisionParis==='function' ? decisionParis(fiches, D.decision, D.protocole).jouer : [];
  document.getElementById('acc-titre').textContent=jouer.length ? `${jouer.length} pari${jouer.length>1?'s':''} à jouer` : 'Rien à jouer pour l\'instant';
  document.getElementById('une-chapo').innerHTML=chapoAccueil(jouer, enCours.length);
  document.getElementById('acc-values-n').textContent=jouer.length ? `${jouer.length} sur ${enCours.length} en cours` : '';
  document.getElementById('acc-values').innerHTML=jouer.length ? jouer.slice(0,5).map(x=>ligneAccueilPari(x.p)).join('')
    + (jouer.length>5 ? `<p class="aide">Et ${jouer.length-5} autres dans l'onglet Décision.</p>` : '')
    : '<p class="aide">Aucun pari ne passe la règle du jour.</p>';
  document.getElementById('acc-tous').textContent=`Les ${enCours.length} paris en cours →`;
  // Recommandées (cotes/recommandations.py) : la liste de la semaine, avec leur preuve et leur résultat depuis l'entrée.
  const noms=new Map(lignesStrategies('futur').map(r=>[r.id, r.nomCourt || r.nom]));
  const recos=(D.recommandees && D.recommandees.actuelles) || [];
  document.getElementById('acc-top5').innerHTML=recos.length ? recos.map((x,i)=>carteRecommandee(x,i,noms)).join('')
    : '<p class="aide">Aucune stratégie ne bat encore la clôture de façon prouvée.</p>';
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
