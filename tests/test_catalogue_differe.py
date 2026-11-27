"""Catalogue des prises servi à part (catalogue.json), chargé après le premier affichage (audit design du 26/11/2026).

Côté construction : fichier écrit, absent de la page, contrôlé par json_public, compté dans la version, préchargé.
Côté page (Node) : fiches remplies sur place, accueil « en chargement » puis rendu, échec annoncé, autres onglets
débloqués seulement avec le catalogue.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from cotes.site import construction
from scripts.site_web import construire
from tests.outils_site import donnees_site
from tests.test_strategie_chatgpt import pari

RACINE = Path(__file__).resolve().parents[1]
MODELE = (RACINE / "web/modele.html").read_text(encoding="utf-8")
ACCUEIL = (RACINE / "web/accueil.js").read_text(encoding="utf-8")
NODE = shutil.which("node")


def _site(tmp_path, paris):
    (tmp_path / "paris.json").write_text(json.dumps(paris), encoding="utf-8")
    html = construire(tmp_path, tmp_path / "site").read_text(encoding="utf-8")
    return html, tmp_path / "site"


def _page(html):
    return json.loads(re.search(r"const D = (\{.*?\});\n", html, re.S).group(1))


def _node(js):
    r = subprocess.run([NODE, "-"], input=js, text=True, capture_output=True)
    assert r.returncode == 0, r.stderr
    return r.stdout


def test_catalogue_ecrit_a_part_et_absent_de_la_page(tmp_path):
    html, site = _site(tmp_path, [pari("a", statut="gagne", gain=11.0), pari("b", domicile="Équipe Témoin")])
    assert "catalogue" not in _page(html)
    assert "Équipe Témoin" not in html                     # les fiches ne sont plus dans index.html
    catalogue = json.loads((site / "catalogue.json").read_text(encoding="utf-8"))
    assert {"champs", "lignes"} <= set(catalogue) and len(catalogue["lignes"]) == 2
    ids = {ligne[catalogue["champs"].index("id")] for ligne in catalogue["lignes"]}
    assert ids == {"a", "b"}
    # les outils de test voient la page complète, catalogue compris
    assert donnees_site(html, site)["catalogue"] == catalogue


def test_catalogue_vide_reste_un_fichier_valide(tmp_path):
    html, site = _site(tmp_path, [])
    catalogue = json.loads((site / "catalogue.json").read_text(encoding="utf-8"))
    assert isinstance(catalogue["champs"], list) and catalogue["lignes"] == []


def test_catalogue_passe_par_le_controle_de_publication(tmp_path, monkeypatch):
    vus = []
    original = construction.json_public
    monkeypatch.setattr(construction, "json_public", lambda d: vus.append(d) or original(d))
    _site(tmp_path, [pari("a")])
    assert any(isinstance(d, dict) and set(d) == {"champs", "lignes"} for d in vus)


def test_secret_dans_une_prise_bloque_tout_le_site(tmp_path, monkeypatch):
    # pari réglé : son texte n'est publié que dans le catalogue des prises
    monkeypatch.setenv("PUSHOVER_APP_TOKEN", "jeton-tres-secret-42")
    ancien, site = _site(tmp_path, [pari("a", statut="gagne", gain=11.0)])
    (tmp_path / "paris.json").write_text(json.dumps([pari("a", statut="gagne", gain=11.0,
                                                         pari="Plus de 2,5 jeton-tres-secret-42")]), encoding="utf-8")
    with pytest.raises(ValueError, match="Publication bloquée"):
        construire(tmp_path, site)
    assert "jeton-tres-secret-42" not in (site / "catalogue.json").read_text(encoding="utf-8")
    assert (site / "index.html").read_text(encoding="utf-8") == ancien      # site existant gardé


def test_version_et_prechargement_suivent_le_catalogue(tmp_path):
    html, site = _site(tmp_path, [pari("a", statut="gagne", gain=11.0)])
    version = json.loads((site / "version.json").read_text())["version"]
    tete = html.split("</head>", 1)[0]
    # préchargé dès l'en-tête, à l'adresse exacte que la page demande ensuite (une seule requête)
    assert f'<link rel="preload" href="catalogue.json?v={version}" as="fetch" crossorigin>' in tete
    assert f'url.searchParams.set("v", "{version}")' in html
    assert html.count("<script>") == 2                       # contrôle de site.yml : rien de plus que les deux scripts
    # un changement du seul catalogue renouvelle la version (actualisation des pages ouvertes)
    _site(tmp_path, [pari("a", statut="gagne", gain=11.0, domicile="Autre équipe")])
    assert json.loads((site / "version.json").read_text())["version"] != version


def test_service_worker_ne_met_rien_en_cache():
    # catalogue.json est demandé avec la version : sans interception du service worker, jamais de catalogue périmé
    sw = (RACINE / "web/sw.js").read_text(encoding="utf-8")
    assert "'fetch'" not in sw and '"fetch"' not in sw and "caches." not in sw


DOM = r'''
const elements = {};
const element = id => elements[id] ||= {id, innerHTML: "", textContent: "", hidden: true, attrs: {},
  setAttribute(k, v) { this.attrs[k] = String(v); }, getAttribute(k) { return this.attrs[k] ?? null; }};
globalThis.document = {getElementById: element};
const e = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
const assert = require("assert");
'''


@pytest.mark.skipif(NODE is None, reason="node absent")
def test_fiches_remplies_sur_place_a_l_arrivee_du_catalogue():
    section = MODELE[MODELE.index("const recentes ="):MODELE.index("var CLES_MISE")]
    catalogue = {"champs": ["id", "mise", "gain", "strategies", "simulation"],
                 "lignes": [["a", 10, 5, ["jules"], "D"], ["b", 10, None, [], "D"]]}
    _node(DOM + "const D = {strategies_badges: {jules: 'Jules'}};\n" + section + f'''
const meme = fiches;
assert.equal(catalogueEnAttente, true); assert.equal(fiches.length, 0);
remplirFiches({json.dumps(catalogue)});
assert.equal(fiches, meme);                                  // même tableau : les vues gardent leur référence
assert.equal(catalogueEnAttente, false);
assert.deepEqual(fiches.map(f => [f.id, f.jules, f.mise_fixe, f.gain_fixe, f.sims[0]]), [["a", true, 10, 5, "D"], ["b", false, 10, null, "D"]]);
''')
    # catalogue embarqué dans D (tests, anciens sites) : lu tout de suite, rien à attendre
    _node(DOM + "const D = " + json.dumps({"catalogue": catalogue}) + ";\n" + section + '''
assert.equal(catalogueEnAttente, false); assert.equal(fiches.length, 2);
''')


@pytest.mark.skipif(NODE is None, reason="node absent")
def test_accueil_en_chargement_puis_echec_sans_rien_memoriser():
    stubs = '''
const D = {boosts: {actuels: []}, winamax_a_part: [], recommandees: {actuelles: []}};
var catalogueEnAttente = true, catalogueEchec = false, miseMode = "kelly", fiches = [];
let compares = 0; const comparerChiffres = () => { compares++; return {}; };
'''
    _node(DOM + stubs + ACCUEIL + '''
rendreAccueil();
const zones = ["acc-kpis", "acc-values", "acc-courbe", "acc-derniers"];
assert.deepEqual(zones.map(id => element(id).getAttribute("aria-busy")), ["true", "true", "true", "true"]);
assert.match(element("acc-kpis").innerHTML, /Gain net.*…/);
assert.match(element("acc-values").innerHTML, /Chargement des paris/);
assert.match(element("acc-boosts").innerHTML, /Aucun boost/);       // le reste de l'accueil est déjà là
assert.equal(compares, 0);                                          // rien de noté pour la visite suivante
catalogueEchec = true;
rendreAccueil();
assert.deepEqual(zones.map(id => element(id).getAttribute("aria-busy")), ["false", "false", "false", "false"]);
assert.match(element("acc-derniers").innerHTML, /indisponibles \\(connexion\\)/);
assert.equal(accueilEnAttente(false, false), false);
assert.equal(element("acc-kpis").getAttribute("aria-busy"), "false");
''')


@pytest.mark.skipif(NODE is None, reason="node absent")
def test_chargement_du_catalogue_reussi_puis_en_echec():
    section = MODELE[MODELE.index("async function chargerCatalogue()"):MODELE.index("var CATALOGUE_PRET")]
    base = DOM + '''
globalThis.location = {href: "https://exemple.github.io/cotes-value/index.html?alerte=x#paris"};
var catalogueEnAttente = true, catalogueEchec = false, pageActive = "accueil", journalMessageDepart = "Noté : joué";
const appels = [], pagesARendre = new Set();
const remplirFiches = c => { appels.push(["remplir", c.lignes.length]); catalogueEnAttente = false; };
const appliquerMise = m => appels.push(["mise", m]), miseMode = "kelly";
const rendreJournal = m => appels.push(["journal", m]), rendrePage = p => appels.push(["page", p, pagesARendre.has(p)]);
const rendreAccueil = () => appels.push(["accueil"]);
''' + section
    _node(base + '''
const urls = [];
globalThis.fetch = async (url, opts) => { urls.push(String(url)); assert.ok(opts.signal);
  return {ok: true, json: async () => ({champs: ["id"], lignes: [["a"], ["b"]]})}; };
chargerCatalogue().then(ok => {
  assert.equal(ok, true);
  // même adresse que le préchargement de l'en-tête : la requête de la page n'est jamais doublée
  assert.deepEqual(urls, ["https://exemple.github.io/cotes-value/catalogue.json?v=__VERSION_SITE__"]);
  assert.deepEqual(appels, [["remplir", 2], ["mise", "kelly"], ["journal", "Noté : joué"], ["page", "accueil", true]]);
  return chargerCatalogue();
}).then(ok => assert.equal(ok, true));
''')
    _node(base + '''
let essais = 0;
globalThis.fetch = async () => { essais++; throw new Error("réseau"); };
chargerCatalogue().then(ok => {
  assert.equal(ok, false); assert.equal(essais, 3); assert.equal(catalogueEchec, true);
  assert.equal(element("hors-ligne").hidden, false);
  assert.match(element("hors-ligne").textContent, /Paris indisponibles \\(connexion\\)/);
  assert.deepEqual(appels, [["accueil"]]);
});
''')


def test_autres_onglets_attendent_le_catalogue():
    corps = MODELE[MODELE.index("async function chargerDifferes()"):]
    corps = corps[:corps.index("\n}\n")]
    # le catalogue est attendu avant de débloquer les onglets et de relire les traces des fiches
    attente = corps.index("await CATALOGUE_PRET")
    assert attente < corps.index("f.trace") and attente < corps.index("differesEnAttente = false")
    assert MODELE.index("var CATALOGUE_PRET = chargerCatalogue();") < MODELE.index("\nchargerDifferes();")
