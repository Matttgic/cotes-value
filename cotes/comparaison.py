"""Comparaison des cotes françaises aux cotes justes des références (Pinnacle, Polymarket ; Smarkets affiché).

Pour chaque cote d'un bookmaker français : on retrouve le même match chez chaque référence
(cotes/correspondance.py), puis le même pari (marché, période, ligne, issue). Écart :

    écart = cote française × probabilité juste de la référence − 1

Une référence n'est utilisée que si elle est fiable à cet instant :
- lue à moins de `FENETRE_MIN` minutes de la cote française (sinon une cote qui a bougé crée une
  fausse erreur) ;
- Pinnacle : marge du marché ≤ 12 % (au-delà, retirer la marge devient imprécis) et cache
  pas plus vieux que `PINNACLE_AGE_MAX_MIN` (``cote_perimee`` faux) ;
- Polymarket et Smarkets : écart achat/vente ≤ 5 points et ≤ 25 % du prix, et un minimum d'argent
  engagé.
Corners, cartons et paris pair/impair ne sont pas comparés : l'ANJ ne les autorise pas chez les
bookmakers français.
« Consensus » = moyenne des probabilités des références disponibles (au moins deux).
"""
from __future__ import annotations

import re
from math import isfinite
from datetime import datetime

from . import controle as CT
from . import correspondance as C
from .marches import cle, deriver_double_chance, inverser
from .marge import proba_justes

FENETRE_MIN = CT.FENETRE_MIN
MARGE_MAX_PINNACLE = 0.12
ECART_ACHAT_VENTE_MAX = 0.05
ECART_RELATIF_MAX = 0.25       # écart achat/vente rapporté au prix : 0,01/0,03 n'est pas un prix fiable
LIQUIDITE_MIN = {"Polymarket": 100.0, "Smarkets": 20.0}
ECARTS_AFFICHES = (("Polymarket", "ecart_polymarket"), ("Smarkets", "ecart_smarkets"))
ECART_MIN = 0.02
# Au-delà, une « erreur de cote » est presque toujours un marché mal reconnu (statistique prise pour des
# buts, série prise pour un match…) : l'opportunité est gardée pour contrôle mais marquée suspecte, sans pari.
ECART_SUSPECT = 0.25            # cotes <= 10
ECART_SUSPECT_GROSSES = 1.0     # cotes > 10
DESACCORD_MAX = 1.25            # cotes justes de deux références qui diffèrent de plus de 25 % : suspect
_HORS_ANJ = re.compile(
    r"odd\s*/\s*even|even\s*/\s*odd|odd\s+or\s+even|even\s+or\s+odd|"
    r"pair\s*/\s*impair|impair\s*/\s*pair|pair\s+ou\s+impair|impair\s+ou\s+pair",
    re.IGNORECASE)


def hors_perimetre_anj(l: dict) -> bool:
    """Corners, cartons et pair/impair : pas de comparaison avec les books français."""
    marche = str(l.get("marche") or "")
    if marche.startswith(("CORNERS_", "CARTONS_")):
        return True
    if "ODD_EVEN" in marche.upper() or "PAIR_IMPAIR" in marche.upper():
        return True
    return bool(_HORS_ANJ.search(f"{marche} {l.get('libelle') or ''}"))


def _t(s) -> datetime | None:
    return CT._lue(s)


# --------------------------------------------------------------------------- références

def reference_echange(lignes: list[dict], source: str) -> list[dict]:
    """Exchange (Smarkets) : probabilité = milieu entre meilleur achat et meilleure vente, renormalisée.

    Le spread est dans le milieu ; aucune commission n'est retirée en plus.
    """
    groupes: dict[tuple, list[dict]] = {}
    for l in lignes:
        groupes.setdefault((l["cle_marche"], l["marche"], l["periode"], l.get("ligne")), []).append(l)
    out = []
    for g in groupes.values():
        probs, ok = [], True
        for l in g:
            achat, vente = l.get("achat") or [], l.get("vente") or []
            if not achat or not vente:
                ok = False
                break
            b, v = achat[0], vente[0]
            try:
                prix_b, prix_v = float(b["price"]), float(v["price"])
            except (TypeError, ValueError, KeyError):
                ok = False
                break
            if not (isfinite(prix_b) and isfinite(prix_v) and 1 < prix_b <= prix_v):
                ok = False
                break
            pb, pv = 1 / prix_b, 1 / prix_v
            l["ecart_achat_vente"] = round(pb - pv, 4)
            l["liquidite"] = round(min(float(b.get("liquidity") or 0), float(v.get("liquidity") or 0)), 2)
            probs.append((pb + pv) / 2)
        if not ok or len(probs) < 2:
            continue
        # renormalisé seulement à la baisse : une somme < 1 veut dire que des issues manquent (score exact,
        # mi-temps/fin…) et gonfler les autres créerait de fausses erreurs de cote
        s = max(sum(probs), 1.0)
        for l, p in zip(g, probs):
            out.append({**l, "source": source, "proba_juste": round(p / s, 6), "cote_juste": round(s / p, 4)})
    return deriver_double_chance(out)


