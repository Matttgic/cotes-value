"""Bankroll automatique des alertes Pushover (docs/strategie-optimisee.md, « Bankroll automatique »).

Le système ne voit pas les comptes chez les bookmakers : il suppose que chaque alerte envoyée est jouée à la mise
affichée. Départ : ``PUSHOVER_BANKROLL`` ; chaque alerte envoyée est notée (``bankroll.json``), et son gain est ajouté
quand le pari est réglé (gain du pari ramené à la mise jouée). Changer ``PUSHOVER_BANKROLL`` repart de ce chiffre :
c'est ainsi qu'on recale la bankroll sur la réalité. ``PUSHOVER_BANKROLL_AUTO=non`` coupe le calcul (mises sur
``PUSHOVER_BANKROLL``).

Bankroll de mise (celle qui sert au calcul des mises), règle asymétrique :
- elle **baisse tout de suite** quand la bankroll calculée passe 10 % sous elle (elle prend alors cette valeur) ;
- elle **monte par paliers de +20 %**, seulement quand la bankroll calculée atteint le palier suivant.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

FICHIER = "bankroll.json"
BAISSE = 0.90           # sous 90 % de la bankroll de mise : on la ramène à la bankroll calculée
PALIER = 1.20           # palier de hausse
OUBLI_JOURS = 10        # alerte sans pari retrouvé après ce délai : retirée sans gain (aucun résultat inventé)
HISTORIQUE_MAX = 300
EN_COURS = ("en_cours", "a_regler")


def _nombre(x) -> float | None:
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) and x == x else None


def depart(env) -> float:
    from cotes.alertes.pushover import _bankroll
    return _bankroll(env)


def actif(env) -> bool:
    return str(env.get("PUSHOVER_BANKROLL_AUTO", "") or "oui").strip().lower() not in ("non", "off", "0", "false")


def lire(donnees: Path) -> dict:
    try:
        etat = json.loads((donnees / FICHIER).read_text())
        return etat if isinstance(etat, dict) else {}
    except (OSError, ValueError):
        return {}


def ecrire(donnees: Path, etat: dict) -> None:
    from cotes.depot.json_io import ecrire_json
    ecrire_json(donnees / FICHIER, etat)


def bankroll_de_mise(bankroll: float, actuelle: float) -> float:
    """Règle asymétrique : baisse immédiate sous 90 %, hausse par paliers de +20 %."""
    if bankroll < actuelle * BAISSE:
        return round(bankroll, 2)
    while bankroll >= actuelle * PALIER:
        actuelle *= PALIER
    return round(actuelle, 2)


def mettre_a_jour(etat: dict, paris: list[dict], env, maintenant: datetime) -> dict:
    """Recale sur ``PUSHOVER_BANKROLL`` s'il a changé, ajoute les gains des alertes réglées, applique la règle de
    mise. Renvoie l'état (modifié sur place, ou neuf)."""
    from cotes.notifications import empreinte_prix
    d = depart(env)
    if _nombre(etat.get("depart")) != d:
        etat.clear()
        etat.update({"depart": d, "depart_le": maintenant.isoformat(timespec="seconds"), "bankroll": d,
                     "mise_sur": d, "ouvertes": {}, "historique": []})
    etat.setdefault("ouvertes", {})
    etat.setdefault("historique", [])
    ouvertes = etat["ouvertes"]
    if ouvertes:
        regles = {}
        for p in paris:
            if p.get("statut") not in EN_COURS and _nombre(p.get("mise")) and _nombre(p.get("gain")) is not None:
                regles.setdefault(empreinte_prix(p), p)
        for aid, o in list(ouvertes.items()):
            p, mise = regles.get(aid), _nombre(o.get("mise")) or 0.0
            if p is not None:
                gain = round(mise * p["gain"] / p["mise"], 2)
            else:
                try:
                    trop_vieux = datetime.fromisoformat(o.get("le")) < maintenant - timedelta(days=OUBLI_JOURS)
                except (TypeError, ValueError):
                    trop_vieux = True
                if not trop_vieux:
                    continue
                gain = 0.0
            etat["bankroll"] = round(etat["bankroll"] + gain, 2)
            etat["historique"].append({**o, "id": aid, "gain": gain, "statut": p.get("statut") if p else "introuvable",
                                       "regle_le": maintenant.isoformat(timespec="seconds")})
            del ouvertes[aid]
        etat["historique"] = etat["historique"][-HISTORIQUE_MAX:]
    etat["mise_sur"] = bankroll_de_mise(etat["bankroll"], _nombre(etat.get("mise_sur")) or d)
    etat["maj"] = maintenant.isoformat(timespec="seconds")
    return etat


def noter(etat: dict, alertes: list[dict], maintenant: datetime) -> None:
    """Note la mise affichée de chaque alerte envoyée (mise unitaire × nombre de stratégies cochées), comme
    ``webhook.message_ntfy``. Une alerte sans mise conseillée n'est pas notée."""
    from cotes.alertes.pushover import BANKROLL_REFERENCE
    from cotes.recap_jouables import mise_arrondie
    for a in alertes:
        kelly = _nombre(a.get("mise_kelly"))
        if not kelly or kelly <= 0 or a["id"] in etat["ouvertes"]:
            continue
        u = mise_arrondie(kelly * etat["mise_sur"] / BANKROLL_REFERENCE)
        mises = a.get("mises") if isinstance(a.get("mises"), int) and not isinstance(a.get("mises"), bool) else 1
        etat["ouvertes"][a["id"]] = {"mise": float(u * max(1, mises)), "le": maintenant.isoformat(timespec="seconds"),
                                    "pari": str(a.get("selection") or a.get("pari") or "")[:80],
                                    "cote": a.get("cote")}
