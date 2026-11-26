import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
// Bilan › Paris uniques › Par mise : mise moyenne, médiane, max et tranches (web/modele.html).
const page=readFileSync(new URL('../web/modele.html',import.meta.url),'utf8');
const bout=(debut)=>{const i=page.indexOf(debut);assert.ok(i>=0,debut);return page.slice(i,page.indexOf('\n}\n',i)+2);};
const tranches=page.match(/const TRANCHES_MISE = .*;/)[0];
const c=vm.createContext({});
vm.runInContext(`${tranches}\n${bout('function statsMises(L)')}\nthis.TRANCHES_MISE=TRANCHES_MISE;`,c);

test('mise moyenne, médiane et max ; null sans pari',()=>{
  assert.equal(c.statsMises([]),null);
  const s=c.statsMises([{mise:1},{mise:2},{mise:20},{mise:3}]);
  assert.deepEqual({...s},{n:4,moyenne:6.5,mediane:2.5,max:20});
  assert.equal(c.statsMises([{mise:4},{}]).max,10);          // mise absente : 10 € fixes
});

test('tranches de mise contiguës, sans trou ni chevauchement',()=>{
  const t=c.TRANCHES_MISE;
  assert.equal(t[0][0],0);assert.equal(t.at(-1)[1],Infinity);
  for(let i=1;i<t.length;i++) assert.equal(t[i][0],t[i-1][1]);
});
