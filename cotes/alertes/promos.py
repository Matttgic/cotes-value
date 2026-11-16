"""Alertes Pushover des surebets et des cotes boostées (cotes/surebets.py, cotes/boosts.py).

Deux cases du bloc « Alertes Pushover » du site, à côté des stratégies : ``surebets`` et ``boosts``. Un surebet part
une fois par épisode (même match, même marché, cotes/surebets.py › ``suivre``) dès que son rendement atteint
``SUREBET_SEUIL_ALERTE`` (1 % par défaut) ; une cote boostée part une fois, quand sa value contre la cote juste
atteint ``BOOST_SEUIL_ALERTE`` (3 %). Jamais un surebet suspect, jamais un match commencé, jamais un relevé de plus de
``FRAICHEUR`` (le prix a pu partir). Mises d'un surebet : 10 % de ``PUSHOVER_BANKROLL`` répartis (100 € par défaut).
Un boost couvert (cotes/boosts.py › ``couverts`` : gain garanti, boost à sa mise maximale) part une fois, dès que son
rendement atteint ``SUREBET_SEUIL_ALERTE``, si l'une des deux cases est cochée ; il remplace alors l'alerte de value
du même boost.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from cotes.alertes.webhook import JOURS, _fr
from cotes.surebets import repartir
from cotes.temps import instant_utc

SPECIALES = {"surebets": "Surebets (gain garanti sur le papier)", "boosts": "Cotes boostées en value",
             "milieux": "Milieux en value (page Euria)"}
DETAILS = {"surebets": "Rendement ≥ 1 % · mises réparties sur 10 % de la bankroll Pushover · et boosts couverts",
           "boosts": "Value ≥ 3 % contre la cote juste · mise maximale du boost · et boosts couverts",
           "milieux": "Espérance ≥ 2 % de la mise · mises réparties sur 10 % de la bankroll Pushover"}
FRAICHEUR = timedelta(minutes=12)
PARIS = ZoneInfo("Europe/Paris")
TTL_MAX_S = 86400


def _seuil(brut, defaut: float) -> float:
    """Seuil lu dans l'environnement ; absent ou illisible : le défaut."""
    try:
        v = float(str(brut or defaut).replace(",", "."))
    except ValueError:
        return defaut
    return v if 0 <= v < 1 else defaut


def _heure(iso) -> str:
    t = instant_utc(iso)
    if t is None:
        return "heure inconnue"
    d = t.astimezone(PARIS)
    return f"{JOURS[d.weekday()]} {d:%d/%m} {d:%H}h{d:%M}"


def _lire(chemin: Path) -> dict:
    try:
        doc = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return doc if isinstance(doc, dict) else {}


def _frais(doc: dict, maintenant: datetime) -> bool:
    maj = instant_utc(doc.get("maj"))
    return maj is not None and timedelta(0) <= maintenant - maj <= FRAICHEUR


def _a_venir(x: dict, maintenant: datetime) -> bool:
    debut = instant_utc(x.get("debut"))
    return debut is not None and debut > maintenant


def alertes_surebets(doc: dict, envoyes: dict, maintenant: datetime, seuil: float | None = None) -> list[dict]:
    """Surebets du dernier relevé pas encore envoyés pour leur épisode en cours."""
    minimum = _seuil(os.environ.get("SUREBET_SEUIL_ALERTE"), 0.01) if seuil is None else seuil
    if not _frais(doc, maintenant):
        return []
    debuts: dict[str, str] = {}
    for e in doc.get("episodes") or []:
        if isinstance(e, dict) and e.get("cle"):
            debuts[e["cle"]] = max(debuts.get(e["cle"], ""), str(e.get("premier") or ""))
    out = []
    for s in doc.get("actuels") or []:
        if not isinstance(s, dict) or s.get("suspect") or (s.get("rendement") or 0) < minimum or not _a_venir(s, maintenant):
            continue
        ident = f'surebet:{s.get("cle")}|{debuts.get(s.get("cle"), "")}'
        if ident not in envoyes:
            out.append({**s, "type": "surebet", "id": ident})
    return out


def alertes_boosts(doc: dict, envoyes: dict, maintenant: datetime, seuil: float | None = None) -> list[dict]:
    """Cotes boostées en value du dernier relevé, une seule fois chacune."""
    minimum = _seuil(os.environ.get("BOOST_SEUIL_ALERTE"), 0.03) if seuil is None else seuil
    if not _frais(doc, maintenant):
        return []
    return [{**b, "type": "boost", "id": f'boost:{b.get("id")}'} for b in doc.get("actuels") or []
            if isinstance(b, dict) and isinstance(b.get("value"), (int, float)) and b["value"] >= minimum
            and _a_venir(b, maintenant) and f'boost:{b.get("id")}' not in envoyes]


