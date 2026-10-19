"""Invariants Eden : exposition par bookmaker, dates et vues du site."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import re

from cotes.strategie_eden import EDEN, motif_refus_eden, paris_eden


def pari(mid="m1", **changes):
    cote = 1.80
    p = {"id": mid, "match_id": "winamax|" + mid, "reference": "Pinnacle", "simulation": "C",
         "bookmaker": "Winamax", "sport": "football", "ligue": "Ligue 1",
         "domicile": "Paris " + mid, "exterieur": "Lyon " + mid, "marche": "TOTAL",
         "periode": "MATCH", "ligne": 2.5, "issue": "PLUS", "pari": "Plus de 2,5 buts",
         "detecte": "2026-10-19T18:30:00+00:00", "debut": "2026-10-19T22:00:00+00:00",
         "lu_reference": "2026-10-19T18:25:00+00:00",
         "cote": cote, "cote_juste": cote / 1.04, "ecart": 0.04, "mise": 10,
         "statut": "en_cours", "gain": None, "clv": None,
         "preuve_prise": {"match_id_reference": mid, "ressemblance_noms": .9,
                          "controle": {"statut": "conforme"}}}
    return {**p, **changes}


def test_chaque_bookmaker_du_meme_match_est_joue():
    premier = pari(domicile="Paris", exterieur="Lyon")
    pmu = pari("pmu", bookmaker="PMU", domicile="Lyon", exterieur="Paris",
               detecte="2026-10-19T18:31:00+00:00")
    betclic = pari("bet", bookmaker="Betclic", detecte="2026-10-19T18:32:00+00:00")
    assert paris_eden([betclic, pmu, premier]) == {id(premier), id(pmu), id(betclic)}


def test_deux_references_du_meme_bookmaker_restent_une_mise():
    premier = pari(domicile="Paris", exterieur="Lyon")
    autre = pari(domicile="Paris", exterieur="Lyon", reference="Polymarket",
                 detecte="2026-10-19T18:31:00+00:00")
    autre = {**autre, "id": "poly",
             "preuve_prise": {**autre["preuve_prise"], "match_id_reference": "poly1"}}
    assert paris_eden([autre, premier]) == {id(premier)}


def test_cote_ecartee_ne_bloque_pas_un_autre_bookmaker():
    premier = pari(domicile="PSG", exterieur="OL")
    pont = pari(ecart=0.20, detecte="2026-10-19T18:31:00+00:00")
    pont = {**pont, "id": "pont", "preuve_prise": {**pont["preuve_prise"], "match_id_reference": "autre"}}
    pmu = {**pont, "id": "pmu", "bookmaker": "PMU", "match_id": "pmu|different", "ecart": 0.04,
           "detecte": "2026-10-19T18:32:00+00:00"}
    assert motif_refus_eden(pont) is not None
    assert paris_eden([pmu, pont, premier]) == {id(premier), id(pmu)}


def test_resultats_ne_rechoisissent_pas_le_passe():
    p, q = pari(), pari("q", detecte="2026-10-19T18:31:00+00:00")
    avant = deepcopy([p, q])
    assert paris_eden([p, q]) == {id(p), id(q)}
    p.update(statut="perdu", gain=-10, clv=-.7, regle_le="2026-10-19T23:00:00+00:00")
    q.update(statut="gagne", gain=8, clv=.7, regle_le="2026-10-19T23:00:00+00:00")
    assert paris_eden([q, p]) == {id(p), id(q)}
    assert avant[0]["statut"] == "en_cours"


def test_pas_de_plafond_journalier():
    rows = [pari(str(i), detecte=f"2026-10-19T18:{30+i:02d}:00+00:00",
                 lu_reference=f"2026-10-19T18:{30+i:02d}:00+00:00")
            for i in range(8)]
    assert paris_eden(rows) == {id(p) for p in rows}
    assert "paris_max_jour" not in EDEN


def test_historique_exclu_et_bornes():
    ancien = pari(detecte="2026-10-19T17:59:00+00:00", lu_reference="2026-10-19T17:50:00+00:00",
                  debut="2026-10-19T20:00:00+00:00")
    assert not paris_eden([ancien])
    assert paris_eden([ancien], depuis="2026-10-07T00:00:00+00:00") == {id(ancien)}
    assert motif_refus_eden(pari(cote=2.01, cote_juste=2.01 / 1.04)) is not None
    assert motif_refus_eden(pari(cote=2.00, cote_juste=2.00 / 1.04)) is None
    assert motif_refus_eden(pari(cote=1.29, cote_juste=1.29 / 1.04)) is not None
    assert motif_refus_eden(pari(ecart=0.019, cote_juste=1.80 / 1.019)) is not None
    assert motif_refus_eden(pari(ecart=0.12, cote_juste=1.80 / 1.12)) is None
    assert motif_refus_eden(pari(ecart=0.121, cote_juste=1.80 / 1.121)) is not None
    assert motif_refus_eden(pari(reference="Betfair")) is not None
    assert motif_refus_eden(pari(reference="Polymarket")) is None
    assert motif_refus_eden(pari(bookmaker="OlyBet")) is not None
    assert motif_refus_eden(pari(suspect=True)) is not None
    assert motif_refus_eden(pari(ligne=2.25)) is not None
    assert motif_refus_eden(pari(lu_reference="2026-10-19T18:14:59+00:00")) is not None
    assert motif_refus_eden(pari(debut="2026-10-19T18:59:00+00:00")) is not None
    assert motif_refus_eden(pari(debut="2026-10-20T18:31:00+00:00")) is not None
    assert motif_refus_eden(pari(debut="2026-10-19T19:00:00+00:00")) is None
    assert motif_refus_eden(pari(debut="2026-10-20T18:30:00+00:00")) is None
    assert motif_refus_eden(pari(sport="tennis", marche="TOTAL")) is not None
    assert motif_refus_eden(pari(sport="tennis", marche="VAINQUEUR", issue="DOM", ligne=None)) is None
    assert motif_refus_eden(pari(domicile="Paris U19")) is not None
    assert motif_refus_eden(pari(ligue="Ligue 1 féminine")) is None
    assert motif_refus_eden(pari()) is None


def test_bilan_courbe_fiches_et_navigation(tmp_path, monkeypatch):
    from cotes.simulation import bilan, bilan_bookmakers, bilan_tranches
    from scripts import site_web

    class Horloge(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 19, 23, tzinfo=timezone.utc)

    monkeypatch.setattr(site_web, "datetime", Horloge)
    rows = [pari("alpha", statut="gagne", gain=8, regle_le="2026-10-19T22:30:00+00:00"),
            pari("bravo", statut="perdu", gain=-10, regle_le="2026-10-19T22:40:00+00:00")]
    avant = deepcopy(rows)
    b = bilan(rows)
    assert b["C|Eden"]["regles"] == 2 and b["C|Eden"]["gains"] == -2
    assert bilan_bookmakers(rows)["Winamax·C|Eden"]["gains"] == -2
    assert bilan_tranches(rows)["1,51 – 2,00|Eden"]["regles"] == 2
    assert sum(p[1] for p in site_web.courbes(rows)[EDEN["nom"]]) == -2
    assert all(p["eden"] for p in site_web.selection_paris(rows)[0])
    (tmp_path / "paris.json").write_text(json.dumps(rows))
    html = site_web.construire(tmp_path, tmp_path / "site").read_text()
    assert 'id="eden-picks"' in html and 'id="voir-eden"' in html
    data = json.loads(re.search(r"const D = (\{.*?\});\n", html, re.S).group(1).replace("<\\/", "</"))
    assert data["eden"]["debut"] == EDEN["debut"]
    assert data["bilan"]["C|Eden"]["gains"] == -2
    assert data["laboratoire"]["comparateurs_futur"]["Eden (rejeu)"]["regles"] == 2
    assert data["laboratoire"]["navigation"]["selections"]["Eden (rejeu)"]["futur"] == ["alpha", "bravo"]
    assert data["laboratoire"]["eden_paris"]
    assert rows == avant


def test_navigation_exclut_lavant_lancement_du_suivi():
    from scripts.site_web import navigation_strategies
    ancien = pari("ancien", detecte="2026-10-09T10:00:00+00:00", lu_reference="2026-10-09T09:55:00+00:00",
                  debut="2026-10-09T12:00:00+00:00", statut="gagne", gain=8, regle_le="2026-10-09T15:00:00+00:00")
    officiel = pari("officiel")
    labo = {"releve": "2026-10-14T10:09:28+00:00", "resultats": [],
            "comparateurs": {"Eden (rejeu)": {}}}
    nav = navigation_strategies([ancien, officiel], labo, "2026-10-19T23:00:00+00:00")
    sel = nav["selections"]["Eden (rejeu)"]
    assert sel["ensemble"] == ["ancien"]
    assert sel["futur"] == ["officiel"]
    assert nav["paris"]["officiel"]["eden"]
    assert not nav["paris"]["ancien"]["eden"]


def test_reference_lue_apres_la_detection_francaise_reste_acceptee_dans_la_fenetre():
    # détection 18:30, Pinnacle relu 9 min 31 s plus tard : le livre français est relu moins souvent
    assert motif_refus_eden(pari(lu_reference="2026-10-19T18:39:31+00:00")) is None
    assert motif_refus_eden(pari(lu_reference="2026-10-19T18:45:01+00:00")) is not None
