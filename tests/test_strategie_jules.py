"""Tests unitaires pour la stratégie JULES EDGE v1."""
from cotes.strategie_jules import JULES, motif_refus_jules, paris_jules


def _pari_base(**kw) -> dict:
    base = {
        "id": 100,
        "reference": "Pinnacle",
        "bookmaker": "Winamax",
        "sport": "football",
        "marche": "RESULTAT_1N2",
        "periode": "MATCH",
        "issue": "DOM",
        "cote": 2.0,
        "cote_juste": 1.818,
        "ecart": 0.10,
        "detecte": "2026-10-10T10:00:00Z",
        "debut": "2026-10-10T12:00:00Z",
        "lu_reference": "2026-10-10T09:58:00Z",
        "preuve_prise": {
            "ressemblance_noms": 0.95,
            "match_id_reference": "m123",
            "controle": {"statut": "conforme"},
        },
    }
    base.update(kw)
    return base


def test_motif_refus_jules_valide():
    pari = _pari_base()
    assert motif_refus_jules(pari) is None


def test_motif_refus_jules_refus():
    assert motif_refus_jules(_pari_base(reference="Polymarket")) == "référence différente de Pinnacle sans marge"
    assert motif_refus_jules(_pari_base(cote=1.10)) == "cote hors intervalle 1,30–2,50"
    assert motif_refus_jules(_pari_base(ecart=0.01)) == "edge hors intervalle 3–12 %"
    assert motif_refus_jules(_pari_base(detecte="2026-10-10T11:50:00Z")) == "détection hors fenêtre de 15 minutes à 12 heures"


def test_paris_jules_unicite_match_et_cap_journalier():
    pari1 = _pari_base(id=1, cote=2.0)
    pari2 = _pari_base(id=2, cote=2.1, bookmaker="Unibet")  # Même match m123

    paris = [pari1, pari2]
    sel = paris_jules(paris)
    assert len(sel) == 1
    assert id(pari2) in sel or id(pari1) in sel


def test_paris_jules_cap_journalier_maximum_6():
    paris = []
    for i in range(10):
        p = _pari_base(
            id=i + 1,
            detecte=f"2026-10-10T08:1{i}:00Z",
            debut=f"2026-10-10T12:1{i}:00Z",
            lu_reference=f"2026-10-10T08:1{i}:00Z",
            preuve_prise={
                "ressemblance_noms": 0.95,
                "match_id_reference": f"match_{i}",
                "controle": {"statut": "conforme"},
            },
        )
        paris.append(p)

    sel = paris_jules(paris)
    assert len(sel) == 6
