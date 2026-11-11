"""Menu « Mise des bilans » : plusieurs modes de mise, Kelly ¼ par défaut, bankroll de départ modifiable."""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import site_web  # noqa: E402
from cotes.mises import MODE_DEFAUT, MODES_BILAN, MODES_INTEGRES, mise_du_mode  # noqa: E402
from cotes.simulation import mise_kelly  # noqa: E402

RACINE = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")


def pari(i, statut="gagne", cote=2.0, ecart=0.04):
    return {"id": f"p{i}", "simulation": "C", "reference": "Pinnacle", "match_id": f"m{i}", "marche": "TOTAL",
            "periode": "MATCH", "ligne": 2.5, "issue": "PLUS", "detecte": f"2026-10-20T10:{i:02d}:00+00:00",
            "debut": "2026-10-20T20:00:00+00:00", "regle_le": "2026-10-20T23:00:00+00:00", "statut": statut,
            "cote": cote, "cote_juste": round(cote / (1 + ecart), 4), "ecart": ecart, "bookmaker": "PMU",
            "sport": "football", "domicile": f"A{i}", "exterieur": f"B{i}", "pari": "Plus de 2,5", "mise": 10,
            "gain": 10 * (cote - 1) if statut == "gagne" else -10 if statut == "perdu" else None, "clv": None}


def test_kelly_un_quart_est_le_mode_par_defaut_et_reste_la_mise_d_origine():
    assert MODE_DEFAUT == "kelly" and next(iter(MODES_BILAN)) == "kelly"
    assert set(MODES_INTEGRES) == {"fixe", "kelly"}
    for cote, ecart in ((1.8, .0364), (7.0, .0774), (2.2, .0234), (1.5, .2), (3.0, .1)):
        p = {"cote": cote, "ecart": ecart}
        assert mise_du_mode("kelly", p) == mise_kelly(p)             # au centime près, bilans déjà publiés


def test_chaque_mode_mise_selon_le_pari_seulement_et_jamais_zero():
    p = {"cote": 2.0, "ecart": .04}
    assert mise_du_mode("fixe", p) == 10.0
    assert mise_du_mode("kelly", p) == 10.0 and mise_du_mode("kelly_8", p) == 5.0
    assert mise_du_mode("kelly_2", p) == 20.0                        # ½ de Kelly, plafond 2 %
    assert mise_du_mode("kelly_4_p1", {"cote": 1.5, "ecart": .2}) == 10.0      # plafond 1 %
    assert mise_du_mode("gain_constant", {"cote": 3.0, "ecart": .03}) == 5.0   # 5 € × (3 − 1) = 10 € de gain
    assert mise_du_mode("gain_constant", {"cote": 1.2, "ecart": .03}) == 25.0  # plafond 2,5 %
    for mode in MODES_BILAN:                                          # écart ou cote inexploitable : 1 €, jamais 0
        assert mise_du_mode(mode, {"cote": 2.0, "ecart": None}) > 0
        assert mise_du_mode(mode, {"cote": None, "ecart": .05}) > 0


def test_paris_en_mise_garde_les_paris_et_fait_suivre_le_gain():
    paris = [pari(1), pari(2, statut="perdu", cote=3.0, ecart=.10), pari(3, statut="en_cours")]
    copies = site_web.paris_en_mise(paris, "kelly_8")
    assert [c["mise"] for c in copies] == [5.0, 6.25, 5.0]
    assert [c["gain"] for c in copies] == [5.0, -6.25, None]
    assert paris[0]["mise"] == 10 and paris[0]["gain"] == 10.0       # les données d'origine restent intactes
    assert site_web.paris_en_mise_kelly(paris)[1]["mise"] == 12.5


def test_le_site_publie_le_menu_et_un_fichier_par_mode_supplementaire(tmp_path):
    paris = [pari(i, statut="gagne" if i % 2 else "perdu") for i in range(6)]
    (tmp_path / "paris.json").write_text(json.dumps(paris), encoding="utf-8")
    sortie = tmp_path / "site"
    html = site_web.construire(tmp_path, sortie).read_text(encoding="utf-8")
    d = json.loads(re.search(r"const D = (\{.*?\});\n", html, re.S).group(1).replace("<\\/", "</"))
    assert [m["cle"] for m in d["modes_mise"]] == list(MODES_BILAN) and d["mode_mise_defaut"] == "kelly"
    assert [m["cle"] for m in d["modes_mise"] if m["integre"]] == ["kelly", "fixe"]
    fichiers = sorted(f.stem for f in (sortie / "mises").glob("*.json"))
    assert fichiers == sorted(set(MODES_BILAN) - set(MODES_INTEGRES))
    bloc = json.loads((sortie / "mises" / "kelly_8.json").read_text(encoding="utf-8"))
    assert {"bilan", "courbes", "segments", "bilan_tranches", "filtres", "laboratoire", "mises_paris"} <= set(bloc)
    assert bloc["mises_paris"] == {f"p{i}": 5.0 for i in range(6)}
    # mêmes paris, mises divisées par deux par rapport à Kelly ¼ : même ROI
    assert bloc["bilan"]["C|Pinnacle"]["mises"] == d["kelly"]["bilan"]["C|Pinnacle"]["mises"] / 2
    assert bloc["bilan"]["C|Pinnacle"]["roi"] == d["kelly"]["bilan"]["C|Pinnacle"]["roi"]
    # le menu et la bankroll sont dans l'en-tête, sans les deux anciens boutons
    assert 'id="mode-mise"' in html and 'id="bankroll"' in html and 'data-mise="kelly"' not in html
    # un mode retiré ne reste pas publié d'une construction à l'autre
    (sortie / "mises" / "ancien.json").write_text("{}", encoding="utf-8")
    site_web.construire(tmp_path, sortie)
    assert not (sortie / "mises" / "ancien.json").exists()


