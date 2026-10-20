"""Intégration des comparateurs, export complet, clôtures et segments par référence."""
import json
import re

from cotes.convergence import selections
from cotes.laboratoire import resume
from cotes.simulation import segments
from scripts import site_web
from tests.test_strategie_jules_v2 import pari


def donnees_html(html):
    return json.loads(re.search(r"const D = (\{.*?\});\n", html, re.S).group(1).replace("<\\/", "</"))


def test_ancien_json_sans_nouveaux_comparateurs(tmp_path, monkeypatch):
    p=pari("avant", detecte="2026-10-09T09:00:00Z", lu_reference="2026-10-09T09:00:00Z",
           debut="2026-10-09T12:00:00Z", statut="gagne", gain=11, regle_le="2026-10-09T15:00:00Z")
    # Un règlement connu seulement après la coupure de construction doit rester en attente.
    tard=pari("tard", detecte="2026-10-09T09:01:00Z", lu_reference="2026-10-09T09:00:00Z",
              debut="2026-10-09T12:00:00Z", statut="perdu", gain=-10, regle_le="2026-10-12T12:00:00Z")
    (tmp_path/"paris.json").write_text(json.dumps([p,tard]))
    original=site_web._lire
    def lire(path, default):
        if path.name == "comparaison-strategies.json":
            return {"releve":"2026-10-14T10:09:28Z", "resultats":[], "comparateurs":{}}
        if path.name in ("strategie-m3.json","strategie-jules-v2.json"):
            return {}
        return original(path,default)
    monkeypatch.setattr(site_web,"_lire",lire)
    d=donnees_html(site_web.construire(tmp_path,tmp_path/"site").read_text())
    labo=d["laboratoire"]; nav=labo["navigation"]
    assert len(labo["comparateurs"]) == 12
    for nom, comp in labo["comparateurs"].items():
        for periode, stats in comp.items():
            pts=nav["courbes"][nom][periode]
            assert len(pts) == stats["regles"]
            assert (pts[-1][1] if pts else 0) == stats["gain"]
    assert labo["comparateurs"]["Convergence ≥ 2"]["ensemble"]["paris"] == 2
    assert labo["comparateurs"]["Convergence ≥ 2"]["construction"]["attente"] == 1
    assert not labo["comparateurs_futur"]["Convergence ≥ 2"]["paris"]
    assert nav["paris"]["avant"]["convergence_historique"]
    assert nav["paris"]["avant"]["tranche"] == "2,01 – 3,00"


def test_catalogue_complet_prix_clv_et_strategies_exacts():
    rows=[pari(str(i),statut="perdu",gain=-10,regle_le="2026-10-15T14:00:00Z",clv=.9)
          for i in range(650)]
    # La CLV courante ne doit pas se transformer en CLV de clôture sans preuve.
    data=site_web.catalogue_paris(rows,selections(rows))
    copies=[dict(zip(data["champs"],r)) for r in data["lignes"]]
    assert len(copies) == 650 and all(p["clv"] is None for p in copies)
    assert copies[0]["cote"] == 2.1 and copies[0]["simulation"] == "D"
    assert sum("jules_v2" in p["strategies"] for p in copies) == 8
    assert sum(p["convergence"] for p in copies) > 0


def test_segments_reference_dedup_et_depliage():
    rows=[]
    for i in range(40):
        p=pari(str(i),reference="Pinnacle" if i%2 else "Betfair",cote=2.0 if i%4<2 else 2.1,
               cote_juste=1.9,statut="gagne",gain=10 if i%4<2 else 11)
        rows.append(p)
        rows.append({**p,"id":"dup"+str(i),"reference":"Polymarket","detecte":"2026-10-15T09:01:00Z"})
    resultat=segments(rows)
    pin=next(s for s in resultat if s.get("reference")=="Pinnacle" and "tranche" not in s)
    assert pin["n"] == 20 and pin["gains"] == 210
    assert all(s["n"] >= 10 for s in resultat)
    assert not any(s.get("reference")=="Polymarket" for s in resultat)
    compact=site_web.paris_des_segments(rows)
    assert len(compact)==40
    assert sum(x[11]==pin["reference"] for x in compact)==pin["n"]
    futur=[{**p,"statut":"en_cours","debut":"2099-10-15T12:00:00Z"} for p in rows]
    assert sum(x[11]=="Pinnacle" for x in site_web.paris_a_venir_des_segments(futur))==20


def test_courbe_meme_calcul_que_resume_demi_gagnes_rembourses():
    rows=[pari(str(i),statut=statut,regle_le=f"2026-10-15T15:0{i}:00Z",gain=999)
          for i,statut in enumerate(("gagne","demi_gagne","perdu","demi_perdu","rembourse"))]
    cutoff="2026-10-15T16:00:00Z"
    points=site_web.courbe_comparateur(rows,cutoff)
    assert len(points)==5 and points[-1][1]==resume(rows,cutoff,incertitude=False)["gain"]


def test_m3_archive_descriptive_est_alignee_sur_coupure_commune():
    p=pari("m3",sport="basket",cote=2.1,cote_juste=2,ecart=.05,
           detecte="2026-10-09T09:00:00Z",lu_reference="2026-10-09T09:00:00Z",
           debut="2026-10-09T12:00:00Z",statut="gagne",gain=11,regle_le="2026-10-12T12:00:00Z")
    labo={"releve":"2026-10-14T10:09:28Z","comparateurs":{"M3 (rejeu)":{
        "construction":{"regles":1,"gain":11}}}}
    site_web.enrichir_comparateurs([p],labo,"2026-10-15T00:00:00Z")
    comp=labo["comparateurs"]["M3 (rejeu)"]
    assert comp["construction"]["regles"] == 0 and comp["construction"]["attente"] == 1
    assert comp["ensemble"]["regles"] == 1 and comp["ensemble"]["gain"] == 11


def test_analyses_reutilise_les_uniques_du_bilan_et_les_mises_enregistrees():
    premier=pari('premier',match_id='meme-match',mise=20,detecte='2026-10-15T09:00:00Z')
    autre=pari('autre-reference',match_id='meme-match',reference='Betfair',detecte='2026-10-15T09:01:00Z')
    data=site_web.catalogue_paris([autre,premier],{})
    rows=[dict(zip(data['champs'],r)) for r in data['lignes']]
    assert [p['id'] for p in rows if p['unique_bilan']] == ['premier']
    assert next(p['mise'] for p in rows if p['id']=='premier') == 20
