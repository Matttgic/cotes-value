import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';
import assert from 'node:assert/strict';
const source=readFileSync(new URL('../web/voyant.js',import.meta.url),'utf8').split('async function afficherVoyant')[0];
const c=vm.createContext({Date,Number,Array,Intl});
vm.runInContext(source,c);
const etat=(cycles,choix,maintenant)=>vm.runInContext('etatVoyant',c)(cycles,choix,maintenant);
const T=Date.parse('2026-10-25T22:20:00Z');
const cyc=(min,p)=>({prepare_le:new Date(T-min*60000).toISOString(),pushover:{actif:true,strategies:4,source:'site',envoyees:0,echecs:0,erreurs:[],...p}});

test('Vert : stratégies cochées suivies, cycle récent',()=>{
  const v=etat([cyc(8,{envoyees:1}),cyc(3,{})],{strategies:['a','b','c','d']},T);
  assert.equal(v.niveau,'ok');
  assert.match(v.texte,/4 stratégies cochées notifiées/); assert.match(v.texte,/1 alerte envoyée sur les 2 derniers cycles/);
});
test('Orange : le serveur ne suit pas encore autant de stratégies que cochées',()=>{
  const v=etat([cyc(3,{strategies:3})],{strategies:['a','b','c','d']},T);
  assert.equal(v.niveau,'attention'); assert.match(v.texte,/coché 4.*en suit 3/);
});
test('Orange : stratégies venues de la variable du dépôt, pas des cases du site',()=>{
  const v=etat([cyc(3,{source:'variable'})],{strategies:['a','b','c','d']},T);
  assert.equal(v.niveau,'attention'); assert.match(v.texte,/variable du dépôt/);
});
test('Orange : collecte en retard',()=>{
  const v=etat([cyc(45,{})],null,T);
  assert.equal(v.niveau,'attention'); assert.match(v.texte,/il y a 45 min/);
});
test('Rouge : Pushover inactif, échec d’envoi',()=>{
  assert.equal(etat([cyc(3,{actif:false,strategies:0})],null,T).niveau,'erreur');
  const v=etat([cyc(3,{echecs:2,erreurs:['HTTP 429']})],null,T);
  assert.equal(v.niveau,'erreur'); assert.match(v.texte,/2 échecs? d’envoi/); assert.match(v.texte,/HTTP 429/);
});
test('Sans relevé ou sans lecture du choix : pas de faux vert ni de plantage',()=>{
  assert.equal(etat([],null,T).niveau,'attention'); assert.equal(etat(undefined,null,T).niveau,'attention');
  assert.equal(etat([{prepare_le:'x'}],null,T).niveau,'attention');
  assert.equal(etat([cyc(3,{})],null,T).niveau,'ok');       // choix non relu : on se fie au serveur
});
test('Envois comptés qu’ils soient un nombre ou une liste',()=>{
  const v=etat([cyc(8,{envoyees:['a','b']}),cyc(3,{envoyees:1})],null,T);
  assert.match(v.texte,/3 alertes envoyées/);
});
