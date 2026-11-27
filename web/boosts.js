// Page Boosts : surebets entre bookmakers français (gain garanti sur le papier), boosts couverts (boost à sa mise
// maximale + couverture des autres issues) et cotes boostées comparées à la cote juste. Lecture seule de D.surebets et
// D.boosts (cotes/surebets.py, cotes/boosts.py) : rien n'est recalculé sauf la répartition des mises des surebets pour
// la somme choisie (même règle que surebets.repartir).
const SB_CLE_TOTAL = 'cv-surebet-total';
let sbTotal = (() => { const v = Number(lire(SB_CLE_TOTAL)); return v >= 10 && v <= 100000 ? v : 100; })();
const fr2 = x => Number(x).toFixed(2).replace('.', ',');
const euros = x => Number(x).toLocaleString('fr-FR', {minimumFractionDigits: 0, maximumFractionDigits: 2}) + ' €';

// Mises arrondies à l'euro, sans dépasser le total, choisies pour que le pire résultat rapporte le plus.
function repartirSurebet(cotes, total) {
  const s = cotes.reduce((a, c) => a + 1 / c, 0), exactes = cotes.map(c => total / c / s);
  let meilleur = null;
  for (let masque = 0; masque < (1 << cotes.length); masque++) {
    const mises = exactes.map((x, i) => (masque >> i) & 1 ? Math.ceil(x) : Math.floor(x));
    const mise = mises.reduce((a, b) => a + b, 0);
    if (mises.some(m => m <= 0) || mise > total + 1e-9) continue;
    const pire = Math.min(...mises.map((m, i) => m * cotes[i])) - mise;
    if (!meilleur || pire > meilleur.gain + 1e-9 || (Math.abs(pire - meilleur.gain) < 1e-9 && mise < meilleur.mise))
      meilleur = {mises, mise, gain: pire};
  }
  if (!meilleur) {
    const mises = exactes.map(x => Math.round(x * 100) / 100), mise = mises.reduce((a, b) => a + b, 0);
    meilleur = {mises, mise, gain: Math.min(...mises.map((m, i) => m * cotes[i])) - mise};
  }
  return meilleur;
}

function carteSurebet(s) {
  const cotes = s.jambes.map(j => j.cote), r = repartirSurebet(cotes, sbTotal);
  const jambes = s.jambes.map((j, i) => {
    const p = {bookmaker: j.bookmaker, lien: j.lien, lien_repli: j.lien_repli, statut: 'en_cours'};
    return `<div class="sb-jambe"><span class="acc-book">${e(j.bookmaker)}</span><b>${e(j.pari)}</b>`
      + `<span class="sb-cote">${cote(j.cote)}${j.cote_juste ? `<small> juste ${cote(j.cote_juste)}</small>` : ''}</span>`
      + `<span class="sb-mise">${euros(r.mises[i])}</span>${boutonBookmaker(p, true)}</div>`;
  }).join('');
  const verif = s.verifie ? '<span class="badge">vérifié par la cote juste</span>'
    : '<span class="badge sb-alerte">non vérifié : contrôle que les paris portent sur le même marché</span>';
  return `<article class="sb-carte${s.suspect ? ' sb-suspect' : ''}">
<div class="sb-tete"><span class="acc-meta">${e(nomSport(s.sport))}${s.ligue ? ' · ' + e(s.ligue) : ''}</span>
<b>${e(s.match)}</b><span>${e(s.pari)} · ${horairePari(s)}</span></div>
<div class="sb-gain"><strong class="pos">+${fr2(100 * s.rendement)} %</strong>${verif}${s.suspect ? `<span class="badge sb-alerte">${e(s.suspect)}</span>` : ''}</div>
<div class="sb-jambes">${jambes}</div>
<p class="sb-retour">Mise ${euros(r.mise)} · retour d'au moins <b>${euros(r.mise + r.gain)}</b> quoi qu'il arrive
(<span class="${signe(r.gain)}">${r.gain >= 0 ? '+' : ''}${euros(r.gain)}</span>). Cotes relevées à ${hm(s.lu_premier)} : vérifie-les avant de miser.</p>
</article>`;
}

