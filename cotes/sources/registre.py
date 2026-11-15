"""Registre des sources de cotes (docs/architecture-cible.md, E2.1).

Une entrée par source lue par le cycle : budget (s), mode, mémoire de réserve, place dans le consensus et dans le
contrôle des intitulés. Rempli depuis `scripts/cycle.py` (`BUDGETS`, `MEMOIRES`, exclusions du contrôle) et les
`hors_consensus()` de Smarkets et Matchbook ; `tests/test_registre_sources.py` vérifie qu'ils concordent.

`lire` appelle la fonction du module au moment de l'appel (un `collecter` remplacé dans un test est bien pris) et
rend toujours `(lignes, meta)` ; `mode()` rend toujours "direct", "shadow" ou "off".
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from types import ModuleType

from cotes import pinnacle, polymarket, smarkets
from cotes.direct import betclic, betfair, draftkings, fanduel, matchbook, netbet, olybet, pmu, unibet, winamax

ROLES = ("reference", "francais", "bourse", "reference_props", "scores")


def _appel(module: ModuleType, nom: str) -> Callable:
    def appeler(*args, **kwargs):
        return getattr(module, nom)(*args, **kwargs)
    appeler.__qualname__ = f"{module.__name__}.{nom}"
    return appeler


def _en_lignes_meta(module: ModuleType) -> Callable:
    """Pinnacle et Polymarket rendent une liste : même forme `(lignes, meta)` que les autres lecteurs."""
    def lire(*args, **kwargs):
        lignes = list(module.collecter(*args, **kwargs) or [])
        erreurs = list(module.ERREURS)
        return lignes, {"ok": not erreurs, "erreurs": erreurs, "requetes": None, "lignes": len(lignes)}
    lire.__qualname__ = f"{module.__name__}.collecter"
    return lire


def _toujours_direct() -> str:
    return "direct"


@dataclass(frozen=True)
class Source:
    nom: str                                  # clé du journal (journal["etapes"]) et de BUDGETS, ex. "pmu_direct"
    role: str
    budget_s: float
    lire: Callable
    mode: Callable[[], str] = _toujours_direct
    memoire: str | None = None                # réserve dans memoire/horizon_direct (repli si la lecture échoue)
    reference: str | None = None              # nom de la table dans `references` (comparaison)
    hors_consensus: Callable[[], frozenset[str]] | None = None
    dans_controle: bool = True                # False : table hors du contrôle de conformité des intitulés
    attend_radar: bool = False                # True : part après Pinnacle (radar du cycle)


def _source(nom, role, budget, module, fonction="collecter", **kw) -> Source:
    return Source(nom, role, budget, _appel(module, fonction), **kw)


SOURCES: tuple[Source, ...] = (
    Source("pinnacle", "reference", 45, _en_lignes_meta(pinnacle), reference="Pinnacle"),
    Source("polymarket", "reference", 30, _en_lignes_meta(polymarket), reference="Polymarket"),
    # PMU, Winamax, Unibet, Betclic, OlyBet, NetBet : bookmakers français, lus en direct
    _source("pmu_direct", "francais", 75, pmu, memoire="pmu"),
    _source("winamax_direct", "francais", 80, winamax),       # 25 filtres depuis le 25/10 : ~70 s
    # coupé par le budget dans la moitié des cycles les 23-24/10 (médiane 72 s)
    _source("unibet_direct", "francais", 80, unibet, memoire="unibet", attend_radar=True),
    _source("olybet", "francais", 40, olybet, mode=_appel(olybet, "mode")),
    # coupé par son budget à chaque cycle jusqu'au 2/11 (lecture tournante incomplète) ; lu en parallèle, et le cycle
    # attend déjà Winamax (~60 s) et Unibet (~75 s après le départ) : 55 s ne rallongent pas la collecte
    _source("netbet", "francais", 55, netbet, mode=_appel(netbet, "mode"), memoire="netbet"),
    _source("betclic_direct", "francais", 80, betclic, memoire="betclic"),
    # bourses : leur table de paris, hors du contrôle des intitulés
    _source("smarkets", "bourse", 60, smarkets,
            mode=lambda: "direct" if smarkets.collecte_active() else "off", reference="Smarkets",
            hors_consensus=_appel(smarkets, "hors_consensus"), dans_controle=False),
    _source("matchbook", "bourse", 25, matchbook, mode=_appel(matchbook, "mode"), reference="Matchbook",
            hors_consensus=_appel(matchbook, "hors_consensus"), dans_controle=False),
    # catalogue relu toutes les 10 min (~50 appels) ; sinon prix seuls, 30 appels au plus
    _source("betfair", "bourse", 45, betfair, mode=_appel(betfair, "mode"), reference="Betfair",
            dans_controle=False),
    # références des props (et des matchs US pour DraftKings) : ni cotes françaises ni paris
    # 4 ligues puis 7 sous-catégories de props, 0,1 à 0,3 s par appel ; SOURCE_DRAFTKINGS=off coupe
    _source("draftkings", "reference_props", 20, draftkings, mode=_appel(draftkings, "mode")),
    # liste NBA/NHL puis onglets de props ; coupé par SOURCE_FANDUEL=off
    _source("fanduel", "reference_props", 40, fanduel, mode=_appel(fanduel, "mode")),
)

_PAR_NOM = {s.nom: s for s in SOURCES}


def source(nom: str) -> Source:
    return _PAR_NOM[nom]


def par_role(role: str) -> list[Source]:
    return [s for s in SOURCES if s.role == role]


def francais() -> list[Source]:
    return par_role("francais")


def budgets() -> dict[str, float]:
    return {s.nom: s.budget_s for s in SOURCES}


def memoires() -> dict[str, str]:
    return {s.nom: s.memoire for s in SOURCES if s.memoire}


def hors_controle() -> frozenset[str]:
    """Tables de `references` exclues du contrôle de conformité des intitulés."""
    return frozenset(s.reference for s in SOURCES if s.reference and not s.dans_controle)


def hors_consensus() -> frozenset[str]:
    """Références qui gardent leur table sans entrer dans la moyenne partagée (selon leurs drapeaux du moment)."""
    out: frozenset[str] = frozenset()
    for s in SOURCES:
        if s.hors_consensus is not None:
            out |= s.hors_consensus()
    return out
