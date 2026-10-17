"""Validations pures, sans accès aux résultats, pour les sélecteurs qui les adoptent.

Les seuils, fenêtres, marchés et plafonds appartiennent à chaque stratégie.
Une nouvelle règle de sélection doit garder un identifiant/version distinct.
"""
from math import isfinite


def nombre_fini(value) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        n = float(value)
        return n if isfinite(n) else None
    except (TypeError, ValueError, OverflowError):
        return None


def preuve_de(p: dict) -> dict:
    preuve = p.get("preuve_prise")
    return preuve if isinstance(preuve, dict) else {}


def correspondance_prouvee(p: dict, seuil: float) -> bool:
    preuve = preuve_de(p)
    controle = preuve.get("controle")
    score = nombre_fini(preuve.get("ressemblance_noms"))
    return (isinstance(controle, dict) and controle.get("statut") == "conforme"
            and score is not None and score >= seuil and bool(preuve.get("match_id_reference")))


def edge_coherent(cote, juste, edge, tolerance=0.002) -> bool:
    c, j, e = (nombre_fini(x) for x in (cote, juste, edge))
    return (c is not None and j is not None and e is not None and j > 1
            and abs(c / j - 1 - e) <= tolerance)


def ligne_non_quart(ligne) -> bool:
    n = nombre_fini(ligne)
    return n is not None and (n * 2).is_integer()


def issue_valide(marche, issue) -> bool:
    issues = (("PLUS", "MOINS") if marche == "TOTAL" else
              ("DOM", "EXT", "NUL") if marche == "RESULTAT_1N2" else
              ("DOM", "EXT") if marche in ("VAINQUEUR", "HANDICAP") else ())
    return issue in issues
