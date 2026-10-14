"""Tests de non-fuite temporelle et du moteur M3."""
from datetime import datetime, timedelta, timezone

from cotes.strategie_m3 import M3, motif_refus_m3, paris_m3


def pari(n=1, quand="2026-10-15T10:00:00+00:00"):
    t = datetime.fromisoformat(quand)
    return {
        "id": str(n), "reference": "Pinnacle", "bookmaker": "Betclic",
        "sport": "basket", "marche": "VAINQUEUR", "periode": "MATCH",
        "issue": "DOM", "ligne": None, "match_id": "betclic|1",
        "detecte": t.isoformat(), "debut": (t + timedelta(hours=2)).isoformat(),
        "lu_reference": (t - timedelta(minutes=3)).isoformat(),
        "cote": 1.8, "cote_juste": 1.72,
        "ecart": round(1.8 / 1.72 - 1, 4),
        "preuve_prise": {
            "match_id_reference": 123,
            "controle": {"statut": "conforme"},
        },
    }


def test_m3_admissible_et_sans_fuite_des_resultats():
    p = pari()
    assert motif_refus_m3(p) is None
    a = paris_m3([p])
    p.update(statut="perdu", gain=-10, clv=-0.08, regle_le="2026-10-16T05:00:00+00:00")
    assert a == paris_m3([p])


def test_m3_refuse_suspect_hors_bornes_ou_avant_lancement():
    p = pari()
    assert motif_refus_m3({**p, "sport": "football"}) is not None
    assert motif_refus_m3({**p, "cote": 8.0}) is not None
    assert motif_refus_m3({**p, "suspect": True}) is not None
    assert motif_refus_m3({**p, "preuve_prise": {"controle": {"statut": "non_conforme"}}}) is not None
    assert motif_refus_m3(pari(quand="2026-10-13T10:00:00+00:00")) is not None
    assert M3["debut"].startswith("2026-10-14T22:00")


def test_m3_premiere_detection_sans_choisir_le_gagnant():
    p1 = pari(1)
    p2 = pari(2, "2026-10-15T10:05:00+00:00")
    p2["gain"], p2["statut"] = 30, "gagne"
    p1["gain"], p1["statut"] = -10, "perdu"
    assert paris_m3([p1, p2]) == {id(p1)}
    p2["issue"] = "EXT"
    assert paris_m3([p1, p2]) == {id(p1), id(p2)}


def test_m3_ne_prend_pas_totaux_en_quarts():
    p = pari()
    p.update(marche="TOTAL", issue="PLUS", ligne=213.25)
    assert motif_refus_m3(p) is not None
