"""Compare le secours pinnodds à la lecture directe de Pinnacle (à lancer quand les deux répondent).

    PINNODDS_API_KEY=... PINNODDS_HANDICAPS=oui python scripts/comparer_secours_pinnacle.py [football tennis ...]

Sans conséquence sur les données : aucune écriture, et le budget journalier du secours n'est pas touché.
Une couverture élevée et plus de 99 % de cotes à ±1 % valident le secours ; sinon, ne pas l'activer.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cotes import pinnacle, pinnacle_secours  # noqa: E402


def main(noms: list[str]) -> int:
    sids = {sid for sid, nom in pinnacle.SPORTS.items() if (not noms or nom in noms)} & set(pinnacle_secours.SPORTS_PINNODDS)
    if not pinnacle_secours.disponible():
        print("PINNODDS_API_KEY absente")
        return 1
    direct = pinnacle.collecter({sid: pinnacle.SPORTS[sid] for sid in sids})
    if not direct:
        print("Pinnacle ne répond pas : rien à comparer", pinnacle.ERREURS[:3])
        return 1
    secours = pinnacle_secours.collecter(sids, datetime.now(timezone.utc), None)
    print(json.dumps({"direct": len(direct), "erreurs_secours": pinnacle_secours.ERREURS,
                      **pinnacle_secours.comparer(direct, secours)}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
