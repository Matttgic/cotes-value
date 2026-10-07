import json
from datetime import datetime, timezone

from cotes.stockage import archiver, lire_archives


def test_archives_mensuelles(tmp_path):
    maintenant = datetime(2026, 12, 15, tzinfo=timezone.utc)
    paris = [{"id": "1", "statut": "gagne", "regle_le": "2026-10-03T10:00:00+00:00", "detecte": "a"},
             {"id": "2", "statut": "perdu", "regle_le": "2026-11-02T10:00:00+00:00", "detecte": "b"},
             {"id": "3", "statut": "perdu", "regle_le": "2026-12-10T10:00:00+00:00", "detecte": "c"},   # récent
             {"id": "4", "statut": "en_cours", "detecte": "d"}]
    restent = archiver(tmp_path, paris, maintenant)
    assert [p["id"] for p in restent] == ["3", "4"]
    assert sorted(f.name for f in (tmp_path / "archives").iterdir()) == ["paris-2026-10.json.gz", "paris-2026-11.json.gz"]
    # un second passage ne duplique rien ; tout reste lisible pour le bilan
    archiver(tmp_path, paris, maintenant)
    assert sorted(p["id"] for p in lire_archives(tmp_path) + restent) == ["1", "2", "3", "4"]


def test_site_compte_les_archives(tmp_path):
    import re
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import site_web
    base = {"simulation": "A", "reference": "Pinnacle", "marche": "TOTAL", "periode": "MATCH", "ligne": 2.5,
            "issue": "PLUS", "mise": 10, "cote": 2.0, "clv": None, "detecte": "2026-10-01T10:00"}
    archiver(tmp_path, [{**base, "id": "v", "match_id": "m1", "statut": "gagne", "gain": 10.0,
                         "regle_le": "2026-10-02T10:00:00+00:00"}], datetime(2026, 12, 1, tzinfo=timezone.utc))
    (tmp_path / "paris.json").write_text(json.dumps([{**base, "id": "w", "match_id": "m2", "statut": "en_cours",
                                                      "gain": None}]), encoding="utf-8")
    html = site_web.construire(tmp_path, tmp_path / "site").read_text(encoding="utf-8")
    d = json.loads(re.search(r"const D = (\{.*?\});\n", html, re.S).group(1).replace("<\\/", "</"))
    assert d["bilan"]["A|Toutes"]["paris"] == 2 and d["bilan"]["A|Toutes"]["gains"] == 10.0


def test_fichier_de_donnees_corrompu_arrete_le_cycle(tmp_path):
    # revue externe (8.1) : un paris.json illisible était lu comme une liste vide, puis écrasé
    import sys
    from pathlib import Path
    import pytest
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import cycle
    f = tmp_path / "paris.json"
    f.write_text('[{"id": ', encoding="utf-8")
    with pytest.raises(ValueError):
        cycle.lire_json(f, [])
    assert cycle.lire_json(tmp_path / "absent.json", []) == []
    cycle.ecrire_json(f, [{"id": 1}])
    assert cycle.lire_json(f, []) == [{"id": 1}] and not list(tmp_path.glob("*.tmp"))
