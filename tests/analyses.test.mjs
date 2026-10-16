import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
const source=readFileSync(new URL('../web/analyses.js',import.meta.url),'utf8');
function contexte(extra={}) {
  const c=vm.createContext({Intl,Date,console,e:s=>String(s??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;'),nomsSports:{football:'Football'},pas:span=>span/4 || 1,quand:s=>s || '—',...extra});
  vm.runInContext(source,c);return c;
}
const pari=(id,plus={})=>({id,unique_bilan:true,sport:'football',bookmaker:'Unibet',reference:'Pinnacle',statut:'gagne',gain:10,mise:10,cote:2,detecte:'2026-10-15T10:00:00Z',debut:'2026-10-15T12:00:00Z',regle_le:'2026-10-15T14:00:00Z',clv:.02,...plus});
test('la déduplication vient du Bilan avant les filtres, pas du classement ou des résultats',()=>{
  const c=contexte(),rows=[pari('a'),pari('b',{unique_bilan:false,bookmaker:'Betclic',gain:500}),pari('c',{sport:'tennis'})];
  assert.deepEqual(Array.from(c.lignesAnalyse({},rows,{periode:'tout',selection:'uniques'}),p=>p.id),['a','c']);
  assert.equal(c.lignesAnalyse({},rows,{periode:'tout',selection:'uniques',book:'Betclic'}).length,0);
  assert.deepEqual(Array.from(c.lignesAnalyse({},rows,{periode:'futur',sport:'football'}),p=>p.id),['a']);
});
test('les règlements tardifs restent en attente dans l’historique figé uniquement',()=>{
  const c=contexte(),d={laboratoire:{releve:'2026-10-14T10:09:00Z'}};
  const rows=[pari('ancien',{detecte:'2026-10-12T10:00:00Z',debut:'2026-10-13T18:00:00Z',regle_le:'2026-10-15T14:00:00Z'}),pari('connu',{detecte:'2026-10-12T10:00:00Z',debut:'2026-10-13T18:00:00Z',regle_le:'2026-10-13T20:00:00Z'})];
  const hist=c.lignesAnalyse(d,rows,{periode:'ensemble'});
  assert.equal(hist[0].statut,'en_cours');assert.equal(hist[0].gain,null);assert.equal(hist[0].clv,null);
  assert.equal(c.statsAnalyse(hist).gain,10);assert.equal(c.statsAnalyse(hist).attente,1);
  assert.equal(c.statsAnalyse(c.lignesAnalyse(d,rows,{periode:'tout'})).gain,20);
  assert.equal(rows[0].statut,'gagne');
});
test('le suivi utilise les IDs officiels de chaque stratégie et conserve une seule prise par ID',()=>{
  const c=contexte(),rows=[pari('a'),pari('b'),pari('c')];
  const d={laboratoire:{navigation:{selections:{Claude:{futur:['b'],ensemble:['a','b']}}}}};
  assert.deepEqual(Array.from(c.lignesAnalyse(d,rows,{selection:'Claude',periode:'futur'}),p=>p.id),['b']);
  assert.deepEqual(Array.from(c.lignesAnalyse(d,rows,{selection:'Claude',periode:'tout'}),p=>p.id),['a','b']);
});
test('le ROI utilise les mises réglées ; CLV manquante, zéro, remboursement et demi-perte restent distincts',()=>{
  const c=contexte(),rows=[pari('a',{mise:20,gain:20,clv:0}),pari('b',{statut:'demi_perdu',gain:-5,clv:null}),pari('c',{statut:'rembourse',gain:0,clv:.03}),pari('d',{statut:'a_regler',gain:null,clv:null})];
  const s=c.statsAnalyse(rows);
  assert.equal(s.regles,3);assert.equal(s.attente,1);assert.equal(s.mises,40);assert.equal(s.gain,15);assert.equal(s.roi,.375);
  assert.equal(s.clv_n,2);assert.equal(s.clv,.015);assert.equal(s.reussite,1/3);
  const vide=c.statsAnalyse([]);assert.equal(vide.roi,null);assert.equal(vide.clv,null);assert.equal(vide.gain,null);
});
test('le repli maximal suit l’ordre des règlements et inclut le capital de départ à zéro',()=>{
  const c=contexte(),rows=[pari('c',{regle_le:'2026-10-15T16:00:00Z',gain:30}),pari('b',{regle_le:'2026-10-15T15:00:00Z',gain:-10,statut:'perdu'}),pari('a',{gain:-10,statut:'perdu'})];
  const s=c.statsAnalyse(rows);assert.equal(s.drawdown,20);assert.equal(s.gain,10);
  assert.deepEqual(Array.from(s.courbe,p=>p[1]),[-10,-20,10]);assert.deepEqual(Array.from(s.replis,p=>p[1]),[-10,-20,0]);
});
test('les jours sont calculés en heure de Paris et les jours sans règlement restent à zéro',()=>{
  const c=contexte();assert.equal(c.jourAnalyse('2026-10-15T23:30:00Z'),'2026-10-16');
  const points=c.seriesQuotidiennesAnalyse([pari('a',{regle_le:'2026-10-15T23:30:00Z'}),pari('b',{regle_le:'2026-10-18T12:00:00Z'})]);
  assert.equal(points.length,3);assert.equal(points[1].valeur,0);assert.equal(points[1].detail,'0 règlements');
});
test('les graphiques gèrent les zéros, absences et valeurs négatives sans NaN ni faux succès',()=>{
  const c=contexte();
  for(const points of [[],[[1,0]],[[1,-10],[2,-20]],[[1,10],[2,0]]]) {
    const html=c.ligneGraphiqueAnalyse(points,'Courbe');assert.ok(!/NaN|Infinity/.test(html));
  }
  assert.ok(c.anneauAnalyse([],'Vide').includes('Aucune donnée'));
  const html=c.anneauAnalyse([{nom:'<script>',n:1},{nom:'Perdus',n:1}],'Résultats');assert.ok(html.includes('&lt;script>'));assert.ok(!html.includes('<script>'));
  assert.ok(c.barresAnalyse([{nom:'Betfair',clv:null,clv_n:0,regles:5}],'clv',c.tauxAnalyse).includes('—'));
});
test('les filtres recomposent tous les graphiques et les indicateurs à partir du même sous-ensemble',()=>{
  const elements=new Map();for(const id of ['analyse-graphiques','analyse-selection','analyse-periode','analyse-sport','analyse-book','analyse-periode-badge','analyse-contexte','analyse-vide','analyse-kpis']) elements.set(id,{value:'',innerHTML:'',classList:{toggle:()=>{}}});
  elements.get('analyse-selection').value='uniques';elements.get('analyse-periode').value='futur';
  const c=contexte({document:{getElementById:id=>elements.get(id)},D:{},fiches:[pari('a'),pari('b',{sport:'tennis',gain:-10,statut:'perdu',clv:null})]});
  c.rendreAnalyses();assert.equal((elements.get('analyse-graphiques').innerHTML.match(/<figure/g) || []).length,8);assert.ok(elements.get('analyse-contexte').textContent.includes('2 prises'));
  elements.get('analyse-sport').value='tennis';c.rendreAnalyses();assert.ok(elements.get('analyse-contexte').textContent.includes('1 prises'));assert.ok(elements.get('analyse-kpis').innerHTML.includes('-10'));
  elements.get('analyse-book').value='Inconnu';c.rendreAnalyses();assert.equal(elements.get('analyse-vide').hidden,false);assert.equal(elements.get('analyse-graphiques').innerHTML,'');
});
