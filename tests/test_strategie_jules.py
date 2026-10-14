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
        "detecte": "2026-10-15T10:00:00Z",
        "debut": "2026-10-15T12:00:00Z",
        "lu_reference": "2026-10-15T09:58:00Z",
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
    assert motif_refus_jules(_pari_base(detecte="2026-10-15T11:50:00Z")) == "détection hors fenêtre de 15 minutes à 12 heures"


def test_paris_jules_unicite_match_et_cap_journalier():
    pari1 = _pari_base(id=1, cote=2.0)
    pari2 = _pari_base(id=2, cote=2.1, cote_juste=2.1/1.1, bookmaker="Unibet")  # Même match m123

    paris = [pari1, pari2]
    assert all(motif_refus_jules(p) is None for p in paris)
    sel = paris_jules(paris)
    assert len(sel) == 1
    assert id(pari2) in sel  # À détection et edge égaux, la cote la plus haute.


def test_paris_jules_cap_journalier_maximum_6():
    paris = []
    for i in range(10):
        p = _pari_base(
            id=i + 1,
            detecte=f"2026-10-15T08:1{i}:00Z",
            debut=f"2026-10-15T12:1{i}:00Z",
            lu_reference=f"2026-10-15T08:1{i}:00Z",
            preuve_prise={
                "ressemblance_noms": 0.95,
                "match_id_reference": f"match_{i}",
                "controle": {"statut": "conforme"},
            },
        )
        paris.append(p)

    sel = paris_jules(paris)
    assert len(sel) == 6


def test_lancement_exclut_le_passe_sauf_rejeu_explicite():
    from cotes.strategie_jules import DEBUT_REJEU
    avant = _pari_base(detecte="2026-10-14T21:04:12Z", lu_reference="2026-10-14T21:04:12Z",
                       debut="2026-10-15T01:00:00Z")
    apres = _pari_base(id=101, detecte=JULES["debut"], lu_reference=JULES["debut"],
                       debut="2026-10-15T01:00:00Z")
    assert motif_refus_jules(avant) is not None
    assert motif_refus_jules(apres) is None
    assert paris_jules([avant, apres]) == {id(apres)}
    assert paris_jules([avant], depuis=DEBUT_REJEU) == {id(avant)}


def test_resultats_clv_et_ajouts_tardifs_ne_changent_pas_les_choix():
    p = _pari_base(id="p", match_id="book|p")
    assert paris_jules([p]) == {id(p)}
    p.update(statut="perdu", gain=-10, clv=-.9)
    futur = {**p, "id": "q", "detecte": "2026-10-15T10:01:00Z"}
    assert paris_jules([futur, p]) == {id(p)}
    p.update(statut="gagne", gain=10, clv=.9)
    assert paris_jules([p, futur]) == {id(p)}


def _complet(pid="p", **kw):
    p = _pari_base(id=pid)
    p.update(match_id="winamax|"+pid, domicile="Equipe "+pid, exterieur="Adversaire "+pid,
             simulation="D", mise=10, statut="en_cours", gain=None, clv=None, pari="Victoire domicile")
    p["preuve_prise"] = {**p["preuve_prise"], "match_id_reference": pid}
    return {**p, **kw}


def test_plafond_se_reinitialise_a_minuit_paris():
    rows = [_complet(str(i), detecte=f"2026-10-15T21:{i:02d}:00Z",
                     lu_reference=f"2026-10-15T21:{i:02d}:00Z", debut="2026-10-16T02:00:00Z")
            for i in range(7)]
    lendemain = _complet("lendemain", detecte="2026-10-15T22:01:00Z",
                         lu_reference="2026-10-15T22:01:00Z", debut="2026-10-16T02:00:00Z")
    assert paris_jules(rows+[lendemain]) == {id(p) for p in rows[:6]+[lendemain]}


