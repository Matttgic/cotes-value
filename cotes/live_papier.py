"""Journal prospectif isolé : observations, refus et prix réellement revus à +15/+30 s.

Pas d'ordre de pari, de notification ni d'écriture dans paris.json. Les états ou
horodatages inconnus restent inconnus, même si cela laisse zéro signal L1/L2.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

import requests

from . import pinnacle, pulsescore
from .correspondance import avec_marqueurs_ligue, normaliser
from .comparaison import libelle_pari
from .live_pauses import (ClosingContext, GaussianModel, LiveQuote, Market, PauseState,
                          PoissonModel, _fresh, evaluate_l1, evaluate_l2, fair_reference)

SPORTS = {29: "football", 19: "hockey", 4: "basket", 18: "handball"}
ALIASES = {"soccer": "football", "ice-hockey": "hockey", "ice_hockey": "hockey",
           "basketball": "basket", "handball": "handball"}
FR = {"winamax": "Winamax", "betclic": "Betclic"}
JOURNAL = Path("docs/live_papier.json")  # sur la branche donnees
MAX_OBSERVATIONS = 500


def heure(x):
    try:
        t = datetime.fromisoformat(str(x).replace("Z", "+00:00"))
        return t if t.tzinfo and t.utcoffset() is not None else None
    except (ValueError, TypeError):
        return None


def vide():
    return {"schema": 1, "mode": "papier", "debut": None, "cycles": [], "observations": [], "signaux": []}


def lire(path: Path, default):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return default


def enregistrer(path: Path, document: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(document, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _hash(parts):
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:24]


def _entier(x):
    if type(x) is int and x >= 0:
        return x
    if isinstance(x, str) and x.isdigit():
        return int(x)
    return None


def pause(sport, clock):
    """Libellés explicites uniquement. running=false, Q2/P1 ou minute=45 ne suffisent pas."""
    label = str(clock.get("period") or clock.get("status") or "").strip().lower()
    if label in {"ht", "half time", "halftime", "mi-temps"} and sport in {"football", "basket", "handball"}:
        return "HT"
    if sport == "hockey":
        return {"fin p1": "P1", "fin p2": "P2", "end of period 1": "P1",
                "end of period 2": "P2", "1st intermission": "P1", "2nd intermission": "P2"}.get(label)
    return None


def _event_id(e, sport):
    start = heure(e.get("startTime"))
    if not start or not e.get("home") or not e.get("away"):
        return None
    # Appariement conservateur exact, sans inclusion floue de noms et sans inversion implicite.
    names = [repr(normaliser(avec_marqueurs_ligue(e[k], e.get("league")))) for k in ("home", "away")]
    return _hash([sport, names, start.astimezone(timezone.utc).isoformat()])


def _time_source(e, market):
    # Le timestamp de marché n'est PAS une preuve que son score est frais.
    return heure(market.get("updatedAt")), heure(e.get("updatedAt"))


def traduire_pulse(frame, cycle):
    out = []
    book = frame["source"]
    for e in frame.get("events", []):
        sport = ALIASES.get(e.get("sport"))
        eid = _event_id(e, sport) if sport else None
        if not eid:
            continue
        score = tuple(_entier((e.get("score") or {}).get(k)) for k in ("home", "away"))
        clock = e.get("matchClock") or {}
        boundary = pause(sport, clock)
        unit = "points" if sport == "basket" else "goals"
        for m in e.get("markets") or []:
            price_time, state_time = _time_source(e, m)
            # Réutilise seulement la traduction des intitulés, jamais ses valeurs implicites d'activité.
            active_selections = [s for s in m.get("selections") or []
                                 if m.get("isActive") is True and s.get("isActive") is True
                                 and not m.get("suspended") and not s.get("suspended")]
            for line in pulsescore.traduire({**e, "markets": [{**m, "selections": active_selections}]},
                                            book, sport, frame["received_at"]):
                if line["marche"] not in {"RESULTAT_1N2", "VAINQUEUR", "HANDICAP", "TOTAL"}:
                    continue
                period = line["periode"]
                if period not in {"MATCH", "TEMPS_REG"}:
                    continue
                scope = "INCLUDING_OT" if period == "MATCH" and sport in {"basket", "hockey"} else "REGULATION"
                rules = f"{sport}/{scope}/full_event/v1"
                state = PauseState(eid, sport, cycle, pulsescore.NOMS[book], str(e.get("eventId") or ""),
                                   heure(frame["received_at"]), state_time, score, boundary or "unknown",
                                   "pause" if boundary else "unknown", unit,
                                   context_complete=e.get("context_complete") is True,
                                   incidents=tuple(e.get("incidents") or ()))
                contract = Market(eid, sport, line["marche"], line["issue"], scope, unit, rules, line["ligne"])
                active = (m.get("isActive") is True and not m.get("suspended") and
                          any(s.get("isActive") is True and not s.get("suspended") and
                              s.get("odds") == line["cote"] for s in m.get("selections") or []))
                q = LiveQuote(contract, state, pulsescore.NOMS[book], heure(frame["received_at"]),
                              price_time, line["cote"], active, str(m.get("marketId") or ""))
                out.append({"quote": q, "match": f'{e["home"]} – {e["away"]}',
                            "pari": libelle_pari(line),
                            "back": line.get("achat"), "lay": line.get("vente"),
                            "timestamp_source": bool(price_time and state_time), "native": str(e.get("eventId"))})
    return out


def traduire_pin(frame, cycle):
    out, sport = [], frame["sport"]
    matchups = frame.get("events") or []
    par_id = {m["id"]: m for m in matchups if isinstance(m, dict) and m.get("id") is not None}
    for mk in frame.get("markets") or []:
        mu = par_id.get(mk.get("matchupId"))
        if (not mu or mu.get("isLive") is not True or mu.get("type") != "matchup"
                or mk.get("status") != "open" or mu.get("units") not in (None, "Regular")):
            continue
        # Un matchup live « Regular » peut pointer vers son parent pré-match.
        # Ce n'est pas un sous-marché exotique : garder SON état live et ses équipes.
        parent = mu
        dom, ext = pinnacle._equipes(parent)
        e = {"home": dom, "away": ext, "league": (parent.get("league") or {}).get("name"),
             "startTime": parent.get("startTime")}
        eid = _event_id(e, sport)
        if not eid:
            continue
        raw_state = parent.get("state") or {}
        score = tuple(_entier((raw_state.get("score") or {}).get(k)) for k in ("home", "away"))
        boundary = pause(sport, raw_state)
        if any(p.get("price") in (None, 0) for p in mk.get("prices") or []):
            continue
        for line in pinnacle._lignes_match({**mu, "parentId": None}, mk, mk.get("prices") or [], par_id,
                                          pinnacle.PERIODES[sport], {"sport": sport}):
            if line["marche"] not in {"RESULTAT_1N2", "VAINQUEUR", "HANDICAP", "TOTAL"}:
                continue
            if line["periode"] not in {"MATCH", "TEMPS_REG"}:
                continue
            scope = "INCLUDING_OT" if line["periode"] == "MATCH" and sport in {"basket", "hockey"} else "REGULATION"
            unit = "points" if sport == "basket" else "goals"
            state = PauseState(eid, sport, cycle, "Pinnacle", str(parent["id"]),
                               heure(frame["received_at"]), heure(raw_state.get("updatedAt")), score,
                               boundary or "unknown", "pause" if boundary else "unknown", unit)
            market = Market(eid, sport, line["marche"], line["issue"], scope, unit,
                            f"{sport}/{scope}/full_event/v1", line["ligne"])
            q = LiveQuote(market, state, "Pinnacle", heure(frame["received_at"]), heure(mk.get("updatedAt")),
                          line["cote"], mk.get("status") == "open", str(mk.get("key") or ""))
            out.append({"quote": q, "timestamp_source": bool(q.updated_at and state.updated_at)})
    return out


def collecter(key, *, only_books=None, http=requests):
    """Rafale indépendante des collectes pré-match, bornée et sans réessai."""
    jobs = [(b, None) for b in (only_books or ("winamax", "betclic", "orbitxch"))]
    if only_books is None:
        jobs += [("Pinnacle", (sid, sport)) for sid, sport in SPORTS.items()]
    def get(url, headers, params=None):
        try:
            r = http.get(url, headers=headers, params=params, timeout=8)
            if r.status_code != 200:
                return None, f"HTTP {r.status_code}"
            return r.json(), None
        except (requests.RequestException, ValueError):
            return None, "lecture_indisponible"
    def one(job):
        source, spec = job
        started = datetime.now(timezone.utc).isoformat()
        if source != "Pinnacle":
            d, error = get(f"{pulsescore.BASE}/{source}/live-events", {"X-Secret": key}, {"page": 1, "limit": 30})
            events = d.get("events") if isinstance(d, dict) else None
            return {"source": source, "started_at": started, "received_at": datetime.now(timezone.utc).isoformat(),
                    "events": events if isinstance(events, list) else [], "requests": 1,
                    "has_next_page": d.get("hasNextPage") if isinstance(d, dict) else None,
                    "error": error or (None if isinstance(events, list) else "schema_inattendu")}
        sid, sport = spec
        ev, error1 = get(f"{pinnacle.BASE}/sports/{sid}/matchups?withSpecials=true", pinnacle.HEADERS)
        mk, error2 = get(f"{pinnacle.BASE}/sports/{sid}/markets/straight?primaryOnly=false&withSpecials=true", pinnacle.HEADERS)
        return {"source": source, "sport": sport, "started_at": started,
                "received_at": datetime.now(timezone.utc).isoformat(), "events": ev if isinstance(ev, list) else [],
                "markets": mk if isinstance(mk, list) else [], "requests": 2,
                "error": error1 or error2 or (None if isinstance(ev, list) and isinstance(mk, list) else "schema_inattendu")}
    with ThreadPoolExecutor(max_workers=7) as pool:
        return list(pool.map(one, jobs))


def _model(document):
    c = dict(document["closing"])
    for k in ("kickoff", "captured_at", "oldest_component_at"):
        c[k] = heure(c[k])
    context = ClosingContext(**c)
    context.validate()
    factory = {"poisson": PoissonModel, "gaussian": GaussianModel}[document["type"]]
    return factory(context, **document["parameters"])


def analyser(frames, now, cycle, models=None):
    rows, counts, errors = [], Counter(), []
    for f in frames:
        if f.get("error"):
            errors.append(f'{f["source"]}: {f["error"]}')
        try:
            rows += traduire_pin(f, cycle) if f["source"] == "Pinnacle" else traduire_pulse(f, cycle)
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
            errors.append(f'{f["source"]}: normalisation_refusee')
    groups, refs = defaultdict(list), {}
    for row in rows:
        q = row["quote"]
        counts["prix_lus"] += 1
        if q.bookmaker not in FR.values():
            groups[(q.bookmaker, replace(q.market, issue="*"))].append(row)
    for (book, _), group in groups.items():
        try:
            qs = tuple(r["quote"] for r in group)
            kwargs = {}
            if book == "Betfair":
                kwargs = {"lay_odds": tuple(float(r["lay"][0]["price"]) for r in group),
                          "liquidity": tuple(min(float(r["lay"][0]["liquidity"]), float(r["back"][0]["liquidity"]))
                                             for r in group)}
                qs = tuple(replace(r["quote"], odds=float(r["back"][0]["price"])) for r in group)
            for ref in fair_reference(qs, now, **kwargs):
                refs.setdefault(ref.quote.market, []).append(ref)
        except (ValueError, TypeError, KeyError, IndexError):
            counts["references_non_verifiees"] += 1
    observations = []
    for row in rows:
        q = row["quote"]
        if q.bookmaker not in FR.values():
            continue
        if not math.isfinite(q.odds):
            counts["prix_invalide"] += 1
            continue
        if q.state.phase != "pause":
            counts["pause_non_confirmee"] += 1
            continue
        counts["prix_en_pause"] += 1
        # Au plus six observations nouvelles par cycle : maîtrise appels, taille et exposition.
        if len(observations) >= 6:
            continue
        decisions = [evaluate_l1(q, ref, now) for ref in refs.get(q.market, [])]
        l1 = max(decisions, key=lambda d: d.edge if d.edge is not None else -999) if decisions else None
        l2, l2_error = None, "cloture_complete_ou_profil_absent"
        if q.market.event_id in (models or {}):
            try:
                l2 = evaluate_l2(q, _model(models[q.market.event_id]), now)
            except (ValueError, KeyError, TypeError):
                l2_error = "cloture_ou_profil_invalide"
        accepted = bool(l1 and l1.accepted or l2 and l2.accepted)
        decision = l1 if l1 and l1.accepted else l2 if l2 and l2.accepted else l1 or l2
        key = [asdict(q.market), q.bookmaker, q.state.boundary, q.state.score]
        observations.append({"id": _hash([cycle, key]), "signal_id": _hash(key), "observe_le": now.isoformat(),
            "mode": "papier", "match": row["match"], "sport": q.market.sport, "bookmaker": q.bookmaker,
            "pari": row["pari"], "cote": q.odds, "score": q.state.score, "pause": q.state.boundary,
            "contrat": asdict(q.market), "native": row["native"], "active": q.active,
            "signal": accepted, "edge": decision.edge if decision else None,
            "cote_juste": decision.fair_odds if decision else None,
            "l1": asdict(l1) if l1 else {"accepted": False, "reason": "reference_live_non_verifiee"},
            "l2": asdict(l2) if l2 else {"accepted": False, "reason": l2_error},
            "timestamp_source_verifie": (_fresh(q.received_at, q.updated_at, now, 30)
                                           and _fresh(q.state.received_at, q.state.updated_at, now, 15)),
            "prix_suivants": {},
            "execution": "montant_acceptation_et_liquidite_bookmaker_inconnus"})
    starts = [heure(f["started_at"]) for f in frames]
    ends = [heure(f["received_at"]) for f in frames]
    span = (max(ends) - min(starts)).total_seconds() if starts else 0
    if span >= 20:
        counts["rafale_hors_delai"] += 1
        for o in observations:
            o.update(signal=False, edge=None, cote_juste=None, refus_rafale="ecart_reel_ge_20s")
            for logic in ("l1", "l2"):
                o[logic] = {**o[logic], "accepted": False, "reason": "burst_too_slow"}
    pulse_counts = Counter()
    for f in frames:
        if f["source"] != "Pinnacle":
            pulse_counts[f["source"]] += f["requests"]
    return observations, {"debut": cycle, "fin": now.isoformat(), "mode": "papier",
        "rafale_secondes": round(span, 3), "rafale_sous_20s": span < 20,
        "requetes": sum(f["requests"] for f in frames), "requetes_pulsescore": dict(pulse_counts),
        "compteurs": dict(counts), "erreurs": errors,
        "sources": [{"source": f["source"], "sport": f.get("sport"), "evenements": len(f.get("events", [])),
                     "page_suivante": f.get("has_next_page"), "recu": f["received_at"]} for f in frames]}


def relever(observation, frames, now, target):
    rows = []
    for frame in frames:
        try:
            rows += traduire_pulse(frame, "suivi")
        except (ValueError, TypeError, KeyError, AttributeError):
            pass
    matches = [r for r in rows if asdict(r["quote"].market) == observation["contrat"]
               and r["quote"].bookmaker == observation["bookmaker"] and r["native"] == observation["native"]]
    delay = (now - heure(observation["observe_le"])).total_seconds()
    result = {"cible_secondes": target, "observe_le": now.isoformat(), "delai_reel_secondes": round(delay, 3),
              "cote": None, "statut": "absent_sur_page_ou_lecture_indisponible"}
    if matches:
        row = matches[0]
        q = row["quote"]
        same_state = q.state.phase == "pause" and q.state.boundary == observation["pause"] and list(q.state.score) == list(observation["score"])
        result.update(cote=q.odds, active=q.active, meme_pause_score=same_state,
                      timestamp_source_verifie=(_fresh(q.received_at, q.updated_at, now, 30)
                                                and _fresh(q.state.received_at, q.state.updated_at, now, 15)),
                      statut="observe" if same_state and q.active else "reprise_ou_marche_inactif")
    if abs(delay - target) > 5:
        result["hors_fenetre"] = True
    return result


def fusionner(old, observations, cycle):
    # Ne réécrit jamais les premiers prix, dates ou edges d'une observation/signal passé.
    result = {**old, "debut": old.get("debut") or cycle["debut"]}
    existing = {o["id"] for o in old.get("observations", [])}
    result["observations"] = (old.get("observations", []) + [o for o in observations if o["id"] not in existing])[-MAX_OBSERVATIONS:]
    signals = {o["signal_id"]: o for o in old.get("signaux", [])}
    for o in observations:
        if o["signal"]:
            signals.setdefault(o["signal_id"], o)
    result["signaux"] = list(signals.values())[-MAX_OBSERVATIONS:]
    result["cycles"] = (old.get("cycles", []) + [cycle])[-100:]
    return result


def lancer(donnees: Path, key: str):
    """Rafale d'abord ; suivis en arrière-plan pendant les collectes lentes pré-match.

    Retourne une finalisation appelée AVANT le commit des données. Les erreurs
    se rapportent au journal live, jamais aux sélections ni aux gains pré-match.
    """
    cycle = datetime.now(timezone.utc).isoformat()
    frames = collecter(key)
    now = datetime.now(timezone.utc)
    models = lire(donnees / "docs/live_clotures.json", {})
    observations, summary = analyser(frames, now, cycle, models)
    pool = ThreadPoolExecutor(max_workers=1)
    def follow():
        origin = time.monotonic()
        for target in (15, 30):
            if not observations:
                break
            time.sleep(max(0, origin + target - time.monotonic()))
            books = [b for b, name in FR.items() if any(o["bookmaker"] == name for o in observations)]
            fs = collecter(key, only_books=books)
            summary["requetes"] += sum(f["requests"] for f in fs)
            for f in fs:
                counts = summary["requetes_pulsescore"]
                counts[f["source"]] = counts.get(f["source"], 0) + f["requests"]
            observed = datetime.now(timezone.utc)
            for o in observations:
                o["prix_suivants"][str(target)] = relever(o, fs, observed, target)
        return observations
    future = pool.submit(follow)
    def finish():
        try:
            obs = future.result(timeout=55)
            old = lire(donnees / JOURNAL, vide())
            result = fusionner(old, obs, summary)
            enregistrer(donnees / JOURNAL, result)
            return {"observations": len(obs), "signaux": sum(o["signal"] for o in obs),
                    "requetes": summary["requetes"], "requetes_pulsescore": summary["requetes_pulsescore"],
                    "rafale_secondes": summary["rafale_secondes"]}
        finally:
            pool.shutdown(wait=True)
    return finish
