import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import site_web  # noqa: E402


def pari(sim, match, quand, statut="en_cours", cote=2.0, bm="Winamax"):
    return {"id": f"{sim}{match}{quand}", "simulation": sim, "reference": "Pinnacle", "match_id": match,
            "marche": "TOTAL", "periode": "MATCH", "ligne": 2.5, "issue": "PLUS", "detecte": quand, "statut": statut,
            "cote": cote, "bookmaker": bm, "sport": "football", "mise": 10, "gain": None, "clv": None}


def test_selection_par_fiches(monkeypatch):
    monkeypatch.setattr(site_web, "FICHES_AFFICHEES", 2)
    paris = [pari("A", "m1", "2026-10-01T10:00", cote=2.10), pari("C", "m1", "2026-10-03T11:00", cote=2.25),
             pari("A", "m2", "2026-10-02T10:00"), pari("A", "m3", "2026-10-04T10:00"),
             pari("A", "m0", "2026-09-01T10:00", statut="a_regler", bm="NetBet")]
    fiches, total, valeurs = site_web.selection_paris(paris, 2)
    # les 2 fiches les plus récentes (m3, m1 vue d'abord le 01/10 mais m2 le 02/10 -> m3, m2) + celle à régler
    assert [f["match_id"] for f in fiches] == ["m3", "m2", "m0"] and total == 4 and fiches[2]["a_regler"]
    assert valeurs["bookmaker"] == ["NetBet", "Winamax"] and valeurs["sims"] == ["A", "C"]  # filtres sur tout
    fiches, _, _ = site_web.selection_paris(paris, 10)
    m1 = next(f for f in fiches if f["match_id"] == "m1")
    assert m1["sims"] == ["A", "C"] and m1["cote"] == 2.10 and m1["detecte"] == "2026-10-01T10:00"   # 1re détection


def test_construire_bilan_sur_tous_les_paris(tmp_path):
    paris = [pari("A", f"m{i}", f"2026-10-01T10:{i:02d}") for i in range(5)]
    (tmp_path / "paris.json").write_text(json.dumps(paris), encoding="utf-8")
    import re
    html = site_web.construire(tmp_path, tmp_path / "site").read_text(encoding="utf-8")
    d = json.loads(re.search(r"const D = (\{.*?\});\n", html, re.S).group(1).replace("<\\/", "</"))
    assert d["fiches_total"] == 5 and d["bilan"]["A|Toutes"]["en_cours"] == 5
