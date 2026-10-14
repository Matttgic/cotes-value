"""Invariants de la reconstruction : identité, causalité, risque et suivi."""
from copy import deepcopy

import pytest

from cotes.strategie_jules_v2 import JULES_V2, analyser_jules_v2, motif_refus_jules_v2, paris_jules_v2


def pari(pid="alpha", **kw):
    p = {"id": pid, "match_id": "winamax|"+pid, "bookmaker": "Winamax", "reference": "Pinnacle",
         "sport": "football", "ligue": "France Ligue 1", "domicile": "Paris "+pid,
         "exterieur": "Lyon "+pid, "match_reference": "Paris "+pid+" - Lyon "+pid,
         "simulation": "D", "detecte": "2026-10-15T09:00:00Z", "debut": "2026-10-15T12:00:00Z",
         "lu_reference": "2026-10-15T08:59:00Z", "cote": 2.1, "cote_juste": 2, "ecart": .05,
         "marche": "VAINQUEUR", "periode": "MATCH", "ligne": None, "issue": "DOM",
         "pari": "Victoire domicile", "mise": 10, "statut": "en_cours", "gain": None,
         "preuve_prise": {"match_id_reference": pid, "ressemblance_noms": .95,
                          "controle": {"statut": "conforme"}}}
    return {**p, **kw}


def ref(p, fournisseur, rid):
    return {**p, "reference": fournisseur, "preuve_prise": {**p["preuve_prise"], "match_id_reference": rid}}


def test_deux_references_un_meme_match_ne_donnent_pas_deux_mises():
    p = pari()
    q = ref({**p, "id":"q", "detecte":"2026-10-15T09:01:00Z"}, "Polymarket", "poly")
    r = analyser_jules_v2([p,q])
    assert r["selection"] == {id(p)} and r["doublons_ecartes"] == 1


def test_alias_sur_cote_refusee_relie_aussi_un_autre_bookmaker():
    p = pari(domicile="PSG", exterieur="OL", match_reference="PSG - OL")
    pont = ref({**p, "id":"pont", "detecte":"2026-10-15T09:01:00Z", "ecart":.2}, "Polymarket", "poly")
    autre = {**pont, "id":"pmu", "bookmaker":"PMU", "match_id":"pmu|different", "ecart":.05,
             "domicile":"Paris Saint Germain", "exterieur":"Olympique Lyonnais", "match_reference":"",
             "detecte":"2026-10-15T09:02:00Z"}
    assert motif_refus_jules_v2(pont) is not None
    assert motif_refus_jules_v2(autre) is None
    assert paris_jules_v2([autre,pont,p]) == {id(p)}


def test_meme_numero_chez_deux_fournisseurs_ne_fusionne_pas_deux_matchs():
    p = ref(pari("alpha"), "Pinnacle", "123")
    q = ref(pari("bravo", detecte="2026-10-15T09:01:00Z"), "Polymarket", "123")
    assert paris_jules_v2([p,q]) == {id(p),id(q)}


def test_equipes_inversees_et_heures_equivalentes_fusionnent():
    p = pari()
    q = ref(pari("autre", bookmaker="PMU", match_id="pmu|9", domicile=p["exterieur"],
                 exterieur=p["domicile"], match_reference="", debut="2026-10-15T14:00:00+02:00",
                 detecte="2026-10-15T09:01:00Z"), "Betfair", "bet")
    assert paris_jules_v2([p,q]) == {id(p)}


@pytest.mark.parametrize("suffixe", [" Women", " U21", " II"])
def test_categories_distinctes_ne_sont_pas_fusionnees(suffixe):
    p = pari()
    q = ref(pari("autre", domicile=p["domicile"]+suffixe, exterieur=p["exterieur"]+suffixe,
                 match_reference="", detecte="2026-10-15T09:01:00Z"), "Betfair", "bet")
    assert paris_jules_v2([p,q]) == {id(p),id(q)}


def test_resultats_et_clv_n_interviennent_jamais():
    p = pari()
    avant = deepcopy(p)
    assert paris_jules_v2([p]) == {id(p)}
    p.update(statut="perdu", gain=-10, clv=-.9, regle_le="2026-10-15T15:00:00Z")
    q = {**p, "id":"tard", "detecte":"2026-10-15T09:01:00Z", "cote":2.2, "cote_juste":2.2/1.08, "ecart":.08}
    assert paris_jules_v2([q,p]) == {id(p)}
    assert avant["statut"] == "en_cours"


def test_fusion_tardive_est_signalee_sans_effacer_un_pari_passe():
    p = pari("alpha", match_reference="")
    q = ref(pari("bravo", detecte="2026-10-15T09:01:00Z", match_reference=""), "Betfair", "bet")
    pont = ref({**p, "id":"pont", "detecte":"2026-10-15T09:02:00Z"}, "Betfair", "bet")
    avant = paris_jules_v2([p,q])
    r = analyser_jules_v2([p,q,pont])
    assert avant == r["selection"] == {id(p),id(q)} and r["fusions_tardives"] == 1


