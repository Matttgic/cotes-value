from datetime import datetime, timezone

from cotes.reglement import taux_manuel
from cotes.simulation import bilan_plafond

T = datetime(2026, 11, 13, tzinfo=timezone.utc)


def _p(debut, statut="gagne", origine="automatique"):
    return {"debut": debut, "statut": statut, "preuve_reglement": {"origine": origine}}


def test_taux_manuel_compte_main_et_a_regler():
    paris = [_p("2026-11-12T10:00:00Z"), _p("2026-11-11T10:00:00Z", origine="résultat saisi à la main"),
             _p("2026-11-10T10:00:00Z", statut="a_regler"), _p("2026-11-12T20:00:00Z", statut="en_cours"),
             _p("2026-11-01T10:00:00Z"), _p("2026-11-02T10:00:00Z", origine="statut saisi à la main")]
    r = taux_manuel(paris, T)
    assert (r["total"], r["manuel"], r["a_regler"], r["taux"]) == (3, 1, 1, 0.6667)
    assert r["taux_avant"] == 0.5 and r["alerte"]


def test_taux_manuel_vide():
    assert taux_manuel([], T)["taux"] is None and not taux_manuel([], T)["alerte"]


def test_plafond_reduit_les_matchs_charges():
    base = {"bookmaker": "PMU", "match_id": "m1", "debut": "2026-11-12T10:00:00Z", "domicile": "Lyon",
            "exterieur": "Nice", "sport": "football", "marche": "TOTAL", "periode": "MATCH", "cote": 2.0,
            "reference": "Pinnacle", "detecte": "2026-11-12T08:00:00Z", "mise": 10.0}
    paris = [dict(base, id="a", issue="OVER", ligne=2.5, statut="gagne", gain=10.0),
             dict(base, id="b", issue="OVER", ligne=3.5, statut="gagne", gain=10.0),
             dict(base, id="c", issue="UNDER", ligne=1.5, statut="perdu", gain=-10.0)]
    sans, dix = bilan_plafond(paris, plafonds=(10.0,))
    assert sans["matchs"] == 1 and sans["paris"] == 3 and sans["gains"] == 10.0 and sans["mises"] == 30.0
    assert dix["matchs_reduits"] == 1 and dix["mises"] == 10.0 and dix["gains"] == 3.33
