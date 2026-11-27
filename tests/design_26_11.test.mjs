// Audit design du 26/11 : copie du lien bookmaker dans le summary d'une ligne (pas de contrôle imbriqué),
// carte de chaleur du bilan en rangées ARIA, champs de dates nommés.
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';
import assert from 'node:assert/strict';

const lire = f => readFileSync(new URL('../web/' + f, import.meta.url), 'utf8');
const e = s => String(s ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('"', '&quot;');
const p = (x = {}) => ({statut: 'en_cours', bookmaker: 'Betclic', lien: 'https://www.betclic.fr/foot/match-m1', ...x});

function liens(ouverts = []) {
  const c = vm.createContext({URL, e, window: {open: (...a) => ouverts.push(a)}});
  vm.runInContext(lire('liens.js'), c);
  return c;
}

test('Summary : la copie du lien est un span non focalisable, sans href ni rôle de lien', () => {
  const c = liens(), h = c.boutonBookmaker(p(), true, true);
  assert.match(h, /^<span class="btn lien-bookmaker court" data-lien="https:\/\/www\.betclic\.fr\/foot\/match-m1" aria-hidden="true">Parier chez Betclic ›<\/span>$/);
  assert.doesNotMatch(h, /href=|tabindex|<a /);
  // Le bouton complet et la version courte hors summary restent de vrais liens.
  assert.match(c.boutonBookmaker(p(), true), /^<a class="btn lien-bookmaker court" href=/);
  assert.equal(c.boutonBookmaker(p({statut: 'gagne'}), true, true), '');
});

test('Toucher la copie : ouvre le match une fois, sans replier la ligne ; hôte revérifié', () => {
  const ouverts = [], c = liens(ouverts);
  const evenement = lien => {
    const ev = {stop: 0, prevent: 0, preventDefault() { this.prevent++; }, stopPropagation() { this.stop++; },
      target: {closest: sel => sel === '[data-lien]' && lien != null ? {dataset: {lien}} : null}};
    return [c.ouvrirLienResume(ev), ev];
  };
  const [pris, ev] = evenement('https://www.betclic.fr/foot/match-m1');
  assert.equal(pris, true);
  assert.equal(ev.prevent, 1);
  assert.equal(ev.stop, 1);
  assert.deepEqual(ouverts, [['https://www.betclic.fr/foot/match-m1', '_blank', 'noopener,noreferrer']]);
  evenement('https://exemple.com/piege');                          // hôte hors liste : rien n'est ouvert
  assert.equal(ouverts.length, 1);
  assert.equal(evenement(null)[0], false);                           // clic ailleurs : ignoré
});

test('Lignes de paris : la copie du summary passe par horsClavier (modèle et suivi)', () => {
  assert.match(lire('modele.html'), /\$\{boutonBookmaker\(p, true, true\)\}<\/span><\/summary>/);
  assert.match(lire('suivi.js'), /boutonBookmaker\(p, court, court\)/);
});

test('Carte de chaleur : en-têtes et cases rangés dans des role="row"', () => {
  const src = lire('bourse.js');
  assert.match(src, /role="table"[^`]*<div class="cv-rangee" role="row"><span class="cv-chaleur-coin" role="columnheader">/);
  assert.match(src, /<div class="cv-rangee" role="row"><span class="cv-chaleur-sport" role="rowheader">/);
});

test('Dates des bilans nommées pour les lecteurs d\'écran', () => {
  const src = lire('suivi.js');
  assert.match(src, /aria-label="Du : date de début" data-p="depuis"/);
  assert.match(src, /aria-label="Au : date de fin" data-p="jusqua"/);
});

test('Chargement différé annoncé : aria-busy sur le contenu, levé à la fin', () => {
  const src = lire('modele.html');
  assert.match(src, /getElementById\("contenu"\)\?\.setAttribute\("aria-busy", String\(attente\)\)/);
  assert.match(src, /classList\.remove\("chargement-differe"\);\n  document\.getElementById\("contenu"\)\?\.setAttribute\("aria-busy", "false"\)/);
});
