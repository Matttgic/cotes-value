"""Suivi de la CLV des values Winamax, sans aucun pari (cotes/winamax_suivi.py, décidé le 26/11/2026)."""
import json
from datetime import datetime, timedelta, timezone

from cotes import comparaison, simulation, winamax_suivi as W
from cotes.pipeline.prise import suivre_winamax

T = datetime(2026, 11, 26, 12, 0, tzinfo=timezone.utc)
DEBUT = T + timedelta(hours=3)
LU = (T - timedelta(minutes=1)).isoformat()
OPP = {"bookmaker": "Winamax", "sport": "football", "match_id": "winamax|1", "domicile": "A", "exterieur": "B",
       "debut": DEBUT.isoformat(), "detecte": LU, "lu_reference": LU, "marche": "MONEYLINE", "periode": "MATCH",
       "ligne": None, "issue": "DOM", "pari": "A gagne", "cote": 2.1, "cote_juste": 2.0, "ecart": 0.05,
       "reference": "Pinnacle"}


def _justes(proba, lue, ref="Pinnacle"):
    return {("winamax|1", comparaison.cle(OPP)): {ref: (proba, lue.isoformat())}}


def test_value_winamax_notee_sans_devenir_un_pari():
    assert simulation.placer([OPP], [], maintenant=T) == []          # Winamax reste hors des paris
    suivi = []
    nouvelles = W.noter(suivi, [OPP, {**OPP, "bookmaker": "PMU", "match_id": "pmu|1"}], T)
    assert len(nouvelles) == 1 and suivi == nouvelles
    p = suivi[0]
    assert p["bookmaker"] == "Winamax" and p["statut"] == "en_cours" and "mise" not in p and "simulation" not in p
    assert W.noter(suivi, [OPP], T + timedelta(minutes=5)) == []       # une fois par référence et cote


def test_hors_regle_ou_lecture_perimee_non_notees():
    for o in ({**OPP, "cote": 6.0}, {**OPP, "ecart": 0.02}, {**OPP, "suspect": "x"},
              {**OPP, "detecte": (T - timedelta(minutes=10)).isoformat()}):
        assert W.noter([], [o], T) == []


def test_cloture_pinnacle_puis_bilan():
    suivi = []
    W.noter(suivi, [OPP], T)
    cloture = DEBUT - timedelta(minutes=10)
    W.suivre(suivi, _justes(1 / 2.2, cloture), cloture + timedelta(minutes=1))
    assert suivi[0]["statut"] == "en_cours" and suivi[0]["cloture_lue"] == cloture.isoformat(timespec="seconds")
    assert W.bilan(suivi)["n"] == 0                                     # pas encore close
    assert W.suivre(suivi, {}, DEBUT + timedelta(hours=2)) == 1
    b = W.bilan(suivi)
    assert suivi[0]["statut"] == "clos" and b["n"] == 1 and b["matchs"] == 1
    assert abs(b["moyenne"] - (2.1 / 2.2 - 1)) < 1e-4 and b["closes"] == 1 and b["en_cours"] == 0


def test_cloture_trop_ancienne_ou_autre_reference():
    p = {"reference": "Pinnacle", "cote": 2.1, "debut": DEBUT.isoformat(), "cote_juste_cloture": 2.0,
         "cloture_lue": (DEBUT - timedelta(hours=2)).isoformat()}
    assert W.clv(p) is None                                             # plus de 30 min avant le match
    poly = {"reference": "Polymarket", "cote": 2.1, "debut": DEBUT.isoformat(), "cote_juste_cloture": 2.0,
            "cloture_lue": (DEBUT - timedelta(minutes=5)).isoformat()}
    assert W.clv(poly) is None                                          # clôture Pinnacle requise
    poly.update(cote_juste_cloture_pinnacle=2.0, cloture_pinnacle_lue=(DEBUT - timedelta(minutes=5)).isoformat())
    assert abs(W.clv(poly) - 0.05) < 1e-9


def test_une_cote_comptee_une_fois():
    base = {"statut": "clos", "match_id": "winamax|1", "marche": "MONEYLINE", "periode": "MATCH", "issue": "DOM",
            "cote": 2.1, "debut": DEBUT.isoformat(), "cote_juste_cloture": 2.0,
            "cloture_lue": (DEBUT - timedelta(minutes=5)).isoformat()}
    suivi = [{**base, "reference": "Pinnacle", "detecte": "2026-11-26T10:00:00+00:00"},
             {**base, "reference": "Pinnacle", "detecte": "2026-11-26T11:00:00+00:00", "cote": 3.0}]
    b = W.bilan(suivi)
    assert b["n"] == 1 and abs(b["moyenne"] - 0.05) < 1e-9 and b["ic95"] is None


def test_cycle_ecrit_le_suivi_et_ne_bloque_jamais(tmp_path):
    journal = {}
    suivre_winamax(tmp_path, [{**OPP, "detecte": datetime.now(timezone.utc).isoformat(),
                               "lu_reference": datetime.now(timezone.utc).isoformat(),
                               "debut": (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()}],
                   {}, set(), T, journal)
    assert journal["winamax_suivi"] == {"notees": 1, "closes": 0, "total": 1}
    assert len(json.loads((tmp_path / W.FICHIER).read_text())) == 1
    (tmp_path / W.FICHIER).write_text("{}")                             # fichier illisible : repart de zéro
    suivre_winamax(tmp_path, [], {}, set(), T, journal)
    assert journal["winamax_suivi"]["total"] == 0
    (tmp_path / W.FICHIER).write_text(json.dumps([{**OPP, "id": "x", "statut": "en_cours"}]))
    journal = {"echecs": []}
    suivre_winamax(tmp_path, [], None, set(), T, journal)               # justes illisibles : erreur notée, pas levée
    assert "erreur" in journal["winamax_suivi"]
