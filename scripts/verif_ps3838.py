"""Vérification : nos cotes Pinnacle (API publique, lecture directe) = cotes PS3838 (via PulseScore) ?

Les deux sources sont lues dans la même minute. Les matchs sont associés par heure de début
(± 5 min) et ressemblance des noms d'équipes, puis on compare chaque cote des marchés communs :
résultat / vainqueur, handicap, total (match et 1re mi-temps ou 1er set).

Sortie : verif/rapport.json et verif/rapport.md. Environ 6 requêtes PulseScore.
Usage : PULSESCORE_KEY=... python scripts/verif_ps3838.py
"""
from __future__ import annotations

import difflib
import json
import os
import statistics
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cotes import pinnacle  # noqa: E402

PS = "https://api.pulsescore.net/api/ps3838"
PAGES = {"soccer": 3, "basketball": 1, "tennis": 2}
SPORT_PIN = {"soccer": (29, "football"), "basketball": (4, "basket"), "tennis": (33, "tennis")}
PERIODES = {"soccer": {"FULL_TIME": "MATCH", "FIRST_HALF": "MT1"},
            "basketball": {"FULL_TIME": "MATCH", "FIRST_HALF": "MT1"},
            "tennis": {"FULL_TIME": "MATCH", "FIRST_HALF": "SET1"}}
MARCHES = {"soccer": {"MATCH_RESULT": "RESULTAT_1N2", "ASIAN_HANDICAP": "HANDICAP", "OVER_UNDER": "TOTAL"},
           "basketball": {"MATCH_RESULT": "VAINQUEUR", "ASIAN_HANDICAP": "HANDICAP", "OVER_UNDER": "TOTAL"},
           "tennis": {"MATCH_RESULT": "VAINQUEUR", "GAME_HANDICAP": "JEUX_HANDICAP", "TOTAL_GAMES": "JEUX_TOTAL"}}
ISSUES = {"HOME": "DOM", "AWAY": "EXT", "DRAW": "NUL", "OVER": "PLUS", "UNDER": "MOINS"}
OUT = Path("verif")


def norm(s: str | None) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return " ".join(s.replace("-", " ").replace(".", " ").split())


def ressemblance(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio()


def heure(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def main() -> int:
    key = os.environ.get("PULSESCORE_KEY", "").strip()
    if not key:
        print("PULSESCORE_KEY manquante", file=sys.stderr)
        return 1
    OUT.mkdir(exist_ok=True)
    session = requests.Session()
    session.headers.update({"X-Secret": key, "Accept-Encoding": "gzip"})
    comparaisons, sports_rapport = [], {}

    for sport, n_pages in PAGES.items():
        sid, nom_pin = SPORT_PIN[sport]
        t_pin = datetime.now(timezone.utc)
        pin = [l for l in pinnacle.collecter({sid: nom_pin}) if l["periode"] in PERIODES[sport].values()]
        evs = []
        for page in range(1, n_pages + 1):
            r = session.get(f"{PS}/{sport}/events", params={"page": page, "limit": 30}, timeout=60)
            time.sleep(1.2)
            if r.status_code != 200:
                print(sport, page, r.status_code, r.text[:200])
                break
            evs += r.json().get("events", [])
        t_ps = datetime.now(timezone.utc)

        # index Pinnacle : (match_id) -> lignes ; matchs candidats par heure
        par_match: dict[int, list[dict]] = {}
        for l in pin:
            par_match.setdefault(l["match_id"], []).append(l)
        infos = {mid: ls[0] for mid, ls in par_match.items()}
        associes = 0
        for ev in evs:
            if ev.get("live"):
                continue
            debut = heure(ev.get("startTime"))
            meilleur, score = None, 0.0
            for mid, l in infos.items():
                d = heure(l["debut"])
                if not d or not debut or abs((d - debut).total_seconds()) > 300:
                    continue
                s = min(ressemblance(ev["home"], l["domicile"]), ressemblance(ev["away"], l["exterieur"]))
                if s > score:
                    meilleur, score = mid, s
            if meilleur is None or score < 0.6:
                continue
            associes += 1
            index = {(l["marche"], l["periode"], l["ligne"], l["issue"]): l for l in par_match[meilleur]}
            for m in ev.get("markets") or []:
                marche = MARCHES[sport].get(m.get("canonicalMarket"))
                periode = PERIODES[sport].get(m.get("period"))
                if not marche or not periode:
                    continue
                for s in m.get("selections") or []:
                    issue = ISSUES.get(s.get("canonicalOutcome"))
                    ligne = s.get("line")
                    if marche.endswith("HANDICAP") and issue == "EXT" and ligne is not None:
                        ligne = -ligne                     # notre ligne = handicap du domicile
                    if marche in ("RESULTAT_1N2", "VAINQUEUR"):
                        ligne = None
                    l = index.get((marche, periode, float(ligne) if ligne is not None else None, issue))
                    if l is None or not s.get("odds"):
                        continue
                    comparaisons.append({
                        "sport": sport, "ligue": ev.get("league"), "match": f'{ev["home"]} - {ev["away"]}',
                        "match_pinnacle": f'{l["domicile"]} - {l["exterieur"]}', "debut": ev.get("startTime"),
                        "marche": marche, "periode": periode, "ligne": ligne, "issue": issue,
                        "pinnacle": l["cote"], "ps3838": float(s["odds"]),
                        "ecart_pct": round(100 * (float(s["odds"]) / l["cote"] - 1), 3),
                        "maj_ps3838": ev.get("updatedAt")})
        sports_rapport[sport] = {"matchs_ps3838": len(evs), "matchs_pinnacle": len(infos), "associes": associes,
                                 "lecture_pinnacle": t_pin.isoformat(timespec="seconds"),
                                 "lecture_ps3838": t_ps.isoformat(timespec="seconds")}

    ecarts = [abs(c["ecart_pct"]) for c in comparaisons]
    resume = {
        "cotes_comparees": len(comparaisons),
        "identiques": sum(e < 0.3 for e in ecarts),
        "ecart_moins_de_1pct": sum(e < 1 for e in ecarts),
        "ecart_median_pct": round(statistics.median(ecarts), 3) if ecarts else None,
        "ecart_moyen_pct": round(statistics.mean(ecarts), 3) if ecarts else None,
    }
    rapport = {"date_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "resume": resume,
               "sports": sports_rapport,
               "plus_gros_ecarts": sorted(comparaisons, key=lambda c: -abs(c["ecart_pct"]))[:25],
               "exemples": comparaisons[:40]}
    (OUT / "rapport.json").write_text(json.dumps(rapport, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"resume": resume, "sports": sports_rapport}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
