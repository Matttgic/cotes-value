import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';

const contexte=vm.createContext({
  e:s=>String(s??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;'),
  pct:x=>x==null?'—':String(x*100)+' %',eur:x=>String(x)+' €',signe:x=>x>0?'pos':x<0?'neg':''
});
vm.runInContext(readFileSync(new URL('../web/visuels.js',import.meta.url),'utf8'),contexte);
const fn=nom=>(...args)=>contexte[nom](...args);
test('les mini-courbes distinguent absence de données et gain nul',()=>{
  assert.ok(!fn('miniCourbe')([]).includes('<path'));
  for(const points of [[[1,0]],[[1,-10],[1,0]],[[1,5],[2,10]],[[1,-10],[2,-5]],[[1,NaN],[2,Infinity]]]) {
    const svg=fn('miniCourbe')(points);
    assert.ok(!/NaN|Infinity/.test(svg));
  }
  const svg=fn('miniCourbe')([[1,-10],[2,5]]);
  assert.ok(svg.includes('2 règlements') && svg.includes('échelle propre'));
  assert.ok(svg.includes('stroke-dasharray="3 3"'));
});
test('les remboursements et autres règlements ne sont pas assimilés à des pertes',()=>{
  const html=fn('repartitionResultats')({regles:10,gagnes:6,perdus:3});
  assert.ok(html.includes('6 gagnés, 3 perdus, 1 autre réglé'));
  assert.ok(html.includes('width:60%') && html.includes('width:30%') && html.includes('width:10%'));
  assert.ok(!fn('repartitionResultats')({regles:0}).includes('resultats-repartition'));
});
test('couverture CLV : aucune moyenne ni couverture inventée',()=>{
  assert.ok(fn('couvertureCLV')({regles:10,clv_n:4}).includes('width:40%'));
  assert.ok(fn('couvertureCLV')({regles:0,clv_n:0}).includes('width:0%'));
  const html=fn('carteStrategieVisuelle')({id:'x',nom:'Claude',detail:'<test>',reussite:null,
    stats:{regles:0,clv:null,roi:null,gain:0,paris:2,attente:2,gagnes:0,perdus:0}},[]);
  assert.ok(html.includes('2 prises · 2 en attente') && html.includes('&lt;test>'));
  assert.ok(!html.includes('NaN') && !html.includes('0 €'));
});
test('les visuels des sports et bookmakers restent locaux et échappés',()=>{
  assert.ok(fn('iconeSport')('football').includes('<svg'));
  assert.ok(fn('iconeSport')('inconnu').includes('<svg'));
  assert.ok(fn('monogrammeBookmaker')('<script>').includes('&lt;'));
  assert.ok(!fn('monogrammeBookmaker')('<script>').includes('<script>'));
});
test('les deux vues graphiques / comparaison se remplacent et le choix est mémorisé',()=>{
  const etats=new Map(),boutons=['liste','graphiques'].map(vue=>({dataset:{vueStrategies:vue},setAttribute:(k,v)=>etats.set(vue+':'+k,v)}));
  const zones={'strategies-vue-liste':{},'strategies-vue-graphiques':{}};
  const ctx=vm.createContext({document:{getElementById:id=>zones[id],querySelectorAll:()=>boutons},ecrire:(k,v)=>etats.set(k,v)});
  const code=readFileSync(new URL('../web/interface.js',import.meta.url),'utf8');
  vm.runInContext(code.slice(code.indexOf('function choisirVueStrategies'),code.indexOf('function connexion')),ctx);
  ctx.choisirVueStrategies('graphiques');assert.equal(zones['strategies-vue-liste'].hidden,true);
  assert.equal(etats.get('graphiques:aria-pressed'),'true');assert.equal(etats.get('cv-vue-strategies-lignes'),'graphiques');
  ctx.choisirVueStrategies('liste');assert.equal(zones['strategies-vue-graphiques'].hidden,true);
  assert.equal(etats.get('liste:aria-pressed'),'true');
});
test('une stratégie se déplie sur place, avec un bouton distinct pour ses paris',()=>{
  const r={id:'Betfair <1>',nom:'Betfair · B01',detail:'Critères complets',reussite:60,
    stats:{regles:10,paris:12,attente:2,gagnes:6,perdus:4,gain:12,roi:12,clv:2,clv_n:8,gains_bruts:52,pertes_brutes:40}};
  const html=fn('carteStrategieVisuelle')(r,[[1,-10],[2,12]]);
  assert.ok(html.startsWith('<details class="ligne-detail ligne-strategie"'));
  const summary=html.slice(0,html.indexOf('</summary>'));
  assert.ok(summary.includes('Betfair · B01') && summary.includes('10 paris réglés'));
  assert.ok(!summary.includes('<button') && !summary.includes('<svg'));
  assert.ok(html.includes('data-strategie="Betfair &lt;1>"'));
  assert.ok(html.indexOf('mini-courbe')>html.indexOf('ligne-corps'));
  assert.ok(html.includes('8/10 mesurés') && html.includes('6 gagnés, 4 perdus'));
});

test('les règles par référence ont un libellé court et gardent leur identité complète',()=>{
  const html=fn('carteStrategieVisuelle')({id:'PIN-1.5-3-e2-h36',nom:'Pinnacle · PIN-1.5-3-e2-h36',nomCourt:'PIN 1,5–3 · 2%/36h',detail:'Cotes 1,5–3, edge ≥ 2 %, ≤ 36 h',stats:{regles:0,paris:0,attente:0}},[]);
  assert.ok(html.includes('>PIN 1,5–3 · 2%/36h</span>'));
  assert.ok(html.includes('<h3>Pinnacle · PIN-1.5-3-e2-h36</h3>'));
});
