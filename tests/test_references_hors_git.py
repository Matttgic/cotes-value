"""references/ hors de la branche « donnees » (cotes/historiques.py, cotes/depot/references.py)."""
import gzip
import io
import json
import re
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError

import pytest

from cotes import historiques
from cotes.depot import references as R

NOW = datetime(2026, 11, 16, 0, 10, tzinfo=timezone.utc)
HIER = "2026-11-15"


def _gz(texte: str) -> bytes:
    return gzip.compress(texte.encode())


def _lignes(contenu: bytes) -> list[str]:
    return gzip.decompress(contenu).decode().splitlines()       # lit tous les membres gzip


class FauxGithub:
    """Releases en mémoire : mêmes routes que l'API (lecture par tag, création, envoi, suppression, lecture)."""

    def __init__(self, echec_envoi=False):
        self.releases, self.n, self.appels, self.echec_envoi = {}, 0, [], echec_envoi

    def __call__(self, req, timeout=None):
        url, methode = req.full_url, req.get_method()
        self.appels.append((methode, url))
        assert req.get_header("Authorization") == "Bearer jeton"
        if m := re.search(r"/releases/tags/([^/?]+)$", url):
            rel = self.releases.get(m[1])
            if rel is None:
                raise HTTPError(url, 404, "Not Found", {}, None)
            return self._rep({**rel, "assets": [{k: v for k, v in a.items() if k != "contenu"} for a in rel["assets"]]})
        if url.endswith("/releases") and methode == "POST":
            corps = json.loads(req.data)
            assert corps["target_commitish"] == "donnees"
            self.n += 1
            self.releases[corps["tag_name"]] = {"id": self.n, "tag_name": corps["tag_name"], "assets": []}
            return self._rep(self.releases[corps["tag_name"]])
        if m := re.search(r"/releases/(\d+)/assets\?name=(.+)$", url):
            if self.echec_envoi:
                raise HTTPError(url, 502, "Bad Gateway", {}, None)
            rel = next(r for r in self.releases.values() if r["id"] == int(m[1]))
            self.n += 1
            asset = {"id": self.n, "name": m[2], "size": len(req.data), "state": "uploaded", "contenu": req.data}
            rel["assets"].append(asset)
            return self._rep({k: v for k, v in asset.items() if k != "contenu"})
        if m := re.search(r"/releases/assets/(\d+)$", url):
            for rel in self.releases.values():
                for a in list(rel["assets"]):
                    if a["id"] == int(m[1]):
                        if methode == "DELETE":
                            rel["assets"].remove(a)
                            return self._rep(None, 204)
                        return self._brut(a["contenu"])
        if url.endswith("/releases?per_page=100"):
            return self._rep([{"tag_name": t} for t in self.releases])
        raise AssertionError(url)

    def _rep(self, doc, statut=200):
        return self._brut(json.dumps(doc).encode() if doc is not None else b"", statut)

    @staticmethod
    def _brut(octets, statut=200):
        r = io.BytesIO(octets)
        r.status = statut
        return r

    def asset(self, jour):
        rel = self.releases[f"references-{jour[:7]}"]
        return next(a for a in rel["assets"] if a["name"] == f"references-{jour}.jsonl.gz")


@pytest.fixture
def memoire_chemin(tmp_path, monkeypatch):
    m = tmp_path / "memoire"
    monkeypatch.setenv("MEMOIRE_CHEMIN", str(m))
    return m


def test_le_fichier_du_jour_va_dans_la_memoire(tmp_path, memoire_chemin):
    donnees = tmp_path / "donnees"
    (donnees / "references").mkdir(parents=True)
    (donnees / "references" / f"{HIER}.jsonl.gz").write_bytes(_gz('{"debut": 1}\n'))   # début du jour, branche
    jour = historiques.chemin_du_jour(donnees, "references", NOW - timedelta(hours=1))
    assert jour == memoire_chemin / "references" / f"{HIER}.jsonl.gz"
    assert not (donnees / "references" / f"{HIER}.jsonl.gz").exists()                 # retiré de la branche
    historiques._ecrire(donnees, "references", [{"t": 2}], NOW - timedelta(hours=1))
    assert _lignes(jour.read_bytes()) == ['{"debut": 1}', '{"t":2}']                  # rien de perdu
    # les autres dossiers restent dans la branche
    assert historiques.chemin_du_jour(donnees, "cotes", NOW) == donnees / "cotes" / "2026-11-16.jsonl.gz"


def test_sans_memoire_externe_rien_ne_change(tmp_path, monkeypatch):
    monkeypatch.delenv("MEMOIRE_CHEMIN", raising=False)
    assert historiques.chemin_du_jour(tmp_path, "references", NOW) == tmp_path / "references" / "2026-11-16.jsonl.gz"


def _jour(memoire_chemin, jour, texte):
    f = memoire_chemin / "references" / f"{jour}.jsonl.gz"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(_gz(texte))
    return f


