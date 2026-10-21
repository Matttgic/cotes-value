"""Flux public d'alertes : mêmes prises et mêmes prix que les badges du site.

Ce module ne change aucune sélection et ne place aucun pari. Les abonnements
et clés privées ne transitent jamais par ce flux ni par la branche donnees.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .convergence import STRATEGIES, cle_selection, paris_convergence
from .laboratoire import DEBUT_SUIVI, REGLES, heure, selectionner
from .liens import lien_match
from .strategie_qwen import QWEN
from .strategies_prudentes import VARIANTES

API = "https://tapotyftgyacbnjmeovn.supabase.co/functions/v1/cv-notifications"
AGE_PRIX_MAX_MINUTES = 5
# Matchs à plus de 6 h : PMU, Unibet et Betclic ne sont relus qu'à leur rythme (20, 27 et 34 min, scripts/cycle.py).
# Le prix de la dernière lecture reste le bon ; la limite de 5 min ferait taire l'alerte jusqu'à la lecture suivante.
LOINTAIN_H = 6
AGE_PRIX_LOINTAIN_MINUTES = {"PMU": 25, "Unibet": 32, "Betclic": 39}


def age_prix_max(o: dict, debut: datetime, recue: datetime) -> timedelta:
    loin = debut - recue > timedelta(hours=LOINTAIN_H)
    return timedelta(minutes=AGE_PRIX_LOINTAIN_MINUTES.get(o.get("bookmaker"), AGE_PRIX_MAX_MINUTES) if loin else AGE_PRIX_MAX_MINUTES)


def _noms_labo() -> dict[str, str]:
    """« labo:PIN-1.3-2-e2-h36 » -> « Pinnacle 2 » : même numérotation que la page Stratégies."""
    numeros, noms = {}, {}
    for r in REGLES:
        numeros[r.reference] = numeros.get(r.reference, 0) + 1
        noms["labo:" + r.id] = f"{r.reference} {numeros[r.reference]}"
    return noms


def _bornes(x: float) -> str:
    return f"{x:.2f}".replace(".", ",")


NOMS = {**{cle: nom for cle, _, nom, _, _ in STRATEGIES},
        **{v["cle"]: v["court"] for v in VARIANTES}, "convergence": "Convergence ≥ 2", **_noms_labo()}
DETAILS = {"labo:" + r.id: f"Cotes {_bornes(r.cote_min)}–{_bornes(r.cote_max)} · edge ≥ {100*r.edge_min:g} % · "
                           f"≤ {r.avance_max_h} h avant le match" for r in REGLES}


def selections_labo(paris: list[dict]) -> dict[str, set[int]]:
    """Prises de chaque règle du laboratoire depuis le début du suivi, comme sur la page Stratégies."""
    return {"labo:" + r.id: {id(p) for p in selectionner(paris, r, DEBUT_SUIVI)} for r in REGLES}


PIN2 = "labo:PIN-1.3-2-e2-h36"       # Pinnacle 2 : alerte webhook
COTE_MIN_PLANCHER = 1.30
COTE_MIN_MARGE = 1.02


def _nombre(x):
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) and x == x else None


def champs_valeur(o: dict) -> dict:
    """Edge, cote juste, cote Pinnacle brute, ligue, cote minimale (garde l'edge ≥ 2 % : juste × 1,02), équipes et lien."""
    juste = _nombre(o.get("cote_juste"))
    return {"ecart": _nombre(o.get("ecart")), "cote_juste": juste,
            "cote_pinnacle": _nombre(o.get("cote_reference")) if o.get("reference") == "Pinnacle" else None,
            "ligue": o.get("ligue"), "marche": o.get("marche"), "selection": o.get("pari", "")[:180],
            "sport": o.get("sport"), "domicile": o.get("domicile"), "exterieur": o.get("exterieur"),
            "match_id": o.get("match_id"), "lien": lien_match(o),
            "cote_min": round(max(COTE_MIN_PLANCHER, juste * COTE_MIN_MARGE), 3) if juste else None}


def empreinte_prix(p: dict) -> str:
    return hashlib.sha256(json.dumps((*cle_selection(p), p.get("cote")),
        ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def flux(actuelles: list[dict], paris: list[dict], retenus: dict[str, set[int]],
         maintenant: datetime | None = None) -> dict:
    maintenant = maintenant or datetime.now(timezone.utc)
    valides = {**retenus, "convergence": paris_convergence(paris, retenus)}
    observations = {}
    for p in paris:
        t0 = heure(p.get("detecte"))
        if not t0:
            continue
        # Pari décidé après sa première détection (référence Pinnacle arrivée plus tard) : la fenêtre de 15 min
        # part de la décision, pas de la première lecture du prix.
        decide = heure(p.get("decide_le"))
        if decide and decide > t0:
            t0 = decide
        for cle, ids in valides.items():
            if id(p) in ids:
                t, cote = t0, p.get("cote")
                if cle == QWEN["cle"]:
                    # Qwen décide à la validation (2ᵉ cycle) : date et prix de ce cycle, pas ceux de la première détection.
                    f = (p.get("selections_figees") or {}).get(cle) or {}
                    t, cote = heure(f.get("decide_le")) or t0, f.get("cote_confirmee", cote)
                dates = observations.setdefault((*cle_selection(p), cote), {})
                dates[cle] = min(dates.get(cle, t), t)
    alertes, depuis_pinnacle = {}, set()
    for o in actuelles:
        debut = heure(o.get("debut"))
        recue = heure(o.get("collecte_recue") or o.get("detecte"))
        if (o.get("suspect") or o.get("pariable") is False or not debut
                or debut <= maintenant + timedelta(minutes=1) or not recue
                or not timedelta(0) <= maintenant-recue <= age_prix_max(o, debut, recue)):
            continue
        key = (*cle_selection(o), o.get("cote"))
        dates = observations.get(key, {})
        if not dates or not any(maintenant-timedelta(minutes=15) <= t <= maintenant for t in dates.values()):
            continue
        empreinte = empreinte_prix(o)
        # Même prise vue par plusieurs références : les valeurs de Pinnacle l'emportent (stratégies Pinnacle).
        if empreinte in depuis_pinnacle and o.get("reference") != "Pinnacle":
            continue
        if o.get("reference") == "Pinnacle":
            depuis_pinnacle.add(empreinte)
        alertes[empreinte] = {
            **champs_valeur(o),
            "id": empreinte, "strategies": sorted(dates), "labels": [NOMS[c] for c in sorted(dates)],
            "validations": {c: t.isoformat() for c, t in dates.items()},
            "detecte": max(dates.values()).isoformat(), "debut": debut.isoformat(),
            "match": f'{o.get("domicile", "")} – {o.get("exterieur", "")}',
            # Le serveur actuel affiche le texte du pari tel quel : l'heure est
            # visible aussi sans redéployer le service Web Push.
            "pari": (o.get("pari", "")[:180]+"\nPrix relevé "+recue.astimezone(ZoneInfo("Europe/Paris")).strftime("%d/%m %H:%M:%S")),
            "collecte_le": recue.isoformat(), "age_prix_secondes": round((maintenant-recue).total_seconds()),
            "bookmaker": o.get("bookmaker", ""), "cote": o.get("cote"),
        }
    return {"generated_at": maintenant.isoformat(timespec="seconds"),
            "alertes": sorted(alertes.values(), key=lambda a: a["detecte"], reverse=True)[:100]}


def alertes_recheck(paris: list[dict], cle_strategie: str = PIN2, maintenant: datetime | None = None) -> list[dict]:
    """Paris ajoutés à une stratégie par ``redecider_ouverts`` : match non commencé, quel que soit leur âge.

    Construit depuis le pari enregistré (la ligne n'est plus forcément une opportunité du moment) ; le prix peut
    avoir bougé, d'où ``cote_min`` et ``recheck``. Un pari marqué avec liste d'ajouts n'est repris que si la
    stratégie y figure ; sans liste (re-décision du 19/10/2026), la sélection figée suffit.
    """
    maintenant = maintenant or datetime.now(timezone.utc)
    out = {}
    for p in paris:
        figees = p.get("selections_figees")
        debut, marque = heure(p.get("debut")), p.get("redecision_lecture_posterieure")
        if (not marque or not isinstance(figees, dict) or cle_strategie not in figees or p.get("suspect")
                or p.get("statut") != "en_cours" or not debut or debut <= maintenant + timedelta(minutes=1)
                or not (_nombre(p.get("cote")) or 0) > 1):
            continue
        ajoutees = p.get("redecision_ajoutees")
        if isinstance(ajoutees, list) and cle_strategie not in ajoutees:
            continue
        empreinte = empreinte_prix(p)
        out[empreinte] = {
            **champs_valeur(p), "id": empreinte, "strategies": [cle_strategie], "labels": [NOMS[cle_strategie]],
            "validations": {cle_strategie: str(marque)}, "detecte": p.get("detecte"), "debut": debut.isoformat(),
            "match": f'{p.get("domicile", "")} – {p.get("exterieur", "")}',
            "collecte_le": p.get("prix_revu_le") or p.get("detecte"), "bookmaker": p.get("bookmaker", ""),
            "cote": p.get("cote"), "recheck": True}
    return sorted(out.values(), key=lambda a: a["debut"])
