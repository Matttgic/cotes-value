// Une petite empreinte publiée avec le HTML, sans appel aux API de cotes.
function installerActualisation({version, capturer, restaurer, protegee}) {
  const cle = 'cv-actualisation-v1';
  const lireSession = () => {try {return JSON.parse(sessionStorage.getItem(cle) || '{}');} catch {return {};}};
  const sauver = objet => {try {sessionStorage.setItem(cle, JSON.stringify(objet));} catch {}};
  const precedente = lireSession();
  if (precedente.etat && Date.now() - precedente.date < 600000) {
    try {restaurer(precedente.etat);} catch {}
  }
  // Ne restaurer qu'une fois ; garder le garde-fou contre un CDN encore ancien.
  sauver({cible:precedente.cible, tentative:precedente.tentative});
  const adresse = new URL(location.href);
  const cibleAdresse = adresse.searchParams.get('_cv');
  if (adresse.searchParams.has('_cv')) {
    adresse.searchParams.delete('_cv');
    history.replaceState(null, '', adresse.href);
  }
  const ouverture = Date.now();
  let enCours = false, navigation = false, derniere = -Infinity, interaction = -Infinity;
  document.addEventListener('input', () => {interaction = Date.now();});
  document.addEventListener('focusin', ev => {
    if (['INPUT','SELECT','TEXTAREA'].includes(ev.target?.tagName)) interaction = Date.now();
  });
  async function verifier() {
    if (document.visibilityState !== 'visible' || enCours || navigation || Date.now()-derniere < 10000) return;
    enCours = true; derniere = Date.now();
    try {
      const url = new URL('./version.json', location.href);
      url.searchParams.set('t', String(Date.now()));
      const r = await fetch(url, {cache:'no-store', signal:AbortSignal.timeout(10000)});
      if (!r.ok) return;
      const {version:cible} = await r.json();
      if (!/^[a-f0-9]{64}$/.test(cible) || cible === version || document.visibilityState !== 'visible') return;
      // Laisser finir la saisie et les réglages des notifications.
      if (protegee() || Date.now()-interaction < 5000) return;
      const avant = lireSession();
      if (avant.cible === cible && Date.now()-avant.tentative < 300000) return;
      if (cibleAdresse === cible && Date.now()-ouverture < 300000) return;
      sauver({cible, tentative:Date.now(), date:Date.now(), etat:capturer()});
      navigation = true;
      const destination = new URL(location.href);
      destination.searchParams.set('_cv', cible);
      location.replace(destination.href);
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