function kpis(liste) {
  return `<div class="acc-kpis sb-kpis">${liste.map(([t, v, c, d]) =>
    `<div class="acc-kpi"><p>${e(t)}</p><strong class="${c}">${e(v)}</strong><span>${e(d)}</span></div>`).join('')}</div>`;
}

function rendreSurebets() {
  const S = D.surebets || {}, zone = document.getElementById('sb-actuels');
  if (!zone) return;
  const actuels = (S.actuels || []).filter(s => !s.suspect), suspects = (S.actuels || []).filter(s => s.suspect);
  document.getElementById('sb-maj').textContent = S.maj ? 'relevé de ' + hm(S.maj) : 'aucun relevé';
  zone.innerHTML = actuels.length ? actuels.map(carteSurebet).join('')
    : '<p class="vide">Aucun surebet au dernier relevé. Ils sont rares : quelques-uns par jour, souvent quelques minutes.</p>';
  document.getElementById('sb-suspects').innerHTML = suspects.length
    ? `<details class="mode-emploi"><summary>Écartés au dernier relevé (${suspects.length})</summary>${suspects.map(carteSurebet).join('')}</details>` : '';
  const b = (S.bilan || {})['7'] || {}, b30 = (S.bilan || {})['30'] || {};
  document.getElementById('sb-bilan').innerHTML = b.n ? kpis([
    ['Surebets (7 j)', String(b.n), '', `${b.un_pour_cent} à 1 % ou plus`],
    ['Rendement médian', '+' + fr2(100 * b.rendement_median) + ' %', 'pos', 'à la première détection'],
    ['Gain si tous pris', '+' + fr2(b.gain_100) + ' €', 'pos', '100 € répartis par surebet'],
    ['Durée médiane', b.duree_mediane_min == null ? '—' : Math.round(b.duree_mediane_min) + ' min', '', `${b.un_seul_cycle} vus un seul relevé`]
  ]) + `<p class="aide">Sur 30 jours : ${b30.n || 0} surebets, ${fr2(b30.gain_100 || 0)} € pour 100 € répartis à chaque fois.
Par bookmakers (7 j) : ${(b.par_bookmakers || []).slice(0, 5).map(x => `${e(x.cle)} ${x.n}`).join(' · ')}.</p>`
    : '<p class="aide">Pas encore de surebet suivi sur 7 jours.</p>';
  const eps = (S.episodes || []).slice(0, 20);
  document.getElementById('sb-episodes').innerHTML = eps.length ? eps.map(x =>
    `<div class="sb-episode"><span class="acc-meta">${e(quand(x.premier))} · ${x.cycles} relevé${x.cycles > 1 ? 's' : ''}</span>`
    + `<b>${e(x.match)}</b><span>${e(x.pari)} · ${e((x.bookmakers || []).join(' + '))}</span>`
    + `<span class="pos">+${fr2(100 * x.rendement_initial)} %${x.verifie ? '' : ' · non vérifié'}</span></div>`).join('')
    : '<p class="aide">Aucun épisode pour l’instant.</p>';
}

