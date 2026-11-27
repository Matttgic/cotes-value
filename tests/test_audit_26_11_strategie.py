"""Audit « stratégie » du 26/11/2026 (etudes/audit_26_11.py, docs/audit-26-11-strategie.md)."""
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import NormalDist

import numpy as np

from cotes import simulation
from etudes import audit_26_11 as a

RACINE = Path(__file__).resolve().parent.parent
T0 = datetime(2026, 11, 20, 12, tzinfo=timezone.utc)


def pari(i=0, cote=2.0, ecart=0.04, bookmaker="PMU", avance_h=2.0, statut="gagne", detecte=T0, ref="Pinnacle",
         match="m1", issue="1", **autres):
    gain = {"gagne": 10 * ((cote or 2.0) - 1), "perdu": -10.0, "rembourse": 0.0}.get(statut)
    p = {"id": f"p{i}", "cote": cote, "ecart": ecart, "bookmaker": bookmaker, "reference": ref, "statut": statut,
         "gain": gain, "mise": 10.0, "match_id": match, "marche": "RESULTAT_1N2", "periode": "MATCH", "ligne": None,
         "issue": issue, "detecte": detecte.isoformat() if isinstance(detecte, datetime) else detecte,
         "debut": (detecte + timedelta(hours=avance_h)).isoformat() if avance_h is not None else None}
    p.update(autres)
    return p


def test_dans_regle_equivaut_a_la_regle_de_prise():
    cas = [pari(cote=c, ecart=e, bookmaker=b, avance_h=h)
           for c in (1.5, 5.0, 5.01, None) for e in (0.0299999, 0.03, 0.05, None)
           for b in ("PMU", "Winamax", "OlyBet", None) for h in (1.0, 24.0, 24.5, None)]
    assert len(cas) == 256
    for p in cas:
        assert a.dans_regle(p) == (simulation.motif_hors_regle(p) is None), p


def test_chaque_contrainte_se_relache_seule():
    assert not a.dans_regle(pari(bookmaker="Winamax"))
    assert a.dans_regle(pari(bookmaker="Winamax"), exclus=("OlyBet",))
    assert not a.dans_regle(pari(bookmaker="OlyBet"), exclus=("OlyBet",))
    assert a.dans_regle(pari(cote=7.0), cote_max=10.0) and not a.dans_regle(pari(cote=7.0))
    assert a.dans_regle(pari(ecart=0.025), ecart_min=0.02) and not a.dans_regle(pari(ecart=0.025))
    assert a.dans_regle(pari(avance_h=30), avance_h=math.inf) and not a.dans_regle(pari(avance_h=30))


def test_univers_une_mise_par_cote_paris_regles_seulement():
    premier = pari(0, ref="Polymarket")
    second = pari(1, ref="Pinnacle", detecte=T0 + timedelta(minutes=5))
    ouvert = pari(2, match="m2", statut="en_cours")
    hors = pari(3, match="m3", cote=6.0)
    assert [p["id"] for p in a.univers([second, premier, ouvert, hors])] == ["p0"]
    # Relâcher le plafond fait entrer la cote 6 : même univers, une seule contrainte en moins.
    assert {p["id"] for p in a.univers([second, premier, ouvert, hors], cote_max=10.0)} == {"p0", "p3"}


def test_tranches():
    assert a.tranche_delai(pari(avance_h=0.5)) == "≤ 1 h"
    assert a.tranche_delai(pari(avance_h=12)) == "6–12 h"
    assert a.tranche_delai(pari(avance_h=30)) == "> 24 h"
    assert a.tranche_delai(pari(avance_h=None)) == "inconnu"
    assert a.tranche_age({"age_prix_pinnacle_s": 30}) == "≤ 1 min"
    assert a.tranche_age({"age_prix_pinnacle_s": 300}) == "2–5 min"
    assert a.tranche_age({"age_prix_pinnacle_s": 301}) == "> 5 min"
    assert a.tranche_age({"age_prix_pinnacle_s": -1}) == a.tranche_age({}) == "inconnu"
    assert a.tranche_heure({"detecte": "2026-11-20T06:30:00+00:00"}) == "0 h – 8 h"        # 7 h 30 à Paris
    assert a.tranche_heure({"detecte": "2026-11-20T19:30:00+00:00"}) == "20 h – 24 h"      # 20 h 30 à Paris
    assert a.tranche_ecart({"simulation": "E"}) == "E (7 % et plus)"
    assert a.periode({"detecte": "2026-11-14T22:59:59+00:00"}) == "avant"
    assert a.periode({"detecte": "2026-11-14T23:00:00+00:00"}) == "apres"     # gel : 15/11 à 0 h, Paris


