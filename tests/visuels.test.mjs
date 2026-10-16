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
  assert.ok(html.includes('6 gagnés, 3 perdus, 1 autres réglés'));
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
  assert.equal(etats.get('graphiques:aria-pressed'),'true');assert.equal(etats.get('cv-vue-strategies'),'graphiques');
  ctx.choisirVueStrategies('liste');assert.equal(zones['strategies-vue-graphiques'].hidden,true);
  assert.equal(etats.get('liste:aria-pressed'),'true');
});
