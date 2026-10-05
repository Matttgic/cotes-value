"""Simulation du nombre de requêtes PulseScore selon les bookmakers, la fréquence et la formule.

Principe : les listes PulseScore sont triées par heure de début et paginées par 30 matchs.
Une photo d'un sport chez un bookmaker coûte donc ceil(matchs dans la fenêtre / 30) requêtes
(au moins 1). On ne lit un sport que si Pinnacle y a des matchs dans la fenêtre (sinon pas de
référence). Pinnacle lui-même est lu directement, gratuitement, sans quota.

Hypothèses (relevées le 05/10/2026, trêve internationale) : nombre de matchs dans les 36 h par
sport, pour trois types de journées. « calme » = mesure réelle de cette nuit ; « moyen » et « pic »
sont extrapolés du calendrier Pinnacle (264 matchs de foot samedi 10/10 déjà listés).

Usage : python scripts/simulation_appels.py
"""
from __future__ import annotations

import math

# matchs démarrant dans la fenêtre de 36 h, par sport
JOURNEES = {
    "calme": {"soccer": 75, "tennis": 113, "basketball": 23, "ice-hockey": 33, "handball": 4,
              "american-football": 2, "baseball": 12, "volleyball": 0, "rugby-union": 0, "mma": 0},
    "moyen": {"soccer": 250, "tennis": 110, "basketball": 40, "ice-hockey": 45, "handball": 15,
              "american-football": 5, "baseball": 12, "volleyball": 10, "rugby-union": 6, "mma": 0},
    "pic":   {"soccer": 600, "tennis": 90, "basketball": 60, "ice-hockey": 60, "handball": 25,
              "american-football": 50, "baseball": 12, "volleyball": 20, "rugby-union": 15, "mma": 12},
}
# part des matchs Pinnacle que chaque bookmaker propose (NetBet liste plus de matchs que les autres)
COUVERTURE = {"winamax": 1.0, "betclic": 1.0, "unibet-fr": 1.0, "pmu": 0.8, "netbet": 1.3,
              "orbitxch": 1.0, "polymarket": 1.0}
FRANCAIS = ["winamax", "betclic", "unibet-fr", "pmu", "netbet"]
SHARPS = ["orbitxch", "polymarket"]
SPORTS_SHARPS = {"soccer", "tennis", "basketball"}      # ailleurs ils n'apportent presque rien

FORMULES = {"STARTER (20 €)": {"mois": 30_000, "par_min_et_bookmaker": 1},
            "PRO (79 €)": {"mois": math.inf, "par_min_et_bookmaker": 60}}
MOIS = {"calme": 10, "moyen": 12, "pic": 8}                # répartition des 30 jours d'un mois type
REGLEMENT_PAR_JOUR = 40                                    # résultats (quelques pages par sport et par jour)


def pages(bookmaker: str, journee: dict, fraction: float = 1.0) -> int:
    """Requêtes pour une photo d'un bookmaker (fraction = part de la fenêtre de 36 h lue)."""
    total = 0
    for sport, n in journee.items():
        if n == 0 or (bookmaker in SHARPS and sport not in SPORTS_SHARPS):
            continue
        total += max(1, math.ceil(n * fraction * COUVERTURE[bookmaker] / 30))
    return total


def scenario(books: list[str], journee: dict, frequence_min: int, proche_min: int | None = None):
    """Requêtes par jour et page maximale par bookmaker (durée d'une photo en STARTER).

    proche_min : si renseigné, seules les 12 premières heures (≈ 1/3 de la fenêtre) sont relues
    toutes les `proche_min` minutes, la fenêtre complète toutes les `frequence_min` minutes.
    """
    par_photo = {b: pages(b, journee) for b in books}
    jour = sum(par_photo.values()) * (24 * 60 / frequence_min)
    proche_max = 0
    if proche_min:
        proche = {b: pages(b, journee, 1 / 3) for b in books}
        jour += sum(proche.values()) * (24 * 60 / proche_min - 24 * 60 / frequence_min)
        proche_max = max(proche.values())
    return round(jour), max(par_photo.values()), proche_max


def main() -> None:
    cas = [("Winamax + Betclic", ["winamax", "betclic"]),
           ("5 bookmakers français", FRANCAIS),
           ("5 français + Betfair + Polymarket", FRANCAIS + SHARPS)]
    frequences = [(15, None), (30, None), (60, None), (120, None), (120, 30)]
    print("Requêtes par photo complète (36 h) :")
    for nom, books in cas:
        print(f"  {nom:36}" + "  ".join(f"{j}={sum(pages(b, J) for b in books):4}" for j, J in JOURNEES.items()))
    print("\nRequêtes par mois (mois type : 10 jours calmes, 12 moyens, 8 de pic) + règlement :")
    for nom, books in cas:
        print(f"\n  {nom}")
        for f, proche in frequences:
            mois = sum(scenario(books, JOURNEES[j], f, proche)[0] * n for j, n in MOIS.items()) + 30 * REGLEMENT_PAR_JOUR
            _, pages_max, proche_max = scenario(books, JOURNEES["pic"], f, proche)
            libelle = f"toutes les {f} min" if not proche else f"12 h proches toutes les {proche} min, 36 h toutes les {f} min"
            # en STARTER (1 req./min par bookmaker), une photo de n pages dure n minutes
            starter_ok = mois <= 30_000 and pages_max <= f and proche_max <= (proche or f)
            print(f"    {libelle:55} {mois:>9,} req./mois   photo la plus longue en STARTER : {pages_max} min"
                  f"   -> {'STARTER possible' if starter_ok else 'PRO nécessaire'}".replace(",", " "))


if __name__ == "__main__":
    main()
