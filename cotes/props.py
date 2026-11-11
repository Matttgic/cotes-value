"""Rapprochement des paris joueurs : un book français contre une référence sharp.

Pinnacle (cote juste, marge retirée), Betfair ou Polymarket. Jamais un book français
contre un autre. Les stratégies décorées ``@figer_selecteur`` ne voient pas ces lignes :
``comparaison.comparer`` les ignore, et ``pariable`` reste faux.
"""
from __future__ import annotations

from .comparaison import ECART_MIN, _t, indexer
from .controle import contemporaines
from .correspondance import ressemblance
from .joueurs import cle_joueur, est_joueur
from .marches import cle
from .temps import instant_utc

REFERENCES = ("Pinnacle", "Betfair", "Polymarket")


def _sharp(references: dict[str, list[dict]]) -> dict[str, list[dict]]:
    out = {}
    for nom in REFERENCES:
        lignes = [l for l in (references.get(nom) or []) if est_joueur(l.get("marche"))]
        if lignes:
            out[nom] = lignes
    return out


def comparer(francais: list[dict], references: dict[str, list[dict]],
             ecart_min: float = ECART_MIN) -> list[dict]:
    """Une ligne par cote française joueur qui a la même clé chez une référence sharp.

    L'écart est ``cote × probabilité juste − 1``. ``valeur`` est vrai au seuil habituel
    (2 %). Aucune de ces lignes n'est un pari.
    """
    fr = [l for l in francais if est_joueur(l.get("marche")) and cle_joueur(l.get("joueur"))]
    refs = _sharp(references)
    if not fr or not refs:
        return []
    index = indexer(fr, refs)
    out = []
    for l in fr:
        if l.get("periode") in (None, "") or str(l.get("periode")).endswith("?") or not l.get("cote"):
            continue
        if not _t(l.get("collecte")):
            continue
        k = cle(l)
        for nom in refs:
            r = index.get(nom, {}).get(l.get("match_id"), {}).get(k)
            if not r or not contemporaines(l, r):
                continue
            if not r.get("proba_juste"):
                continue
            ecart = round(l["cote"] * r["proba_juste"] - 1, 4)
            out.append({
                "bookmaker": l.get("source"), "sport": l.get("sport"), "ligue": l.get("ligue") or r.get("ligue"),
                "match_id": l.get("match_id"), "match_id_reference": r.get("match_id"),
                "domicile": l.get("domicile"), "exterieur": l.get("exterieur"),
                "debut": l.get("debut"), "joueur": l.get("joueur"), "cle_joueur": cle_joueur(l.get("joueur")),
                "marche": l.get("marche"),
                "periode": l.get("periode"), "ligne": l.get("ligne"), "issue": l.get("issue"),
                "cote": l.get("cote"), "reference": nom, "cote_juste": round(1 / r["proba_juste"], 3),
                "cote_reference": r.get("cote"), "proba_juste": round(r["proba_juste"], 5),
                "ecart": ecart, "valeur": ecart >= ecart_min, "pariable": False,
                "detecte": l.get("collecte"), "lu_reference": r.get("collecte"),
                "match_reference": f'{r.get("domicile")} - {r.get("exterieur")}',
            })
    return out


def _meme_rencontre(a: dict, b: dict) -> bool:
    da, db = instant_utc(a.get("debut")), instant_utc(b.get("debut"))
    if da is None or db is None or abs((da - db).total_seconds()) > 3 * 3600:
        return False
    direct = min(ressemblance(a.get("domicile"), b.get("domicile")),
                 ressemblance(a.get("exterieur"), b.get("exterieur")))
    inverse = min(ressemblance(a.get("domicile"), b.get("exterieur")),
                  ressemblance(a.get("exterieur"), b.get("domicile")))
    return max(direct, inverse) >= 0.85


def comparer_fanduel(fanduel: list[dict], pinnacle: list[dict]) -> dict:
    """Props FanDuel contre Pinnacle (``comparer_reference``)."""
    return comparer_reference(fanduel, pinnacle, "fanduel")


