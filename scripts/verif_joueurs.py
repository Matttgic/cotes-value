"""Vérification : les paris joueurs des bookmakers français ont-ils une cote juste chez Pinnacle ?

1. Pinnacle (API publique) : tous les paris joueurs ouverts (« Player Props », plus/moins), par sport,
   ligue et statistique, avec leur probabilité juste (marge retirée).
2. PulseScore : les marchés joueurs de Winamax, Betclic, Unibet et PMU (1re page de 30 matchs) en foot,
   hockey, basket, foot US et baseball.
3. Association : même sport, coup d'envoi à ± 10 min, même joueur (nom sans accents), même seuil
   (« N buts ou plus » chez le bookmaker = « plus de N - 0,5 » chez Pinnacle). Écart = cote × proba juste − 1.

Lecture seule, rien n'est parié ni enregistré ailleurs que dans verif/. Environ 20 requêtes PulseScore.
Sortie : verif/rapport.json et verif/rapport.md.
Usage : PULSESCORE_KEY=... python scripts/verif_joueurs.py
"""
from __future__ import annotations

import collections
import json
import math
import os
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cotes import pinnacle  # noqa: E402

PS = "https://api.pulsescore.net/api"
BOOKMAKERS = ["winamax", "betclic", "unibet-fr", "pmu"]
SPORTS_PS = {"soccer": "football", "ice-hockey": "hockey", "basketball": "basket",
             "american-football": "football_americain", "baseball": "baseball"}
SPORTS_PIN = {29: "football", 19: "hockey", 4: "basket", 15: "football_americain", 3: "baseball"}
SEUIL_PAR_DEFAUT = {"ANYTIME_GOALSCORER": 1, "PLAYER_TO_SCORE_2_PLUS": 2, "PLAYER_HATTRICK": 3,
                    "PLAYER_TO_ASSIST": 1}
OUT = Path("verif")


def norm(s: str | None) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z ]", " ", s).split())


def cles_nom(nom: str) -> set[str]:
    """« Connor McDavid » -> {"connor mcdavid", "c mcdavid"} ; « McDavid, Connor » aussi."""
    n = nom.strip()
    if "," in n:
        a, b = n.split(",", 1)
        n = f"{b} {a}"
    mots = norm(n).split()
    if not mots:
        return set()
    return {" ".join(mots), f"{mots[0][0]} {' '.join(mots[1:])}" if len(mots) > 1 else mots[0]}


