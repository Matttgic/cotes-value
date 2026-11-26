"""Values Winamax affichées à part sur l'Accueil : la règle de prise sans l'exclusion de Winamax, jamais des paris."""
from datetime import datetime, timedelta, timezone

from cotes import simulation
from cotes.site.construction import winamax_a_part

T = datetime(2026, 11, 26, 12, 0, tzinfo=timezone.utc)
BASE = {"bookmaker": "Winamax", "sport": "football", "match_id": "winamax|1", "domicile": "A", "exterieur": "B",
        "debut": (T + timedelta(hours=3)).isoformat(), "detecte": T.isoformat(), "marche": "MONEYLINE",
        "periode": "MATCH", "ligne": None, "issue": "DOM", "pari": "A gagne", "cote": 2.1, "cote_juste": 2.0,
        "ecart": 0.05, "reference": "Pinnacle"}


def test_winamax_reste_hors_de_la_regle_de_prise():
    assert simulation.motif_hors_regle(BASE) == "Winamax"
    assert simulation.dans_regle_sauf_bookmaker(BASE)
    assert simulation.placer([BASE], [], maintenant=T) == []


def test_values_winamax_dans_la_regle_publiees_une_fois_par_cote():
    autre_ref = {**BASE, "reference": "Polymarket", "ecart": 0.04}
    lignes = winamax_a_part([autre_ref, BASE], T)
    assert len(lignes) == 1 and lignes[0]["reference"] == "Pinnacle" and lignes[0]["ecart"] == 0.05
    assert "statut" not in lignes[0] and "mise" not in lignes[0]


def test_hors_regle_ou_autre_bookmaker_ecartes():
    exclus = [{**BASE, "bookmaker": "PMU"}, {**BASE, "cote": 6.0}, {**BASE, "ecart": 0.02},
              {**BASE, "debut": (T - timedelta(minutes=1)).isoformat()},
              {**BASE, "debut": (T + timedelta(hours=30)).isoformat()},
              {**BASE, "suspect": "intitulé"}, {**BASE, "pariable": False}, {**BASE, "match_id": None},
              {**BASE, "debut": None}]
    assert winamax_a_part(exclus, T) == []
    assert winamax_a_part(None, T) == []
