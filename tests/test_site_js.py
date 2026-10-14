"""Contrats JS du vrai modèle : recherche composée, CSV complet et courbes SVG."""
import json
import shutil
import subprocess

import pytest

from scripts.site_web import MODELE

NODE=shutil.which("node")
pytestmark=pytest.mark.skipif(not NODE,reason="Node absent")


def executer(js):
    r=subprocess.run([NODE,"-"],input=js,text=True,capture_output=True)
    assert r.returncode == 0, r.stderr


DOM = '''
const assert=require("node:assert/strict");
const elements=new Map();
const document={getElementById(id){
  if(!elements.has(id)) elements.set(id,{value:"",innerHTML:"",textContent:"",style:{},querySelectorAll(){return []},setAttribute(){}});
  return elements.get(id);
},querySelectorAll(){return []}};
const e=s => String(s ?? "").replaceAll("<","&lt;").replaceAll('"','&quot;');
const cote=e,pct=e,eur=e,quand=e,signe=()=>"",ouvrir=()=>{};
const STATUTS={}, STRAT_PERIODES={futur:"Depuis le lancement",ensemble:"Historique"};
'''


def test_js_recherche_filtres_export_bom_echappement_et_archive_complete():
    rows=[{"id":str(i),"simulation":"D","reference":"Pinnacle","statut":"gagne",
           "sport":"football","bookmaker":"Winamax","domicile":"Équipe Saint-Étienne",
           "exterieur":"Lyon","ligue":"Ligue 1","pari":"Victoire; \'a\' \"domicile\"\nligne",
           "cote":2.1,"gain":-10,"ecart":.05,"clv":None,"detecte":"2026-10-15T09:00:00Z",
           "strategies":["chatgpt"],"convergence":True,"tranche":"2,01 – 3,00"} for i in range(75)]
    champs=list(rows[0]); data={"paris":[],"catalogue":{"champs":champs,"lignes":[list(p.values()) for p in rows]},
                              "strategies_badges":{"chatgpt":"ChatGPT v1"},"tranches":[],"valeurs_filtres":{},"simulations":{}}
    section=MODELE[MODELE.index("const recentes ="):MODELE.index("// --- Segments")]
    js=DOM+"const D="+json.dumps(data)+";\nconst badgeStrategies=()=>'';\n"+section+'''
assert.equal(parisFiltres.length,75);
assert.equal((document.getElementById("paris").innerHTML.match(/<article/g)||[]).length,50);
document.getElementById("f-q").value="EQUIPE SAINT-ETIENNE";
document.getElementById("f-q").oninput();
assert.equal(parisFiltres.length,75);
document.getElementById("f-book").value="Betclic"; rendreParis(); assert.equal(parisFiltres.length,0);
document.getElementById("f-book").value="Winamax";
document.getElementById("f-sim").value="Convergence ≥ 2"; rendreParis(); assert.equal(parisFiltres.length,75);
const csv=csvParis(parisFiltres);
assert.equal(csv.charCodeAt(0),0xfeff);
assert.equal(csv.split('"2026-10-15T09:00:00Z"').length-1,75);
assert.ok(csv.includes(`"Victoire; 'a' ""domicile""\nligne"`));
assert.ok(csv.includes('"-10"')); assert.ok(csv.includes('ChatGPT v1 | Convergence ≥ 2'));
assert.equal(celluleCSV('=HYPERLINK("x")'),`"'=HYPERLINK(""x"")"`);
assert.equal(celluleCSV('\t+cmd'),`"'\t+cmd"`);
assert.equal(normaliserRecherche("CONFÉRENCE"),"conference");
'''
    executer(js)


def test_js_courbes_legend_masquage_et_periode_vide():
    outils = MODELE[MODELE.index("const eurC ="):MODELE.index("\n", MODELE.index("const eurC ="))] + "\n"
    outils += MODELE[MODELE.index("function pas("):MODELE.index("function rendreCourbe()")]
    section=MODELE[MODELE.index("const courbesMasquees ="):MODELE.index('let periodeStrategies = "futur";')]
    executer(DOM+outils+'''
const D={laboratoire:{navigation:{courbes:{"Claude (rejeu)":{ensemble:[[1,10],[2,-5]]}}}}};
let periodeStrategies="ensemble";
'''+section+'''
const rows=[{id:"Claude (rejeu)",nom:"Claude"}];
rendreCourbesStrategies(rows);
assert.ok(document.getElementById("strategies-courbes").innerHTML.includes('data-serie="Claude (rejeu)"'));
assert.ok(!document.getElementById("strategies-courbes").innerHTML.includes("NaN"));
assert.ok(document.getElementById("strategies-legende").innerHTML.includes("Claude -5 €"));
assert.ok(document.getElementById("strategies-courbes").innerHTML.includes("01/01 01h"));
document.getElementById("strategies-tout").onclick();
assert.equal(document.getElementById("strategies-courbes").style.display,"none");
assert.ok(document.getElementById("strategies-courbes-vide").textContent.includes("masquées"));
assert.ok(document.getElementById("strategies-legende").innerHTML.includes("Tout afficher"));
document.getElementById("strategies-tout").onclick();
assert.ok(document.getElementById("strategies-courbes").innerHTML.includes('data-serie="Claude (rejeu)"'));
D.laboratoire.navigation.courbes["Claude (rejeu)"].ensemble=[[1,-96.46],[4*86400,340.86]];
rendreCourbesStrategies(rows);
const axes=document.getElementById("strategies-courbes").innerHTML.match(/<text[^>]*>[^<]*<\\/text>/g).join(" ").replace(/<[^>]+>/g,"");
assert.ok(axes.includes("+400 €") && axes.includes("-200 €") && axes.includes("0 €"));
assert.ok(!axes.includes("h") && !axes.includes(","));
periodeStrategies="futur"; rendreCourbesStrategies(rows);
assert.ok(document.getElementById("strategies-courbes-vide").textContent.includes("Aucun pari réglé"));
''')
