"""Eden v1 : favoris Pinnacle et Polymarket, suivi depuis le 19 octobre 2026 à 20 h (Paris).

Règle retenue après une grille déclarée de 1 260 combinaisons (référence, bande de
cotes, edge, horizon) sur l'univers de qualité commun, coupée avant de lire le
test : construction jusqu'au 13 octobre, validation du 14 au 16, test du 17 au 19
(début de match, heure de Paris). Une mise par bookmaker français et par match.

La région qui reste positive sur les trois fenêtres, y compris après retrait du
meilleur pari, est celle des cotes 1,30–2,00, edge 2–12 %, détection entre
30 minutes et 24 heures, références encore collectées (Pinnacle et Polymarket).
Les bandes au-dessus de 2,00 s'aplatissent sur le test. Au-delà de 24 heures,
la CLV de construction est négative. Avant 30 minutes, le ROI de construction
est négatif.

Ce n'est pas une promesse. La validation est en grande partie portée par le
basket, souvent féminin. Le test du 17–19 octobre reste positif sans ce basket.
Le filtre linguistique de Gemini, qui retire ces matchs, a été mesuré puis
écarté : il laisse la validation autour de zéro. Aucun plafond journalier :
un plafond de 8 ou de 6 réduit le test et n'appartenait pas à la région retenue.
Les jeunes et les réserves restent exclus ; ce filtre ne change aucun pari de
ce relevé.
"""
from __future__ import annotations

from datetime import datetime, timezone

from .correspondance import normaliser
from .decisions import figer_selecteur
from .strategie_commune import (
    correspondance_prouvee,
    edge_coherent,
    ligne_non_quart,
    nombre_fini as _nombre,
)

EDEN = {
    "nom": "Eden",
    "version": "1",
    "debut": "2026-10-19T18:00:00+00:00",
    "references": ("Pinnacle", "Polymarket"),
    "bookmakers": ("Winamax", "Betclic", "Unibet", "PMU"),
    "sports": (
        "football", "basket", "hockey", "baseball", "rugby",
        "handball", "football_americain", "tennis", "volley",
    ),
    "marches": (
        "RESULTAT_1N2", "VAINQUEUR", "DOUBLE_CHANCE", "DRAW_NO_BET",
        "TOTAL", "HANDICAP",
    ),
    "cote_min": 1.30,
    "cote_max": 2.00,
    "edge_min": 0.02,
    "edge_max": 0.12,
    "avance_min_minutes": 30,
    "avance_max_h": 24,
    "fraicheur_max_minutes": 15,
    "ressemblance_min": 0.85,
    "mise": 10.0,
}


def _heure(value) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo is not None else None
    except (TypeError, ValueError):
        return None


def _issue_valide(marche, issue) -> bool:
    issues = {
        "TOTAL": ("PLUS", "MOINS"),
        "RESULTAT_1N2": ("DOM", "EXT", "NUL"),
        "DOUBLE_CHANCE": ("HOME_DRAW", "HOME_AWAY", "DRAW_AWAY"),
    }
    return issue in issues.get(marche, ("DOM", "EXT"))


def motif_refus_eden(p: dict, depuis: str = EDEN["debut"]) -> str | None:
    """Évalue un pari avec les seules données connues à la détection.

    Ne consulte jamais statut, gain, regle_le ou clv.
    """
    if p.get("reference") not in EDEN["references"]:
        return "référence hors périmètre"
    if p.get("bookmaker") not in EDEN["bookmakers"] or p.get("sport") not in EDEN["sports"]:
        return "bookmaker ou sport hors périmètre"
    if p.get("suspect"):
        return "opportunité suspecte"

    t, debut, lu, lancement = (
        _heure(p.get("detecte")),
        _heure(p.get("debut")),
        _heure(p.get("lu_reference")),
        _heure(depuis),
    )
    if not t or not debut or not lu or not lancement or t < lancement:
        return "date invalide ou détection antérieure au lancement"

    avance_min = (debut - t).total_seconds() / 60.0
    if not EDEN["avance_min_minutes"] <= avance_min <= EDEN["avance_max_h"] * 60:
        return "détection hors fenêtre de 30 min à 24 h avant match"

    fraicheur_sec = abs((t - lu).total_seconds())      # lecture Pinnacle avant ou après la détection FR
    if not fraicheur_sec <= EDEN["fraicheur_max_minutes"] * 60:
        return "référence absente ou éloignée de plus de 15 minutes"

    cote, juste, edge = (_nombre(p.get(k)) for k in ("cote", "cote_juste", "ecart"))
    if cote is None or not EDEN["cote_min"] <= cote <= EDEN["cote_max"]:
        return "cote hors intervalle 1,30–2,00"
    if edge is None or not EDEN["edge_min"] <= edge <= EDEN["edge_max"]:
        return "edge hors intervalle 2–12 %"
    if not edge_coherent(cote, juste, edge):
        return "edge incohérent avec la cote juste"

    if not correspondance_prouvee(p, EDEN["ressemblance_min"]):
        return "preuve de correspondance ou conformité du marché insuffisante"

    equipes = [normaliser(str(p.get(k) or "")) for k in ("domicile", "exterieur")]
    if any(n[2] for n in equipes):
        return "catégorie jeunes ou réserve à risque d'appariement"

    marche = p.get("marche")
    if marche not in EDEN["marches"] or p.get("periode") not in ("MATCH", "TEMPS_REG"):
        return "marché ou période hors périmètre"
    if p.get("sport") in ("tennis", "volley") and (marche != "VAINQUEUR" or p.get("periode") != "MATCH"):
        return "tennis et volley : vainqueur du match uniquement"
    if marche in ("TOTAL", "HANDICAP") and not ligne_non_quart(p.get("ligne")):
        return "ligne absente ou fractionnée en quarts"
    if not _issue_valide(marche, p.get("issue")):
        return "issue invalide"
    return None


@figer_selecteur("eden")
def paris_eden(paris: list[dict], depuis: str = EDEN["debut"]) -> set[int]:
    """Au plus une mise par bookmaker et par match, dans l'ordre réel.

    À détection simultanée : edge le plus élevé, puis cote la plus basse.
    Deux références du même bookmaker sur le même match restent une seule mise.
    Un autre bookmaker français qui cote mal le même match est une mise distincte.
    Pas de plafond journalier : les plafonds essayés réduisaient le test.
    """
    candidats = [p for p in paris if motif_refus_eden(p, depuis) is None]
    candidats.sort(
        key=lambda p: (
            _heure(p["detecte"]),
            -float(p["ecart"]),
            float(p["cote"]),
            str(p.get("bookmaker") or ""),
            str(p.get("id") or p.get("match_id") or ""),
        )
    )
    parents, utilises, selection = {}, {}, set()

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
        sport, book = p.get("sport"), p.get("bookmaker")
        preuve = p.get("preuve_prise") or {}
        cles = [("reference", sport, book, p["reference"], str(preuve["match_id_reference"]))]
        if p.get("match_id"):
            cles.append(("bookmaker", sport, book, str(p["match_id"])))
        if p.get("domicile") and p.get("exterieur"):
            noms = tuple(sorted(normaliser(p[k])[0] for k in ("domicile", "exterieur")))
            if all(noms):
                cles.append(("equipes", sport, book, _heure(p["debut"]).astimezone(timezone.utc), noms))
        root = associer(cles)
        if utilises.get(root):
            continue
        utilises[root] = True
        selection.add(id(p))
    return selection
