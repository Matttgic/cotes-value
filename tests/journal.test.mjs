// Journal réel (web/journal.js) : réponse notée depuis l'ancre, bilan réel, limitation.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

function charger() {
  const stock = {};
  const ctx = {localStorage: {getItem: k => stock[k] ?? null, setItem: (k, v) => { stock[k] = String(v); }},
    URLSearchParams, location: {hash: ''}, console};
  vm.createContext(ctx);
  vm.runInContext(readFileSync(new URL('../web/journal.js', import.meta.url), 'utf8'), ctx);
  return ctx;
}

test('une réponse valide est notée, une ancre quelconque ignorée', () => {
  const c = charger();
  assert.equal(c.journalNoterDepuisAncre('#notifications?journal=abc123&r=joue&cote=2.15'), 'Noté : Joué.');
  assert.deepEqual({...c.journalLire().abc123, le: 0}, {r: 'joue', cote: 2.15, le: 0});
  assert.equal(c.journalNoterDepuisAncre('#notifications?journal=abc123&r=pirate'), '');
  assert.equal(c.journalNoterDepuisAncre('#bilan'), '');
});

test('bilan réel à la cote obtenue et bookmaker qui limite', () => {
  const c = charger();
  const fiches = [{id: 'a', statut: 'gagne', gain: 12, cote: 2.2, bookmaker: 'PMU'},
    {id: 'b', statut: 'perdu', gain: -10, cote: 2.0, bookmaker: 'PMU'},
    ...['c', 'd', 'e'].map(id => ({id, statut: 'en_cours', gain: null, cote: 1.9, bookmaker: 'Betclic'}))];
  const j = {a: {r: 'joue', cote: 2.1}, b: {r: 'joue', cote: null}, c: {r: 'plafonne'}, d: {r: 'plafonne'}, e: {r: 'plafonne'}};
  const B = c.journalBilan(j, fiches);
  assert.equal(B.regles, 2);
  assert.equal(B.gain, 1);                       // +11 (2,10) − 10
  assert.deepEqual([...B.limites], ['Betclic']);
  assert.equal(B.comptes.plafonne, 3);
});