JS_MISE = r'''
const assert = require("node:assert/strict");
const stock = new Map(Object.entries(STOCK));
const localStorage = {getItem: k => stock.has(k) ? stock.get(k) : null, setItem: (k, v) => stock.set(k, String(v))};
const menu = {value: "", options: []};
const document = {getElementById: id => id === "mode-mise" ? menu : null, body: {classList: {toggle() {}}}};
const D = {modes_mise: [{cle: "kelly", nom: "Kelly ¼", regle: "r", integre: true}, {cle: "kelly_8", nom: "Kelly ⅛", regle: "r", integre: false},
  {cle: "fixe", nom: "Fixe 1 %", regle: "r", integre: true}], mode_mise_defaut: "kelly",
  bilan: "fixe", bilan_tranches: "fixe", courbes: "fixe", segments: "fixe", filtres: "fixe", laboratoire: {a: 1, b: 1},
  paris_segments: [["m", "p", "PMU", 2, 1.9, "gagne", 10, null, "d", "t", "s", "Pinnacle", 4]],
  kelly: {bilan: "k4", bilan_tranches: "k4", courbes: "k4", segments: "k4", filtres: "k4", laboratoire: {b: 2}}};
const fiches = [{id: "p1", mise: 10, gain: 10, mise_kelly: 4}, {id: "p2", mise: 10, gain: null, mise_kelly: 6}];
'''


@pytest.mark.skipif(not NODE, reason="Node absent")
@pytest.mark.parametrize("stock, attendu", [({}, "kelly"), ({"cv-mise-v2": "fixe"}, "fixe"),
                                            ({"cv-mise": "fixe"}, "kelly"), ({"cv-mise-v2": "inconnu"}, "kelly")])
def test_js_kelly_par_defaut_et_choix_memorise(stock, attendu):
    """Sans choix mémorisé (ou avec l'ancienne clé) : Kelly ¼. Le choix fait depuis le menu est repris."""
    modele = site_web.MODELE
    formats = modele[modele.index("const BANKROLL_BASE"):modele.index("const pctC")]
    section = modele[modele.index("var CLES_MISE"):modele.index("const normaliserRecherche")]
    js = JS_MISE.replace("STOCK", json.dumps(stock)) + "const e = s => String(s);\n" + formats + section + f'''
assert.equal(miseMode, {json.dumps(attendu)});
assert.equal(D.bilan, miseMode === "fixe" ? "fixe" : "k4");
assert.equal(menu.value, miseMode);
// Kelly ¼ : la mise du catalogue ; le gain suit la mise ; le laboratoire ne remplace que ce qui change
appliquerMise("kelly");
assert.deepEqual(fiches.map(f => [f.mise, f.gain]), [[4, 4], [6, null]]);
assert.deepEqual(D.laboratoire, {{a: 1, b: 2}});
assert.equal(D.paris_segments[0][6], 4);
// mode chargé à la demande : sans son bloc, la vue fixe ; avec, ses mises par identifiant et ses gains de segments
appliquerMise("kelly_8");
assert.equal(miseMode, "fixe");
BLOCS_MISE.kelly_8 = {{bilan: "k8", bilan_tranches: "k8", courbes: "k8", segments: "k8", filtres: "k8", laboratoire: {{b: 3}},
  gains_segments: [2], mises_paris: {{p1: 2, p2: 3}}}};
appliquerMise("kelly_8");
assert.equal(miseMode, "kelly_8");
assert.deepEqual(fiches.map(f => [f.mise, f.gain]), [[2, 2], [3, null]]);
assert.equal(D.bilan, "k8"); assert.deepEqual(D.laboratoire, {{a: 1, b: 3}}); assert.equal(D.paris_segments[0][6], 2);
assert.equal(D.paris_segments[0].length, 12);
appliquerMise("fixe");
assert.deepEqual(fiches.map(f => [f.mise, f.gain]), [[10, 10], [10, null]]);
assert.equal(D.paris_segments[0][6], 10);
// bankroll : les montants suivent, pas les pourcentages
assert.equal(eur(10), "+10,00 €"); assert.equal(nomMise("fixe"), "10 € fixes");
BANKROLL = 2500;
assert.equal(eur(10), "+25,00 €"); assert.equal(eurC(-3186), "-7 965 €"); assert.equal(nomMise("fixe"), "25 € fixes");
assert.equal(eurC(null), "—"); assert.equal(nomMise("kelly_8"), "Kelly ⅛");
'''
    r = subprocess.run([NODE, "-"], input=js, text=True, capture_output=True)
    assert r.returncode == 0, r.stderr


@pytest.mark.skipif(not NODE, reason="Node absent")
def test_js_bankroll_memorisee_et_bornee():
    modele = site_web.MODELE
    formats = modele[modele.index("const BANKROLL_BASE"):modele.index("const pctC")]
    for stock, attendu in (({"cv-bankroll": "5000"}, 5000), ({"cv-bankroll": "3"}, 1000), ({"cv-bankroll": "abc"}, 1000),
                           ({}, 1000)):
        js = (f'const assert=require("node:assert/strict");const s={json.dumps(stock)};'
              'const localStorage={getItem:k=>k in s?s[k]:null};\n' + formats +
              f'\nassert.equal(BANKROLL,{attendu});assert.equal(enBankroll(null),null);assert.equal(enBankroll(20),{attendu}*20/1000);')
        r = subprocess.run([NODE, "-"], input=js, text=True, capture_output=True)
        assert r.returncode == 0, r.stderr
