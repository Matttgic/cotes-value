"""Claude · Méthode humaine : la stratégie que Claude jouerait lui-même s'il était humain, pour gagner, avec une
quinzaine de paris par jour au plus (docs/strategie-claude-humain.md).

Choisie le 11/11/2026 sur les 3 801 paris uniques réglés à cote ≤ 5 (38 jours), en privilégiant la CLV (battre la
cote de clôture Pinnacle), signal bien plus stable que le ROI :

- écart ≥ 5 % : en dessous, la CLV est quasi nulle (+0,1 % à 2–3 %, 40 % du volume) ;
- cote 1,50–3,00 : assez de paris gagnés pour suivre à la main, peu de hasard ;
- Betclic, PMU, Unibet seulement : OlyBet, NetBet et Winamax ont une CLV négative ;
- références Pinnacle, Polymarket, Betfair, Matchbook (Kalshi : CLV −10 %, Smarkets : −3 %) ;
- pas de mi-temps (MT1, MT2), ni score exact ni mi-temps/fin ;
- un pari par match, 20 par jour au plus : jouable par une personne, sans paris liés entre eux.

Sur l'historique (choisi sur ces mêmes données, donc flatteur) : 578 paris, environ 15 par jour, CLV +5,8 %, ROI
+4,7 % ± 4,2. Seul le suivi depuis DEBUT compte (pas de rejeu). Écart borné à 25 % : au-delà, c'est presque
toujours un marché mal reconnu.

La sélection ne lit jamais statut, gain, CLV ni cote de clôture.
"""
from __future__ import annotations

from zoneinfo import ZoneInfo

from .decisions import figer_selecteur
from .laboratoire import heure
from .strategie_commune import nombre_fini, preuve_de
from .strategie_gemini_defi import cle_cote, ecart_pct

DEBUT = "2026-11-12T00:00:00+00:00"
PARIS = ZoneInfo("Europe/Paris")

CLAUDE_HUMAIN = {
    "cle": "claude_humain", "nom": "Claude · Méthode humaine", "court": "Claude humain",
    "debut": DEBUT, "version": "1", "mise": 10.0, "maximum_jour": 20, "max_par_match": 1, "auteur": "Claude",
    "prospectif_seulement": True,
    "references": ("Pinnacle", "Polymarket", "Betfair", "Matchbook"),
    "bookmakers": ("Betclic", "PMU", "Unibet"),
    "marches_exclus": ("CORRECT_SCORE", "HALF_TIME_FULL_TIME"),
    "periodes_exclues": ("MT1", "MT2"),
    "cote_min": 1.50, "cote_max": 3.00, "ecart_min_pct": 5.0, "ecart_max_pct": 25.0,
    "regles": "La stratégie de Claude : ce qu'il jouerait lui-même s'il était humain, pour gagner · écart ≥ 5 % "
              "contre Pinnacle, Polymarket, Betfair ou Matchbook · cote 1,50–3,00 · Betclic, PMU ou Unibet · "
              "pas de mi-temps · un pari par match, 20 par jour au plus · mise fictive 10 €",
}


def motif_refus_claude_humain(p: dict, c: dict = CLAUDE_HUMAIN) -> str | None:
    """Raison du refus, ou None si la détection passe la règle. Bornes incluses. Ne lit que ce qui est connu à
    l'instant de la détection."""
    if p.get("reference") not in c["references"]:
        return "référence hors périmètre"
    if p.get("bookmaker") not in c["bookmakers"]:
        return "bookmaker hors périmètre"
    if p.get("marche") in c["marches_exclus"]:
        return "marché exclu"
    if p.get("periode") in c["periodes_exclues"]:
        return "mi-temps"
    if preuve_de(p).get("equipes_inversees") is True:
        return "équipes inversées"
    cote = nombre_fini(p.get("cote"))
    if cote is None or not c["cote_min"] <= cote <= c["cote_max"]:
        return "cote hors intervalle"
    e = ecart_pct(p)
    if e is None or not c["ecart_min_pct"] <= e <= c["ecart_max_pct"]:
        return "écart hors intervalle"
    t, debut = heure(p.get("detecte")), heure(p.get("debut"))
    if not t or not debut:
        return "date absente ou invalide"
    if debut <= t:
        return "match déjà commencé"
    return None


def selection_claude_humain(paris: list[dict], c: dict = CLAUDE_HUMAIN, depart: str | None = None) -> set[int]:
    """Dans l'ordre d'arrivée depuis le lancement : la première détection qui passe la règle, une par cote
    française, une par match, ``maximum_jour`` par jour (heure de Paris). Une détection refusée ne consomme rien."""
    t0 = heure(depart or c["debut"])
    if t0 is None:
        return set()
    candidats = sorted((p for p in paris if heure(p.get("detecte")) and heure(p["detecte"]) >= t0
                        and motif_refus_claude_humain(p, c) is None), key=lambda p: heure(p["detecte"]))
    retenus, cotes, matchs, jours = set(), set(), set(), {}
    for p in candidats:
        cle, match = cle_cote(p), p.get("match_id")
        jour = heure(p["detecte"]).astimezone(PARIS).date()
        if cle in cotes or match in matchs or jours.get(jour, 0) >= c["maximum_jour"]:
            continue
        cotes.add(cle)
        matchs.add(match)
        jours[jour] = jours.get(jour, 0) + 1
        retenus.add(id(p))
    return retenus


@figer_selecteur(CLAUDE_HUMAIN["cle"])
def paris_claude_humain(paris, depuis=None):
    """Claude · Méthode humaine (figée au lancement, 12/11/2026). Pas de rejeu."""
    if depuis is not None:            # pas de rejeu : seul le suivi depuis le lancement compte
        return set()
    return selection_claude_humain(paris)


SELECTEURS = {CLAUDE_HUMAIN["cle"]: paris_claude_humain}
