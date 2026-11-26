"""Filtres observés (cotes/filtres_observes.py) : 2 sources ou plus et écart minimal, suivis après le gel du 26/11."""
from cotes import filtres_observes as F


def _pari(i, ecart, ref="Pinnacle", detecte="2026-11-27T10:00:00+00:00", match="pmu|1", statut="gagne"):
    return {"id": f"{i}{ref}", "bookmaker": "PMU", "reference": ref, "match_id": match, "marche": "MONEYLINE",
            "periode": "MATCH", "ligne": None, "issue": "DOM", "cote": 2.0, "ecart": ecart, "detecte": detecte,
            "debut": "2026-11-27T20:00:00+00:00", "statut": statut, "mise": 10.0, "gain": 10.0}


def _construire(paris):
    return F.construire(paris, lambda p: p["match_id"], {})


def test_seuils_figes_et_un_seul_principal():
    assert F.PRINCIPAL in F.SEUILS and F.SOURCES_MIN == 2 and F.GEL.startswith("2026-11-26")
    out = _construire([])
    assert [f["principal"] for f in out["filtres"]] == [s == F.PRINCIPAL for s in F.SEUILS]
    assert all(f["paris"] == 0 and not f["prouve"] for f in out["filtres"])


def test_deux_sources_et_ecart():
    paris = [_pari(1, 0.09), _pari(1, 0.09, ref="Polymarket", detecte="2026-11-27T10:05:00+00:00"),   # 2 sources, 9 %
             _pari(2, 0.12, match="pmu|2"),                                                          # 1 source
             _pari(3, 0.06, match="pmu|3"), _pari(3, 0.06, ref="Matchbook", match="pmu|3")]           # 2 sources, 6 %
    par_seuil = {f["seuil"]: f for f in _construire(paris)["filtres"]}
    assert par_seuil[0.05]["paris"] == 2 and par_seuil[0.08]["paris"] == 1 and par_seuil[0.10]["paris"] == 0
    assert par_seuil[0.08]["regles"] == 1 and par_seuil[0.08]["gain"] == 10.0


def test_paris_d_avant_le_gel_exclus():
    avant = "2026-11-20T10:00:00+00:00"
    paris = [_pari(1, 0.09, detecte=avant), _pari(1, 0.09, ref="Polymarket", detecte=avant)]
    assert all(f["paris"] == 0 for f in _construire(paris)["filtres"])
