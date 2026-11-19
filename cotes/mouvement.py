"""Mouvement de la cote juste de Pinnacle (« dropping odds ») avant la prise d'un pari.

Quand la cote de Pinnacle baisse sur une issue, la probabilité juste monte : le marché sharp « sait » quelque chose
et les bookmakers français ne l'ont peut-être pas encore suivi. Pour tester si ce signal annonce de meilleurs paris,
on garde pour chaque cote Pinnacle associée à un match français une **ancre** (probabilité juste, heure de lecture).
Chaque cycle compare la probabilité actuelle à l'ancre quand celle-ci a au moins ``AGE_MIN_S`` secondes ; l'ancre
est renouvelée après ``AGE_MAX_S``. Le mouvement (+3 % = probabilité juste 3 % plus haute que l'ancre) et la
durée mesurée sont inscrits dans l'opportunité, puis dans le pari.

Garde-fou (1er novembre 2026) : une cote Pinnacle **figée** ne sert plus de référence. Si sa probabilité juste est
strictement identique à l'ancre lue au moins ``AGE_MIN_S`` secondes plus tôt (mouvement 0, arrondi à 4 décimales),
le prix servi est probablement une copie de cache restée en place pendant que le vrai marché bougeait. Du 25/10 au
01/11, 53 paris adossés à une cote ainsi figée (jusqu'à 62 min) avaient une CLV de −8 % (24 % positives), contre
environ 0 % ou mieux quand la cote bougeait. L'opportunité de référence Pinnacle, ou Consensus dont Pinnacle est une
composante, est alors marquée ``suspect = "cote Pinnacle figée"`` et ``pariable = False`` : ni pari, ni alerte.
Les autres références (Polymarket, Matchbook…) ne sont pas touchées. Les paris déjà pris ne changent pas.

z-score (18 novembre 2026, idée reprise de kaykyif/pinnacle-odds-radar, src/volatility.py) : une chute de 3 % ne
pèse pas pareil sur un marché nerveux et sur un marché calme. Pour chaque marché (type + période), on tient la
moyenne et la variance des mouvements non nuls mesurés sur toutes les cotes Pinnacle suivies, pondérées sur environ
``Z_FENETRE`` mesures (moyenne mobile exponentielle). ``mouvement_z`` = (mouvement − moyenne) / écart-type, calculé
avec les statistiques **d'avant** le cycle (le cycle ne se juge pas lui-même), puis le cycle les met à jour. Moins de
``Z_MIN_MESURES`` mesures ou écart-type nul : pas de z. Les mouvements nuls (cote figée) restent hors base.

Épisode (même source) : un vrai mouvement fait souvent chuter plusieurs lignes alternatives d'un coup (handicap −0,5,
−0,75, −1…). ``mouvement_lignes`` = nombre de cotes Pinnacle du même match, marché, période et issue (lignes
différentes) dont le mouvement atteint ``EPISODE_MIN`` ce cycle. Descriptif seulement.

Les ancres et les statistiques vivent dans le cache GitHub Actions, à côté de la reprise (même dossier), jamais dans
la branche « donnees ». Absent ou illisible : aucun mouvement (ou pas de z), le cycle continue. Ne lève jamais.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path

from .marches import cle

AGE_MIN_S = 600          # en dessous, le mouvement est du bruit d'un cycle à l'autre
AGE_MAX_S = 3600         # l'ancre est renouvelée après une heure : le mouvement porte sur 10 à 60 minutes
FIGEE = "cote Pinnacle figée"
Z_FENETRE = 5000         # poids des statistiques par marché : environ les 5 000 dernières mesures
Z_MIN_MESURES = 200      # en dessous, l'écart-type n'est pas fiable : pas de z
EPISODE_MIN = 0.03       # chute comptée dans un épisode (même seuil que Drop Pinnacle)
STATS = "stats_mouvement.json.gz"


def _depend_de_pinnacle(o: dict) -> bool:
    """Référence Pinnacle, ou Consensus dont Pinnacle est une composante."""
    if o.get("reference") == "Pinnacle":
        return True
    return o.get("reference") == "Consensus" and "Pinnacle" in str(o.get("sources") or "").split("+")


def est_figee(o: dict) -> bool:
    """Cote Pinnacle de référence strictement inchangée depuis au moins AGE_MIN_S secondes."""
    m, s = o.get("mouvement_pinnacle"), o.get("mouvement_s")
    return (_depend_de_pinnacle(o) and isinstance(m, (int, float)) and not isinstance(m, bool) and m == 0
            and isinstance(s, (int, float)) and not isinstance(s, bool) and s >= AGE_MIN_S)


def _id(match_id, k: tuple) -> str:
    return hashlib.blake2b(f"{match_id}|{k}".encode(), digest_size=6).hexdigest()


def _cote_pinnacle(mid_fr, k: tuple, l: dict) -> tuple:
    """(match Pinnacle, clé dans l'ordre de Pinnacle) de la ligne ``l`` rangée sous le match français ``mid_fr``.

    Un même match Pinnacle est associé à un match de chaque bookmaker français : sans cette clé, son mouvement
    comptait une fois par bookmaker dans les statistiques du z (19/11/2026). Ligne sans identifiant ou incomplète :
    repli sur le match français et sa clé."""
    mid = l.get("match_id")
    if mid is None:
        return mid_fr, k
    try:
        return mid, cle(l)
    except (KeyError, TypeError, ValueError):
        return mid_fr, k


def lire(chemin: Path | None) -> dict:
    if chemin is None:
        return {}
    try:
        doc = json.loads(gzip.decompress(chemin.read_bytes()))
    except (OSError, EOFError, ValueError):
        return {}
    return doc if isinstance(doc, dict) else {}


def ecrire(chemin: Path, ancres: dict) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    tmp = chemin.with_name(chemin.name + ".tmp")
    tmp.write_bytes(gzip.compress(json.dumps(ancres, separators=(",", ":")).encode(), 6))
    os.replace(tmp, chemin)


def mettre_a_jour(ancres: dict, lignes: dict[str, float], maintenant: datetime) -> dict[str, tuple[float, int]]:
    """Met `ancres` à jour (modifié sur place) et renvoie {id: (mouvement, secondes mesurées)}.

    `lignes` = {id: probabilité juste de Pinnacle ce cycle}. Les ancres des lignes absentes sont oubliées."""
    t = int(maintenant.timestamp())
    mouvements: dict[str, tuple[float, int]] = {}
    for i in [i for i in ancres if i not in lignes]:
        del ancres[i]
    for i, p in lignes.items():
        a = ancres.get(i)
        if not (isinstance(a, list) and len(a) == 2 and a[0] > 0):
            ancres[i] = [round(p, 5), t]
            continue
        age = t - a[1]
        if age >= AGE_MIN_S:
            mouvements[i] = (round(p / a[0] - 1, 4), age)
        if age >= AGE_MAX_S or age < 0:
            ancres[i] = [round(p, 5), t]
    return mouvements


def _groupe(k: tuple) -> str:
    return f"{k[0]}|{k[1]}"


def _episode(match_id, k: tuple) -> tuple:
    """Même match, marché, période et issue (et joueur) : seules les lignes diffèrent."""
    return (str(match_id), k[0], k[1], *k[3:])


def z_et_maj(stats: dict, mesures: dict[str, list[float]]) -> dict[str, tuple[float, float] | None]:
    """Moyenne et écart-type d'avant le cycle par groupe (None si base insuffisante), puis mise à jour de `stats`
    (modifié sur place) avec les mouvements non nuls du cycle. `stats` = {groupe: [n, moyenne, variance]}."""
    avant: dict[str, tuple[float, float] | None] = {}
    for g in set(stats) | set(mesures):
        e = stats.get(g)
        ok = isinstance(e, list) and len(e) == 3 and all(isinstance(x, (int, float)) for x in e)
        n, moy, var = e if ok else (0, 0.0, 0.0)
        avant[g] = (moy, var ** .5) if n >= Z_MIN_MESURES and var > 0 else None
        for m in mesures.get(g, ()):
            if m == 0:
                continue
            n += 1
            a = max(1 / n, 1 / Z_FENETRE)
            d = m - moy
            moy += a * d
            var = (1 - a) * (var + a * d * d)
        stats[g] = [min(n, 10 ** 9), round(moy, 7), round(var, 9)]
    return avant


def annoter(opportunites: list[dict], index: dict, chemin: Path | None, maintenant: datetime) -> dict:
    """Ajoute `mouvement_pinnacle` et `mouvement_s` aux opportunités, écarte celles dont la cote Pinnacle de référence
    est figée (garde-fou, voir en tête du module) ; résumé pour le journal. Ne lève jamais."""
    if chemin is None:
        return {"actif": False}
    try:
        pinnacle = index.get("Pinnacle") or {}
        lignes: dict[str, float] = {}
        cles: dict[str, tuple] = {}
        for mid_fr, par_cle in pinnacle.items():
            for k, l in par_cle.items():
                p = l.get("proba_juste")
                if isinstance(p, (int, float)) and 0 < p < 1:
                    mid, kp = _cote_pinnacle(mid_fr, k, l)
                    i = _id(mid, kp)
                    lignes[i], cles[i] = p, (mid, kp)     # une seule fois par cote Pinnacle, quel que soit le bookmaker
        ancres = lire(chemin)
        mouvements = mettre_a_jour(ancres, lignes, maintenant)
        mesures: dict[str, list[float]] = {}
        episodes: dict[tuple, int] = {}
        for i, (m, _s) in mouvements.items():
            mid_fr, k = cles[i]
            mesures.setdefault(_groupe(k), []).append(m)
            if m >= EPISODE_MIN:
                e = _episode(mid_fr, k)
                episodes[e] = episodes.get(e, 0) + 1
        chemin_stats = chemin.with_name(STATS)
        stats = lire(chemin_stats)
        avant = z_et_maj(stats, mesures)
        n = figees = 0
        for o in opportunites:
            k = cle(o)
            l = (pinnacle.get(o.get("match_id")) or {}).get(k)
            mid, kp = _cote_pinnacle(o.get("match_id"), k, l) if isinstance(l, dict) else (o.get("match_id"), k)
            m = mouvements.get(_id(mid, kp))
            if m:
                o["mouvement_pinnacle"], o["mouvement_s"] = m
                base = avant.get(_groupe(kp))
                if base:
                    o["mouvement_z"] = round((m[0] - base[0]) / base[1], 2)
                o["mouvement_lignes"] = episodes.get(_episode(mid, kp), 0)
                n += 1
                if est_figee(o):
                    if not o.get("suspect"):
                        o["suspect"] = FIGEE
                    o["pariable"] = False
                    figees += 1
        try:
            ecrire(chemin, ancres)
            ecrire(chemin_stats, stats)
        except Exception as e:  # noqa: BLE001  une écriture ratée ne retire pas les mouvements du cycle
            return {"actif": True, "ancres": len(ancres), "annotees": n, "figees": figees,
                    "ecriture": type(e).__name__}
        return {"actif": True, "ancres": len(ancres), "mesures": len(mouvements), "annotees": n, "figees": figees}
    except Exception as e:  # noqa: BLE001
        return {"actif": True, "erreur": type(e).__name__}
