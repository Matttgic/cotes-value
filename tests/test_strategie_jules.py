"""Tests unitaires pour les stratégies JULES EDGE v1 et v2."""
from cotes.strategie_jules import JULES, JULES_V2, motif_refus_jules, motif_refus_jules_v2, paris_jules, paris_jules_v2


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


def test_motif_refus_jules_v2_valide():
    pari = _pari_base(detecte="2026-10-14T13:00:00Z", debut="2026-10-14T18:00:00Z", lu_reference="2026-10-14T12:58:00Z")
    assert motif_refus_jules_v2(pari) is None

    pari_betfair = _pari_base(reference="Betfair", detecte="2026-10-14T13:00:00Z", debut="2026-10-14T18:00:00Z", lu_reference="2026-10-14T12:58:00Z", cote=2.70, ecart=0.028, cote_juste=2.6264)
    assert motif_refus_jules_v2(pari_betfair) is None


def test_motif_refus_jules_v2_refus():
    p = _pari_base(reference="Kalshi", detecte="2026-10-14T13:00:00Z", debut="2026-10-14T18:00:00Z", lu_reference="2026-10-14T12:58:00Z")
    assert motif_refus_jules_v2(p) == "référence hors périmètre (Pinnacle, Betfair, Polymarket)"

    p_cote = _pari_base(cote=2.90, detecte="2026-10-14T13:00:00Z", debut="2026-10-14T18:00:00Z", lu_reference="2026-10-14T12:58:00Z")
    assert motif_refus_jules_v2(p_cote) == "cote hors intervalle 1,30–2,80"


def test_paris_jules_v2_cap_journalier_maximum_8():
    paris = []
    for i in range(12):
        p = _pari_base(
            id=i + 1,
            detecte=f"2026-10-14T13:{i:02d}:00Z",
            debut=f"2026-10-14T18:{i:02d}:00Z",
            lu_reference=f"2026-10-14T13:{i:02d}:00Z",
            preuve_prise={
                "ressemblance_noms": 0.95,
                "match_id_reference": f"match_{i}",
                "controle": {"statut": "conforme"},
            },
        )
        paris.append(p)

    sel = paris_jules_v2(paris)
    assert len(sel) == 8
