"""Mise en pause automatique des stratégies qui perdent clairement contre la cote de clôture.

Une stratégie en pause ne sélectionne plus aucun pari détecté après le début de sa pause : ni décision figée, ni
alerte, ni nouvelle ligne dans son suivi. Son historique reste affiché tel quel.

Critères (``a_mettre_en_pause``), sur son suivi depuis le lancement (mise fixe) :
- au moins ``MIN_REGLES`` paris réglés, dont ``MIN_CLV`` avec une CLV mesurée ;
- CLV moyenne par pari clairement négative : même la borne haute à 95 % (unilatérale) est sous zéro ;
- CLV moyenne par match (``clv_ajustee`` de la note) négative aussi.

Jamais en pause : les bases du Bilan, les 7 stratégies de base et la convergence (leurs votes alimentent d'autres
stratégies figées) et les membres d'une fusion active (ses membres sont figés).

État : ``pauses.json`` dans « donnees », écrit par la construction du site (``mettre_a_jour``) et lu au début de
chaque construction, du cycle et de l'envoi des alertes (``charger``). Une pause décidée à une construction agit à
partir de la suivante. Pour relancer une stratégie, retirer sa ligne de ``pauses.json``.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from math import sqrt
from pathlib import Path
from .temps import instant as _date

FICHIER = "pauses.json"
MIN_REGLES = 200
MIN_CLV = 100
Z95 = 1.645
# Stratégies retirées à la main : plus aucun nouveau pari ni alerte ; l'historique reste, masqué par défaut sur la
# page Stratégies (« Afficher › Retirées »). Règles et chiffres gardés dans docs/strategies-retirees.md.
# Champs : id (ligne du site), motif (badge), depuis (défaut RETIREES_DEPUIS), roi et roi_haut (%, 10 € fixes, par
# match, borne haute à 95 %), matchs, regles. ``votes`` : stratégie de base dont les votes font tourner Convergence ≥ 2 ;
# sa sélection continue (sinon cette règle lancée changerait), seuls l'affichage et les alertes s'arrêtent.
RETIREES_DEPUIS = "2026-11-19T22:00:00+00:00"
RETIREES_27_11 = "2026-11-27T00:00:00+00:00"
RETIREES_27_11_CLV = "2026-11-27T18:00:00+00:00"
_PERDANTE_27_11 = {"motif": "ROI négatif sur plus de 100 paris réglés", "depuis": RETIREES_27_11}
_MORTE_27_11 = {"motif": "ne prend plus de paris", "depuis": RETIREES_27_11}
_SOUS_REGLE_27_11 = {"motif": "CLV sous celle de la règle principale, même au mieux", "depuis": RETIREES_27_11_CLV}
RETIREES = {
    # 19/11/2026 : perdantes même dans le meilleur cas, alors que leur CLV paraît bonne.
    "claude_defi_5": {"id": "Claude Défi 5 · Books lents, cotes courtes", "roi": -26.6, "roi_haut": -4.0, "matchs": 73},
    "claude_fusion": {"id": "Claude Fusion · Défi 4 + Défi 5", "roi": -25.8, "roi_haut": -2.9, "matchs": 93},
    "claude_defi_2": {"id": "Claude Défi 2 · Handicaps", "roi": -31.0, "roi_haut": -2.6, "matchs": 26},
    "claude_defi_1": {"id": "Claude Défi 1 · Gros écart 12 h", "roi": -22.1, "roi_haut": 2.4, "matchs": 85},
    # 27/11/2026 : ROI négatif à 10 € fixes avec au moins 100 paris réglés (seuil « Trop tôt pour juger » de l'analyste).
    "convergence_3": {"id": "Convergence ≥ 3 hors M3", "roi": -11.8, "roi_haut": 3.2, "matchs": 105, "regles": 106,
                      **_PERDANTE_27_11},
    "defi_1": {"id": "Défi 1 · Écart fort, match proche", "roi": -3.9, "roi_haut": 15.6, "matchs": 109, "regles": 207,
               **_PERDANTE_27_11},
    "conseil_retard": {"id": "Conseil · bookmaker en retard (hors foot)", "roi": -1.8, "roi_haut": 15.3, "matchs": 114,
                       "regles": 114, **_PERDANTE_27_11},
    "gemini_defi_1": {"id": "Gemini Défi 1 · Indoor & Glace", "roi": -1.8, "roi_haut": 14.4, "matchs": 128,
                      "regles": 244, **_PERDANTE_27_11},
    "claude_prudent": {"id": "Claude 1/match · max 10/j", "roi": -1.5, "roi_haut": 9.3, "matchs": 196, "regles": 198,
                       **_PERDANTE_27_11},
    "grok_6": {"id": "Grok 6 · Pinnacle hors foot", "roi": -0.9, "roi_haut": 14.7, "matchs": 124, "regles": 124,
               **_PERDANTE_27_11},
    "grok_10": {"id": "Grok 10 · Valeur Polymarket", "roi": -0.3, "roi_haut": 25.9, "matchs": 64, "regles": 114,
                **_PERDANTE_27_11},
    "gemini_defi_4": {"id": "Gemini Défi 4 · Lignes asiatiques", "roi": -0.2, "roi_haut": 18.2, "matchs": 92,
                      "regles": 181, **_PERDANTE_27_11},
    "liquidite_sure": {"id": "Liquidité sûre", "roi": -0.1, "roi_haut": 17.9, "matchs": 118, "regles": 118,
                       **_PERDANTE_27_11},
    "jules_v2": {"id": "JULES EDGE v2 (rejeu)", "roi": -8.3, "roi_haut": 4.0, "matchs": 170, "regles": 170,
                 "votes": True, **_PERDANTE_27_11},
    "jules": {"id": "JULES EDGE v1 (rejeu)", "roi": -6.6, "roi_haut": 6.8, "matchs": 133, "regles": 133,
              "votes": True, **_PERDANTE_27_11},
    "strategie": {"id": "Claude (rejeu)", "roi": -1.9, "roi_haut": 6.1, "matchs": 412, "regles": 654,
                  "votes": True, **_PERDANTE_27_11},
    "gemini": {"id": "Gemini Argon v1 (rejeu)", "roi": -1.6, "roi_haut": 8.6, "matchs": 181, "regles": 188,
               "votes": True, **_PERDANTE_27_11},
    # 27/11/2026 : plus de paris depuis la règle de prise du 19/11 (Winamax exclu, cote ≤ 5…), ou presque.
    "grok_4": {"id": "Grok 4 · Polymarket low-odds", "regles": 13, "dernier": "2026-11-18", **_MORTE_27_11},
    "grok_5": {"id": "Grok 5 · Multi-sharp low", "regles": 16, "dernier": "2026-11-18", **_MORTE_27_11},
    "optimisee_19_11_polymarket": {"id": "Optimisée 19/11 + Polymarket", "regles": 2, "dernier": "2026-11-22",
                                   **_MORTE_27_11},
    "qwen_persistence": {"id": "Qwen", "regles": 12, "dernier": "2026-11-24", **_MORTE_27_11},
    # 27/11/2026 à 18 h UTC (docs/audit-26-11-strategie.md) : au moins 50 CLV mesurées et borne haute à 95 % de la CLV
    # sous celle de la règle principale (+3,4 %). Plus récentes (Drop Pinnacle, Drop z-score, Néon 1) : gardées.
    "chatgpt": {"id": "ChatGPT v1 (rejeu)", "roi": -8.7, "roi_haut": 13.3, "matchs": 90, "regles": 90,
                "votes": True, **_SOUS_REGLE_27_11},
    "grok_2": {"id": "Grok 2 · Pinnacle low", "roi": -3.9, "roi_haut": 13.8, "matchs": 95, "regles": 95,
               **_SOUS_REGLE_27_11},
    "claude_opus_favoris": {"id": "Claude Opus · Favoris réguliers", "roi": 7.6, "roi_haut": 26.8, "matchs": 111,
                            "regles": 170, **_SOUS_REGLE_27_11},
    "coeur_value": {"id": "Cœur value", "roi": -4.6, "roi_haut": 18.4, "matchs": 63, "regles": 63,
                    **_SOUS_REGLE_27_11},
}
_ACTIVES: dict[str, datetime] = {}


def depuis_retrait(cle: str) -> str:
    """Instant du retrait de ``cle`` (ISO)."""
    return RETIREES[cle].get("depuis", RETIREES_DEPUIS)


def _lire(donnees) -> dict:
    try:
        etat = json.loads((Path(donnees) / FICHIER).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return etat if isinstance(etat, dict) and isinstance(etat.get("pauses"), dict) else {}


def charger(source) -> dict[str, datetime]:
    """Active les pauses de ``pauses.json`` (``source`` : dossier « donnees » ou état déjà lu). Rend {clé: début}."""
    etat = source if isinstance(source, dict) else _lire(source)
    _ACTIVES.clear()
    _ACTIVES.update({cle: _date(depuis_retrait(cle)) for cle, r in RETIREES.items() if not r.get("votes")})
    for cle, p in (etat.get("pauses") or {}).items():
        debut = _date((p or {}).get("depuis"))
        if debut is not None:
            _ACTIVES[cle] = debut
    return dict(_ACTIVES)


def actives() -> dict[str, datetime]:
    """Pauses en vigueur ({clé: début}), telles que ``charger`` les a lues."""
    return dict(_ACTIVES)


def filtrer(paris: list[dict], ids: set[int], cle: str) -> set[int]:
    """``ids`` sans les paris détectés depuis la pause de ``cle`` (inchangés si ``cle`` n'est pas en pause)."""
    limite = _ACTIVES.get(cle)
    if limite is None or not ids:
        return ids
    garde = set()
    for p in paris:
        if id(p) in ids:
            t = _date(p.get("detecte"))
            if t is None or t < limite:
                garde.add(id(p))
    return garde


def stats_clv(valeurs: list[float]) -> tuple[float | None, float | None]:
    """(moyenne, borne haute unilatérale à 95 %) en %, ou (None, None) sous deux valeurs."""
    n = len(valeurs)
    if n < 2:
        return None, None
    m = sum(valeurs) / n
    sd = sqrt(sum((v - m) ** 2 for v in valeurs) / (n - 1))
    return round(100 * m, 2), round(100 * (m + Z95 * sd / sqrt(n)), 2)


def a_mettre_en_pause(stats: dict | None, clvs: list[float]) -> dict | None:
    """Mesures qui justifient la pause, ou None si la stratégie continue."""
    stats = stats or {}
    regles = stats.get("regles") or 0
    par_match = ((stats.get("note") or {}).get("mesures") or {}).get("clv_ajustee")
    if regles < MIN_REGLES or len(clvs) < MIN_CLV or par_match is None or par_match >= 0:
        return None
    moyenne, haute = stats_clv(clvs)
    if haute is None or haute >= 0:
        return None
    return {"regles": regles, "clv_n": len(clvs), "clv": moyenne, "clv_haute": haute, "clv_match": par_match}


def mettre_a_jour(donnees, lignes: list[dict], cle_de: dict[str, str], clvs_de, exemptes: set[str],
                  maintenant: datetime) -> dict:
    """Ajoute les nouvelles pauses à ``pauses.json`` (jamais de reprise automatique) et rend l'état publié.

    ``lignes`` : {id, stats} du classement ; ``cle_de`` : id de ligne → clé de stratégie ; ``clvs_de(id)`` : CLV
    des paris réglés de la ligne ; ``exemptes`` : ids jamais mis en pause. Une erreur d'écriture n'est pas propagée."""
    chemin = Path(donnees) / FICHIER
    etat = _lire(donnees) or {"pauses": {}}
    pauses = dict(etat["pauses"])
    instant = maintenant.isoformat(timespec="seconds")
    for l in lignes:
        cle = cle_de.get(l["id"])
        if not cle or cle in pauses or l["id"] in exemptes:
            continue
        mesures = a_mettre_en_pause(l.get("stats"), clvs_de(l["id"]))
        if mesures:
            pauses[cle] = {"id": l["id"], "depuis": instant, **mesures}
    if pauses != etat["pauses"]:
        etat = {**etat, "pauses": pauses}
        try:
            tmp = chemin.with_name(chemin.name + ".tmp")
            tmp.write_text(json.dumps(etat, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            os.replace(tmp, chemin)
        except OSError:
            pass
    liste = {p["id"]: {k: v for k, v in p.items() if k != "id"} | {"cle": cle}
             for cle, p in pauses.items() if isinstance(p, dict) and p.get("id")}
    liste.update({r["id"]: {k: v for k, v in r.items() if k != "id"} | {"cle": cle, "depuis": depuis_retrait(cle),
                                                                         "retiree": True}
                  for cle, r in RETIREES.items()})
    return {"liste": liste,
            "criteres": {"min_regles": MIN_REGLES, "min_clv": MIN_CLV}}
