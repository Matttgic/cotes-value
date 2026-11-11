"""Archivage mensuel des données brutes (cotes/ et opportunites/) hors de git, en release GitHub.

Les fichiers quotidiens ``cotes/AAAA-MM-JJ.jsonl.gz`` et ``opportunites/AAAA-MM-JJ.jsonl.gz`` font l'essentiel de la
branche « donnees » (87 des 101 Mo le 11/11/2026) et ne servent pas aux bilans du site (paris.json et
archives/paris-*.json.gz). Un mois entier, terminé depuis plus de ``--garder-jours`` jours, est réuni dans un tar
(``donnees-brutes-AAAA-MM.tar``, fichiers déjà compressés) accompagné d'un manifeste (taille et SHA-256 de chaque
fichier). L'action « Archivage des données brutes » publie les deux en release ``donnees-brutes-AAAA-MM``, vérifie
le téléchargement contre le manifeste, puis seulement retire les fichiers de la branche. Rien n'est perdu : pour une
étude, télécharger la release et extraire le tar dans le dossier des données.

    python scripts/archiver_donnees_brutes.py donnees                  # essai à blanc : ce qui serait archivé
    python scripts/archiver_donnees_brutes.py donnees --sortie a/      # écrit les tar et manifestes dans a/
    python scripts/archiver_donnees_brutes.py --verifier a/x.tar a/x.json   # contrôle un tar téléchargé
"""
from __future__ import annotations

import argparse
import calendar
import hashlib
import io
import json
import re
import sys
import tarfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

DOSSIERS = ("cotes", "opportunites")
NOM = re.compile(r"^(\d{4})-(\d{2})-(\d{2})\.jsonl(\.gz)?$")
GARDER_JOURS = 30


def _sha(octets: bytes) -> str:
    return hashlib.sha256(octets).hexdigest()


def mois_archivables(donnees: Path, aujourd_hui: date, garder_jours: int = GARDER_JOURS) -> dict[str, list[str]]:
    """Mois (AAAA-MM) entièrement terminés avant aujourd'hui − garder_jours -> chemins relatifs, triés."""
    limite = aujourd_hui - timedelta(days=garder_jours)
    out: dict[str, list[str]] = {}
    for dossier in DOSSIERS:
        for f in sorted((donnees / dossier).glob("*")):
            m = NOM.match(f.name)
            if not m or not f.is_file():
                continue
            annee, mois = int(m[1]), int(m[2])
            fin_mois = date(annee, mois, calendar.monthrange(annee, mois)[1])
            if fin_mois < limite:
                out.setdefault(f"{annee:04d}-{mois:02d}", []).append(f"{dossier}/{f.name}")
    return {k: sorted(v) for k, v in sorted(out.items())}


def emballer(donnees: Path, mois: str, fichiers: list[str], sortie: Path) -> tuple[Path, Path]:
    """Écrit donnees-brutes-<mois>.tar et .json (manifeste) dans `sortie`. Ordre et dates fixes : reproductible."""
    sortie.mkdir(parents=True, exist_ok=True)
    tar_chemin = sortie / f"donnees-brutes-{mois}.tar"
    manifeste = {"mois": mois, "cree_le": datetime.now(timezone.utc).isoformat(timespec="seconds"), "fichiers": []}
    with tarfile.open(tar_chemin, "w", format=tarfile.PAX_FORMAT) as tar:
        for rel in fichiers:
            octets = (donnees / rel).read_bytes()
            info = tarfile.TarInfo(rel)
            info.size, info.mtime, info.mode = len(octets), 0, 0o644
            tar.addfile(info, io.BytesIO(octets))
            manifeste["fichiers"].append({"chemin": rel, "octets": len(octets), "sha256": _sha(octets)})
    manifeste["tar_sha256"] = _sha(tar_chemin.read_bytes())
    man_chemin = sortie / f"donnees-brutes-{mois}.json"
    man_chemin.write_text(json.dumps(manifeste, ensure_ascii=False, indent=1), encoding="utf-8")
    return tar_chemin, man_chemin


def verifier(tar_chemin: Path, man_chemin: Path) -> list[str]:
    """Erreurs (vide = conforme) : le tar contient exactement les fichiers du manifeste, octet pour octet."""
    man = json.loads(man_chemin.read_text(encoding="utf-8"))
    erreurs = []
    if _sha(tar_chemin.read_bytes()) != man.get("tar_sha256"):
        erreurs.append("empreinte du tar différente du manifeste")
    attendus = {f["chemin"]: f for f in man["fichiers"]}
    vus = set()
    with tarfile.open(tar_chemin) as tar:
        for membre in tar.getmembers():
            f = attendus.get(membre.name)
            if f is None:
                erreurs.append(f"fichier inattendu : {membre.name}")
                continue
            octets = tar.extractfile(membre).read()
            if len(octets) != f["octets"] or _sha(octets) != f["sha256"]:
                erreurs.append(f"contenu différent : {membre.name}")
            vus.add(membre.name)
    erreurs += [f"fichier manquant : {c}" for c in attendus if c not in vus]
    return erreurs


def main(argv: list[str] | None = None) -> int:
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("donnees", nargs="?", type=Path)
    a.add_argument("--garder-jours", type=int, default=GARDER_JOURS)
    a.add_argument("--sortie", type=Path, help="écrit les tar et manifestes ici (sans : essai à blanc)")
    a.add_argument("--verifier", nargs=2, type=Path, metavar=("TAR", "MANIFESTE"))
    a.add_argument("--aujourdhui", type=date.fromisoformat, default=None)
    x = a.parse_args(argv)
    if x.verifier:
        erreurs = verifier(*x.verifier)
        print("\n".join(erreurs) or "conforme")
        return 1 if erreurs else 0
    if not x.donnees:
        a.error("dossier des données manquant")
    jour = x.aujourdhui or datetime.now(timezone.utc).date()
    plan = mois_archivables(x.donnees, jour, x.garder_jours)
    if not plan:
        print(f"Rien à archiver : aucun mois terminé avant le {jour - timedelta(days=x.garder_jours)}.")
    for mois, fichiers in plan.items():
        poids = sum((x.donnees / f).stat().st_size for f in fichiers)
        print(f"{mois} : {len(fichiers)} fichiers, {poids / 1048576:.1f} Mo")
        if x.sortie:
            tar_chemin, man_chemin = emballer(x.donnees, mois, fichiers, x.sortie)
            erreurs = verifier(tar_chemin, man_chemin)
            if erreurs:
                print("\n".join(erreurs), file=sys.stderr)
                return 1
            print(f"  -> {tar_chemin.name} et {man_chemin.name} (vérifiés)")
    if x.sortie:
        (x.sortie / "mois.txt").write_text("\n".join(plan), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
