"""Suivi de santé : repère une source de cotes tombée pour de bon (et son retour), sans rien envoyer.

Une panne d'un seul cycle (coupure réseau) ou une lecture partielle « budget » (prévue, la suite est gardée en
cache) ne préviennent pas : il faut SEUIL_CYCLES cycles de suite. L'état (dont le dernier message) est dans donnees/sante_alertes.json.
Ne lève jamais : la surveillance ne doit pas arrêter la collecte.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ETAT = "sante_alertes.json"
INCIDENTS = "sante_incidents.json"  # journal des 24 dernières heures, affiché sur la page Santé du site
GARDE_INCIDENTS = timedelta(hours=24)
MAX_TERMINES = 60
SEUIL_REFUS = 3                     # cycles de suite avant qu'un refus 403/429 devienne un incident (sinon bruit)
SEUIL_CYCLES = 2                    # cycles de suite avant d'alerter (toutes les ~5 min)
RAPPEL = timedelta(hours=3)         # une panne qui dure est rappelée
SURVEILLEES_DEGRADE = {"pinnacle", "winamax_direct", "betclic_direct", "unibet_direct", "pmu_direct", "olybet"}
BENINS = ("budget", "HTTP 403", "HTTP 429")   # lecture partielle prévue, refus avec reprise ou quota : pas une alerte


def noms(nom: str) -> str:
    return nom.replace("_direct", "").capitalize()


def problemes(etapes: dict) -> dict[str, tuple[str, str]]:
    """{étape: (niveau, détail)} pour les étapes de cotes en panne ou durablement dégradées."""
    out = {}
    for nom, v in etapes.items():
        if nom.startswith("resultats_") or v.get("desactive"):
            continue
        if not v.get("ok"):
            erreurs = v.get("erreurs") or [v.get("erreur") or "arrêtée"]
            out[nom] = ("panne", str(erreurs[0])[:80])
        elif v.get("degrade") and nom in SURVEILLEES_DEGRADE:
            erreurs = [str(e) for e in (v.get("erreurs") or [])]
            if erreurs and not all(any(b in e for b in BENINS) for e in erreurs):
                out[nom] = ("alerte", erreurs[0][:80])
    return out


def constats(etapes: dict) -> dict[str, tuple[str, str, str]]:
    """{étape: (niveau, genre, détail)} pour le journal d'incidents.

    Plus large que `problemes` : un refus 403/429 est relevé (genre « refus ») car il doit se voir sur la page
    Santé s'il dure. Le budget dépassé reste ignoré (limite de temps chronique, traitée à part)."""
    out = {nom: (niveau, "panne" if niveau == "panne" else "alerte", detail)
           for nom, (niveau, detail) in problemes(etapes).items()}
    for nom, v in etapes.items():
        if nom in out or nom.startswith("resultats_") or v.get("desactive") or not v.get("ok") or not v.get("degrade"):
            continue
        erreurs = [str(e) for e in (v.get("erreurs") or [])]
        refus = [e for e in erreurs if "HTTP 403" in e or "HTTP 429" in e]
        if nom in SURVEILLEES_DEGRADE and refus:
            codes = sorted({c for c in ("403", "429") if any(f"HTTP {c}" in e for e in refus)})
            out[nom] = ("alerte", "refus", f"Refus HTTP {', '.join(codes)} sur {len(refus)} requête{'s' if len(refus) > 1 else ''}")
    return out


def journal_incidents(etapes: dict, ancien: dict, maintenant: datetime) -> dict:
    """Met à jour le journal : {"en_cours": {étape: incident}, "termines": [incident, …]} sur 24 h.

    Un incident garde son début, son nombre de cycles et son dernier détail. Il se termine quand l'étape va
    mieux (ou, pour un refus, ne se répète plus). Un refus n'est « visible » qu'à partir de SEUIL_REFUS cycles."""
    ancien = ancien if isinstance(ancien, dict) else {}
    avant = ancien.get("en_cours") if isinstance(ancien.get("en_cours"), dict) else {}
    termines = [t for t in (ancien.get("termines") if isinstance(ancien.get("termines"), list) else [])
                if isinstance(t, dict)]
    maintenant_iso = maintenant.isoformat(timespec="seconds")
    courants, en_cours = constats(etapes), {}
    for nom, (niveau, genre, detail) in courants.items():
        vu = avant.get(nom) if isinstance(avant.get(nom), dict) else {}
        meme = vu and vu.get("genre") == genre
        en_cours[nom] = {"source": noms(nom), "niveau": niveau, "genre": genre, "detail": detail,
                         "debut": vu["debut"] if meme else maintenant_iso,
                         "cycles": vu.get("cycles", 0) + 1 if meme else 1, "dernier": maintenant_iso}
        if vu and not meme:
            termines.append({**vu, "fin": maintenant_iso})
    for nom, vu in avant.items():
        if nom not in courants and isinstance(vu, dict):
            termines.append({**vu, "fin": maintenant_iso})
    limite = maintenant - GARDE_INCIDENTS
    gardes = []
    for t in termines:
        try:
            fin = datetime.fromisoformat(str(t.get("fin")))
        except ValueError:
            continue
        visible = t.get("genre") != "refus" or t.get("cycles", 0) >= SEUIL_REFUS
        if fin >= limite and visible:
            gardes.append(t)
    return {"mis_a_jour": maintenant_iso, "en_cours": en_cours, "termines": gardes[-MAX_TERMINES:]}


def evaluer(etapes: dict, ancien: dict, maintenant: datetime) -> tuple[dict, list[tuple[str, str, str]]]:
    """(nouvel état, messages [(titre, corps, priorité)])."""
    courants, nouvel, messages = problemes(etapes), {}, []
    for nom, (niveau, detail) in courants.items():
        vu = ancien.get(nom, {})
        n = vu.get("cycles", 0) + 1
        envoye = vu.get("envoye")
        a_envoyer = n >= SEUIL_CYCLES and (
            not envoye or vu.get("niveau") != niveau or maintenant - datetime.fromisoformat(envoye) >= RAPPEL)
        if a_envoyer:
            envoye = maintenant.isoformat(timespec="seconds")
            mot = "en panne" if niveau == "panne" else "en alerte"
            messages.append((f"{noms(nom)} {mot}", f"{detail}\n{n} cycles de suite", "high" if niveau == "panne" else "default"))
        nouvel[nom] = {"niveau": niveau, "cycles": n, "envoye": envoye}
    for nom, vu in ancien.items():
        if nom not in courants and vu.get("envoye"):
            messages.append((f"{noms(nom)} rétablie", "Lecture normale", "default"))
    return nouvel, messages


def surveiller(donnees: Path, etapes: dict, maintenant: datetime | None = None) -> dict:
    try:
        maintenant = maintenant or datetime.now(timezone.utc)
        chemin = donnees / ETAT
        try:
            ancien = json.loads(chemin.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            ancien = {}
        nouvel, messages = evaluer(etapes, ancien if isinstance(ancien, dict) else {}, maintenant)
        try:
            ancien_i = json.loads((donnees / INCIDENTS).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            ancien_i = {}
        incidents = journal_incidents(etapes, ancien_i, maintenant)
        tmp_i = (donnees / INCIDENTS).with_suffix(".tmp")
        tmp_i.write_text(json.dumps(incidents, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp_i.replace(donnees / INCIDENTS)
        tmp = chemin.with_suffix(".tmp")
        tmp.write_text(json.dumps(nouvel, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(chemin)
        return {"problemes": len(nouvel), "messages": [titre for titre, _, _ in messages]}
    except Exception as e:  # noqa: BLE001
        return {"erreur": type(e).__name__}
