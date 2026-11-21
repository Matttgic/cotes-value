// Accueil, façon Une de journal : la date, un titre (combien de paris à jouer), un exemple concret, les chiffres,
// les paris à jouer (règle de la page Décision), les recommandées, le gain cumulé et les derniers résultats.
// Lecture seule des données déjà chargées : aucune sélection, aucun règlement n'est modifié.
function ligneAccueilPari(p) {
  const ref=(typeof REF_COURTE!=='undefined' && REF_COURTE[p.reference]!==undefined ? REF_COURTE[p.reference] : (p.reference || '')+' ');
  return `<article class="acc-pari"><div class="acc-pari-texte"><span class="acc-meta">${e(nomSport(p.sport))}${p.ligue ? ' · '+e(p.ligue) : ''}</span>
<b>${e(p.domicile)} – ${e(p.exterieur)}</b><span>${e(p.pari)}</span><span class="pari-debut">Match ${horairePari(p)}</span></div>
<div class="acc-pari-prix"><span class="acc-book">${e(p.bookmaker)}${heureEnvoi(p) ? ' · '+heureEnvoi(p) : ''}</span>
<b class="acc-cote">${cote(p.cote)}</b><small class="acc-ref">${e(ref)}${cote(p.cote_juste)}</small><i class="acc-ecart">${pct(p.ecart)}</i>${sourcesAccueil(p)}${boutonBookmaker(p,true)}</div></article>`;
}
// Plusieurs références sur la même cote : la mise est multipliée (3 fois au plus), comme dans l'alerte Pushover.
function sourcesAccueil(p) {
  const k=typeof facteurSources==='function' ? facteurSources(p) : 1;
  return k>1 ? `<i class="acc-mise">${p.sources} sources · mise ×${k}</i>` : '';
}
function rangTexte(n) {return `${n}<sup>${n===1 ? 'er' : 'e'}</sup>`;}
// Bilan des paris uniques réglés dans une mise donnée, quel que soit le mode affiché : même règle qu'appliquerMise
// (mise Kelly ⅛ corrigé, celle des alertes, quand le pari en a une, sinon la mise fixe d'origine).
function bilanEnMise(ps, kelly) {
  let mises = 0, net = 0;
  for (const p of ps) {
    const k = typeof facteurSources === 'function' ? facteurSources(p) : 1;
    if (kelly && p.mise_kelly && p.mise_fixe) { mises += k * p.mise_kelly; net += k * p.gain_fixe * p.mise_kelly / p.mise_fixe; }
    else { mises += k * (p.mise_fixe ?? p.mise ?? 0); net += k * (p.gain_fixe ?? p.gain ?? 0); }
  }
  return {net: Math.round(net * 100) / 100, roi: mises ? net / mises : null};
}
function nomMiseAccueil(mode) { return typeof nomMise === 'function' ? nomMise(mode) : mode === 'fixe' ? '10 € fixes' : 'Kelly ⅛ corrigé'; }
// Le chapô : un exemple chiffré plutôt qu'une explication.
function chapoAccueil(jouer, enCours) {
  const x=jouer[0] && jouer[0].p;
  if(!x) return `${enCours} paris en cours, aucun n'est assez sûr aujourd'hui.`;
  return `Exemple : ${e(x.bookmaker)} paie <b>${cote(x.cote)}</b> sur « ${e(x.pari)} » (${e(x.domicile)} – ${e(x.exterieur)}). `
    +`${e(x.reference)} estime le juste prix à <b>${cote(x.cote_juste)}</b> : on est payé ${pct(x.ecart)} de plus que ce que le pari vaut.`;
}
function carteRecommandee(x, i, noms) {
  const d=x.depuis_entree || {}, jour=`${x.depuis.slice(8,10)}/${x.depuis.slice(5,7)}`;
  const depuis=d.regles ? `<span class="${signe(d.gain)}">${eur(d.gain)}</span> depuis le ${jour} (${d.regles} paris terminés)`
    : `recommandée depuis le ${jour}, aucun pari terminé`;
  return `<div class="acc-rang"><span class="acc-num">${i+1}.</span><span class="acc-rang-nom"><b>${e(noms.get(x.id) || x.id)}</b>
<small class="acc-rang-detail">${depuis}</small></span></div>`;
}
// Boost « jouer » du dernier relevé : la mise max en premier, c'est elle qu'on joue.
function ligneAccueilBoost(b) {
  const match=[b.domicile, b.exterieur].filter(Boolean).join(' – ');
  return `<article class="acc-pari"><div class="acc-pari-texte"><span class="acc-meta">${b.sport ? e(nomSport(b.sport))+' · ' : ''}${e(match)}</span>
<b>${e(b.libelle)}</b><span class="pari-debut">Match ${horairePari(b)}</span></div>
<div class="acc-pari-prix"><span class="acc-book">${e(b.bookmaker)}</span><b class="acc-cote">${cote(b.cote)}</b>
<small class="acc-ref">au lieu de ${cote(b.cote_avant)}</small><i class="acc-mise">Mise max ${b.mise_max ? euros(b.mise_max) : 'inconnue : 10 €'}</i>
${boutonBookmaker({bookmaker: b.bookmaker, lien: b.lien, statut: 'en_cours'},true)}</div></article>`;
}
// Noms des recommandées avant l'arrivée du laboratoire (bloc différé) : même numérotation que lignesStrategies
// (« Pinnacle 12 », règles dans l'ordre du laboratoire) ; les variantes gardent leur nom.
function nomsAvantLaboratoire() {
  const noms=new Map(), numeros={};
  for (const [id, ref] of D.regles_labo || []) noms.set(id, `${ref} ${numeros[ref]=(numeros[ref] || 0)+1}`);
  for (const [id, v] of Object.entries(D.variantes || {})) if (v && v.nom) noms.set(id, v.nom);
  return noms;
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
  const unes=fiches.filter(p=>p.unique_bilan && p.gain!=null && !(p.cote>10));
  const reglees=typeof enSources==='function' ? enSources(unes) : unes,s=statsBU(reglees);
  const enCours=fiches.filter(p=>p.statut==='en_cours' && !p.a_regler);
  const autreKelly=miseMode==='fixe', autre=bilanEnMise(unes,autreKelly), nomAutre=nomMiseAccueil(autreKelly ? 'kelly' : 'fixe');
  // Variation chiffrée depuis la visite précédente sur cet appareil (bourse.js) ; le clignotement est dans interface.js.
  const bouge=typeof comparerChiffres==='function' ? comparerChiffres(`${miseMode}|${typeof BANKROLL!=='undefined'?BANKROLL:''}`,
    {net:s.net, roi:s.roi, reussite:s.reussite, encours:enCours.length}) : {};
  const variation=(k,texte)=>bouge[k]==null ? '' : `<em class="cv-delta ${bouge[k]>0?'pos':'neg'}" title="Depuis ta dernière visite">${bouge[k]>0?'▲':'▼'} ${texte(bouge[k])}</em>`;
  cible.innerHTML=[
    ['Gain net',eurC(s.net),signe(s.net),`${s.n} paris réglés · ${mise}`,variation('net',v=>eurC(v))],
    ['ROI',pct(s.roi),signe(s.net),`en ${nomAutre} : ${pct(autre.roi)}`,variation('roi',v=>pct(v))],
    ['Réussite',pctEntier(s.reussite),'','paris gagnés',variation('reussite',v=>pct(v))],
    ['En cours',String(enCours.length),'','pas encore réglés',variation('encours',v=>(v>0?'+':'')+v)]
  ].map(([t,v,c,d,x])=>`<div class="acc-kpi"><p>${e(t)}</p><strong class="${c}">${e(v)}</strong><span>${e(d)}</span>${x}</div>`).join('');
  // À jouer : la règle de la page Décision (bookmaker ET référence qui battent la clôture Pinnacle).
  const jouer=typeof decisionParis==='function' ? decisionParis(fiches, D.decision, D.protocole).jouer : [];
  document.getElementById('acc-titre').textContent=jouer.length ? `${jouer.length} pari${jouer.length>1?'s':''} à jouer` : 'Rien à jouer pour l\'instant';
  document.getElementById('une-chapo').innerHTML=chapoAccueil(jouer, enCours.length);
  document.getElementById('acc-values-n').textContent=jouer.length ? `${jouer.length} sur ${enCours.length} en cours` : '';
  document.getElementById('acc-values').innerHTML=jouer.length ? jouer.map(x=>ligneAccueilPari(x.p)).join('')
    : '<p class="aide">Aucun pari ne passe la règle du jour.</p>';
  const boosts=((D.boosts || {}).actuels || []).filter(b=>b.verdict==='jouer');
  document.getElementById('acc-boosts-n').textContent=boosts.length ? String(boosts.length) : '';
  document.getElementById('acc-boosts').innerHTML=boosts.length ? boosts.map(ligneAccueilBoost).join('')
    : '<p class="aide">Aucun boost à jouer pour l\'instant.</p>';
  // Recommandées (cotes/recommandations.py) : la liste de la semaine, avec leur preuve et leur résultat depuis l'entrée.
  const noms=D.laboratoire && D.laboratoire.resultats ? new Map(lignesStrategies('futur').map(r=>[r.id, r.nomCourt || r.nom]))
    : nomsAvantLaboratoire();
  const recos=(D.recommandees && D.recommandees.actuelles) || [];
  document.getElementById('acc-top5').innerHTML=recos.length ? recos.map((x,i)=>carteRecommandee(x,i,noms)).join('')
    : '<p class="aide">Aucune stratégie ne bat encore la clôture de façon prouvée.</p>';
  // Gain cumulé des paris uniques (même courbe que le Bilan, tracée en marches), avec la ligne témoin : gain attendu
  // cumulé et marge du hasard (variance cumulée de chaque pari, 5e colonne).
  document.getElementById('acc-courbe').innerHTML=grandeCourbe(pointsDepuisParis(reglees));
  document.getElementById('acc-courbe-mise').textContent=`paris uniques · ${mise} × sources`;
  // Derniers résultats : les cinq derniers paris uniques réglés.
  const derniers=fiches.filter(p=>p.unique_bilan && p.gain!=null && p.regle_le).sort((a,b)=>Date.parse(b.regle_le)-Date.parse(a.regle_le)).slice(0,5);
  document.getElementById('acc-derniers').innerHTML=derniers.length ? derniers.map(p=>`<div class="acc-resultat"><span><b>${e(p.domicile)} – ${e(p.exterieur)}</b>
<small>${e(p.pari)} · ${e(p.bookmaker)} ${cote(p.cote)}</small></span><b class="${signe(p.gain)}">${eur(p.gain)}</b></div>`).join('')
    : '<p class="aide">Aucun résultat récent.</p>';
  if (typeof tableauCotation === 'function') { tableauCotation(enCours, jouer); afficherSeance(enCours); }
  if (typeof bandeauBoursier === 'function') {
    const court=t=>String(t || '').toUpperCase();
    bandeauBoursier([
      ['GAIN NET', eurC(s.net), '', signe(s.net)],
      ['ROI', pct(s.roi), '', signe(s.net)],
      ['RÉUSSITE', pctEntier(s.reussite), '', ''],
      ['EN COURS', String(enCours.length), '', ''],
      ...jouer.map(x=>[`${court(x.p.domicile)} – ${court(x.p.exterieur)}`, cote(x.p.cote), pct(x.p.ecart), 'pos']),
      ...derniers.map(p=>[`${court(p.domicile)} – ${court(p.exterieur)}`, cote(p.cote), eur(p.gain), signe(p.gain)])
    ]);
  }
}
