"""Registre du protocole de validation (docs/protocole.md) : gel, inscription, vérification, tableaux.

Usage :
  python scripts/protocole.py --verifier                    empreintes du code contre le registre (code 1 si écart)
  python scripts/protocole.py --tableau [--donnees CHEMIN]  tableau Markdown du registre (docs/protocole.md)
  python scripts/protocole.py --etat --donnees CHEMIN       état du suivi sur ces données, sans rien écrire
  python scripts/protocole.py --simuler --donnees CHEMIN    taux de faux succès et puissance du test (numpy, 40 secondes)
  python scripts/protocole.py --inscrire CLE --donnees CHEMIN [--debut ISO]
                                                            ajoute une stratégie, ou la nouvelle version d'une
                                                            stratégie dont les règles ont changé (nouveau protocole)
  python scripts/protocole.py --geler --donnees CHEMIN      premier gel : témoin et registre (refusé s'ils existent)

CHEMIN = branche « donnees » extraite (scripts/cloner_donnees.sh). Le registre ne se modifie pas : il s'allonge.
tests/test_protocole.py vérifie le scellé de chaque état passé du registre.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cotes import pauses, protocole, stockage  # noqa: E402
from cotes.reglement import GAIN  # noqa: E402
from cotes.simulation import COTE_MAX_PRISE  # noqa: E402
from cotes.strategie_recommandee import charger_fusions  # noqa: E402

REGLES = {
    "version": 1,
    "debut": "2026-11-16T00:00:00+01:00",   # seuls les paris détectés à partir de cet instant comptent
    "duree_jours": 365,                      # échéance de chaque protocole, depuis son début
    "places": 200,                           # nombre maximal de protocoles ; le seuil d'un test en découle
    "alpha_famille": 0.05,                   # risque d'au moins un faux succès sur toutes les places
    "puissance": 0.80,
    "effet": 0.02,                           # CLV Pinnacle que le nombre de paris permet de prouver
    "part_mi_parcours": 0.5,                 # lecture intermédiaire : échec anticipé seulement
    "couverture_min": 0.5,                   # part des paris réglés dont la clôture Pinnacle est connue
    "alpha_roi": 0.025,                      # rendement nettement sous la CLV : échec
    "matchs_min": 50,                        # matchs différents à la lecture finale
    "cote_max": COTE_MAX_PRISE,
    "n_min": 300,
    "sigma_defaut": 0.12,                    # écart-type par pari quand l'historique compte trop peu de mesures
    "sigma_mesures_min": 50,
}


def charger(donnees: Path) -> list[dict]:
    charger_fusions(donnees)
    pauses.charger(donnees)
    return stockage.fusionner_paris(stockage.lire_archives(donnees), json.loads((donnees / "paris.json").read_text()))


def ecrire_temoin(paris: list[dict]) -> str:
    temoin = [{k: v for k, v in p.items() if k not in protocole.CHAMPS_HORS_TEMOIN} for p in paris]
    # Les champs retirés ne changent aucune sélection : sinon le témoin ne représenterait pas les règles.
    complet = [{k: v for k, v in p.items() if k != "selections_figees"} for p in paris]
    def prises(lignes):
        return {cle: sorted(p["id"] for p in lignes if id(p) in ids)
                for cle, ids in protocole.selections_officielles(lignes).items()}
    if prises(temoin) != prises(complet):
        raise SystemExit("Un champ retiré du témoin change une sélection : témoin refusé.")
    brut = gzip.compress(json.dumps(temoin, ensure_ascii=False, separators=(",", ":")).encode(), 9, mtime=0)
    protocole.TEMOIN.write_bytes(brut)
    return hashlib.sha256(brut).hexdigest()


def sigmas(paris: list[dict]) -> dict[str, tuple[float | None, int]]:
    """Écart-type par pari de la CLV Pinnacle de chaque stratégie (grappes de matchs comprises) et nombre de mesures,
    sur ses paris réglés des bilans (cote ≤ plafond)."""
    from cotes.evenements import identites
    paris = [p for p in paris if (p.get("cote") or 0) <= COTE_MAX_PRISE]
    liens, clvs = identites(paris), protocole.clv_pinnacle(paris)
    out = {}
    for cle, ids in protocole.selections_officielles(paris).items():
        mesures = [p for p in paris if id(p) in ids and p.get("statut") in GAIN and id(p) in clvs]
        s = protocole.moyenne_par_match([clvs[id(p)] for p in mesures], [liens[id(p)] for p in mesures]) if mesures else {}
        et = s.get("erreur_type")
        out[cle] = (et * math.sqrt(len(mesures)) if et else None, len(mesures))
    return out


def inscription(cle: str, definition: dict, sigma: tuple, empreinte: str, regles: dict, debut: str | None) -> dict:
    mesure, n = sigma
    retenu = mesure if mesure and n >= regles["sigma_mesures_min"] else regles["sigma_defaut"]
    lancement = max(str(definition.get("debut") or regles["debut"]), debut or regles["debut"],
                    key=lambda t: datetime.fromisoformat(t))
    return {"cle": cle, "ligne": definition["ligne"], "nom": definition.get("nom") or definition["ligne"],
            "version": str(definition.get("version") or "1"), "debut": lancement,
            "sigma": round(retenu, 4), "sigma_mesures": n if retenu == mesure else 0,
            "n": protocole.taille(round(retenu, 4), regles), "empreinte": empreinte}


def geler(donnees: Path) -> None:
    if protocole.REGISTRE.exists() or protocole.TEMOIN.exists():
        raise SystemExit("Le registre ou le témoin existe déjà : le protocole ne se gèle qu'une fois (--inscrire ensuite).")
    paris = charger(donnees)
    sha = ecrire_temoin(paris)
    temoin, _ = protocole.lire_temoin()
    regles = {**REGLES, "temoin_sha256": sha, "temoin_paris": len(temoin),
              "temoin_jusqua": max(p["detecte"] for p in temoin)}
    empreintes, s, definitions = protocole.empreintes(temoin), sigmas(paris), protocole.definitions()
    doc = {"regles": regles, "inscrites": [inscription(cle, d, s[cle], empreintes[cle], regles, None)
                                           for cle, d in definitions.items()]}
    ecrire(doc)
    print(f"{len(doc['inscrites'])} stratégies inscrites, scellé {protocole.scelle(doc)}")


def ecrire(doc: dict) -> None:
    protocole.REGISTRE.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def inscrire(cle: str, donnees: Path, debut: str | None) -> None:
    doc = protocole.registre()
    regles, definitions = doc["regles"], protocole.definitions()
    if cle not in definitions:
        raise SystemExit(f"Stratégie inconnue ou inactive : {cle}")
    if len(doc["inscrites"]) >= regles["places"]:
        raise SystemExit("Toutes les places du protocole sont prises : aucune nouvelle inscription.")
    paris = charger(donnees)
    empreinte = protocole.empreintes(protocole.lire_temoin()[0])[cle]
    nouvelle = inscription(cle, protocole.definitions()[cle], sigmas(paris)[cle], empreinte, regles,
                           debut or datetime.now(timezone.utc).isoformat(timespec="seconds"))
    anciennes = [e for e in doc["inscrites"] if e["cle"] == cle]
    if any(e["version"] == nouvelle["version"] for e in anciennes):
        raise SystemExit(f"{cle} est déjà inscrite en version {nouvelle['version']} : changer sa version d'abord.")
    doc["inscrites"].append(nouvelle)
    ecrire(doc)
    print(f"{cle} inscrite ({nouvelle['n']} paris mesurés à atteindre). Nouveau scellé à ajouter dans "
          f"tests/test_protocole.py : ({len(doc['inscrites'])}, \"{protocole.scelle(doc)}\")")


def verifier() -> int:
    doc = protocole.registre()
    actuelles = protocole.empreintes_actuelles(doc)
    if actuelles is None:
        print("Témoin absent ou différent de celui du registre.")
        return 1
    dernieres = {e["cle"]: e for e in doc["inscrites"]}
    ecarts = [e for e in dernieres.values() if actuelles.get(e["cle"]) != e["empreinte"]]
    for e in ecarts:
        print(f"Règles modifiées : {e['cle']} ({e['nom']}) — registre {e['empreinte']}, code {actuelles.get(e['cle'])}")
    hors = sorted(set(protocole.definitions()) - set(dernieres))
    if hors:
        print("Hors protocole (non inscrites) :", ", ".join(hors))
    print(f"{len(dernieres) - len(ecarts)} stratégies conformes sur {len(dernieres)}, scellé {protocole.scelle(doc)}")
    return 1 if ecarts else 0


def fr(x: float, d: int = 1) -> str:
    return f"{x:.{d}f}".replace(".", ",")


def rythmes(donnees: Path, jusqua: str, jours: int = 14) -> dict[str, tuple[float, float | None]]:
    """Par stratégie : paris mesurés par jour sur les ``jours`` derniers jours avant ``jusqua`` (ou depuis son premier
    pari, si elle est plus récente) et part des paris réglés dont la clôture Pinnacle est connue."""
    from datetime import timedelta
    paris = [p for p in charger(donnees) if (p.get("cote") or 0) <= COTE_MAX_PRISE and p["detecte"] <= jusqua]
    clvs, fin = protocole.clv_pinnacle(paris), datetime.fromisoformat(jusqua)
    out = {}
    for cle, ids in protocole.selections_officielles(paris).items():
        siens = [p for p in paris if id(p) in ids]
        if not siens:
            out[cle] = (0.0, None)
            continue
        debut = max(fin - timedelta(days=jours), min(datetime.fromisoformat(p["detecte"]) for p in siens))
        recents = [p for p in siens if datetime.fromisoformat(p["detecte"]) >= debut and p.get("statut") in GAIN]
        duree = max((fin - debut).total_seconds() / 86400, 1.0)
        mesures = sum(id(p) in clvs for p in recents)
        out[cle] = (mesures / duree, mesures / len(recents) if recents else None)
    return out


def tableau(donnees: Path | None = None) -> str:
    """Registre en Markdown. Avec ``donnees`` : rythme observé avant le gel et durée attendue à ce rythme."""
    doc = protocole.registre()
    r = doc["regles"]
    rythme = rythmes(donnees, r["temoin_jusqua"]) if donnees else {}
    out = ["| Stratégie | Version | Écart-type par pari | Paris mesurés à atteindre | Mi-parcours "
           + ("| Mesurés par jour | Clôture Pinnacle connue | Durée à ce rythme " if rythme else "") + "| Empreinte des règles |",
           "|---|---|---|---|---|" + ("---|---|---|" if rythme else "") + "---|"]
    for e in doc["inscrites"]:
        source = f"{fr(100 * e['sigma'])} %" + ("" if e["sigma_mesures"] else " (par défaut)")
        plus = ""
        if rythme:
            par_jour, part = rythme.get(e["cle"], (0.0, None))
            jours = e["n"] / par_jour if par_jour else None
            duree = "—" if jours is None else f"{round(jours)} jours" if jours <= r["duree_jours"] else "**plus d'un an**"
            plus = f"| {fr(par_jour)} | {'—' if part is None else fr(100 * part, 0) + ' %'} | {duree} "
        out.append(f"| {e['nom']} | {e['version']} | {source} | {e['n']} "
                   f"| {math.ceil(e['n'] * r['part_mi_parcours'])} {plus}| `{e['empreinte']}` |")
    return "\n".join(out)


def simuler(donnees: Path, tirages: int = 200_000, graine: int = 20261115, mesures_min: int = 100) -> str:
    """Le test tient-il son seuil ? Pour chaque stratégie d'au moins ``mesures_min`` CLV Pinnacle avant le gel, des
    échantillons de la taille de son protocole sont tirés par matchs entiers dans ses propres CLV, recentrées sur zéro
    (aucun avantage) puis sur ``effet`` (l'avantage visé). Rend le taux de faux succès et la puissance. Demande numpy."""
    import numpy as np
    from cotes.evenements import identites
    doc = protocole.registre()
    r = doc["regles"]
    seuil = protocole.alpha(r)
    paris = [p for p in charger(donnees) if (p.get("cote") or 0) <= COTE_MAX_PRISE and p["detecte"] <= r["temoin_jusqua"]]
    liens, clvs, prises = identites(paris), protocole.clv_pinnacle(paris), protocole.selections_officielles(paris)
    rng = np.random.default_rng(graine)
    out = ["| Stratégie | CLV mesurées (matchs) | Paris du protocole | Faux succès sans avantage | Succès si la CLV vaut "
           f"{fr(100 * r['effet'], 0)} % |", "|---|---|---|---|---|"]
    faux, puissances = [], []
    for e in doc["inscrites"]:
        siens = [p for p in paris if id(p) in prises.get(e["cle"], ()) and id(p) in clvs]
        if len(siens) < mesures_min:
            continue
        rang: dict = {}
        idx = np.fromiter((rang.setdefault(liens[id(p)], len(rang)) for p in siens), dtype=np.int64, count=len(siens))
        v = np.array([clvs[id(p)] for p in siens])
        somme, compte = np.bincount(idx, weights=v), np.bincount(idx).astype(float)
        somme = somme - v.mean() * compte                       # hypothèse nulle : CLV moyenne nulle
        k = max(2, round(e["n"] * len(rang) / len(siens)))      # matchs tirés pour obtenir environ n paris
        bas, haut = 0.0, 60.0                                   # valeur critique de Student à k − 1 degrés de liberté
        for _ in range(60):
            milieu = (bas + haut) / 2
            bas, haut = (milieu, haut) if protocole.p_student(milieu, k - 1) > seuil else (bas, milieu)
        nul = vrai = fait = 0
        while fait < tirages:
            lot = min(max(1, 4_000_000 // k), tirages - fait)
            tire = rng.integers(0, len(rang), (lot, k))
            s, c = somme[tire], compte[tire]
            n = c.sum(1)
            m = s.sum(1) / n
            et = np.sqrt(((s - m[:, None] * c) ** 2).sum(1) * k / (k - 1)) / n
            nul += int((m / et > haut).sum())
            vrai += int(((m + r["effet"]) / et > haut).sum())
            fait += lot
        faux.append(nul / tirages)
        puissances.append(vrai / tirages)
        out.append(f"| {e['nom']} | {len(siens)} ({len(rang)}) | {e['n']} | {fr(100 * nul / tirages, 3)} % | {fr(100 * vrai / tirages, 0)} % |")
    out += ["", f"{len(faux)} stratégies, {tirages} tirages chacune, graine {graine}. Seuil visé : {fr(100 * seuil, 3)} %. "
                f"Faux succès : de {fr(100 * min(faux), 3)} % à {fr(100 * max(faux), 3)} %, médiane "
                f"{fr(100 * sorted(faux)[len(faux) // 2], 3)} %. Puissance : de {fr(100 * min(puissances), 0)} % à "
                f"{fr(100 * max(puissances), 0)} %, médiane {fr(100 * sorted(puissances)[len(puissances) // 2], 0)} %."]
    return "\n".join(out)


def etat(donnees: Path) -> str:
    paris = [p for p in charger(donnees) if (p.get("cote") or 0) <= COTE_MAX_PRISE]
    suivi = protocole.suivre(paris, protocole.selections_officielles(paris), donnees, datetime.now(timezone.utc),
                             protocole.empreintes_actuelles(), ecrire=False)
    out = [json.dumps(suivi["regles"], ensure_ascii=False), json.dumps(suivi["resume"], ensure_ascii=False)]
    for l in suivi["lignes"].values():
        out.append(f"{l['nom'][:44]:44} {l['statut']:9} {l.get('mesures', 0):5}/{l.get('n', 0):5} mesurés, "
                   f"{l.get('regles', 0):5} réglés, fin estimée {l.get('fin_estimee') or '—'} {l.get('motif') or ''}")
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--donnees", type=Path)
    ap.add_argument("--geler", action="store_true")
    ap.add_argument("--inscrire", metavar="CLE")
    ap.add_argument("--debut", help="début du protocole de la stratégie inscrite (ISO, avec fuseau) ; défaut : maintenant")
    ap.add_argument("--verifier", action="store_true")
    ap.add_argument("--tableau", action="store_true")
    ap.add_argument("--etat", action="store_true")
    ap.add_argument("--simuler", action="store_true")
    a = ap.parse_args()
    if (a.geler or a.inscrire or a.etat or a.simuler) and not a.donnees:
        ap.error("--donnees est requis")
    if a.geler:
        geler(a.donnees)
    elif a.inscrire:
        inscrire(a.inscrire, a.donnees, a.debut)
    elif a.tableau:
        print(tableau(a.donnees))
    elif a.etat:
        print(etat(a.donnees))
    elif a.simuler:
        print(simuler(a.donnees))
    else:
        raise SystemExit(verifier())


if __name__ == "__main__":
    main()
