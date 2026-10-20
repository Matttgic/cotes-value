import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from cotes import strategie_qwen as Q
from cotes.notifications import flux
from cotes.strategie_qwen import QWEN, motif_refus_ligne, paris_qwen, suivre, valider
from cotes.strategies_prudentes import VARIANTES, selections_prudentes

NOW = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
CLE = QWEN["cle"]


def opp(**kw):
    base = dict(reference="Pinnacle", bookmaker="Betclic", sport="football", match_id="betclic|1", marche="RESULTAT_1N2",
                periode="MATCH", ligne=None, issue="DOM", cote=2.0, cote_juste=1.92, ecart=0.0417, suspect=None,
                pariable=True, domicile="Lens", exterieur="Lille", pari="Lens",
                debut=(NOW + timedelta(minutes=60)).isoformat())
    return {**base, **kw}


def pari(**kw):
    p = {**opp(), "id": "p1", "statut": "en_cours", "mise": 10, "gain": None, "detecte": (NOW - timedelta(minutes=9)).isoformat(),
         "decide_le": (NOW - timedelta(minutes=9)).isoformat(), "selections_figees": {}, "ligue": "Ligue 1",
         "preuve_prise": {"match_id_reference": "9", "ressemblance_noms": .95, "controle": {"statut": "conforme"}}}
    return {**p, **kw}


def cycle(etat, opps, minutes, paris):
    t = NOW + timedelta(minutes=minutes)
    etat, vues = suivre(etat, opps, t, f"c{minutes}")
    return etat, valider(paris, vues, t), t


def test_un_seul_cycle_ne_valide_pas_deux_cycles_consecutifs_oui():
    p = [pari()]
    etat, r1, _ = cycle({}, [opp()], 0, p)
    assert r1["validees"] == 0 and CLE not in p[0]["selections_figees"]
    etat, r2, t = cycle(etat, [opp()], 5, p)
    assert r2["validees"] == 1
    f = p[0]["selections_figees"][CLE]
    assert f["cycles"] == 2 and f["cote_confirmee"] == 2.0 and f["decide_le"].startswith("2026-10-20T12:05")
    assert paris_qwen(p) == {id(p[0])}
    _, r3, _ = cycle(etat, [opp()], 10, p)
    assert r3["validees"] == 0                                            # déjà validé : pas de doublon


def test_trou_de_plus_de_12_minutes_ou_prise_manquante_remet_le_compteur_a_zero():
    p = [pari()]
    etat, _, _ = cycle({}, [opp()], 0, p)
    etat, r, _ = cycle(etat, [opp()], 13, p)                              # trou de 13 minutes
    assert r["validees"] == 0 and etat["prises"] and list(etat["prises"].values())[0]["cycles"] == 1
    etat, _, _ = cycle(etat, [], 18, p)                                   # la prise disparaît...
    etat, r, _ = cycle(etat, [opp()], 23, p)                              # ... puis revient : repart de 1
    assert r["validees"] == 0
    etat, r, _ = cycle(etat, [opp()], 28, p)
    assert r["validees"] == 1


@pytest.mark.parametrize("changes,motif", [
    ({"reference": "Polymarket"}, "référence"), ({"bookmaker": "Unibet"}, "bookmaker"), ({"bookmaker": "PMU"}, "bookmaker"),
    ({"marche": "CORRECT_SCORE"}, "marché"), ({"marche": "TOTAL_DOM"}, "marché"), ({"periode": "MT1"}, "marché"),
    ({"sport": "tennis", "marche": "HANDICAP"}, "unité"), ({"cote": 1.44}, "cote"), ({"cote": 3.21}, "cote"),
    ({"ecart": 0.0349}, "edge"), ({"suspect": "écart trop grand"}, "suspecte"), ({"pariable": False}, "suspecte"),
])
def test_criteres_de_ligne_refuses(changes, motif):
    assert motif in motif_refus_ligne(opp(**changes))


@pytest.mark.parametrize("changes", [
    {"bookmaker": "Winamax"}, {"cote": 1.45}, {"cote": 3.20}, {"ecart": 0.035}, {"marche": "VAINQUEUR", "issue": "EXT"},
    {"marche": "HANDICAP", "ligne": -0.25}, {"marche": "TOTAL", "ligne": 2.5, "issue": "PLUS"},
    {"sport": "tennis", "marche": "VAINQUEUR"}, {"periode": "TEMPS_REG"}])
def test_criteres_de_ligne_acceptes(changes):
    assert motif_refus_ligne(opp(**changes)) is None


@pytest.mark.parametrize("minutes_avant_match,valide", [(14, False), (15, True), (60, True), (120, True), (121, False)])
def test_fenetre_de_15_minutes_a_2_heures_a_la_validation(minutes_avant_match, valide):
    debut = (NOW + timedelta(minutes=5 + minutes_avant_match)).isoformat()      # mesuré au 2ᵉ cycle (t = +5 min)
    p = [pari(debut=debut)]
    etat, _, _ = cycle({}, [opp(debut=debut)], 0, p)
    _, r, _ = cycle(etat, [opp(debut=debut)], 5, p)
    assert (r["validees"] == 1) is valide


