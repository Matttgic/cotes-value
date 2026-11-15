"""Historique des références hors de git (depuis le 15/11/2026) : un jour UTC terminé = un fichier en release GitHub.

``references/AAAA-MM-JJ.jsonl.gz`` (cotes/historiques.py) faisait l'essentiel de la croissance de l'historique de
la branche « donnees » (≈ 30 Mo par jour, réécrit à chaque cycle ; 408 Mio d'historique le 15/11/2026). Le fichier du
jour vit désormais dans la mémoire de travail (cache Actions ``memoire/``, disque du serveur) ; après chaque
enregistrement réussi, chaque jour terminé est publié dans la release ``references-AAAA-MM`` (fichier
``references-AAAA-MM-JJ.jsonl.gz``), contrôlé (taille) puis seulement retiré de la mémoire.

Le même jour écrit par GitHub et par le serveur en direct (relais) : la seconde publication ajoute ses membres gzip à
la suite de la première (un .jsonl.gz peut contenir plusieurs membres), jamais à sa place.

    python -m cotes references --publier --donnees donnees            # GitHub Actions, serveur (GH_TOKEN)
    python -m cotes references --telecharger donnees/references       # pour une étude : tous les jours publiés
    python -m cotes references --telecharger donnees/references --mois 2026-11
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote, urlparse

from cotes import memoire

API = "https://api.github.com"
UPLOADS = "https://uploads.github.com"
DEPOT_DEFAUT = "Matttgic/cotes-value"
BRANCHE = "donnees"                     # les tags des releases pointent sur la branche des données
DOSSIER = "references"
NOM = re.compile(r"^(\d{4})-(\d{2})-(\d{2})\.jsonl\.gz$")
DELAI_S = 120


class _SansJetonAilleurs(urllib.request.HTTPRedirectHandler):
    """Téléchargement d'un fichier : GitHub redirige vers un stockage qui refuse l'en-tête Authorization."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        nouvelle = super().redirect_request(req, fp, code, msg, headers, newurl)
        if nouvelle is not None and urlparse(newurl).hostname != urlparse(req.full_url).hostname:
            nouvelle.remove_header("Authorization")
        return nouvelle


_OUVREUR = urllib.request.build_opener(_SansJetonAilleurs())


def ouvrir_url(req, timeout=DELAI_S):
    return _OUVREUR.open(req, timeout=timeout)


class Github:
    """Appels de l'API des releases ; ``ouvrir`` est remplacé dans les tests."""

    def __init__(self, depot: str, jeton: str | None, ouvrir=ouvrir_url):
        self.depot, self.jeton, self.ouvrir = depot, jeton, ouvrir

    def _requete(self, methode: str, url: str, donnees: bytes | None = None, type_contenu: str | None = None,
                 accepter: str = "application/vnd.github+json") -> tuple[int, bytes]:
        entetes = {"Accept": accepter, "User-Agent": "cotes-value", "X-GitHub-Api-Version": "2022-11-28"}
        if self.jeton:
            entetes["Authorization"] = f"Bearer {self.jeton}"
        if type_contenu:
            entetes["Content-Type"] = type_contenu
        req = urllib.request.Request(url, data=donnees, method=methode, headers=entetes)
        try:
            with self.ouvrir(req, timeout=DELAI_S) as r:
                return r.status, r.read()
        except HTTPError as e:
            if e.code == 404:
                return 404, b""
            raise

    def _json(self, methode, chemin, corps=None):
        statut, brut = self._requete(methode, f"{API}/repos/{self.depot}{chemin}",
                                     json.dumps(corps).encode() if corps is not None else None,
                                     "application/json" if corps is not None else None)
        return statut, (json.loads(brut) if brut else None)

    def release(self, tag: str) -> dict | None:
        statut, doc = self._json("GET", f"/releases/tags/{quote(tag)}")
        return None if statut == 404 else doc

    def creer_release(self, tag: str, mois: str) -> dict:
        _, doc = self._json("POST", "/releases", {
            "tag_name": tag, "target_commitish": BRANCHE, "name": f"Références {mois}",
            "body": f"Historique des cotes justes des références, un fichier par jour UTC ({mois}). Format : "
                    "cotes/historiques.py. Téléchargement : python -m cotes references --telecharger DOSSIER.",
            "draft": False, "prerelease": False})
        return doc

    def envoyer(self, release: dict, nom: str, contenu: bytes) -> dict:
        _, brut = self._requete("POST", f"{UPLOADS}/repos/{self.depot}/releases/{release['id']}/assets?name={quote(nom)}",
                                contenu, "application/gzip")
        return json.loads(brut)

    def supprimer(self, asset: dict) -> None:
        self._requete("DELETE", f"{API}/repos/{self.depot}/releases/assets/{asset['id']}")

    def lire(self, asset: dict) -> bytes:
        _, brut = self._requete("GET", f"{API}/repos/{self.depot}/releases/assets/{asset['id']}",
                                accepter="application/octet-stream")
        return brut


def _tag(jour: str) -> str:
    return f"references-{jour[:7]}"


