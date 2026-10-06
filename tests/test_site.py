import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import site_web  # noqa: E402


def pari(sim, match, quand, statut="en_cours", cote=2.0, bm="Winamax"):
    return {"id": f"{sim}{match}{quand}", "simulation": sim, "reference": "Pinnacle", "match_id": match,
            "marche": "TOTAL", "periode": "MATCH", "ligne": 2.5, "issue": "PLUS", "detecte": quand, "statut": statut,
            "cote": cote, "bookmaker": bm, "sport": "football", "mise": 10, "gain": None, "clv": None}


def test_selection_par_fiches():
    paris = [pari("A", "m1", "2026-10-01T10:00", cote=2.10), pari("C", "m1", "2026-10-03T11:00", cote=2.25),
             pari("A", "m2", "2026-10-02T10:00"), pari("A", "m3", "2026-10-04T10:00"),
             pari("A", "m0", "2026-09-01T10:00", statut="a_regler", bm="NetBet"),
             {**pari("A", "m8", "2026-09-02T10:00", statut="gagne"), "regle_le": "2026-09-03T10:00"},
             {**pari("A", "m9", "2026-09-01T09:00", statut="perdu"), "regle_le": "2026-09-01T12:00"}]
    fiches, total, valeurs = site_web.selection_paris(paris, en_cours=2, regles=1)
    # 2 en cours les plus récents (m3, m2) + le réglé le plus récent (m8) + celui à régler (m0)
    assert [f["match_id"] for f in fiches] == ["m3", "m2", "m8", "m0"] and total == 6 and fiches[3]["a_regler"]
    assert valeurs["bookmaker"] == ["NetBet", "Winamax"] and valeurs["sims"] == ["A", "C"]  # filtres sur tout
    fiches, _, _ = site_web.selection_paris(paris)
    m1 = next(f for f in fiches if f["match_id"] == "m1")
    assert m1["sims"] == ["A", "C"] and m1["cote"] == 2.10 and m1["detecte"] == "2026-10-01T10:00"   # 1re détection


def test_temoin_a_sa_propre_part():
    paris = [{**pari("A", f"t{i}", f"2026-10-05T10:{i:02d}"), "reference": "Pinnacle brut"} for i in range(50)]
    paris += [pari("A", f"v{i}", f"2026-10-01T10:{i:02d}") for i in range(5)]
    fiches, _, _ = site_web.selection_paris(paris, en_cours=8, regles=4)
    assert sum(f["reference"] == "Pinnacle" for f in fiches) == 5          # pas évincés par le témoin
    assert sum(f["reference"] == "Pinnacle brut" for f in fiches) == 2     # 8 // 4


def test_construire_bilan_sur_tous_les_paris(tmp_path):
    paris = [pari("A", f"m{i}", f"2026-10-01T10:{i:02d}") for i in range(5)]
    (tmp_path / "paris.json").write_text(json.dumps(paris), encoding="utf-8")
    import re
    html = site_web.construire(tmp_path, tmp_path / "site").read_text(encoding="utf-8")
    d = json.loads(re.search(r"const D = (\{.*?\});\n", html, re.S).group(1).replace("<\\/", "</"))
    assert d["fiches_total"] == 5 and d["bilan"]["A|Toutes"]["en_cours"] == 5
