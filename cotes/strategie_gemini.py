"""Règles figées Gemini Argon v1 : sélection prospective multi-références.

Principe :
- Trois références conformes (Pinnacle, Betfair, Polymarket).
- Plafond de cote adaptatif selon la structure de marché :
  * Pinnacle : 1,30 à 2,15 (concentration sur les favoris / cotes basses).
  * Betfair & Polymarket : 1,30 à 2,60 (capture des retards de cotation ANJ).
- Edge requis : 2,5 % à 12,0 %.
- Fenêtre d'anticipation : 30 minutes à 24 heures avant le début du match.
- Fraîcheur de la référence : <= 10 minutes.
- Stricte indépendance par événement : 1 seule mise par match (match_id et
  match_id_reference), tous bookmakers et toutes références confondus.
- Plafond d'exposition : 8 paris maximum par jour (heure de Paris) dans l'ordre
  chronologique réel des détections.
"""
from __future__ import annotations

from .decisions import figer_selecteur

from collections import Counter
from datetime import datetime, timezone
from math import isfinite
from zoneinfo import ZoneInfo

from .correspondance import normaliser

PARIS = ZoneInfo("Europe/Paris")

GEMINI = {
    "nom": "Gemini Argon",
    "version": "1",
    "debut": "2026-10-14T18:00:00+00:00",
    "references": ("Pinnacle", "Betfair", "Polymarket"),
    "bookmakers": ("Winamax", "Betclic", "Unibet", "PMU"),
    "marches": ("RESULTAT_1N2", "VAINQUEUR", "DOUBLE_CHANCE", "DRAW_NO_BET", "TOTAL", "HANDICAP"),
    "cote_min": 1.30,
    "cote_max_par_reference": {
        "Pinnacle": 2.15,
        "Betfair": 2.60,
        "Polymarket": 2.60,
    },
    "edge_min": 0.025,
    "edge_max": 0.12,
    "avance_min_minutes": 30,
    "avance_max_h": 24,
    "fraicheur_max_minutes": 10,
    "ressemblance_min": 0.85,
    "paris_max_jour": 8,
    "mise": 10.0,
}


def _heure(value) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo is not None else None
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


def motif_refus_gemini(p: dict, depuis: str = GEMINI["debut"]) -> str | None:
    """Évalue un pari uniquement avec les données connues à l'instant de détection.

    Ne consulte jamais statut, gain, regle_le ou clv.
    """
    ref = p.get("reference")
    if ref not in GEMINI["references"]:
        return "référence hors périmètre"
    if p.get("bookmaker") not in GEMINI["bookmakers"] or p.get("suspect"):
        return "bookmaker hors périmètre ou opportunité suspecte"

    t, debut, lu, lancement = (
        _heure(p.get("detecte")),
        _heure(p.get("debut")),
        _heure(p.get("lu_reference")),
        _heure(depuis),
    )
    if not t or not debut or not lu or not lancement or t < lancement:
        return "date invalide ou détection antérieure au lancement"

    avance_min = (debut - t).total_seconds() / 60.0
    if not GEMINI["avance_min_minutes"] <= avance_min <= GEMINI["avance_max_h"] * 60:
        return "détection hors fenêtre de 30 min à 24 h avant match"

    fraicheur_sec = (t - lu).total_seconds()
    if not 0 <= fraicheur_sec <= GEMINI["fraicheur_max_minutes"] * 60:
        return "référence absente, future ou vieille de plus de 10 minutes"

    cote, juste, edge = (_nombre(p.get(k)) for k in ("cote", "cote_juste", "ecart"))
    cote_max = GEMINI["cote_max_par_reference"][ref]
    if cote is None or not GEMINI["cote_min"] <= cote <= cote_max:
        return f"cote hors intervalle 1,30–{cote_max:.2f} pour {ref}"
    if edge is None or not GEMINI["edge_min"] <= edge <= GEMINI["edge_max"]:
        return "edge hors intervalle 2,5–12 %"
    if juste is None or juste <= 1 or abs(cote / juste - 1 - edge) > 0.002:
        return "edge incohérent avec la cote juste"

    preuve = p.get("preuve_prise") or {}
    score = _nombre(preuve.get("ressemblance_noms"))
    if (
        not preuve.get("match_id_reference")
        or score is None
        or score < GEMINI["ressemblance_min"]
        or (preuve.get("controle") or {}).get("statut") != "conforme"
    ):
        return "preuve de correspondance ou conformité du marché insuffisante"

    # Filtre linguistique (exclusion jeunes, réserves, féminines non alignées)
    noms = [normaliser(str(p.get(k) or "")) for k in ("domicile", "exterieur", "ligue")]
    if any(n[1] for n in noms) or any(n[2] for n in noms[:2]):
        return "catégorie d'équipe (jeunes/réserve/genre) à risque d'appariement"

    marche = p.get("marche")
    if marche not in GEMINI["marches"] or p.get("periode") not in ("MATCH", "TEMPS_REG"):
        return "marché ou période hors périmètre"
    if p.get("sport") in ("tennis", "volley") and marche != "VAINQUEUR":
        return "tennis et volley : vainqueur uniquement"
    if marche in ("TOTAL", "HANDICAP"):
        ligne = _nombre(p.get("ligne"))
        if ligne is None or not (ligne * 2).is_integer():
            return "ligne absente ou fractionnée en quarts"

    issues = {
        "TOTAL": ("PLUS", "MOINS"),
        "RESULTAT_1N2": ("DOM", "EXT", "NUL"),
        "DOUBLE_CHANCE": ("HOME_DRAW", "HOME_AWAY", "DRAW_AWAY"),
    }
    if p.get("issue") not in issues.get(marche, ("DOM", "EXT")):
        return "issue invalide"

    return None


