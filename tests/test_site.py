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


def test_courbes_du_gain_cumule():
    base = {"simulation": "A", "mise": 10, "match_id": "w|1", "marche": "VAINQUEUR", "periode": "MATCH",
            "ligne": None, "issue": "DOM", "joueur": None, "statut": "gagne", "gain": 11.0}
    paris = [{**base, "reference": "Pinnacle", "regle_le": "2026-10-07T12:00:00+00:00", "detecte": "1"},
             {**base, "reference": "Betfair", "regle_le": "2026-10-07T12:00:00+00:00", "detecte": "2"},
             {**base, "reference": "Pinnacle", "issue": "EXT", "statut": "perdu", "gain": -10.0,
              "regle_le": "2026-10-07T11:00:00+00:00", "detecte": "1"},
             {**base, "reference": "Pinnacle", "issue": "NUL", "statut": "en_cours", "gain": None, "detecte": "1"}]
    c = site_web.courbes(paris)
    assert [p[1] for p in c["Pinnacle"]] == [-10.0, 11.0]               # dans l'ordre du règlement
    assert len(c["Toutes"]) == 3 and len(c["Uniques"]) == 2              # la même cote ne compte qu'une fois


def test_gain_attendu_et_bilan_par_bookmaker():
    from cotes.simulation import bilan_bookmakers
    base = {"simulation": "A", "mise": 10, "match_id": "w|1", "marche": "VAINQUEUR", "periode": "MATCH", "ligne": None,
            "issue": "DOM", "joueur": None, "statut": "perdu", "gain": -10.0, "cote": 2.2, "cote_juste": 2.0,
            "regle_le": "2026-10-07T12:00:00+00:00", "detecte": "1", "bookmaker": "PMU"}
    c = site_web.courbes([{**base, "reference": "Pinnacle"}, {**base, "reference": "Pinnacle brut", "issue": "EXT"}])
    assert c["Uniques"][0][3] == 1.0                     # 10 × (2,2 / 2,0 − 1)
    assert c["Pinnacle brut"][0][3] is None              # témoin : pas de gain attendu
    b = bilan_bookmakers([{**base, "reference": "Pinnacle"}, {**base, "reference": "Pinnacle", "simulation": "X",
                                                             "issue": "EXT", "bookmaker": "Winamax"}])
    assert b["PMU·A|Uniques"]["regles"] == 1 and b["Winamax·X|Uniques"]["regles"] == 1


def test_bilan_reel_contre_espere_selon_la_clv():
    from cotes.simulation import bilan
    base = {"simulation": "A", "mise": 10, "reference": "Pinnacle", "marche": "VAINQUEUR", "periode": "MATCH",
            "ligne": None, "joueur": None, "cote": 2.0, "detecte": "1", "debut": "2026-10-07T18:00:00+00:00"}
    avec = {**base, "match_id": "w|1", "issue": "DOM", "statut": "gagne", "gain": 10.0, "clv": 0.05,
            "cloture_lue": "2026-10-07T17:50:00+00:00"}
    sans = {**base, "match_id": "w|2", "issue": "DOM", "statut": "perdu", "gain": -10.0}       # pas de clôture
    ouvert = {**base, "match_id": "w|3", "issue": "DOM", "statut": "en_cours", "gain": None}
    b = bilan([avec, sans, ouvert])["A|Pinnacle"]
    assert b["gains_avec_clv"] == 10.0 and b["espere_clv"] == 0.5
    assert b["regles_sans_clv"] == 1 and b["gains_sans_clv"] == -10.0


def test_segments_reussite_contre_attendu_sans_doublon():
    from cotes.simulation import segments
    base = {"simulation": "A", "mise": 10, "reference": "Pinnacle", "marche": "VAINQUEUR", "periode": "MATCH",
            "ligne": None, "joueur": None, "cote": 1.3, "cote_juste": 1.25, "detecte": "1", "bookmaker": "Betclic",
            "sport": "hockey", "issue": "DOM"}
    paris = [{**base, "match_id": f"b|{i}", "statut": "gagne" if i < 11 else "perdu", "gain": 3.0 if i < 11 else -10.0}
             for i in range(12)]
    s = segments(paris)
    assert len(s) == 1                          # tranche, bookmaker, sport et croisements : les mêmes 12 paris
    seg = s[0]
    assert seg == {**seg, "tranche": "1,01 – 1,50", "n": 12, "gagnes": 11, "attendus": 9.6}
    assert seg["ecart_sigma"] > 0 and seg["roi"] == round((33 - 10) / 120, 4)


def test_paris_a_venir_des_segments_uniques_et_pas_commences():
    from datetime import datetime, timezone
    base = {"simulation": "A", "mise": 10, "reference": "Pinnacle", "marche": "VAINQUEUR", "periode": "MATCH",
            "ligne": None, "joueur": None, "cote": 1.3, "cote_juste": 1.25, "bookmaker": "Betclic", "sport": "hockey",
            "issue": "DOM", "statut": "en_cours", "ecart": 0.04, "domicile": "A", "exterieur": "B"}
    paris = [{**base, "match_id": "b|1", "detecte": "1", "debut": "2026-10-12T20:00:00.000Z"},
             {**base, "match_id": "b|1", "detecte": "2", "reference": "Betfair", "debut": "2026-10-12T20:00:00.000Z"},
             {**base, "match_id": "b|2", "detecte": "1", "debut": "2026-10-12T09:00:00Z"},     # déjà commencé
             {**base, "match_id": "b|3", "detecte": "1", "debut": "2026-10-12T15:00:00+00:00"},
             {**base, "match_id": "b|4", "detecte": "1", "debut": "2026-10-13T15:00:00Z", "statut": "gagne"}]
    L = site_web.paris_a_venir_des_segments(paris, datetime(2026, 10, 12, 12, tzinfo=timezone.utc))
    assert [x[8] for x in L] == ["2026-10-12T15:00:00+00:00", "2026-10-12T20:00:00.000Z"]   # un seul pari par cote
    assert L[0][2] == "Betclic" and L[0][9] == "1,01 – 1,50" and L[0][10] == "hockey" and L[0][5] == 0.04
