"""Recherche sur les pauses : calculs purs, aucune collecte, mise ni notification.

L1 compare deux observations live strictement synchronisées. L2 projette une
clôture complète sous des hypothèses explicites, jamais une cote isolée de paris.json.
Toutes les décisions sont en mode papier. Voir docs/live-pauses.md.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from statistics import NormalDist

from .marge import proba_justes

SPORTS = frozenset({"football", "hockey", "basket", "handball", "tennis", "volley",
                    "rugby", "football_americain", "baseball"})
FRANCAIS = frozenset({"Winamax", "Betclic", "Unibet", "PMU"})
REFERENCES = frozenset({"Pinnacle", "Betfair"})


def _finite(x: float) -> bool:
    return type(x) in (int, float) and math.isfinite(x)


def _aware(t: datetime) -> bool:
    return isinstance(t, datetime) and t.tzinfo is not None and t.utcoffset() is not None


def _prob(p: float) -> bool:
    return _finite(p) and 0 < p < 1


def _score(s: tuple[int, int]) -> bool:
    return len(s) == 2 and all(type(n) is int and n >= 0 for n in s)


def _half_line(x: float | None) -> bool:
    return _finite(x) and abs(2 * x - round(2 * x)) < 1e-9


def _boundary(sport: str, boundary: str) -> bool:
    if sport in {"football", "handball", "rugby"}:
        return boundary == "HT"
    if sport in {"basket", "football_americain"}:
        return boundary in {"QT1", "HT", "QT3"}
    if sport == "hockey":
        return boundary in {"P1", "P2"}
    if sport in {"tennis", "volley"}:
        return boundary in {"SET1", "SET2", "SET3", "SET4"}
    if sport == "baseball":
        return any(boundary == f"{half}{n}" for half in ("TOP", "BOTTOM") for n in range(1, 10))
    return False


@dataclass(frozen=True)
class Policy:
    # La limite de 180 s demandée est un plafond, pas un objectif de latence.
    quote_age_s: float = 30
    state_age_s: float = 15
    skew_s: float = 10
    min_edge: float = .06
    max_margin: float = .12
    exchange_gap: float = .03
    min_liquidity: float = 20
    sets_favorite_min: float = .68

    def __post_init__(self):
        values = (self.quote_age_s, self.state_age_s, self.skew_s, self.min_edge,
                  self.max_margin, self.exchange_gap, self.min_liquidity, self.sets_favorite_min)
        if (not all(_finite(x) and x >= 0 for x in values)
                or not 0 < self.quote_age_s <= 180 or not 0 < self.state_age_s <= 30
                or self.skew_s > self.state_age_s or self.min_edge > 1
                or self.max_margin > .2 or self.exchange_gap > .1 or not .5 < self.sets_favorite_min < 1):
            raise ValueError("politique invalide")


@dataclass(frozen=True)
class PauseState:
    event_id: str                 # identifiant commun, orientation DOM/EXT déjà vérifiée
    sport: str
    cycle: str
    source: str
    source_event_id: str
    received_at: datetime
    updated_at: datetime         # heure SOURCE, jamais remplacée par received_at
    score: tuple[int, int]
    boundary: str                # période TERMINÉE, pas prochaine période
    phase: str = "unknown"       # doit être explicitement « pause »
    score_unit: str = "points"
    context_complete: bool = False
    incidents: tuple[str, ...] = ()
    resumes_at: datetime | None = None


@dataclass(frozen=True)
class Market:
    event_id: str
    sport: str
    name: str                    # VAINQUEUR, RESULTAT_1N2, HANDICAP, TOTAL
    issue: str                   # DOM / NUL / EXT / PLUS / MOINS
    scope: str                   # REGULATION / INCLUDING_OT / SETS
    unit: str                    # goals / points / sets
    rules: str                   # règle exacte : OT, abandon, push, prolongation…
    line: float | None = None
    basis: str = "full_event"    # jamais confondre fin du match et temps restant


@dataclass(frozen=True)
class LiveQuote:
    market: Market
    state: PauseState
    bookmaker: str
    received_at: datetime
    updated_at: datetime
    odds: float
    active: bool = False
    price_id: str = ""


@dataclass(frozen=True)
class FairPrice:
    quote: LiveQuote
    probability: float           # probabilité conditionnelle hors remboursement
    lower_probability: float
    margin: float = 0
    liquidity: float = 0
    spread: float = 0
    method: str = "power"
    push_probability: float | None = None


@dataclass(frozen=True)
class Outcome:
    win: float
    push: float
    loss: float

    def __post_init__(self):
        if (not all(_finite(x) and 0 <= x <= 1 + 1e-10 for x in (self.win, self.push, self.loss))
                or abs(self.win + self.push + self.loss - 1) > 1e-8):
            raise ValueError("distribution invalide")

    @property
    def fair_odds(self) -> float:
        return 1 + self.loss / self.win if self.win else math.inf

    def edge(self, odds: float) -> float:
        # Une cote juste à elle seule ne suffit pas pour l'EV avec remboursements.
        return self.win * (odds - 1) - self.loss


@dataclass(frozen=True)
class Decision:
    accepted: bool
    reason: str
    logic: str
    edge: float | None = None
    fair_odds: float | None = None
    outcome: Outcome | None = None
    mode: str = "paper"


def _fresh(received: datetime, updated: datetime, now: datetime, max_age: float) -> bool:
    return (all(_aware(t) for t in (received, updated, now)) and updated <= received <= now
            and 0 <= (now - updated).total_seconds() <= max_age)


def _quote_error(q: LiveQuote, now: datetime, policy: Policy) -> str | None:
    s, m = q.state, q.market
    if not m.event_id or (s.event_id, s.sport) != (m.event_id, m.sport):
        return "identity_mismatch"
    if m.sport not in SPORTS or not m.rules or m.scope not in {"REGULATION", "INCLUDING_OT", "SETS"}:
        return "unknown_contract"
    if m.basis != "full_event" or not m.name or not m.issue:
        return "unsupported_basis"
    if not s.cycle or not s.source or not s.source_event_id or not _score(s.score):
        return "unknown_state"
    if s.phase != "pause" or not _boundary(s.sport, s.boundary):
        return "not_a_confirmed_pause"
    expected_unit = "sets" if s.sport in {"tennis", "volley"} else (
        "goals" if s.sport in {"football", "hockey", "handball"} else
        "runs" if s.sport == "baseball" else "points")
    if s.score_unit != expected_unit:
        return "score_unit_mismatch"
    if s.sport in {"tennis", "volley"} and sum(s.score) != int(s.boundary[-1]):
        return "set_boundary_mismatch"
    if not _fresh(s.received_at, s.updated_at, now, policy.state_age_s):
        return "stale_state"
    if s.resumes_at is not None and (not _aware(s.resumes_at)
                                   or (s.resumes_at - now).total_seconds() <= 20):
        return "pause_ending"
    if not q.active or not q.price_id or not _finite(q.odds) or q.odds <= 1:
        return "unavailable_price"
    if not _fresh(q.received_at, q.updated_at, now, policy.quote_age_s):
        return "stale_price"
    if abs((s.updated_at - q.updated_at).total_seconds()) > policy.skew_s:
        return "price_state_skew"
    return None


def fair_reference(quotes: tuple[LiveQuote, ...], now: datetime,
                   policy: Policy = Policy(), *,
                   lay_odds: tuple[float, ...] | None = None,
                   liquidity: tuple[float, ...] | None = None) -> tuple[FairPrice, ...]:
    """Marché COMPLET Pinnacle ou carnet Betfair ; refuse un mélange d'états/prix.

    Betfair : quote.odds = meilleur back, lay_odds = meilleur lay, liquidité =
    minimum disponible des deux côtés. Bornes normalisées de façon conservatrice.
    Ni commission ni achat/vente ne transforment ceci en arbitrage exécutable.
    """
    if not quotes:
        raise ValueError("marché absent")
    q0, m0, s0 = quotes[0], quotes[0].market, quotes[0].state
    issues = {q.market.issue for q in quotes}
    expected = {"DOM", "NUL", "EXT"} if m0.name == "RESULTAT_1N2" else (
        {"DOM", "EXT"} if m0.name in {"VAINQUEUR", "HANDICAP"} else
        {"PLUS", "MOINS"} if m0.name == "TOTAL" else set())
    if not expected or issues != expected or len(quotes) != len(expected):
        raise ValueError("marché incomplet ou non pris en charge")
    for q in quotes:
        if (_quote_error(q, now, policy) or q.bookmaker != q0.bookmaker
                or q.state != s0 or q.market != Market(
                    m0.event_id, m0.sport, m0.name, q.market.issue, m0.scope,
                    m0.unit, m0.rules, m0.line, m0.basis)):
            raise ValueError("observations incompatibles")
    times = [q.updated_at for q in quotes]
    if (max(times) - min(times)).total_seconds() > policy.skew_s:
        raise ValueError("marché désynchronisé")
    prices = [q.odds for q in quotes]
    if q0.bookmaker == "Pinnacle":
        margin = sum(1 / x for x in prices) - 1
        if margin < -1e-8 or margin > policy.max_margin:
            raise ValueError("marge non fiable")
        ps = proba_justes(prices)
        if not ps:
            raise ValueError("retrait de marge impossible")
        return tuple(FairPrice(q, p, p, margin=max(0, margin)) for q, p in zip(quotes, ps))
    if q0.bookmaker != "Betfair" or lay_odds is None or liquidity is None:
        raise ValueError("référence non autorisée ou carnet absent")
    if len(lay_odds) != len(quotes) or len(liquidity) != len(quotes):
        raise ValueError("carnet incomplet")
    if any(not _finite(l) or l < b or not _finite(v) or v < policy.min_liquidity
           for b, l, v in zip(prices, lay_odds, liquidity)):
        raise ValueError("carnet croisé ou liquidité insuffisante")
    lows, highs = [1 / l for l in lay_odds], [1 / b for b in prices]
    gaps = [h - l for l, h in zip(lows, highs)]
    if any(g > policy.exchange_gap for g in gaps):
        raise ValueError("écart back/lay excessif")
    if sum(lows) > 1 + 1e-6 or sum(highs) < 1 - 1e-6:
        raise ValueError("carnet incohérent")
    mids = [(l + h) / 2 for l, h in zip(lows, highs)]
    return tuple(FairPrice(q, mids[i] / sum(mids), lows[i] / (lows[i] + sum(highs) - highs[i]),
                           liquidity=liquidity[i], spread=gaps[i], method="back_lay_interval")
                 for i, q in enumerate(quotes))


def evaluate_l1(offer: LiveQuote, reference: FairPrice, now: datetime,
                policy: Policy = Policy()) -> Decision:
    """Value directe uniquement : aucun envoi et aucune prétention de gain certain."""
    for q in (offer, reference.quote):
        error = _quote_error(q, now, policy)
        if error:
            return Decision(False, error, "L1")
    r, s = reference.quote, offer.state
    if offer.bookmaker not in FRANCAIS or r.bookmaker not in REFERENCES:
        return Decision(False, "unsupported_bookmaker", "L1")
    if offer.market != r.market:
        return Decision(False, "contract_mismatch", "L1")
    if (s.cycle, s.boundary, s.score, s.score_unit) != (
            r.state.cycle, r.state.boundary, r.state.score, r.state.score_unit):
        return Decision(False, "state_mismatch", "L1")
    stamps = (offer.updated_at, r.updated_at, s.updated_at, r.state.updated_at)
    if (max(stamps) - min(stamps)).total_seconds() > policy.skew_s:
        return Decision(False, "cross_source_skew", "L1")
    if (not _prob(reference.probability) or not _prob(reference.lower_probability)
            or reference.lower_probability > reference.probability
            or not _finite(reference.margin) or not 0 <= reference.margin <= policy.max_margin
            or (r.bookmaker == "Pinnacle" and reference.method != "power")
            or (r.bookmaker == "Betfair" and (reference.method != "back_lay_interval"
                or not _finite(reference.liquidity) or reference.liquidity < policy.min_liquidity
                or not _finite(reference.spread) or not 0 <= reference.spread <= policy.exchange_gap))):
        return Decision(False, "unreliable_reference", "L1")
    # Les cotes à deux issues ne permettent pas d'identifier la masse du push.
    m = offer.market
    has_push = (m.name in {"HANDICAP", "TOTAL"} and _finite(m.line) and m.line == int(m.line)
                or m.name == "VAINQUEUR" and m.scope == "REGULATION")
    push = reference.push_probability
    if has_push and push is None:
        return Decision(False, "push_probability_unknown", "L1")
    if push is not None and (not _finite(push) or not 0 <= push < 1 or not has_push and push != 0):
        return Decision(False, "invalid_push_probability", "L1")
    edge = (offer.odds * reference.lower_probability - 1) * (1 - (push or 0))
    return Decision(edge >= policy.min_edge - 1e-12, "candidate" if edge >= policy.min_edge - 1e-12
                    else "edge_too_small", "L1", edge, 1 / reference.probability)


@dataclass(frozen=True)
class ClosingContext:
    event_id: str
    sport: str
    reference: str
    kickoff: datetime
    captured_at: datetime          # dernier composant du snapshot ; tous avant kickoff
    oldest_component_at: datetime
    rules: str
    version: str                  # version du modèle / profil figé, indispensable à l'audit
    scope: str = "REGULATION"

    def validate(self):
        if (not self.event_id or self.sport not in SPORTS or self.reference not in REFERENCES
                or not self.rules or not self.version or self.scope not in {"REGULATION", "SETS"}
                or not all(_aware(t) for t in (self.kickoff, self.captured_at, self.oldest_component_at))
                or not 0 < (self.kickoff - self.captured_at).total_seconds() <= 900
                or not 0 <= (self.captured_at - self.oldest_component_at).total_seconds() <= 30
                or (self.kickoff - self.oldest_component_at).total_seconds() > 900):
            raise ValueError("clôture absente, tardive, désynchronisée ou insuffisamment documentée")


def _poisson(lam: float) -> tuple[float, ...]:
    if not _finite(lam) or not 0 <= lam <= 40:
        raise ValueError("intensité hors domaine")
    ps = [math.exp(-lam)]
    for k in range(1, 201):
        ps.append(ps[-1] * lam / k)
        if k > lam and 1 - sum(ps) < 1e-13:
            break
    total = sum(ps)
    return tuple(x / total for x in ps)


def _classify(m: Market, home: float, away: float) -> int:
    if m.name in {"VAINQUEUR", "RESULTAT_1N2"}:
        if m.issue == "NUL" and m.name == "RESULTAT_1N2":
            return 1 if home == away else -1
        diff = home - away if m.issue == "DOM" else away - home
        return (1 if diff > 0 else -1 if diff < 0 else
                0 if m.name == "VAINQUEUR" else -1)
    if m.name == "HANDICAP":
        diff = home - away + m.line
        diff = diff if m.issue == "DOM" else -diff
    elif m.name == "TOTAL":
        diff = home + away - m.line
        diff = diff if m.issue == "PLUS" else -diff
    else:
        raise ValueError("marché L2 non pris en charge")
    return 1 if diff > 0 else -1 if diff < 0 else 0


def _market(m: Market):
    expected = {"DOM", "NUL", "EXT"} if m.name == "RESULTAT_1N2" else (
        {"DOM", "EXT"} if m.name in {"VAINQUEUR", "HANDICAP"} else
        {"PLUS", "MOINS"} if m.name == "TOTAL" else set())
    if m.issue not in expected or (m.name in {"HANDICAP", "TOTAL"} and not _half_line(m.line)):
        raise ValueError("marché, issue ou ligne L2 non pris en charge")
    if m.name in {"VAINQUEUR", "RESULTAT_1N2"} and m.line is not None:
        raise ValueError("ligne inattendue")


def _discrete(m: Market, scores: list[tuple[int, int, float]]) -> Outcome:
    weights = {1: 0., 0: 0., -1: 0.}
    for home, away, p in scores:
        weights[_classify(m, home, away)] += p
    total = sum(weights.values())
    return Outcome(*(max(0, weights[k] / total) for k in (1, 0, -1)))


@dataclass(frozen=True)
class PoissonModel:
    closing: ClosingContext
    home_rate: float
    away_rate: float
    second_half_share: float | None = None

    def project(self, m: Market, s: PauseState) -> Outcome:
        _market(m)
        if self.closing.sport not in {"football", "hockey"} or m.scope != "REGULATION" or m.unit != "goals":
            raise ValueError("Poisson réservé aux buts du temps réglementaire")
        if s.sport == "football":
            if s.boundary != "HT" or not _prob(self.second_half_share):
                raise ValueError("profil temporel football requis")
            remaining = self.second_half_share
        else:
            remaining = {"P1": 2 / 3, "P2": 1 / 3}.get(s.boundary)
            if remaining is None:
                raise ValueError("pause hockey inconnue")
        # Valide aussi les intensités avant de les réduire.
        for rate in (self.home_rate, self.away_rate):
            if not _finite(rate) or not 0 < rate <= 20:
                raise ValueError("intensité invalide")
        h, a = _poisson(self.home_rate * remaining), _poisson(self.away_rate * remaining)
        return _discrete(m, [(s.score[0] + i, s.score[1] + j, pi * pj)
                             for i, pi in enumerate(h) for j, pj in enumerate(a)])


def fit_poisson(closing: ClosingContext, probabilities_1n2: tuple[float, float, float],
                total_line: float, over_probability: float, *,
                second_half_share: float | None = None, max_error: float = .025) -> PoissonModel:
    """Inverse total demi-entier puis partage DOM/EXT ; rejette un 1N2 incompatible.

    Entrées = probabilités sans marge du MÊME snapshot pré-match. Les buts sont
    indépendants : ajustement imparfait normal, mais aucune calibration forcée.
    """
    closing.validate()
    if (closing.sport not in {"football", "hockey"} or closing.scope != "REGULATION"
            or len(probabilities_1n2) != 3 or not all(_prob(p) for p in probabilities_1n2)
            or abs(sum(probabilities_1n2) - 1) > 1e-6 or not _half_line(total_line)
            or total_line < .5 or total_line > 19.5 or int(total_line) == total_line
            or not _prob(over_probability) or not _finite(max_error) or not 0 < max_error <= .05):
        raise ValueError("snapshot Poisson invalide")
    lo, hi = .01, 20.
    def over(rate):
        return sum(p for n, p in enumerate(_poisson(rate)) if n > total_line)
    if not over(lo) < over_probability < over(hi):
        raise ValueError("total hors domaine")
    for _ in range(60):
        mid = (lo + hi) / 2
        if over(mid) < over_probability:
            lo = mid
        else:
            hi = mid
    total = (lo + hi) / 2
    def probs(share):
        h, a = _poisson(total * share), _poisson(total * (1 - share))
        return tuple(sum(pi * pj for i, pi in enumerate(h) for j, pj in enumerate(a)
                         if (i > j if k == 0 else i == j if k == 1 else i < j)) for k in range(3))
    lo, hi = .001, .999
    for _ in range(55):
        x, y = lo + (hi - lo) / 3, hi - (hi - lo) / 3
        loss = lambda z: sum((a - b) ** 2 for a, b in zip(probs(z), probabilities_1n2))
        if loss(x) < loss(y):
            hi = y
        else:
            lo = x
    share = (lo + hi) / 2
    if max(abs(a - b) for a, b in zip(probs(share), probabilities_1n2)) > max_error:
        raise ValueError("clôture incompatible avec Poisson indépendant")
    return PoissonModel(closing, total * share, total * (1 - share), second_half_share)


def _normal_outcome(mean: float, sigma: float, line: float, side: int,
                    lower_bound: int | None = None) -> Outcome:
    # Scores entiers : correction de continuité et remboursement des lignes entières.
    n = NormalDist(mean, sigma)
    if line == int(line):
        loss, win = n.cdf(line - .5), 1 - n.cdf(line + .5)
    else:
        loss = n.cdf(math.ceil(line) - .5)
        win = 1 - loss
    if lower_bound is not None:
        if line < lower_bound:
            return Outcome(1, 0, 0) if side == 1 else Outcome(0, 0, 1)
        floor = n.cdf(lower_bound - .5)
        if floor >= 1:
            raise ValueError("distribution résiduelle dégénérée")
        loss, win = max(0, loss - floor) / (1 - floor), win / (1 - floor)
    push = max(0, 1 - win - loss)
    return Outcome(win, push, loss) if side == 1 else Outcome(loss, push, win)


@dataclass(frozen=True)
class GaussianModel:
    closing: ClosingContext
    mean_difference: float
    mean_total: float
    sigma_difference: float
    sigma_total: float             # ne PAS réutiliser sigma_difference pour les totaux

    def project(self, m: Market, s: PauseState) -> Outcome:
        _market(m)
        unit = "goals" if s.sport == "handball" else "points"
        if self.closing.sport not in {"basket", "handball"} or m.scope != "REGULATION" or m.unit != unit:
            raise ValueError("Gaussien réservé au basket/handball réglementaire")
        if (not all(_finite(x) for x in (self.mean_difference, self.mean_total,
                                        self.sigma_difference, self.sigma_total))
                or not 0 < self.sigma_difference <= 100 or not 0 < self.sigma_total <= 150
                or self.mean_total <= abs(self.mean_difference)):
            raise ValueError("profil gaussien invalide")
        r = {"HT": .5, "QT1": .75, "QT3": .25}.get(s.boundary)
        if r is None or (s.sport == "handball" and s.boundary != "HT"):
            raise ValueError("pause non prise en charge")
        diff = s.score[0] - s.score[1] + r * self.mean_difference
        sd = math.sqrt(r) * self.sigma_difference
        if m.name == "TOTAL":
            return _normal_outcome(sum(s.score) + r * self.mean_total,
                                   math.sqrt(r) * self.sigma_total, m.line,
                                   1 if m.issue == "PLUS" else -1, lower_bound=sum(s.score))
        if m.name == "HANDICAP":
            return _normal_outcome(diff, sd, -m.line, 1 if m.issue == "DOM" else -1)
        result = _normal_outcome(diff, sd, 0, 1)
        if m.name == "RESULTAT_1N2":
            p = {"DOM": result.win, "NUL": result.push, "EXT": result.loss}[m.issue]
            return Outcome(p, 0, 1 - p)
        # VAINQUEUR en REGULATION signifie ici remboursé si nul (rules doit le préciser).
        return result if m.issue == "DOM" else Outcome(result.loss, result.push, result.win)


def fit_gaussian(closing: ClosingContext, handicap_line: float, home_probability: float,
                 total_line: float, over_probability: float, *,
                 sigma_difference: float, sigma_total: float) -> GaussianModel:
    """Deux lignes demi-entières, probabilités sans marge, sigmas fournis par profil.

    Pas de valeur 11,5 ou 4,5 universelle codée en dur. L'écart-type dépend de la
    compétition, des règles et de l'échantillon de calibration.
    """
    closing.validate()
    if (closing.sport not in {"basket", "handball"} or closing.scope != "REGULATION"
            or not all(_half_line(x) and int(x) != x for x in (handicap_line, total_line))
            or not all(_prob(x) for x in (home_probability, over_probability))
            or not _finite(sigma_difference) or not 0 < sigma_difference <= 100
            or not _finite(sigma_total) or not 0 < sigma_total <= 150):
        raise ValueError("snapshot gaussien invalide")
    z = NormalDist().inv_cdf
    model = GaussianModel(closing, -handicap_line + sigma_difference * z(home_probability),
                          total_line + sigma_total * z(over_probability), sigma_difference, sigma_total)
    if model.mean_total <= abs(model.mean_difference):
        raise ValueError("moyennes incohérentes")
    return model


def set_match_probability(p: float, to_win: int, home: int = 0, away: int = 0,
                          deciding_set_probability: float | None = None) -> float:
    if (not _prob(p) or type(to_win) is not int or to_win not in (2, 3)
            or any(type(x) is not int or x < 0 or x > to_win for x in (home, away))
            or home == away == to_win
            or (deciding_set_probability is not None and not _prob(deciding_set_probability))):
        raise ValueError("format ou probabilité de set invalide")
    @lru_cache(None)
    def rec(h, a):
        if h == to_win:
            return 1.
        if a == to_win:
            return 0.
        q = deciding_set_probability if h == a == to_win - 1 and deciding_set_probability is not None else p
        return q * rec(h + 1, a) + (1 - q) * rec(h, a + 1)
    return rec(home, away)


@dataclass(frozen=True)
class SetsModel:
    closing: ClosingContext
    set_probability: float
    to_win: int
    standard_format: bool         # faux pour super tie-break / format inconnu
    deciding_set_probability: float | None = None

    def project(self, m: Market, s: PauseState) -> Outcome:
        _market(m)
        if (self.closing.sport not in {"tennis", "volley"} or not self.standard_format
                or m.scope != "SETS" or m.unit != "sets"):
            raise ValueError("format de sets inconnu ou différent")
        set_match_probability(self.set_probability, self.to_win, *s.score, self.deciding_set_probability)
        if max(s.score) >= self.to_win:
            raise ValueError("match déjà terminé")
        terminal = []
        def rec(h, a, weight):
            if h == self.to_win or a == self.to_win:
                terminal.append((h, a, weight))
                return
            q = (self.deciding_set_probability if h == a == self.to_win - 1
                 and self.deciding_set_probability is not None else self.set_probability)
            rec(h + 1, a, weight * q)
            rec(h, a + 1, weight * (1 - q))
        rec(*s.score, 1.)
        return _discrete(m, terminal)


def fit_sets(closing: ClosingContext, match_probability: float, to_win: int, *,
             standard_format: bool, deciding_set_probability: float | None = None) -> SetsModel:
    closing.validate()
    if (closing.sport not in {"tennis", "volley"} or closing.scope != "SETS"
            or not standard_format or not _prob(match_probability)):
        raise ValueError("snapshot ou format de sets invalide")
    # Dans le modèle IID best-of-3 : P_match = 3 p² - 2 p³.
    lo, hi = 1e-9, 1 - 1e-9
    for _ in range(65):
        p = (lo + hi) / 2
        if set_match_probability(p, to_win, deciding_set_probability=deciding_set_probability) < match_probability:
            lo = p
        else:
            hi = p
    return SetsModel(closing, (lo + hi) / 2, to_win, standard_format, deciding_set_probability)


def evaluate_l2(offer: LiveQuote, model: PoissonModel | GaussianModel | SetsModel,
                now: datetime, policy: Policy = Policy()) -> Decision:
    error = _quote_error(offer, now, policy)
    if error:
        return Decision(False, error, "L2")
    if offer.bookmaker not in FRANCAIS:
        return Decision(False, "unsupported_bookmaker", "L2")
    c, m, s = model.closing, offer.market, offer.state
    try:
        c.validate()
        _market(m)
        if (c.event_id, c.sport, c.scope, c.rules) != (m.event_id, m.sport, m.scope, m.rules):
            return Decision(False, "closing_contract_mismatch", "L2")
        if c.kickoff >= now:
            return Decision(False, "match_not_started", "L2")
        if not s.context_complete or s.incidents:
            return Decision(False, "missing_or_exceptional_context", "L2")
        if isinstance(model, SetsModel):
            before = set_match_probability(model.set_probability, model.to_win,
                                           deciding_set_probability=model.deciding_set_probability)
            favorite = "DOM" if before >= policy.sets_favorite_min else (
                "EXT" if 1 - before >= policy.sets_favorite_min else None)
            lost_first = (0, 1) if favorite == "DOM" else (1, 0)
            if (favorite is None or m.name != "VAINQUEUR" or m.issue != favorite
                    or s.boundary != "SET1" or s.score != lost_first):
                return Decision(False, "sets_rebound_filter", "L2")
        outcome = model.project(m, s)
        if outcome.win == 0 or outcome.loss == 0:
            return Decision(False, "already_decided_market", "L2")
        edge = outcome.edge(offer.odds)
        accepted = edge >= policy.min_edge - 1e-12
        return Decision(accepted, "experimental_candidate" if accepted else "edge_too_small",
                        "L2", edge, outcome.fair_odds, outcome)
    except (ValueError, OverflowError):
        return Decision(False, "unsupported_or_invalid_model", "L2")
