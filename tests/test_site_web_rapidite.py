from scripts.site_web import rapidite_alertes


def test_rapidite_ecarts_entre_releves_et_delai_envoi():
    historique = [{"debut": f"2026-10-18T10:{m:02d}:00Z"} for m in (0, 5, 10, 25, 30)] + [{"debut": "illisible"}]
    cycles = [{"envoi_demande_le": "2026-10-18T10:05:02Z",
               "alertes": [{"match": "A – B", "pari": "A gagne", "bookmaker": "PMU", "cote": 2.1,
                            "collecte_le": "2026-10-18T10:05:00Z"}]},
              {"envoi_demande_le": "2026-10-18T10:30:04Z",
               "alertes": [{"match": "C – D", "pari": "Nul", "bookmaker": "Betclic", "cote": 3.2,
                            "detecte": "2026-10-18T10:30:00Z"}]}]
    r = rapidite_alertes(historique, cycles)
    assert r["releves"] == 5 and r["ecart_median_min"] == 5 and r["ecarts_plus_8_min"] == 1
    assert r["plus_long_trou_min"] == 15 and r["envoi_median_s"] == 4
    assert [a["match"] for a in r["dernieres"]] == ["C – D", "A – B"]
    assert rapidite_alertes([], [])["envoi_median_s"] is None