function carteCouvert(c) {
  const jambes = c.jambes.map(j => {
    const p = {bookmaker: j.bookmaker, lien: j.lien, lien_repli: j.lien_repli, statut: 'en_cours'};
    return `<div class="sb-jambe"><span class="acc-book">${e(j.bookmaker)}${j.boost ? ' · boost' : ''}</span><b>${e(j.boost ? (j.libelle_bookmaker || j.pari) : j.pari)}</b>`
      + `<span class="sb-cote">${cote(j.cote)}${j.cote_juste ? `<small> juste ${cote(j.cote_juste)}</small>` : ''}</span>`
      + `<span class="sb-mise">${euros(j.mise)}</span>${boutonBookmaker(p, true)}</div>`;
  }).join('');
  const verif = c.verifie ? '<span class="badge">vérifié par la cote juste</span>'
    : '<span class="badge sb-alerte">non vérifié : contrôle que le boost et la couverture portent sur le même pari</span>';
  return `<article class="sb-carte${c.suspect ? ' sb-suspect' : ''}">
<div class="sb-tete"><span class="acc-meta">${e(nomSport(c.sport))}${c.ligue ? ' · ' + e(c.ligue) : ''}</span>
<b>${e(c.match)}</b><span>${e(c.pari || '')} · ${horairePari(c)}</span></div>
<div class="sb-gain"><strong class="pos">+${fr2(100 * c.rendement)} %</strong>${verif}${c.suspect ? `<span class="badge sb-alerte">${e(c.suspect)}</span>` : ''}</div>
<div class="sb-jambes">${jambes}</div>
<p class="sb-retour">Boost misé ${euros(c.mise_boost)} ${c.mise_max ? '(mise max)' : '(mise max inconnue)'} · ${euros(c.mise_totale)} en tout · gain d'au moins
<b class="${signe(c.gain)}">${c.gain >= 0 ? '+' : ''}${euros(c.gain)}</b> quoi qu'il arrive. Mise d'abord le boost, puis la couverture. Cotes relevées à ${hm(c.detecte)} : vérifie-les avant de miser.</p>
</article>`;
}

function rendreCouverts() {
  const B = D.boosts || {}, zone = document.getElementById('bc-actuels');
  if (!zone) return;
  document.getElementById('bc-maj').textContent = B.maj ? 'relevé de ' + hm(B.maj) : 'aucun relevé';
  const tous = B.couverts || [], actuels = tous.filter(c => !c.suspect), suspects = tous.filter(c => c.suspect);
  zone.innerHTML = actuels.length ? actuels.map(carteCouvert).join('')
    : '<p class="vide">Aucun boost couvrable au dernier relevé : il faut un boost plus gros que la marge des autres issues.</p>';
  document.getElementById('bc-suspects').innerHTML = suspects.length
    ? `<details class="mode-emploi"><summary>Écartés au dernier relevé (${suspects.length})</summary>${suspects.map(carteCouvert).join('')}</details>` : '';
  const b = (B.bilan_couverts || {})['7'] || {}, b30 = (B.bilan_couverts || {})['30'] || {};
  document.getElementById('bc-bilan').innerHTML = b.n ? kpis([
    ['Boosts couverts (7 j)', String(b.n), '', `${b.verifies} vérifiés`],
    ['Rendement médian', '+' + fr2(100 * b.rendement_median) + ' %', 'pos', 'à la première lecture'],
    ['Gain si tous pris', (b.gain >= 0 ? '+' : '') + fr2(b.gain) + ' €', signe(b.gain), 'boost à sa mise max'],
    ['Mise engagée', fr2(b.mise) + ' €', '', 'boost et couvertures']
  ]) + `<p class="aide">Sur 30 jours : ${b30.n || 0} boosts couverts, ${fr2(b30.gain || 0)} € garantis s’ils avaient tous été pris.</p>`
    : '<p class="aide">Pas encore de boost couvert sur 7 jours.</p>';
  const eps = (B.episodes_couverts || []).slice(0, 20);
  document.getElementById('bc-episodes').innerHTML = eps.length ? eps.map(x =>
    `<div class="sb-episode"><span class="acc-meta">${e(quand(x.premier))} · ${x.cycles} relevé${x.cycles > 1 ? 's' : ''}</span>`
    + `<b>${e(x.match)}</b><span>${e(x.libelle || x.pari || '')} · ${e((x.bookmakers || []).join(' + '))}</span>`
    + `<span class="pos">+${fr2(100 * x.rendement_initial)} % · +${fr2(x.gain_initial)} €${x.verifie ? '' : ' · non vérifié'}</span></div>`).join('')
    : '<p class="aide">Aucun épisode pour l’instant.</p>';
}

