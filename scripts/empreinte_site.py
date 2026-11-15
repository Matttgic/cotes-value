"""Empreinte du site : prouve qu'un changement de code ne change ni le site, ni les états qu'il réécrit.

    python scripts/empreinte_site.py --donnees DOSSIER --sortie avant.json      # avant le changement
    python scripts/empreinte_site.py --donnees DOSSIER --comparer avant.json    # après : code 1 si différent

Le dossier donné n'est jamais modifié : la construction tourne sur une copie, à l'heure donnée (``--maintenant``,
passée à ``construire``), chronomètres à 0, avec ``PYTHONHASHSEED=0``, sans réseau, sans mémoire externe (``MEMOIRE_CHEMIN``) ni envoi Pushover ou webhook.
L'empreinte est le sha256 de chaque fichier produit dans le site et de chaque fichier de la copie que la
construction a créé ou modifié (``donnees/…``). Voir docs/architecture-cible.md, étape E0.1.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as _dt
import hashlib
import importlib
import json
import os
import pkgutil
import shutil
import socket
import sys
import tempfile
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
MAINTENANT_DEFAUT = "2026-11-15T12:00:00+00:00"
# Variables qui feraient lire un autre dossier ou envoyer quelque chose pendant la construction.
VARIABLES_RETIREES = ("MEMOIRE_CHEMIN", "REPRISE_CHEMIN", "HC_PING_URL")
PREFIXES_RETIRES = ("PUSHOVER_", "ALERTE_WEBHOOK")
PREFIXES_MODULES = ("cotes", "scripts", "site_web")


def _sha(chemin: Path) -> str:
    return hashlib.sha256(chemin.read_bytes()).hexdigest()


def _empreintes(dossier: Path) -> dict[str, str]:
    return {f.relative_to(dossier).as_posix(): _sha(f) for f in sorted(dossier.rglob("*"))
            if f.is_file() and ".git" not in f.relative_to(dossier).parts}


def importer_tout() -> list[str]:
    """Charge tous les modules de ``cotes`` avant de figer l'heure : un import tardif garderait la vraie heure."""
    if str(RACINE) not in sys.path:
        sys.path.insert(0, str(RACINE))
    importlib.import_module("scripts.site_web")
    ignores = []
    for m in pkgutil.walk_packages([str(RACINE / "cotes")], "cotes."):
        try:
            importlib.import_module(m.name)
        except ImportError as e:             # dépendance facultative absente : signalé, jamais bloquant
            ignores.append(f"{m.name} ({e})")
    return ignores


@contextlib.contextmanager
def chronometres_figes():
    """Remplace les chronomètres (et leurs alias) des modules du projet par 0 : les durées mesurées
    (``protection.py``, publiées sur la page Santé) ne varient plus d'une construction à l'autre. L'heure, elle, est
    passée à ``construire`` (E5.3). Tout est remis en place à la sortie."""
    substituts = {id(time.perf_counter): lambda: 0.0, id(time.monotonic): lambda: 0.0}
    remplaces = []
    for nom, module in list(sys.modules.items()):
        if module is None or not nom.startswith(PREFIXES_MODULES):
            continue
        for attribut, valeur in list(vars(module).items()):
            if id(valeur) in substituts:         # identité seulement : jamais de == sur un objet quelconque
                setattr(module, attribut, substituts[id(valeur)])
                remplaces.append((module, attribut, valeur))
    try:
        yield len(remplaces)
    finally:
        for module, attribut, valeur in remplaces:
            setattr(module, attribut, valeur)


def _reseau_coupe(*_a, **_k):
    raise OSError("réseau coupé pendant l'empreinte du site")


@contextlib.contextmanager
def sans_reseau_ni_envoi():
    retirees = {k: os.environ.pop(k) for k in list(os.environ)
                if k in VARIABLES_RETIREES or k.startswith(PREFIXES_RETIRES)}
    anciens = (socket.socket.connect, socket.socket.connect_ex, socket.create_connection)
    socket.socket.connect = socket.socket.connect_ex = _reseau_coupe
    socket.create_connection = _reseau_coupe
    try:
        yield
    finally:
        socket.socket.connect, socket.socket.connect_ex, socket.create_connection = anciens
        os.environ.update(retirees)


