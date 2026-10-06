"""Génère le site (une page HTML autonome, en onglets) à partir des données de la branche « donnees »."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cotes.simulation import REFERENCES, SIMULATIONS, TEMOIN, TRANCHES, bilan, bilan_tranches  # noqa: E402
from cotes.stockage import lire_archives  # noqa: E402


def _lire(chemin: Path, defaut):
    try:
        return json.loads(chemin.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return defaut


EN_COURS_AFFICHES = 400        # paris en cours les plus récents
REGLES_AFFICHES = 600          # paris réglés les plus récemment (+ tous ceux à régler à la main)
CHAMPS_FILTRES = {"sims": "simulation", "reference": "reference", "statut": "statut", "bookmaker": "bookmaker",
                  "sport": "sport"}


def cle_fiche(p: dict) -> tuple:
    """Un même pari pris par plusieurs simulations = une seule fiche (même clé que la page)."""
    return (p.get("reference"), p.get("match_id"), p.get("marche"), p.get("periode"), p.get("ligne"), p.get("issue"))


CHAMPS_FICHE = ("reference", "match_id", "marche", "periode", "ligne", "issue", "domicile", "exterieur", "debut",
                "pari", "bookmaker", "cote", "cote_juste", "ecart", "statut", "gain", "clv", "detecte", "sport",
                "ligue", "regle_le")


def selection_paris(paris: list[dict], en_cours: int = EN_COURS_AFFICHES,
                    regles: int = REGLES_AFFICHES) -> tuple[list[dict], int, dict]:
    """Page légère : un même pari pris par plusieurs simulations = une fiche (celle de la première
    détection, avec la liste des simulations). Garde les `en_cours` fiches en cours les plus récentes, les
    `regles` fiches réglées le plus récemment et toutes celles à régler à la main. Renvoie (fiches de la
    plus récente à la plus ancienne, nombre total de fiches, valeurs des filtres calculées sur TOUS les
    paris)."""
    groupes: dict[tuple, list[dict]] = {}
    for p in paris:
        groupes.setdefault(cle_fiche(p), []).append(p)
    fiches = []
    for lignes in groupes.values():
        lignes.sort(key=lambda r: r.get("detecte") or "")
        f = {c: lignes[0].get(c) for c in CHAMPS_FICHE}
        f["sims"] = sorted({r.get("simulation") for r in lignes})
        f["a_regler"] = any(r.get("statut") == "a_regler" for r in lignes)
        fiches.append(f)
    recents = lambda champ: lambda f: f.get(champ) or ""      # noqa: E731
    ouverts = sorted((f for f in fiches if f["statut"] == "en_cours"), key=recents("detecte"), reverse=True)
    finis = sorted((f for f in fiches if f["statut"] not in ("en_cours", "a_regler")), key=recents("regle_le"),
                   reverse=True)
    # le témoin « Pinnacle brut » (des centaines de paris par cycle) a sa propre part, plus petite
    temoin = lambda f: f["reference"] == TEMOIN                 # noqa: E731
    gardees = ([f for f in ouverts if not temoin(f)][:en_cours] + [f for f in finis if not temoin(f)][:regles]
               + [f for f in ouverts if temoin(f)][:en_cours // 4] + [f for f in finis if temoin(f)][:regles // 4]
               + [f for f in fiches if f["a_regler"]])
    gardees.sort(key=recents("detecte"), reverse=True)
    valeurs = {f: sorted({str(p.get(c)) for p in paris if p.get(c) is not None}) for f, c in CHAMPS_FILTRES.items()}
    return gardees, sum(f["reference"] != TEMOIN for f in fiches), valeurs


def construire(donnees: Path, sortie: Path) -> Path:
    paris = _lire(donnees / "paris.json", []) + lire_archives(donnees)     # bilan sur TOUS les paris
    etat = _lire(donnees / "etat.json", {})
    actuelles = [o for o in _lire(donnees / "opportunites_actuelles.json", [])
                 if not o.get("suspect") and o.get("reference") != "Pinnacle brut"]
    ctl = _lire(donnees / "controle.json", {})
    # seulement les groupes mesurés dans les 6 dernières heures (les anciens restent dans controle.json)
    dernier = (etat.get("dernier_cycle") or {}).get("debut") or ""
    try:
        recent = (datetime.fromisoformat(dernier) - timedelta(hours=6)).isoformat()
    except ValueError:
        recent = ""
    groupes = [{k: g.get(k) for k in ("bookmaker", "sport", "marche", "periode", "type", "n", "mediane",
                                      "part_haute", "statut", "exemples", "dispersion", "dispersion_autre_periode")} for g in ctl.get("groupes", {}).values()
               if (g.get("maj") or "") >= recent]
    controle = {"groupes": sorted(groupes, key=lambda g: (-(g["n"] or 0))), "matchs": ctl.get("matchs_suspects", [])}
    # page légère sur mobile : liste limitée aux fiches récentes ; le bilan est calculé sur tous les paris
    liste, fiches_total, valeurs = selection_paris(paris)
    data = {"paris": liste, "fiches_total": fiches_total, "valeurs_filtres": valeurs, "etat": etat, "actuelles": actuelles[:300], "bilan": bilan(paris),
            "bilan_tranches": bilan_tranches(paris), "tranches": [t[2] for t in TRANCHES], "controle": controle,
            "simulations": {k: v["nom"].replace(" %", "\u00a0%").replace("≥ ", "≥\u00a0") for k, v in SIMULATIONS.items()}, "references": REFERENCES}
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
@media (max-width:480px){th,td{padding:8px 4px;font-size:12.5px}td small{font-size:11px}
th:first-child,td:first-child{padding-left:8px}th:last-child,td:last-child{padding-right:8px}}
th{font-size:12px;color:var(--doux);font-weight:600;vertical-align:bottom}
th small{display:block;font-size:11px}
th:first-child,td:first-child{text-align:left}
tr:last-child td{border-bottom:0}
td{vertical-align:top}
td small{display:block;color:var(--doux);font-size:11.5px;white-space:nowrap}
td:first-child small{white-space:normal}
.filtres{display:flex;gap:6px;overflow-x:auto;margin-bottom:10px;scrollbar-width:none}
.sous-titre{font-size:15px;margin:18px 0 8px}
.tableau{overflow-x:auto;border-radius:12px}
tr.total td{border-top:2px solid var(--ligne);background:var(--accent-f)}
select.cumul{display:block;margin-top:4px;padding:3px 4px;font-size:12px;max-width:70px}
td small.roi{font-size:12px;font-weight:700;color:inherit}
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
    <div class="tableau"><table id="bilan"></table></div>
    <p class="aide" style="margin-top:8px">10 € par pari. ROI sur les paris réglés. Simulations = tranches d'écart à la première détection : un pari
    n'appartient qu'à une seule. Total : somme des simulations choisies, chaque pari compté une fois. CLV : écart entre la cote prise et la cote
    juste juste avant le match (positive = on a battu le marché ; c'est l'indicateur le plus rapide à devenir fiable).
    « Pinnacle brut » : témoin, comparé à la cote affichée par Pinnacle sans retirer sa marge (sa CLV est mesurée
    contre la cote juste).</p>
    <h2 class="sous-titre">Par tranche de cote</h2>
    <div class="tableau"><table id="bilan-tranches"></table></div>
    <p class="aide" style="margin-top:8px">Tous les paris (au moins 2 % d'écart, au moins 3 % au-dessus de 10),
    chacun compté une fois, classés selon la cote prise.</p>

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
// bilan : montants compacts (euros entiers, séparateur de milliers ; pourcentages sans décimale au-delà de 100 %)
const eurC = x => x==null ? "—" : (x>0?"+":"") + Math.round(x).toLocaleString("fr-FR") + " €";
const pctC = x => x==null ? "—" : (x>0?"+":"") + (Math.abs(x) >= 1 ? Math.round(100*x).toLocaleString("fr-FR")
  : (100*x).toFixed(1).replace(".", ",")) + " %";
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
// ligne « Total » : cumul des simulations choisies (A, A+B, A+B+C…), par défaut toutes
const SIMS = Object.keys(D.simulations);
const CUMULS = [...SIMS.filter(s => s !== "X").map((s, i, l) => l.slice(0, i + 1)), SIMS];
let cumul = CUMULS.length - 1;
const nomCumul = l => l.length === SIMS.length ? "Toutes" : l.join("+");
function additionner(sims) {
  const t = {paris: 0, regles: 0, en_cours: 0, mises: 0, gains: 0, clv_somme: 0, clv_n: 0, gagnes: 0};
  let vu = false;
  for (const s of sims) {
    const b = D.bilan[s + "|" + refBilan];
    if (!b) continue;
    vu = true;
    for (const k of Object.keys(t)) t[k] += b[k] || 0;
  }
  if (!vu) return null;
  t.roi = t.mises ? t.gains / t.mises : null;
  t.clv_moyenne = t.clv_n ? t.clv_somme / t.clv_n : null;
  return t;
}
function rendreBilan() {
  document.getElementById("puces-ref").innerHTML = ["Toutes", ...D.references].map(r =>
    `<button data-r="${r}" class="${r===refBilan?"actif":""}">${r==="Toutes"?"Toutes réf.":r}</button>`).join("");
  document.querySelectorAll("#puces-ref button").forEach(b => b.onclick = () => { refBilan = b.dataset.r; rendreBilan(); });
  const ligne = (titre, b) => !b ? `<tr><td>${titre}</td><td>0</td><td>—</td><td>—</td></tr>`
    : `<tr><td>${titre}</td><td>${b.regles}${b.regles ? `<small>${b.gagnes} gagné${b.gagnes > 1 ? "s" : ""}</small>` : ""}${b.en_cours ? `<small>${b.en_cours} en cours</small>` : ""}</td>
<td class="${signe(b.gains)}">${eurC(b.gains)}<small class="roi ${signe(b.roi)}">${b.roi==null ? "" : pctC(b.roi)}</small></td>
<td class="${signe(b.clv_moyenne)}">${pctC(b.clv_moyenne)}</td></tr>`;
  document.getElementById("bilan").innerHTML = `<tr><th>Simul.</th><th>Paris</th><th>Gain<small>ROI</small></th><th>CLV</th></tr>` +
    Object.entries(D.simulations).map(([s, nom]) => ligne(`<b>${s}</b> <small>${e(nom)}</small>`, D.bilan[s + "|" + refBilan])).join("") +
    ligne(`<b>Total</b> <select id="cumul" class="cumul">${CUMULS.map((l, i) =>
      `<option value="${i}"${i===cumul?" selected":""}>${nomCumul(l)}</option>`).join("")}</select>`,
      additionner(CUMULS[cumul])).replace("<tr>", '<tr class="total">');
  document.getElementById("cumul").onchange = ev => { cumul = Number(ev.target.value); rendreBilan(); };
  document.getElementById("bilan-tranches").innerHTML = `<tr><th>Cote</th><th>Paris</th><th>Gain<small>ROI</small></th><th>CLV</th></tr>` +
    (D.tranches || []).map(t => ligne(`<b>${e(t)}</b>`, (D.bilan_tranches || {})[t + "|" + refBilan])).join("");
}
rendreBilan();
const mois = new Date().toISOString().slice(0,7);
document.getElementById("infos").innerHTML = [
  ["Cotes françaises lues", (dc.cotes||{}).francaises], ["Matchs comparés", dc.matchs_francais],
  ["Erreurs au dernier passage", dc.opportunites], ["Requêtes PulseScore ce mois", ((D.etat||{}).requetes_par_mois||{})[mois] || 0]
].map(([a,b]) => `<div>${a}<b>${b ?? "—"}</b></div>`).join("");

// --- Paris : fiches déjà regroupées (un même pari pris par plusieurs simulations = une seule fiche)
const fiches = D.paris;
document.getElementById("nb-paris").textContent = fiches.filter(f => f.reference !== "Pinnacle brut").length || "";
const affiches = fiches.filter(f => f.reference !== "Pinnacle brut").length;
if (D.fiches_total > affiches) document.getElementById("paris").insertAdjacentHTML("beforebegin",
  `<p class="aide">${affiches} paris affichés sur ${D.fiches_total} : les 400 derniers en cours, les 600 derniers réglés et
  ceux à régler (le bilan compte tous les paris). Filtre « Statuts » pour ne voir que les gagnés, perdus… ; le témoin
  « Pinnacle brut » s'affiche en le choisissant dans « Références ».</p>`);
const FILTRES = {sim:["sims","Simulations"], ref:["reference","Références"], statut:["statut","Statuts"],
  book:["bookmaker","Bookmakers"], sport:["sport","Sports"]};
for (const [id,[champ,tous]] of Object.entries(FILTRES)) {
  const vals = (D.valeurs_filtres || {})[champ] || [];
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
  // le témoin « Pinnacle brut » n'apparaît que si on le choisit dans « Références »
  const L = fiches.filter(p => (f.reference || p.reference !== "Pinnacle brut") &&
    Object.entries(f).every(([k,v]) => !v || (k==="sims" ? p.sims.includes(v) : p[k]===v)));
  document.getElementById("paris").innerHTML = L.length ? L.slice(0, limite).map(carteParis).join("")
    : `<div class="vide">Aucun pari pour ces filtres.</div>`;
  const plus = document.getElementById("plus");
  plus.style.display = L.length > limite ? "" : "none";
  plus.onclick = () => { limite += 50; rendreParis(); };
}
rendreParis();

// --- À régler
const vus = new Set(), man = D.paris.filter(p => p.a_regler && !vus.has(p.match_id+p.pari) && vus.add(p.match_id+p.pari));
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
<div class="l4"><span>Rapport médian <b>${num(g.mediane)}</b></span><span>au-dessus de 1,12 : ${g.part_haute==null?"—":Math.round(100*g.part_haute)+" %"}</span>
${g.dispersion_autre_periode!=null && g.dispersion_autre_periode < 0.8*g.dispersion ? `<b class="neg">suit mieux l'autre période (temps réglementaire / prolongation)</b>` : ""}</div>
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
