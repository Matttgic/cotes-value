"""Intervalle de confiance du ROI par grappes (match) : lot statistiques, 9/11/2026. Cas calculé à la main."""
import shutil

import pytest

from cotes.simulation import bilan
from scripts.site_web import MODELE
from tests.test_site_js import executer

NODE = shutil.which("node")


def _pari(pid, match, statut, gain, simulation="A"):
    return {"id": pid, "reference": "Pinnacle", "simulation": simulation, "statut": statut, "gain": gain, "mise": 10.0,
            "match_id": match, "domicile": "Lens", "exterieur": "Lille", "debut": "2026-11-01T20:00:00+00:00",
            "detecte": "2026-11-01T18:00:00+00:00", "bookmaker": "Winamax", "sport": "football", "cote": 2.0,
            "cote_juste": 1.9, "ecart": 0.05, "marche": "TOTAL", "periode": "MATCH", "ligne": 2.5,
            "issue": "PLUS" if pid != "b" else "MOINS"}


def test_sommes_par_match_dans_le_bilan():
    # match 1 : deux paris gagnés (+10, +10) ; matchs 2 et 3 : un pari perdu chacun (−10)
    paris = [_pari("a", "m1", "gagne", 10.0), _pari("b", "m1", "gagne", 10.0),
             _pari("c", "m2", "perdu", -10.0), _pari("d", "m3", "perdu", -10.0)]
    b = bilan(paris)["A|Pinnacle"]
    assert sorted((v[4], v[5]) for v in b["evenements_detail"].values()) == [(-10.0, 10.0), (-10.0, 10.0), (20.0, 20.0)]
    assert b["evenements_regles"] == 3 and b["roi"] == 0


@pytest.mark.skipif(not NODE, reason="node absent")
def test_ic_par_match_calcule_a_la_main():
    section = MODELE[MODELE.index('function unitesMatchs('):MODELE.index('const texteIc')]
    additionner = MODELE[MODELE.index('function additionner('):MODELE.index('function rendreBilan()')]
    executer('''
const assert=require('node:assert/strict');
const refBilan='Pinnacle';
''' + section + additionner + '''
// À la main : matchs (g, m) = (20, 20), (−10, 10), (−10, 10) ; ROI R = 0 ; Σ(g − R·m)² = 600 ; k = 3 ;
// variance = 600 × 3/2 / 40² = 0,5625 ; écart type 0,75 ; IC 95 % = ±1,96 × 0,75 = ±1,47.
const D={bilan:{'A|Pinnacle':{paris:3,regles:3,mises:30,gains:10,g2:300,gm:300,m2:300,
                 evenements_detail:{'1':[1,1,0,0,10,10],'2':[1,1,0,0,-10,10]}},
               'B|Pinnacle':{paris:1,regles:1,mises:10,gains:-10,g2:100,gm:-100,m2:100,
                 evenements_detail:{'1':[1,1,0,0,10,10],'3':[1,1,0,0,-10,10]}}}};
const t=additionner(['A','B'], D.bilan);
assert.deepEqual(t.evenements_detail['1'],[2,2,0,0,20,20]);    // le match 1 vu dans deux tranches : une grappe
const ic=icRoi(t);
assert.ok(Math.abs(ic[0]+1.47)<1e-9 && Math.abs(ic[1]-1.47)<1e-9, String(ic));
// Paris supposés indépendants (ancien calcul) : ±1,96 × √(400 × 4/3 / 1600) = ±1,13, trop étroit
const ancien=icRoi({regles:4,mises:40,gains:0,g2:400,gm:0,m2:400});
assert.ok(Math.abs(ancien[1]-1.96*Math.sqrt(1/3))<1e-9);
assert.equal(icRoi({evenements_detail:{'1':[1,1,0,0,10,10]}}), null);   // un seul match : pas d'intervalle
''')
