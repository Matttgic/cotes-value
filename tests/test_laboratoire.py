"""Sélection causale, limites temporelles, règlements et décision figée."""
from copy import deepcopy

import pytest

from cotes.laboratoire import (REGLES, Regle, audit, classer, evaluer, intervalle_roi,
                               resume, selectionner, suivi_futur)

R = Regle("test", "Pinnacle", 1.3, 3, .02, 36)


def pari(id="a", **changes):
    return {"id": id, "match_id": "book|"+id, "reference": "Pinnacle", "bookmaker": "Winamax",
            "sport": "football", "marche": "TOTAL", "periode": "MATCH", "ligne": 2.5, "issue": "PLUS",
            "detecte": "2026-10-10T18:00:00Z", "debut": "2026-10-10T20:00:00Z",
            "lu_reference": "2026-10-10T17:59:00Z", "cote": 2.1, "cote_juste": 2.0, "ecart": .05,
            "statut": "gagne", "gain": 11, "mise": 10, "regle_le": "2026-10-10T21:59:00Z",
            "preuve_prise": {"match_id_reference": id, "ressemblance_noms": .9,
                              "controle": {"statut": "conforme"}}, **changes}


def test_famille_figee_et_selection_sans_resultat():
    assert len(REGLES) == len({r.id for r in REGLES}) == 24
    assert {r.reference for r in REGLES} == {"Pinnacle", "Polymarket"}
    p = pari()
    later = {**p, "id": "b", "detecte": "2026-10-10T18:01:00Z", "ecart": .10, "cote": 2.2}
    assert [p["id"] for p in selectionner([later, p], R)] == ["a"]
    p.update(statut="perdu", gain=-10, clv=-.9, regle_le=None)
    later.update(statut="gagne", gain=12, clv=.9)
    assert [p["id"] for p in selectionner([later, p], R)] == ["a"]


def test_cote_et_edge_textuels_ne_font_pas_planter_la_selection():
    p = pari(cote="2.10", ecart="0.05", cote_juste="2.0")
    assert selectionner([p], R) == [p]


def test_un_match_plusieurs_books_et_egalite_deterministe():
    a = pari()
    b = {**a, "id": "b", "bookmaker": "PMU", "ecart": .06, "cote": 2.12}
    assert selectionner([a, b], R) == selectionner([b, a], R) == [b]


@pytest.mark.parametrize("changes", [
    {"ecart": float("nan")}, {"cote": float("inf")}, {"ligne": 2.25},
    {"lu_reference": "2026-10-10T17:44:59Z"}, {"lu_reference": "2026-10-10T18:15:01Z"},
    {"detecte": "2026-10-10T18:00:00"}, {"preuve_prise": {}}, {"cote_juste": 3},
    {"issue": "YES"}, {"periode": "MT1"}, {"sport": "tennis"}, {"reference": "Pinnacle brut"},
])
def test_qualite_avant_resultat(changes):
    assert not selectionner([pari(**changes)], R)


def test_reglement_a_la_coupure_reste_en_attente_et_roi_denominateur():
    a = pari()
    b = pari("b", statut="perdu", gain=-10, regle_le="2026-10-10T22:00:00Z")
    s = resume([a, b], "2026-10-11T00:00:00+02:00")
    assert (s["regles"], s["attente"], s["mise"], s["gain"], s["roi"]) == (1, 1, 10, 11, 110)
    assert s["roi_attente_pessimiste"] == 5
    assert s["roi_attente_optimiste"] == 110


def test_clv_absente_ne_devient_pas_zero_et_limite_30_minutes():
    a = pari(clv=.04, cloture_lue="2026-10-10T19:30:00Z")
    b = pari("b", clv=.9, cloture_lue="2026-10-10T19:29:59Z")
    s = resume([a, b], "2026-10-12T00:00:00Z")
    assert (s["clv"], s["clv_n"], s["couverture_clv"]) == (4, 1, 50)
    assert resume([pari()], "2026-10-12T00:00:00Z")["clv"] is None