def test_pas_de_derive_negative_cote_actuelle_au_moins_egale_a_la_cote_initiale():
    p = [pari(cote=2.0)]
    etat, _, _ = cycle({}, [opp(cote=2.0)], 0, p)
    _, r, _ = cycle(etat, [opp(cote=1.98, ecart=0.04)], 5, p)                  # la ligne a baissé : annulé
    assert r["validees"] == 0 and "cote en baisse depuis la première détection" in r["refus"]
    etat, _, _ = cycle({}, [opp(cote=2.1, ecart=0.09)], 0, p)
    _, r, _ = cycle(etat, [opp(cote=2.1, ecart=0.09)], 5, p)                   # plus haute : validé, prix du pari gardé
    assert r["validees"] == 1 and p[0]["cote"] == 2.0 and p[0]["selections_figees"][CLE]["cote_confirmee"] == 2.1


def test_maximum_3_par_jour_de_paris_et_ordre_de_validation():
    opps = [opp(match_id=f"betclic|{i}", ecart=0.05 + i / 1000) for i in range(5)]
    p = [pari(id=f"p{i}", match_id=f"betclic|{i}") for i in range(5)]
    etat, _, _ = cycle({}, opps, 0, p)
    etat, r, _ = cycle(etat, opps, 5, p)
    assert r["validees"] == 3 and r["refus"] == {"plafond de 3 paris par jour": 2}
    assert {q["id"] for q in p if CLE in q["selections_figees"]} == {"p4", "p3", "p2"}        # meilleurs edges d'abord
    suite = [pari(id="p9", match_id="betclic|9")]
    etat, r, _ = cycle(etat, [opp(match_id="betclic|9")], 10, p + suite)
    etat, r, _ = cycle(etat, [opp(match_id="betclic|9")], 15, p + suite)
    assert r["validees"] == 0                                                  # même jour : plafond atteint
    lendemain = NOW + timedelta(days=1)
    etat2, vues = suivre({"cycle_le": (lendemain - timedelta(minutes=5)).isoformat(),
                          "prises": {Q._texte_cle(suite[0]): {"cycles": 1}}}, [opp(match_id="betclic|9", debut=(lendemain + timedelta(hours=1)).isoformat())], lendemain, "j2")
    suite[0]["debut"] = (lendemain + timedelta(hours=1)).isoformat()
    assert valider(p + suite, vues, lendemain)["validees"] == 1                  # nouveau jour de Paris


def test_pari_absent_clos_ou_sans_preuve_n_est_pas_valide():
    for pari_p, motif in ((None, "pari absent du registre"), (pari(statut="gagne"), "pari clos"),
                          (pari(preuve_prise={}), "preuve de correspondance ou de conformité insuffisante"),
                          (pari(cote_juste=1.5), "edge incohérent avec la cote juste")):
        paris = [pari_p] if pari_p else []
        etat, _, _ = cycle({}, [opp()], 0, paris)
        _, r, _ = cycle(etat, [opp()], 5, paris)
        assert r["validees"] == 0 and motif in r["refus"]


def test_aucune_validation_avant_le_lancement_ni_rejeu_historique():
    p = [pari()]
    t = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
    etat, vues = suivre({"cycle_le": (t - timedelta(minutes=5)).isoformat(), "prises": {Q._texte_cle(p[0]): {"cycles": 1}}}, [opp()], t, "x")
    assert valider(p, vues, t)["validees"] == 0
    assert paris_qwen(p, depuis="2026-10-07T00:00:00+00:00") == set()


def test_variante_prospective_sans_effet_sur_les_autres_strategies_ni_sur_convergence():
    assert QWEN in VARIANTES and QWEN["prospectif_seulement"] is True
    json.dumps(QWEN)                                                            # publiable sur le site
    p = [pari()]
    p[0]["selections_figees"][CLE] = {"version": "1", "decide_le": NOW.isoformat()}
    sel = selections_prudentes(p)
    assert sel[CLE] == {id(p[0])} and selections_prudentes(p, depuis="2026-10-15T04:00:00+00:00")[CLE] == set()
    from cotes.convergence import STRATEGIES
    assert CLE not in {c for c, *_ in STRATEGIES}


def test_alerte_a_la_validation_avec_la_date_et_le_prix_du_2e_cycle():
    p = pari(cote=2.0, detecte=(NOW - timedelta(hours=2)).isoformat(), debut=(NOW + timedelta(hours=1)).isoformat())
    p["selections_figees"][CLE] = {"version": "1", "decide_le": (NOW - timedelta(minutes=1)).isoformat(), "cote_confirmee": 2.1}
    actuelle = opp(cote=2.1, debut=p["debut"], collecte_recue=(NOW - timedelta(minutes=1)).isoformat(),
                   detecte=(NOW - timedelta(minutes=1)).isoformat())
    f = flux([actuelle], [p], {CLE: {id(p)}}, NOW)
    assert [a["strategies"] for a in f["alertes"]] == [[CLE]] and f["alertes"][0]["labels"] == ["Qwen"]
    assert f["alertes"][0]["cote"] == 2.1
