import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';
import assert from 'node:assert/strict';
const source=readFileSync(new URL('../web/liens.js',import.meta.url),'utf8');
const e=s=>String(s??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');
const c=vm.createContext({URL,e});
vm.runInContext(source,c);
const p=(x={})=>({statut:'en_cours',bookmaker:'Winamax',lien:'https://www.winamax.fr/paris-sportifs/match/73265464',...x});

test('Un toucher : bouton vers la page du match, dans la ligne et en complet',()=>{
  const court=c.boutonBookmaker(p(),true), long=c.boutonBookmaker(p());
  assert.match(court,/href="https:\/\/www\.winamax\.fr\/paris-sportifs\/match\/73265464"/);
  assert.match(court,/target="_blank" rel="noopener noreferrer"/);
  assert.match(court,/Parier chez Winamax ›/);
  assert.match(court,/event\.stopPropagation\(\)/);           // ne replie pas la ligne du pari
  assert.match(long,/Ouvrir le match chez Winamax ›/);
});

test('Lien de repli annoncé comme tel',()=>{
  const b=c.boutonBookmaker(p({bookmaker:'Unibet',lien:'https://www.unibet.fr/paris-football',lien_repli:true}));
  assert.match(b,/class="btn lien-bookmaker repli"/);
  assert.match(b,/Page du sport chez Unibet › \(match à chercher\)/);
});

test('Rien pour un pari terminé, un lien hors bookmaker ou non https',()=>{
  assert.equal(c.boutonBookmaker(p({statut:'gagne'})),'');
  assert.equal(c.boutonBookmaker(p({lien:'https://www.google.com/search?q=x'})),'');
  assert.equal(c.boutonBookmaker(p({lien:'http://www.winamax.fr/x'})),'');
  assert.equal(c.boutonBookmaker(p({lien:'https://winamax.fr.exemple.com/x'})),'');
  assert.equal(c.boutonBookmaker(p({lien:'javascript:alert(1)'})),'');
  assert.equal(c.boutonBookmaker(p({lien:null})),'');
  for(const u of ['https://www.betclic.fr/x-m1','https://www.pmu.fr/sport/event/1','https://www.unibet.fr/a',
    'https://www.olybet.fr/sportsbook/pre-match/match/Soccer/France/548/1','https://www.netbet.fr/evenement/1'])
    assert.notEqual(c.boutonBookmaker(p({lien:u})),'');
});

test('Nom du bookmaker échappé',()=>{
  assert.match(c.boutonBookmaker(p({bookmaker:'<b>'})),/Parier chez &lt;b> ›|Ouvrir le match chez &lt;b> ›/);
});

test('Mes stratégies : la carte d’un pari en cours porte le bouton',()=>{
  const suivi=readFileSync(new URL('../web/suivi.js',import.meta.url),'utf8');
  const s=vm.createContext({URL,Intl,Date,JSON,Object,Number,Set,lire:()=>null,ecrire:()=>{},e,D:{},cote:String,eur2:String});
  vm.runInContext(source+suivi,s);
  const carte=vm.runInContext('carteSuivi',s);
  const pari={statut:'en_cours',bookmaker:'Betclic',lien:'https://www.betclic.fr/x-m1',sport:'football',domicile:'A',
    exterieur:'B',pari:'A',detecte:'2026-10-25T10:00:00Z',suivies:['eden'],cote:2};
  assert.equal((carte(pari).match(/lien-bookmaker/g)||[]).length,2);
  assert.equal((carte({...pari,statut:'gagne',gain:10}).match(/lien-bookmaker/g)||[]).length,0);
});
