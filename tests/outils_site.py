"""Données complètes d'un site construit : celles de la page (const D) plus les blocs différés (donnees.json)."""
import json
import re
from pathlib import Path


def donnees_site(html: str, site: Path | None = None) -> dict:
    """``D`` tel que la page l'a une fois donnees.json chargé (web/modele.html › chargerDifferes)."""
    from cotes.site import construction
    d = json.loads(re.search(r"const D = (\{.*?\});\n", html, re.S).group(1).replace("<\\/", "</"))
    dossier = site or construction.DERNIER_SITE
    if dossier is not None and (Path(dossier) / "donnees.json").exists():
        d.update(json.loads((Path(dossier) / "donnees.json").read_text(encoding="utf-8")))
    return d
