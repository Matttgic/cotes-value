"""Contrats JS du vrai modèle : recherche composée, CSV complet et courbes SVG."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.site_web import MODELE

NODE=shutil.which("node")
pytestmark=pytest.mark.skipif(not NODE,reason="Node absent")


def executer(js):
    r=subprocess.run([NODE,"-"],input=js,text=True,capture_output=True)
    assert r.returncode == 0, r.stderr


def test_js_vue_restauree_apres_actualisation():
    section=MODELE.split("__ACTUALISATION_JS__",1)[1].split("</script>",1)[0]
    executer('''
const assert=require('node:assert/strict');
const elements=new Map();
for(const [id,value] of Object.entries({'f-q':'Équipe Lyon','f-book':'Winamax','strategies-ref':'comparateurs','analyse-selection':'uniques','analyse-periode':'ensemble','analyse-sport':'hockey','analyse-book':'Unibet'}))
  elements.set(id,{value,tagName:'INPUT'});
const document={getElementById:id=>elements.get(id),querySelectorAll:()=>[]};
const window={scrollY:320,scrollTo:(x,y)=>assert.equal(y,320)};
const requestAnimationFrame=fn=>fn();
const adapterTableaux=()=>{};
const FILTRES={book:[]}, CUMULS=[[]], TRIS={roi:''}, STRAT_PERIODES={ensemble:''};
let refBilan='Stratégie',cumul=0,limite=150,
    strategieChoisie={id:'Claude (rejeu)',nom:'Claude',periode:'ensemble'},triSeg='roi',ctlVue='conforme',periodeStrategies='ensemble';
const courbesMasquees=new Set(['M3']);
const rendus=[];
const rendreBilan=()=>rendus.push(refBilan),
 rendreParis=()=>rendus.push(document.getElementById('f-q').value),rendreSegments=()=>{},rendreControle=()=>{},rendreBilanUniques=()=>{},rendreSante=()=>{},
 rendreStrategies=()=>rendus.push(periodeStrategies),rendreAnalyses=()=>{},rendreMesStrategies=()=>{},rendreAccueil=()=>{};
function installerActualisation(config) {
  const etat=config.capturer();
  refBilan='Uniques';limite=50;strategieChoisie=null;periodeStrategies='futur';
  courbesMasquees.clear();elements.get('f-q').value='';elements.get('f-book').value='';
  config.restaurer(JSON.parse(JSON.stringify(etat)));
  assert.equal(elements.get('f-book').value,'Winamax');
  assert.equal(elements.get('analyse-sport').value,'hockey');
  assert.equal(elements.get('analyse-periode').value,'ensemble');
  assert.equal(strategieChoisie.id,'Claude (rejeu)');assert.equal(limite,150);
  assert.deepEqual([...courbesMasquees],['M3']);
  assert.deepEqual(rendus,['Stratégie','Équipe Lyon','ensemble']);
  assert.equal(etat.presentation,'lignes-v1');
  // Un ancien instantané ne réintroduit pas le filtre qui masquait les règles.
  elements.get('strategies-ref').value='';delete etat.presentation;
  config.restaurer(etat);
  assert.equal(elements.get('strategies-ref').value,'');
}
'''+section)


DOM = '''
const assert=require("node:assert/strict");
const elements=new Map();
const document={getElementById(id){
  if(!elements.has(id)) elements.set(id,{value:"",innerHTML:"",textContent:"",style:{},dataset:{},querySelectorAll(){return []},setAttribute(){}});
  return elements.get(id);
},querySelectorAll(){return []}};
const e=s => String(s ?? "").replaceAll("<","&lt;").replaceAll('"','&quot;');
const cote=e,pct=e,eur=e,quand=e,signe=()=>"",ouvrir=()=>{};
const STATUTS={}, STRAT_PERIODES={futur:"Depuis le lancement",ensemble:"Historique"};
const lire=()=>null, ecrire=()=>{};
'''+(Path(__file__).resolve().parents[1]/'web/liens.js').read_text()+(Path(__file__).resolve().parents[1]/'web/horaires.js').read_text()+(Path(__file__).resolve().parents[1]/'web/suivi.js').read_text()


def test_js_recherche_filtres_export_bom_echappement_et_archive_complete():
    rows=[{"id":str(i),"simulation":"D","reference":"Pinnacle","statut":"gagne",
           "sport":"football","bookmaker":"Winamax","domicile":"Équipe Saint-Étienne",
           "exterieur":"Lyon","ligue":"Ligue 1","pari":"Victoire; \'a\' \"domicile\"\nligne",
           "cote":2.1,"gain":-10,"ecart":.05,"clv":None,"detecte":"2026-10-15T09:00:00Z",
           "strategies":["chatgpt"],"convergence":True,"tranche":"2,01 – 3,00"} for i in range(75)]
    champs=list(rows[0]); data={"paris":[],"catalogue":{"champs":champs,"lignes":[list(p.values()) for p in rows]},
                              "strategies_badges":{"chatgpt":"ChatGPT v1"},"tranches":[],"valeurs_filtres":{},"simulations":{}}
    section=MODELE[MODELE.index("const recentes ="):MODELE.index("// --- Segments")]
    js=DOM+"const D="+json.dumps(data)+";\nconst badgeStrategies=()=>'';\nconst ecartsReferences=()=>'';\n"+section+'''
assert.equal(parisFiltres.length,75);
assert.equal((document.getElementById("liste-paris").innerHTML.match(/<article/g)||[]).length,50);
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


def test_js_paris_lignes_colorees_puces_resume_et_sante():
    base={"reference":"Pinnacle","sport":"volley","bookmaker":"Unibet","domicile":"Galatasaray","exterieur":"Fenerbahçe",
          "ligue":"Ligue turque","pari":"Galatasaray gagne","cote":1.9,"cote_juste":1.78,"ecart":.067,"mise":10,
          "detecte":"2026-10-15T09:00:00Z","strategies":[],"convergence":False,"simulation":"D","tranche":""}
    rows=[{**base,"id":"g","statut":"gagne","gain":9.0},{**base,"id":"d","statut":"demi_perdu","gain":-5.0},
          {**base,"id":"p","statut":"perdu","gain":-10.0},{**base,"id":"c","statut":"en_cours","gain":None},
          {**base,"id":"r","statut":"a_regler","gain":None}]
    champs=list(rows[0]); data={"paris":[],"catalogue":{"champs":champs,"lignes":[list(p.values()) for p in rows]},
        "strategies_badges":{},"tranches":[],"valeurs_filtres":{},"simulations":{},
        "etat":{"dernier_cycle":{"fin":"2026-10-15T09:00:00Z","etapes":{"pinnacle":{"ok":True,"degrade":True},
                "pulsescore":{"ok":True,"desactive":True},"netbet":{"ok":False}}}}}
    section=MODELE[MODELE.index("const recentes ="):MODELE.index("// --- Segments")]
    executer(DOM+"const D="+json.dumps(data)+";\nconst badgeStrategies=()=>'';\nconst ecartsReferences=()=>'';\n"+section+'''
const html=()=>document.getElementById("liste-paris").innerHTML;
assert.equal((html().match(/etat-gagne/g)||[]).length,1);
assert.equal((html().match(/etat-perdu/g)||[]).length,2);
assert.ok(html().includes("etat-regler") && html().includes("etat-cours"));
assert.ok(html().includes('class="puce-sport"') && html().includes("(1.78)"));
const resume=document.getElementById("paris-resume").innerHTML;
assert.ok(resume.includes("<b>3</b> réglés sur 5"));
assert.ok(resume.includes("-6"));
puceStatut="perdu"; rendreParis(); assert.deepEqual(parisFiltres.map(p=>p.id),["d","p"]);
puceStatut="gagne"; rendreParis(); assert.deepEqual(parisFiltres.map(p=>p.id),["g"]);
puceStatut="a_regler"; rendreParis(); assert.deepEqual(parisFiltres.map(p=>p.id),["r"]);
document.getElementById("reinitialiser-filtres").onclick(); assert.equal(parisFiltres.length,5);
rendreSanteParis(Date.parse("2026-10-15T09:05:00Z"));
const s=document.getElementById("paris-sante");
assert.equal(s.className,"paris-sante sante-panne");
assert.ok(s.innerHTML.includes("netbet") && !s.innerHTML.includes("pulsescore") && s.innerHTML.includes("1 alerte mineure"));
D.etat.dernier_cycle.etapes.netbet.ok=true;
rendreSanteParis(Date.parse("2026-10-15T09:30:00Z")); assert.equal(s.className,"paris-sante sante-alerte");
''')


def test_js_bilan_paris_uniques_tranches_etoile_et_periode():
    def pari(i, sim, statut, gain, regle, unique=True, sport="football"):
        return {"id":str(i),"simulation":sim,"statut":statut,"gain":gain,"mise":10,"unique_bilan":unique,"sport":sport,
                "tranche":"1,51 – 2,00","regle_le":regle,"detecte":regle,"reference":"Pinnacle","strategies":[]}
    rows=([pari(i,"A","gagne",8,"2026-10-18T10:00:00Z") for i in range(30)]+
          [pari(100+i,"A","perdu",-10,"2026-10-18T10:00:00Z") for i in range(20)]+
          [pari(200,"B","gagne",15,"2026-09-01T10:00:00Z",sport="tennis"),
           pari(201,"B","perdu",-10,"2026-10-18T10:00:00Z",unique=False),
           pari(202,"C","en_cours",None,None)])
    champs=list(rows[0]); data={"paris":[],"catalogue":{"champs":champs,"lignes":[list(p.values()) for p in rows]},
        "strategies_badges":{},"tranches":["1,01 – 1,50","1,51 – 2,00"],"valeurs_filtres":{},"simulations":{}}
    section=MODELE[MODELE.index("const recentes ="):MODELE.index("// --- Segments")]
    executer(DOM+"const D="+json.dumps(data)+";\nconst eurC=e;\nconst badgeStrategies=()=>'';\nconst ecartsReferences=()=>'';\n"+section+'''
const h=id=>document.getElementById(id).innerHTML;
assert.equal(document.getElementById("bu-note").textContent.split(" ")[0],"51");
assert.ok(h("bu-ecart").includes("A · 2 à 3 %") && h("bu-ecart").includes("B · 3 à 4 %") && !h("bu-ecart").includes("C · 4"));
assert.equal((h("bu-ecart").match(/★/g)||[]).length,1);
assert.ok(h("bu-ecart").indexOf("★")<h("bu-ecart").indexOf("B · 3"));
assert.ok(h("bu-cote").includes("1,51 – 2,00") && !h("bu-cote").includes("1,01 – 1,50"));
assert.ok(h("bu-sport").includes("tennis") || h("bu-sport").includes("Tennis"));
assert.ok(h("bu-kpis").includes(">55<"));
assert.equal(document.getElementById("bu-note-cotes").textContent,"");      // aucune cote de plus de 10 : rien à séparer
periodeBU="30"; rendreBilanUniques(Date.parse("2026-10-19T00:00:00Z"));
assert.equal(document.getElementById("bu-note").textContent.split(" ")[0],"50");
assert.ok(!h("bu-ecart").includes("B · 3"));
''')


def test_js_filtre_reference_egal_bilan_uniques():
    """La liste Paris filtrée sur une référence égale la ligne du bilan des paris uniques."""
    def ligne(i, ref, unique, statut, gain):
        return {"id": i, "simulation": "A", "reference": ref, "statut": statut, "gain": gain,
                "mise": 10, "unique_bilan": unique, "sport": "football", "bookmaker": "Winamax",
                "domicile": "Domicile", "exterieur": "Exterieur", "ligue": "Ligue", "pari": "1",
                "cote": 2.0, "cote_juste": 1.8, "ecart": 0.05, "clv": None,
                "detecte": "2026-10-01T10:00:00Z", "strategies": [], "convergence": False,
                "tranche": "1,51 – 2,00", "regle_le": "2026-10-01T12:00:00Z" if gain is not None else None}
    rows = [ligne("s1", "Smarkets", True, "gagne", 12),
            ligne("s1b", "Smarkets", False, "perdu", -10),
            ligne("s2", "Smarkets", True, "en_cours", None),
            ligne("s3", "Smarkets", False, "gagne", 5),
            ligne("p1", "Pinnacle", True, "perdu", -10),
            ligne("k1", "Kalshi", False, "gagne", 8)]
    champs = list(rows[0])
    data = {"paris": [], "catalogue": {"champs": champs, "lignes": [list(p.values()) for p in rows]},
            "strategies_badges": {}, "tranches": ["1,51 – 2,00"], "simulations": {},
            "valeurs_filtres": {"reference": ["Pinnacle", "Smarkets"]},
            "references": ["Pinnacle", "Betfair", "Polymarket", "Matchbook", "Smarkets", "Kalshi", "Consensus"]}
    section = MODELE[MODELE.index("const recentes ="):MODELE.index("// --- Segments")]
    executer(DOM + "const D=" + json.dumps(data) + ";\nconst eurC=e;\nconst badgeStrategies=()=>'';\nconst ecartsReferences=()=>'';\n" + section + r'''
const options = document.getElementById("f-ref").innerHTML;
for (const nom of ["Smarkets", "Kalshi", "Matchbook", "Pinnacle", "Betfair", "Polymarket"])
  assert.ok(options.includes('value="' + nom + '"'), nom);
assert.equal(parisFiltres.length, 6);
function ligneEgale(nom) {
  const L = selectionUniqueReference(nom);
  const s = statsListe(L);
  const html = document.getElementById("bu-reference").innerHTML;
  const m = html.match(new RegExp('data-ref="' + nom + '" data-n="(\\d+)" data-regles="(\\d+)" data-mises="([^"]*)" data-gain="([^"]*)" data-roi="([^"]*)"'));
  assert.ok(m, nom);
  assert.equal(Number(m[1]), s.n);
  assert.equal(Number(m[2]), s.regles);
  assert.equal(Number(m[3]), s.mises);
  assert.equal(Number(m[4]), s.gain);
  assert.equal(m[5] === "" ? null : Number(m[5]), s.roi);
  document.getElementById("f-ref").value = nom;
  rendreParis();
  assert.deepEqual(parisFiltres.map(p => p.id), L.map(p => p.id));
  const total = statsListe(parisFiltres);
  assert.equal(total.n, s.n);
  assert.equal(total.regles, s.regles);
  assert.equal(total.mises, s.mises);
  assert.equal(total.gain, s.gain);
  assert.equal(total.roi, s.roi);
}
ligneEgale("Smarkets");
assert.deepEqual(parisFiltres.map(p => p.id), ["s1", "s2"]);
assert.equal(statsListe(parisFiltres).gain, 12);
assert.equal(statsListe(parisFiltres).mises, 10);
assert.equal(statsListe(parisFiltres).roi, 1.2);
ligneEgale("Pinnacle");
assert.ok(!document.getElementById("bu-reference").innerHTML.includes('data-ref="Matchbook"'));
assert.ok(!document.getElementById("bu-reference").innerHTML.includes('data-ref="Kalshi"'));
periodeBU = "7";
rendreBilanUniques(Date.parse("2026-10-27T00:00:00Z"));
assert.ok(document.getElementById("bu-reference").innerHTML.includes('data-ref="Smarkets" data-n="2"'));
voirReference("Smarkets");
assert.equal(document.getElementById("f-ref").value, "Smarkets");
assert.equal(document.getElementById("f-sim").value, "");
assert.deepEqual(parisFiltres.map(p => p.id), selectionUniqueReference("Smarkets").map(p => p.id));
assert.equal(hashParis, "paris?ref=Smarkets");
''')


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


def test_cumul_evenements_pas_double_compte_entre_tranches():
    section=MODELE[MODELE.index('function additionner('):MODELE.index('function rendreBilan()')]
    executer('''
const assert=require('node:assert/strict');
const refBilan='Pinnacle';
const D={bilan:{'A|Pinnacle':{paris:2,regles:2,clv_n:2,evenements_detail:{'1':[2,2,.2,2]}},
                 'B|Pinnacle':{paris:2,regles:2,clv_n:2,evenements_detail:{'1':[1,1,.1,1],'2':[1,1,-.1,1]}}}};
'''+section+'''
const s=additionner(['A','B']);
assert.equal(s.regles,4);assert.equal(s.evenements_regles,2);assert.equal(s.clv_evenements_n,2);
assert.ok(Math.abs(s.clv_evenement)<1e-10);
''')


def test_navigation_compacte_retrouve_contrat_exact_du_catalogue():
    section=MODELE[MODELE.index('const recentes = '):MODELE.index('document.getElementById("nb-paris")')]
    executer('''
const assert=require('node:assert/strict');
const D={paris:[{id:'p',trace:['preuve']}],strategies_badges:{m3_structure:'M3 Max 3'},
 catalogue:{champs:['id','cote','debut','pari','simulation','strategies'],
            lignes:[['p',1.8,'2026-10-17T12:00:00Z','Handicap -3,5','C',['m3_structure']]]},
 laboratoire:{navigation:{paris:{p:{strategies_historiques:[],convergence_historique:false}}}}};
'''+section+'''
const p=D.laboratoire.navigation.paris.p;
assert.equal(p.cote,1.8);assert.equal(p.pari,'Handicap -3,5');assert.equal(p.debut,'2026-10-17T12:00:00Z');
assert.deepEqual(p.trace,['preuve']);assert.equal(p.m3_structure,true);
''')


def test_segments_sigma_exploratoire_et_compatibilite_anciens_champs():
    section=MODELE[MODELE.index('let triSeg = "roi";'):MODELE.index('// --- À régler')]
    executer(DOM+'''
const pctC=pct, eurC=eur;
const ancien={n:35,gagnes:30,attendus:20,ecart_sigma:3,roi:.2,gains:70,clv_moyenne:.02,clv_n:30};
const D={segments:[ancien]};
'''+section+'''
let html=document.getElementById('liste-segments').innerHTML;
assert.ok(html.includes('Sigma fragile') && !html.includes('Solide'));
assert.ok(!html.includes('undefined') && !html.includes('NaN'));
assert.deepEqual(verdict(ancien),['Piste','en_cours']);
D.segments=[{...ancien,sigma_fiable:false,evenements:4,sigma_limites:['tickets_meme_evenement']}];
rendreSegments();html=document.getElementById('liste-segments').innerHTML;
assert.ok(html.includes('4 matchs') && html.includes('tickets sur les mêmes matchs'));
D.segments=[{...ancien,sigma_fiable:true,evenements:35,sigma_limites:[]}];
rendreSegments();html=document.getElementById('liste-segments').innerHTML;
assert.ok(html.includes('À confirmer') && html.includes('essais multiples non corrigés'));
''')


def test_js_sante_niveaux_et_resume_des_erreurs():
    section = (MODELE[MODELE.index("function diagnosticSante"):MODELE.index("function rendreSanteParis")] +
               MODELE[MODELE.index("const SOURCES_COTES"):MODELE.index("rendreSante();\n\n// Famille publiée")])
    cycle = {"fin": "2026-10-15T09:00:00Z", "debut": "2026-10-15T08:58:00Z", "cotes": {"francaises": 25833},
             "pinnacle_secours": {"lignes": 120, "sports": ["football", "tennis"], "erreurs": [], "retard": ["football"]},
             "pinnacle_fraicheur": {"seuil_min": 10, "lignes": 1000, "lignes_perimees": 1000, "age_min_s": 650, "age_max_s": 880},
             "etapes": {"pinnacle": {"ok": True, "degrade": True, "erreurs": ["sport 17 : HTTP 403", "sport 45 : HTTP 403"]},
                        "netbet": {"ok": True, "degrade": True, "erreurs": ["budget"]},
                        "winamax_direct": {"ok": True}, "pulsescore": {"ok": True, "desactive": True}}}
    reglement = {"debut": "2026-10-15T08:30:00Z", "fin": "2026-10-15T08:35:00Z",
                 "resultats": {"paris_regles": 5, "paris_en_attente": 11, "sources_reglement": {"espn": 5}},
                 "etapes": {"resultats_espn_basket": {"ok": True}, "resultats_flashscore_basket": {"ok": True, "degrade": True, "erreurs": ["HTTP 429"]},
                            "resultats_nhl_officiel": {"ok": False}}}
    incidents = {"en_cours": {"winamax_direct": {"source": "Winamax", "niveau": "panne", "genre": "panne", "detail": "sport:1 : réseau",
                                                 "debut": "2026-10-15T08:50:00Z", "cycles": 3},
                              "pinnacle": {"source": "Pinnacle", "niveau": "alerte", "genre": "refus", "detail": "Refus HTTP 403", "debut": "2026-10-15T08:55:00Z", "cycles": 2}},
                 "termines": [{"source": "Unibet", "niveau": "panne", "genre": "panne", "detail": "lecture interrompue",
                               "debut": "2026-10-15T07:00:00Z", "fin": "2026-10-15T07:10:00Z", "cycles": 2}]}
    executer(DOM + '''
const D={etat:{dernier_cycle:%s,dernier_cycle_reglement:%s},incidents:%s};
const hm=()=>"09:00",man=[],groupesReglement=new Map();
''' % (json.dumps(cycle), json.dumps(reglement), json.dumps(incidents)) + section + '''
const t0=Date.parse("2026-10-15T09:05:00Z");
let d=diagnosticSante(t0); assert.equal(d.niveau,"ok"); assert.equal(d.mineures,2);
assert.equal(diagnosticSante(Date.parse("2026-10-15T09:30:00Z")).niveau,"alerte");
assert.equal(diagnosticSante(Date.parse("2026-10-15T11:00:00Z")).niveau,"panne");
rendreSante(t0);
const h=id=>document.getElementById(id).innerHTML;
assert.ok(h("sante-cotes").includes("Refus (403) sur 2 requêtes") && h("sante-cotes").includes("limite de temps"));
assert.ok(h("sante-cotes").includes("Lu normalement") && !h("sante-cotes").includes("PulseScore"));
assert.ok(h("sante-cotes").includes("Pinnacle · secours (pinnodds, PinBook)") && h("sante-cotes").includes("Pinnacle en retard (football) · 120 cotes · 2 sports"));
assert.ok(h("sante-cotes").includes("Pinnacle · fraîcheur") && h("sante-cotes").includes("En retard : cotes de 11 à 15 min, toutes écartées (limite 10 min)"));
assert.equal(ligneFraicheurPinnacle({seuil_min:10,lignes:10,lignes_perimees:0,age_min_s:30,age_max_s:240}).includes("Cotes de 1 à 4 min (limite 10 min)"), true);
assert.ok(ligneFraicheurPinnacle({seuil_min:10,lignes:200,lignes_perimees:50,age_max_s:700}).includes("25 % des cotes écartées"));
assert.ok(ligneFraicheurPinnacle({seuil_min:10,seuil_loin_min:16,proche_h:2,lignes:200,lignes_perimees:2,age_max_s:700})
  .includes("1 % des cotes écartées (limite 10 min si le match est dans les 2 h, 16 min sinon)"));
assert.equal(ligneFraicheurPinnacle({lignes:0}), "");
assert.ok(ligneSecoursPinnacle({pause:true,lignes:0}).includes("sante-mot-alerte"));
assert.ok(h("sante-auto").includes("Collecte et comparaison") && h("sante-auto").includes("5 enregistrements réglés"));
assert.ok(h("sante-resultats").includes("ESPN") && h("sante-resultats").includes("5 enregistrements réglés"));
assert.ok(h("sante-resultats").includes("sante-mot-panne"));
assert.ok(document.getElementById("sante-attente").textContent.includes("11 paris"));
assert.ok(h("sante-global").includes("2 alertes mineures sans effet"));
const inc=h("sante-incidents");
assert.ok(inc.includes("Winamax") && inc.includes("sante-mot-panne") && inc.includes("15 min") && inc.includes("3 cycles"));
assert.ok(inc.includes("Unibet") && inc.includes("terminé") && inc.includes("10 min"));
assert.ok(!inc.includes("Pinnacle"));                      // 2 cycles de refus : pas encore un incident
assert.ok(incidentsSante({}, t0).includes("Aucun incident") && incidentsSante(undefined, t0).includes("Aucun incident"));
// Échecs non bloquants (etat.json › echecs_recents) : ligne « Erreurs non bloquantes » des automatismes.
assert.ok(h("sante-auto").includes("Erreurs non bloquantes") && h("sante-auto").includes("Aucune ces dernières 24 heures"));
const ech={total:4,liste:[{quand:"2026-10-13T08:00:00Z",etape:"redecision",message:"ancien"},
  {quand:"2026-10-15T08:40:00Z",etape:"qwen",message:"KeyError: cle"}]};
const le=ligneEchecs(ech, t0);
assert.ok(le.includes("sante-mot-alerte") && le.includes("1 ces dernières 24 heures") && le.includes("qwen") && le.includes("KeyError: cle"), le);
assert.ok(!le.includes("ancien"));
const vieux=ligneEchecs({total:4,liste:[ech.liste[0]]}, t0);
assert.ok(vieux.includes("sante-mot-ok") && vieux.includes("4 depuis le début du suivi"), vieux);
assert.ok(ligneEchecs(undefined, t0).includes("sante-mot-ok"));
''')


def test_js_bilan_separe_les_cotes_de_plus_de_10():
    def pari(i, cote, statut, gain):
        return {"id":str(i),"simulation":"A","statut":statut,"gain":gain,"mise":10,"unique_bilan":True,"sport":"football","cote":cote,
                "tranche":"1,51 – 2,00","regle_le":"2026-10-18T10:00:00Z","detecte":"2026-10-18T10:00:00Z","reference":"Pinnacle","strategies":[]}
    rows=[pari(1,2.0,"gagne",10),pari(2,2.0,"perdu",-10),pari(3,30.0,"perdu",-10),pari(4,40.0,"perdu",-10)]
    champs=list(rows[0]); data={"paris":[],"catalogue":{"champs":champs,"lignes":[list(p.values()) for p in rows]},
        "strategies_badges":{},"tranches":["1,51 – 2,00"],"valeurs_filtres":{},"simulations":{}}
    section=MODELE[MODELE.index("const recentes ="):MODELE.index("// --- Segments")]
    executer(DOM+"const D="+json.dumps(data)+";\nconst eurC=e;\nconst badgeStrategies=()=>'';\nconst ecartsReferences=()=>'';\n"+section+'''
const note=document.getElementById("bu-note-cotes").textContent;
assert.ok(note.includes("Cote de 10 au plus : 2 paris") && note.includes("Cote supérieure à 10 : 2 paris"), note);
assert.ok(note.includes("−20") || note.includes("-20"), note);
''')
