// Effets de présentation : bandeau de cotation de l'Accueil (statique) et fondu court entre onglets (View Transitions).
// Rien ne bouge si l'appareil demande moins de mouvement.

// Changement d'onglet : fondu enchaîné natif quand le navigateur le permet.
function basculer(action) {
  if(document.startViewTransition && animationsPermises()) document.startViewTransition(action);
  else action();
}

// Bandeau boursier de l'Accueil, façon cotation de Wall Street : chiffres clés, paris à jouer (▲ vert), derniers
// résultats (▲ gain, ▼ perte). Le bandeau est statique : il défile au doigt, pas tout seul.
function bandeauBoursier(elements) {
  const une=document.querySelector('#o-accueil .une-tete');if(!une) return;
  let bandeau=une.querySelector('.cv-bandeau');
  if(!elements.length){bandeau?.remove();return;}
  if(!bandeau){
    bandeau=document.createElement('div');bandeau.className='cv-bandeau';bandeau.setAttribute('role','region');
    bandeau.setAttribute('aria-label','Cotation du jour');
    bandeau.tabIndex=0;une.prepend(bandeau);   // défile au clavier aussi (WCAG 2.1.1)
  }
  const fleche=c=>c==='pos'?'▲':c==='neg'?'▼':'';
  const html=elements.map(([nom,valeur,variation,classe])=>`<span class="cv-cote"><span class="cv-sym">${e(nom)}</span> <b>${e(valeur)}</b>${variation||classe?` <i class="${classe||''}">${fleche(classe)}${variation?' '+e(variation):''}</i>`:''}</span>`).join('');
  bandeau.innerHTML=`<div class="cv-piste">${html}</div>`;
}