def test_plafond_8_et_minuit_paris():
    rows = [pari("equipe"+str(i), detecte=f"2026-10-15T21:{i:02d}:00Z",
                  lu_reference=f"2026-10-15T21:{i:02d}:00Z", debut="2026-10-16T01:00:00Z") for i in range(9)]
    suivant = pari("suivant", detecte="2026-10-15T22:01:00Z", lu_reference="2026-10-15T22:00:00Z",
                   debut="2026-10-16T01:00:00Z")
    assert paris_jules_v2(rows+[suivant]) == {id(p) for p in rows[:8]+[suivant]}


def test_ancien_rejeu_exclu_du_suivi():
    p = pari(detecte="2026-10-14T22:29:59Z", lu_reference="2026-10-14T22:29:00Z", debut="2026-10-15T01:00:00Z")
    assert not paris_jules_v2([p])
    assert paris_jules_v2([p],depuis="2026-10-05T00:00:00Z") == {id(p)}
    q = {**p, "detecte":JULES_V2["debut"]}
    assert paris_jules_v2([q]) == {id(q)}


@pytest.mark.parametrize("kw", [{"cote":float("nan")}, {"ecart":float("inf")}, {"cote":True},
    {"lu_reference":"2026-10-15T09:01:00Z"}, {"lu_reference":"2026-10-15T08:54:59Z"},
    {"marche":"TOTAL","issue":"PLUS","ligne":2.25},
    {"sport":"tennis","periode":"TEMPS_REG"}, {"reference":"Pinnacle brut"}])
def test_donnees_ou_marches_invalides_refuses(kw):
    assert motif_refus_jules_v2(pari(**kw)) is not None


def test_departage_simultane_reste_deterministe():
    p = pari()
    q = {**p,"id":"q","cote":2.2,"cote_juste":2.2/1.05}
    assert paris_jules_v2([p,q]) == paris_jules_v2([q,p]) == {id(q)}


def test_bilan_courbe_cartes_navigation_et_prix_exact_coherents(tmp_path, monkeypatch):
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
    p = pari("alpha", statut="gagne", gain=11, regle_le="2026-10-15T15:00:00Z")
    q = pari("bravo", statut="perdu", gain=-10, regle_le="2026-10-15T15:00:00Z")
    alias = ref({**p, "id":"alias", "detecte":"2026-10-15T09:01:00Z"}, "Polymarket", "poly")
    ancien = pari("ancien", detecte="2026-10-14T22:00:00Z", lu_reference="2026-10-14T22:00:00Z",
                  debut="2026-10-15T03:00:00Z")
    # Une cote initiale non admissible ne doit pas masquer la sélection exacte.
    mauvaise = {**p, "id":"mauvaise", "cote":1.1, "detecte":"2026-10-15T08:58:00Z"}
    rows = [p,q,alias,ancien,mauvaise]
    avant = deepcopy(rows)
    assert bilan(rows)["D|JULES EDGE v2"]["regles"] == 2
    assert bilan(rows)["D|JULES EDGE v2"]["gains"] == 1
    assert bilan_bookmakers(rows)["Winamax·D|JULES EDGE v2"]["gains"] == 1
    assert bilan_tranches(rows)["2,01 – 3,00|JULES EDGE v2"]["regles"] == 2
    assert sum(x[1] for x in site_web.courbes(rows)["JULES EDGE v2"]) == 1
    (tmp_path/"paris.json").write_text(json.dumps(rows))
    h = site_web.construire(tmp_path,tmp_path/"site").read_text()
    d = json.loads(re.search(r"const D = (\{.*?\});\n",h,re.S).group(1).replace("<\\/","</"))
    nom = "JULES EDGE v2 (rejeu)"
    assert d["laboratoire"]["comparateurs_futur"][nom]["regles"] == 2
    assert d["laboratoire"]["navigation"]["selections"][nom]["futur"] == ["alpha","bravo"]
    assert d["laboratoire"]["navigation"]["paris"]["alpha"]["cote"] == 2.1
    assert d["laboratoire"]["navigation"]["paris"]["alpha"]["jules_v2"]
    assert rows == avant


def test_navigation_historique_distincte_du_lancement():
    from scripts.site_web import navigation_strategies
    p = pari("avant", detecte="2026-10-09T09:00:00Z", lu_reference="2026-10-09T08:59:00Z",
             debut="2026-10-09T12:00:00Z")
    q = pari("apres")
    nom = "JULES EDGE v2 (rejeu)"
    labo = {"releve":"2026-10-14T10:09:28Z", "resultats":[], "comparateurs":{nom:{}}}
    nav = navigation_strategies([p,q],labo,"2026-10-16T00:00:00Z")
    assert nav["selections"][nom]["ensemble"] == ["avant"]
    assert nav["selections"][nom]["futur"] == ["apres"]
    assert not nav["paris"]["avant"]["jules_v2"]


def test_mesure_du_risque_n_inclut_pas_les_reglements_futurs():
    from scripts.verifier_strategie_jules_v2 import mesures
    p = pari(statut="gagne",gain=11,regle_le="2026-10-15T15:00:00Z")
    s = mesures([p],"2026-10-15T14:00:00Z")
    assert s["regles"] == 0 and s["attente"] == 1 and s["gain"] == 0 and s["ic95_jours"] is None
    s = mesures([p],"2026-10-15T16:00:00Z")
    assert s["regles"] == 1 and s["gain"] == 11 and s["jours_regles"] == 1
