import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';
import assert from 'node:assert/strict';
const source=readFileSync(new URL('../web/horaires.js',import.meta.url),'utf8');
const c=vm.createContext({Intl,Date,e:s=>String(s??'').replaceAll('<','&lt;'),iconeSport:()=>'',nomsSports:{football:'Football'}});
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

test('Collecte visible : Paris, prix baissé et début de lot historique distingués',()=>{
  c.cote=x=>Number(x).toFixed(2).replace('.',',');
  const now=at('2026-10-17T00:05:00Z');
  const p={cote:1.76,detecte:'2026-10-16T23:56:25Z',collecte_recue:'2026-10-16T23:56:30Z',
    prix_revu:1.56,prix_revu_le:'2026-10-17T00:04:00Z',alerte_demande_le:'2026-10-16T23:57:00Z',statut:'en_cours'};
  const html=c.collectePari(p,now);
  assert.ok(html.includes('01:56:30'));
  assert.ok(html.includes('il y a 8 min'));
  assert.ok(html.includes('1,56 (-0,20)'));
  assert.ok(html.includes('Envoi demandé 01:57:00 · délai 30 s'));
  assert.ok(html.includes('collecte-ancienne'));
  assert.ok(c.collectePari({detecte:p.detecte},now).includes('réception exacte inconnue'));
  assert.ok(c.collectePari({}).includes('Collecte non renseignée'));
});