def test_publie_les_jours_termines_et_garde_le_jour_en_cours(tmp_path, memoire_chemin):
    gh = FauxGithub()
    hier, avant = _jour(memoire_chemin, HIER, "a\n"), _jour(memoire_chemin, "2026-10-31", "b\n")
    aujourd_hui = _jour(memoire_chemin, "2026-11-16", "c\n")
    bilan = R.publier(tmp_path, NOW, "test/repo", "jeton", gh)
    assert bilan == {"publies": {"2026-10-31": "publié", HIER: "publié"}, "erreurs": []}
    assert set(gh.releases) == {"references-2026-10", "references-2026-11"}
    assert _lignes(gh.asset(HIER)["contenu"]) == ["a"] and _lignes(gh.asset("2026-10-31")["contenu"]) == ["b"]
    assert not hier.exists() and not avant.exists() and aujourd_hui.exists()
    assert R.publier(tmp_path, NOW, "test/repo", "jeton", gh) == {"publies": {}, "erreurs": []}


def test_envoi_en_echec_le_jour_reste_en_memoire(tmp_path, memoire_chemin):
    hier = _jour(memoire_chemin, HIER, "a\n")
    bilan = R.publier(tmp_path, NOW, "test/repo", "jeton", FauxGithub(echec_envoi=True))
    assert bilan["publies"] == {} and len(bilan["erreurs"]) == 1 and hier.exists()


def test_sans_jeton_rien_n_est_retire(tmp_path, memoire_chemin, monkeypatch):
    for v in ("GH_TOKEN", "GITHUB_TOKEN"):
        monkeypatch.delenv(v, raising=False)
    hier = _jour(memoire_chemin, HIER, "a\n")
    assert "aucun jeton" in R.publier(tmp_path, NOW)["erreurs"][0] and hier.exists()


def test_deja_publie_a_un_passage_precedent(tmp_path, memoire_chemin):
    gh = FauxGithub()
    _jour(memoire_chemin, HIER, "a\n")
    R.publier(tmp_path, NOW, "test/repo", "jeton", gh)
    hier = _jour(memoire_chemin, HIER, "a\n")              # le passage a publié mais n'a pas pu effacer
    assert R.publier(tmp_path, NOW, "test/repo", "jeton", gh)["publies"] == {HIER: "déjà publié"}
    assert not hier.exists() and len(gh.releases["references-2026-11"]["assets"]) == 1


def test_meme_jour_ecrit_par_github_et_par_le_serveur(tmp_path, memoire_chemin):
    """Relais GitHub / serveur : la seconde publication s'ajoute à la suite, sans remplacer la première."""
    gh = FauxGithub()
    _jour(memoire_chemin, HIER, "github\n")
    R.publier(tmp_path, NOW, "test/repo", "jeton", gh)
    _jour(memoire_chemin, HIER, "serveur\n")
    assert R.publier(tmp_path, NOW, "test/repo", "jeton", gh)["publies"] == {HIER: "ajouté à la suite"}
    assert _lignes(gh.asset(HIER)["contenu"]) == ["github", "serveur"]
    _jour(memoire_chemin, HIER, "serveur\n")                 # même passage rejoué : pas de doublon
    assert R.publier(tmp_path, NOW, "test/repo", "jeton", gh)["publies"] == {HIER: "déjà publié"}
    assert _lignes(gh.asset(HIER)["contenu"]) == ["github", "serveur"]


def test_telecharger_pour_une_etude(tmp_path, memoire_chemin):
    gh = FauxGithub()
    _jour(memoire_chemin, HIER, "a\n")
    _jour(memoire_chemin, "2026-10-31", "b\n")
    R.publier(tmp_path, NOW, "test/repo", "jeton", gh)
    sortie = tmp_path / "etude" / "references"
    assert R.telecharger(sortie, None, "test/repo", "jeton", gh) == ["2026-10-31.jsonl.gz", f"{HIER}.jsonl.gz"]
    assert _lignes((sortie / f"{HIER}.jsonl.gz").read_bytes()) == ["a"]
    assert R.telecharger(tmp_path / "x", "2026-10", "test/repo", "jeton", gh) == ["2026-10-31.jsonl.gz"]


def test_le_jeton_ne_suit_pas_la_redirection_vers_le_stockage():
    import urllib.request
    h = R._SansJetonAilleurs()
    req = urllib.request.Request("https://api.github.com/repos/x/y/releases/assets/1",
                                 headers={"Authorization": "Bearer jeton"})
    vers_stockage = h.redirect_request(req, None, 302, "Found", {}, "https://objects.githubusercontent.com/f")
    assert vers_stockage.get_header("Authorization") is None
    meme_hote = h.redirect_request(req, None, 302, "Found", {}, "https://api.github.com/autre")
    assert meme_hote.get_header("Authorization") == "Bearer jeton"


def test_workflow_publie_apres_un_enregistrement_reussi():
    import yaml
    from pathlib import Path
    racine = Path(__file__).resolve().parent.parent
    steps = yaml.safe_load((racine / ".github/workflows/collecte.yml").read_text())["jobs"]["cycle"]["steps"]
    noms = [s.get("name", "") for s in steps]
    i = noms.index("Publier les références des jours terminés")
    assert noms.index("Enregistrer les données") < i < noms.index("Sauver la mémoire de travail")
    etape = steps[i]
    assert "steps.enregistrer.outcome == 'success'" in etape["if"] and etape["continue-on-error"] is True
    assert etape["run"] == "python -m cotes references --publier --donnees donnees"
    assert etape["env"]["MEMOIRE_CHEMIN"] == "memoire"
