// Une petite empreinte publiée avec le HTML, sans appel aux API de cotes. Une nouvelle publication n'interrompt jamais la
// lecture : un bandeau discret propose « Actualiser » ; la page ne se recharge que sur ce geste, à la même place.
function installerActualisation({version, capturer, restaurer}) {
  const cle = 'cv-actualisation-v1';
  const lireSession = () => {try {return JSON.parse(sessionStorage.getItem(cle) || '{}');} catch {return {};}};
  const sauver = objet => {try {sessionStorage.setItem(cle, JSON.stringify(objet));} catch {}};
  const precedente = lireSession();
  if (precedente.etat && Date.now() - precedente.date < 600000) {
    try {restaurer(precedente.etat);} catch {}
  }
  // Ne restaurer qu'une fois.
  sauver({});
  const adresse = new URL(location.href);
  const cibleAdresse = adresse.searchParams.get('_cv');
  if (adresse.searchParams.has('_cv')) {
    adresse.searchParams.delete('_cv');
    history.replaceState(null, '', adresse.href);
  }
  const ouverture = Date.now();
  let enCours = false, derniere = -Infinity, proposee = null;
  function proposer(cible) {
    if (proposee === cible) return;
    proposee = cible;
    let bandeau = document.getElementById('actualisation');
    if (!bandeau) {
      bandeau = document.createElement('div');
      bandeau.id = 'actualisation'; bandeau.className = 'actualisation';
      bandeau.setAttribute('role', 'status');
      document.body.appendChild(bandeau);
    }
    bandeau.innerHTML = '<span>Nouvelles données</span><button type="button">Actualiser</button>';
    bandeau.hidden = false;
    bandeau.querySelector('button').onclick = () => {
      sauver({date:Date.now(), etat:capturer()});
      const destination = new URL(location.href);
      destination.searchParams.set('_cv', cible);         // contourne un cache encore ancien
      location.replace(destination.href);
    };
  }
  async function verifier() {
    if (document.visibilityState !== 'visible' || enCours || Date.now()-derniere < 10000) return;
    enCours = true; derniere = Date.now();
    try {
      const url = new URL('./version.json', location.href);
      url.searchParams.set('t', String(Date.now()));
      const r = await fetch(url, {cache:'no-store', signal:AbortSignal.timeout(10000)});
      if (!r.ok) return;
      const {version:cible} = await r.json();
      if (!/^[a-f0-9]{64}$/.test(cible) || cible === version) return;
      // HTML encore ancien juste après une actualisation (cache du CDN) : ne pas la reproposer tout de suite.
      if (cibleAdresse === cible && Date.now()-ouverture < 300000) return;
      proposer(cible);
    } catch {
      // Hors ligne ou publication en cours : conserver la page et réessayer.
    } finally {enCours = false;}
  }
  document.addEventListener('visibilitychange', verifier);
  window.addEventListener('focus', verifier);
  window.addEventListener('pageshow', verifier);
  window.addEventListener('online', () => {derniere = -Infinity; return verifier();});
  setInterval(verifier, 60000);
  verifier();
}