def test_coupure_paris_et_aucun_resultat_futur_pour_construction():
    a = pari(regle_le="2026-10-11T01:00:00Z")
    b = pari("b", debut="2026-10-10T22:00:00Z", regle_le="2026-10-11T01:00:00Z")
    s = evaluer([a, b], "2026-10-14T10:09:28Z")
    assert s["construction"]["paris"] == s["construction"]["attente"] == 1
    assert s["validation"]["paris"] == s["validation"]["regles"] == 1


def test_resultat_test_ne_choisit_jamais_la_candidate():
    def score(roi=5, n=20, borne=-10):
        return {"roi": roi, "regles": n, "clv": 1, "couverture_clv": 60, "ic95": [borne, 20]}
    rows = [{"regle": {"id": id}, "construction": score(), "validation": score(borne=borne), "test": score()}
            for id, borne in (("a", -1), ("b", -5))]
    assert classer(rows)["candidate"] == "a"
    rows[0]["test"] = score(-99)
    rows[1]["test"] = score(200)
    d = classer(rows)
    assert d["candidate"] == "a" and not d["test_reussi"]
    assert not d["rentabilite_demontree"]
    for row in rows:
        row["construction"] = score(n=19)
    assert classer(rows)["candidate"] is None


def test_suivi_futur_exclut_ancien_et_futur_et_ne_modifie_pas_source():
    rows = [pari(), pari("b", detecte="2026-10-10T18:01:00Z"),
            pari("c", detecte="2026-10-10T18:02:00Z")]
    avant = deepcopy(rows)
    result = suivi_futur(rows, "2026-10-10T18:01:00Z", "2026-10-10T18:02:00Z")
    r = next(r for r in result if r["id"] == "PIN-1.5-3-e2-h36")
    assert r["paris"] == r["attente"] == 1 and r["ids_recents"] == ["b"]
    assert rows == avant


def test_audit_bloque_incoherence_et_geres_dates_invalides():
    from scripts.comparer_strategies import comparer
    with pytest.raises(ValueError, match="Audit bloquant"):
        comparer([pari(gain=99)], "2026-10-14T10:00:00Z")
    assert audit([pari(detecte="invalide")])["dates_reglement_invalides"] == ["a"]
    assert audit([])["lignes"] == 0


def test_bootstrap_reproductible_et_une_observation_non_estimable():
    assert intervalle_roi([1]) is None
    a = intervalle_roi([1.1, -1, 0, .4], repetitions=500)
    assert a == intervalle_roi([1.1, -1, 0, .4], repetitions=500)
    assert a[0] < 0 < a[1]


def test_gains_pertes_et_net_excluent_les_attentes():
    s = resume([pari(), pari("b", statut="perdu", gain=-10),
                pari("c", statut="demi_gagne", gain=5.5),
                pari("d", statut="en_cours", gain=None, regle_le=None)], "2026-10-12T00:00:00Z")
    assert (s["gains_bruts"], s["pertes_brutes"], s["gain"]) == (16.5, 10, 6.5)
    assert s["gains_bruts"] - s["pertes_brutes"] == s["gain"]
    assert (s["paris"], s["regles"], s["attente"], s["gagnes"]) == (4, 3, 1, 2)


def test_ensemble_inclut_reglements_tardifs_sans_changer_decision():
    from scripts.comparer_strategies import comparer
    p = pari(regle_le="2026-10-11T01:00:00Z")
    r = comparer([p], "2026-10-14T10:09:28Z")
    x = next(r for r in r["resultats"] if r["regle"]["id"] == "PIN-1.5-3-e2-h36")
    assert x["construction"]["regles"] == 0 and x["construction"]["attente"] == 1
    assert x["ensemble"]["regles"] == 1 and x["ensemble"]["gain"] == 11
    assert r["decision"]["candidate"] is None


