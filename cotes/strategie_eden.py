"""Eden v1 : filtre prudent sur Pinnacle, suivi à partir du 19 octobre 2026.

Le protocole du 14 octobre n'a retenu aucune des 36 règles. Eden ne corrige pas
ce constat et ne promet aucun rendement. Elle écarte des zones déjà mauvaises
ou instables, puis se mesure seulement sur les détections postérieures à son
lancement.

Principe, lu uniquement à l'instant de la détection :
- Référence Pinnacle sans marge. Sur le relevé du 19 octobre, c'est la seule
  référence à la fois volumineuse et de CLV moyenne positive parmi les prises
  qui passent le contrôle de qualité commun. Polymarket est proche de zéro en
  CLV. Betfair est nettement négatif en ROI sur ce même filtre. Cela ne veut
  pas dire que Pinnacle gagne.
- Cotes 1,30 à 2,00. Le protocole a rejeté les bandes 2,00–5,00 (ROI de
  construction de −43 % à −61 %). Au-dessus de 5,00, Pinnacle est à −100 %
  sur 38 réglés. La bande 3,01–5,00 change de signe après le 14 octobre :
  elle n'est pas stable. Le plafond 2,00 est une borne de la grille déjà
  écrite, pas un optimum recherché.
- Edge 2 % à 8 %. Le plancher est celui du protocole. Le relever à 3 % ou à
  5 % aurait sélectionné des tranches qui s'inversent après le 14 octobre
  (favoris Pinnacle, 1,30–2,00, 30 min–12 h : 3–5 % passe de +38 % à −10 %).
  Dans cette même fenêtre, 2–3 % reste positif des deux côtés, sur de petits
  effectifs (18 puis 17 réglés). Le plafond 8 % retire la queue 8–12 % et
  au-delà, négative avant le 14 octobre malgré une CLV très haute : signature
  de cotes aberrantes. Ce n'est pas un seuil optimal démontré. Le rejeu du
  sélecteur complet, plafond journalier inclus, ne confirme pas cette tranche.
- Détection de 30 minutes à 12 heures avant le match. Au-delà de 24 heures,
  la CLV du filtre de qualité est négative. Le plancher de 30 minutes est
  celui de Gemini : 15–30 minutes est un délai trop court. Sur tout le relevé
  ce créneau est à −26 % (42 réglés), mais avant le 14 octobre il ne compte
  que 12 paris, de signe opposé. Douze heures reprend l'horizon de Claude et
  de Jules. La tranche 12–24 h change de signe et les règles à 36 heures n'ont
  pas passé le protocole.
- Référence lue depuis 10 minutes au plus. Correspondance ≥ 0,85 et contrôle
  conforme. Hommes seniors : pas de jeunes, de réserves ni d'intitulé féminin
  non aligné. Tennis et volley : vainqueur du match seulement. Pas de ligne
  en quart.
- Une mise fictive de 10 € par bookmaker français et par match. Winamax,
  Betclic, Unibet et PMU peuvent tous être joués si chacun est mal coté.
  Deux références du même bookmaker restent une seule mise. Six prises
  maximum par jour civil de Paris, dans l'ordre réel des détections.

Le rejeu antérieur au 19 octobre 2026 à 14:00 UTC est descriptif. Il ne doit
pas alimenter le bilan de suivi.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .correspondance import normaliser
from .decisions import figer_selecteur
from .strategie_commune import (
    correspondance_prouvee,
    edge_coherent,
    issue_valide,
    ligne_non_quart,
    nombre_fini as _nombre,
)

PARIS = ZoneInfo("Europe/Paris")

EDEN = {
    "nom": "Eden",
    "version": "1",
    "debut": "2026-10-19T14:00:00+00:00",
    "references": ("Pinnacle",),
    "bookmakers": ("Winamax", "Betclic", "Unibet", "PMU"),
    "sports": (
        "football", "basket", "hockey", "baseball", "rugby",
        "handball", "football_americain", "tennis", "volley",
    ),
    "marches": ("RESULTAT_1N2", "VAINQUEUR", "TOTAL", "HANDICAP"),
    "cote_min": 1.30,
    "cote_max": 2.00,
    "edge_min": 0.02,
    "edge_max": 0.08,
    "avance_min_minutes": 30,
    "avance_max_h": 12,
    "fraicheur_max_minutes": 10,
    "ressemblance_min": 0.85,
    "paris_max_jour": 6,
    "mise": 10.0,
}


def _heure(value) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo is not None else None
    except (TypeError, ValueError):
        return None


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
        return "détection hors fenêtre de 30 min à 12 h avant match"

    fraicheur_sec = (t - lu).total_seconds()
    if not 0 <= fraicheur_sec <= EDEN["fraicheur_max_minutes"] * 60:
        return "référence absente, future ou vieille de plus de 10 minutes"

    cote, juste, edge = (_nombre(p.get(k)) for k in ("cote", "cote_juste", "ecart"))
    if cote is None or not EDEN["cote_min"] <= cote <= EDEN["cote_max"]:
        return "cote hors intervalle 1,30–2,00"
    if edge is None or not EDEN["edge_min"] <= edge <= EDEN["edge_max"]:
        return "edge hors intervalle 2–8 %"
    if not edge_coherent(cote, juste, edge):
        return "edge incohérent avec la cote juste"

    if not correspondance_prouvee(p, EDEN["ressemblance_min"]):
        return "preuve de correspondance ou conformité du marché insuffisante"

    noms = [normaliser(str(p.get(k) or "")) for k in ("domicile", "exterieur", "ligue")]
    if any(n[1] for n in noms) or any(n[2] for n in noms[:2]):
        return "catégorie d'équipe (jeunes/réserve/genre) à risque d'appariement"

    marche = p.get("marche")
    if marche not in EDEN["marches"] or p.get("periode") not in ("MATCH", "TEMPS_REG"):
        return "marché ou période hors périmètre"
    if p.get("sport") in ("tennis", "volley") and (marche != "VAINQUEUR" or p.get("periode") != "MATCH"):
        return "tennis et volley : vainqueur du match uniquement"
    if marche in ("TOTAL", "HANDICAP") and not ligne_non_quart(p.get("ligne")):
        return "ligne absente ou fractionnée en quarts"
    if not issue_valide(marche, p.get("issue")):
        return "issue invalide"
    return None


@figer_selecteur("eden")
def paris_eden(paris: list[dict], depuis: str = EDEN["debut"]) -> set[int]:
    """Au plus une mise par bookmaker et par match, dans l'ordre réel.

    À détection simultanée : edge le plus élevé, puis cote la plus basse.
    Le plafond de six prises suit le jour civil de Paris. Un autre bookmaker
    français qui cote mal le même match est une mise distincte.
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
        sport, book = p.get("sport"), p.get("bookmaker")
        preuve = p.get("preuve_prise") or {}
        # Le bookmaker fait partie de chaque clé : un alias ne traverse pas Winamax et PMU.
        cles = [("reference", sport, book, p["reference"], str(preuve["match_id_reference"]))]
        if p.get("match_id"):
            cles.append(("bookmaker", sport, book, str(p["match_id"])))
        if p.get("domicile") and p.get("exterieur"):
            noms = tuple(sorted(normaliser(p[k])[0] for k in ("domicile", "exterieur")))
            if all(noms):
                cles.append(("equipes", sport, book, _heure(p["debut"]).astimezone(timezone.utc), noms))
        root = associer(cles)
        jour = _heure(p["detecte"]).astimezone(PARIS).date()
        if utilises.get(root) or par_jour[jour] >= EDEN["paris_max_jour"]:
            continue
        utilises[root] = True
        par_jour[jour] += 1
        selection.add(id(p))
    return selection
