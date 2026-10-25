"""Dernier bon état des références (Pinnacle, Polymarket), sport par sport.

Diagnostic du 23 au 25/10/2026 (349 cycles) : Pinnacle refuse (HTTP 403) un sport ou deux presque à chaque
cycle et tombe en entier 7 fois ; Polymarket est en panne 4 cycles sur 10. Sans référence, un sport n'a ni
comparaison ni pari, même quand les bookmakers français sont lus.

Un sport qu'une référence n'a pas rendu ce cycle reprend les lignes de son dernier passage réussi, marquées
``reprise``, avec leur heure de lecture d'origine (``collecte``) et leur âge réel : âge du cache Pinnacle plus
le temps écoulé depuis la lecture, ou temps écoulé depuis la lecture pour Polymarket. Une ligne n'est reprise
que si cet âge respecte les seuils de fraîcheur de Pinnacle (``pinnacle.est_perimee``) ; les fenêtres de
15 minutes de la comparaison et de la prise s'appliquent ensuite comme à toute lecture.

Pas de reprise :
- des cotes françaises : on ne parie que sur un prix lu au cycle même ;
- d'un sport que la référence a rendu ce cycle (un match qu'elle a retiré ne revient pas) ;
- d'un match commencé. Une ligne reprise n'est jamais remémorisée : son âge ne repart pas de zéro.

Le fichier (gzip, quelques Mo) vit hors de la branche « donnees », dans le cache GitHub Actions
(.github/workflows/collecte.yml). Absent ou illisible : aucune reprise, le cycle continue. Ne lève jamais.
"""
from __future__ import annotations

import gzip
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import pinnacle

REFERENCES = ("Pinnacle", "Polymarket")
TOLERANCE_HORLOGE_S = 60


def _instant(valeur) -> datetime | None:
    try:
        t = datetime.fromisoformat(str(valeur).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return t.astimezone(timezone.utc) if t.tzinfo else None


class Seuils:
    """Règle de ``pinnacle.est_perimee`` (seuil court pour un match dans ``PROCHE_H`` heures, long au-delà),
    seuils lus une seule fois : la reprise examine jusqu'à 200 000 lignes par cycle."""

    def __init__(self, maintenant: datetime):
        self.maintenant = maintenant
        self.court, self.long = pinnacle.age_max_secondes(), pinnacle.age_max_loin_secondes()
        self.proche = maintenant + timedelta(hours=pinnacle.PROCHE_H)

    def age(self, nom: str, ligne) -> int | None:
        """Âge réel d'une ligne encore utilisable comme référence ; None si périmée, commencée ou non prouvée
        (lecture non datée, âge du cache inconnu)."""
        if not isinstance(ligne, dict) or ligne.get("reprise"):
            return None
        debut, lue = _instant(ligne.get("debut")), _instant(ligne.get("collecte"))
        if debut is None or debut <= self.maintenant or lue is None:
            return None
        ecoule = (self.maintenant - lue).total_seconds()
        if ecoule < -TOLERANCE_HORLOGE_S:
            return None
        age = max(0, int(ecoule))
        if nom == "Pinnacle":
            cache = ligne.get("age_cache_s")
            if isinstance(cache, bool) or not isinstance(cache, int):
                return None
            age += cache
        return None if age > (self.court if debut <= self.proche else self.long) else age


def lire(chemin: Path | None) -> dict:
    if chemin is None:
        return {}
    try:
        doc = json.loads(gzip.decompress(chemin.read_bytes()))
    except (OSError, EOFError, ValueError):
        return {}
    return doc if isinstance(doc, dict) else {}


def _blocs(stock: dict, nom: str) -> dict:
    bloc = stock.get(nom)
    return bloc if isinstance(bloc, dict) else {}


def completer(nom: str, lignes: list[dict], stock: dict, seuils: Seuils) -> tuple[list[dict], dict[str, int]]:
    """(lignes reprises pour les sports absents de `lignes`, {sport: nombre de lignes reprises})."""
    lus = {l.get("sport") for l in lignes if isinstance(l, dict)}
    out, compte = [], {}
    for sport, bloc in _blocs(stock, nom).items():
        anciennes = bloc.get("lignes") if isinstance(bloc, dict) else None
        if sport in lus or not isinstance(anciennes, list):
            continue
        for l in anciennes:
            age = seuils.age(nom, l)
            if age is None:
                continue
            r = {**l, "reprise": True}
            if nom == "Pinnacle":
                r |= {"age_cache_s": age, "cote_perimee": False}
            out.append(r)
            compte[sport] = compte.get(sport, 0) + 1
    return out, compte


def memoriser(stock: dict, nom: str, lignes: list[dict], maintenant: datetime) -> None:
    """Remplace, sport par sport, le dernier passage réussi par les lignes fraîches du cycle. Le tri fin
    (âge, match commencé) se fait à la reprise : ici, seulement ce qui ne pourra jamais servir."""
    par_sport: dict[str, list[dict]] = {}
    for l in lignes:
        if isinstance(l, dict) and l.get("sport") and not l.get("reprise") and not l.get("cote_perimee"):
            par_sport.setdefault(l["sport"], []).append(l)
    lu = maintenant.isoformat(timespec="seconds")
    stock[nom] = {**_blocs(stock, nom), **{s: {"lu": lu, "lignes": ls} for s, ls in par_sport.items()}}


def ecrire(chemin: Path, stock: dict, seuils: Seuils) -> None:
    """Écriture atomique, sans les passages plus vieux que le seuil long : leurs lignes, lues pendant le cycle
    du passage (``lu`` = son début), ne peuvent plus servir. Au pire, une ligne est oubliée quelques secondes tôt."""
    limite = seuils.maintenant - timedelta(seconds=max(seuils.court, seuils.long))
    propre = {}
    for nom in REFERENCES:
        gardes = {s: b for s, b in _blocs(stock, nom).items()
                  if isinstance(b, dict) and (lu := _instant(b.get("lu"))) is not None and lu >= limite}
        if gardes:
            propre[nom] = gardes
    chemin.parent.mkdir(parents=True, exist_ok=True)
    tmp = chemin.with_name(chemin.name + ".tmp")
    tmp.write_bytes(gzip.compress(json.dumps(propre, ensure_ascii=False, separators=(",", ":"), default=str).encode(), 6))
    os.replace(tmp, chemin)


def appliquer(chemin: Path | None, references: dict[str, list[dict]],
              maintenant: datetime) -> tuple[dict[str, list[dict]], dict]:
    """({référence: lignes reprises}, résumé pour le journal). Mémorise les lignes fraîches du cycle."""
    vide = {nom: [] for nom in references}
    if chemin is None:
        return vide, {"actif": False}
    try:
        stock, seuils = lire(chemin), Seuils(maintenant)
        reprises, resume = dict(vide), {"actif": True}
        for nom, lignes in references.items():
            if nom not in REFERENCES:
                continue
            reprises[nom], compte = completer(nom, lignes, stock, seuils)
            if compte:
                resume[nom] = compte
            memoriser(stock, nom, lignes, maintenant)
        try:                       # une écriture ratée ne retire pas les reprises du cycle
            ecrire(chemin, stock, seuils)
        except Exception as e:  # noqa: BLE001
            resume["ecriture"] = type(e).__name__
        return reprises, resume
    except Exception as e:  # noqa: BLE001
        return vide, {"actif": True, "erreur": type(e).__name__}
