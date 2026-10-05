"""Génère le site (une page HTML autonome) à partir des données de la branche « donnees »."""
from __future__ import annotations

import json
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cotes.simulation import REFERENCES, SIMULATIONS, bilan  # noqa: E402


def _lire(chemin: Path, defaut):
    try:
        return json.loads(chemin.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return defaut


def construire(donnees: Path, sortie: Path) -> Path:
    paris = _lire(donnees / "paris.json", [])
    etat = _lire(donnees / "etat.json", {})
    actuelles = _lire(donnees / "opportunites_actuelles.json", [])
    data = {"paris": paris, "etat": etat, "actuelles": actuelles[:300], "bilan": bilan(paris),
            "simulations": {k: v["nom"] for k, v in SIMULATIONS.items()}, "references": REFERENCES}
    sortie.mkdir(parents=True, exist_ok=True)
    html = MODELE.replace("__DONNEES__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
    (sortie / "index.html").write_text(html, encoding="utf-8")
    (sortie / ".nojekyll").write_text("", encoding="utf-8")
    return sortie / "index.html"


MODELE = r"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Cotes Value</title>
<style>
:root{--fond:#f6f7f9;--carte:#fff;--texte:#1d2330;--doux:#5d6677;--ligne:#e3e6ec;--accent:#2457d6;
--vert:#0f8a4b;--vert-f:#e3f5ea;--rouge:#c23434;--rouge-f:#fbe7e7;--jaune:#9a6a00;--jaune-f:#fff4d6}
@media (prefers-color-scheme:dark){:root{--fond:#12151b;--carte:#1b1f27;--texte:#e7eaf0;--doux:#9aa3b2;
--ligne:#2c323d;--accent:#7aa2ff;--vert:#4cc98a;--vert-f:#173525;--rouge:#ff7b7b;--rouge-f:#3a1d1f;
--jaune:#f0c35a;--jaune-f:#3a3018}}
*{box-sizing:border-box}
body{margin:0;background:var(--fond);color:var(--texte);font:15px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
header{padding:20px 16px 8px;max-width:1200px;margin:auto}
h1{font-size:22px;margin:0 0 4px}
h2{font-size:17px;margin:0 0 10px}
.sous{color:var(--doux);font-size:13px}
main{max-width:1200px;margin:auto;padding:0 16px 40px}
section{background:var(--carte);border:1px solid var(--ligne);border-radius:12px;padding:16px;margin:14px 0}
.defile{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{border-collapse:collapse;width:100%;font-size:13.5px}
th,td{padding:7px 8px;border-bottom:1px solid var(--ligne);text-align:left;white-space:nowrap}
th{color:var(--doux);font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.02em}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
.pari{white-space:normal;min-width:180px}
.pos{color:var(--vert);font-weight:600}.neg{color:var(--rouge);font-weight:600}
.etiq{display:inline-block;padding:1px 7px;border-radius:999px;font-size:12px;font-weight:600}
.gagne,.demi_gagne{background:var(--vert-f);color:var(--vert)}
.perdu,.demi_perdu{background:var(--rouge-f);color:var(--rouge)}
.en_cours,.rembourse{background:var(--ligne);color:var(--doux)}
.a_regler{background:var(--jaune-f);color:var(--jaune)}
.grille td{text-align:center;white-space:normal;min-width:92px}
.grille td.ref{text-align:left;font-weight:600}
.grille .roi{font-size:16px;font-weight:700}
.grille .det{font-size:12px;color:var(--doux)}
.filtres{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:10px}
select,button{font:inherit;font-size:13px;padding:6px 8px;border-radius:8px;border:1px solid var(--ligne);
background:var(--carte);color:var(--texte)}
button{cursor:pointer;background:var(--accent);color:#fff;border:0}
.vide{color:var(--doux);padding:8px 0}
.indic{display:flex;flex-wrap:wrap;gap:10px;margin-top:10px}
.indic div{background:var(--carte);border:1px solid var(--ligne);border-radius:10px;padding:8px 12px;font-size:13px}
.indic b{display:block;font-size:17px}
details summary{cursor:pointer;color:var(--doux);font-size:13px;margin-top:6px}
.heure{display:block;color:var(--doux);font-size:12px}
@media (max-width:720px){
 table.fiches tr:first-child{display:none}
 table.fiches tr{display:block;border:1px solid var(--ligne);border-radius:10px;margin:0 0 10px;padding:6px 10px}
 table.fiches td{display:flex;justify-content:space-between;gap:12px;border:0;padding:3px 0;white-space:normal;text-align:right}
 table.fiches td::before{content:attr(data-l);color:var(--doux);font-size:12px;text-align:left;flex:none}
 table.fiches td.pari{min-width:0}
}
</style>
</head>
<body>
<header>
<h1>Cotes Value</h1>
<div class="sous" id="maj"></div>
<div class="indic" id="indic"></div>
</header>
<main>
<section>
<h2>À jouer maintenant</h2>
<div class="sous" style="margin-bottom:8px">Cotes françaises au-dessus de la cote juste d'au moins une référence, au dernier passage.
L'écart = cote × probabilité juste − 1.</div>
<div class="defile"><table id="actuelles" class="fiches"></table></div>
</section>
<section>
<h2>Bilan des simulations (10 € par pari)</h2>
<div class="sous" style="margin-bottom:8px">ROI des paris réglés · nombre de paris (dont en cours) · gain · CLV moyenne
(écart entre la cote prise et la cote juste juste avant le match : positive = on a battu le marché).</div>
<div class="defile"><table class="grille" id="grille"></table></div>
</section>
<section>
<h2>Paris simulés</h2>
<div class="filtres">
<select id="f-sim"></select><select id="f-ref"></select><select id="f-book"></select>
<select id="f-sport"></select><select id="f-statut"></select>
</div>
<div class="defile"><table id="paris" class="fiches"></table></div>
<div class="sous" id="nb-paris"></div>
</section>
<section>
<h2>Paris à régler à la main</h2>
<div class="sous" style="margin-bottom:8px">Résultat introuvable automatiquement (corners, match absent des résultats…).
Copiez la liste et collez-la à Claude : il cherchera les résultats et les enregistrera.</div>
<button id="copier">Copier la liste</button>
<div class="defile"><table id="manuels" class="fiches"></table></div>
</section>
</main>
<script>
const D = __DONNEES__;
const fmtE = x => (x>0?"+":"") + x.toFixed(2).replace(".", ",") + " €";
const fmtP = x => x==null ? "—" : (x>0?"+":"") + (100*x).toFixed(1).replace(".", ",") + " %";
const fmtC = x => x==null ? "—" : Number(x).toFixed(2).replace(".", ",");
const heure = s => { if(!s) return "—"; const d=new Date(s);
  return d.toLocaleString("fr-FR",{weekday:"short",day:"2-digit",month:"2-digit",hour:"2-digit",minute:"2-digit"}); };
const hm = s => s ? new Date(s).toLocaleTimeString("fr-FR",{hour:"2-digit",minute:"2-digit"}) : "";
const classe = x => x==null ? "" : (x>0 ? "pos" : x<0 ? "neg" : "");
const STATUTS = {en_cours:"En cours",gagne:"Gagné",perdu:"Perdu",rembourse:"Remboursé",demi_gagne:"½ gagné",
  demi_perdu:"½ perdu",a_regler:"À régler"};
const e = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

// en-tête
const dc = (D.etat||{}).dernier_cycle || {};
document.getElementById("maj").textContent = dc.debut ? "Dernière mise à jour : " + heure(dc.debut) +
  (dc.mode==="test" ? " (cycle de test)" : "") : "Pas encore de données.";
const moisCourant = new Date().toISOString().slice(0,7);
const req = ((D.etat||{}).requetes_par_mois||{})[moisCourant] || 0;
const nbRegles = D.paris.filter(p => !["en_cours","a_regler"].includes(p.statut)).length;
document.getElementById("indic").innerHTML = [
  ["Cotes françaises lues", (dc.cotes||{}).francaises ?? "—"], ["Matchs", dc.matchs_francais ?? "—"],
  ["Erreurs détectées", dc.opportunites ?? "—"], ["Paris simulés", D.paris.length],
  ["Paris réglés", nbRegles], ["Requêtes PulseScore ce mois", req]
].map(([a,b]) => `<div>${a}<b>${b}</b></div>`).join("");

// à jouer maintenant
const act = D.actuelles;
document.getElementById("actuelles").innerHTML = act.length ? `<tr><th>Début</th><th>Match</th><th>Pari</th>
<th>Cote française</th><th>Cote juste (référence)</th><th class="num">Écart</th></tr>` +
 act.map(o => `<tr><td data-l="Début">${heure(o.debut)}</td><td data-l="Match">${e(o.domicile)} – ${e(o.exterieur)}</td>
<td class="pari" data-l="Pari">${e(o.pari)}</td>
<td data-l="Cote française"><b>${e(o.bookmaker)} ${fmtC(o.cote)}</b><span class="heure">lue à ${hm(o.detecte)}</span></td>
<td data-l="Cote juste">${e(o.reference)} ${fmtC(o.cote_juste)}<span class="heure">lue à ${hm(o.lu_reference || o.detecte)}</span></td>
<td class="num pos" data-l="Écart">${fmtP(o.ecart)}</td></tr>`).join("")
 : `<tr><td class="vide">Aucune erreur de cote au dernier passage.</td></tr>`;

// grille des simulations
const sims = Object.keys(D.simulations), refs = [...D.references, "Toutes"];
let g = `<tr><th></th>${sims.map(s => `<th>${s}<br><span style="text-transform:none">${e(D.simulations[s])}</span></th>`).join("")}</tr>`;
for (const r of refs) {
  g += `<tr><td class="ref">${r === "Toutes" ? "Toutes références" : r}</td>`;
  for (const s of sims) {
    const b = D.bilan[s + "|" + r];
    g += b ? `<td><div class="roi ${classe(b.roi)}">${fmtP(b.roi)}</div><div class="det">${b.regles} réglés`+
      `${b.en_cours ? " (+" + b.en_cours + ")" : ""}<br>${fmtE(b.gains)} · CLV ${fmtP(b.clv_moyenne)}</div></td>` : `<td class="det">—</td>`;
  }
  g += "</tr>";
}
document.getElementById("grille").innerHTML = g;

// paris simulés + filtres
const filtres = {sim:["simulation","Toutes simulations"], ref:["reference","Toutes références"],
  book:["bookmaker","Tous bookmakers"], sport:["sport","Tous sports"], statut:["statut","Tous statuts"]};
for (const [id,[champ,tous]] of Object.entries(filtres)) {
  const vals = [...new Set(D.paris.map(p => p[champ]))].sort();
  const sel = document.getElementById("f-" + id);
  sel.innerHTML = `<option value="">${tous}</option>` + vals.map(v => `<option value="${e(v)}">${e(champ==="statut" ? STATUTS[v]||v : champ==="simulation" ? v + " " + (D.simulations[v]||"") : v)}</option>`).join("");
  sel.onchange = rendreParis;
}
function rendreParis() {
  const f = Object.fromEntries(Object.entries(filtres).map(([id,[champ]]) => [champ, document.getElementById("f-" + id).value]));
  const L = D.paris.filter(p => Object.entries(f).every(([k,v]) => !v || p[k] === v))
    .sort((a,b) => (b.detecte||"").localeCompare(a.detecte||""));
  document.getElementById("nb-paris").textContent = L.length + " paris" + (L.length > 500 ? " (500 plus récents affichés)" : "");
  document.getElementById("paris").innerHTML = L.length ? `<tr><th>Détecté</th><th>Match</th><th>Début</th><th>Pari</th>
<th>Bookmaker</th><th class="num">Cote</th><th>Réf.</th><th class="num">Cote juste</th><th class="num">Écart</th>
<th class="num">CLV</th><th>Sim.</th><th>Statut</th><th class="num">Gain</th></tr>` + L.slice(0,500).map(p => `<tr>
<td data-l="Détecté">${heure(p.detecte)}</td><td data-l="Match">${e(p.domicile)} – ${e(p.exterieur)}</td>
<td data-l="Début">${heure(p.debut)}</td><td class="pari" data-l="Pari">${e(p.pari)}</td>
<td data-l="Bookmaker">${e(p.bookmaker)}</td><td class="num" data-l="Cote"><b>${fmtC(p.cote)}</b></td>
<td data-l="Référence">${e(p.reference)}</td><td class="num" data-l="Cote juste">${fmtC(p.cote_juste)}<span class="heure">${hm(p.lu_reference)}</span></td>
<td class="num pos" data-l="Écart">${fmtP(p.ecart)}</td><td class="num ${classe(p.clv)}" data-l="CLV">${fmtP(p.clv)}</td>
<td data-l="Simulation">${p.simulation}</td>
<td data-l="Statut"><span class="etiq ${p.statut}">${STATUTS[p.statut]||p.statut}</span></td>
<td class="num ${classe(p.gain)}" data-l="Gain">${p.gain==null ? "—" : fmtE(p.gain)}</td></tr>`).join("")
  : `<tr><td class="vide">Aucun pari pour ces filtres.</td></tr>`;
}
rendreParis();

// à régler à la main (un pari par sélection, toutes simulations confondues)
const vus = new Set(), man = D.paris.filter(p => p.statut === "a_regler" && !vus.has(p.match_id + p.pari) && vus.add(p.match_id + p.pari));
document.getElementById("manuels").innerHTML = man.length ? `<tr><th>Match</th><th>Début</th><th>Pari</th><th>Bookmaker</th></tr>` +
  man.map(p => `<tr><td data-l="Match">${e(p.domicile)} – ${e(p.exterieur)}</td><td data-l="Début">${heure(p.debut)}</td>
<td class="pari" data-l="Pari">${e(p.pari)}</td><td data-l="Bookmaker">${e(p.bookmaker)}</td></tr>`).join("")
  : `<tr><td class="vide">Rien à régler à la main.</td></tr>`;
document.getElementById("copier").onclick = () => {
  const txt = "Paris à régler (cotes-value) :\n" + man.map(p =>
    `- [${p.match_id}] ${p.domicile} – ${p.exterieur} (${p.sport}, ${p.ligue||""}, ${new Date(p.debut).toLocaleString("fr-FR")}) : ${p.pari}`).join("\n");
  navigator.clipboard.writeText(txt).then(() => { const b = document.getElementById("copier"); b.textContent = "Copié ✓";
    setTimeout(() => b.textContent = "Copier la liste", 2000); });
};
</script>
</body>
</html>
"""