// Mise conseillée (mise max du boost, 10 € si inconnue, comme cotes/boosts.py › MISE_DEFAUT) et gain attendu
// (mise × value, la même espérance que le « gain espéré » du bilan) : rien d'autre n'est calculé ici.
function conseilBoost(b) {
  const mise = b.mise_max || 10;
  return {mise, gain: b.value != null ? mise * b.value : null};
}

function ligneConseil(b, seuil) {
  const c = conseilBoost(b);
  const gain = c.gain != null ? `gain attendu <b class="${signe(c.gain)}">${c.gain >= 0 ? '+' : ''}${fr2(c.gain)} €</b>`
    : 'gain attendu inconnu (pas de cote juste)';
  const fort = b.value != null && seuil != null && b.value >= seuil ? ' <span class="badge">value ≥ ' + pct(seuil) + '</span>' : '';
  return `<p class="aide bo-conseil">Mise conseillée <b>${euros(c.mise)}</b>${b.mise_max ? '' : ' (mise max inconnue)'} · ${gain}${fort}</p>`;
}

function motifPasser(b) {
  if (b.exclusion) return b.exclusion;
  if (b.long_terme) return 'pari de saison : pas jugé';
  if (b.value != null) return `value ${pct(b.value)}`;
  return b.statut || '';
}

function carteBoost(b, seuil) {
  const p = {bookmaker: b.bookmaker, lien: b.lien, statut: 'en_cours'};
  const value = b.value != null
    ? `<i class="acc-ecart">${pct(b.value)}</i><small class="acc-ref">juste ${cote(b.cote_juste)} (${e(b.reference)})</small>`
    : `<small class="acc-ref">${b.hausse != null ? `hausse ${pct(b.hausse)} · gagnant si la marge d’origine est sous ${fr2(100 * b.marge_seuil)} %${b.marge_attendue != null ? ` (habituelle ≈ ${fr2(100 * b.marge_attendue)} %)` : ''}` : 'sans cote juste ni cote d’avant'}</small>`;
  const verdict = b.verdict ? `<span class="badge verdict ${b.verdict}">${b.verdict === 'jouer' ? 'Jouer' : 'Passer'}</span>` : '';
  const detail = b.pari ? `${e(b.pari)}${b.verifie ? '' : ' (cote habituelle non retrouvée)'}` : e(b.statut || '');
  return `<article class="acc-pari"><div class="acc-pari-texte"><span class="acc-meta">${b.sport ? e(nomSport(b.sport)) + ' · ' : ''}${e(b.domicile)} – ${e(b.exterieur)}</span>
<b>${e(b.libelle)}</b><span>${detail}</span><span class="pari-debut">Match ${horairePari(b)}</span></div>
<div class="acc-pari-prix"><span class="acc-book">${e(b.bookmaker)}${b.mise_max ? ' · mise max ' + euros(b.mise_max) : ''}</span>
${verdict}<b class="acc-cote">${cote(b.cote)}</b><small class="acc-ref">avant ${cote(b.cote_avant)}</small>${value}${boutonBookmaker(p, true)}</div>
${b.verdict === 'jouer' ? ligneConseil(b, seuil) : `<p class="aide bo-conseil">${e(motifPasser(b))}</p>`}</article>`;
}

// « À jouer » en tête (value d'abord, de la plus forte à la plus faible, puis les boosts jugés sans cote juste), le
// reste replié. L'ordre et le verdict viennent de cotes/boosts.py › evaluer ; rien n'est recalculé.
function trierBoosts(actuels) {
  const aJouer = actuels.filter(b => b.verdict === 'jouer'), aPasser = actuels.filter(b => b.verdict !== 'jouer');
  aJouer.sort((a, b) => (a.value == null) - (b.value == null) || (b.value || 0) - (a.value || 0));
  return {aJouer, aPasser};
}

