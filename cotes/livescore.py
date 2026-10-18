"""Résultats LiveScore : source gratuite, sans clé, sans PulseScore (football, hockey, basket, tennis).

L'API publique de l'application renvoie tous les matchs d'un jour (UTC) avec le statut, le score final et
le score de chaque période : mi-temps, tiers-temps, quart-temps, prolongation, manches du tennis. Une
requête par sport et par jour, lue seulement pour les jours où un pari attend son résultat.

Le score est celui que le règlement attend : football = temps réglementaire (prolongation et tirs au but
exclus), hockey et basket = prolongation incluse (le vainqueur des tirs au but compte un but de plus, comme
chez les bookmakers), tennis = sets gagnés avec les jeux de chaque set. Un abandon est signalé, un forfait
est ignoré. Les noms viennent en français et en anglais : les deux servent au rapprochement avec le pari.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import requests

BASE = "https://prod-public-api.livescore.com/v1/api/app/date"
SPORTS = {"football": "soccer", "hockey": "hockey", "basket": "basketball", "tennis": "tennis"}
FINAUX = {"football": {"FT", "AET", "AP"}, "hockey": {"FT", "OT", "AP"},
          "basket": {"FT", "OT"}, "tennis": {"FT", "Ret."}}
ERREURS: list[str] = []


def _entier(valeur) -> int | None:
    try:
        n = int(str(valeur).strip())
    except (TypeError, ValueError):
        return None
    return n if n >= 0 else None


def _debut(valeur) -> datetime | None:
    try:
        return datetime.strptime(str(valeur), "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _equipes(e: dict, cle: str) -> list[str]:
    noms = []
    for champ in ("Nm", "NmEn"):
        lus = [str(x.get(champ)) for x in e.get(cle) or [] if isinstance(x, dict) and x.get(champ)]
        if lus and len(lus) == len(e.get(cle) or []):
            nom = " / ".join(lus)
            if nom not in noms:
                noms.append(nom)
    return noms


def _paires(e: dict, motifs: list[str]) -> list[tuple[int, int]]:
    """Paires (domicile, extérieur) des périodes présentes, dans l'ordre ; s'arrête à la première absente."""
    out = []
    for motif in motifs:
        a, b = _entier(e.get(f"Tr1{motif}")), _entier(e.get(f"Tr2{motif}"))
        if a is None or b is None:
            break
        out.append((a, b))
    return out


def match(sport: str, e: dict) -> list[dict]:
    """Un match terminé au format des validateurs (un enregistrement par variante de nom), ou []."""
    statut = e.get("Eps")
    if statut not in FINAUX.get(sport, ()):
        return []
    debut = _debut(e.get("Esd"))
    doms, exts = _equipes(e, "T1"), _equipes(e, "T2")
    final = (_entier(e.get("Tr1")), _entier(e.get("Tr2")))
    if not debut or not doms or not exts or None in final:
        return []
    periodes: list[tuple[int, int]] = []
    libelles: list[str] = []
    abandon = False
    if sport == "football":
        score = final
        if statut != "FT":                          # prolongation, tirs au but : le règlement veut les 90 minutes
            score = (_entier(e.get("Tr1OR")), _entier(e.get("Tr2OR")))
            if None in score:
                return []
        mt = (_entier(e.get("Trh1")), _entier(e.get("Trh2")))
        if None not in mt and mt[0] <= score[0] and mt[1] <= score[1]:
            periodes, libelles = [mt, (score[0] - mt[0], score[1] - mt[1])], ["1", "2"]
    elif sport in ("hockey", "basket"):
        score = final
        base = ["Pe1", "Pe2", "Pe3"] if sport == "hockey" else ["Q1", "Q2", "Q3", "Q4"]
        periodes = _paires(e, base)
        if len(periodes) == len(base):
            libelles = [str(i + 1) for i in range(len(base))]
            prol = (_entier(e.get("Tr1OT")), _entier(e.get("Tr2OT")))
            if None not in prol and prol != (0, 0):
                periodes.append(prol)
                libelles.append("OT")
        else:
            periodes = []                           # détail incomplet : seul le score final sert
    else:                                           # tennis : sets gagnés, jeux de chaque set
        score = final
        periodes = _paires(e, ["S1", "S2", "S3", "S4", "S5"])
        libelles = [str(i + 1) for i in range(len(periodes))]
        abandon = statut == "Ret."
    base_rec = {"source": "livescore", "sport": sport, "debut": debut, "score": tuple(score),
                "periodes": periodes, "libelles": libelles, "corners": None, "abandon": abandon}
    noms = [(doms[0], exts[0])]
    if (doms[-1], exts[-1]) != noms[0]:
        noms.append((doms[-1], exts[-1]))
    return [{**base_rec, "domicile": d, "exterieur": x} for d, x in noms]


def lire(sport: str, jours: list[str], http=requests) -> list[dict]:
    """Matchs terminés de ces jours (AAAA-MM-JJ, UTC)."""
    slug = SPORTS.get(sport)
    out = []
    for jour in sorted(set(jours)):
        try:
            r = http.get(f"{BASE}/{slug}/{jour.replace('-', '')}/0",
                         params={"countryCode": "FR", "locale": "fr"},
                         headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
            if not r.ok:
                raise ValueError(f"HTTP {r.status_code}")
            d = r.json()
            etapes = d.get("Stages") if isinstance(d, dict) else None
            if not isinstance(etapes, list):
                raise ValueError("Stages absent")
        except (requests.RequestException, ValueError, AttributeError) as ex:
            ERREURS.append(f"{sport} {jour} : {repr(ex)[:120]}")
            continue
        for etape in etapes:
            for e in (etape.get("Events") or []) if isinstance(etape, dict) else []:
                if isinstance(e, dict):
                    out += match(sport, e)
    return out


def jours_a_lire(depuis: datetime, maintenant: datetime) -> list[str]:
    """Jours UTC de `depuis` (moins un jour : un match de nuit) à aujourd'hui."""
    premier = (depuis - timedelta(days=1)).date()
    jours, jour = [], premier
    while jour <= maintenant.date():
        jours.append(jour.isoformat())
        jour += timedelta(days=1)
    return jours


HISTORIQUE_J = 14


def a_lire(paris: list[dict], maintenant: datetime) -> dict[str, datetime]:
    """Sport -> début du plus ancien pari ouvert (commencé depuis 2 h, au plus HISTORIQUE_J jours)."""
    out: dict[str, datetime] = {}
    for p in paris:
        if p.get("statut") not in ("en_cours", "a_regler") or p.get("sport") not in SPORTS:
            continue
        try:
            debut = datetime.fromisoformat(str(p.get("reporte_au") or p.get("debut")).replace("Z", "+00:00"))
        except ValueError:
            continue
        if debut.tzinfo is None:
            continue
        if timedelta(hours=2) < maintenant - debut < timedelta(days=HISTORIQUE_J):
            out[p["sport"]] = min(out.get(p["sport"], debut), debut)
    return out