def test_site_strategies_et_comparateurs_meme_date(tmp_path, monkeypatch):
    import json
    import re
    from datetime import datetime, timezone
    from scripts import site_web

    class Horloge(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 14, 18, tzinfo=timezone.utc)

    monkeypatch.setattr(site_web, "datetime", Horloge)
    rows = [pari("ancien", simulation="D"), pari("nouveau", simulation="D",
            detecte="2026-10-14T12:01:00Z", lu_reference="2026-10-14T12:00:00Z",
            debut="2026-10-14T15:00:00Z", regle_le="2026-10-14T17:00:00Z")]
    (tmp_path / "paris.json").write_text(json.dumps(rows))
    html = site_web.construire(tmp_path, tmp_path / "site").read_text()
    data = json.loads(re.search(r"const D = (\{.*?\});\n", html, re.S).group(1).replace("<\\/", "</"))
    assert 'data-bilan="strategies"' in html and 'id="o-strategies"' in html
    assert len(data["laboratoire"]["resultats"]) == 24
    for nom in ("Claude (rejeu)", "ChatGPT v1 (rejeu)"):
        s = data["laboratoire"]["comparateurs_futur"][nom]
        assert s["paris"] == s["regles"] == 1
        assert s["gain"] == s["gains_bruts"] == 11 and s["pertes_brutes"] == 0
    # M3 démarre le 15/10 : aucun pari du 14/10 ne doit être rétroactivement inclus.
    m3 = data["laboratoire"]["comparateurs_futur"]["M3 (rejeu)"]
    assert m3["paris"] == m3["regles"] == 0
    assert data["laboratoire"]["m3_paris"] == []


def test_reference_lue_apres_la_detection_francaise_reste_acceptee_dans_la_fenetre():
    """Betclic n'est relu que toutes les 34 min alors que Pinnacle l'est à chaque cycle : la lecture de
    référence peut suivre la cote française (Galatasaray, 19/10 : 18:19:16 contre 18:28:47)."""
    assert selectionner([pari(lu_reference="2026-10-10T18:09:31Z")], R)
    assert selectionner([pari(lu_reference="2026-10-10T18:15:00Z")], R)
    assert not selectionner([pari(lu_reference="2026-10-10T18:15:01Z")], R)


def test_redecision_unique_des_paris_ouverts_refuses_par_l_ancienne_regle():
    from datetime import datetime, timezone
    from cotes.decisions import REDECISION, redecider_ouverts

    now = datetime(2026, 10, 19, 19, 0, tzinfo=timezone.utc)
    base = dict(bookmaker="Betclic", detecte="2026-10-19T18:19:16Z", lu_reference="2026-10-19T18:28:47Z",
                debut="2026-10-20T17:00:00Z", cote=1.93, cote_juste=1.835, ecart=.0516, statut="en_cours",
                gain=None, regle_le=None, decide_le="2026-10-19T18:30:00+00:00", selections_figees={},
                registre_version="1")
    ouvert = pari("ouvert", **base)
    deja_joue = pari("joue", **{**base, "debut": "2026-10-19T18:45:00Z"})
    accepte = pari("accepte", **{**base, "selections_figees": {"labo:autre": {"version": "1"}}})
    paris = [ouvert, deja_joue, accepte]
    assert redecider_ouverts(paris, now) > 0
    assert "labo:PIN-1.3-2-e2-h36" in ouvert["selections_figees"] and ouvert[REDECISION]
    assert "labo:PIN-1.3-2-e2-h36" in ouvert["redecision_ajoutees"]                    # liste des ajouts (webhook)
    assert deja_joue["selections_figees"] == {} and REDECISION not in deja_joue      # match commencé : intact
    assert "labo:autre" in accepte["selections_figees"]                              # jamais de retrait
    figees = dict(ouvert["selections_figees"])
    assert redecider_ouverts(paris, now) == 0 and ouvert["selections_figees"] == figees   # une seule fois
    assert [p["id"] for p in selectionner(paris, next(r for r in REGLES if r.id == "PIN-1.3-2-e2-h36"),
                                          "2026-10-14T12:00:00+00:00")] == ["ouvert", "accepte"]