def _peut_relier(p: dict) -> bool:
    """Identité fiable, y compris sur une ligne ensuite écartée (edge, fenêtre, cote)."""
    if p.get("reference") not in GEMINI["references"]:
        return False
    if p.get("bookmaker") not in GEMINI["bookmakers"] or p.get("suspect"):
        return False
    if not _heure(p.get("detecte")) or not _heure(p.get("debut")):
        return False
    preuve = p.get("preuve_prise") or {}
    score = _nombre(preuve.get("ressemblance_noms"))
    return bool(
        preuve.get("match_id_reference")
        and score is not None
        and score >= GEMINI["ressemblance_min"]
        and (preuve.get("controle") or {}).get("statut") == "conforme"
    )


@figer_selecteur("gemini")
def paris_gemini(paris: list[dict], depuis: str = GEMINI["debut"]) -> set[int]:
    """Sélectionne au plus un pari par événement sportif, dans l'ordre réel.

    À détection simultanée, priorise l'edge le plus élevé puis la cote la plus
    basse (minimisation de la variance). Respecte le plafond journalier Europe/Paris.
    Un alias rencontré sur un pari déjà écarté est mémorisé : sinon
    W/Pinnacle → W/Polymarket (écarté) → PMU/Polymarket reprend le match.
    """
    candidats = [p for p in paris if _peut_relier(p)]
    candidats.sort(
        key=lambda p: (
            _heure(p["detecte"]),
            -(_nombre(p.get("ecart")) or 0),
            _nombre(p.get("cote")) or 0,
            str(p.get("bookmaker") or ""),
            str(p.get("id") or p.get("match_id") or ""),
        )
    )
    parents, utilises, selection, par_jour = {}, {}, set(), Counter()

    def racine(cle):
        parents.setdefault(cle, cle)
        if parents[cle] != cle:
            parents[cle] = racine(parents[cle])
        return parents[cle]

    def associer(cles):
        root = racine(cles[0])
        for cle in cles[1:]:
            autre = racine(cle)
            if autre != root:
                parents[autre] = root
                utilises[root] = utilises.get(root, False) or utilises.get(autre, False)
        return root

    for p in candidats:
        sport = p.get("sport")
        cles = [("reference", sport, p["reference"], str(p["preuve_prise"]["match_id_reference"]))]
        if p.get("match_id"):
            cles.append(("bookmaker", sport, str(p["match_id"])))
        if p.get("domicile") and p.get("exterieur"):
            noms = tuple(sorted(normaliser(p[k])[0] for k in ("domicile", "exterieur")))
            if all(noms):
                cles.append(("equipes", sport, _heure(p["debut"]).astimezone(timezone.utc), noms))
        root = associer(cles)
        if motif_refus_gemini(p, depuis) is not None:
            continue
        jour = _heure(p["detecte"]).astimezone(PARIS).date()
        if utilises.get(root) or par_jour[jour] >= GEMINI["paris_max_jour"]:
            continue
        utilises[root] = True
        par_jour[jour] += 1
        selection.add(id(p))
    return selection