def alertes_couverts(doc: dict, envoyes: dict, maintenant: datetime, seuil: float | None = None) -> list[dict]:
    """Boosts couverts du dernier relevé (gain garanti), une seule fois chacun."""
    minimum = _seuil(os.environ.get("SUREBET_SEUIL_ALERTE"), 0.01) if seuil is None else seuil
    if not _frais(doc, maintenant):
        return []
    return [{**c, "type": "couvert", "id": f'couvert:{c.get("cle")}'} for c in doc.get("couverts") or []
            if isinstance(c, dict) and not c.get("suspect") and (c.get("rendement") or 0) >= minimum
            and c.get("jambes") and _a_venir(c, maintenant) and f'couvert:{c.get("cle")}' not in envoyes]


def alertes_milieux(doc: dict, envoyes: dict, maintenant: datetime, seuil: float | None = None) -> list[dict]:
    """Milieux du dernier relevé (cotes/euria.py) dont l'espérance atteint ``MILIEU_SEUIL_ALERTE`` (2 % de la mise),
    une fois par épisode."""
    minimum = _seuil(os.environ.get("MILIEU_SEUIL_ALERTE"), 0.02) if seuil is None else seuil
    if not _frais(doc, maintenant):
        return []
    premiers = {e.get("cle"): str(e.get("premier") or "") for e in doc.get("episodes_milieux") or [] if isinstance(e, dict)}
    out = []
    for m in doc.get("milieux") or []:
        if not isinstance(m, dict) or (m.get("esperance_100") or 0) < 100 * minimum or not _a_venir(m, maintenant) \
                or len(m.get("jambes") or []) != 2:
            continue
        ident = f'milieu:{m.get("cle")}|{premiers.get(m.get("cle"), "")}'
        if ident not in envoyes:
            out.append({**m, "type": "milieu", "id": ident})
    return out


def alertes(donnees: Path, envoyes: dict, choisies: set[str], maintenant: datetime) -> list[dict]:
    out = []
    if "milieux" in choisies:
        out += alertes_milieux(_lire(donnees / "euria.json"), envoyes, maintenant)
    if "surebets" in choisies:
        out += alertes_surebets(_lire(donnees / "surebets.json"), envoyes, maintenant)
    if "surebets" in choisies or "boosts" in choisies:
        doc = _lire(donnees / "boosts.json")
        couverts = alertes_couverts(doc, envoyes, maintenant)
        out += couverts
        if "boosts" in choisies:                 # le boost couvert remplace l'alerte de value du même boost
            maintenant_couverts = {str(c.get("boost_id")) for c in couverts}
            envoyes_couverts = [k for k in envoyes if k.startswith("couvert:")]
            out += [a for a in alertes_boosts(doc, envoyes, maintenant)
                    if a["id"][6:] not in maintenant_couverts
                    and not any(k.startswith(f'couvert:{a["id"][6:]}|') for k in envoyes_couverts)]
    return out


def _lien(champs: dict, lien, chez: str) -> None:
    if isinstance(lien, str) and lien.startswith("https://") and len(lien) <= 500:
        champs["url"], champs["url_title"] = lien, f"Ouvrir chez {chez}"[:100]


def message_surebet(s: dict, bankroll: float) -> dict:
    """Titre, corps et lien Pushover d'un surebet : chaque mise, le retour garanti, vérifié ou non."""
    total = max(10.0, round(bankroll / 10))
    rep = repartir([j["cote"] for j in s["jambes"]], total)
    lignes = [f'{s.get("pari")} · {_heure(s.get("debut"))}']
    for j, m in zip(s["jambes"], rep["mises"]):
        lignes.append(f'{j.get("bookmaker")} : {j.get("pari")} {_fr(j.get("cote"), 2)} → {_fr(m, 0)} €')
    gain = rep["gain_min"]
    lignes.append(f'Retour d\'au moins {_fr(rep["mise_totale"] + gain, 2)} € pour {_fr(rep["mise_totale"], 0)} € '
                  f'({"+" if gain >= 0 else ""}{_fr(gain, 2)} €), quoi qu\'il arrive.')
    lignes.append("Vérifié par la cote juste." if s.get("verifie")
                  else "Non vérifié : contrôle que les paris portent sur le même marché.")
    lignes.append("Mise d'abord la cote la plus rare : l'autre peut bouger.")
    champs = {"title": f'Surebet +{_fr(100 * s["rendement"], 1)} % · {s.get("match")}'[:250],
              "message": "\n".join(lignes)[:1000]}
    premiere = next((j for j in s["jambes"] if j.get("lien") and not j.get("lien_repli")), s["jambes"][0])
    _lien(champs, premiere.get("lien"), premiere.get("bookmaker") or "le bookmaker")
    return champs


