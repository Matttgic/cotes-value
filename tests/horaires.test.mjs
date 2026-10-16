import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';
import assert from 'node:assert/strict';
const source=readFileSync(new URL('../web/horaires.js',import.meta.url),'utf8');
const c=vm.createContext({Intl,Date,e:s=>String(s??'').replaceAll('<','&lt;'),iconeSport:()=>'',nomsSports:{football:'Football'},carteActuelle:o=>`<details>${o.pari}</details>`});
vm.runInContext(source,c);
const at=s=>Date.parse(s);

test('Paris, passage de minuit, demain et fenêtre exacte de 2 h',()=>{
  const now=at('2026-10-16T22:30:00Z'); // 17 octobre, 00 h 30 à Paris
  const p={debut:'2026-10-16T23:59:00Z'};
  assert.equal(c.infoHoraire(p,now).texte,'Auj. 01:59 (dans 1h29)');
  assert.equal(c.accepteHoraire(p,'aujourdhui',now),true);
  assert.equal(c.accepteHoraire(p,'demain',now),false);
  assert.equal(c.infoHoraire({debut:'2026-10-18T14:00:00Z'},now).texte,'Demain 16:00');
  assert.equal(c.accepteHoraire({debut:'2026-10-17T00:30:00Z'},'imminent',now),true);
  assert.equal(c.accepteHoraire({debut:'2026-10-17T00:30:01Z'},'imminent',now),false);
  assert.equal(c.accepteHoraire({debut:new Date(now).toISOString()},'imminent',now),false);
});

test('Heure d’hiver et d’été : demain est un jour civil, pas 24 h de durée',()=>{
  assert.equal(c.infoHoraire({debut:'2026-10-25T19:00:00Z'},at('2026-10-24T22:30:00Z')).texte,'Auj. 20:00');
  assert.equal(c.infoHoraire({debut:'2026-03-29T18:00:00Z'},at('2026-03-28T11:00:00Z')).texte,'Demain 20:00');
  assert.equal(c.infoHoraire({debut:'2026-10-25T19:00:00Z'},at('2026-10-24T11:00:00Z')).texte,'Demain 20:00');
});

test('Reports, dates invalides et tri non destructif',()=>{
  const now=at('2026-10-17T00:00:00Z');
  const p={debut:'2026-10-15T18:00:00Z',reporte_au:'2026-10-18T14:00:00Z',statut:'en_cours'};
  assert.equal(c.infoHoraire(p,now).texte,'Reporté · Demain 16:00');
  assert.equal(c.accepteHoraire(p,'demain',now),true);
  assert.equal(c.infoHoraire({debut:'bad'},now).date,null);
  assert.equal(c.accepteHoraire({},'imminent',now),false);
  const rows=[{id:'inconnu'},p,{debut:'2026-10-17T18:00:00Z'}];
  const sorted=c.trierHoraires(rows,'heure');
  assert.equal(sorted[2].id,'inconnu');assert.equal(rows[0].id,'inconnu');
  const html=c.horairePari(p,now);assert.ok(html.includes('datetime="2026-10-18T14:00:00.000Z"'));
  assert.ok(html.includes('Reporté · Demain 16:00'));
});

test('Regroupement visuel, meilleur edge et catégories préservées',()=>{
  const p={sport:'football',domicile:'Équipe A U21',exterieur:'B',debut:'2026-10-17T18:00:00Z',ecart:.04,pari:'Under 2,5'};
  const rows=[p,{...p,bookmaker:'PMU',pari:'Handicap +1,5',ecart:.06},{...p,domicile:'Équipe A',pari:'Seniors'},
    {...p,debut:'2026-10-18T18:00:00Z',pari:'Demain'}];
  assert.equal(c.groupesMatchs(rows).length,3);
  const html=c.rendreGroupesJouer(rows);
  assert.equal((html.match(/class="groupe-match"/g)||[]).length,3);
  assert.ok(html.indexOf('Handicap +1,5')<html.indexOf('Under 2,5'));
  assert.equal((html.match(/<details>/g)||[]).length,4);
  assert.equal(rows[0],p);
});