function rendreBoostsListe() {
  const B = D.boosts || {}, zone = document.getElementById('bo-actuels');
  if (!zone) return;
  document.getElementById('bo-maj').textContent = B.maj ? 'relevé de ' + hm(B.maj) : 'aucun relevé';
  const actuels = B.actuels || [], {aJouer, aPasser} = trierBoosts(actuels), seuil = B.seuil_alerte;
  const attendu = aJouer.reduce((t, b) => t + (conseilBoost(b).gain || 0), 0);
  const tete = aJouer.length ? `<p class="aide bo-resume"><b>${aJouer.length} à jouer</b> · gain attendu total `
    + `<b class="${signe(attendu)}">${attendu >= 0 ? '+' : ''}${fr2(attendu)} €</b> à la mise conseillée</p>` : '';
  const replies = aPasser.length ? `<details class="mode-emploi"><summary>À passer (${aPasser.length})</summary>`
    + aPasser.map(b => carteBoost(b, seuil)).join('') + '</details>' : '';
  zone.innerHTML = (aJouer.length ? tete + aJouer.map(b => carteBoost(b, seuil)).join('')
    : `<p class="vide">Aucun boost à jouer au dernier relevé${actuels.length ? ` (${actuels.length} à passer)` : ''}.</p>`) + replies;
  const b = (B.bilan || {})['7'] || {};
  document.getElementById('bo-bilan').innerHTML = b.n && b.jouer != null ? kpis([
    ['À jouer (7 j)', String(b.jouer), b.jouer ? 'pos' : '', `sur ${b.n} boosts lus`]
  ]) : '';
}

function rendreBoosts() {
  const champ = document.getElementById('sb-total');
  if (champ && !champ.dataset.lie) {
    champ.dataset.lie = '1'; champ.value = sbTotal;
    champ.addEventListener('change', () => {
      const v = Number(champ.value);
      if (v >= 10 && v <= 100000) { sbTotal = v; ecrire(SB_CLE_TOTAL, String(v)); rendreSurebets(); }
      else champ.value = sbTotal;
    });
  }
  rendreSurebets();
  rendreCouverts();
}

