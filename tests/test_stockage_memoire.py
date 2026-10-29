"""Stockage du 30/10/2026 : mémoire de travail hors de « donnees », historique des cotes en ajout seul,
controle.json compact publié au plus une fois par heure."""
import gzip
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cotes import historique_cotes, memoire
from scripts import cycle

NOW = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)


def ligne(mid="unibet-fr|1", cote=2.0, issue="DOM", lu=NOW, **k):
    return {"source": "Unibet", "bookmaker": "unibet-fr", "sport": "football", "ligue": "L1", "match_id": mid,
            "domicile": "Lens", "exterieur": "Lille", "debut": (NOW + timedelta(hours=3)).isoformat(),
            "collecte": lu.isoformat(), "joueur": None, "marche": "RESULTAT_1N2", "periode": "MATCH",
            "ligne": None, "issue": issue, "cote": cote, **k}


def _cycle_unibet(monkeypatch, lignes_unibet):
    """Cycle sans réseau : seul Unibet rend des lignes (et sa mémoire)."""
    from tests.test_collecte_parallele import _sans_reseau
    _sans_reseau(monkeypatch)
    monkeypatch.setattr(cycle.pinnacle, "collecter", lambda: [])
    monkeypatch.setattr(cycle.polymarket, "collecter", lambda *a: [])
    monkeypatch.setattr(cycle.pinnacle_secours, "disponible", lambda: False)
    monkeypatch.setattr(cycle, "harmoniser_pinnacle", lambda x: x)
    monkeypatch.setattr(cycle.unibet_direct, "collecter", lambda *a, **k: (
        list(lignes_unibet), {"ok": True, "erreurs": [], "requetes": 1, "matchs": 1,
                              "reserve": {"curseur": 1, "lignes": list(lignes_unibet)}}))


def _jour(donnees: Path) -> Path:
    return donnees / "cotes" / f"{NOW:%Y-%m-%d}.jsonl.gz"


def _lignes_historique(donnees: Path) -> list[dict]:
    with gzip.open(_jour(donnees), "rt", encoding="utf-8") as f:
        return [json.loads(x) for x in f]


# --- mémoire ------------------------------------------------------------------------------------------------

