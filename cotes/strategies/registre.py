"""Registre des stratégies, en lecture seule (docs/architecture-cible.md, E4.1).

Une `Strategie` par clé, assemblée depuis les registres existants : les 7 bases de `convergence.STRATEGIES`,
la Convergence ≥ 2, les 58 variantes de `strategies_prudentes.VARIANTES` (Grok, Défis, Fusions…) et les règles du
laboratoire. Aucun fichier existant n'est modifié : les règles restent où elles sont, figées par
`tests/test_protocole.py`.

`selectionner(paris)` rend les `id()` des paris retenus, comme les sélecteurs d'origine. `ligne` est le libellé de la
stratégie dans le laboratoire et la navigation du site (« Claude (rejeu) », id d'une règle…).
"""
from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache

# Fichiers sous empreinte (scripts/verifier_strategie_jules_v2.py) : leurs stratégies ne se modifient pas.
FICHIERS_FIGES = ("strategie_jules_v2.py", "strategie_commune.py", "strategie_jules.py", "correspondance.py",
                  "decisions.py")
FAMILLES = ("base", "convergence", "variante", "grok", "conseil", "defi", "claude", "fusion", "labo")
# Doc de chaque famille (README › Ajouter une stratégie ; tests/test_registre_strategies.py vérifie qu'elle existe)
DOCS_FAMILLES = {
    "base": "docs/comparaison-strategies.md", "convergence": "docs/strategie-convergence.md",
    "variante": "docs/variantes-prudentes.md", "grok": "docs/strategie-grok.md", "conseil": "docs/strategie-conseil.md",
    "defi": "docs/strategie-defi.md", "claude": "docs/strategie-claude-opus.md", "fusion": "docs/recommandees.md",
    "labo": "docs/comparaison-strategies.md",
}


@dataclass(frozen=True)
class Strategie:
    cle: str
    nom: str
    famille: str
    version: str | None
    debut: str | None
    selectionner: Callable[[list[dict]], set[int]]
    figee: bool
    ligne: str
    court: str                                # nom court (cases des notifications, page Stratégies)


def _a_l_appel(f: Callable) -> Callable:
    """Sélecteur relu dans son module à chaque appel : un sélecteur remplacé (tests) est bien pris."""
    module, nom = sys.modules[f.__module__], f.__name__

    def selectionner(paris, *args, **kwargs):
        return getattr(module, nom)(paris, *args, **kwargs)
    selectionner.__qualname__ = f"{f.__module__}.{nom}"
    return selectionner


def _bases():
    from cotes.convergence import STRATEGIES
    from cotes.simulation import STRATEGIE
    from cotes.strategie_chatgpt import CHATGPT
    from cotes.strategie_eden import EDEN
    from cotes.strategie_gemini import GEMINI
    from cotes.strategie_jules import JULES
    from cotes.strategie_jules_v2 import JULES_V2
    from cotes.strategie_m3 import M3
    regles = {"strategie": STRATEGIE, "chatgpt": CHATGPT, "gemini": GEMINI, "jules": JULES, "jules_v2": JULES_V2,
              "eden": EDEN, "m3": M3}
    modules = {"strategie": "simulation.py", "chatgpt": "strategie_chatgpt.py", "gemini": "strategie_gemini.py",
               "jules": "strategie_jules.py", "jules_v2": "strategie_jules_v2.py", "eden": "strategie_eden.py",
               "m3": "strategie_m3.py"}
    for cle, _famille_vote, libelle, ligne, selecteur in STRATEGIES:
        r = regles[cle]
        yield Strategie(cle, libelle, "base", r.get("version"), r.get("debut"), _a_l_appel(selecteur),
                        modules[cle] in FICHIERS_FIGES, ligne, libelle)


def _convergence():
    from cotes.convergence import CONVERGENCE, paris_convergence
    yield Strategie("convergence", CONVERGENCE["nom"], "convergence", CONVERGENCE.get("version"),
                    CONVERGENCE["debut"], _a_l_appel(paris_convergence), False, CONVERGENCE["nom"], CONVERGENCE["nom"])


def _famille_variante(cle: str) -> str:
    from cotes import strategies_prudentes as sp
    groupes = {"grok": (*sp.GROKS, *sp.GROKS_V2, *sp.GROKS_V3), "conseil": sp.CONSEILS,
               "defi": (*sp.DEFIS, *sp.GEMINI_DEFIS, *sp.CLAUDE_DEFIS), "claude": (*sp.CLAUDE_OPUS, *sp.CLAUDE_SIGNAL),
               "fusion": (sp.RECOMMANDEE_FUSION, *sp.FUSIONS_AUTO)}
    return next((famille for famille, membres in groupes.items() if any(v["cle"] == cle for v in membres)),
                "variante")


def _variantes():
    from cotes.strategies_prudentes import VARIANTES, selections_prudentes
    for v in VARIANTES:
        def selectionner(paris, cle=v["cle"]):
            return selections_prudentes(paris).get(cle, set())
        yield Strategie(v["cle"], v["nom"], _famille_variante(v["cle"]), v.get("version"), v.get("debut"),
                        selectionner, False, v["nom"], v["court"])


def _laboratoire():
    from cotes.laboratoire import DEBUT_ETUDE, REGLES, selectionner as selectionner_regle
    numeros: dict[str, int] = {}
    for r in REGLES:
        def selectionner(paris, r=r):
            return {id(p) for p in selectionner_regle(paris, r)}
        numeros[r.reference] = numeros.get(r.reference, 0) + 1     # « Pinnacle 2 » : numérotation de la page
        yield Strategie("labo:" + r.id, r.nom, "labo", "1", DEBUT_ETUDE, selectionner, False, r.id,
                        f"{r.reference} {numeros[r.reference]}")


@lru_cache(maxsize=1)
def _tout() -> tuple[Strategie, ...]:
    return (*_bases(), *_convergence(), *_variantes(), *_laboratoire())


def toutes() -> list[Strategie]:
    return list(_tout())


def strategie(cle: str) -> Strategie:
    return next(s for s in _tout() if s.cle == cle)


def par_famille(famille: str) -> list[Strategie]:
    return [s for s in _tout() if s.famille == famille]