def _nom(jour: str) -> str:
    return f"references-{jour}.jsonl.gz"


def jours_termines(dossier: Path, maintenant: datetime) -> list[Path]:
    """Fichiers des jours UTC antérieurs à aujourd'hui, du plus ancien au plus récent."""
    aujourd_hui = maintenant.astimezone(timezone.utc).strftime("%Y-%m-%d")
    return sorted(f for f in dossier.glob("*.jsonl.gz") if NOM.match(f.name) and f.name[:10] < aujourd_hui)


def _publier_jour(gh: Github, fichier: Path) -> str:
    jour = fichier.name[:10]
    local = fichier.read_bytes()
    release = gh.release(_tag(jour)) or gh.creer_release(_tag(jour), jour[:7])
    existant = next((a for a in release.get("assets") or [] if a.get("name") == _nom(jour)), None)
    if existant is not None:
        distant = gh.lire(existant)
        if distant.endswith(local) or distant.startswith(local):
            return "déjà publié"                       # ajout fait à un passage précédent
        contenu = distant + local                      # autre écrivain (GitHub / serveur) : membres gzip à la suite
    else:
        contenu = local
    if existant is not None:
        gh.supprimer(existant)
    envoye = gh.envoyer(release, _nom(jour), contenu)
    if envoye.get("size") != len(contenu) or envoye.get("state", "uploaded") != "uploaded":
        raise RuntimeError(f"{_nom(jour)} : taille publiée {envoye.get('size')} au lieu de {len(contenu)}")
    return "ajouté à la suite" if existant is not None else "publié"


def publier(donnees: Path, maintenant: datetime | None = None, depot: str | None = None, jeton: str | None = None,
            ouvrir=ouvrir_url) -> dict:
    """Publie chaque jour terminé de la mémoire, puis le retire de la mémoire. Ne lève jamais : une erreur garde le
    fichier pour le passage suivant et figure dans le bilan."""
    maintenant = maintenant or datetime.now(timezone.utc)
    dossier = memoire.dossier(donnees) / DOSSIER
    bilan: dict = {"publies": {}, "erreurs": []}
    fichiers = jours_termines(dossier, maintenant) if dossier.is_dir() else []
    if not fichiers:
        return bilan
    jeton = jeton if jeton is not None else (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or "")
    if not jeton:
        bilan["erreurs"].append("aucun jeton GitHub (GH_TOKEN) : jours gardés en mémoire")
        return bilan
    gh = Github(depot or os.environ.get("DEPOT") or DEPOT_DEFAUT, jeton, ouvrir)
    for f in fichiers:
        try:
            bilan["publies"][f.name[:10]] = _publier_jour(gh, f)
            f.unlink()
        except Exception as e:  # noqa: BLE001 - jamais bloquant ; le jour reste en mémoire
            bilan["erreurs"].append(f"{f.name[:10]} : {type(e).__name__} {str(e)[:120]}")
    return bilan


def telecharger(sortie: Path, mois: str | None = None, depot: str | None = None, jeton: str | None = None,
                ouvrir=ouvrir_url) -> list[str]:
    """Télécharge les jours publiés (tous, ou ceux de ``mois`` AAAA-MM) dans ``sortie``/AAAA-MM-JJ.jsonl.gz."""
    jeton = jeton if jeton is not None else (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or "")
    gh = Github(depot or os.environ.get("DEPOT") or DEPOT_DEFAUT, jeton or None, ouvrir)
    tags = [f"references-{mois}"] if mois else None
    if tags is None:
        _, releases = gh._json("GET", "/releases?per_page=100")
        tags = sorted(r["tag_name"] for r in releases or [] if str(r.get("tag_name", "")).startswith("references-"))
    sortie.mkdir(parents=True, exist_ok=True)
    ecrits = []
    for tag in tags:
        release = gh.release(tag)
        for asset in (release or {}).get("assets") or []:
            m = re.match(r"^references-(\d{4}-\d{2}-\d{2}\.jsonl\.gz)$", asset.get("name", ""))
            if m:
                (sortie / m[1]).write_bytes(gh.lire(asset))
                ecrits.append(m[1])
    return sorted(ecrits)


def main(argv: list[str] | None = None) -> int:
    a = argparse.ArgumentParser(prog="references", description=__doc__.split("\n")[0])
    a.add_argument("--publier", action="store_true", help="publier les jours terminés de la mémoire de travail")
    a.add_argument("--donnees", type=Path, default=Path("donnees"))
    a.add_argument("--telecharger", type=Path, metavar="DOSSIER", help="télécharger les jours publiés ici")
    a.add_argument("--mois", help="AAAA-MM (avec --telecharger)")
    args = a.parse_args(argv)
    if args.publier:
        bilan = publier(args.donnees)
        print(json.dumps(bilan, ensure_ascii=False))
        for erreur in bilan["erreurs"]:
            print(f"::warning title=Références::{erreur}")
        return 0
    if args.telecharger:
        print("\n".join(telecharger(args.telecharger, args.mois)))
        return 0
    a.print_help(sys.stderr)
    return 2