// Bilan › Boosts : boosts « jouer » à régler à la main (texte à copier pour Claude) et boosts réglés
// (donnees/boosts_resultats.json, scripts/regler_boosts.py).
function texteBoostsARegler(liste) {
  const jour = x => x ? new Intl.DateTimeFormat('fr-FR', {timeZone: 'Europe/Paris', weekday: 'short', day: '2-digit',
    month: '2-digit', hour: '2-digit', minute: '2-digit'}).format(new Date(x)) : '?';
  const match = b => [b.domicile, b.exterieur].filter(Boolean).join(' – ');
  return ['Boosts à régler (gagné / perdu / remboursé) :'].concat(liste.map(b =>
    `${b.code} · ${jour(b.debut)} · ${b.bookmaker} · ${match(b)} · ${b.libelle} · cote ${fr2(b.cote)} · mise ${fr2(b.mise)} €`)).join('\n');
}
function rendreBilanBoosts() {
  rendreBoostsListe();
  const B = D.boosts || {}, zone = document.getElementById('bb-a-regler');
  if (!zone) return;
  const aRegler = B.a_regler || [], regles = B.regles || [], s = B.bilan_regles || {}, av = B.bilan_regles_avant || {};
  const depuis = B.date_regles ? ' depuis le ' + new Intl.DateTimeFormat('fr-FR', {timeZone: 'Europe/Paris', day: '2-digit',
    month: '2-digit'}).format(new Date(B.date_regles)) : '';
  document.getElementById('bb-kpis').innerHTML = s.n ? kpis([
    ['Gain net', (s.gain >= 0 ? '+' : '') + fr2(s.gain) + ' €', signe(s.gain), `${s.n} boosts réglés${depuis}`],
    ['ROI', s.roi == null ? '—' : pct(s.roi), signe(s.gain), `${fr2(s.mise)} € misés`],
    ['Gagnés', `${s.gagnes}/${s.n}`, '', 'boosts gagnés']
  ]) : `<p class="aide">Aucun boost réglé${depuis} : le bilan repart de zéro avec les règles actuelles.</p>`;
  document.getElementById('bb-avant').textContent = av.n ? `Avant les règles actuelles : ${av.n} réglés, `
    + `${av.gagnes} gagnés, ${(av.gain >= 0 ? '+' : '') + fr2(av.gain)} € (ROI ${av.roi == null ? '—' : pct(av.roi)}).` : '';
  document.getElementById('bb-n').textContent = aRegler.length ? String(aRegler.length) : '';
  zone.innerHTML = aRegler.length
    ? `<textarea class="bb-texte" id="bb-texte" readonly rows="${Math.min(12, aRegler.length + 1)}">${e(texteBoostsARegler(aRegler))}</textarea>
<p><button type="button" class="btn" id="bb-copier">Copier la liste</button> <span class="aide" id="bb-copie" role="status"></span></p>`
    : '<p class="aide">Rien à régler.</p>';
  const bouton = document.getElementById('bb-copier');
  if (bouton) bouton.onclick = async () => {
    const t = document.getElementById('bb-texte'), msg = document.getElementById('bb-copie');
    try { await navigator.clipboard.writeText(t.value); msg.textContent = 'Copié. Colle-le dans ton message à Claude.'; }
    catch { t.select(); msg.textContent = 'Sélectionné : copie-le à la main.'; }
  };
  const mot = {gagne: 'Gagné', perdu: 'Perdu', rembourse: 'Remboursé'};
  document.getElementById('bb-regles').innerHTML = regles.length ? regles.map(r =>
    `<div class="acc-resultat"><span><b>${e([r.domicile, r.exterieur].filter(Boolean).join(' – '))}</b>
<small>${e(r.libelle)} · ${e(r.bookmaker)} ${fr2(r.cote)} · mise ${fr2(r.mise)} €${r.score ? ' · ' + e(r.score) : ''} · ${mot[r.statut] || e(r.statut)}</small></span>
<b class="${signe(r.gain)}">${(r.gain >= 0 ? '+' : '') + fr2(r.gain)} €</b></div>`).join('')
    : '<p class="aide">Aucun boost réglé pour l’instant.</p>';
  rendreTypesBoosts(B.bilan_types);
}

// Gagnés contre attendus par type de pari : historique de cotes-boostees + boosts réglés ici (cotes/boosts.py › bilan_types).
function rendreTypesBoosts(T) {
  const zone = document.getElementById('bb-types');
  if (!zone) return;
  if (!T || !(T.types || []).length) { zone.innerHTML = ''; return; }
  const fr1 = x => Number(x).toFixed(1).replace('.', ',');
  const mot = {prendre: 'Prendre', eviter: 'Éviter', neutre: 'Neutre'};
  document.getElementById('bb-types-note').textContent = `Gagnés attendus = somme des 1/cote. Point de départ : ${T.source}, `
    + `plus les boosts réglés ici. ROI espéré rétréci vers la moyenne ; « Prendre » à partir de ${pct(T.seuil)} sur `
    + `au moins ${T.min} boosts réglés. Un suivi : seuls les types « ne plus jouer » changent le verdict.`;
  zone.innerHTML = `<div class="tableau"><table><tr><th>Type</th><th>Réglés<small>dont ici</small></th>`
    + `<th>Gagnés<small>attendus</small></th><th>ROI espéré</th><th>Conseil</th></tr>`
    + T.types.map(t => `<tr><td>${e(t.type)}</td><td>${t.paris}<small>${t.ici.paris}</small></td>`
      + `<td>${t.gagnes}<small>${fr1(t.attendus)}</small></td><td class="${signe(t.roi_espere)}">${pct(t.roi_espere)}</td>`
      + `<td>${t.exclu ? 'Ne plus jouer' : mot[t.conseil] || e(t.conseil)}</td></tr>`).join('') + '</table></div>';
}
