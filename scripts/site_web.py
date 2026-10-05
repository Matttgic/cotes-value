"""Génère le site (une page HTML autonome, en onglets) à partir des données de la branche « donnees »."""
from __future__ import annotations

import json
import sys
from pathlib import Path

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
    actuelles = [o for o in _lire(donnees / "opportunites_actuelles.json", []) if not o.get("suspect")]
    ctl = _lire(donnees / "controle.json", {})
    groupes = [{k: g.get(k) for k in ("bookmaker", "sport", "marche", "periode", "type", "n", "mediane",
                                      "part_haute", "statut", "exemples")} for g in ctl.get("groupes", {}).values()]
    controle = {"groupes": sorted(groupes, key=lambda g: (-(g["n"] or 0))), "matchs": ctl.get("matchs_suspects", [])}
    data = {"paris": paris, "etat": etat, "actuelles": actuelles[:300], "bilan": bilan(paris), "controle": controle,
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
:root{--fond:#f5f6f8;--carte:#fff;--texte:#1b2130;--doux:#677084;--ligne:#e4e7ec;--accent:#2457d6;
--accent-f:#e8eefc;--vert:#0f8a4b;--vert-f:#e2f4e9;--rouge:#c23434;--rouge-f:#fbe6e6;--jaune:#8f6200;--jaune-f:#fff3d1}
@media (prefers-color-scheme:dark){:root{--fond:#111419;--carte:#1a1e26;--texte:#e6e9ef;--doux:#9aa2b1;
--ligne:#2a303b;--accent:#7ea4ff;--accent-f:#1f2a44;--vert:#4ec88a;--vert-f:#16321f;--rouge:#ff8080;
--rouge-f:#3a1c1e;--jaune:#f0c35a;--jaune-f:#36301b}}
*{box-sizing:border-box}
body{margin:0;background:var(--fond);color:var(--texte);font:15px/1.4 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
.haut{position:sticky;top:0;z-index:5;background:var(--fond);border-bottom:1px solid var(--ligne)}
.titre{max-width:760px;margin:auto;padding:12px 16px 6px;display:flex;align-items:baseline;justify-content:space-between;gap:8px}
h1{font-size:18px;margin:0}
.maj{color:var(--doux);font-size:12.5px}
nav{max-width:760px;margin:auto;padding:0 12px 8px;display:flex;gap:6px;overflow-x:auto;scrollbar-width:none}
nav button{flex:none;font:inherit;font-size:14px;padding:7px 12px;border-radius:999px;border:1px solid var(--ligne);
background:var(--carte);color:var(--texte);cursor:pointer}
nav button.actif{background:var(--accent);border-color:var(--accent);color:#fff}
nav .nb{font-size:12px;opacity:.75;margin-left:3px}
main{max-width:760px;margin:auto;padding:12px 16px 40px}
.onglet{display:none}.onglet.actif{display:block}
.aide{color:var(--doux);font-size:13px;margin:0 0 10px}
.carte{background:var(--carte);border:1px solid var(--ligne);border-radius:12px;padding:10px 12px;margin-bottom:8px}
.l1{display:flex;justify-content:space-between;gap:10px;font-size:13px;color:var(--doux)}
.l1 .match{color:var(--texte);font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.l1 .quand{flex:none}
.l2{margin:3px 0 6px;font-size:15px}
.l3{display:flex;flex-wrap:wrap;align-items:center;gap:4px 12px;font-size:13.5px}
.l3 i{font-style:normal;color:var(--doux);font-size:12px}
.ecart{margin-left:auto;font-weight:700;color:var(--vert)}
.l4{display:flex;flex-wrap:wrap;gap:4px 10px;margin-top:6px;font-size:12px;color:var(--doux);align-items:center}
.badge{display:inline-block;padding:1px 7px;border-radius:999px;font-size:12px;font-weight:600;background:var(--accent-f);color:var(--accent)}
.gagne,.demi_gagne{background:var(--vert-f);color:var(--vert)}
.perdu,.demi_perdu{background:var(--rouge-f);color:var(--rouge)}
.en_cours,.rembourse{background:var(--ligne);color:var(--doux)}
.a_regler{background:var(--jaune-f);color:var(--jaune)}
.pos{color:var(--vert)}.neg{color:var(--rouge)}
.vide{color:var(--doux);text-align:center;padding:30px 10px}
.puces{display:flex;gap:6px;overflow-x:auto;margin-bottom:10px;scrollbar-width:none}
.puces button,select,.btn{flex:none;font:inherit;font-size:13px;padding:6px 10px;border-radius:8px;border:1px solid var(--ligne);
background:var(--carte);color:var(--texte);cursor:pointer}
.puces button.actif{border-color:var(--accent);color:var(--accent);font-weight:600}
.btn{background:var(--accent);border-color:var(--accent);color:#fff}
table{width:100%;border-collapse:collapse;background:var(--carte);border:1px solid var(--ligne);border-radius:12px;overflow:hidden;font-size:14px}
th,td{padding:9px 10px;border-bottom:1px solid var(--ligne);text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
@media (max-width:480px){th,td{padding:8px 6px;font-size:13px}}
th{font-size:12px;color:var(--doux);font-weight:600}
th:first-child,td:first-child{text-align:left}
tr:last-child td{border-bottom:0}
td small{display:block;color:var(--doux);font-size:11.5px}
.filtres{display:flex;gap:6px;overflow-x:auto;margin-bottom:10px;scrollbar-width:none}
.infos{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px;margin-top:14px}
.infos div{background:var(--carte);border:1px solid var(--ligne);border-radius:10px;padding:8px 10px;font-size:12.5px;color:var(--doux)}
.infos b{display:block;color:var(--texte);font-size:16px}
</style>
</head>
<body>
<div class="haut">
  <div class="titre"><h1>Cotes Value</h1><span class="maj" id="maj"></span></div>
  <nav id="onglets">
    <button data-o="jouer">À jouer<span class="nb" id="nb-jouer"></span></button>
    <button data-o="bilan">Bilan</button>
    <button data-o="paris">Paris<span class="nb" id="nb-paris"></span></button>
    <button data-o="regler">À régler<span class="nb" id="nb-regler"></span></button>
    <button data-o="controle">Contrôle<span class="nb" id="nb-controle"></span></button>
  </nav>
</div>
<main>
  <section class="onglet" id="o-jouer">
    <p class="aide">Cotes françaises au-dessus de la cote juste d'une référence, au dernier passage.</p>
    <div id="jouer"></div>
  </section>
  <section class="onglet" id="o-bilan">
    <div class="puces" id="puces-ref"></div>
    <table id="bilan"></table>
    <p class="aide" style="margin-top:8px">10 € par pari. ROI sur les paris réglés. CLV : écart entre la cote prise et la cote
    juste juste avant le match (positive = on a battu le marché ; c'est l'indicateur le plus rapide à devenir fiable).</p>
    <div class="infos" id="infos"></div>
  </section>
  <section class="onglet" id="o-paris">
    <div class="filtres"><select id="f-sim"></select><select id="f-ref"></select><select id="f-statut"></select>
    <select id="f-book"></select><select id="f-sport"></select></div>
    <div id="paris"></div>
    <div style="text-align:center"><button class="btn" id="plus" style="display:none">Afficher plus</button></div>
  </section>
  <section class="onglet" id="o-regler">
    <p class="aide">Résultat introuvable automatiquement. Copiez la liste et collez-la à Claude : il cherchera les
    résultats et les enregistrera.</p>
    <p><button class="btn" id="copier">Copier la liste</button></p>
    <div id="regler"></div>
  </section>
  <section class="onglet" id="o-controle">
    <p class="aide">Chaque type d'intitulé de chaque bookmaker est comparé à la référence à chaque passage. Bien
    traduit, un marché est en général un peu sous la cote juste (marge) : rapport médian cote / cote juste entre
    0,70 et 1,02, et moins de 10 % des cotes au-dessus de 1,12. Seuls les intitulés <b>conformes</b> donnent des paris.</p>
    <div class="infos" id="ctl-resume" style="margin:0 0 12px"></div>
    <div class="puces" id="ctl-puces"></div>
    <div id="ctl-liste"></div>
  </section>
</main>
<script>
const D = __DONNEES__;
const e = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const cote = x => x==null ? "—" : Number(x).toFixed(2).replace(".", ",");
const pct = x => x==null ? "—" : (x>0?"+":"") + (100*x).toFixed(1).replace(".", ",") + " %";
const eur = x => (x>0?"+":"") + Number(x).toFixed(2).replace(".", ",") + " €";
const quand = s => s ? new Date(s).toLocaleString("fr-FR",{weekday:"short",day:"numeric",month:"numeric",hour:"2-digit",minute:"2-digit"}) : "—";
const hm = s => s ? new Date(s).toLocaleTimeString("fr-FR",{hour:"2-digit",minute:"2-digit"}) : "";
const signe = x => x==null ? "" : x>0 ? "pos" : x<0 ? "neg" : "";
const STATUTS = {en_cours:"En cours",gagne:"Gagné",perdu:"Perdu",rembourse:"Remboursé",demi_gagne:"½ gagné",
  demi_perdu:"½ perdu",a_regler:"À régler"};
const lire = k => { try { return localStorage.getItem(k); } catch { return null; } };
const ecrire = (k,v) => { try { localStorage.setItem(k,v); } catch {} };

// --- en-tête et onglets
const dc = (D.etat||{}).dernier_cycle || {};
document.getElementById("maj").textContent = dc.debut ? "mis à jour " + quand(dc.debut) + (dc.mode==="test" ? " · test" : "") : "pas encore de données";
function ouvrir(o) {
  document.querySelectorAll("nav button").forEach(b => b.classList.toggle("actif", b.dataset.o===o));
  document.querySelectorAll(".onglet").forEach(s => s.classList.toggle("actif", s.id==="o-"+o));
  ecrire("onglet", o); history.replaceState(null, "", "#"+o);
}
document.querySelectorAll("nav button").forEach(b => b.onclick = () => ouvrir(b.dataset.o));

// --- À jouer
const carteActuelle = o => `<article class="carte">
<div class="l1"><span class="match">${e(o.domicile)} – ${e(o.exterieur)}</span><span class="quand">${quand(o.debut)}</span></div>
<div class="l2">${e(o.pari)}</div>
<div class="l3"><span><b>${e(o.bookmaker)} ${cote(o.cote)}</b> <i>${hm(o.detecte)}</i></span>
<span>${e(o.reference)} ${cote(o.cote_juste)} <i>${hm(o.lu_reference || o.detecte)}</i></span><span class="ecart">${pct(o.ecart)}</span></div>
</article>`;
document.getElementById("jouer").innerHTML = D.actuelles.length ? D.actuelles.map(carteActuelle).join("")
  : `<div class="vide">Aucune erreur de cote au dernier passage.</div>`;
document.getElementById("nb-jouer").textContent = D.actuelles.length || "";

// --- Bilan
let refBilan = "Toutes";
function rendreBilan() {
  document.getElementById("puces-ref").innerHTML = ["Toutes", ...D.references].map(r =>
    `<button data-r="${r}" class="${r===refBilan?"actif":""}">${r==="Toutes"?"Toutes réf.":r}</button>`).join("");
  document.querySelectorAll("#puces-ref button").forEach(b => b.onclick = () => { refBilan = b.dataset.r; rendreBilan(); });
  document.getElementById("bilan").innerHTML = `<tr><th>Simulation</th><th>Paris</th><th>Gain</th><th>ROI</th><th>CLV</th></tr>` +
    Object.entries(D.simulations).map(([s, nom]) => {
      const b = D.bilan[s + "|" + refBilan];
      if (!b) return `<tr><td><b>${s}</b> <small>${e(nom)}</small></td><td>0</td><td>—</td><td>—</td><td>—</td></tr>`;
      return `<tr><td><b>${s}</b> <small>${e(nom)}</small></td><td>${b.regles}<small>${b.en_cours ? "+" + b.en_cours + " en cours" : ""}</small></td>
<td class="${signe(b.gains)}">${eur(b.gains)}</td><td class="${signe(b.roi)}"><b>${pct(b.roi)}</b></td><td class="${signe(b.clv_moyenne)}">${pct(b.clv_moyenne)}</td></tr>`;
    }).join("");
}
rendreBilan();
const mois = new Date().toISOString().slice(0,7);
document.getElementById("infos").innerHTML = [
  ["Cotes françaises lues", (dc.cotes||{}).francaises], ["Matchs comparés", dc.matchs_francais],
  ["Erreurs au dernier passage", dc.opportunites], ["Requêtes PulseScore ce mois", ((D.etat||{}).requetes_par_mois||{})[mois] || 0]
].map(([a,b]) => `<div>${a}<b>${b ?? "—"}</b></div>`).join("");

// --- Paris : un même pari pris par plusieurs simulations = une seule fiche
const groupes = new Map();
for (const p of D.paris) {
  const k = [p.reference, p.match_id, p.marche, p.periode, p.ligne, p.issue].join("|");
  if (!groupes.has(k)) groupes.set(k, {...p, sims: []});
  groupes.get(k).sims.push(p.simulation);
}
const fiches = [...groupes.values()].sort((a,b) => (b.detecte||"").localeCompare(a.detecte||""));
document.getElementById("nb-paris").textContent = fiches.length || "";
const FILTRES = {sim:["sims","Simulations"], ref:["reference","Références"], statut:["statut","Statuts"],
  book:["bookmaker","Bookmakers"], sport:["sport","Sports"]};
for (const [id,[champ,tous]] of Object.entries(FILTRES)) {
  const vals = [...new Set(fiches.flatMap(f => champ==="sims" ? f.sims : [f[champ]]))].sort();
  const sel = document.getElementById("f-" + id);
  sel.innerHTML = `<option value="">${tous}</option>` + vals.map(v => `<option value="${e(v)}">${e(
    champ==="statut" ? STATUTS[v]||v : champ==="sims" ? v + " " + (D.simulations[v]||"") : v)}</option>`).join("");
  sel.onchange = () => { limite = 50; rendreParis(); };
}
let limite = 50;
const carteParis = p => `<article class="carte">
<div class="l1"><span class="match">${e(p.domicile)} – ${e(p.exterieur)}</span><span class="quand">${quand(p.debut)}</span></div>
<div class="l2">${e(p.pari)}</div>
<div class="l3"><span><b>${e(p.bookmaker)} ${cote(p.cote)}</b></span><span>${e(p.reference)} ${cote(p.cote_juste)}</span>
<span class="ecart">${pct(p.ecart)}</span></div>
<div class="l4"><span class="badge ${p.statut}">${STATUTS[p.statut]||p.statut}</span>
${p.gain!=null ? `<b class="${signe(p.gain)}">${eur(p.gain)}</b>` : ""}
<span>CLV <span class="${signe(p.clv)}">${pct(p.clv)}</span></span><span>Sim. ${p.sims.join(" ")}</span><span>vu ${quand(p.detecte)}</span></div>
</article>`;
function rendreParis() {
  const f = Object.fromEntries(Object.entries(FILTRES).map(([id,[champ]]) => [champ, document.getElementById("f-"+id).value]));
  const L = fiches.filter(p => Object.entries(f).every(([k,v]) => !v || (k==="sims" ? p.sims.includes(v) : p[k]===v)));
  document.getElementById("paris").innerHTML = L.length ? L.slice(0, limite).map(carteParis).join("")
    : `<div class="vide">Aucun pari pour ces filtres.</div>`;
  const plus = document.getElementById("plus");
  plus.style.display = L.length > limite ? "" : "none";
  plus.onclick = () => { limite += 50; rendreParis(); };
}
rendreParis();

// --- À régler
const vus = new Set(), man = D.paris.filter(p => p.statut==="a_regler" && !vus.has(p.match_id+p.pari) && vus.add(p.match_id+p.pari));
document.getElementById("nb-regler").textContent = man.length || "";
document.getElementById("regler").innerHTML = man.length ? man.map(p => `<article class="carte">
<div class="l1"><span class="match">${e(p.domicile)} – ${e(p.exterieur)}</span><span class="quand">${quand(p.debut)}</span></div>
<div class="l2">${e(p.pari)}</div><div class="l4"><span>${e(p.bookmaker)}</span><span>${e(p.ligue||"")}</span></div></article>`).join("")
  : `<div class="vide">Rien à régler à la main.</div>`;
document.getElementById("copier").style.display = man.length ? "" : "none";
document.getElementById("copier").onclick = () => {
  const txt = "Paris à régler (cotes-value) :\n" + man.map(p =>
    `- [${p.match_id}] ${p.domicile} – ${p.exterieur} (${p.sport}, ${p.ligue||""}, ${new Date(p.debut).toLocaleString("fr-FR")}) : ${p.pari}`).join("\n");
  navigator.clipboard.writeText(txt).then(() => { const b = document.getElementById("copier"); b.textContent = "Copié ✓";
    setTimeout(() => b.textContent = "Copier la liste", 2000); });
};

// --- Contrôle
const CTL = {non_conforme:"Non conformes", a_verifier:"À vérifier", conforme:"Conformes"};
const cg = (D.controle||{}).groupes || [], cm = (D.controle||{}).matchs || [];
const nbc = s => cg.filter(g => g.statut===s).length;
document.getElementById("nb-controle").textContent = nbc("non_conforme") || "";
document.getElementById("ctl-resume").innerHTML = [["Conformes", nbc("conforme")], ["À vérifier", nbc("a_verifier")],
  ["Non conformes", nbc("non_conforme")], ["Matchs mal associés ?", cm.length]].map(([a,b]) => `<div>${a}<b>${b}</b></div>`).join("");
let ctlVue = nbc("non_conforme") ? "non_conforme" : "a_verifier";
const num = x => x==null ? "—" : Number(x).toFixed(2).replace(".", ",");
function rendreControle() {
  document.getElementById("ctl-puces").innerHTML = [...Object.entries(CTL), ["matchs","Matchs"]].map(([k,v]) =>
    `<button data-v="${k}" class="${k===ctlVue?"actif":""}">${v}</button>`).join("");
  document.querySelectorAll("#ctl-puces button").forEach(b => b.onclick = () => { ctlVue = b.dataset.v; rendreControle(); });
  let html;
  if (ctlVue === "matchs") {
    html = cm.length ? cm.map(m => `<article class="carte"><div class="l1"><span class="match">${e(m.match)}</span>
<span>${e(m.bookmaker)}</span></div><div class="l4">Rapport médian ${num(m.rapport_median)} sur tous les marchés du match</div></article>`).join("")
      : `<div class="vide">Aucun match suspect au dernier passage.</div>`;
  } else {
    const L = cg.filter(g => g.statut === ctlVue).slice(0, 300);
    html = L.length ? L.map(g => `<article class="carte">
<div class="l1"><span class="match">${e(g.bookmaker)} · ${e(g.sport)} · ${e(g.marche)} ${e(g.periode)}</span>
<span class="quand">${g.n} mesure${g.n>1?"s":""}</span></div>
<div class="l2">« ${e(g.type)} »</div>
<div class="l4"><span>Rapport médian <b>${num(g.mediane)}</b></span><span>au-dessus de 1,12 : ${g.part_haute==null?"—":Math.round(100*g.part_haute)+" %"}</span></div>
${(g.exemples||[]).map(x => `<div class="l4"><span>${e(x.match)}</span><span>${e(x.libelle)}${x.ligne!=null?" ["+e(x.ligne)+"]":""} ${e(x.issue)}</span>
<span>${cote(x.cote)} / ${e(x.reference)} ${cote(x.cote_juste)}</span></div>`).join("")}</article>`).join("")
      : `<div class="vide">Aucun intitulé dans cette catégorie.</div>`;
  }
  document.getElementById("ctl-liste").innerHTML = html;
}
rendreControle();

// onglet de départ : celui de l'adresse, sinon le dernier ouvert, sinon « À jouer »
const depart = location.hash.slice(1) || lire("onglet") || "jouer";
const ONGLETS = ["jouer","bilan","paris","regler","controle"];
ouvrir(ONGLETS.includes(depart) ? depart : "jouer");
window.addEventListener("hashchange", () => { const o = location.hash.slice(1); if (ONGLETS.includes(o)) ouvrir(o); });
</script>
</body>
</html>
"""
