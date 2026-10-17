"""Stockage des paris sur la branche « donnees ».

`paris.json` ne garde que les paris actifs : en cours, à régler, ou réglés depuis moins de
ARCHIVE_APRES_JOURS jours. Les plus anciens partent dans des archives mensuelles compressées
(`archives/paris-AAAA-MM.json.gz`, mois du règlement), qui restent comptées dans le bilan. Sans cela,
`paris.json` grossirait d'environ 1 Mo par jour et dépasserait la limite de 100 Mo par fichier de GitHub.
"""
from __future__ import annotations

import gzip
import json
import logging
import os
import tempfile
import zlib
from datetime import datetime, timedelta
from pathlib import Path

ARCHIVE_APRES_JOURS = 30
DOSSIER = "archives"
logger = logging.getLogger(__name__)
STATUTS_REGLES = {"gagne", "perdu", "demi_gagne", "demi_perdu", "rembourse"}


class ArchiveInvalide(ValueError):
    """Une archive ne doit pas être remplacée ni omise d'un bilan officiel."""


def _heure(s) -> datetime | None:
    try:
        date = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return date if date.tzinfo is not None and date.utcoffset() is not None else None
    except (TypeError, ValueError):
        return None


def fusionner_paris(*lots: list[dict]) -> list[dict]:
    """Une copie identique par ID ; conflit explicite si deux contenus diffèrent.

    L'ordre et les objets du premier lot sont conservés. Les données ne sont
    jamais modifiées pour faire disparaître un conflit.
    """
    out = {}
    for lot in lots:
        if not isinstance(lot, list):
            raise ValueError("Les paris doivent former une liste d'objets")
        for p in lot:
            pid = p.get("id") if isinstance(p, dict) else None
            if not isinstance(pid, str) or not pid.strip():
                raise ValueError("Pari sans identifiant stable : fusion impossible")
            if pid in out:
                # Tuples de scores en mémoire et listes relues en JSON sont équivalents.
                if out[pid] != p and json.dumps(out[pid], sort_keys=True, allow_nan=False) != json.dumps(p, sort_keys=True, allow_nan=False):
                    raise ValueError(f"Identifiant de pari en conflit : {pid}")
            else:
                out[pid] = p
    return list(out.values())


def _lire_archive(f: Path) -> list[dict]:
    def refuser_constante(valeur):
        raise ValueError(f"Constante JSON non finie : {valeur}")
    try:
        with gzip.open(f, "rt", encoding="utf-8") as g:
            return fusionner_paris(json.load(g, parse_constant=refuser_constante))
    except (OSError, EOFError, UnicodeError, zlib.error, ValueError) as e:
        raise ArchiveInvalide(f"Archive illisible ou incohérente {f.name} : {e}") from e


def lire_archives(donnees: Path, *, erreurs: list[dict] | None = None) -> list[dict]:
    """Lecture stricte par défaut. `erreurs=[]` autorise un diagnostic partiel explicite.

    Le cycle, les notifications et le site n'utilisent jamais le mode partiel :
    omettre une archive fausserait les bilans et les plafonds prospectifs.
    """
    out = []
    for f in sorted((Path(donnees) / DOSSIER).glob("paris-*.json.gz")):
        try:
            out = fusionner_paris(out, _lire_archive(f))
        except (ArchiveInvalide, ValueError) as e:
            message = f"{f.name} : {e}"
            logger.error("Lecture des archives interrompue ou partielle : %s", message)
            if erreurs is None:
                raise ArchiveInvalide(message) from e
            erreurs.append({"fichier": f.name, "raison": str(e)})
    return out


def archiver(donnees: Path, paris: list[dict], maintenant: datetime) -> list[dict]:
    """Déplace les paris réglés depuis plus de ARCHIVE_APRES_JOURS jours dans les archives mensuelles ;
    renvoie les paris qui restent dans paris.json."""
    if maintenant.tzinfo is None or maintenant.utcoffset() is None:
        raise ValueError("Horloge d'archivage sans fuseau")
    paris = fusionner_paris(paris)
    limite = maintenant - timedelta(days=ARCHIVE_APRES_JOURS)
    par_mois: dict[str, list[dict]] = {}
    restent = []
    for p in paris:
        regle = _heure(p.get("regle_le"))
        if p.get("statut") in STATUTS_REGLES and regle and regle < limite:
            par_mois.setdefault(f"{regle:%Y-%m}", []).append(p)
        else:
            restent.append(p)
    if not par_mois:
        return restent
    # Valider tout l'existant et tous les nouveaux contenus avant une écriture.
    archives = lire_archives(donnees)
    fusionner_paris(archives, paris)
    ids_archives = {p["id"] for p in archives}
    prets = []
    try:
        for mois, candidats in sorted(par_mois.items()):
            nouveaux = [p for p in candidats if p["id"] not in ids_archives]
            if not nouveaux:                          # reprise après écriture déjà réussie
                continue
            f = Path(donnees) / DOSSIER / f"paris-{mois}.json.gz"
            f.parent.mkdir(parents=True, exist_ok=True)
            anciens = _lire_archive(f) if f.exists() else []
            fusion = fusionner_paris(anciens, nouveaux)
            texte = json.dumps(sorted(fusion, key=lambda p: p.get("detecte") or ""),
                               ensure_ascii=False, allow_nan=False)
            fd, nom = tempfile.mkstemp(prefix=f.name + ".", suffix=".tmp", dir=f.parent)
            os.close(fd)
            tmp = Path(nom)
            prets.append((tmp, f))
            with gzip.open(tmp, "wt", encoding="utf-8") as g:
                g.write(texte)
            # Vérifier le gzip/JSON complet, y compris son pied de page, avant remplacement.
            if _lire_archive(tmp) != json.loads(texte):
                raise ArchiveInvalide(f"Vérification du fichier temporaire échouée : {f.name}")
        for tmp, f in prets:
            os.replace(tmp, f)
    finally:
        for tmp, _ in prets:
            tmp.unlink(missing_ok=True)
    return restent
