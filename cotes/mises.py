"""Méthodes de mise comparées sur les mêmes paris réglés : rien n'est joué, aucune sélection ne change.

Chaque pari est misé au moment de sa détection, avec ce qu'on savait alors : la bankroll et la série en cours ne
comptent que les paris déjà réglés à cet instant (jamais le résultat du pari lui-même). Départ : 1 000 €.
Le gain d'un pari suit ``cotes.reglement.gain`` (demi-gains, remboursés). Les paris en cours ne sont pas comptés.
"""
from __future__ import annotations

from .laboratoire import heure
from .reglement import GAIN, gain as gain_reglement

BANKROLL = 1000.0


def _fini(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and x == x and abs(x) != float("inf")


def _kelly(fraction: float, plafond: float, evolutive: bool = False, borne: float | None = None):
    def mise(p, bankroll, serie):
        cote, ecart = p["cote"], p.get("ecart")
        if not _fini(ecart) or ecart <= 0 or cote <= 1:
            return 0.0
        base = bankroll if evolutive else BANKROLL
        m = min(base * fraction * ecart / (cote - 1), base * plafond)
        return min(m, borne) if borne else m
    return mise


def _pct_bankroll(part: float):
    return lambda p, bankroll, serie: bankroll * part


def _par_point(euros: float, plafond: float):
    return lambda p, bankroll, serie: min(euros * 100 * p["ecart"], plafond) if _fini(p.get("ecart")) and p["ecart"] > 0 else 0.0


def _gain_constant(cible: float, plafond: float):
    return lambda p, bankroll, serie: min(cible / (p["cote"] - 1), plafond) if p["cote"] > 1 else 0.0


def _paliers(p, bankroll, serie):
    e = p.get("ecart")
    if not _fini(e) or e <= 0:
        return 0.0
    return 5.0 if e < 0.04 else 10.0 if e < 0.07 else 15.0


def _apres_pertes(p, bankroll, serie):
    return 5.0 if len(serie) >= 3 and all(s == "perdu" for s in serie[-3:]) else 10.0


def _apres_gains(p, bankroll, serie):
    return 15.0 if len(serie) >= 3 and all(s == "gagne" for s in serie[-3:]) else 10.0


def _martingale(p, bankroll, serie):
    k = 0
    for s in reversed(serie):
        if s != "perdu" or k == 3:
            break
        k += 1
    return 10.0 * 2 ** k


# clé: (libellé, description courte, fonction de mise, mise tenant compte de la bankroll ?)
METHODES = {
    "fixe": ("Fixe 10 €", "10 € par pari", lambda p, b, s: 10.0),
    "kelly_8": ("Kelly ⅛", "bankroll fixe 1 000 €, plafond 2 %", _kelly(0.125, 0.02)),
    "kelly_4": ("Kelly ¼", "bankroll fixe 1 000 €, plafond 2 % (mode actuel)", _kelly(0.25, 0.02)),
    "kelly_2": ("Kelly ½", "bankroll fixe, plafond 2 %", _kelly(0.5, 0.02)),
    "kelly_1": ("Kelly complet", "bankroll fixe, plafond 5 %", _kelly(1.0, 0.05)),
    "kelly_4_p1": ("Kelly ¼ plafond 1 %", "plafond 10 €", _kelly(0.25, 0.01)),
    "kelly_4_p3": ("Kelly ¼ plafond 3 %", "plafond 30 €", _kelly(0.25, 0.03)),
    "kelly_4_evol": ("Kelly ¼ sur bankroll évolutive", "bankroll = solde du moment, plafond 2 %", _kelly(0.25, 0.02, True)),
    "kelly_4_liquide": ("Kelly ¼ limité à 10 €", "hypothèse : le bookmaker n'accepte pas plus", _kelly(0.25, 0.02, borne=10.0)),
    "pct_1": ("1 % de la bankroll", "1 % du solde du moment, sans tenir compte de l'écart", _pct_bankroll(0.01)),
    "par_ecart": ("Proportionnelle à l'écart", "2,50 € par point d'écart, plafond 25 €", _par_point(2.5, 25.0)),
    "gain_constant": ("Gain constant", "miser pour gagner 10 €, plafond 25 €", _gain_constant(10.0, 25.0)),
    "paliers": ("Par paliers d'écart", "5 € sous 4 %, 10 € de 4 à 7 %, 15 € au-delà", _paliers),
    "apres_pertes": ("Réduite après 3 pertes", "5 € après 3 pertes d'affilée, sinon 10 €", _apres_pertes),
    "apres_gains": ("Augmentée après 3 gains", "15 € après 3 gains d'affilée, sinon 10 €", _apres_gains),
    "martingale": ("Martingale (déconseillée)", "10 € doublés après chaque perte, 80 € au plus", _martingale),
}
EVOLUTIVES = {"kelly_4_evol", "pct_1", "martingale"}


def simuler(rows: list[dict], cle: str) -> dict:
    """Rejoue les paris réglés avec une méthode de mise. Renvoie nombre, mise, gain, ROI, mise moyenne et maximale,
    plus forte baisse du gain cumulé, solde final et solde minimum."""
    mise_de = METHODES[cle][2]
    regles = [p for p in rows if p.get("statut") in GAIN and heure(p.get("detecte")) and heure(p.get("regle_le"))
              and _fini(p.get("cote"))]
    regles = [p for p in regles if heure(p["detecte"]) <= heure(p["regle_le"])]
    par_detection = sorted(regles, key=lambda p: (heure(p["detecte"]), p["id"]))
    par_reglement = sorted(regles, key=lambda p: (heure(p["regle_le"]), p["id"]))
    solde, serie, i, gains = BANKROLL, [], 0, {}
    evenements, mises = [], []
    for p in par_detection:
        t = heure(p["detecte"])
        while i < len(par_reglement) and heure(par_reglement[i]["regle_le"]) <= t:
            q = par_reglement[i]
            solde += gains.get(q["id"], 0.0)
            serie.append(q["statut"])
            i += 1
        m = mise_de(p, solde, serie)
        # une méthode qui mise sur le solde du moment ne dépasse jamais ce solde ; les autres peuvent passer sous zéro
        m = round(min(m, max(solde, 0.0)) if cle in EVOLUTIVES else m, 2)
        if m <= 0:
            continue
        g = gain_reglement(p["statut"], m, p["cote"])
        mises.append(m)
        evenements.append((heure(p["regle_le"]), p["id"], g))
        gains[p["id"]] = g
    cumul = sommet = baisse = 0.0
    plus_bas = BANKROLL
    for _, _, g in sorted(evenements):
        cumul += g
        sommet = max(sommet, cumul)
        baisse = max(baisse, sommet - cumul)
        plus_bas = min(plus_bas, BANKROLL + cumul)
    n, total_mise, total = len(mises), sum(mises), sum(g for _, _, g in evenements)
    return {"paris": n, "mise": round(total_mise, 2), "gain": round(total, 2),
            "roi": round(100 * total / total_mise, 2) if total_mise else None,
            "mise_moyenne": round(total_mise / n, 2) if n else None, "mise_max": max(mises, default=0.0),
            "baisse": round(baisse, 2), "solde": round(BANKROLL + total, 2), "solde_min": round(plus_bas, 2)}


def comparer(rows: list[dict]) -> dict:
    """Toutes les méthodes sur les mêmes paris ; ``rows`` n'est pas modifié."""
    return {cle: simuler(rows, cle) for cle in METHODES}