def test_navigation_jules_historique_separe_et_prix_exact():
    from scripts.site_web import navigation_strategies
    historique = _complet("ancien", detecte="2026-10-09T10:00:00Z", lu_reference="2026-10-09T10:00:00Z",
                           debut="2026-10-09T12:00:00Z", statut="gagne", gain=10)
    # Même fiche bookmaker : une première cote non admissible ne remplace pas
    # le prix sélectionné au moment où l'opportunité devient admissible.
    mauvaise = _complet("avant", cote=1.1, match_id="winamax|exact")
    bonne = _complet("exact", detecte="2026-10-15T10:01:00Z", match_id="winamax|exact")
    labo = {"releve":"2026-10-14T10:09:28Z", "resultats":[],
            "comparateurs":{"JULES EDGE v1 (rejeu)":{}}}
    nav = navigation_strategies([historique, mauvaise, bonne], labo, "2026-10-16T00:00:00Z")
    sel = nav["selections"]["JULES EDGE v1 (rejeu)"]
    assert sel["ensemble"] == ["ancien"] and sel["futur"] == ["exact"]
    assert nav["paris"]["exact"]["cote"] == 2 and nav["paris"]["exact"]["jules"]
    assert not nav["paris"]["ancien"]["jules"]


def test_bilans_courbes_et_cartes_jules_identiques(tmp_path, monkeypatch):
    from copy import deepcopy
    from datetime import datetime, timezone
    import json
    import re
    from cotes.simulation import bilan, bilan_bookmakers, bilan_tranches
    from scripts import site_web

    class Horloge(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 16, tzinfo=timezone.utc)

    monkeypatch.setattr(site_web, "datetime", Horloge)
    rows = [_complet("g", statut="gagne", gain=10, regle_le="2026-10-15T15:00:00Z"),
            _complet("p", statut="perdu", gain=-10, regle_le="2026-10-15T15:00:00Z")]
    avant = deepcopy(rows)
    assert bilan(rows)["D|JULES EDGE"]["regles"] == 2
    assert bilan(rows)["D|Toutes"]["regles"] == 2  # Pas de duplication des mises.
    assert bilan_bookmakers(rows)["Winamax·D|JULES EDGE"]["gains"] == 0
    assert bilan_tranches(rows)["1,51 – 2,00|JULES EDGE"]["regles"] == 2
    assert sum(p[1] for p in site_web.courbes(rows)["JULES EDGE"]) == 0
    assert all(p["jules"] for p in site_web.selection_paris(rows)[0])
    (tmp_path/"paris.json").write_text(json.dumps(rows))
    h = site_web.construire(tmp_path, tmp_path/"site").read_text()
    d = json.loads(re.search(r"const D = (\{.*?\});\n",h,re.S).group(1).replace("<\\/","</"))
    assert d["laboratoire"]["comparateurs_futur"]["JULES EDGE v1 (rejeu)"]["regles"] == 2
    assert d["laboratoire"]["navigation"]["selections"]["JULES EDGE v1 (rejeu)"]["futur"] == ["g","p"]
    assert d["bilan"]["D|JULES EDGE"]["gains"] == 0
    assert rows == avant


def test_rapport_bloque_les_doublons_et_ne_compte_pas_de_reglement_futur():
    import pytest
    from scripts.verifier_strategie_jules import rapport
    p = _complet("ancien", detecte="2026-10-09T10:00:00Z", lu_reference="2026-10-09T10:00:00Z",
                 debut="2026-10-09T12:00:00Z", statut="gagne", gain=10, regle_le="2026-10-10T00:00:00Z")
    r = rapport([p], "2026-10-09T18:00:00Z")
    assert r["ids_selections"] == ["ancien"]
    assert r["ensemble"]["regles"] == 0 and r["ensemble"]["attente"] == 1
    with pytest.raises(ValueError, match="dupliqués"):
        rapport([p,p], "2026-10-09T18:00:00Z")
    with pytest.raises(ValueError, match="Relevé invalide"):
        rapport([p], "2026-10-09T18:00:00")