def test_mesurer_compte_par_match():
    paris = [pari(i, match=f"m{i // 2}", issue=str(i), statut="gagne" if i % 4 == 0 else "perdu") for i in range(40)]
    clv = {id(p): 0.01 * (i % 5) for i, p in enumerate(paris)}
    x = a.mesurer("test", "ligne", paris, lambda p: p["match_id"], clv, 300, np.random.default_rng(1))
    assert x["paris"] == 40 and x["matchs"] == 20 and x["teste"] and x["clv_teste"]
    assert math.isclose(x["roi"], (10 * 10 - 30 * 10) / 400)
    assert math.isclose(x["clv"], 0.02) and x["clv_n"] == 40
    assert x["roi_ic"][0] < x["roi"] < x["roi_ic"][1]
    assert math.isclose(x["et_hasard"], math.sqrt(40 * 1.0) / 40)
    sans = a.mesurer("test", "ligne", paris, lambda p: p["match_id"], clv, 0, None)    # formule, sans bootstrap
    assert math.isclose(sans["roi"], x["roi"]) and sans["roi_ic"][0] < sans["roi"] < sans["roi_ic"][1]
    petit = a.mesurer("test", "petit", paris[:10], lambda p: p["match_id"], clv, 300, np.random.default_rng(1))
    assert not petit["teste"] and not petit["clv_teste"]


def test_corriger_compte_les_survivants():
    lignes = [{"teste": True, "clv_teste": True, "roi": r, "roi_p": p, "clv": r, "clv_p": p}
              for r, p in ((0.05, 0.0001), (-0.04, 0.0002), (0.01, 0.04), (0.02, 0.5))]
    t = a.corriger(lignes)
    assert t["roi"]["tests"] == 4 and t["roi"]["p_brute_5"] == 3
    assert (t["roi"]["bh_positif"], t["roi"]["bh_negatif"]) == (1, 1)
    assert (t["clv"]["holm_positif"], t["clv"]["holm_negatif"]) == (1, 1)


def test_decouverte_puis_confirmation():
    def bloc(clv, p, teste=True):
        return {"clv_teste": teste, "clv": clv, "clv_p_pos": p, "nom": "x"}
    lignes = [
        {"tout": {"nom": "robuste", "roi_moins_clv_ic": [-0.05, 0.03]}, "avant": bloc(0.03, 1e-5), "apres": bloc(0.02, 1e-3)},
        {"tout": {"nom": "contredite", "roi_moins_clv_ic": [-0.30, -0.02]}, "avant": bloc(0.09, 1e-6), "apres": bloc(0.08, 1e-4)},
        {"tout": {"nom": "bruit"}, "avant": bloc(0.01, 0.30), "apres": bloc(0.01, 0.30)},
        {"tout": {"nom": "retombée"}, "avant": bloc(0.02, 1e-4), "apres": bloc(-0.01, 0.80)},
        {"tout": {"nom": "attente"}, "avant": bloc(0.02, 1e-4), "apres": bloc(None, None, teste=False)},
    ]
    r = a.decouvrir_confirmer(lignes, +1)
    assert r["decouvertes"] == ["robuste", "contredite", "retombée", "attente"]
    assert r["robustes"] == ["robuste"] and r["testables_apres"] == 3
    assert [x.get("robustesse", {}).get(1) for x in lignes] == [
        "robuste", "contredite par le ROI", None, "non confirmée après le gel",
        "en attente (moins de 30 CLV après le gel)"]


def test_puissance_et_kelly():
    z = NormalDist().inv_cdf(0.95) + NormalDist().inv_cdf(0.80)
    assert a.n_paris(1.0, 0.03, 0.05) == math.ceil((z / 0.03) ** 2)
    assert a.n_paris(1.0, 0.03, 0.05, effet_plan=2.0) == math.ceil(2 * (z / 0.03) ** 2)
    assert a.n_paris(1.0, 0.03, 0.05, unilateral=False) > a.n_paris(1.0, 0.03, 0.05)
    assert math.isclose(a.kelly(0.02, 2.0), 0.02) and math.isclose(a.kelly(0.02, 3.0), 0.01)
    assert a.kelly(-0.01, 2.0) == 0.0 and a.kelly(0.05, 1.0) == 0.0


def test_rythme_compte_les_paris_de_la_regle_par_jour_de_paris():
    paris = [pari(i, match=f"m{i}", detecte=datetime(2026, 11, 16 + i % 7, 10, tzinfo=timezone.utc)) for i in range(14)]
    paris.append(pari(99, match="w", bookmaker="Winamax", detecte=datetime(2026, 11, 18, 10, tzinfo=timezone.utc)))
    r = a.rythme(paris, datetime(2026, 11, 23, 12, tzinfo=timezone.utc))
    assert (r["du"], r["au"]) == ("2026-11-16", "2026-11-22")
    assert r["detail"] == [2] * 7 and r["par_jour"] == 2.0


def test_tests_anterieurs_cites_mot_pour_mot():
    for doc, phrase, n in a.TESTS_ANTERIEURS:
        assert phrase in (RACINE / doc).read_text(encoding="utf-8"), (doc, phrase)
        assert str(n) in phrase


def test_rapport_publie_et_reproductible():
    texte = (RACINE / "docs" / "audit-26-11-strategie.md").read_text(encoding="utf-8")
    assert "python etudes/audit_26_11.py --donnees" in texte
    assert f"graine {a.GRAINE}" in texte