def message_boost(b: dict) -> dict:
    """Titre, corps et lien Pushover d'une cote boostée en value."""
    lignes = [str(b.get("libelle") or ""),
              f'{b.get("bookmaker")} {_fr(b.get("cote"), 2)} (avant {_fr(b.get("cote_avant"), 2)})'
              + (f' · mise max {_fr(b.get("mise_max"), 0)} €' if b.get("mise_max") else ""),
              f'Cote juste {_fr(b.get("cote_juste"), 2)} ({b.get("reference")}) · value +{_fr(100 * b["value"], 1)} %',
              f'Pari : {b.get("pari")} · {_heure(b.get("debut"))}']
    champs = {"title": f'Boost +{_fr(100 * b["value"], 1)} % · {b.get("domicile")} – {b.get("exterieur")}'[:250],
              "message": "\n".join(lignes)[:1000]}
    _lien(champs, b.get("lien"), b.get("bookmaker") or "le bookmaker")
    return champs


def message_couvert(c: dict) -> dict:
    """Titre, corps et lien Pushover d'un boost couvert : le boost à sa mise maximale, chaque couverture, le gain."""
    lignes = [f'{c.get("libelle")} · {_heure(c.get("debut"))}']
    for j in c["jambes"]:
        quoi = f'boost {_fr(j.get("cote"), 2)}' if j.get("boost") else f'{j.get("pari")} {_fr(j.get("cote"), 2)}'
        lignes.append(f'{j.get("bookmaker")} : {quoi} → {_fr(j.get("mise"), 2)} €')
    gain = c.get("gain") or 0
    lignes.append(f'Gain d\'au moins {"+" if gain >= 0 else ""}{_fr(gain, 2)} € pour {_fr(c.get("mise_totale"), 2)} € '
                  f'misés, quoi qu\'il arrive' + ("." if c.get("mise_max") else " (mise max inconnue : 10 € sur le boost)."))
    lignes.append("Vérifié par la cote juste." if c.get("verifie")
                  else "Non vérifié : contrôle que le boost et la couverture portent sur le même pari.")
    lignes.append("Mise d'abord le boost, puis la couverture.")
    champs = {"title": f'Boost couvert +{_fr(100 * c["rendement"], 1)} % · {c.get("match")}'[:250],
              "message": "\n".join(lignes)[:1000]}
    boost = next((j for j in c["jambes"] if j.get("boost")), c["jambes"][0])
    _lien(champs, boost.get("lien"), boost.get("bookmaker") or "le bookmaker")
    return champs


def message_milieu(m: dict, bankroll: float) -> dict:
    """Titre, corps et lien Pushover d'un milieu : les deux mises, le résultat dans et hors du milieu, l'espérance."""
    total = max(10.0, round(bankroll / 10))
    k = total / 100
    (a, b), (m1, m2) = m["jambes"], m["mises_100"]
    zone = (f'écart {m.get("de")} à {m.get("a")}' if m.get("ecart") else f'{m.get("de")} à {m.get("a")}') \
        + (f' {m["unite"]}' if m.get("unite") else "")
    lignes = [f'{_heure(m.get("debut"))}',
              f'{a.get("bookmaker")} : {a.get("pari")} {_fr(a.get("cote"), 2)} → {_fr(m1 * k, 0)} €',
              f'{b.get("bookmaker")} : {b.get("pari")} {_fr(b.get("cote"), 2)} → {_fr(m2 * k, 0)} €',
              f'Milieu ({zone}) : {"+" if m["milieu_100"] >= 0 else ""}{_fr(m["milieu_100"] * k, 2)} € ; '
              f'sinon {"+" if m["hors_100"] >= 0 else ""}{_fr(m["hors_100"] * k, 2)} €.',
              f'Chance du milieu {_fr(100 * m["p_milieu"], 1)} % ({m.get("reference")}) · espérance '
              f'+{_fr(m["esperance_100"] * k, 2)} € pour {_fr(total, 0)} €.']
    champs = {"title": f'Milieu +{_fr(m["esperance_100"], 1)} % · {m.get("match")}'[:250],
              "message": "\n".join(lignes)[:1000]}
    premiere = next((j for j in m["jambes"] if j.get("lien") and not j.get("lien_repli")), a)
    _lien(champs, premiere.get("lien"), premiere.get("bookmaker") or "le bookmaker")
    return champs


def ttl(a: dict, maintenant: datetime) -> int | None:
    """Le message reste sur le téléphone jusqu'au coup d'envoi, 24 h au plus."""
    debut = instant_utc(a.get("debut"))
    return int(max(60, min(TTL_MAX_S, (debut - maintenant).total_seconds()))) if debut else None
