"""Stockage des paris sur la branche « donnees ».

`paris.json` ne garde que les paris actifs : en cours, à régler, ou réglés depuis moins de
ARCHIVE_APRES_JOURS jours. Les plus anciens partent dans des archives mensuelles compressées
(`archives/paris-AAAA-MM.json.gz`, mois du règlement), qui restent comptées dans le bilan. Sans cela,
`paris.json` grossirait d'environ 1 Mo par jour et dépasserait la limite de 100 Mo par fichier de GitHub.
"""
from __future__ import annotations

import gzip
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

ARCHIVE_APRES_JOURS = 30
DOSSIER = "archives"


def _heure(s) -> datetime | None:
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def lire_archives(donnees: Path) -> list[dict]:
    out = []
    for f in sorted((Path(donnees) / DOSSIER).glob("paris-*.json.gz")):
        with gzip.open(f, "rt", encoding="utf-8") as g:
            out += json.load(g)
    return out


def archiver(donnees: Path, paris: list[dict], maintenant: datetime) -> list[dict]:
    """Déplace les paris réglés depuis plus de ARCHIVE_APRES_JOURS jours dans les archives mensuelles ;
    renvoie les paris qui restent dans paris.json."""
    limite = maintenant - timedelta(days=ARCHIVE_APRES_JOURS)
    par_mois: dict[str, list[dict]] = {}
    restent = []
    for p in paris:
        regle = _heure(p.get("regle_le"))
        if p.get("statut") not in ("en_cours", "a_regler") and regle and regle < limite:
            par_mois.setdefault(f"{regle:%Y-%m}", []).append(p)
        else:
            restent.append(p)
    for mois, nouveaux in par_mois.items():
        f = Path(donnees) / DOSSIER / f"paris-{mois}.json.gz"
        f.parent.mkdir(parents=True, exist_ok=True)
        anciens = []
        if f.exists():
            with gzip.open(f, "rt", encoding="utf-8") as g:
                anciens = json.load(g)
        fusion = {p["id"]: p for p in anciens} | {p["id"]: p for p in nouveaux}
        tmp = f.with_name(f.name + ".tmp")           # écriture atomique : jamais d'archive à moitié écrite
        with gzip.open(tmp, "wt", encoding="utf-8") as g:
            json.dump(sorted(fusion.values(), key=lambda p: p.get("detecte") or ""), g, ensure_ascii=False)
        os.replace(tmp, f)
    return restent