def empreinte(donnees: Path, maintenant: str = MAINTENANT_DEFAUT) -> dict:
    """Construit le site sur une copie de ``donnees`` et rend les empreintes ; ``donnees`` reste intact."""
    instant = _dt.datetime.fromisoformat(maintenant)
    if instant.tzinfo is None:
        raise ValueError("--maintenant doit porter un fuseau (ex. +00:00)")
    ignores = importer_tout()
    from cotes.site.construction import construire
    with tempfile.TemporaryDirectory(prefix="empreinte-site-") as tmp:
        copie, site = Path(tmp) / "donnees", Path(tmp) / "site"
        shutil.copytree(donnees, copie, ignore=shutil.ignore_patterns(".git"))
        avant = _empreintes(copie)
        with sans_reseau_ni_envoi(), chronometres_figes() as remplaces:
            construire(copie, site, instant)
        apres = _empreintes(copie)
        fichiers = {f"site/{k}": v for k, v in _empreintes(site).items()}
        fichiers |= {f"donnees/{k}": v for k, v in apres.items() if avant.get(k) != v}
        fichiers |= {f"donnees/{k}": "supprimé" for k in avant if k not in apres}
    return {"maintenant": maintenant, "hash_seed": os.environ.get("PYTHONHASHSEED"),
            "modules_figes": remplaces, "modules_ignores": ignores, "fichiers": dict(sorted(fichiers.items()))}


def differences(avant: dict, apres: dict) -> list[str]:
    a, b = avant.get("fichiers", {}), apres.get("fichiers", {})
    lignes = [f"différent : {k}" for k in sorted(a.keys() & b.keys()) if a[k] != b[k]]
    lignes += [f"disparu : {k}" for k in sorted(a.keys() - b.keys())]
    lignes += [f"nouveau : {k}" for k in sorted(b.keys() - a.keys())]
    if avant.get("maintenant") != apres.get("maintenant"):
        lignes.insert(0, f"heure différente : {avant.get('maintenant')} / {apres.get('maintenant')}")
    return lignes


def main(argv: list[str] | None = None) -> int:
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--donnees", required=True, type=Path)
    a.add_argument("--maintenant", default=None, help=f"heure figée, ISO avec fuseau (défaut {MAINTENANT_DEFAUT})")
    groupe = a.add_mutually_exclusive_group(required=True)
    groupe.add_argument("--sortie", type=Path, help="écrire l'empreinte dans ce fichier JSON")
    groupe.add_argument("--comparer", type=Path, help="comparer à une empreinte écrite avant ; code 1 si différent")
    args = a.parse_args(argv)
    if not args.donnees.is_dir():
        a.error(f"dossier introuvable : {args.donnees}")
    reference = json.loads(args.comparer.read_text(encoding="utf-8")) if args.comparer else None
    maintenant = args.maintenant or (reference or {}).get("maintenant") or MAINTENANT_DEFAUT
    resultat = empreinte(args.donnees, maintenant)
    for m in resultat["modules_ignores"]:
        print(f"module non chargé : {m}", file=sys.stderr)
    if args.sortie:
        args.sortie.write_text(json.dumps(resultat, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"{len(resultat['fichiers'])} fichiers, empreinte écrite dans {args.sortie}")
        return 0
    lignes = differences(reference, resultat)
    print("\n".join(lignes) if lignes else f"identique : {len(resultat['fichiers'])} fichiers")
    return 1 if lignes else 0


if __name__ == "__main__":
    if os.environ.get("PYTHONHASHSEED") != "0":       # ordre des ensembles de textes reproductible
        os.execve(sys.executable, [sys.executable, *sys.argv], {**os.environ, "PYTHONHASHSEED": "0"})
    raise SystemExit(main())