def test_memoire_absente_ou_illisible_rend_la_valeur_par_defaut(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMOIRE_CHEMIN", str(tmp_path / "memoire"))       # dossier inexistant : cache absent
    assert memoire.lire(tmp_path, "horizon_direct", {}) == {}
    (tmp_path / "memoire").mkdir()
    (tmp_path / "memoire" / "horizon_direct.json.gz").write_bytes(b"pas du gzip")
    assert memoire.lire(tmp_path, "horizon_direct", {"froid": 1}) == {"froid": 1}


def test_memoire_reprend_l_ancien_fichier_puis_le_retire_de_donnees(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMOIRE_CHEMIN", str(tmp_path / "memoire"))
    donnees = tmp_path / "donnees"
    donnees.mkdir()
    (donnees / "smarkets_cache.json").write_text(json.dumps({"lignes": [1]}))
    assert memoire.lire(donnees, "smarkets_cache") == {"lignes": [1]}          # premier cycle après la migration
    gz = memoire.ecrire(donnees, "smarkets_cache", {"lignes": [2]})
    assert gz == tmp_path / "memoire" / "smarkets_cache.json.gz"
    assert not (donnees / "smarkets_cache.json").exists()                     # sorti de la branche « donnees »
    assert json.loads(gzip.decompress(gz.read_bytes())) == {"lignes": [2]}
    assert b"\n" not in gzip.decompress(gz.read_bytes())                      # JSON compact


def test_demarrage_a_froid_sans_cache_ne_plante_pas(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMOIRE_CHEMIN", str(tmp_path / "memoire"))          # aucun cache restauré
    donnees = tmp_path / "donnees"
    _cycle_unibet(monkeypatch, [ligne(), ligne(issue="EXT", cote=3.5)])
    journal = {"etapes": {}}
    _, _, lignes = cycle.collecter_prematch("complet", NOW, journal, donnees)
    assert len(lignes) == 2
    assert memoire.lire(donnees, "horizon_direct")["unibet"]["curseur"] == 1
    assert not (donnees / "horizon_direct.json").exists()
    # à froid, l'état de départ est écrit une fois : une description du match et ses deux cotes
    hist = _lignes_historique(donnees)
    assert [x.get("c") for x in hist] == [None, 2.0, 3.5] and hist[0]["dom"] == "Lens"
    assert journal["historique_cotes"] == {"lignes": 3}


def test_caches_secours_et_smarkets_absents_ou_illisibles(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMOIRE_CHEMIN", str(tmp_path / "memoire"))
    from cotes import pinnacle_secours as S
    assert S._lire_cache(memoire.lire(tmp_path, "pinnacle_secours_cache", {}), {29}, NOW) == []
    (tmp_path / "memoire").mkdir()
    (tmp_path / "memoire" / "smarkets_cache.json.gz").write_bytes(b"\x1f\x8b abime")
    assert cycle._cache_sm(tmp_path) == {}


# --- historique des cotes -----------------------------------------------------------------------------------

def test_ajout_seul_des_cotes_changees(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMOIRE_CHEMIN", str(tmp_path / "memoire"))
    donnees = tmp_path / "donnees"
    _cycle_unibet(monkeypatch, [ligne(), ligne(issue="EXT", cote=3.5)])
    cycle.collecter_prematch("complet", NOW, {"etapes": {}}, donnees)
    avant = _jour(donnees).read_bytes()
    plus_tard = NOW + timedelta(minutes=5)
    _cycle_unibet(monkeypatch, [ligne(lu=plus_tard), ligne(issue="EXT", cote=3.4, lu=plus_tard)])
    journal = {"etapes": {}}
    cycle.collecter_prematch("complet", plus_tard, journal, donnees)
    apres = _jour(donnees).read_bytes()
    assert apres.startswith(avant)                                            # rien de réécrit, ajout seul
    nouvelles = _lignes_historique(donnees)[3:]
    assert nouvelles == [{"t": plus_tard.isoformat(), "b": "Unibet", "m": "unibet-fr|1",
                          "k": "RESULTAT_1N2|MATCH||EXT", "c": 3.4}]
    assert journal["historique_cotes"] == {"lignes": 1}


def test_aucune_ligne_ecrite_si_rien_ne_change(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMOIRE_CHEMIN", str(tmp_path / "memoire"))
    donnees = tmp_path / "donnees"
    _cycle_unibet(monkeypatch, [ligne()])
    cycle.collecter_prematch("complet", NOW, {"etapes": {}}, donnees)
    avant = _jour(donnees).read_bytes()
    plus_tard = NOW + timedelta(minutes=5)
    _cycle_unibet(monkeypatch, [ligne(lu=plus_tard)])                         # relue, même cote
    journal = {"etapes": {}}
    cycle.collecter_prematch("complet", plus_tard, journal, donnees)
    assert _jour(donnees).read_bytes() == avant
    assert journal["historique_cotes"] == {"lignes": 0}
    assert historique_cotes.ajouter(donnees, {}, {}, NOW) == 0


def test_selection_en_double_ne_compte_pas_comme_un_changement(tmp_path):
    horizon = {"unibet": {"lignes": [ligne(cote=2.0), ligne(cote=2.1)]}}     # même sélection, deux lignes
    assert historique_cotes.changements(historique_cotes.index(horizon), horizon) == []
    assert historique_cotes.ajouter(tmp_path, historique_cotes.index(horizon), horizon, NOW) == 0
    assert not (tmp_path / "cotes").exists()


def test_historique_jour_utc_et_joueur_dans_la_cle(tmp_path):
    tard = datetime(2026, 10, 30, 23, 30, tzinfo=timezone(timedelta(hours=-2)))   # 31/10 01:30 UTC
    n = historique_cotes.ajouter(tmp_path, {}, {"pmu": {"lignes": [ligne(joueur="Mbappé", marche="BUTEUR")]}}, tard)
    assert n == 2
    with gzip.open(tmp_path / "cotes" / "2026-10-31.jsonl.gz", "rt", encoding="utf-8") as f:
        assert json.loads(f.readlines()[1])["k"] == "BUTEUR|MATCH||DOM|Mbappé"


# --- controle.json ------------------------------------------------------------------------------------------

def test_controle_compact_publie_au_plus_une_fois_par_heure(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMOIRE_CHEMIN", str(tmp_path / "memoire"))
    etat = {"groupes": {"g": {"maj": NOW.isoformat(), "n": 1, "rapports": [0.9]}}, "matchs_suspects": []}
    assert cycle.enregistrer_controle(tmp_path, etat, NOW) is True
    texte = (tmp_path / "controle.json").read_text(encoding="utf-8")
    assert "\n" not in texte and ": " not in texte and json.loads(texte)["publie"] == NOW.isoformat()
    t2 = NOW + timedelta(minutes=5)
    etat2 = {"groupes": {"g": {"maj": t2.isoformat(), "n": 2, "rapports": [0.9, 0.91]}}, "matchs_suspects": []}
    assert cycle.enregistrer_controle(tmp_path, etat2, t2) is False
    assert (tmp_path / "controle.json").read_text(encoding="utf-8") == texte   # pas de nouvelle version
    assert cycle.lire_controle(tmp_path)["groupes"]["g"]["n"] == 2              # la mémoire suit chaque cycle
    assert cycle.enregistrer_controle(tmp_path, etat2, NOW + timedelta(minutes=55)) is True


def test_controle_sans_memoire_repart_de_la_publication(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMOIRE_CHEMIN", str(tmp_path / "memoire"))
    publie = {"groupes": {"g": {"maj": NOW.isoformat(), "n": 7}}, "publie": NOW.isoformat()}
    (tmp_path / "controle.json").write_text(json.dumps(publie))
    assert cycle.lire_controle(tmp_path) == {"groupes": {"g": {"maj": NOW.isoformat(), "n": 7}}}
    # mémoire plus ancienne que la publication (vieux cache restauré) : la publication gagne
    memoire.ecrire(tmp_path, "controle", {"groupes": {"g": {"maj": (NOW - timedelta(hours=2)).isoformat(), "n": 3}}},
                   retirer_ancien=False)
    assert cycle.lire_controle(tmp_path)["groupes"]["g"]["n"] == 7
    assert (tmp_path / "controle.json").exists()


def test_le_site_lit_le_controle_du_dernier_cycle(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMOIRE_CHEMIN", str(tmp_path / "memoire"))
    memoire.ecrire(tmp_path, "controle", {"groupes": {}, "matchs_suspects": [{"match_id": "x"}]},
                   retirer_ancien=False)
    assert memoire.lire(tmp_path, "controle", None, ancien_aussi=False)["matchs_suspects"] == [{"match_id": "x"}]


# --- workflow -----------------------------------------------------------------------------------------------

def test_workflow_memoire_en_cache_et_un_seul_commit():
    s = (Path(__file__).resolve().parents[1] / ".github/workflows/collecte.yml").read_text(encoding="utf-8")
    assert "path: memoire" in s and "restore-keys: memoire-" in s
    assert "key: memoire-${{ github.run_id }}-${{ github.run_attempt }}" in s
    assert s.count("MEMOIRE_CHEMIN: memoire") == 2
    assert s.count("git commit") == 1 and s.count("git push -q origin donnees") == 1
    assert "git rm -q --cached --ignore-unmatch horizon_direct.json pinnacle_secours_cache.json smarkets_cache.json" in s
    assert s.index("git rm -q --cached") < s.index("git add -A")
    for nom in memoire.SORTIS:
        assert f"/{nom}.json " in s or f"/{nom}.json\n" in s
    ignores = (Path(__file__).resolve().parents[1] / ".gitignore").read_text(encoding="utf-8").split()
    assert "memoire/" in ignores
