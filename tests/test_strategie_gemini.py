"""Invariants Gemini : exposition par événement, dates et cohérence des vues."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import re

from cotes.strategie_gemini import GEMINI, motif_refus_gemini, paris_gemini


def pari(mid="m1", **changes):
    p = {"id": mid, "match_id": "winamax|" + mid, "reference": "Pinnacle", "simulation": "D",
         "bookmaker": "Winamax", "sport": "football", "ligue": "Ligue 1", "domicile": "Paris " + mid,
         "exterieur": "Lyon " + mid, "marche": "TOTAL", "periode": "MATCH", "ligne": 2.5, "issue": "PLUS",
         "pari": "Plus de 2,5 buts", "detecte": "2026-10-14T18:00:00Z",
         "debut": "2026-10-14T21:00:00Z", "lu_reference": "2026-10-14T18:00:00Z",
         "cote": 2.1, "cote_juste": 2.0, "ecart": .05, "mise": 10,
         "statut": "en_cours", "gain": None, "clv": None,
         "preuve_prise": {"match_id_reference": mid, "ressemblance_noms": .9,
                          "controle": {"statut": "conforme"}}}
    return {**p, **changes}


def test_chaque_bookmaker_du_meme_match_est_joue():
    premier = pari(domicile="Paris", exterieur="Lyon")
    pmu = pari("pmu", bookmaker="PMU", reference="Polymarket", domicile="Lyon", exterieur="Paris",
               detecte="2026-10-14T18:01:00Z")
    betclic = pari("bet", bookmaker="Betclic", detecte="2026-10-14T18:02:00Z")
    assert paris_gemini([betclic, pmu, premier]) == {id(premier), id(pmu), id(betclic)}


def test_deux_references_du_meme_bookmaker_restent_une_mise():
    premier = pari(domicile="Paris", exterieur="Lyon")
    autre_ref = pari(reference="Polymarket", detecte="2026-10-14T18:01:00Z",
                     domicile="Paris", exterieur="Lyon")
    autre_ref = {**autre_ref, "id": "poly",
                 "preuve_prise": {**autre_ref["preuve_prise"], "match_id_reference": "poly1"}}
    assert paris_gemini([autre_ref, premier]) == {id(premier)}


def test_cote_ecartee_ne_bloque_pas_un_autre_bookmaker():
    premier = pari(domicile="PSG", exterieur="OL")
    pont = pari(reference="Polymarket", ecart=0.20, detecte="2026-10-14T18:01:00Z")
    pont = {**pont, "id": "pont", "preuve_prise": {**pont["preuve_prise"], "match_id_reference": "poly"}}
    pmu = {**pont, "id": "pmu", "bookmaker": "PMU", "match_id": "pmu|different", "ecart": 0.05,
           "detecte": "2026-10-14T18:02:00Z"}
    assert motif_refus_gemini(pont) is not None
    assert paris_gemini([pmu, pont, premier]) == {id(premier), id(pmu)}


def test_resultats_et_ajouts_futurs_ne_rechoisissent_pas_le_passe():
    p=pari()
    q=pari("q", detecte="2026-10-14T18:01:00Z")
    avant=deepcopy([p,q])
    assert paris_gemini([p,q]) == {id(p),id(q)}
    p.update(statut="perdu",gain=-10,clv=-.7)
    q.update(statut="gagne",gain=11,clv=.7)
    assert paris_gemini([q,p]) == {id(p),id(q)}
    nouveau={**p,"id":"plus_tard","detecte":"2026-10-14T18:02:00Z"}
    assert paris_gemini([q,p,nouveau]) == {id(p),id(q)}
    assert avant[0]["statut"] == "en_cours"


def test_plafond_8_et_changement_de_jour_paris():
    rows=[]
    for i in range(9):
        t=(datetime(2026,10,14,18,tzinfo=timezone.utc)+timedelta(minutes=i)).isoformat()
        rows.append(pari(str(i),detecte=t,lu_reference=t))
    suivant=pari("jour2",detecte="2026-10-14T22:01:00Z",lu_reference="2026-10-14T22:01:00Z",
                 debut="2026-10-15T01:00:00Z")
    assert paris_gemini(rows+[suivant]) == {id(p) for p in rows[:8]+[suivant]}


def test_historique_exclu_et_bornes_reference():
    p=pari(detecte="2026-10-14T17:59:00Z",lu_reference="2026-10-14T17:59:00Z")
    assert not paris_gemini([p])
    assert paris_gemini([p],depuis="2026-10-07T00:00:00Z") == {id(p)}
    assert motif_refus_gemini(pari(cote=2.16,cote_juste=2.16/1.05)) is not None
    assert motif_refus_gemini(pari(reference="Betfair",cote=2.6,cote_juste=2.6/1.05)) is None
    assert motif_refus_gemini(pari(ligne=2.25)) is not None
    assert motif_refus_gemini(pari(lu_reference="2026-10-14T17:49:59Z")) is not None


def test_bilan_courbe_et_fiches_memes_selections(tmp_path):
    from cotes.simulation import bilan,bilan_bookmakers,bilan_tranches
    from scripts.site_web import construire,courbes,selection_paris
    rows=[pari("alpha",statut="gagne",gain=11,regle_le="2026-10-14T23:00:00Z"),
          pari("bravo",statut="perdu",gain=-10,regle_le="2026-10-14T23:00:00Z")]
    avant=deepcopy(rows)
    b=bilan(rows)
    assert b["D|Gemini Argon"]["regles"] == 2 and b["D|Gemini Argon"]["gains"] == 1
    assert b["D|Toutes"]["regles"] == 2
    assert bilan_bookmakers(rows)["Winamax·D|Gemini Argon"]["gains"] == 1
    assert bilan_tranches(rows)["2,01 – 3,00|Gemini Argon"]["regles"] == 2
    assert sum(p[1] for p in courbes(rows)[GEMINI["nom"]]) == 1
    assert all(p["gemini"] for p in selection_paris(rows)[0])
    (tmp_path/"paris.json").write_text(json.dumps(rows))
    h=construire(tmp_path,tmp_path/"site").read_text()
    d=json.loads(re.search(r"const D = (\{.*?\});\n",h,re.S).group(1).replace("<\\/","</"))
    assert d["bilan"]["D|Gemini Argon"]["gains"] == 1
    assert rows == avant
