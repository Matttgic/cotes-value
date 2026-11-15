"""Étude des erreurs systématiques (etudes/erreurs_systematiques.py) : classement des paris et des causes."""
from etudes import erreurs_systematiques as E


def pari(**kw):
    base = {"bookmaker": "PMU", "match_id": "pmu|1", "marche": "RESULTAT_1N2", "periode": "MATCH", "ligne": None,
            "issue": "DOM", "detecte": "2026-11-01T12:00:00+00:00", "debut": "2026-11-01T12:30:00+00:00", "cote": 2.0,
            "sport": "football", "mouvement_pinnacle": 0.0, "trj_bookmaker": 0.93, "limite_pinnacle": 200}
    return {**base, **kw}


def test_familles_et_segments():
    assert E.famille_marche(pari(marche="TOTAL_DOM")) == "Total d'une équipe"
    assert E.famille_marche(pari(marche="INCONNU")) == "Autre marché"
    assert E.periode(pari(periode="QT1")).startswith("Autre partie")
    assert E.liquidite(pari(limite_pinnacle=2000)) == "limite Pinnacle > 1 500 €"
    assert E.liquidite(pari(limite_pinnacle=None)) is None
    assert E.delai(pari()) == "moins d'1 h avant"


def test_causes_copie_puis_lenteur_puis_marge():
    cle = ("cycle", "pin-1", "RESULTAT_1N2", "MATCH", None, "DOM", "Pinnacle")
    copie = pari()
    lent = pari(match_id="pmu|2", mouvement_pinnacle=0.01)
    marge = pari(match_id="pmu|3")
    vers_cycle = {("PMU", "pmu|1", "RESULTAT_1N2", "MATCH", None, "DOM", copie["detecte"]): cle}
    par_selection = {cle: {"PMU": 2.0, "Unibet": 2.0}}
    c = E.causes([copie, lent, marge], vers_cycle, par_selection)
    assert c["paris"] == 3 and c["copie"] == c["lent"] == c["marge"] == 1 / 3
    assert E.causes([pari(detecte="2026-10-01T00:00:00+00:00")], {}, {}) == {"paris": 0}   # avant le 25/10


def test_segments_separent_les_grosses_cotes():
    paris = [pari(match_id=f"pmu|{i}", cote=2.0) for i in range(45)] + [
        pari(match_id=f"pmu|g{i}", cote=30.0, marche="CORRECT_SCORE") for i in range(45)]
    noms = {(f, n): len(ps) for f, n, ps in E.segments(paris)}
    assert noms[("Type de marché", "1N2 / vainqueur")] == 45
    assert noms[("Grosses cotes (> 5) par marché", "Score exact")] == 45
    assert ("Type de marché", "Score exact") not in noms
