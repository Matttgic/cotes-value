"""Statut vivant des alertes (audit du 20/11/2026, priorité 9) : ne plus jouer une value disparue.

Chaque cycle relit la cote des paris déjà alertés (``prix_revu`` de ``simulation.suivre_prix``). Une alerte envoyée
depuis moins de ``FENETRE_H`` heures, dont le match n'a pas commencé, passe :

- « cote baissée » : la cote relue est sous la cote alertée, mais encore au-dessus de la cote minimale ;
- « plus jouable » : la cote relue est sous la cote minimale (écart < 2 %).

Pushover ne sait pas remplacer un message : une relance discrète (priorité −1) part une seule fois par statut.
Le web push reçoit les statuts dans ``notifications.json`` (``statuts``) et remplace la notification (même ``tag``).
Betclic corrige une cote en 14 min médianes, PMU en 65 (audit) : la relance arrive avant la plupart des mises.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from cotes.temps import instant_utc

FENETRE_H = 3
COTE_BAISSEE, PLUS_JOUABLE = "cote_baissee", "plus_jouable"
TITRES = {COTE_BAISSEE: "Cote baissée", PLUS_JOUABLE: "Plus jouable"}


def _fr(x: float) -> str:
    return f"{x:.2f}".replace(".", ",")


def statut(p: dict) -> tuple[str, float] | None:
    """(statut, cote relue) d'un pari alerté, ou None s'il reste jouable ou n'a pas été relu."""
    from cotes.notifications import COTE_MIN_MARGE, COTE_MIN_PLANCHER
    prix, cote, juste = p.get("prix_revu"), p.get("cote"), p.get("cote_juste")
    if not all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in (prix, cote)):
        return None
    if prix >= cote - 1e-9:
        return None
    cote_min = max(COTE_MIN_PLANCHER, juste * COTE_MIN_MARGE) if isinstance(juste, (int, float)) else None
    if cote_min is not None and prix < cote_min - 1e-9:
        return PLUS_JOUABLE, prix
    return COTE_BAISSEE, prix


def statuts(paris: list[dict], envoyes: dict, maintenant: datetime) -> list[dict]:
    """Statuts des alertes envoyées (``envoyes`` : id d'alerte → date d'envoi), un par alerte, le plus grave."""
    from cotes.notifications import empreinte_prix
    limite = maintenant - timedelta(hours=FENETRE_H)
    out: dict[str, dict] = {}
    for p in paris:
        if p.get("statut") != "en_cours":
            continue
        debut = instant_utc(p.get("debut"))
        if debut is None or debut <= maintenant:
            continue
        aid = empreinte_prix(p)
        envoi = instant_utc(envoyes.get(aid)) if isinstance(envoyes.get(aid), str) else None
        if envoi is None or envoi < limite:
            continue
        s = statut(p)
        if s is None or (aid in out and out[aid]["statut"] == PLUS_JOUABLE):
            continue
        out[aid] = {"id": aid, "statut": s[0], "cote": p["cote"], "cote_relue": s[1], "relue_le": p.get("prix_revu_le"),
                    "match": f'{p.get("domicile", "")} – {p.get("exterieur", "")}', "pari": str(p.get("pari") or "")[:180],
                    "bookmaker": p.get("bookmaker") or "", "debut": p.get("debut")}
    return sorted(out.values(), key=lambda s: s["id"])


def relances(liste: list[dict], envoyes: dict) -> list[dict]:
    """Statuts pas encore relancés sur Pushover (clé ``<id>:<statut>`` dans ``envoyes``)."""
    return [s for s in liste if f'{s["id"]}:{s["statut"]}' not in envoyes]


def message(s: dict) -> dict:
    """Champs Pushover d'une relance : discrète (priorité −1), sans lien."""
    corps = (f'{s["match"]}\n{s["pari"]}\nCote {_fr(s["cote"])} → {_fr(s["cote_relue"])}'
             + ("\nNe plus jouer : la value a disparu." if s["statut"] == PLUS_JOUABLE else ""))
    return {"title": f'{TITRES[s["statut"]]} · {s["bookmaker"]}'[:250], "message": corps[:1000], "priority": -1}