def _fiable(nom: str, l: dict) -> bool:
    if not l.get("proba_juste") or not (0 < l["proba_juste"] < 1):
        return False
    if nom == "Pinnacle":
        if l.get("cote_perimee"):
            return False
        return (l.get("marge_pinnacle") or 0) <= MARGE_MAX_PINNACLE
    ecart = l.get("ecart_achat_vente") or 0
    if not 0 <= ecart <= ECART_ACHAT_VENTE_MAX or ecart > ECART_RELATIF_MAX * min(l["proba_juste"], 1 - l["proba_juste"]):
        return False
    return float(l.get("liquidite") or 0) >= LIQUIDITE_MIN.get(nom, 0)


# --------------------------------------------------------------------------- comparaison

def annoter_ecarts(opportunites: list[dict], francais: list[dict],
                   references: dict[str, list[dict]]) -> list[dict]:
    """Écart de chaque cote française contre Polymarket et Smarkets.

    Ces champs servent au bilan. Ils ne créent pas de pari : seules les clés
    présentes dans le dictionnaire passé à ``comparer`` décident.
    """
    index = indexer(francais, {n: references.get(n) or [] for n, _ in ECARTS_AFFICHES})
    for o in opportunites:
        if not o.get("cote"):
            continue
        k = cle(o)
        for nom, champ in ECARTS_AFFICHES:
            r = index.get(nom, {}).get(o.get("match_id"), {}).get(k)
            if not r or not CT.contemporaines({"collecte": o.get("detecte")}, r):
                o[champ] = None
                continue
            o[champ] = round(o["cote"] * r["proba_juste"] - 1, 4)
    return opportunites


def indexer(francais: list[dict], references: dict[str, list[dict]]) -> dict[str, dict]:
    """nom de la référence -> {match français: {clé de marché: ligne de référence fiable}}."""
    matchs_fr = C.matchs_de(francais)
    index: dict[str, dict] = {}
    for nom, lignes in references.items():
        lignes = [l for l in lignes if _fiable(nom, l)]
        par_match: dict[str, list[dict]] = {}
        for l in lignes:
            par_match.setdefault(l["match_id"], []).append(l)
        assoc = C.associer(matchs_fr, C.matchs_de(lignes))
        index[nom] = {}
        for mid_fr, (mid_ref, inverse, score) in assoc.items():
            index[nom][mid_fr] = {cle(inverser(l) if inverse else l): {**l, "score_association": round(score, 2),
                                                                        "inverse": inverse}
                                  for l in par_match.get(mid_ref, [])}
    return index