def comparer_reference(fanduel: list[dict], pinnacle: list[dict], source: str = "fanduel") -> dict:
    """Écart de probabilité juste d'une référence de props (FanDuel, DraftKings) − Pinnacle, et taux d'accord du
    côté favori.

    C'est une référence : le résultat ne contient que des comptes. Une ligne
    sans jumelle Pinnacle (joueur, statistique, ligne, rencontre) augmente
    ``non_rapproches`` et n'est pas nommée.
    """
    def plus(lignes, source):
        out = []
        for l in lignes or []:
            if source and l.get("source") != source:
                continue
            if not est_joueur(l.get("marche")) or l.get("issue") != "PLUS":
                continue
            if not l.get("proba_juste") or not cle_joueur(l.get("joueur")):
                continue
            try:
                round(float(l.get("ligne")), 2)
            except (TypeError, ValueError):
                continue
            out.append(l)
        return out

    fd = plus(fanduel, source)
    pin = plus(pinnacle, "pinnacle")
    index: dict[tuple, list[dict]] = {}
    for l in pin:
        cle_l = (l.get("sport"), l.get("marche"), round(float(l["ligne"]), 2), cle_joueur(l.get("joueur")))
        index.setdefault(cle_l, []).append(l)
    ecarts = []
    accords = 0
    non = 0
    for l in fd:
        cle_l = (l.get("sport"), l.get("marche"), round(float(l["ligne"]), 2), cle_joueur(l.get("joueur")))
        candidats = [p for p in index.get(cle_l, []) if _meme_rencontre(l, p)]
        if len(candidats) != 1:
            non += 1
            continue
        p = candidats[0]
        ecart = l["proba_juste"] - p["proba_juste"]
        ecarts.append(ecart)
        cote_fd, cote_pin = l["proba_juste"] - 0.5, p["proba_juste"] - 0.5
        if cote_fd * cote_pin > 0 or (abs(cote_fd) < 1e-9 and abs(cote_pin) < 1e-9):
            accords += 1
    n = len(ecarts)
    return {
        source: len(fd), "pinnacle": len(pin), "rapproches": n, "non_rapproches": non,
        "ecart_proba_moyen": round(sum(ecarts) / n, 5) if n else None,
        "ecart_absolu_moyen": round(sum(abs(x) for x in ecarts) / n, 5) if n else None,
        "accord": round(accords / n, 4) if n else None,
        "reference_seule": True,
    }


MARCHES_MATCH = ("VAINQUEUR", "HANDICAP", "TOTAL")


def comparer_matchs(lignes: list[dict], pinnacle: list[dict], source: str = "draftkings") -> dict:
    """Vainqueur, handicap et total d'une référence (DraftKings) contre Pinnacle, match entier : écart de
    probabilité juste et accord du favori, par sport. Des comptes seulement, aucune ligne nommée.

    Même rencontre (± 3 h, équipes à 0,85), même marché et même ligne. Équipes inversées entre les deux sources :
    domicile et extérieur s'échangent, et le handicap change de signe. Une issue par marché (domicile ou « plus »),
    l'autre s'en déduit."""
    def lue(l, origine):
        return (l.get("source") == origine and l.get("marche") in MARCHES_MATCH and l.get("periode") == "MATCH"
                and l.get("proba_juste") and l.get("issue") in ("DOM", "PLUS"))

    def cle(l, inverse=False):
        ligne = l.get("ligne")
        if l["marche"] == "VAINQUEUR":
            ligne = None
        elif isinstance(ligne, bool) or not isinstance(ligne, (int, float)):
            return None
        elif inverse and l["marche"] == "HANDICAP":
            ligne = -ligne
        return (l.get("sport"), l["marche"], None if ligne is None else round(float(ligne), 2))

    index: dict[tuple, list[dict]] = {}
    for l in pinnacle or []:
        if lue(l, "pinnacle") and cle(l):
            index.setdefault(cle(l), []).append(l)
    par_sport: dict[str, list[float]] = {}
    accords: dict[str, int] = {}
    lues = non = 0
    for l in lignes or []:
        if not lue(l, source) or not cle(l):
            continue
        lues += 1
        trouve = None
        for inverse in (False, True):
            for p in index.get(cle(l, inverse), []):
                da, db = instant_utc(l.get("debut")), instant_utc(p.get("debut"))
                if da is None or db is None or abs((da - db).total_seconds()) > 3 * 3600:
                    continue
                a, b = (("exterieur", "domicile") if inverse else ("domicile", "exterieur"))
                if min(ressemblance(l.get("domicile"), p.get(a)), ressemblance(l.get("exterieur"), p.get(b))) >= 0.85:
                    # vainqueur et handicap : la probabilité « domicile » de l'un est celle « extérieur » de l'autre
                    proba_pin = 1 - p["proba_juste"] if inverse and l["marche"] != "TOTAL" else p["proba_juste"]
                    trouve = (trouve or []) + [proba_pin]
        if not trouve or len(trouve) != 1:
            non += 1
            continue
        ecart = l["proba_juste"] - trouve[0]
        par_sport.setdefault(l.get("sport"), []).append(ecart)
        accords[l.get("sport")] = accords.get(l.get("sport"), 0) + ((l["proba_juste"] - 0.5) * (trouve[0] - 0.5) >= 0)
    tous = [e for es in par_sport.values() for e in es]
    resume = lambda es: {"rapproches": len(es),  # noqa: E731
                         "ecart_absolu_moyen": round(sum(abs(x) for x in es) / len(es), 5) if es else None}
    return {source: lues, "non_rapproches": non, **resume(tous),
            "ecart_proba_moyen": round(sum(tous) / len(tous), 5) if tous else None,
            "accord": round(sum(accords.values()) / len(tous), 4) if tous else None,
            "par_sport": {s: {**resume(es), "accord": round(accords[s] / len(es), 4)} for s, es in sorted(par_sport.items())},
            "reference_seule": True}


def compter(lignes: list[dict]) -> dict[str, int]:
    """Nombre de lignes JOUEUR par source (pinnacle, Winamax, Unibet, …)."""
    out: dict[str, int] = {}
    for l in lignes:
        if not est_joueur(l.get("marche")):
            continue
        nom = str(l.get("source") or l.get("bookmaker") or "?")
        out[nom] = out.get(nom, 0) + 1
    return out