def heure(s: str | None) -> float | None:
    try:
        return datetime.fromisoformat((s or "").replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


# --------------------------------------------------------------------------- Pinnacle

def pinnacle_joueurs() -> list[dict]:
    lignes = [l for l in pinnacle.collecter(SPORTS_PIN) if l["marche"].startswith("JOUEUR:")]
    for l in lignes:
        l["stat"] = l["marche"][7:]
        l["cles"] = cles_nom(l["joueur"])
    return lignes


# --------------------------------------------------------------------------- bookmakers français

def stat_fr(canon: str, libelle: str) -> str | None:
    c, l = canon or "", (libelle or "").lower()
    if "GOALSCORER" in c or "SCORE_2_PLUS" in c or "HATTRICK" in c:
        return None if ("FIRST" in c or "LAST" in c) else "Goals"
    if c in ("PLAYER_TO_ASSIST", "PLAYER_ASSISTS") or "passe" in l or "assist" in l:
        return "Assists"
    if c == "PLAYER_POINTS" or "point" in l:
        return "Points"
    if c == "PLAYER_REBOUNDS" or "rebond" in l or "rebound" in l:
        return "Rebounds"
    if c == "PLAYER_THREES_MADE" or "three" in l or "3 points" in l:
        return "3 Point FG"
    return None


def francais_joueurs(session: requests.Session, rapport: dict) -> list[dict]:
    out = []
    for bm in BOOKMAKERS:
        for sp_ps, sp in SPORTS_PS.items():
            time.sleep(1.2)
            try:
                r = session.get(f"{PS}/{bm}/{sp_ps}/events", params={"page": 1, "limit": 30}, timeout=60)
                d = r.json() if r.status_code == 200 else None
            except (requests.RequestException, ValueError):
                d = None
            rapport["requetes_pulsescore"] += 1
            if not isinstance(d, dict):
                rapport["erreurs"].append(f"{bm}/{sp_ps} : {getattr(r, 'status_code', '?')}")
                continue
            for e in d.get("events") or []:
                for m in e.get("markets") or []:
                    canon, lib = m.get("canonicalMarket") or "", m.get("rawName") or ""
                    joueur_marche = (m.get("moreInfo") or {}).get("player")
                    if not ("PLAYER" in canon or "GOALSCORER" in canon or joueur_marche
                            or re.search(r"joueur|player", lib, re.I)):
                        continue
                    if m.get("period") not in (None, "FULL_TIME"):
                        continue
                    for s in m.get("selections") or []:
                        nom = (s.get("moreInfo") or {}).get("participant") or joueur_marche or s.get("rawName") or ""
                        seuil = s.get("line") or m.get("line")
                        g = re.search(r"\s(\d+)\+\s*$", nom)
                        if g:
                            seuil, nom = int(g.group(1)), nom[:g.start()]
                        if seuil is None:
                            g = re.search(r"(\d+)\s*(?:\+|ou plus|or more)", lib)
                            seuil = int(g.group(1)) if g else SEUIL_PAR_DEFAUT.get(canon)
                        if norm(nom) in ("yes", "no", "oui", "non", ""):
                            continue
                        out.append({"bookmaker": bm, "sport": sp, "match": f"{e.get('home')} - {e.get('away')}",
                                    "debut": e.get("startTime"), "marche": canon, "libelle": lib,
                                    "stat": stat_fr(canon, lib), "joueur": nom.strip(), "seuil": seuil,
                                    "cote": s.get("odds"), "cles": cles_nom(nom)})
    return out


# --------------------------------------------------------------------------- association

def associer(fr: list[dict], pin: list[dict]) -> list[dict]:
    index = collections.defaultdict(list)
    for p in pin:
        if p["issue"] == "PLUS" and p.get("proba_juste") and p.get("ligne") is not None:
            for k in p["cles"]:
                index[(p["sport"], p["stat"], k)].append(p)
    paires = []
    for f in fr:
        if not f["stat"] or not f["seuil"] or not f["cote"]:
            continue
        t = heure(f["debut"])
        for k in f["cles"]:
            trouve = None
            for p in index.get((f["sport"], f["stat"], k), []):
                tp = heure(p["debut"])
                if t and tp and abs(t - tp) <= 600 and math.ceil(float(p["ligne"])) == int(f["seuil"]):
                    trouve = p
                    break
            if trouve:
                paires.append({"bookmaker": f["bookmaker"], "sport": f["sport"], "match": f["match"],
                               "joueur": f["joueur"], "stat": f["stat"], "seuil": f["seuil"],
                               "libelle_fr": f["libelle"], "cote_fr": f["cote"],
                               "ligne_pinnacle": trouve["ligne"], "cote_juste": trouve["cote_juste"],
                               "marge_pinnacle": trouve["marge_pinnacle"], "mise_max_pinnacle": trouve.get("mise_max"),
                               "ecart": round(f["cote"] * trouve["proba_juste"] - 1, 4)})
                break
    return paires


# --------------------------------------------------------------------------- rapport

def main() -> int:
    key = os.environ.get("PULSESCORE_KEY", "").strip()
    if not key:
        print("PULSESCORE_KEY manquante", file=sys.stderr)
        return 1
    OUT.mkdir(exist_ok=True)
    rapport = {"date_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "requetes_pulsescore": 0, "erreurs": []}

    pin = pinnacle_joueurs()
    s = requests.Session()
    s.headers.update({"X-Secret": key, "Accept-Encoding": "gzip", "Accept": "application/json"})
    fr = francais_joueurs(s, rapport)
    paires = associer(fr, pin)

    pin_stats = collections.Counter((p["sport"], p["stat"]) for p in pin if p["issue"] == "PLUS")
    pin_ligues = collections.Counter((p["sport"], p.get("ligue")) for p in pin if p["issue"] == "PLUS")
    fr_stats = collections.Counter((f["bookmaker"], f["sport"], f["stat"] or f"? {f['marche']}") for f in fr)
    par_bm = collections.Counter((p["bookmaker"], p["sport"], p["stat"]) for p in paires)
    rapport.update({
        "pinnacle_joueurs_par_sport_stat": {f"{a} / {b}": n for (a, b), n in pin_stats.most_common()},
        "pinnacle_joueurs_par_ligue": {f"{a} / {b}": n for (a, b), n in pin_ligues.most_common(25)},
        "pinnacle_exemples": [{k: p.get(k) for k in ("sport", "ligue", "joueur", "stat", "ligne", "issue", "cote",
                                                       "cote_juste", "mise_max", "debut")} for p in pin[:10]],
        "francais_par_bookmaker_sport_stat": {" / ".join(map(str, k)): n for k, n in fr_stats.most_common()},
        "associes_par_bookmaker_sport_stat": {" / ".join(map(str, k)): n for k, n in par_bm.most_common()},
        "nb_associes": len(paires),
        "ecarts_positifs": sum(p["ecart"] > 0 for p in paires),
        "ecarts_3pc_ou_plus": sum(p["ecart"] >= 0.03 for p in paires),
        "meilleurs_ecarts": sorted(paires, key=lambda p: -p["ecart"])[:25],
        "exemples_associes": paires[:15],
    })
    (OUT / "rapport.json").write_text(json.dumps(rapport, ensure_ascii=False, indent=1, default=list),
                                      encoding="utf-8")

    md = [f"# Paris joueurs : Pinnacle face aux bookmakers français ({rapport['date_utc']})", "",
          f"Requêtes PulseScore : {rapport['requetes_pulsescore']}. Erreurs : {rapport['erreurs'] or 'aucune'}.", "",
          "## Pinnacle : paris joueurs ouverts (issue « plus »)", ""]
    md += [f"- {k} : {n}" for k, n in rapport["pinnacle_joueurs_par_sport_stat"].items()] or ["- aucun"]
    md += ["", "## Bookmakers français : sélections joueurs lues (1re page)", ""]
    md += [f"- {k} : {n}" for k, n in rapport["francais_par_bookmaker_sport_stat"].items()] or ["- aucune"]
    md += ["", f"## Associés à Pinnacle : {len(paires)} (écart > 0 : {rapport['ecarts_positifs']}, "
               f"≥ 3 % : {rapport['ecarts_3pc_ou_plus']})", ""]
    md += [f"- {k} : {n}" for k, n in rapport["associes_par_bookmaker_sport_stat"].items()] or ["- aucun"]
    md += ["", "## Meilleurs écarts", "", "| Bookmaker | Match | Joueur | Pari | Cote | Cote juste | Écart |",
           "|---|---|---|---|---|---|---|"]
    md += [f"| {p['bookmaker']} | {p['match']} | {p['joueur']} | {p['stat']} {p['seuil']}+ | {p['cote_fr']} | "
           f"{p['cote_juste']} | {p['ecart']:+.1%} |" for p in rapport["meilleurs_ecarts"]]
    (OUT / "rapport.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    sys.exit(main())