def comparer(francais: list[dict], references: dict[str, list[dict]], ecart_min: float = ECART_MIN,
             index: dict | None = None, controle: tuple[dict, dict] | None = None,
             hors_consensus: set[str] | None = None) -> list[dict]:
    """Opportunités (cote française × probabilité juste − 1 ≥ ecart_min). `controle` = (état du contrôle
    de conformité, matchs suspects) : une cote dont l'intitulé n'est pas contrôlé conforme est marquée
    suspecte (pas de pari)."""
    index = index if index is not None else indexer(francais, references)
    opportunites = []
    for l in francais:
        if hors_perimetre_anj(l):
            continue
        if l["periode"].endswith("?") or not l.get("cote"):
            continue
        t_fr, debut = _t(l.get("collecte")), _t(l.get("debut"))
        if not t_fr:
            continue
        if debut and t_fr and debut <= t_fr:
            continue
        k = cle(l)
        trouvees = {}
        for nom in references:
            r = index[nom].get(l["match_id"], {}).get(k)
            if not r:
                continue
            if not CT.contemporaines(l, r):
                continue
            trouvees[nom] = r
        controle_raison = CT.raison(l, *controle) if controle and trouvees else None
        desaccord = False
        # Une référence hors consensus garde sa table de paris. Elle ne change
        # ni la moyenne partagée, ni le désaccord des tables déjà en place.
        membres = {n: r for n, r in trouvees.items() if n not in (hors_consensus or ())}
        if len(membres) >= 2:
            justes = [1 / r["proba_juste"] for r in membres.values()]
            desaccord = max(justes) / min(justes) > DESACCORD_MAX
            # Mélange équipondéré des probabilités, pas des cotes inverses :
            # sur un marché complet commun, la somme des probabilités reste 1.
            p = sum(r["proba_juste"] for r in membres.values()) / len(membres)
            trouvees["Consensus"] = {"proba_juste": p, "cote_juste": 1 / p, "collecte": l["collecte"],
                                     "domicile": l["domicile"], "exterieur": l["exterieur"],
                                     "sources": "+".join(sorted(membres)),
                                     "lectures_references": {n: r.get("collecte") for n, r in membres.items()},
                                     "composantes": {n: round(1 / r["proba_juste"], 3) for n, r in membres.items()},
                                     # Preuve d'association de chaque référence moyennée. Champ distinct :
                                     # score_association reste vide pour ne rien changer aux règles figées.
                                     "preuves_composantes": {n: {"ressemblance_noms": r.get("score_association"),
                                                                 "match_id_reference": r.get("match_id")}
                                                             for n, r in membres.items()}}
        for nom, r in trouvees.items():
            ecart = l["cote"] * r["proba_juste"] - 1
            if ecart < ecart_min:
                continue
            suspect = controle_raison
            if not suspect and desaccord:
                suspect = "références en désaccord"
            elif not suspect and ecart > (ECART_SUSPECT if l["cote"] <= 10 else ECART_SUSPECT_GROSSES):
                suspect = "écart trop grand"
            opportunites.append({
                "detecte": l["collecte"], "bookmaker": l["source"], "sport": l["sport"], "ligue": l.get("ligue"),
                "collecte_debut": l.get("collecte_debut"), "collecte_recue": l.get("collecte_recue"),
                "match_id": l["match_id"], "domicile": l["domicile"], "exterieur": l["exterieur"],
                "debut": l["debut"], "marche": l["marche"], "periode": l["periode"], "ligne": l.get("ligne"),
                "issue": l["issue"], "pari": libelle_pari(l), "libelle_bookmaker": l.get("libelle"),
                "cote": l["cote"], "reference": nom, "cote_juste": round(1 / r["proba_juste"], 3),
                "cote_reference": r.get("cote"), "proba_juste": round(r["proba_juste"], 5),
                "ecart": round(ecart, 4), "lu_reference": r.get("collecte"),
                "lectures_references": r.get("lectures_references"),
                "match_reference": f'{r.get("domicile")} - {r.get("exterieur")}',
                "score_association": r.get("score_association"), "sources": r.get("sources"),
                "match_id_reference": r.get("match_id"), "reference_inversee": r.get("inverse"),
                "composantes": r.get("composantes"), "preuves_composantes": r.get("preuves_composantes"),
                "controle": _controle_du_groupe(l, controle),
                "lien": l.get("lien"), "suspect": suspect,
                "pariable": not bool(suspect)})
    return opportunites


def _controle_du_groupe(l: dict, controle: tuple[dict, dict] | None) -> dict | None:
    """État du contrôle de conformité de l'intitulé au moment de la détection (trace du pari)."""
    if not controle:
        return None
    g = (controle[0] or {}).get("groupes", {}).get(CT.cle_groupe(l)) or {}
    return {k: g.get(k) for k in ("statut", "n", "mediane")} if g else None


