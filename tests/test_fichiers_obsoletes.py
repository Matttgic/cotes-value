"""Les fichiers de « donnees » que plus aucun code n'utilise sont retirés, sans toucher au reste."""
from scripts import cycle


def test_obsoletes_retires_le_reste_intact(tmp_path):
    for nom in ("apisports.json", "rythme_sources.json", "docs/live_papier.json", "paris.json", "etat.json"):
        (tmp_path / nom).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / nom).write_text("{}", encoding="utf-8")
    journal = {}
    cycle.retirer_obsoletes(tmp_path, journal)
    assert journal["obsoletes_retires"] == ["apisports.json", "rythme_sources.json", "docs/live_papier.json"]
    assert sorted(p.name for p in tmp_path.iterdir() if p.is_file()) == ["etat.json", "paris.json"]


def test_rien_a_retirer_rien_dans_le_journal(tmp_path):
    journal = {}
    cycle.retirer_obsoletes(tmp_path, journal)
    assert journal == {}


def test_aucun_fichier_obsolete_n_est_encore_utilise():
    """Un nom de la liste ne doit plus apparaître dans le code qui lit ou écrit « donnees »."""
    from pathlib import Path
    racine = Path(__file__).resolve().parent.parent
    code = "\n".join(p.read_text(encoding="utf-8") for d in ("cotes", "scripts", "web")
                     for p in (racine / d).rglob("*") if p.suffix in (".py", ".js") and p.name != "cycle.py")
    for nom in cycle.FICHIERS_OBSOLETES:
        assert Path(nom).name not in code, nom
