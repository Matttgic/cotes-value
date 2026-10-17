"""Règles figées ChatGPT v1 : sélection prospective, sans consulter les résultats.

Vue des nouvelles premières détections Pinnacle déjà enregistrées par le moteur.
Un match Pinnacle = une mise, même s'il apparaît chez plusieurs bookmakers.
Les archives doivent être incluses avant de sélectionner, comme pour le bilan.
"""
from __future__ import annotations

from .decisions import figer_selecteur

from collections import Counter
from datetime import datetime
from math import isfinite
from zoneinfo import ZoneInfo

CHATGPT = {
    "nom": "ChatGPT", "version": "1", "debut": "2026-10-14T03:15:00+00:00",
    "reference": "Pinnacle", "cote_min": 1.5, "cote_max": 3.0,
    "edge_min": 0.03, "edge_max": 0.12, "avance_min_minutes": 15,
    "avance_max_h": 6, "fraicheur_max_minutes": 5,
    "paris_max_jour": 5, "mise": 10.0,
    "bookmakers": ("Winamax", "Betclic", "Unibet", "PMU"),
    "marches": ("RESULTAT_1N2", "VAINQUEUR", "TOTAL", "HANDICAP"),
    "sports": ("football", "basket", "hockey", "baseball", "rugby", "handball",
               "football_americain", "tennis", "volley"),
}
PARIS = ZoneInfo("Europe/Paris")


def _heure(value) -> datetime | None:
    try:
        t = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return t if t.tzinfo is not None else None
    except (TypeError, ValueError):
        return None


def _nombre(value) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        n = float(value)
        return n if isfinite(n) else None
    except (TypeError, ValueError):
        return None


def motif_refus(p: dict, depuis: str = CHATGPT["debut"]) -> str | None:
    """Uniquement des informations connues à la prise ; jamais statut, gain ou CLV.

    `depuis` sert au diagnostic rétrospectif explicite. Le bilan utilise toujours
    la date de lancement figée par défaut.
    """
    if p.get("reference") != CHATGPT["reference"]:
        return "référence différente de Pinnacle sans marge"
    if p.get("bookmaker") not in CHATGPT["bookmakers"] or p.get("sport") not in CHATGPT["sports"]:
        return "bookmaker ou sport hors périmètre"
    if p.get("suspect"):
        return "opportunité suspecte"
    t, debut, lancement = (_heure(p.get("detecte")), _heure(p.get("debut")), _heure(depuis))
    if not t or not debut or not lancement or t < lancement:
        return "détection antérieure au lancement ou date invalide"
    avance = (debut - t).total_seconds() / 60
    if not CHATGPT["avance_min_minutes"] <= avance <= CHATGPT["avance_max_h"] * 60:
        return "détection hors fenêtre de 15 minutes à 6 heures"
    cote, edge, juste = (_nombre(p.get(k)) for k in ("cote", "ecart", "cote_juste"))
    if cote is None or not CHATGPT["cote_min"] <= cote <= CHATGPT["cote_max"]:
        return "cote hors intervalle 1,50–3,00"
    if edge is None or not CHATGPT["edge_min"] <= edge <= CHATGPT["edge_max"]:
        return "edge hors intervalle 3–12 %"
    if juste is None or juste <= 1 or abs(cote / juste - 1 - edge) > 0.002:
        return "edge incohérent avec la cote juste"
    lu = _heure(p.get("lu_reference"))
    if not lu or not 0 <= (t - lu).total_seconds() <= CHATGPT["fraicheur_max_minutes"] * 60:
        return "référence absente, future ou vieille de plus de 5 minutes"
    preuve = p.get("preuve_prise") or {}
    score = _nombre(preuve.get("ressemblance_noms"))
    if ((preuve.get("controle") or {}).get("statut") != "conforme"
            or score is None or score < 0.85 or not preuve.get("match_id_reference")):
        return "preuve de correspondance ou de conformité insuffisante"
    marche = p.get("marche")
    if marche not in CHATGPT["marches"] or p.get("periode") not in ("MATCH", "TEMPS_REG"):
        return "marché ou période hors périmètre"
    # Les génériques TOTAL/HANDICAP ne distinguent pas assez sûrement points,
    # jeux et sets dans ces deux sports. Seul le vainqueur est retenu en v1.
    if p.get("sport") in ("tennis", "volley") and marche != "VAINQUEUR":
        return "tennis et volley : vainqueur uniquement"
    if marche in ("TOTAL", "HANDICAP"):
        ligne = _nombre(p.get("ligne"))
        if ligne is None or not (ligne * 2).is_integer():
            return "ligne absente ou fractionnée en quarts"
    issues = ("PLUS", "MOINS") if marche == "TOTAL" else ("DOM", "EXT", "NUL") if marche == "RESULTAT_1N2" else ("DOM", "EXT")
    if p.get("issue") not in issues:
        return "issue invalide"
    return None


@figer_selecteur("chatgpt")
def paris_chatgpt(paris: list[dict], depuis: str = CHATGPT["debut"]) -> set[int]:
    """Première détection admissible par match ; au même instant, edge maximal.

    Le plafond journalier se remplit dans l'ordre réel des détections, sans
    sélectionner a posteriori les cinq meilleurs paris de la journée.
    """
    candidats = [p for p in paris if motif_refus(p, depuis) is None]
    candidats.sort(key=lambda p: (_heure(p["detecte"]), -float(p["ecart"]), -float(p["cote"]),
                                 p["bookmaker"], str(p.get("id") or p["match_id"])))
    matchs, selection, par_jour = set(), set(), Counter()
    for p in candidats:
        match = (p["sport"], str(p["preuve_prise"]["match_id_reference"]))
        jour = _heure(p["detecte"]).astimezone(PARIS).date()
        if match in matchs or par_jour[jour] >= CHATGPT["paris_max_jour"]:
            continue
        matchs.add(match)
        par_jour[jour] += 1
        selection.add(id(p))
    return selection
