import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
const source=readFileSync(new URL('../web/decision.js',import.meta.url),'utf8');
const e=s=>String(s??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');
function contexte(extra={}) {
  const c=vm.createContext({Date,console,e,quand:s=>s || '—',signe:x=>x==null?'':x>0?'pos':x<0?'neg':'',...extra});
  vm.runInContext(source,c);return c;
}
const MAINTENANT=Date.parse('2026-11-20T10:00:00Z');
const ligne=(id,decision,plus={})=>({id,famille:id.split(':')[0],nom:id.split(':')[1] || 'Paris uniques',cle:id.split(':')[1],paris:210,regles:200,matchs:180,
  roi:2.1,roi_ic:[-2.5,6.7],clv:1.19,clv_ic:[0.55,1.82],clv_n:150,couverture:75,decision,raison:'raison de '+id,...plus});
const pari=(id,plus={})=>({id,unique_bilan:true,statut:'en_cours',debut:'2026-11-20T18:00:00Z',bookmaker:'PMU',reference:'Pinnacle',
  domicile:'A',exterieur:'B',pari:'Victoire A',strategies:[],regles:[],...plus});
const protocole=(lignes={})=>({regles:{debut:'2026-11-16T00:00:00+01:00',alpha:0.00025,couverture_min:0.5,scelle:'94faa228f06d'},
  resume:{en_cours:Object.values(lignes).filter(l=>l.statut==='en_cours').length,succes:Object.values(lignes).filter(l=>l.statut==='succes').length},lignes});
const DEC={calcule_le:'2026-11-20T09:00:00+00:00',regles:{part_pinnacle_min:0.5,tests_roi:8,tests_clv:8},lignes:[
  ligne('ensemble','jouer'),ligne('bookmaker:PMU','jouer'),ligne('bookmaker:Betclic','attendre'),
  ligne('bookmaker:OlyBet','couper',{roi:-15.1,roi_ic:[-31.8,-1.7],clv:-3.02,clv_ic:[-6.75,-0.72]}),
  ligne('reference:Pinnacle','jouer'),ligne('reference:Kalshi','surveiller',{roi:-28.4,roi_ic:[-43.6,-11.9],clv:null,clv_ic:null,clv_n:0})]};

test('prouvé : seulement si le protocole a validé une stratégie ; prochaine lecture sans chiffre intermédiaire',()=>{
  const c=contexte();
  const P=protocole({a:{cle:'a',nom:'A',statut:'en_cours',n:400,mi:200,mesures:150},b:{cle:'b',nom:'B',statut:'en_cours',n:300,mi:150,mesures:0},
    h:{cle:'h',nom:'H',statut:'hors_protocole'}});
  const a=c.decisionAvantage(P,MAINTENANT);
  assert.equal(a.prouve,false);assert.equal(a.inscrites,2);assert.equal(a.commence,true);
  assert.equal(a.prochaine.nom,'A');assert.equal(a.prochaine.manque,50);assert.equal(a.prochaine.lecture,'mi-parcours');
  assert.equal(c.decisionAvantage(P,Date.parse('2026-11-15T10:00:00Z')).commence,false);
  P.lignes.a={...P.lignes.a,statut:'succes',finale:{clv:2.4,p:0.0001,n:400}};
  assert.equal(c.decisionAvantage(P,MAINTENANT).prouve,true);
});
test('à jouer : pari ouvert dont le bookmaker et la référence sont jouables, jamais une ligne coupée',()=>{
  const c=contexte();
  const fiches=[pari('ok'),pari('betclic',{bookmaker:'Betclic'}),pari('olybet',{bookmaker:'OlyBet'}),pari('kalshi',{reference:'Kalshi'}),
    pari('commence',{debut:'2026-11-20T09:00:00Z'}),pari('regle',{statut:'gagne'}),pari('double',{unique_bilan:false}),pari('tot',{debut:'2026-11-20T12:00:00Z'})];
  const j=c.decisionParis(fiches,DEC,protocole(),MAINTENANT);
  assert.equal(j.ouverts,5);
  assert.deepEqual(Array.from(j.jouer,x=>x.p.id),['tot','ok']);                       // par heure de match
  assert.deepEqual(Array.from(j.jouer[0].preuves,l=>l.id),['bookmaker:PMU','reference:Pinnacle']);
  assert.deepEqual(Array.from(j.coupes,x=>[x.p.id,x.ligne.id]),[['olybet','bookmaker:OlyBet']]);
  assert.deepEqual(Array.from(j.attente,x=>[x.p.id,x.ligne.id]),[['betclic','bookmaker:Betclic'],['kalshi','reference:Kalshi']]);
});
test('une stratégie validée rend ses paris jouables en premier, sauf chez un bookmaker coupé',()=>{
  const c=contexte();
  const P=protocole({e:{cle:'eden',nom:'Eden',statut:'succes',n:460,mesures:460,finale:{clv:2.4,p:0.0001,n:460}},
    r:{cle:'labo:PIN-1',nom:'Pinnacle 1',statut:'succes',n:300,mesures:300,finale:{clv:2,p:0.0001,n:300}}});
  const fiches=[pari('probable'),pari('eden',{bookmaker:'Betclic',strategies:['eden'],debut:'2026-11-21T18:00:00Z'}),
    pari('labo',{bookmaker:'Betclic',regles:['PIN-1'],debut:'2026-11-22T18:00:00Z'}),pari('coupe',{bookmaker:'OlyBet',strategies:['eden']})];
  const j=c.decisionParis(fiches,DEC,P,MAINTENANT);
  assert.deepEqual(Array.from(j.jouer,x=>[x.p.id,x.niveau]),[['eden','prouve'],['labo','prouve'],['probable','probable']]);
  assert.deepEqual(Array.from(j.coupes,x=>x.p.id),['coupe']);
});
test('à couper : lignes perdantes, pauses, échecs du protocole ; sinon la ligne la plus proche',()=>{
  const c=contexte();
  const P=protocole({a:{cle:'a',nom:'A',statut:'echec',motif:'CLV Pinnacle non prouvée au seuil du protocole',n:300,mesures:300,finale:{clv:0.4,p:0.2,n:300}},
    b:{cle:'b',nom:'B',statut:'echec',motif:'stratégie mise en pause',n:300,mesures:10},
    r:{cle:'r',nom:'R',statut:'rompu',motif:'règles modifiées pendant le protocole',n:300,mesures:10},
    s:{cle:'s',nom:'S',statut:'en_cours',n:680,mesures:20,regles:80,couverture:25}});
  const D={decision:DEC,protocole:P,pauses:{liste:{'Ligne B':{cle:'b',depuis:'2026-11-18T10:00:00+00:00',regles:240,clv:-2.1,clv_haute:-0.4,clv_match:-1.8}}},doublons:[]};
  const k=c.decisionCoupes(D);
  assert.deepEqual(Array.from(k.couper,l=>l.id),['bookmaker:OlyBet']);
  assert.deepEqual(Array.from(k.pauses,p=>p.id),['Ligne B']);
  assert.deepEqual(Array.from(k.echecs,l=>l.cle),['a']);                              // B est déjà listée comme pause
  assert.deepEqual(Array.from(k.rompues,l=>l.cle),['r']);
  assert.deepEqual(Array.from(k.surveiller,l=>l.id),['reference:Kalshi']);
  assert.deepEqual(Array.from(k.sansCloture,l=>l.cle),['s']);
  // Rien à couper : la ligne au ROI négatif dont l'intervalle monte le moins haut est citée, sans être coupée.
  const calme={decision:{lignes:[ligne('bookmaker:PMU','jouer'),ligne('bookmaker:NetBet','attendre',{roi:-6.9,roi_ic:[-35.7,21.9]}),
    ligne('bookmaker:OlyBet','attendre',{roi:-15.1,roi_ic:[-31.8,1.7]})]}};
  const r=c.decisionCoupes(calme);
  assert.equal(r.couper.length,0);assert.equal(r.plusProche.id,'bookmaker:OlyBet');
});
test('chaque réponse renvoie à un chiffre présent dans « Les chiffres »',()=>{
  const c=contexte();
  const P=protocole({a:{cle:'a',nom:'A',statut:'echec',motif:'CLV Pinnacle non prouvée au seuil du protocole',n:300,mesures:300,finale:{clv:0.4,p:0.2,n:300}},
    e:{cle:'eden',nom:'Eden',statut:'succes',n:460,mesures:460,finale:{clv:2.4,p:0.0001,n:460}},
    s:{cle:'s',nom:'S',statut:'en_cours',n:680,mesures:20,regles:80,couverture:25}});
  const D={decision:DEC,protocole:P,pauses:{liste:{}},doublons:[{a:'X',b:'Y',part:100,communs:293}]};
  const fiches=[pari('ok'),pari('eden',{strategies:['eden']}),pari('betclic',{bookmaker:'Betclic'}),pari('olybet',{bookmaker:'OlyBet'})];
  const html=c.htmlDecision(D,fiches,MAINTENANT);
  const preuves=[...html.matchAll(/data-chiffre="([^"]+)"/g)].map(m=>m[1]);
  assert.ok(preuves.length >= 10);
  for (const id of preuves) assert.ok(html.includes(`id="${c.decAncre(id)}"`),id);
  // Les trois réponses, avec leur chiffre écrit en toutes lettres.
  assert.match(html,/Oui, pour 1 stratégie\./);
  assert.match(html,/CLV Pinnacle \+2,40 % · p = 0,01 % · 460 paris mesurés/);
  assert.match(html,/<strong>2 paris\.<\/strong>/);
  assert.match(html,/CLV Pinnacle \+1,19 % \[\+0,55 ; \+1,82\] · 150 mesurés/);
  assert.match(html,/Ne plus prendre de paris chez <b>OlyBet<\/b>/);
  assert.match(html,/ROI -15,1 % \[-31,8 ; -1,7\] · 200 réglés/);
  assert.match(html,/Clôture connue pour 25 % des 80 réglés/);
  assert.match(html,/partagent 100 % de leurs paris/);
  // Sans validation : « Non », et aucun pari présenté comme prouvé.
  const sans=c.htmlDecision({decision:DEC,protocole:protocole({b:{cle:'b',nom:'B',statut:'en_cours',n:300,mi:150,mesures:0}})},fiches,MAINTENANT);
  assert.match(sans,/<strong class="">Non\.<\/strong>/);assert.doesNotMatch(sans,/Avantage prouvé<\/span>/);
  assert.match(c.htmlDecision({},[],MAINTENANT),/indisponibles/);
  assert.match(html,/A-t-elle marché \?<\/b> Jamais appliquée/);
});
test('quoi jouer : bilan de la règle rejouée, chiffres présents dans « Les chiffres »',()=>{
  const c=contexte();
  const b=(plus)=>({regles:1095,matchs:667,gain:145.4,roi:1.33,roi_ic:[-6.59,9.25],clv:1.35,clv_ic:[0.56,2.14],clv_n:931,couverture:85,...plus});
  const rejeu={debut:'2026-10-18',jours:27,retenus:b(),ecartes:b({regles:1851,roi:0.68,roi_ic:[-6.76,8.12],clv:-0.31,clv_ic:[-1.53,0.91],clv_n:879})};
  const html=c.htmlDecision({decision:{...DEC,rejeu},protocole:protocole()},[pari('ok')],MAINTENANT);
  assert.match(html,/A-t-elle marché \? Pas encore tranché\./);
  assert.match(html,/depuis le 18\/10\/2026.*1\s095 paris retenus, 27 jours/s);
  assert.match(html,/Ses paris battent bien la clôture Pinnacle/);
  assert.match(html,/ROI \+1,3 % \[-6,6 ; \+9,3\] · 1\s095 réglés/);
  assert.match(html,/les 1\s851 autres paris uniques des mêmes jours/);
  for (const id of ['rejeu:retenus','rejeu:ecartes']) assert.ok(html.includes(`id="${c.decAncre(id)}"`),id);
  assert.match(html,/dec-etat attendre">Non tranché/);
  const gagnante=c.htmlDecision({decision:{...DEC,rejeu:{...rejeu,retenus:b({roi_ic:[0.5,9]})}},protocole:protocole()},[],MAINTENANT);
  assert.match(gagnante,/Oui, elle a gagné\./);assert.match(gagnante,/dec-etat jouer">Gagnante/);
});
