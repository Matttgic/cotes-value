"""Diagnostic en lecture seule : pourquoi les matchs de donnees/resultats_a_saisir.json ne trouvent aucun résultat.

Pour chaque match en attente, lit les sources (ESPN, LiveScore, Flashscore, Sofascore, TheSportsDB) autour de
la date du match et affiche les 3 candidats les plus proches (noms, écart d'heure, score) par source, ou « rien ».
Affiche aussi quels identifiants de sport Flashscore existent. N'écrit aucun fichier de données.

Usage : python scripts/diagnostic_sources.py --donnees donnees
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cotes import flashscore, livescore, resultats  # noqa: E402
from cotes.correspondance import ressemblance  # noqa: E402

SOFASCORE = "https://api.sofascore.com/api/v1/sport/{slug}/scheduled-events/{jour}"
SOFA_SLUGS = {"basket": "basketball", "rugby": "rugby", "hockey": "ice-hockey", "volley": "volleyball",
              "tennis": "tennis", "snooker": "snooker", "football": "football", "handball": "handball"}
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
      "Accept": "application/json"}


def sofascore(sport: str, jour: str) -> tuple[list[dict], str]:
    slug = SOFA_SLUGS.get(sport)
    if not slug:
        return [], "sport non prévu"
    try:
        r = requests.get(SOFASCORE.format(slug=slug, jour=jour), headers=UA, timeout=30)
    except requests.RequestException as e:
        return [], f"erreur {repr(e)[:80]}"
    if not r.ok:
        return [], f"HTTP {r.status_code}"
    out = []
    for e in (r.json().get("events") or []):
        if (e.get("status") or {}).get("type") != "finished":
            continue
        h, a = (e.get("homeScore") or {}).get("current"), (e.get("awayScore") or {}).get("current")
        if h is None or a is None:
            continue
        out.append({"source": "sofascore", "sport": sport, "domicile": (e.get("homeTeam") or {}).get("name"),
                    "exterieur": (e.get("awayTeam") or {}).get("name"),
                    "debut": datetime.fromtimestamp(e["startTimestamp"], timezone.utc), "score": (h, a)})
    return out, f"HTTP 200, {len(out)} terminés"


def thesportsdb(sport: str, dom: str, ext: str) -> list[dict]:
    try:
        r = requests.get("https://www.thesportsdb.com/api/v1/json/123/searchevents.php",
                         params={"e": f"{dom}_vs_{ext}".replace(" ", "_")}, timeout=30)
        evs = (r.json() or {}).get("event") or []
    except (requests.RequestException, ValueError):
        return []
    return [{"source": "thesportsdb", "sport": sport, "domicile": e.get("strHomeTeam"), "exterieur": e.get("strAwayTeam"),
             "debut": resultats._heure((e.get("strTimestamp") or "") + "+00:00"),
             "score": (e.get("intHomeScore"), e.get("intAwayScore")), "statut": e.get("strStatus")} for e in evs]


def proches(m: dict, enregistrements: list[dict], n: int = 3) -> list[str]:
    dom, ext = (x.strip() for x in m["match"].split(" – ", 1))
    debut = resultats._heure(m["debut"])
    notes = []
    for r in enregistrements:
        if r.get("debut") is None or not r.get("domicile") or not r.get("exterieur"):
            continue
        ecart = (r["debut"] - debut).total_seconds() / 3600
        if abs(ecart) > 14:
            continue
        direct = min(ressemblance(dom, r["domicile"]), ressemblance(ext, r["exterieur"]))
        inverse = min(ressemblance(dom, r["exterieur"]), ressemblance(ext, r["domicile"]))
        notes.append((max(direct, inverse), ecart, r))
    notes.sort(key=lambda t: -t[0])
    return [f"    {r['source']:11} {s:.2f}  {r['domicile']} – {r['exterieur']}  ({ecart:+.1f} h)  {r.get('score')} {r.get('statut', '')}"
            for s, ecart, r in notes[:n]]


def sports_flashscore() -> None:
    print("\n== Flashscore : identifiants de sport (aujourd'hui) ==")
    for i in range(1, 41):
        try:
            r = requests.get(f"{flashscore.BASE}/f_{i}_0_0_fr-fr_1", headers=flashscore.ENTETES, timeout=30)
        except requests.RequestException as e:
            print(i, "erreur", repr(e)[:60])
            continue
        if not r.ok or "AA÷" not in r.text:
            print(f"{i:2} HTTP {r.status_code} sans match")
            continue
        titres = [b.split("ZA÷", 1)[1].split("¬")[0] for b in r.text.split("~") if b.startswith("ZA÷")]
        print(f"{i:2} {r.text.count('AA÷'):4} matchs  ex. : {' | '.join(titres[:2])}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--donnees", default="donnees")
    a = ap.parse_args()
    maintenant = datetime.now(timezone.utc)
    attente = json.loads((Path(a.donnees) / "resultats_a_saisir.json").read_text())["matchs"]
    print(f"{len(attente)} matchs en attente ; sources lues le {maintenant:%Y-%m-%d %H:%M} UTC")
    cache: dict = {}
    for m in attente:
        sport, debut = m["sport"], resultats._heure(m["debut"])
        jours = [(debut + timedelta(days=k)).strftime("%Y-%m-%d") for k in (-1, 0, 1)]
        recs: list[dict] = []
        etats = []
        if sport in resultats.ESPN_LIGUES:
            k = ("espn", sport)
            cache[k] = cache.get(k) or resultats.lire_espn(sport, debut - timedelta(days=1), maintenant)
            recs += cache[k]
        if sport in livescore.SPORTS:
            k = ("ls", sport, jours[0])
            cache[k] = cache.get(k) or livescore.lire(sport, jours)
            recs += cache[k]
        if sport in flashscore.SPORTS:
            k = ("fs", sport, jours[0])
            cache[k] = cache.get(k) or flashscore.lire(sport, jours, maintenant)
            recs += cache[k]
        for j in jours:
            k = ("sofa", sport, j)
            if k not in cache:
                cache[k] = sofascore(sport, j)
            recs += cache[k][0]
            etats.append(f"{j}: {cache[k][1]}")
        dom, ext = (x.strip() for x in m["match"].split(" – ", 1))
        recs += thesportsdb(sport, dom, ext)
        print(f"\n### {sport} | {m['ligue']} | {m['match']} | {m['debut'][:16]} | {m['paris']} pari(s)")
        print(f"  Sofascore : {'; '.join(etats)}")
        lignes = proches(m, recs)
        print("\n".join(lignes) if lignes else "    aucun candidat à ±14 h")
    sports_flashscore()
    print("\nErreurs :", livescore.ERREURS[:5], flashscore.ERREURS[:5], resultats.ERREURS_ESPN[:5])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
