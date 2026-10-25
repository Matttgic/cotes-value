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

test('Un pari pris par trois stratégies compte trois mises dans « Toutes », une dans la vue d’une stratégie',()=>{
  const p={statut:'perdu',cote:2,suivies:['a','b','c']};
  const tout=c.suiviBilan([p],q=>q.suivies.length);
  assert.equal(tout.gains,-30); assert.equal(tout.mises,30); assert.equal(tout.regles,3); assert.equal(tout.roi,-1);
  assert.equal(c.suiviBilan([p]).gains,-10);
  const g=c.suiviBilan([{statut:'gagne',cote:1.5,suivies:['a','b']},{statut:'en_cours',suivies:['a','b','c']}],q=>q.suivies.length);
  assert.equal(g.gains,10); assert.equal(g.en_cours,3); assert.equal(g.regles,2);
});

// Mise Kelly : « Mes stratégies » recalcule ses gains avec la mise Kelly de chaque pari
test('prisesSuivi suit la mise des bilans (fixe ou Kelly)', async () => {
  const fs = await import('node:fs');
  const src = fs.readFileSync(new URL('../web/suivi.js', import.meta.url), 'utf8');
  const D = {catalogue: {champs: ['id', 'mise', 'mise_kelly', 'gain'], lignes: [['a', 10, 4, 12], ['b', 10, 6, -10], ['c', 10, 5, null]]}};
  const corps = src.slice(src.indexOf('function suiviObjets'), src.indexOf('// Prises détectées'))
    + src.slice(src.indexOf('let prisesCache'), src.indexOf('function datesHtml'));
  const fabrique = new Function('D', 'miseMode', corps + '; return prisesSuivi;');
  const fixe = fabrique(D, 'fixe')();
  assert.deepEqual(fixe.map(p => [p.mise, p.gain]), [[10, 12], [10, -10], [10, null]]);
  const kelly = fabrique(D, 'kelly')();
  assert.deepEqual(kelly.map(p => [p.mise, p.gain]), [[4, 4.8], [6, -6], [5, null]]);
});

test('les stratégies Pushover entrent dans « Mes stratégies » sans effacer celles de Chrome', () => {
  for (const k of Object.keys(mem)) delete mem[k];
  const cle = 'cv-suivi-strategies-v1';
  c.suiviPushover(['qwen_persistence', 'coeur_value']);
  let etat = JSON.parse(mem[cle]);
  assert.deepEqual(Object.keys(etat).sort(), ['coeur_value', 'qwen_persistence']);
  assert.equal(etat.qwen_persistence[0][0], Date.parse('2026-10-25T12:44:00Z'));      // suivi depuis le choix sur le site
  mem['cv-notifications-v1'] = JSON.stringify({enabled: true, strategies: ['claude_prudent']});
  c.suiviEnregistrer(['claude_prudent']);                                              // coche Chrome : Pushover reste actif
  etat = JSON.parse(mem[cle]);
  assert.deepEqual(Object.keys(etat).sort(), ['claude_prudent', 'coeur_value', 'qwen_persistence']);
  assert.ok(Object.values(etat).every(l => l[l.length - 1][1] == null));
  c.suiviPushover(['coeur_value']);                                                    // décoche Pushover de Qwen : arrêtée
  etat = JSON.parse(mem[cle]);
  assert.notEqual(etat.qwen_persistence[0][1], null);
  assert.equal(etat.claude_prudent[0][1], null);
});
