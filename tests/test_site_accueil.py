"""Lot site (9/11/2026) : accueil santé -> à jouer -> chiffres -> Top 5, santé dans l'en-tête, compteur = à jouer."""
import shutil
from pathlib import Path

import pytest

from scripts.site_web import MODELE
from tests.test_site_js import executer

WEB = Path(__file__).resolve().parents[1] / "web"
NODE = shutil.which("node")


def test_ordre_de_l_accueil():
    accueil = MODELE[MODELE.index('id="o-accueil"'):MODELE.index('id="o-bilan"')]
    positions = [accueil.index(x) for x in ('id="acc-sante"', 'id="acc-values"', 'id="acc-kpis"', 'id="acc-top5"')]
    assert positions == sorted(positions)
    assert "À jouer maintenant" in accueil


@pytest.mark.skipif(not NODE, reason="node absent")
def test_a_jouer_et_compteur_d_onglet():
    section = MODELE[MODELE.index('const aJouer'):MODELE.index('var CLES_MISE')]
    executer('''
const assert=require('node:assert/strict');
const el={textContent:'x'}; const document={getElementById:()=>el};
const futur=new Date(Date.now()+3600e3).toISOString(), passe=new Date(Date.now()-60e3).toISOString();
let fiches=[{id:'a',unique_bilan:true,statut:'en_cours',debut:futur},
  {id:'b',unique_bilan:true,statut:'en_cours',debut:passe},                         // match commencé
  {id:'c',unique_bilan:false,statut:'en_cours',debut:futur},                        // doublon d'une autre référence
  {id:'d',unique_bilan:true,statut:'en_cours',debut:futur,reference_suspecte:'écart > 30 %'},
  {id:'e',unique_bilan:true,statut:'gagne',debut:futur}];
''' + section + '''
assert.deepEqual(aJouer().map(p=>p.id),['a']); assert.equal(el.textContent,1);
fiches=[]; assert.equal(aJouer().length || "", "");                                 // 0 : compteur masqué
''')


@pytest.mark.skipif(not NODE, reason="node absent")
def test_en_tete_colore_par_la_sante():
    js = (WEB / "interface.js").read_text(encoding="utf-8")
    fonction = js[js.index("function actualiserFraicheur()"):js.index("function choisirVueStrategies")]
    executer('''
const assert=require('node:assert/strict');
const classes=new Set(); const info={textContent:'',title:'',classList:{toggle:(c,v)=>v?classes.add(c):classes.delete(c)}};
const document={getElementById:()=>info}; const minutes=()=>3;
const D={etat:{dernier_cycle:{fin:'x'}}};
const diagnosticSante=()=>({niveau:'panne',texte:'En panne : unibet · relevé il y a 3 min',pannes:['unibet']});
''' + fonction + '''
actualiserFraicheur();
assert.equal(info.textContent,'1 source en panne · relevé il y a 3 min'); assert.ok(classes.has('panne'));
''')
