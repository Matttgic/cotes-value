import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';
import assert from 'node:assert/strict';
const source=readFileSync(new URL('../web/suivi.js',import.meta.url),'utf8');
const mem={};
const c=vm.createContext({Intl,Date,JSON,Object,Number,Set,lire:k=>mem[k]??null,ecrire:(k,v)=>{mem[k]=v;},e:s=>String(s??''),D:{}});
vm.runInContext(source,c);
const at=s=>Date.parse(s);
const eq=(a,b)=>assert.equal(JSON.stringify(a),JSON.stringify(b));

test('Cocher ouvre une période, décocher la ferme, recocher en ouvre une autre',()=>{
  let etat=c.suiviSynchroniser({}, ['pin2','pol1'], at('2026-10-20T10:00:00Z'));
  eq(etat.pin2,[[at('2026-10-20T10:00:00Z'),null]]);
  etat=c.suiviSynchroniser(etat, ['pin2'], at('2026-10-20T12:00:00Z'));
  eq(etat.pol1,[[at('2026-10-20T10:00:00Z'),at('2026-10-20T12:00:00Z')]]);
  assert.equal(etat.pin2[0][1],null);
  etat=c.suiviSynchroniser(etat, ['pin2','pol1'], at('2026-10-20T14:00:00Z'));
  assert.equal(etat.pol1.length,2);
  assert.equal(vm.runInContext('suiviCompte',c)(etat.pol1,at('2026-10-20T11:00:00Z')),true);
  assert.equal(vm.runInContext('suiviCompte',c)(etat.pol1,at('2026-10-20T13:00:00Z')),false);   // décochée : plus de paris
  assert.equal(vm.runInContext('suiviCompte',c)(etat.pol1,at('2026-10-20T15:00:00Z')),true);
});

test('Début imposé à l’amorçage (abonnement existant)',()=>{
  const etat=c.suiviSynchroniser({}, ['pin2'], at('2026-10-20T14:00:00Z'), at('2026-10-20T10:00:00Z'));
  assert.equal(etat.pin2[0][0],at('2026-10-20T10:00:00Z'));
});

const prises=[
  {id:1,detecte:'2026-10-20T11:00:00Z',statut:'gagne',cote:2,strategies:['pin2'],unique_bilan:true},   // avant la coche
  {id:2,detecte:'2026-10-20T12:30:00Z',statut:'gagne',cote:2,gain:10,strategies:['pin2'],regles:['pol1'],unique_bilan:true},
  {id:3,detecte:'2026-10-20T13:00:00Z',statut:'perdu',cote:1.8,strategies:['pol1']},                    // pol1 décochée
  {id:4,detecte:'2026-10-20T13:30:00Z',statut:'en_cours',cote:1.5,strategies:['pin2'],convergence:true},
];
const etat={pin2:[[at('2026-10-20T12:00:00Z'),null]],pol1:[[at('2026-10-20T12:00:00Z'),at('2026-10-20T12:45:00Z')]]};

test('Seules les prises détectées pendant la coche comptent, avec leurs puces',()=>{
  const l=c.suiviPrises(prises,{etat});
  eq(l.map(p=>p.id),[2,4]);
  eq([...l[0].suivies].sort(),['pin2','pol1']);
  eq(l[1].suivies,['pin2']);
});

test('Filtre de période et bilan',()=>{
  const b=c.suiviBornes('2026-10-20','2026-10-20');
  assert.equal(b.depuis,at('2026-10-19T22:00:00Z'));          // minuit à Paris (UTC+2)
  assert.equal(b.jusqua,at('2026-10-20T22:00:00Z'));
  assert.equal(c.suiviBornes('2026-10-25','2026-10-25').depuis,at('2026-10-24T22:00:00Z'));
  assert.equal(c.suiviBornes('2026-10-26','').depuis,at('2026-10-25T23:00:00Z'));   // heure d’hiver
  const l=c.suiviPrises(prises,{etat,depuis:at('2026-10-20T13:00:00Z')});
  eq(l.map(p=>p.id),[4]);
  const r=c.suiviBilan(c.suiviPrises(prises,{etat}));
  assert.equal(r.regles,1); assert.equal(r.gains,10); assert.equal(r.en_cours,1); assert.equal(r.roi,1);
  eq(c.suiviPrises(prises,{unique:true}).map(p=>p.id),[1,2]);
});
