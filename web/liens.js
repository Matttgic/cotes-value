// Bouton « Parier chez … » : ouvre la page du match chez le bookmaker, en un toucher (l'application du
// bookmaker s'ouvre à la place du navigateur quand le téléphone l'associe au site). Seulement pour un pari
// en cours, et seulement vers le site d'un des bookmakers suivis (même liste que la notification Chrome).
const HOTES_PARIS=/(^|\.)(winamax\.fr|betclic\.fr|pmu\.fr|unibet\.fr|olybet\.fr|netbet\.fr)$/;
function lienPari(p) {
  if(!p || p.statut!=='en_cours' || typeof p.lien!=='string' || p.lien.length>600) return null;
  try {
    const u=new URL(p.lien);
    return u.protocol==='https:' && !u.port && !u.username && !u.password && HOTES_PARIS.test(u.hostname) ? u.href : null;
  } catch { return null; }
}
// court : dans la ligne repliée d'un pari ; sinon le bouton complet. Le lien de repli (page du sport, le
// match à chercher) est annoncé comme tel.
function boutonBookmaker(p, court=false) {
  const u=lienPari(p);
  if(!u) return '';
  const chez=p.bookmaker || 'le bookmaker';
  const texte=p.lien_repli ? (court ? `${chez} : sport ›` : `Page du sport chez ${chez} › (match à chercher)`)
    : (court ? `Parier chez ${chez} ›` : `Ouvrir le match chez ${chez} ›`);
  return `<a class="btn lien-bookmaker${court?' court':''}${p.lien_repli?' repli':''}" href="${e(u)}" target="_blank" rel="noopener noreferrer"`
    + ` onclick="event.stopPropagation()">${e(texte)}</a>`;
}
