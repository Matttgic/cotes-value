"""Étude : combien de surebets les historiques contiennent-ils déjà ?

Rejoue cycle par cycle (heures de ``releves/``) les cotes françaises (``cotes/``), les cotes justes des références
(``references/``) et les rapprochements de matchs (``correspondances/``), puis applique le détecteur du cycle
(``cotes/surebets.py``, mêmes marchés, mêmes garde-fous de cote juste) et son suivi des épisodes.

Différences avec le direct, toutes connues :
- l'historique n'écrit une cote qu'à son changement : une cote non retirée est supposée encore proposée (les retraits
  sont notés depuis le 12/11/2026, quand le match a été relu). Pour limiter ce biais, seuls les matchs qui commencent
  dans les ``HORIZON_H`` heures (relus à chaque cycle) sont pris ;
- l'âge des cotes et l'écart de lecture entre bookmakers ne sont pas mesurables (toutes datées de l'heure du cycle) ;
- le contrôle des intitulés n'est pas rejoué (son état passé n'est pas archivé).
Le rejeu compte donc des surebets que le direct aurait écartés : c'est un plafond, pas une prévision.

    python etudes/etude_surebets.py --donnees donnees --jours 2026-11-13 2026-11-14 [--horizon 36]

La veille du premier jour (si elle existe) remplit seulement l'état des cotes, sans détection.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cotes import surebets as S  # noqa: E402
from cotes.analyse_marche import lecture as L  # noqa: E402
from cotes.marches import cle, inverser  # noqa: E402

FRANCAIS = {"PMU", "Betclic", "Unibet", "Winamax", "NetBet", "OlyBet"}
HORIZON_H = 6
MARCHES = set(S.TROIS_ISSUES) | set(S.DEUX_ISSUES) | set(S.DEMI_LIGNE) | {"DOUBLE_CHANCE"}
PREFIXES = tuple(f'"k":"{m}|' for m in MARCHES)


def _cle(k: str):
    """(marché, période, ligne, issue) d'une clé d'historique, None hors des marchés des surebets."""
    parts = str(k).split("|")
    if len(parts) != 4 or parts[0] not in MARCHES:
        return None
    try:
        ligne = float(parts[2]) if parts[2] else None
    except ValueError:
        return None
    return parts[0], parts[1], ligne, parts[3]


def descriptions(donnees: Path, jour: str) -> dict:
    """Match français -> description (sport, ligue, équipes, début), vue dans les 4 jours précédents."""
    out = {}
    for d in range(-4, 1):
        for x in L.lire(L.chemin(donnees, "cotes", L.decaler(jour, d)), lambda brut: '"k"' not in brut):
            if x.get("b") in FRANCAIS and x.get("m") and x.get("dom") and x.get("ext") and L.t(x.get("debut")):
                out[x["m"]] = x
    return out


def rapprochements(donnees: Path, jour: str) -> list[tuple]:
    """(heure, match français, référence, rencontre, inversé) de la veille et du jour, triés."""
    out = []
    for d in (-1, 0):
        for x in L.lire(L.chemin(donnees, "correspondances", L.decaler(jour, d))):
            if x.get("fr") and x.get("b") and x.get("m") is not None:
                out.append((x["t"], x["fr"], x["b"], x["m"], bool(x.get("inv"))))
    return sorted(out)


def evenements(donnees: Path, jour: str, rencontres: set) -> list[tuple]:
    """Cotes françaises et cotes justes du jour, triées par heure : (heure, genre, source, match, clé, valeur)."""
    out = []
    garder = (lambda brut: any(p in brut for p in PREFIXES))
    for x in L.lire(L.chemin(donnees, "cotes", jour), garder):
        k = _cle(x.get("k"))
        if k and x.get("b") in FRANCAIS:
            out.append((x["t"], "f", x["b"], x["m"], k, x.get("c")))
    for x in L.lire(L.chemin(donnees, "references", jour), garder):
        k = _cle(x.get("k"))
        if k and (x.get("b"), x.get("m")) in rencontres:
            out.append((x["t"], "r", x["b"], x["m"], k, None if x.get("c") is None or x.get("per") else x.get("p")))
    out.sort(key=lambda e: e[0])
    return out


def _orient(k: tuple, inverse: bool) -> tuple:
    if not inverse:
        return k
    m, per, ligne, issue = k
    return cle(inverser({"marche": m, "periode": per, "ligne": ligne, "issue": issue, "domicile": "", "exterieur": ""}))


def rejouer(donnees: Path, jour: str, etat: dict, memoire: dict | None = None,
            detecter: bool = True) -> tuple[dict, Counter]:
    """Rejoue un jour. ``memoire`` (cotes, cotes justes et rapprochements en cours) passe d'un jour au suivant : une
    cote inchangée depuis la veille reste connue. ``detecter`` faux : le jour sert seulement à remplir la mémoire."""
    memoire = memoire if memoire is not None else {}
    fr, ref, assoc = (memoire.setdefault(k, {}) for k in ("fr", "ref", "assoc"))
    desc = descriptions(donnees, jour)
    rappro = rapprochements(donnees, jour)
    rencontres = {(b, m) for _, _, b, m, _ in rappro} | set(ref)
    evts = evenements(donnees, jour, rencontres)
    cycles = sorted({x["t"] for x in L.lire(L.chemin(donnees, "releves", jour)) if x.get("t")})
    i = j = 0
    compte: Counter = Counter()
    for n, _debut_cycle in enumerate(cycles):
        fin = cycles[n + 1] if n + 1 < len(cycles) else None
        if fin is None:
            break
        while i < len(evts) and evts[i][0] < fin:
            _, genre, b, m, k, v = evts[i]
            cible = fr if genre == "f" else ref
            d = cible.setdefault((b, m), {})
            if v is None:
                d.pop(k, None)
            else:
                d[k] = v
            i += 1
        while j < len(rappro) and rappro[j][0] < fin:
            _, mid_fr, b, m, inv = rappro[j]
            assoc.setdefault(mid_fr, {})[b] = (m, inv)
            j += 1
        if not detecter:
            continue
        maintenant = L.t(fin) - timedelta(seconds=1)
        iso = maintenant.isoformat(timespec="seconds")
        limite = maintenant + timedelta(hours=HORIZON_H)
        francais, index = [], {}
        for (b, mid), cotes in fr.items():
            dsc, refs = desc.get(mid), assoc.get(mid)
            debut = L.t(dsc.get("debut")) if dsc else None
            if not refs or debut is None or not maintenant < debut <= limite:
                continue
            for nom, (rmid, inv) in refs.items():
                justes = ref.get((nom, rmid))
                if justes:
                    index.setdefault(nom, {})[mid] = {
                        _orient(k, inv): {"match_id": rmid, "inverse": inv, "proba_juste": p, "collecte": iso}
                        for k, p in justes.items()}
            for (marche, per, ligne, issue), c in cotes.items():
                francais.append({"source": b, "bookmaker": b.lower(), "match_id": mid, "sport": dsc.get("sport"),
                                 "ligue": dsc.get("ligue"), "domicile": dsc["dom"], "exterieur": dsc["ext"],
                                 "debut": dsc["debut"], "collecte": iso, "marche": marche, "periode": per,
                                 "ligne": ligne, "issue": issue, "cote": c, "libelle": None, "lien": None})
        actuels, journal = S.detecter(francais, index, maintenant)
        etat = S.suivre(etat, actuels, maintenant)
        compte["cycles"] += 1
        compte["surebets_vus"] += len(actuels)
        compte["suspects_vus"] += journal["suspects"]
    return etat, compte


def resume(episodes: list[dict]) -> dict:
    """Comptes par seuil de rendement, bookmakers, sports, marchés et durée."""
    def tranche(r):
        return "≥ 2 %" if r >= 0.02 else "1–2 %" if r >= 0.01 else "0,5–1 %" if r >= 0.005 else "< 0,5 %"
    verifies = [e for e in episodes if e.get("verifie")]
    duree = Counter("1 cycle" if e["cycles"] == 1 else "2-3 cycles" if e["cycles"] <= 3 else "4 cycles et +"
                    for e in episodes)
    marche = Counter(e["pari"].split(" (")[0].split(" de ")[0] for e in episodes)
    return {"episodes": len(episodes), "verifies": len(verifies),
            "tranches": Counter(tranche(e["rendement_initial"]) for e in episodes),
            "tranches_verifies": Counter(tranche(e["rendement_initial"]) for e in verifies),
            "gain_100": round(sum(e["gain_100"] for e in episodes), 2),
            "gain_100_un_pour_cent": round(sum(e["gain_100"] for e in episodes if e["rendement_initial"] >= 0.01), 2),
            "bookmakers": Counter(" + ".join(e["bookmakers"]) for e in episodes).most_common(10),
            "sports": Counter(e.get("sport") for e in episodes).most_common(8),
            "marches": marche.most_common(10), "duree": duree}


def main(argv: list[str] | None = None) -> int:
    global HORIZON_H
    a = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    a.add_argument("--donnees", type=Path, default=Path("donnees"))
    a.add_argument("--jours", nargs="+", required=True)
    a.add_argument("--exemples", type=int, default=12)
    a.add_argument("--horizon", type=float, default=HORIZON_H, help="heures avant le match (défaut 6)")
    args = a.parse_args(argv)
    HORIZON_H = args.horizon
    etat: dict = {}
    memoire: dict = {}
    veille = L.decaler(args.jours[0], -1)
    if L.chemin(args.donnees, "cotes", veille).exists():      # la veille remplit seulement la mémoire
        etat, _ = rejouer(args.donnees, veille, etat, memoire, detecter=False)
    for jour in args.jours:
        avant = len(etat.get("episodes", []))
        etat, compte = rejouer(args.donnees, jour, etat, memoire)
        print(f"{jour} : {compte['cycles']} cycles, {len(etat.get('episodes', [])) - avant} épisodes, "
              f"{compte['suspects_vus']} surebets suspects vus", file=sys.stderr)
    episodes = etat.get("episodes", [])
    print(json.dumps(resume(episodes), ensure_ascii=False, indent=1))
    for e in sorted(episodes, key=lambda e: -e["rendement_initial"])[:args.exemples]:
        jambes = " · ".join(f'{x["bookmaker"]} {x["issue"]} {x["cote"]} (juste {x["cote_juste"] or "?"})'
                            for x in e["jambes"])
        print(f'{e["premier"][:16]} {e["sport"]} {e["match"]} | {e["pari"]} | +{100 * e["rendement_initial"]:.2f} % '
              f'| {e["cycles"]} cycle(s) | {"vérifié" if e.get("verifie") else "non vérifié"} | {jambes}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