def cotes_justes_depuis(index: dict, hors_consensus: set[str] | None = None) -> dict[tuple, dict[str, tuple]]:
    """Même table que ``index_cotes_justes``, lue sur un index déjà associé.

    Évite de relancer l'association (environ une minute) à la clôture.
    """
    out: dict[tuple, dict[str, tuple]] = {}
    for nom, par_match in (index or {}).items():
        if not isinstance(par_match, dict):
            continue
        for mid_fr, par_cle in par_match.items():
            if not isinstance(par_cle, dict):
                continue
            for k, ligne in par_cle.items():
                if not isinstance(ligne, dict) or "proba_juste" not in ligne:
                    continue
                out.setdefault((mid_fr, k), {})[nom] = (ligne["proba_juste"], ligne.get("collecte"))
    hors = hors_consensus or ()
    for v in out.values():
        membres = {n: x for n, x in v.items() if n not in hors}
        if len(membres) >= 2:            # lu à l'heure de la plus ancienne des références qui le composent
            heures = [_t(t) for _, t in membres.values()]
            v["Consensus"] = (sum(p for p, _ in membres.values()) / len(membres),
                              min(heures).isoformat(timespec="seconds") if all(h and h.tzinfo for h in heures) else None)
    return out


def index_cotes_justes(francais: list[dict], references: dict[str, list[dict]],
                       hors_consensus: set[str] | None = None) -> dict[tuple, dict[str, tuple]]:
    """(match français, clé) -> {référence: (probabilité juste, heure de lecture)} : sert à suivre la cote
    juste jusqu'au coup d'envoi (CLV) des paris déjà pris, même quand l'écart a disparu."""
    return cotes_justes_depuis(indexer(francais, references), hors_consensus)


# --------------------------------------------------------------------------- libellés

PERIODES = {"MATCH": "", "MT1": " (1re mi-temps)", "MT2": " (2e mi-temps)", "TEMPS_REG": " (temps réglementaire)",
            "P1": " (1re période)", "P2": " (2e période)", "P3": " (3e période)", "QT1": " (1er quart-temps)",
            "QT2": " (2e quart-temps)", "QT3": " (3e quart-temps)", "QT4": " (4e quart-temps)",
            "SET1": " (1er set)", "SET2": " (2e set)"}


def _nombre(x) -> str:
    return (f"{x:+g}" if x else "0").replace(".", ",")


def libelle_pari(l: dict) -> str:
    m, i, ligne = l["marche"], l["issue"], l.get("ligne")
    dom, ext = l["domicile"], l["exterieur"]
    eq = {"DOM": dom, "EXT": ext, "NUL": "Match nul"}
    unite = ""
    for p, u in (("CORNERS_", " corners"), ("JEUX_", " jeux"), ("SETS_", " sets")):
        if m.startswith(p):
            m, unite = m[len(p):], u
    if m in ("RESULTAT_1N2", "VAINQUEUR", "DRAW_NO_BET"):
        s = eq.get(i, i) + (" (remboursé si nul)" if m == "DRAW_NO_BET" else "")
    elif m == "HANDICAP":
        h = ligne if i == "DOM" else -ligne
        s = f"{eq[i]} {_nombre(h)}{unite}"
    elif m == "HANDICAP_3":
        s = f"{eq.get(i, i)} (handicap {dom} {_nombre(ligne)})"
    elif m in ("TOTAL", "TOTAL_DOM", "TOTAL_EXT"):
        qui = {"TOTAL": "", "TOTAL_DOM": f" {dom}", "TOTAL_EXT": f" {ext}"}[m]
        defaut = {"football": " buts", "hockey": " buts", "handball": " buts", "basket": " points",
                  "football_americain": " points", "rugby": " points", "volley": " points"}.get(l.get("sport"), "")
        s = f"{'Plus' if i == 'PLUS' else 'Moins'} de {str(ligne).replace('.', ',')}{unite or defaut}{qui}"
    elif m == "DOUBLE_CHANCE":
        s = {"HOME_DRAW": f"{dom} ou nul", "HOME_AWAY": f"{dom} ou {ext}", "DRAW_AWAY": f"Nul ou {ext}"}[i]
    elif m == "BOTH_TEAMS_TO_SCORE":
        s = "Les deux équipes marquent : " + ("oui" if i == "YES" else "non")
    elif m == "CORRECT_SCORE":
        s = f"Score exact {i}"
    elif m == "HALF_TIME_FULL_TIME":
        a, b = i.split("/")
        s = f"Mi-temps/fin : {eq[a]} / {eq[b]}"
    else:
        s = f"{m} {i} {ligne or ''}".strip()
    return re.sub(r"\s+", " ", s + PERIODES.get(l["periode"], f" ({l['periode']})")).strip()
