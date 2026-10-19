"""Essai ponctuel de PinBook (Pinnacle via RapidAPI) : couverture, fraîcheur et quota, sans rien écrire.

    PINBOOK_API_KEY=... python scripts/tester_pinbook.py [identifiants de sport PinBook, 1 2 3 par défaut]

Trois requêtes au plus (l'offre gratuite en compte 550 par mois). Le résultat s'affiche et, sous GitHub Actions,
s'ajoute au résumé du job. La clé n'est jamais affichée.
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cotes import pinnacle, pinnacle_secours  # noqa: E402

HOTE = "pinbook-odds.p.rapidapi.com"
SPORTS = {1: "football", 2: "tennis", 3: "basket"}


def analyser(corps: dict, sport: str, maintenant: datetime) -> dict:
    evenements = [e for e in (corps.get("events") or []) if isinstance(e, dict)]
    base = {"source": "pinnacle", "origine": "pinbook", "sport": sport, "age_cache_s": 0, "cote_perimee": False}
    lignes = [l for e in evenements for l in pinnacle_secours._lignes_evenement(e, sport, base, True)]
    pinnacle._ajouter_proba_justes(lignes)
    sures = [l for l in lignes if l.get("proba_juste")]
    debuts = []
    for e in evenements:
        try:
            debuts.append(datetime.fromisoformat(str(e.get("starts")).replace("Z", "+00:00")).replace(tzinfo=timezone.utc))
        except ValueError:
            pass
    futurs = sorted(d for d in debuts if d > maintenant)
    try:
        age_min = round((maintenant.timestamp() - float(corps.get("last_call"))) / 60, 1)
    except (TypeError, ValueError):
        age_min = None
    return {"evenements": len(evenements), "matchs_a_venir": len(futurs),
            "matchs_36h": sum(1 for d in futurs if (d - maintenant).total_seconds() <= 36 * 3600),
            "dernier_match_h": round((futurs[-1] - maintenant).total_seconds() / 3600, 1) if futurs else None,
            "lignes": len(lignes), "lignes_avec_proba": len(sures),
            "marches": sorted({l["marche"] for l in sures}), "age_last_call_min": age_min,
            "avec_home_team_type": sum(1 for e in evenements if e.get("home_team_type"))}


def main(ids: list[int]) -> int:
    cle = os.environ.get("PINBOOK_API_KEY", "").strip()
    if not cle:
        print("PINBOOK_API_KEY absente")
        return 1
    session, rapport = requests.Session(), {}
    for sid in ids or list(SPORTS):
        maintenant = datetime.now(timezone.utc)
        r = session.get(f"https://{HOTE}/kit/v1/markets", timeout=40,
                        params={"sport_id": sid, "is_have_odds": 1, "event_type": "prematch"},
                        headers={"x-rapidapi-key": cle, "x-rapidapi-host": HOTE})
        bloc = {"http": r.status_code,
                "quota": {k: v for k, v in r.headers.items() if k.lower().startswith("x-ratelimit")}}
        if r.status_code == 200:
            try:
                bloc.update(analyser(r.json(), SPORTS.get(sid, str(sid)), maintenant))
            except Exception as e:                       # un sport illisible ne cache pas les autres
                bloc["erreur"] = f"{type(e).__name__} : {str(e)[:120]}"
        else:
            bloc["erreur"] = r.text[:150].replace(cle, "***")
        rapport[SPORTS.get(sid, str(sid))] = bloc
    texte = json.dumps(rapport, ensure_ascii=False, indent=1)
    print(texte)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write("### Essai PinBook\n```json\n" + texte + "\n```\n")
    return 0 if all(b["http"] == 200 and "erreur" not in b for b in rapport.values()) else 1


if __name__ == "__main__":
    sys.exit(main([int(a) for a in sys.argv[1:] if a.isdigit()]))
